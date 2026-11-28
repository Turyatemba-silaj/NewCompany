from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect

ROLE_GROUPS = {
    "Supervisor": {
        "models": {"attendance", "deployments"},
        "views": {"leave_notifications", "leave_notification_action", "supervisor_checklist"},
    },
    "Human Resources": {
        "models": {
            "employees",
            "guards",
            "supervisors",
            "training",
            "leaves",
            "disciplinary-actions",
            "performance-evaluations",
            "documents",
            "job-postings",
            "job-applications",
            "job-application-notifications",
            "payroll",
            "salaries",
            "advances",
            "payroll-deductions",
        },
        "views": {"guard_report", "leave_notifications", "leave_notification_action", "advance_notifications", "advance_notification_action", "payroll"},
    },
    "Operations Manager": {
        "models": {
            "clients",
            "contracts",
            "regions",
            "sites",
            "shifts",
            "assets",
            "asset-assignments",
            "incidents",
            "deployments",
            "deployment-areas",
            "attendance",
        },
        "views": {
            "asset_assignment_report",
            "asset_store_report",
            "contract_report",
            "contract_management_report",
            "duty_roster_export",
            "duty_roster_upload",
            "incident_notifications",
            "incident_manage",
            "incident_notify",
            "incident_report",
            "leave_notifications",
            "leave_notification_action",
            "supervisor_checklist",
            "advance_notifications",
            "advance_notification_action",
        },
    },
    "Finance Officer": {
        "models": {
            "payroll",
            "salaries",
            "advances",
            "payroll-deductions",
            "procurement",
            "suppliers",
            "procurement-requisitions",
            "procurement-approvals",
            "proforma-item-prices",
            "supplier-proformas",
            "purchase-orders",
            "goods-received-notes",
            "supplier-invoices",
            "supplier-payments",
            "procurement-notifications",
            "invoices",
            "paymees",
            "payments",
            "budgets",
            "expenses",
        },
        "views": {
            "aging_report",
            "contract_management_report",
            "advance_notifications",
            "advance_notification_action",
            "budget_notifications",
            "budget_report",
            "expense_notifications",
            "expense_report",
            "invoice_document",
            "payment_receipt",
            "payment_reconciliation",
            "payout_api_batch",
            "payout_api_index",
            "procurement",
            "procurement_api_detail",
            "procurement_api_index",
            "procurement_api_list",
            "procurement_contact_supplier",
            "procurement_notification_action",
        },
    },
}

ROLE_GROUPS["Head of Finance"] = {
    "models": set(ROLE_GROUPS["Finance Officer"]["models"]),
    "views": set(ROLE_GROUPS["Finance Officer"]["views"]),
}
MODEL_PERMISSION_NAMES = {
    "attendance": "attendance",
    "employees": "employee",
    "guards": "guard",
    "supervisors": "supervisor",
    "training": "training",
    "leaves": "leave",
    "disciplinary-actions": "disciplinary_action",
    "performance-evaluations": "performance_evaluation",
    "documents": "document",
    "job-postings": "jobposting",
    "job-applications": "jobapplication",
    "job-application-notifications": "jobapplicationnotification",
    "salaries": "salary",
    "advances": "advance",
    "payroll-deductions": "payrolldeduction",
    "clients": "client",
    "contracts": "contract",
    "regions": "region",
    "sites": "site",
    "shifts": "shift",
    "assets": "asset",
    "asset-assignments": "assetassignment",
    "incidents": "incident",
    "deployments": "deployment",
    "deployment-areas": "deploymentarea",
    "suppliers": "supplier",
    "procurement-requisitions": "procurementrequisition",
    "procurement-approvals": "procurementapproval",
    "proforma-item-prices": "supplierproformaitemprice",
    "supplier-proformas": "supplierproformainvoice",
    "purchase-orders": "purchaseorder",
    "goods-received-notes": "goodsreceivednote",
    "supplier-invoices": "supplierinvoice",
    "supplier-payments": "supplierpayment",
    "procurement-notifications": "procurementnotification",
    "invoices": "invoice",
    "paymees": "paymee",
    "payments": "payment",
    "budgets": "budget",
    "expenses": "expense",
}

ROLE_PERMISSION_ACTIONS = ("view", "add", "change", "delete")
ROLE_ADVANCE_PERMISSIONS = {
    "Operations Manager": "verify_advance",
    "Human Resources": "approve_advance",
    "Finance Officer": "pay_advance",
}


def role_group_permission_queryset(group_or_name):
    group_name = getattr(group_or_name, "name", group_or_name) or ""
    model_slugs = ROLE_GROUPS.get(group_name, {}).get("models", set())
    model_names = [MODEL_PERMISSION_NAMES[slug] for slug in model_slugs if slug in MODEL_PERMISSION_NAMES]
    codenames = []
    for model_name in model_names:
        codenames.extend(f"{action}_{model_name}" for action in ROLE_PERMISSION_ACTIONS)
    advance_permission = ROLE_ADVANCE_PERMISSIONS.get(group_name)
    if advance_permission:
        codenames.append(advance_permission)
    return Permission.objects.filter(content_type__app_label="webroaster", codename__in=codenames)


def sync_role_group_permissions(group):
    return role_group_permission_queryset(group)


def sync_role_groups():
    groups = []
    for group_name in ROLE_GROUPS:
        group, _created = Group.objects.get_or_create(name=group_name)
        groups.append(group)
    return groups

def user_group_names(user):
    if not getattr(user, "is_authenticated", False):
        return set()
    return set(user.groups.values_list("name", flat=True))


def user_allowed_models(user):
    if not getattr(user, "is_authenticated", False):
        return set()
    group_names = user_group_names(user)
    if user.is_superuser:
        return None
    restricted_groups = group_names.intersection(ROLE_GROUPS)
    if not restricted_groups:
        return set()
    allowed = set()
    for group_name in restricted_groups:
        allowed.update(ROLE_GROUPS[group_name].get("models", set()))
    return allowed


def user_allowed_views(user):
    if not getattr(user, "is_authenticated", False):
        return set()
    group_names = user_group_names(user)
    if user.is_superuser:
        return None
    restricted_groups = group_names.intersection(ROLE_GROUPS)
    if not restricted_groups:
        return set()
    allowed = set()
    for group_name in restricted_groups:
        allowed.update(ROLE_GROUPS[group_name].get("views", set()))
    return allowed


def advance_notification_groups(user):
    allowed = set()
    if user.has_perm("webroaster.verify_advance"):
        allowed.add("Supervisor")
    if user.has_perm("webroaster.approve_advance"):
        allowed.update({"HR Officer", "HR Approver"})
    if user.has_perm("webroaster.pay_advance"):
        allowed.add("Finance")
    return allowed


def leave_notification_groups(user):
    if getattr(user, "is_superuser", False):
        return None
    groups = user_group_names(user)
    if not groups.intersection(ROLE_GROUPS):
        return set()
    allowed = set()
    if "Supervisor" in groups or "Operations Manager" in groups:
        allowed.add("Verifier")
        allowed.add("Stand-In")
    if "Human Resources" in groups:
        allowed.add("Approver")
    return allowed


def employee_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return None
    from .models import Employee

    email_key = (getattr(user, "email", "") or "").strip()
    username_key = (getattr(user, "username", "") or "").strip()
    if email_key:
        employee = Employee.objects.filter(email__iexact=email_key).first()
        if employee:
            return employee
    if username_key:
        employee = Employee.objects.filter(employee_number__iexact=username_key).first()
        if employee:
            return employee
    return None


def notification_actor_for_user(user, notification):
    if getattr(user, "is_superuser", False):
        return notification.recipient
    employee = employee_for_user(user)
    if employee:
        return employee if employee.pk == notification.recipient_id else None
    if user_allowed_views(user) is not None:
        return None
    return notification.recipient


def can_access_model(user, model_name):
    allowed = user_allowed_models(user)
    return allowed is None or model_name in allowed


def can_access_view(user, view_name):
    allowed = user_allowed_views(user)
    return allowed is None or view_name in allowed


def _active_employee_for_workflow(user, advance):
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return None
    employee = employee_for_user(user)
    if not employee or employee.status != "active" or employee.pk == advance.employee_id:
        return None
    return employee


def can_verify_advance(user, advance):
    return bool(
        getattr(user, "is_authenticated", False)
        and user.has_perm("webroaster.verify_advance")
        and _active_employee_for_workflow(user, advance)
        and advance.verification_status == "pending"
        and advance.approval_status == "pending"
        and advance.status == "pending"
    )


def can_approve_advance(user, advance):
    return bool(
        getattr(user, "is_authenticated", False)
        and user.has_perm("webroaster.approve_advance")
        and _active_employee_for_workflow(user, advance)
        and advance.verification_status == "verified"
        and advance.approval_status == "pending"
        and advance.status == "pending"
    )


def can_pay_advance(user, advance):
    return bool(
        getattr(user, "is_authenticated", False)
        and user.has_perm("webroaster.pay_advance")
        and _active_employee_for_workflow(user, advance)
        and advance.verification_status == "verified"
        and advance.approval_status == "approved"
        and advance.status == "pending"
    )


def _access_actor_has_permission(actor, permission):
    return bool(
        actor
        and actor.is_authenticated
        and actor.is_active
        and actor.is_staff
        and (actor.is_superuser or actor.has_perm(permission))
    )


def change_user_access(
    actor,
    user,
    *,
    groups=None,
    permissions=None,
    is_active=None,
    action="update_user_access",
    system_termination=False,
):
    termination_event = (
        system_termination
        and actor is None
        and action == "deactivate_terminated_employee"
        and is_active is False
        and groups is None
        and permissions is None
    )
    if not termination_event and not _access_actor_has_permission(actor, "auth.change_user"):
        raise PermissionDenied("You are not authorized to change user access.")

    from .models import AccessChangeLog

    User = get_user_model()
    with transaction.atomic():
        target = User.objects.select_for_update().get(pk=user.pk)
        previous = {
            "groups": sorted(target.groups.values_list("name", flat=True)),
            "permissions": sorted(
                target.user_permissions.values_list("codename", flat=True)
            ),
            "is_active": target.is_active,
        }
        if groups is not None:
            target.groups.set(groups)
        if permissions is not None:
            target.user_permissions.set(permissions)
        if is_active is not None:
            target.is_active = is_active
            target.save(update_fields=["is_active"])
        current = {
            "groups": sorted(target.groups.values_list("name", flat=True)),
            "permissions": sorted(
                target.user_permissions.values_list("codename", flat=True)
            ),
            "is_active": target.is_active,
        }
        if previous != current:
            AccessChangeLog.objects.create(
                actor=actor,
                affected_user=target,
                action=action,
                previous_values=previous,
                new_values=current,
            )
    return target


def change_group_permissions(actor, group, permissions, *, adding=False):
    permission = "auth.add_group" if adding else "auth.change_group"
    if not _access_actor_has_permission(actor, permission):
        raise PermissionDenied("You are not authorized to change group permissions.")

    from .models import AccessChangeLog

    with transaction.atomic():
        target = Group.objects.select_for_update().get(pk=group.pk)
        previous = sorted(
            target.permissions.values_list("content_type__app_label", "codename")
        )
        target.permissions.set(permissions)
        current = sorted(
            target.permissions.values_list("content_type__app_label", "codename")
        )
        if previous != current:
            AccessChangeLog.objects.create(
                actor=actor,
                affected_group=target,
                action="update_group_permissions",
                previous_values={"permissions": previous},
                new_values={"permissions": current},
            )
    return target


def provision_user(actor, *, username, first_name, last_name, email, group, permissions):
    if not _access_actor_has_permission(actor, "auth.add_user"):
        raise PermissionDenied("You are not authorized to provision user accounts.")

    from .models import AccessChangeLog

    User = get_user_model()
    with transaction.atomic():
        user = User(
            username=username,
            first_name=first_name,
            last_name=last_name,
            email=email,
            is_staff=True,
            is_active=True,
            is_superuser=False,
        )
        user.set_unusable_password()
        user.save()
        if group:
            user.groups.set([group])
        user.user_permissions.set(permissions)
        AccessChangeLog.objects.create(
            actor=actor,
            affected_user=user,
            action="invite_user",
            previous_values={},
            new_values={
                "groups": [group.name] if group else [],
                "permissions": sorted(
                    user.user_permissions.values_list("codename", flat=True)
                ),
                "is_active": user.is_active,
            },
        )
    return user


def deactivate_for_termination(user):
    if not user.is_active:
        return False

    change_user_access(
        None,
        user,
        is_active=False,
        action="deactivate_terminated_employee",
        system_termination=True,
    )
    return True


def require_model_access(request, model_name):
    if not can_access_model(request.user, model_name):
        raise PermissionDenied("You do not have permission to open this module.")


def require_view_access(request, view_name):
    if not can_access_view(request.user, view_name):
        raise PermissionDenied("You do not have permission to open this page.")


def first_allowed_model(user):
    allowed = user_allowed_models(user)
    if allowed is None:
        return None
    preferred = [
        "attendance",
        "employees",
        "payroll",
        "clients",
        "procurement",
        "invoices",
        "payments",
        "budgets",
    ]
    for model_name in preferred:
        if model_name in allowed:
            return model_name
    return next(iter(sorted(allowed)), None)


def redirect_to_first_allowed_module(user):
    model_name = first_allowed_model(user)
    if model_name:
        return redirect("webroaster:list", model_name=model_name)
    raise PermissionDenied("No modules are assigned to this account.")


