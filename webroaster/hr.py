from datetime import timedelta
from io import BytesIO
import mimetypes

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from .access import advance_notification_groups, require_model_access, require_view_access
from .finance import sync_salary_table
from .forms_hr import EmployeeDeploymentTransferForm, LeaveReviewForm
from .models import AdvanceNotification, DisciplinaryNotification, Document, Employee, JobApplication, Leave, LeaveNotification, Salary, Training
from .models import Advance
from .pdf_utils import simple_pdf_response
from .views import get_field_label, get_field_value, render_page

def document_status(document, today=None):
    today = today or timezone.localdate()
    if not document.expiry_date:
        return "No Expiry"
    if document.expiry_date < today:
        return "Expired"
    if document.expiry_date <= today + timedelta(days=30):
        return "Expiring Soon"
    return "Valid"


def document_register_context():
    today = timezone.localdate()
    documents = Document.objects.select_related("employee").order_by("employee__first_name", "employee__last_name", "doc_type", "expiry_date")
    employee_groups = []
    grouped = {}
    expired_count = 0
    expiring_count = 0
    for document in documents:
        status = document_status(document, today)
        if status == "Expired":
            expired_count += 1
        elif status == "Expiring Soon":
            expiring_count += 1
        employee = document.employee
        group = grouped.setdefault(employee.pk, {"employee": employee, "documents": []})
        group["documents"].append({"object": document, "status": status})
    employee_groups = list(grouped.values())
    return {
        "title": "Documents",
        "model_name": "documents",
        "documents": documents,
        "employee_groups": employee_groups,
        "document_count": documents.count(),
        "employee_count": len(employee_groups),
        "expired_count": expired_count,
        "expiring_count": expiring_count,
    }

def training_certificate(request, pk):
    training = get_object_or_404(Training.objects.select_related("employee"), pk=pk)
    certificate_no = training.ensure_certificate_number()
    training_manager = Employee.objects.filter(status="active", role="manager").order_by("first_name", "last_name").first()
    context = {
        "title": f"Certificate - {training.trainee}",
        "training": training,
        "certificate_no": certificate_no,
        "training_manager_name": str(training_manager) if training_manager else "Training Manager",
    }
    return render_page(request, "webroaster/training_certificate.html", context, "training")


def employee_profile_context(employee):
    profile_fields = [
        "employee_id",
        "employee_number",
        "first_name",
        "last_name",
        "date_of_birth",
        "gender",
        "phone_number",
        "email",
        "address",
        "national_id",
        "nssf_number",
        "role",
        "position",
        "department",
        "current_deployment_area",
        "daily_rate",
        "is_reliever",
        "payout_method",
        "bank_name",
        "bank_account_name",
        "bank_account_number",
        "mobile_money_provider",
        "mobile_money_number",
        "qualification",
        "hire_date",
        "status",
    ]
    details = [
        (get_field_label(Employee, field), get_field_value(employee, field))
        for field in profile_fields
    ]
    return {
        "title": f"Employee Profile - {employee}",
        "employee": employee,
        "details": details,
        "documents": Document.objects.filter(employee=employee).order_by("doc_type", "expiry_date", "-created_at")[:8],
        "trainings": Training.objects.filter(employee=employee).order_by("-start_date", "-training_id")[:5],
        "leaves": Leave.objects.filter(employee=employee).order_by("-start_date", "-leave_id")[:5],
        "salaries": Salary.objects.filter(employee=employee).order_by("-pay_period", "-salary_id")[:5],
        "deployment_areas": employee.deployment_areas.select_related("region", "transferred_by_hr_manager").order_by("-start_date", "-deployment_area_id")[:5],
    }


def employee_profile(request, pk):
    require_model_access(request, "employees")
    employee = get_object_or_404(Employee, pk=pk)
    context = employee_profile_context(employee)
    return render_page(request, "webroaster/employee_profile.html", context, "employees")


def employee_profile_pdf(request, pk):
    require_model_access(request, "employees")
    employee = get_object_or_404(Employee, pk=pk)
    context = employee_profile_context(employee)
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_RIGHT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        filename = f"employee-profile-{employee.employee_number or employee.pk}.pdf".replace(" ", "-")
        lines = [
            f"Employee: {employee}",
            f"Employee No.: {employee.employee_number or '-'}",
            f"Role: {employee.get_role_display()}",
            f"Status: {employee.get_status_display()}",
            f"Deployment Area: {employee.current_deployment_area}",
            "",
            "Employee Details",
            *[f"{label}: {value}" for label, value in context["details"]],
            "",
            "Deployment Areas",
            *[f"{area.region}: {area.start_date} to {area.end_date or 'Current'} - {area.get_status_display()}" for area in context["deployment_areas"]],
        ]
        return simple_pdf_response("Employee Profile Report", filename, lines)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"Employee Profile - {employee}",
    )
    styles = getSampleStyleSheet()
    heading = ParagraphStyle("ProfileHeading", parent=styles["Heading1"], fontSize=15, leading=18, textColor=colors.HexColor("#0f2f66"), spaceAfter=3)
    title = ParagraphStyle("ProfileTitle", parent=styles["Heading2"], fontSize=12, leading=14, textColor=colors.HexColor("#0f766e"), spaceBefore=8, spaceAfter=5)
    normal = ParagraphStyle("ProfileNormal", parent=styles["BodyText"], fontSize=8, leading=10)
    small = ParagraphStyle("ProfileSmall", parent=normal, fontSize=7, leading=9, textColor=colors.HexColor("#64748b"))
    right = ParagraphStyle("ProfileRight", parent=small, alignment=TA_RIGHT)

    def text(value):
        if value is None or value == "":
            return "-"
        return str(value)

    def p(value, style=normal):
        return Paragraph(text(value), style)

    def build_table(data, widths, header=False):
        rendered = Table(data, colWidths=widths, hAlign="LEFT", repeatRows=1 if header else 0)
        style = [
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d8e0ea")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if header:
            style.extend([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#edf2f7")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#334155")),
            ])
        rendered.setStyle(TableStyle(style))
        return rendered

    def passport_photo():
        if not employee.passport_photo:
            return p("No passport photo", small)
        try:
            image = Image(employee.passport_photo.path, width=30 * mm, height=40 * mm)
            image.hAlign = "CENTER"
            return image
        except (OSError, ValueError, AttributeError):
            return p("Passport photo unavailable", small)

    detail_rows = []
    for index in range(0, len(context["details"]), 2):
        first = context["details"][index]
        second = context["details"][index + 1] if index + 1 < len(context["details"]) else ("", "")
        detail_rows.append([p(first[0], small), p(first[1]), p(second[0], small), p(second[1])])

    story = [
        build_table([[
            [p(getattr(settings, "COMPANY_NAME", "NewCompany"), heading), p("Employee Profile Report", small)],
            [p("Generated", right), p(timezone.localtime().strftime("%Y-%m-%d %H:%M"), right)],
        ]], [125 * mm, 40 * mm]),
        Spacer(1, 6),
        build_table([[
            passport_photo(),
            [
                p(employee, heading),
                p(f"Employee No.: {employee.employee_number or '-'}", normal),
                p(f"Role: {employee.get_role_display()}", normal),
                p(f"Status: {employee.get_status_display()}", normal),
                p(f"Deployment Area: {employee.current_deployment_area}", normal),
            ],
        ]], [35 * mm, 130 * mm]),
        Paragraph("Employee Details", title),
        build_table(detail_rows, [34 * mm, 48 * mm, 34 * mm, 49 * mm]),
    ]

    story.append(Paragraph("Deployment Areas", title))
    deployment_rows = [[p("Area", small), p("Start", small), p("End", small), p("Status", small)]]
    deployment_rows.extend([[p(area.region), p(area.start_date), p(area.end_date or "Current"), p(area.get_status_display())] for area in context["deployment_areas"]])
    if len(deployment_rows) == 1:
        deployment_rows.append([p("No deployment area history."), p("-"), p("-"), p("-")])
    story.append(build_table(deployment_rows, [60 * mm, 35 * mm, 35 * mm, 35 * mm], header=True))

    story.append(Paragraph("Documents", title))
    document_rows = [[p("Document", small), p("Expiry", small), p("Status", small)]]
    document_rows.extend([[p(document.get_doc_type_display()), p(document.expiry_date or "-"), p(document_status(document))] for document in context["documents"]])
    if len(document_rows) == 1:
        document_rows.append([p("No documents recorded."), p("-"), p("-")])
    story.append(build_table(document_rows, [75 * mm, 45 * mm, 45 * mm], header=True))

    story.append(Paragraph("Training", title))
    training_rows = [[p("Training", small), p("Period", small), p("Status", small)]]
    training_rows.extend([[p(training.get_training_name_display()), p(f"{training.start_date} to {training.end_date}"), p(training.status)] for training in context["trainings"]])
    if len(training_rows) == 1:
        training_rows.append([p("No training records."), p("-"), p("-")])
    story.append(build_table(training_rows, [75 * mm, 55 * mm, 35 * mm], header=True))

    story.append(Paragraph("Leave And Salary", title))
    summary_rows = [[p("Type", small), p("Period", small), p("Status / Amount", small)]]
    summary_rows.extend([[p(leave.get_leave_type_display()), p(f"{leave.start_date} to {leave.end_date}"), p(leave.get_approval_status_display())] for leave in context["leaves"]])
    summary_rows.extend([[p("Salary"), p(salary.get_pay_period_display()), p(f"Total: {salary.total_salary}")] for salary in context["salaries"]])
    if len(summary_rows) == 1:
        summary_rows.append([p("No leave or salary records."), p("-"), p("-")])
    story.append(build_table(summary_rows, [48 * mm, 62 * mm, 55 * mm], header=True))

    doc.build(story)
    filename = f"employee-profile-{employee.employee_number or employee.pk}.pdf".replace(" ", "-")
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response

def employee_transfer(request, pk):
    require_model_access(request, "employees")
    employee = get_object_or_404(Employee, pk=pk, role__in=("guard", "supervisor"))
    form = EmployeeDeploymentTransferForm(request.POST or None, employee=employee)

    if request.method == "POST" and form.is_valid():
        new_area = form.save()
        sync_salary_table()
        messages.success(request, f"{employee} transferred to {new_area.region} successfully.")
        return redirect("webroaster:detail", model_name="employees", pk=employee.pk)

    context = {
        "model_name": "employees",
        "title": f"Transfer {employee}",
        "form": form,
        "object": employee,
        "pk": employee.pk,
        "submit_label": "Transfer",
    }
    return render_page(request, "webroaster/model_form.html", context, "employees")


def job_application_resume(request, pk):
    require_model_access(request, "job-applications")
    application = get_object_or_404(JobApplication, pk=pk)
    if not application.resume:
        raise Http404("This application has no resume attached.")
    filename = application.resume.name.rsplit("/", 1)[-1]
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return FileResponse(
        application.resume.open("rb"),
        as_attachment=request.GET.get("download") == "1",
        filename=filename,
        content_type=content_type,
    )

def build_leave_feedback_message(leave):
    decision = leave.get_approval_status_display()
    operations_status = leave.get_operations_verification_status_display()
    return (
        f"Your {leave.get_leave_type_display()} request from {leave.start_date} to {leave.end_date} has been {decision}.\n\n"
        f"Operations verification: {operations_status}.\n"
        f"Operations feedback: {leave.operations_feedback or '-'}\n"
        f"Human Resource feedback: {leave.feedback or '-'}"
    )


def deliver_leave_feedback(leave):
    if not leave.employee.email:
        return False, "Employee has no email address; feedback was saved on the leave request."
    try:
        send_mail(
            subject=f"Leave request {leave.get_approval_status_display()}",
            message=build_leave_feedback_message(leave),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[leave.employee.email],
            fail_silently=False,
        )
    except Exception as exc:
        return False, f"Feedback was saved, but email delivery failed: {str(exc)[:255]}"
    return True, "Feedback email sent to the employee."


def leave_review(request, pk):
    require_model_access(request, "leaves")
    leave = get_object_or_404(Leave.objects.select_related("employee", "verified_by", "approved_by"), pk=pk)
    form = LeaveReviewForm(request.POST or None, leave=leave)

    if request.method == "POST" and form.is_valid():
        leave = form.save()
        delivered, delivery_message = deliver_leave_feedback(leave)
        if delivered:
            messages.success(request, f"Leave request reviewed successfully. {delivery_message}")
        else:
            messages.warning(request, f"Leave request reviewed successfully. {delivery_message}")
        return redirect("webroaster:detail", model_name="leaves", pk=leave.pk)

    context = {
        "model_name": "leaves",
        "title": f"Review Leave - {leave.employee}",
        "form": form,
        "object": leave,
        "pk": leave.pk,
        "submit_label": "Submit Review",
    }
    return render_page(request, "webroaster/model_form.html", context, "leaves")


def leave_notifications(request):
    require_view_access(request, "leave_notifications")
    notifications = LeaveNotification.objects.select_related(
        "leave",
        "leave__employee",
        "recipient",
    ).order_by("-notified_at", "-notification_id")
    context = {
        "title": "Leave Notifications",
        "notifications": notifications,
    }
    return render_page(request, "webroaster/leave_notifications.html", context, "leaves")


def leave_notification_action(request, notification_id, action):
    require_view_access(request, "leave_notification_action")
    notification = get_object_or_404(
        LeaveNotification.objects.select_related("leave", "leave__employee", "recipient"),
        pk=notification_id,
    )
    leave = notification.leave
    actor = notification.recipient

    if request.method != "POST":
        return redirect("webroaster:leave_notifications")

    now = timezone.now()
    if action == "verify":
        if not notification.can_verify:
            messages.error(request, "This leave request cannot be verified from this notification.")
            return redirect("webroaster:leave_notifications")
        leave.operations_verification_status = "verified"
        leave.verified_by = actor
        leave.operations_feedback = leave.operations_feedback or "Verified from leave notification."
        leave.operations_verified_at = now
        leave.save(update_fields=["operations_verification_status", "verified_by", "operations_feedback", "operations_verified_at", "updated_at"])
        leave.notify(leave.employee, "Requester", "leave_verified", f"Your leave request from {leave.start_date} to {leave.end_date} has been verified.")
        messages.success(request, "Leave request verified.")
    elif action == "approve":
        if not notification.can_approve:
            messages.error(request, "This leave request must be verified before approval.")
            return redirect("webroaster:leave_notifications")
        leave.approval_status = "approved"
        leave.approved_by = actor
        leave.feedback = leave.feedback or "Approved from leave notification."
        leave.hr_decided_at = now
        leave.save(update_fields=["approval_status", "approved_by", "feedback", "hr_decided_at", "updated_at"])
        leave.notify(leave.employee, "Requester", "leave_approved", f"Your leave request from {leave.start_date} to {leave.end_date} has been approved.")
        deliver_leave_feedback(leave)
        messages.success(request, "Leave request approved.")
    elif action == "reject":
        if not notification.can_reject:
            messages.error(request, "This leave request cannot be rejected from this notification.")
            return redirect("webroaster:leave_notifications")
        if notification.recipient_group == "Verifier" and leave.operations_verification_status == "pending":
            leave.operations_verification_status = "rejected"
            leave.verified_by = actor
            leave.operations_feedback = leave.operations_feedback or "Rejected from leave notification."
            leave.operations_verified_at = now
        leave.approval_status = "rejected"
        leave.approved_by = actor
        leave.feedback = leave.feedback or "Rejected from leave notification."
        leave.hr_decided_at = now
        leave.save(update_fields=["operations_verification_status", "verified_by", "operations_feedback", "operations_verified_at", "approval_status", "approved_by", "feedback", "hr_decided_at", "updated_at"])
        leave.notify(leave.employee, "Requester", "leave_rejected", f"Your leave request from {leave.start_date} to {leave.end_date} has been rejected.")
        deliver_leave_feedback(leave)
        messages.success(request, "Leave request rejected.")
    else:
        messages.error(request, "Unknown leave decision.")
        return redirect("webroaster:leave_notifications")

    notification.status = "actioned"
    notification.decision = action
    notification.decided_at = now
    notification.save(update_fields=["status", "decision", "decided_at", "updated_at"])
    return redirect("webroaster:leave_notifications")


def advance_notifications(request):
    require_view_access(request, "advance_notifications")
    notifications = AdvanceNotification.objects.select_related(
        "advance", "advance__employee", "recipient"
    ).order_by("-notified_at", "-notification_id")
    notification_groups = advance_notification_groups(request.user)
    if notification_groups is not None:
        notifications = notifications.filter(recipient_group__in=notification_groups)
    return render_page(request, "webroaster/advance_notifications.html", {
        "title": "Salary Advance Notifications",
        "notifications": notifications,
    }, "advances")


def advance_notification_action(request, notification_id, action):
    require_view_access(request, "advance_notification_action")
    notification = get_object_or_404(
        AdvanceNotification.objects.select_related("advance", "advance__employee", "recipient"),
        pk=notification_id,
    )
    notification_groups = advance_notification_groups(request.user)
    if notification_groups is not None and notification.recipient_group not in notification_groups:
        messages.error(request, "You cannot act on this advance notification.")
        return redirect("webroaster:advance_notifications")
    if request.method != "POST":
        return redirect("webroaster:advance_notifications")
    allowed_action = (
        action == "verify" and notification.can_verify
    ) or (
        action in ("approve", "reject") and notification.can_approve
    ) or (
        action == "pay" and notification.can_pay
    )
    if not allowed_action:
        messages.error(request, "This salary advance cannot be changed from this notification.")
        return redirect("webroaster:advance_notifications")

    advance = notification.advance
    now = timezone.now()
    with transaction.atomic():
        if action == "verify":
            advance.verification_status = "verified"
            advance.verified_by = notification.recipient
            advance.verified_at = now
            advance.save(update_fields=["verification_status", "verified_by", "verified_at", "updated_at"])
            advance.notify_hr_for_approval()
            notification_type = "advance_verified"
            outcome = "verified"
        elif action == "approve":
            advance.approval_status = "approved"
            advance.status = "disbursed"
            advance.disbursement_date = advance.disbursement_date or timezone.localdate()
            advance.approved_by = notification.recipient
            advance.save(update_fields=["approval_status", "status", "disbursement_date", "approved_by", "updated_at"])
            advance.refresh_payroll()
            notification_type = "advance_approved"
            outcome = "approved"
            finance_message = f"Salary advance for {advance.employee} was approved by HR and disbursed."
            finance_staff = Employee.objects.filter(status="active").filter(
                Q(role__in=("finance_officer", "administrator", "manager")) | Q(department="finance")
            ).distinct()
            for employee in finance_staff:
                advance.notify(employee, "Finance", "finance_update", finance_message)
            advance.notify(advance.employee, "Requester", notification_type, f"Your salary advance request of UGX {advance.amount_requested:,.2f} was approved.")
        elif action == "reject":
            advance.approval_status = "rejected"
            advance.status = "rejected"
            advance.approved_by = notification.recipient
            advance.save(update_fields=["approval_status", "status", "approved_by", "updated_at"])
            notification_type = "advance_rejected"
            outcome = "rejected"
            advance.refresh_payroll()
            advance.notify(advance.employee, "Requester", notification_type, f"Your salary advance request of UGX {advance.amount_requested:,.2f} was rejected.")
        else:
            advance.status = "disbursed"
            advance.disbursement_date = advance.disbursement_date or timezone.localdate()
            advance.save(update_fields=["status", "disbursement_date", "updated_at"])
            advance.refresh_payroll()
            advance.notify(advance.employee, "Requester", "advance_paid", f"Your salary advance of UGX {advance.amount_requested:,.2f} has been paid by Finance.")
            notification_type = "advance_paid"
            outcome = "paid"
        notification.status = "actioned"
        notification.decision = action
        notification.decided_at = now
        notification.save(update_fields=["status", "decision", "decided_at", "updated_at"])

    if action == "verify":
        messages.success(request, "Salary advance verified and sent to Human Resource for approval.")
    elif action == "approve":
        messages.success(request, "Salary advance approved and sent to Finance for payment.")
    elif action == "pay":
        messages.success(request, "Salary advance paid and payroll was updated.")
    else:
        messages.success(request, "Salary advance rejected and payroll was updated.")
    return redirect("webroaster:advance_notifications")


def disciplinary_action_has_feedback(action):
    return bool(action.steps_taken or action.conclusion or action.outcome != "pending")


def build_disciplinary_feedback_message(action):
    lines = [
        f"Disciplinary feedback for {action.employee}.",
        f"Offence committed: {action.offence_committed}.",
        f"Status: {action.get_status_display()}.",
    ]
    if action.steps_taken:
        lines.append(f"Steps taken: {action.steps_taken}")
    if action.outcome != "pending":
        lines.append(f"Outcome: {action.get_outcome_display()}.")
    if action.conclusion:
        lines.append(f"Conclusion: {action.conclusion}")
    if action.handled_by_id:
        lines.append(f"Handled by: {action.handled_by}.")
    return "\n".join(lines)


def deliver_disciplinary_notification(notification):
    if not notification.recipient.email:
        notification.status = "pending"
        notification.delivery_note = "Recipient has no email address. Message saved in disciplinary notifications."
        notification.save(update_fields=["status", "delivery_note", "updated_at"])
        return False

    try:
        send_mail(
            subject=f"Disciplinary feedback: {notification.disciplinary_action.offence_committed}",
            message=notification.message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[notification.recipient.email],
            fail_silently=False,
        )
        notification.status = "sent"
        notification.delivery_note = "Feedback message sent to employee."
    except Exception as exc:
        notification.status = "failed"
        notification.delivery_note = str(exc)[:255]
    notification.notified_at = timezone.now()
    notification.save(update_fields=["status", "delivery_note", "notified_at", "updated_at"])
    return notification.status == "sent"


def notify_disciplinary_employee(action):
    if not disciplinary_action_has_feedback(action):
        return None
    notification, _created = DisciplinaryNotification.objects.update_or_create(
        disciplinary_action=action,
        recipient=action.employee,
        defaults={
            "message": build_disciplinary_feedback_message(action),
            "status": "pending",
            "delivery_note": "",
            "notified_at": timezone.now(),
        },
    )
    deliver_disciplinary_notification(notification)
    return notification


def disciplinary_notifications(request):
    notifications = DisciplinaryNotification.objects.select_related(
        "disciplinary_action",
        "recipient",
    ).order_by("-notified_at", "-notification_id")
    context = {
        "title": "Disciplinary Notifications",
        "notifications": notifications,
    }
    return render_page(request, "webroaster/disciplinary_notifications.html", context, "disciplinary-actions")

