"""Salary advance authorization, inbox routing, and audited decisions."""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .access import employee_for_user, user_group_names
from .models import Advance, AdvanceNotification, Employee
from .views import render_page

INBOX = "webroaster:advance_notifications"
ROLE_NAMES = {"Operations Manager", "Human Resources", "Head of Finance",
              "Finance Officer", "General Manager", "CEO", "Cashier"}
STAGE_ROLES = {
    ("staff", "approve"): "Human Resources",
    ("staff", "authorize"): "Head of Finance",
    ("staff", "pay"): "Finance Officer",
    ("head", "verify"): "General Manager",
    ("head", "approve"): "CEO",
    ("head", "pay"): "Cashier",
}
STAGE_NOTIFICATIONS = {
    "verify": ("verification_requested", "Salary advance awaiting verification"),
    "approve": ("approval_requested", "Verified salary advance awaiting approval"),
    "authorize": ("finance_update", "HR-approved salary advance awaiting payment authorization"),
    "pay": ("payment_requested", "Approved salary advance ready for payment"),
}
ACTION_LABELS = {
    "verify": "Verify", "approve": "Approve", "reject": "Reject",
    "authorize": "Authorize Payment", "pay": "Record Payment",
}


def staff_actor(user):
    if user.is_authenticated and user.is_active and user.is_staff:
        actor = employee_for_user(user)
        if actor and actor.status == "active":
            return actor
    return None


def can_open_queue(user):
    actor = staff_actor(user)
    return bool(actor and (
        user_group_names(user) & ROLE_NAMES or actor.advance_reports.exists()
    ))


def request_route(advance):
    return advance.routing_path or ("head" if advance.employee.is_department_head else "staff")


def pending_stage(advance):
    if advance.status != "pending" or advance.disbursement_date:
        return None
    if advance.approval_status == "rejected" or advance.verification_status == "rejected":
        return None
    if not advance.routing_path or advance.verification_status == "pending":
        return "verify"
    if advance.verification_status != "verified":
        return None
    if advance.approval_status == "pending":
        return "approve"
    if advance.approval_status == "approved":
        if advance.routing_path == "staff" and not advance.payment_authorized_at:
            return "authorize"
        return "pay"
    return None


def can_act(groups, actor, advance, stage):
    if not actor or actor.pk == advance.employee_id or not stage:
        return False
    if stage != "verify" and actor.pk in (
        advance.verified_by_id, advance.approved_by_id, advance.payment_authorized_by_id,
    ):
        return False

    route = request_route(advance)
    if route == "staff" and stage == "verify":
        supervisor_id = advance.employee.advance_supervisor_id
        if supervisor_id:
            return actor.pk == supervisor_id
        return advance.employee.role in {"guard", "supervisor"} and "Operations Manager" in groups
    return STAGE_ROLES.get((route, stage)) in groups


def notify_next_stage(advance):
    if not advance.pk:
        return
    stage = pending_stage(advance)
    if not stage:
        return
    role = STAGE_ROLES.get((request_route(advance), stage))
    users = get_user_model().objects.filter(is_active=True, is_staff=True)
    if role:
        users = users.filter(groups__name=role)
    elif advance.employee.advance_supervisor_id:
        supervisor = advance.employee.advance_supervisor
        linked = Q(username__iexact=supervisor.employee_number)
        if supervisor.email:
            linked |= Q(email__iexact=supervisor.email)
        users = users.filter(linked)
    elif advance.employee.role in {"guard", "supervisor"}:
        users = users.filter(groups__name="Operations Manager")
    else:
        return

    kind, message = STAGE_NOTIFICATIONS[stage]
    for user in users.distinct().prefetch_related("groups"):
        actor = staff_actor(user)
        if can_act(user_group_names(user), actor, advance, stage):
            advance.notify(actor, "Advance Workflow", kind, f"{message}: {advance.employee}.")


def advance_notifications(request):
    if not can_open_queue(request.user):
        raise PermissionDenied
    actor = staff_actor(request.user)
    groups = user_group_names(request.user)
    rows = []
    advances = Advance.objects.filter(status="pending").select_related("employee").order_by("-updated_at", "-pk")
    for advance in advances:
        stage = pending_stage(advance)
        if can_act(groups, actor, advance, stage):
            actions = ("approve", "reject") if stage == "approve" else (stage,)
            rows.append({
                "advance": advance,
                "actions": [(action, ACTION_LABELS[action]) for action in actions],
            })
    return render_page(request, "webroaster/advance_routing_notifications.html", {
        "title": "Salary Advance Notifications", "rows": rows,
    }, "advances")


@require_http_methods(["GET", "POST"])
def advance_notification_action(request, notification_id, action):
    actor = staff_actor(request.user)
    if not actor:
        raise PermissionDenied
    notification = get_object_or_404(AdvanceNotification, pk=notification_id, recipient=actor)
    return advance_workflow_action(request, notification.advance_id, action)


@require_http_methods(["GET", "POST"])
def advance_workflow_action(request, advance_id, action):
    actor = staff_actor(request.user)
    groups = user_group_names(request.user)
    if not actor:
        raise PermissionDenied
    expected = "approve" if action == "reject" else action
    if action not in ACTION_LABELS:
        raise Http404
    if request.method == "GET":
        advance = get_object_or_404(Advance.objects.select_related("employee"), pk=advance_id)
        stage = pending_stage(advance)
        if stage != expected or not can_act(groups, actor, advance, stage):
            raise Http404
        return render_page(request, "webroaster/advance_routing_review.html", {
            "title": f"{ACTION_LABELS[action]} Salary Advance",
            "decision": ACTION_LABELS[action],
            "action": action,
            "advance": advance,
            "route": request_route(advance),
        }, "advances")

    with transaction.atomic():
        advance = get_object_or_404(Advance.objects.select_for_update(), pk=advance_id)
        stage = pending_stage(advance)
        if stage != expected or not can_act(groups, actor, advance, stage):
            raise PermissionDenied("This salary advance is not awaiting an action from your account.")
        reason = request.POST.get("reason", "").strip()
        if action == "reject" and (not reason or len(reason) > 1000):
            messages.error(request, "Enter a rejection reason of up to 1,000 characters.")
            return redirect("webroaster:advance_workflow_action", advance.pk, action)

        now = timezone.now()
        if action == "verify":
            advance.routing_path = request_route(advance)
            advance.verification_status = "verified"
            advance.verified_by = actor
            advance.verified_at = now
            advance.approval_status = "pending"
            advance.approved_by = None
            advance.decision_at = None
            fields = ("routing_path", "verification_status", "verified_by", "verified_at",
                      "approval_status", "approved_by", "decision_at")
        elif action in {"approve", "reject"}:
            advance.approval_status = "approved" if action == "approve" else "rejected"
            advance.status = "pending" if action == "approve" else "rejected"
            advance.approved_by = actor
            advance.decision_at = now
            fields = ("approval_status", "status", "approved_by", "decision_at")
        elif action == "authorize":
            advance.payment_authorized_by = actor
            advance.payment_authorized_at = now
            fields = ("payment_authorized_by", "payment_authorized_at")
        else:
            advance.status = "disbursed"
            advance.disbursement_date = timezone.localdate(now)
            advance.paid_by = actor
            advance.paid_at = now
            fields = ("status", "disbursement_date", "paid_by", "paid_at")

        advance.save(update_fields=[*fields, "updated_at"])
        kind, label = STAGE_NOTIFICATIONS[stage]
        receipt = advance.notify(actor, "Advance Workflow", kind, f"{label}: {advance.employee}.")
        receipt.status = "actioned"
        receipt.decision = action
        receipt.decided_at = now
        if action == "reject":
            receipt.message = reason
        receipt.save(update_fields=["status", "decision", "decided_at", "message", "updated_at"])
        if action == "pay":
            advance.refresh_payroll()
        if action in {"approve", "reject", "pay"}:
            outcome = {"approve": "approved", "reject": "rejected", "pay": "paid"}[action]
            advance.notify(advance.employee, "Requester", f"advance_{outcome}",
                           f"Your salary advance was {outcome}." + (f" Reason: {reason}" if reason else ""))
        notify_next_stage(advance)

    messages.success(request, f"Salary advance action recorded: {ACTION_LABELS[action]}.")
    return redirect(INBOX)
