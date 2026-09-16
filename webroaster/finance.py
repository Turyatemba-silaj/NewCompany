import json
import re
from io import BytesIO
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from .access import require_model_access, require_view_access
from .models import (
    Advance,
    Budget,
    Employee,
    Expense,
    Invoice,
    InvoiceBillableItemPrice,
    Paymee,
    Payment,
    PayrollDeduction,
    ProcurementNotification,
    ProcurementRequisition,
    PurchaseOrder,
    Region,
    Salary,
    SupplierInvoice,
    SupplierPayment,
    SupplierProformaInvoiceItem,
    SupplierProformaItemPrice,
)
from .views import get_config, get_field_label, render_page

def sync_receivables_from_payments():
    invoices = Invoice.objects.exclude(status="cancelled").select_related("client", "contract")
    for invoice in invoices:
        receivable, _created = Paymee.objects.get_or_create(invoice=invoice)
        receivable.save(update_fields=[
            "client",
            "total_amount",
            "amount_paid",
            "due_date",
            "last_payment_date",
            "status",
            "updated_at",
        ])

def payroll_employee_queryset():
    attendance_employee_ids = Employee.objects.filter(
        role__in=("guard", "supervisor"),
        attended_attendance_records__present=True,
    ).values_list("pk", flat=True)
    fixed_monthly_roles = ("manager", "operations_officer", "hr_officer", "finance_officer", "administrator")
    return (
        Employee.objects.filter(Q(role__in=fixed_monthly_roles) | Q(pk__in=attendance_employee_ids))
        .distinct()
        .order_by("employee_number", "first_name", "last_name")
    )


def payroll_salary_queryset():
    return Salary.objects.select_related("employee").filter(employee__in=payroll_employee_queryset())


def sync_salary_table():
    payroll_employees = payroll_employee_queryset()
    payroll_employee_ids = set(payroll_employees.values_list("pk", flat=True))
    for employee in payroll_employees:
        salary, _created = Salary.objects.get_or_create(
            employee=employee,
            defaults={"basic_salary": Decimal("0.00")},
        )
        salary.update_basic_salary()
        salary.save(update_fields=["basic_salary", "updated_at"])
    for salary in Salary.objects.select_related("employee").filter(employee__role__in=("guard", "supervisor")):
        if salary.employee_id in payroll_employee_ids:
            continue
        salary.update_basic_salary()
        salary.save(update_fields=["basic_salary", "overtime_pay", "updated_at"])


def payroll_dashboard(request):
    sync_salary_table()
    salaries = payroll_salary_queryset().order_by("employee__first_name", "employee__last_name")
    advances = Advance.objects.select_related("employee", "approved_by").all().order_by("-created_at")
    deductions = PayrollDeduction.objects.select_related("employee").filter(status="active").order_by("employee__first_name", "employee__last_name", "category")
    salary_rows = list(salaries[:8])
    advance_rows = list(advances[:8])
    deduction_rows = list(deductions[:8])
    gross_payroll = sum((salary.gross_pay for salary in salaries), Decimal("0.00"))
    net_payroll = sum((salary.net_pay for salary in salaries), Decimal("0.00"))
    period_shifts_worked = sum((salary.shifts_worked for salary in salaries), 0)
    outstanding_advances = sum((advance.balance for advance in advances), Decimal("0.00"))
    pending_advances = advances.filter(approval_status="pending").count()
    loan_total = sum((salary.loan_deduction for salary in salaries), Decimal("0.00"))
    medical_total = sum((salary.medical_deduction for salary in salaries), Decimal("0.00"))

    context = {
        "title": "Payroll",
        "module_cards": [
            {"label": "Salary Records", "value": salaries.count(), "caption": "Employee salary profiles", "model_name": "salaries", "accent": "blue"},
            {"label": "Advances", "value": advances.count(), "caption": f"{pending_advances} pending approval", "model_name": "advances", "accent": "amber"},
            {"label": "Gross Payroll", "value": f"UGX {gross_payroll:,.0f}", "caption": "Current salary period", "model_name": "salaries", "accent": "green"},
            {"label": "Period Shifts", "value": period_shifts_worked, "caption": "Attendance shifts in this pay period", "model_name": "salaries", "accent": "blue"},
            {"label": "Outstanding Advances", "value": f"UGX {outstanding_advances:,.0f}", "caption": "Recoverable balances", "model_name": "advances", "accent": "red"},
            {"label": "Loan Deductions", "value": f"UGX {loan_total:,.0f}", "caption": "Active loan deductions", "model_name": "payroll-deductions", "accent": "amber"},
            {"label": "Medical Deductions", "value": f"UGX {medical_total:,.0f}", "caption": "Active medical deductions", "model_name": "payroll-deductions", "accent": "blue"},
        ],
        "salary_rows": salary_rows,
        "advance_rows": advance_rows,
        "deduction_rows": deduction_rows,
        "gross_payroll": gross_payroll,
        "net_payroll": net_payroll,
        "period_shifts_worked": period_shifts_worked,
        "outstanding_advances": outstanding_advances,
        "loan_total": loan_total,
        "medical_total": medical_total,
    }
    return render_page(request, "webroaster/payroll_dashboard.html", context, "payroll")

def refresh_budget_audit_notifications():
    """Refresh budget accountability alerts for screens that audit finance records."""
    approved_budgets = Budget.objects.filter(approval_status="approved")
    for budget in approved_budgets:
        budget.save(update_fields=["spent_amount", "updated_at"])


def budget_report(request):
    require_view_access(request, "budget_report")
    refresh_budget_audit_notifications()
    budgets = Budget.objects.select_related(
        "requested_by",
        "verified_by",
        "approved_by",
    ).order_by("-fiscal_year", "department", "budget_title")
    report_rows = []
    total_requested = Decimal("0.00")
    total_allocated = Decimal("0.00")
    total_spent = Decimal("0.00")
    total_remaining = Decimal("0.00")
    for budget in budgets:
        total_requested += budget.requested_amount
        total_allocated += budget.allocated_amount
        total_spent += budget.spent_amount
        total_remaining += budget.remaining_amount
        report_rows.append({
            "budget": budget,
            "expense_count": budget.expenses.exclude(status="rejected").count(),
        })
    context = {
        "title": "Budget Report",
        "report_rows": report_rows,
        "total_requested": total_requested,
        "total_allocated": total_allocated,
        "total_spent": total_spent,
        "total_remaining": total_remaining,
    }
    return render_page(request, "webroaster/budget_report.html", context, "budgets")


budget_notifications = budget_report
def refresh_expense_accountability_notifications():
    approved_expenses = Expense.objects.filter(approval_status="approved")
    for expense in approved_expenses:
        expense.save(update_fields=["accountability_status", "accounted_at", "updated_at"])


def expense_report(request):
    require_view_access(request, "expense_report")
    refresh_expense_accountability_notifications()
    budgets = Budget.objects.prefetch_related("expenses").order_by("-fiscal_year", "department", "budget_title")
    report_rows = []
    total_budget_allocated = Decimal("0.00")
    total_requested = Decimal("0.00")
    total_accounted = Decimal("0.00")
    total_variance = Decimal("0.00")
    pending_count = 0
    overdue_count = 0
    for budget in budgets:
        budget_expenses = budget.expenses.exclude(status="rejected").order_by("expense_date", "expense_id")
        total_budget_allocated += budget.allocated_amount
        for expense in budget_expenses:
            total_requested += expense.requested_amount
            total_accounted += expense.amount
            total_variance += expense.variance_amount
            if expense.accountability_status in ("not_due", "pending_accountability"):
                pending_count += 1
            if expense.accountability_status == "overdue":
                overdue_count += 1
            report_rows.append({
                "budget": budget,
                "expense": expense,
            })
    context = {
        "title": "Expense Accountability Report",
        "report_rows": report_rows,
        "total_budget_allocated": total_budget_allocated,
        "total_requested": total_requested,
        "total_accounted": total_accounted,
        "total_variance": total_variance,
        "pending_count": pending_count,
        "overdue_count": overdue_count,
    }
    return render_page(request, "webroaster/expense_report.html", context, "expenses")


expense_notifications = expense_report


def aging_months(aging_days):
    if aging_days <= 0:
        return 1
    return max(1, int((aging_days + 29) / 30))


def client_customer_code(client):
    return f"CL{client.client_id:06d}"


def client_area(client):
    areas = list(
        Region.objects.filter(sites__client=client)
        .distinct()
        .order_by("region_name")
        .values_list("region_name", flat=True)
    )
    return ", ".join(areas) if areas else "-"


def finance_debt_collector():
    collector = (
        Employee.objects.filter(status="active")
        .filter(Q(role="finance_officer") | Q(department="finance"))
        .order_by("first_name", "last_name")
        .first()
    )
    return str(collector) if collector else "-"


def aging_report(request):
    require_view_access(request, "aging_report")
    sync_receivables_from_payments()
    today = timezone.localdate()
    collector_name = finance_debt_collector()
    receivables = (
        Paymee.objects.select_related("invoice", "client", "invoice__contract")
        .exclude(status__in=("paid", "overpaid", "cancelled"))
        .order_by("client__client_name", "due_date", "invoice_id")
    )
    grouped = {}
    total_receipts = Decimal("0.00")
    total_invoices = Decimal("0.00")
    total_balance_due = Decimal("0.00")

    for receivable in receivables:
        balance = receivable.balance_amount
        if balance <= 0:
            continue
        client = receivable.client
        row = grouped.setdefault(
            client.pk,
            {
                "customer_code": client_customer_code(client),
                "customer_name": client.client_name,
                "area": client_area(client),
                "manager": client.contact_person or "-",
                "debt_collector": collector_name,
                "receipts": Decimal("0.00"),
                "invoices": Decimal("0.00"),
                "balance_due": Decimal("0.00"),
                "months": 1,
                "max_aging_days": 0,
            },
        )
        row["receipts"] += receivable.amount_paid
        row["invoices"] += receivable.total_amount
        row["balance_due"] += balance
        row["max_aging_days"] = max(row["max_aging_days"], receivable.aging_days)
        row["months"] = aging_months(row["max_aging_days"])
        total_receipts += receivable.amount_paid
        total_invoices += receivable.total_amount
        total_balance_due += balance

    report_rows = sorted(grouped.values(), key=lambda row: row["customer_name"].lower())
    context = {
        "title": "Receivables Aging Report",
        "report_date": today,
        "company_name": getattr(settings, "COMPANY_NAME", "TURYANS SECURITY COMPANY (U) LIMITED"),
        "report_rows": report_rows,
        "total_receipts": total_receipts,
        "total_invoices": total_invoices,
        "total_balance_due": total_balance_due,
    }
    return render_page(request, "webroaster/aging_report.html", context, "paymees")

PROCUREMENT_API_MODELS = {
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
}
API_DEFAULT_PAGE_SIZE = 50
API_MAX_PAGE_SIZE = 200


def api_error(message, status=400, code="bad_request"):
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


def parse_positive_int(value, default, maximum=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < 1:
        return default
    if maximum is not None:
        return min(parsed, maximum)
    return parsed


def model_field_for(model, field_name):
    try:
        return model._meta.get_field(field_name)
    except Exception:
        return None


def api_scalar(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def api_attribute_value(obj, field_name):
    value = getattr(obj, field_name)
    if callable(value):
        value = value()
    field = model_field_for(obj.__class__, field_name)
    if field is not None and getattr(field, "many_to_one", False):
        if value is None:
            return None
        return {"id": value.pk, "display": str(value)}
    if isinstance(value, models.Model):
        return {"id": value.pk, "display": str(value)}
    return api_scalar(value)


def api_field_schema(model, field_name):
    field = model_field_for(model, field_name)
    label = get_field_label(model, field_name)
    if field is None:
        return {"name": field_name, "label": label, "type": "computed", "filterable": False}
    choices = [{"value": value, "label": label} for value, label in (getattr(field, "choices", None) or [])]
    return {
        "name": field_name,
        "label": label,
        "type": field.get_internal_type(),
        "required": not getattr(field, "blank", True) and not getattr(field, "null", True),
        "filterable": field.get_internal_type() in {"CharField", "EmailField", "DateField", "DateTimeField", "BooleanField"} or getattr(field, "many_to_one", False),
        "choices": choices,
    }


def requested_api_fields(request, config, detail=False):
    default_fields = config.get("detail_fields" if detail else "fields", config.get("fields", []))
    requested = [item.strip() for item in request.GET.get("fields", "").split(",") if item.strip()]
    if not requested:
        return default_fields
    allowed = set(config.get("detail_fields", [])) | set(config.get("fields", []))
    return [field for field in requested if field in allowed]


def procurement_api_payload(request, obj, fields):
    attributes = {field: api_attribute_value(obj, field) for field in fields}
    detail_url = request.build_absolute_uri(f"/api/procurement/{obj._api_model_name}/{obj.pk}/") if hasattr(obj, "_api_model_name") else None
    links = {"self": detail_url} if detail_url else {}
    if getattr(obj, "_api_model_name", "") == "purchase-orders":
        links["lpo_report"] = request.build_absolute_uri(f"/purchase-orders/{obj.pk}/lpo/")
    return {
        "id": obj.pk,
        "display": str(obj),
        "attributes": attributes,
        "links": links,
    }


def searchable_fields(model):
    names = []
    for field in model._meta.fields:
        if field.get_internal_type() in {"CharField", "TextField", "EmailField"}:
            names.append(field.name)
    return names


def apply_procurement_api_filters(queryset, request, config):
    model = config["model"]
    query = request.GET.get("q", "").strip()
    if query:
        search_query = Q()
        for field_name in searchable_fields(model):
            search_query |= Q(**{f"{field_name}__icontains": query})
        if search_query:
            queryset = queryset.filter(search_query)

    status = request.GET.get("status", "").strip()
    if status and model_field_for(model, "status") is not None:
        queryset = queryset.filter(status=status)

    supplier = request.GET.get("supplier", "").strip()
    if supplier and model_field_for(model, "supplier") is not None:
        queryset = queryset.filter(supplier_id=supplier)

    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    date_field = next((name for name in ("order_date", "required_date", "proforma_date", "invoice_date", "payment_date", "received_date", "created_at") if model_field_for(model, name) is not None), None)
    if date_field and date_from:
        queryset = queryset.filter(**{f"{date_field}__gte": date_from})
    if date_field and date_to:
        queryset = queryset.filter(**{f"{date_field}__lte": date_to})

    return queryset


def procurement_api_metadata(request, model_name, config, fields):
    return {
        "module": model_name,
        "title": config["title"],
        "fields": [api_field_schema(config["model"], field) for field in fields],
        "filters": {
            "q": "Search text fields",
            "status": "Exact workflow status where available",
            "supplier": "Supplier primary key where available",
            "date_from": "Inclusive start date on the module date field",
            "date_to": "Inclusive end date on the module date field",
            "fields": "Comma-separated response fields",
            "page": "Page number",
            "page_size": f"Records per page, max {API_MAX_PAGE_SIZE}",
        },
        "links": {
            "list": request.build_absolute_uri(f"/api/procurement/{model_name}/"),
        },
    }


def procurement_api_index(request):
    require_view_access(request, "procurement_api_index")
    if request.method != "GET":
        return api_error("Only GET is supported by this API endpoint.", status=405, code="method_not_allowed")
    modules = []
    for model_name in sorted(PROCUREMENT_API_MODELS):
        config = get_config(model_name)
        modules.append({
            "name": model_name,
            "title": config["title"],
            "count": config["model"].objects.count(),
            "records_url": request.build_absolute_uri(f"/api/procurement/{model_name}/"),
            "web_url": request.build_absolute_uri(f"/{model_name}/"),
        })
    return JsonResponse({
        "api": "procurement",
        "version": "1.1",
        "security": "Authenticated staff session required. API reads are permission controlled and write workflows remain in the audited web forms.",
        "modules": modules,
    })


def procurement_api_list(request, model_name):
    require_view_access(request, "procurement_api_list")
    if request.method != "GET":
        return api_error("Only GET is supported by this API endpoint.", status=405, code="method_not_allowed")
    if model_name not in PROCUREMENT_API_MODELS:
        raise Http404("The requested procurement API module does not exist.")
    config = get_config(model_name)
    fields = requested_api_fields(request, config)
    ordering = config.get("ordering") or [config["model"]._meta.pk.name]
    queryset = config["model"].objects.all().order_by(*ordering)
    queryset = apply_procurement_api_filters(queryset, request, config)
    total_count = queryset.count()
    page_size = parse_positive_int(request.GET.get("page_size"), API_DEFAULT_PAGE_SIZE, API_MAX_PAGE_SIZE)
    page = parse_positive_int(request.GET.get("page"), 1)
    offset = (page - 1) * page_size
    objects = list(queryset[offset:offset + page_size])
    for obj in objects:
        obj._api_model_name = model_name
    next_page = page + 1 if offset + page_size < total_count else None
    previous_page = page - 1 if page > 1 else None
    return JsonResponse({
        "metadata": procurement_api_metadata(request, model_name, config, fields),
        "pagination": {
            "count": total_count,
            "page": page,
            "page_size": page_size,
            "next": request.build_absolute_uri(f"/api/procurement/{model_name}/?page={next_page}&page_size={page_size}") if next_page else None,
            "previous": request.build_absolute_uri(f"/api/procurement/{model_name}/?page={previous_page}&page_size={page_size}") if previous_page else None,
        },
        "results": [procurement_api_payload(request, obj, fields) for obj in objects],
    })


def procurement_api_detail(request, model_name, pk):
    require_view_access(request, "procurement_api_detail")
    if request.method != "GET":
        return api_error("Only GET is supported by this API endpoint.", status=405, code="method_not_allowed")
    if model_name not in PROCUREMENT_API_MODELS:
        raise Http404("The requested procurement API module does not exist.")
    config = get_config(model_name)
    obj = get_object_or_404(config["model"], pk=pk)
    obj._api_model_name = model_name
    fields = requested_api_fields(request, config, detail=True)
    return JsonResponse({
        "metadata": procurement_api_metadata(request, model_name, config, fields),
        "result": procurement_api_payload(request, obj, fields),
    })

PAYOUT_API_BATCHES = {
    "salaries": "Employee salary payouts",
    "advances": "Employee salary advance payouts",
    "supplier-payments": "Approved supplier invoice payments",
    "client-payments": "Incoming client payment references",
}


def payout_channel_details(employee=None, supplier=None, method=None):
    method = method or getattr(employee, "payout_method", "") or "bank_transfer"
    if method == "mobile_money":
        mobile_number = getattr(employee, "mobile_money_number", "") or getattr(employee, "phone_number", "")
        missing = []
        if not (getattr(employee, "mobile_money_provider", "") if employee else ""):
            missing.append("mobile_money_provider")
        if not mobile_number:
            missing.append("mobile_money_number")
        return {
            "channel": "mobile_money",
            "mobile_money": {
                "provider": getattr(employee, "mobile_money_provider", "") if employee else "",
                "number": mobile_number,
                "account_name": str(employee) if employee else "",
            },
            "bank_account": None,
            "missing_fields": missing,
        }
    bank_owner = employee or supplier
    missing = []
    bank_name = getattr(bank_owner, "bank_name", "") if bank_owner else ""
    account_name = getattr(bank_owner, "bank_account_name", "") if bank_owner else ""
    account_number = getattr(bank_owner, "bank_account_number", "") if bank_owner else ""
    if not bank_name:
        missing.append("bank_name")
    if not account_name:
        missing.append("bank_account_name")
    if not account_number:
        missing.append("bank_account_number")
    return {
        "channel": "bank_transfer",
        "bank_account": {
            "bank_name": bank_name,
            "account_name": account_name,
            "account_number": account_number,
        },
        "mobile_money": None,
        "missing_fields": missing,
    }


def payout_record(record_type, record_id, reference, direction, amount, currency, party, channel_details, status, date_value, links=None):
    missing_fields = channel_details.pop("missing_fields", [])
    return {
        "type": record_type,
        "id": record_id,
        "reference": reference,
        "direction": direction,
        "amount": str(amount or Decimal("0.00")),
        "currency": currency or "UGX",
        "party": party,
        "channel": channel_details["channel"],
        "bank_account": channel_details["bank_account"],
        "mobile_money": channel_details["mobile_money"],
        "status": status,
        "date": api_scalar(date_value),
        "ready_for_export": not missing_fields,
        "missing_fields": missing_fields,
        "links": links or {},
    }


def apply_payout_common_filters(records, request):
    method = request.GET.get("method", "").strip()
    ready = request.GET.get("ready", "").strip().lower()
    if method:
        records = [record for record in records if record["channel"] == method]
    if ready in {"1", "true", "yes"}:
        records = [record for record in records if record["ready_for_export"]]
    elif ready in {"0", "false", "no"}:
        records = [record for record in records if not record["ready_for_export"]]
    return records


def date_in_range(value, date_from, date_to):
    if not value:
        return True
    if date_from and str(value) < date_from:
        return False
    if date_to and str(value) > date_to:
        return False
    return True


def salary_payout_records(request):
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    records = []
    salaries = Salary.objects.select_related("employee").all().order_by("employee__employee_number", "salary_id")
    for salary in salaries:
        period_end = salary.period_end_date
        if not date_in_range(period_end, date_from, date_to):
            continue
        employee = salary.employee
        channel_details = payout_channel_details(employee=employee, method=employee.payout_method)
        records.append(payout_record(
            "salary",
            salary.pk,
            f"SAL-{salary.pk:06d}",
            "outbound",
            salary.net_pay,
            "UGX",
            {"id": employee.pk, "name": str(employee), "employee_number": employee.employee_number, "phone_number": employee.phone_number},
            channel_details,
            employee.status,
            period_end,
            {"self": request.build_absolute_uri(f"/salaries/{salary.pk}/"), "payslip": request.build_absolute_uri(f"/salaries/{salary.pk}/payslip/")},
        ))
    return records


def advance_payout_records(request):
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    status = request.GET.get("status", "").strip()
    advances = Advance.objects.select_related("employee").filter(approval_status="approved").order_by("-disbursement_date", "-advance_id")
    if status:
        advances = advances.filter(status=status)
    records = []
    for advance in advances:
        payout_date = advance.disbursement_date or advance.created_at.date()
        if not date_in_range(payout_date, date_from, date_to):
            continue
        employee = advance.employee
        channel_details = payout_channel_details(employee=employee, method=employee.payout_method)
        records.append(payout_record(
            "advance",
            advance.pk,
            f"ADV-{advance.pk:06d}",
            "outbound",
            advance.amount_requested,
            "UGX",
            {"id": employee.pk, "name": str(employee), "employee_number": employee.employee_number, "phone_number": employee.phone_number},
            channel_details,
            advance.status,
            payout_date,
            {"self": request.build_absolute_uri(f"/advances/{advance.pk}/")},
        ))
    return records


def supplier_payment_payout_records(request):
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    status = request.GET.get("status", "").strip()
    payments = SupplierPayment.objects.select_related("supplier_invoice", "supplier_invoice__supplier").all().order_by("-payment_date", "-supplier_payment_id")
    if status:
        payments = payments.filter(approval_status=status)
    records = []
    for payment in payments:
        if not date_in_range(payment.payment_date, date_from, date_to):
            continue
        supplier = payment.supplier_invoice.supplier
        method = "mobile_money" if payment.payment_method == "mobile_money" else "bank_transfer"
        channel_details = payout_channel_details(supplier=supplier, method=method)
        records.append(payout_record(
            "supplier_payment",
            payment.pk,
            payment.transaction_ref or f"SUPPAY-{payment.pk:06d}",
            "outbound",
            payment.amount,
            "UGX",
            {"id": supplier.pk, "name": supplier.supplier_name, "supplier_code": supplier.supplier_code, "phone_number": supplier.phone_number},
            channel_details,
            payment.payment_status,
            payment.payment_date,
            {"self": request.build_absolute_uri(f"/supplier-payments/{payment.pk}/")},
        ))
    return records


def client_payment_records(request):
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    method = request.GET.get("method", "").strip()
    payments = Payment.objects.select_related("invoice", "invoice__client").all().order_by("-payment_date", "-payment_id")
    if method:
        payments = payments.filter(payment_method=method)
    records = []
    for payment in payments:
        if not date_in_range(payment.payment_date, date_from, date_to):
            continue
        client = payment.invoice.client
        channel = "bank_transfer" if payment.payment_method == "bank_transfer" else payment.payment_method
        records.append({
            "type": "client_payment",
            "id": payment.pk,
            "reference": payment.transaction_ref or f"PAY-{payment.pk:06d}",
            "direction": "inbound",
            "amount": str(payment.amount),
            "currency": "UGX",
            "party": {"id": client.pk, "name": client.client_name, "phone_number": client.phone_number, "email": client.email},
            "channel": channel,
            "bank_account": None,
            "mobile_money": None,
            "status": "received",
            "date": api_scalar(payment.payment_date),
            "ready_for_export": bool(payment.transaction_ref),
            "missing_fields": [] if payment.transaction_ref else ["transaction_ref"],
            "links": {"self": request.build_absolute_uri(f"/payments/{payment.pk}/"), "receipt": request.build_absolute_uri(f"/payments/{payment.pk}/receipt/")},
        })
    return records


def payout_api_records(request, batch_type):
    builders = {
        "salaries": salary_payout_records,
        "advances": advance_payout_records,
        "supplier-payments": supplier_payment_payout_records,
        "client-payments": client_payment_records,
    }
    return builders[batch_type](request)


def payout_api_index(request):
    require_view_access(request, "payout_api_index")
    if request.method != "GET":
        return api_error("Only GET is supported by this API endpoint.", status=405, code="method_not_allowed")
    return JsonResponse({
        "api": "finance-payouts",
        "version": "1.0",
        "security": "Authenticated finance staff session required. These endpoints prepare bank and mobile money batches; they do not transmit funds.",
        "batches": [
            {"name": name, "title": title, "records_url": request.build_absolute_uri(f"/api/payouts/{name}/")}
            for name, title in PAYOUT_API_BATCHES.items()
        ],
        "filters": {
            "method": "bank_transfer or mobile_money where applicable",
            "ready": "true/false readiness for export",
            "status": "Workflow status where applicable",
            "date_from": "Inclusive start date",
            "date_to": "Inclusive end date",
            "page": "Page number",
            "page_size": f"Records per page, max {API_MAX_PAGE_SIZE}",
        },
    })


def payout_api_batch(request, batch_type):
    require_view_access(request, "payout_api_batch")
    if request.method != "GET":
        return api_error("Only GET is supported by this API endpoint.", status=405, code="method_not_allowed")
    if batch_type not in PAYOUT_API_BATCHES:
        raise Http404("The requested payout API batch does not exist.")
    records = apply_payout_common_filters(payout_api_records(request, batch_type), request)
    total_count = len(records)
    page_size = parse_positive_int(request.GET.get("page_size"), API_DEFAULT_PAGE_SIZE, API_MAX_PAGE_SIZE)
    page = parse_positive_int(request.GET.get("page"), 1)
    offset = (page - 1) * page_size
    page_records = records[offset:offset + page_size]
    next_page = page + 1 if offset + page_size < total_count else None
    previous_page = page - 1 if page > 1 else None
    return JsonResponse({
        "metadata": {
            "batch": batch_type,
            "title": PAYOUT_API_BATCHES[batch_type],
            "direction": "inbound" if batch_type == "client-payments" else "outbound",
            "links": {"index": request.build_absolute_uri("/api/payouts/")},
        },
        "pagination": {
            "count": total_count,
            "page": page,
            "page_size": page_size,
            "next": request.build_absolute_uri(f"/api/payouts/{batch_type}/?page={next_page}&page_size={page_size}") if next_page else None,
            "previous": request.build_absolute_uri(f"/api/payouts/{batch_type}/?page={previous_page}&page_size={page_size}") if previous_page else None,
        },
        "totals": {
            "amount": str(sum((Decimal(record["amount"]) for record in records), Decimal("0.00"))),
            "ready_count": sum(1 for record in records if record["ready_for_export"]),
            "not_ready_count": sum(1 for record in records if not record["ready_for_export"]),
        },
        "results": page_records,
    })

def procurement_dashboard(request):
    register_items = [
        "suppliers",
        "procurement-requisitions",
        "supplier-proformas",
        "purchase-orders",
        "goods-received-notes",
        "supplier-invoices",
        "supplier-payments",
    ]
    module_cards = []
    for item_name in register_items:
        config = get_config(item_name)
        module_cards.append({
            "model_name": item_name,
            "label": config["title"],
            "value": config["model"].objects.count(),
            "caption": "records",
            "accent": "blue",
        })
    pending_requisitions = ProcurementRequisition.objects.filter(status="submitted").select_related("requested_by", "approval_assigned_to")[:8]
    approved_requisitions = ProcurementRequisition.objects.filter(status="approved").select_related("preferred_supplier")[:8]
    pending_payments = SupplierPayment.objects.filter(approval_status="pending").select_related("supplier_invoice", "supplier_invoice__supplier")[:8]
    supplier_invoices_ready = SupplierInvoice.objects.filter(status="approved").select_related("supplier")[:8]
    notifications = ProcurementNotification.objects.select_related("recipient")[:8]
    context = {
        "title": "Procurement",
        "module_cards": module_cards,
        "pending_requisitions": pending_requisitions,
        "approved_requisitions": approved_requisitions,
        "pending_payments": pending_payments,
        "supplier_invoices_ready": supplier_invoices_ready,
        "notifications": notifications,
    }
    return render_page(request, "webroaster/procurement_dashboard.html", context, "procurement")

def salary_payslip_context(salary):
    salary.update_basic_salary()
    salary.save(update_fields=["basic_salary", "updated_at"])
    salary.recover_advances()
    return {
        "title": f"Payslip - {salary.employee}",
        "salary": salary,
        "employee": salary.employee,
        "shift_summary": [
            ("Pay Period Shifts Worked", salary.shifts_worked),
            ("Overtime Shifts Paid", salary.overtime_shifts),
            ("Daily Rate", salary.daily_rate),
            ("Overtime Daily Rate", salary.overtime_daily_rate),
        ],
        "earnings": [
            ("Basic Shift Pay", salary.basic_salary),
            ("Overtime Pay", salary.overtime_pay),
            ("Allowances", salary.allowances),
            ("Bonus", salary.bonus),
        ],
        "deductions": [
            ("NSSF Employee (5%)", salary.nssf_employee),
            ("PAYE", salary.paye),
            ("Loan Deduction", salary.loan_deduction),
            ("Medical Deduction", salary.medical_deduction),
            ("Advance Recovery", salary.advance_recovery),
            ("Other Payroll", salary.other_payroll_deductions),
            ("Other Deductions", salary.deductions),
        ],
        "advance_balance": salary.ledger_advance_balance,
        "employer_contributions": [
            ("NSSF Employer Contribution (10%)", salary.nssf_employer),
        ],
        "statutory_summary": [
            ("Taxable Pay", salary.taxable_pay),
            ("PAYE Basis", salary.paye_tax_year_basis),
            ("PAYE Deducted", salary.paye),
            ("NSSF Employee 5%", salary.nssf_employee),
            ("NSSF Employer 10%", salary.nssf_employer),
            ("Total NSSF 15%", salary.total_nssf),
        ],
        "net_pay_summary": [
            ("Gross Pay", salary.gross_pay),
            ("Less NSSF 5%", salary.nssf_employee),
            ("Less PAYE", salary.paye),
            ("Less Payroll Deductions", salary.staff_deductions),
            ("Less Advance Recovery", salary.advance_recovery),
            ("Less Other Deductions", salary.deductions),
            ("Net Pay", salary.net_pay),
        ],
    }


def salary_payslip(request, pk):
    require_model_access(request, "salaries")
    salary = get_object_or_404(Salary.objects.select_related("employee"), pk=pk)
    context = salary_payslip_context(salary)
    return render_page(request, "webroaster/salary_payslip.html", context, "salaries")


def pdf_money(value):
    return f"{Decimal(value):,.2f}"


def salary_payslip_pdf(request, pk):
    require_model_access(request, "salaries")
    salary = get_object_or_404(Salary.objects.select_related("employee"), pk=pk)
    context = salary_payslip_context(salary)
    employee = context["employee"]

    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_RIGHT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        return HttpResponse("PDF export requires reportlab. Run: pip install -r requirements.txt", status=500)

    styles = getSampleStyleSheet()
    normal = ParagraphStyle("PayslipNormal", parent=styles["Normal"], fontName="Helvetica", fontSize=8, leading=10)
    small = ParagraphStyle("PayslipSmall", parent=normal, fontSize=7, leading=8, textColor=colors.HexColor("#475569"))
    heading = ParagraphStyle("PayslipHeading", parent=normal, fontName="Helvetica-Bold", fontSize=12, leading=14, textColor=colors.HexColor("#0f172a"))
    title = ParagraphStyle("PayslipTitle", parent=heading, fontSize=14, leading=16, alignment=TA_RIGHT, textColor=colors.HexColor("#0f766e"))
    section_title = ParagraphStyle("SectionTitle", parent=normal, fontName="Helvetica-Bold", fontSize=8, leading=9, textColor=colors.HexColor("#0f766e"))

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=10 * mm,
        leftMargin=10 * mm,
        topMargin=9 * mm,
        bottomMargin=9 * mm,
        title=f"Payslip - {employee}",
    )

    accent = colors.HexColor("#0f766e")
    border = colors.HexColor("#cbd5e1")
    soft = colors.HexColor("#f8fafc")
    soft_accent = colors.HexColor("#ecfdf5")

    def p(value, style=normal):
        return Paragraph(str(value if value not in (None, "") else "-"), style)

    def table(data, widths, style_commands=None):
        base_style = [
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("LEADING", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.35, border),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 0), (-1, 0), soft),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#334155")),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if style_commands:
            base_style.extend(style_commands)
        rendered = Table(data, colWidths=widths, hAlign="LEFT")
        rendered.setStyle(TableStyle(base_style))
        return rendered

    def key_value_rows(rows):
        return [[p(label, small), p(pdf_money(amount), normal)] for label, amount in rows]

    story = []
    header = Table(
        [[
            [p("TURYANS SECURITY COMPANY (U) LIMITED", heading), p("Payroll advice generated from approved attendance and payroll records", small)],
            [p("PAYSLIP", title), p(f"{salary.period_start_date} to {salary.period_end_date}", small)],
        ]],
        colWidths=[125 * mm, 50 * mm],
    )
    header.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 1, accent),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([header, Spacer(1, 5)])

    meta_rows = [
        [p("Employee", small), p(employee), p("Employee No.", small), p(employee.employee_number or "-")],
        [p("Role", small), p(employee.get_role_display()), p("Position", small), p(employee.get_position_display())],
        [p("NSSF No.", small), p(employee.nssf_number or "-"), p("Pay Period", small), p(salary.get_pay_period_display())],
        [p("Period Start", small), p(salary.period_start_date), p("Period End", small), p(salary.period_end_date)],
    ]
    story.append(table(meta_rows, [27 * mm, 61 * mm, 27 * mm, 60 * mm], [("BACKGROUND", (0, 0), (-1, -1), colors.white)]))
    story.append(Spacer(1, 5))

    summary = Table(
        [[
            p("Gross Pay<br/><b>%s</b>" % pdf_money(salary.gross_pay), normal),
            p("Total Deductions<br/><b>%s</b>" % pdf_money(salary.total_deductions), normal),
            p("Net Pay<br/><b>%s</b>" % pdf_money(salary.net_pay), normal),
        ]],
        colWidths=[58 * mm, 58 * mm, 59 * mm],
    )
    summary.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, border),
        ("BACKGROUND", (0, 0), (1, 0), soft),
        ("BACKGROUND", (2, 0), (2, 0), soft_accent),
        ("TEXTCOLOR", (2, 0), (2, 0), colors.HexColor("#065f46")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([summary, Spacer(1, 5)])

    def titled_table(title_text, body, widths, extra_style=None):
        return [
            table([[p(title_text, section_title)]], [sum(widths)], [("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0fdfa")), ("BOX", (0, 0), (-1, -1), 0.35, colors.HexColor("#99f6e4"))]),
            table(body, widths, extra_style),
            Spacer(1, 4),
        ]

    shift_rows = [
        [p("Shifts Worked", small), p(salary.shifts_worked), p("Overtime Shifts", small), p(salary.overtime_shifts)],
        [p("Daily Rate", small), p(pdf_money(salary.daily_rate)), p("Overtime Rate", small), p(pdf_money(salary.overtime_daily_rate))],
        [p("Basic Shift Pay", small), p(pdf_money(salary.basic_salary)), p("Overtime Pay", small), p(pdf_money(salary.overtime_pay))],
    ]
    story.extend(titled_table("Worked Shift Calculation", shift_rows, [43 * mm, 44 * mm, 43 * mm, 45 * mm]))

    earnings_table = titled_table("Earnings", key_value_rows(context["earnings"]) + [[p("Gross Pay", small), p(pdf_money(salary.gross_pay))]], [58 * mm, 29 * mm])
    deductions_table = titled_table("Deductions", key_value_rows(context["deductions"]) + [[p("Total Deductions", small), p(pdf_money(salary.total_deductions))], [p("Advance Balance", small), p(pdf_money(context["advance_balance"]))], [p("Net Pay", small), p(pdf_money(salary.net_pay))]], [58 * mm, 30 * mm])
    pair = Table([[earnings_table, deductions_table]], colWidths=[87 * mm, 88 * mm])
    pair.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(pair)

    statutory_rows = [[p(label, small), p(value if isinstance(value, str) else pdf_money(value), normal)] for label, value in context["statutory_summary"]]
    net_rows = key_value_rows(context["net_pay_summary"])
    employer_rows = key_value_rows(context["employer_contributions"]) + [[p("Total NSSF", small), p(pdf_money(salary.total_nssf))]]
    lower = Table([[
        titled_table("Uganda Statutory Summary", statutory_rows, [34 * mm, 46 * mm]),
        titled_table("Net Pay Calculation", net_rows, [35 * mm, 30 * mm]),
        titled_table("Employer Contributions", employer_rows, [21 * mm, 9 * mm]),
    ]], colWidths=[80 * mm, 65 * mm, 30 * mm])
    lower.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(lower)

    story.append(Spacer(1, 12))
    signatures = Table([[p("Prepared By", small), p("Checked By", small), p("Employee Signature", small)]], colWidths=[58 * mm, 58 * mm, 59 * mm])
    signatures.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, -1), 0.6, colors.HexColor("#0f172a")), ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    story.append(signatures)

    doc.build(story)
    filename = f"payslip-{employee.employee_number or employee.pk}.pdf".replace(" ", "-")
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response

def invoice_document(request, pk):
    require_model_access(request, "invoices")
    invoice = get_object_or_404(Invoice.objects.select_related("client", "contract").prefetch_related("sites", "billable_products", "provisional_items"), pk=pk)
    invoice.save(update_fields=invoice_update_fields())
    payments = invoice.payments.all().order_by("payment_date", "payment_id")
    amount_paid = sum((payment.amount for payment in payments), Decimal("0.00"))
    balance_due = invoice.total_amount - amount_paid
    context = {
        "title": invoice.invoice_number or invoice.generate_invoice_number(),
        "company_name": getattr(settings, "COMPANY_NAME", "TURYANS SECURITY COMPANY (U) LIMITED"),
        "invoice": invoice,
        "client": invoice.client,
        "contract": invoice.contract,
        "invoice_lines": invoice.invoice_line_items(),
        "payments": payments,
        "amount_paid": amount_paid,
        "balance_due": balance_due,
    }
    return render_page(request, "webroaster/invoice_document.html", context, "invoices")

def purchase_order_lpo_lines(purchase_order):
    proforma = getattr(purchase_order, "proforma_invoice", None)
    if proforma:
        return [
            {
                "description": item.description or item.catalog_item or "Item",
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "discount_amount": item.discount_amount,
                "tax_rate": item.tax_rate,
                "tax_amount": item.tax_amount,
                "line_total": item.line_total,
                "total_amount": item.total_amount,
            }
            for item in proforma.items.select_related("catalog_item").all().order_by("item_id")
        ]
    return [
        {
            "description": purchase_order.requisition.description or purchase_order.requisition.title,
            "quantity": 1,
            "unit_price": purchase_order.subtotal_amount,
            "discount_amount": Decimal("0.00"),
            "tax_rate": "-",
            "tax_amount": purchase_order.tax_amount,
            "line_total": purchase_order.subtotal_amount,
            "total_amount": purchase_order.total_amount,
        }
    ]


def purchase_order_lpo_report(request, pk):
    require_model_access(request, "purchase-orders")
    purchase_order = get_object_or_404(
        PurchaseOrder.objects.select_related("requisition", "supplier", "prepared_by"),
        pk=pk,
    )
    context = {
        "title": purchase_order.po_number or purchase_order.generate_po_number(),
        "company_name": getattr(settings, "COMPANY_NAME", "TURYANS SECURITY COMPANY (U) LIMITED"),
        "purchase_order": purchase_order,
        "supplier": purchase_order.supplier,
        "requisition": purchase_order.requisition,
        "proforma": getattr(purchase_order, "proforma_invoice", None),
        "lpo_lines": purchase_order_lpo_lines(purchase_order),
    }
    return render_page(request, "webroaster/purchase_order_lpo_report.html", context, "purchase-orders")
def payment_reconciliation_rows(invoice, current_payment=None):
    payments = list(invoice.payments.all().order_by("payment_date", "payment_id"))
    running_balance = invoice.total_amount
    rows = []
    for payment in payments:
        running_balance -= payment.amount
        rows.append({
            "payment": payment,
            "is_current": current_payment is not None and payment.pk == current_payment.pk,
            "balance_after": running_balance,
        })
    return rows


def payment_document_context(payment):
    invoice = payment.invoice
    invoice.save(update_fields=invoice_update_fields())
    payment_record, _created = Paymee.objects.get_or_create(invoice=invoice)
    payment_record.save(update_fields=["client", "total_amount", "amount_paid", "due_date", "last_payment_date", "status", "updated_at"])
    prior_paid = sum(
        (item.amount for item in invoice.payments.filter(payment_date__lt=payment.payment_date)),
        Decimal("0.00"),
    )
    prior_paid += sum(
        (item.amount for item in invoice.payments.filter(payment_date=payment.payment_date, payment_id__lt=payment.payment_id)),
        Decimal("0.00"),
    )
    total_paid_to_date = prior_paid + payment.amount
    balance_before = invoice.total_amount - prior_paid
    balance_after = invoice.total_amount - total_paid_to_date
    return {
        "company_name": getattr(settings, "COMPANY_NAME", "TURYANS SECURITY COMPANY (U) LIMITED"),
        "payment": payment,
        "invoice": invoice,
        "client": invoice.client,
        "contract": invoice.contract,
        "payment_record": payment_record,
        "receipt_number": f"RCT-{payment.payment_id:06d}",
        "statement_number": f"REC-{payment.payment_id:06d}",
        "prior_paid": prior_paid,
        "balance_before": balance_before,
        "total_paid_to_date": total_paid_to_date,
        "balance_after": balance_after,
        "reconciliation_rows": payment_reconciliation_rows(invoice, payment),
    }


def payment_receipt(request, pk):
    require_view_access(request, "payment_receipt")
    payment = get_object_or_404(Payment.objects.select_related("invoice", "invoice__client", "invoice__contract"), pk=pk)
    context = payment_document_context(payment)
    context["title"] = f"Receipt {context['receipt_number']}"
    return render_page(request, "webroaster/payment_receipt.html", context, "payments")


def payment_reconciliation(request, pk):
    require_view_access(request, "payment_reconciliation")
    payment = get_object_or_404(Payment.objects.select_related("invoice", "invoice__client", "invoice__contract"), pk=pk)
    context = payment_document_context(payment)
    context["title"] = f"Reconciliation {context['statement_number']}"
    return render_page(request, "webroaster/payment_reconciliation.html", context, "payments")

def invoice_item_price_payload():
    prices = InvoiceBillableItemPrice.objects.filter(active=True)
    return json.dumps({
        price.item_name: {
            "unit_price": str(price.unit_price),
            "taxable": price.taxable,
        }
        for price in prices
    })

def invoice_item_post_data(request):
    if request.method != "POST":
        return None
    if "items-TOTAL_FORMS" in request.POST and "items-INITIAL_FORMS" in request.POST:
        return request.POST
    item_indexes = set()
    for key in request.POST:
        match = re.match(r"items-(\d+)-", key)
        if match:
            item_indexes.add(int(match.group(1)))
    if not item_indexes:
        return None
    data = request.POST.copy()
    data["items-TOTAL_FORMS"] = str(max(item_indexes) + 1)
    data["items-INITIAL_FORMS"] = "0"
    data.setdefault("items-MIN_NUM_FORMS", "0")
    data.setdefault("items-MAX_NUM_FORMS", "1000")
    return data

def invoice_update_fields():
    return ["invoice_number", "client", "deployed_guards", "rate_per_guard", "contract_amount", "tax_amount", "total_amount", "description", "updated_at"]


def create_split_site_invoices(form):
    data = form.cleaned_data
    contract = data["contract"]
    invoices = []
    for site in contract.sites.all().order_by("site_name", "site_id"):
        invoice = Invoice.objects.create(
            contract=contract,
            client=contract.client,
            invoice_date=data["invoice_date"],
            due_date=data["due_date"],
            billing_start_date=data["billing_start_date"],
            billing_end_date=data["billing_end_date"],
            amendment_amount=Decimal("0.00"),
            amendment_reason="",
            tax_rate=data["tax_rate"],
            status=data["status"],
        )
        invoice.sites.set([site])
        invoice.save(update_fields=invoice_update_fields())
        invoices.append(invoice)
    return invoices


def invoice_item_formset_has_rows(formset):
    return any(
        form.cleaned_data and not form.cleaned_data.get("DELETE") and form.cleaned_data.get("item_name")
        for form in formset.forms
        if hasattr(form, "cleaned_data")
    )



def proforma_item_price_payload():
    prices = SupplierProformaItemPrice.objects.filter(active=True)
    return json.dumps({
        str(price.pk): {"unit_price": str(price.unit_price), "tax_rate": str(price.tax_rate), "discount_allowed": price.discount_allowed}
        for price in prices
    })

def proforma_item_formset_has_rows(formset):
    return any(
        form.cleaned_data and not form.cleaned_data.get("DELETE") and form.cleaned_data.get("catalog_item")
        for form in formset.forms
        if hasattr(form, "cleaned_data")
    )


def proforma_formset_total(formset):
    subtotal = Decimal("0.00")
    tax_total = Decimal("0.00")
    for form in formset.forms:
        if not hasattr(form, "cleaned_data") or not form.cleaned_data or form.cleaned_data.get("DELETE"):
            continue
        catalog_item = form.cleaned_data.get("catalog_item")
        quantity = form.cleaned_data.get("quantity") or Decimal("0.00")
        if not catalog_item or quantity <= 0:
            continue
        gross_amount = (quantity * catalog_item.unit_price).quantize(Decimal("0.01"))
        discount_amount = Decimal("0.00")
        if catalog_item.discount_allowed:
            discount_rate = SupplierProformaInvoiceItem.discount_rate_for_quantity(quantity)
            discount_amount = (gross_amount * (discount_rate / Decimal("100"))).quantize(Decimal("0.01"))
        line_total = (gross_amount - discount_amount).quantize(Decimal("0.01"))
        tax_amount = (line_total * ((catalog_item.tax_rate or Decimal("0.00")) / Decimal("100"))).quantize(Decimal("0.01"))
        subtotal += line_total
        tax_total += tax_amount
    return subtotal + tax_total


def validate_proforma_total_against_requisition(form, formset):
    requisition = form.cleaned_data.get("requisition")
    if not requisition or not hasattr(formset, "forms"):
        return True
    approved_limit = requisition.approved_amount or requisition.estimated_amount
    submitted_total = proforma_formset_total(formset)
    if approved_limit and submitted_total > approved_limit:
        form.add_error(None, f"Supplier proforma total {submitted_total:,.2f} exceeds the approved requisition amount {approved_limit:,.2f}.")
        return False
    return True

def procurement_contact_supplier(request, pk):
    require_view_access(request, "procurement_contact_supplier")
    requisition = get_object_or_404(ProcurementRequisition, pk=pk)
    if request.method != "POST":
        return redirect("webroaster:detail", model_name="procurement-requisitions", pk=requisition.pk)
    try:
        requisition.mark_supplier_contacted()
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    else:
        messages.success(request, "Supplier contacted and procurement notifications sent.")
    return redirect("webroaster:list", model_name="procurement")

