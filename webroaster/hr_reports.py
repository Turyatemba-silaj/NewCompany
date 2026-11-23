import csv
from collections import defaultdict
from datetime import date, timedelta

from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_safe

from .models import (
    Attendance, Deployment, Disciplinary_Action, Document, Employee,
    EmployeeComplianceRecord, ExitClearance, JobApplication, Leave,
    Performance_Evaluation, Salary, Training,
)
from .templatetags.hr_report_access import can_open_hr_reports
from .views import render_page


REPORTS = {
    "staff": ("Staff Nominal Roll", ("Position", "Hired on", "Employee status", "Deployment sites"), False),
    "attendance": ("Attendance & Shifts Worked", ("Recorded scheduled shifts", "Worked shifts", "Replacement shifts worked", "Scheduled shifts missed"), True),
    "leave": ("Leave & Availability", ("Leave type", "Start", "End", "Calendar days in period", "Operations verification", "HR approval", "Expected return"), True),
    "contracts": ("Employment Contract Expiry", ("Document recorded", "Recorded end date", "Days remaining", "Expiry status"), False),
    "compliance": ("Documents & Compliance", ("Record type", "Expiry date", "Days remaining", "Expiry status", "Verification"), False),
    "recruitment": ("Recruitment", ("Applicant", "Vacancy", "Hiring department", "Application channel", "Submitted", "Application status"), True),
    "training": ("Training & Certification", ("Recruit", "Course", "Provider", "Start", "Completion date", "Certificate number"), True),
    "performance": ("Performance Appraisals", ("Review start", "Review end", "Review date", "Rating", "Overall score", "Evaluator", "Improvement areas", "Status"), True),
    "discipline": ("Disciplinary Cases", ("Case reference", "Offence", "Offence date", "Hearing date", "Case status", "Outcome", "Closed on"), True),
    "movements": ("Staff Starts & Exit Clearances", ("Event", "Date", "Employee status", "Clearance status"), True),
    "payroll": ("Payroll Exceptions", ("Exception", "Date", "Details"), True),
}
IDENTITY = ("Employee number", "Employee name", "Department")


def employee_cells(employee):
    if employee is None:
        return ("", "", "")
    return (employee.employee_number, f"{employee.first_name} {employee.last_name}", employee.get_department_display())


def date_filter(params, name, fallback):
    try:
        return date.fromisoformat(params.get(name, ""))
    except ValueError:
        return fallback


def recorded_date(value):
    return timezone.localdate(value) if timezone.is_aware(value) else value.date()


def expiry_cells(end, today):
    if end is None:
        return (None, None, "No expiry recorded")
    days = (end - today).days
    status = "Expired" if days < 0 else "Expiring soon" if days <= 30 else "Current"
    return (end, days, status)


def attendance_counts(start, end):
    counts = defaultdict(lambda: [0, 0, 0, 0])
    records = Attendance.objects.filter(date__range=(start, end)).values_list(
        "scheduled_guard_id", "attended_guard_id", "employee_id", "present"
    )
    for scheduled, actual, employee, present in records.iterator():
        worker = (actual or employee) if present else None
        if scheduled:
            counts[scheduled][0] += 1
            if worker != scheduled:
                counts[scheduled][3] += 1
        if worker:
            counts[worker][1] += 1
            if scheduled and worker != scheduled:
                counts[worker][2] += 1
    return counts


def report_rows(key, employees, start, end, today, department):
    if key == "staff":
        sites_by_employee = defaultdict(set)
        deployments = Deployment.objects.filter(status="active", start_date__lte=today).exclude(
            end_date__lt=today
        ).select_related("site").prefetch_related("day_guards", "night_guards")
        for deployment in deployments:
            staff_ids = {guard.pk for guard in deployment.day_guards.all()}
            staff_ids.update(guard.pk for guard in deployment.night_guards.all())
            staff_ids.add(deployment.guard_id)
            for employee_id in staff_ids:
                sites_by_employee[employee_id].add(deployment.site.site_name)
        for employee in employees:
            yield (*employee_cells(employee), employee.get_position_display(), employee.hire_date,
                   employee.get_status_display(), ", ".join(sorted(sites_by_employee[employee.pk])))
        return

    if key == "attendance":
        counts = attendance_counts(start, end)
        for employee in employees.filter(pk__in=counts):
            yield (*employee_cells(employee), *counts[employee.pk])
        return

    if key == "leave":
        leaves = Leave.objects.filter(employee__in=employees, start_date__lte=end, end_date__gte=start)
        for leave in leaves.select_related("employee").order_by("start_date", "pk"):
            days = (min(end, leave.end_date) - max(start, leave.start_date)).days + 1
            expected_return = None
            if leave.approval_status == "approved" and leave.end_date < date.max:
                expected_return = leave.end_date + timedelta(days=1)
            yield (*employee_cells(leave.employee), leave.get_leave_type_display(), leave.start_date,
                   leave.end_date, days, leave.get_operations_verification_status_display(),
                   leave.get_approval_status_display(), expected_return)
        return

    if key in {"contracts", "compliance"}:
        documents = Document.objects.filter(employee__in=employees).select_related("employee").order_by("employee__employee_number", "expiry_date", "pk")
        if key == "contracts":
            for doc in documents.filter(doc_type="contract"):
                yield (*employee_cells(doc.employee), recorded_date(doc.created_at),
                       *expiry_cells(doc.expiry_date, today))
            for employee in employees.filter(status="active").exclude(documents__doc_type="contract"):
                yield (*employee_cells(employee), None, None, None, "No contract document")
        else:
            for doc in documents:
                yield (*employee_cells(doc.employee), doc.get_doc_type_display(),
                       *expiry_cells(doc.expiry_date, today), "Not recorded")
            for record in EmployeeComplianceRecord.objects.filter(employee__in=employees).select_related("employee").order_by("employee__employee_number", "pk"):
                yield (*employee_cells(record.employee), record.get_compliance_type_display(),
                       *expiry_cells(record.expiry_date, today), record.get_status_display())
            for employee in employees.filter(status="active", documents__isnull=True, compliance_records__isnull=True):
                yield (*employee_cells(employee), "No documents or compliance records", None, None, "No document records", "")
        return

    if key == "recruitment":
        applications = JobApplication.objects.filter(submitted_at__date__range=(start, end)).select_related("job")
        if department:
            applications = applications.filter(job__department__iexact=dict(Employee.DEPARTMENT_CHOICES)[department])
        for application in applications.order_by("submitted_at", "pk"):
            yield (application.applicant_name, application.job.title, application.job.department,
                   application.get_application_mode_display(), recorded_date(application.submitted_at),
                   application.get_status_display())
        return

    if key == "training":
        records = Training.objects.filter(end_date__range=(start, end), employee__in=employees)
        if not department:
            records = Training.objects.filter(end_date__range=(start, end))
        for record in records.select_related("employee").order_by("end_date", "pk"):
            yield (*employee_cells(record.employee), record.recruit, record.get_training_name_display(),
                   record.provider, record.start_date, record.end_date, record.certificate_no)
        return

    if key == "performance":
        records = Performance_Evaluation.objects.filter(employee__in=employees, date__range=(start, end))
        for record in records.select_related("employee", "evaluated_by").order_by("date", "pk"):
            evaluator = employee_cells(record.evaluated_by)[1]
            yield (*employee_cells(record.employee), record.review_period_start, record.review_period_end,
                   record.date, record.get_rating_display(), record.overall_score, evaluator,
                   record.areas_for_improvement, record.get_status_display())
        return

    if key == "discipline":
        records = Disciplinary_Action.objects.filter(employee__in=employees, offence_date__range=(start, end))
        for record in records.select_related("employee").order_by("offence_date", "pk"):
            yield (*employee_cells(record.employee), record.pk, record.offence_committed, record.offence_date,
                   record.hearing_date, record.get_status_display(), record.get_outcome_display(), record.concluded_on)
        return

    starters = employees.filter(hire_date__range=(start, end)).order_by("hire_date", "pk")
    exits = ExitClearance.objects.filter(employee__in=employees, clearance_date__range=(start, end))
    exits = exits.select_related("employee").order_by("clearance_date", "pk")
    if key == "movements":
        for employee in starters:
            yield (*employee_cells(employee), "Hire", employee.hire_date, employee.get_status_display(), "")
        for record in exits:
            yield (*employee_cells(record.employee), "Exit clearance", record.clearance_date,
                   record.employee.get_status_display(), record.get_status_display())
        return

    for employee in starters:
        yield (*employee_cells(employee), "New starter", employee.hire_date, "")
    for record in exits:
        yield (*employee_cells(record.employee), "Exit clearance", record.clearance_date, record.get_status_display())
    salary_employees = Salary.objects.values("employee_id")
    for employee in employees.filter(status="active", hire_date__lte=end).exclude(pk__in=salary_employees):
        yield (*employee_cells(employee), "Active employee without salary record", None, "")
    unpaid = Leave.objects.filter(
        employee__in=employees, leave_type="unpaid", approval_status="approved",
        start_date__lte=end, end_date__gte=start,
    )
    for leave in unpaid.select_related("employee").order_by("start_date", "pk"):
        yield (*employee_cells(leave.employee), "Approved unpaid leave", leave.start_date, f"Ends {leave.end_date}")
    missed = {employee_id: values[3] for employee_id, values in attendance_counts(start, end).items() if values[3]}
    for employee in employees.filter(pk__in=missed):
        yield (*employee_cells(employee), "Recorded scheduled shifts missed", None, missed[employee.pk])


def dashboard(employees, today):
    active = employees.filter(status="active")
    upcoming = (today, today + timedelta(days=30))
    contracts = Document.objects.filter(employee__in=active, doc_type="contract", expiry_date__range=upcoming)
    on_leave = Leave.objects.filter(employee__in=active, approval_status="approved", start_date__lte=today, end_date__gte=today)
    documents = Document.objects.filter(employee__in=active, expiry_date__lt=today).exclude(doc_type="contract")
    compliance = EmployeeComplianceRecord.objects.filter(employee__in=active, expiry_date__lt=today)
    no_records = active.filter(documents__isnull=True, compliance_records__isnull=True)
    return (
        ("Active employees", active.count(), "staff", "green", ""),
        ("On approved leave", on_leave.values("employee_id").order_by().distinct().count(), "leave", "blue", ""),
        ("Contract documents expiring in 30 days", contracts.count(), "contracts", "amber", "Expiring soon"),
        ("Expired documents or compliance records", documents.count() + compliance.count(), "compliance", "red", "Expired"),
        ("Active employees without document records", no_records.count(), "compliance", "amber", "No document records"),
    )


def csv_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


@require_safe
def hr_reports(request):
    if not can_open_hr_reports(request.user):
        raise PermissionDenied

    params = request.GET
    key = params.get("report", "staff")
    if key not in REPORTS:
        key = "staff"
    title, columns, period_report = REPORTS[key]
    if key != "recruitment":
        columns = (*IDENTITY, *columns)
    today = timezone.localdate()
    start = date_filter(params, "from", today.replace(day=1))
    end = date_filter(params, "to", today)
    if start > end:
        start, end = end, start
    department = params.get("department", "")
    employees = Employee.objects.all().order_by("employee_number", "pk")
    if department in dict(Employee.DEPARTMENT_CHOICES):
        employees = employees.filter(department=department)
    else:
        department = ""

    common_statuses = ("Expiring soon", "Expired", "Current", "No expiry recorded")
    expiry_statuses = {
        "contracts": (*common_statuses, "No contract document"),
        "compliance": (*common_statuses, "No document records"),
    }.get(key, ())
    status = params.get("status", "")
    rows = report_rows(key, employees, start, end, today, department)
    if status in expiry_statuses:
        status_index = -1 if key == "contracts" else -2
        rows = (row for row in rows if row[status_index] == status)
    else:
        status = ""
    if params.get("export") == "csv":
        response = HttpResponse("\ufeff", content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="hr-{key}.csv"'
        response["Cache-Control"] = "private, no-store"
        writer = csv.writer(response)
        writer.writerow(columns)
        writer.writerows(tuple(map(csv_cell, row)) for row in rows)
        return response

    response = render_page(request, "webroaster/hr_reports.html", {
        "report_menu": [(name, report[0]) for name, report in REPORTS.items()],
        "report_key": key, "title": title, "columns": columns, "rows": list(rows),
        "department_choices": Employee.DEPARTMENT_CHOICES, "department": department,
        "expiry_statuses": expiry_statuses, "status": status,
        "show_period": period_report, "start": start, "end": end,
        "cards": dashboard(employees, today),
    }, "employees")
    response["Cache-Control"] = "private, no-store"
    return response
