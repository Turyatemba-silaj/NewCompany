import csv
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.contrib.auth.views import redirect_to_login
from django.db.models import Prefetch, Q, Sum
from django.http import HttpResponse, HttpResponseBadRequest
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_safe

from .models import (
    Advance, AdvanceRecovery, Attendance, Budget, Contract, Expense, GoodsReceivedNote,
    Employee, Invoice, Payment, PayrollRun, PurchaseOrder, Salary, Site, SupplierInvoice, SupplierPayment,
)
from .views import render_page

ZERO = Decimal("0.00")
ISSUED = ("sent", "overdue", "paid")
FORECAST_PAYABLE = ("approved", "partially_paid")
REPORTS = {
    "receivables": ("Client Receivables & Aging", "As of the To date. Open issued invoices only. Credits are already included in invoice totals.",
                    "Client|Invoice|Due date|Invoiced UGX|Credit UGX|Received UGX|Outstanding UGX|Days overdue|Aging"),
    "billing": ("Billing & Collections", "Invoice rows use invoice dates. Missing billing checks use service-period overlap. Receipts on each invoice are cumulative through the To date.",
                "Client|Contract|Invoice|Service start|Service end|Billed site or gap|Invoiced UGX|Received UGX|Outstanding UGX|Check"),
    "collections": ("Client Collections Detail", "Lists individual receipts by payment date. Cancelled invoices are excluded.",
                    "Received on|Client|Contract|Invoice|Received UGX|Method|Reference"),
    "payroll": ("Payroll Summary & Exceptions", "Shows current salary records whose native pay periods overlap the selected dates. Amounts are for full pay periods. Run status is shown only when the employee is linked to the latest run for that exact period.",
                "Employee no.|Employee|Pay basis|Period start|Period end|Payable shifts|Rate or fixed base UGX|Gross UGX|Advance recovery UGX|Other deductions UGX|Net UGX|Run status"),
    "profit": ("Contract Profitability", "Estimated contribution at contract level. Revenue excludes invoice tax. Guard cost uses eligible worked shifts at the current base rate. Approved linked expenses exclude payroll-category expenses to avoid overlap. This estimate excludes overtime premiums and unallocated overhead.",
               "Client|Contract|Service revenue UGX|Base shift wages UGX|Other expenses UGX|Contribution UGX|Margin %"),
    "payables": ("Supplier Payables & Aging", "As of the To date. Open supplier invoices include disputed or unapproved amounts. Only completed payments reduce the balance.",
                 "Supplier|Invoice|Purchase order|Due date|Currency|Invoiced|Paid|Outstanding|Days overdue|Aging|Status"),
    "forecast": ("Cash Forecast", "Actual cash uses recorded client receipts and completed supplier payments. Expected cash uses open client balances, approved supplier balances, and approved payroll runs. Opening cash and actual payroll disbursements are outside this forecast.",
                 "Week from|Week to|Actual receipts UGX|Actual supplier payments UGX|Expected receipts UGX|Expected supplier payments UGX|Expected payroll UGX|Projected net movement UGX"),
    "budget": ("Expense & Budget Variance", "Shows approved budgets overlapping the period with approved spend to date within each budget's dates. Commitments are open UGX purchase order amounts after linked invoices. Unbudgeted expenses use the selected period.",
               "Budget|Department|Category|Budget start|Budget end|Allocation UGX|Approved expenses UGX|Remaining UGX|Open PO commitment UGX"),
    "advances": ("Staff Advances & Recoveries", "Disbursements and posted recoveries through the To date. Installment is the current recorded amount.",
                 "Employee no.|Employee|Advance|Disbursed on|Disbursed UGX|Recovered UGX|Outstanding UGX|Current installment UGX"),
    "procurement": ("Procurement Reconciliation", "Compares purchase order, accepted delivery evidence, supplier invoices and completed payments. Variances are order-level checks. Item quantities on receipt notes are stored as text.",
                    "PO|Supplier|Order date|Currency|Order total|Accepted delivery notes|Delivery summary|Invoices|Invoice total|Paid|Invoice less PO|Check"),
}


def aging(due, cutoff):
    days = max((cutoff - due).days, 0)
    if not days:
        return days, "Current"
    return days, next((band for limit, band in ((30, "1–30"), (60, "31–60"), (90, "61–90")) if days <= limit), "Over 90")


def client_invoices(cutoff):
    return Invoice.objects.filter(invoice_date__lte=cutoff, status__in=ISSUED).select_related(
        "client", "contract",
    ).annotate(received=Sum("payments__amount", filter=Q(payments__payment_date__lte=cutoff), default=ZERO))


def supplier_invoices(cutoff):
    return SupplierInvoice.objects.filter(invoice_date__lte=cutoff).exclude(status="cancelled").select_related(
        "supplier", "purchase_order",
    ).annotate(received=Sum("payments__amount", filter=Q(
        payments__payment_status="paid", payments__payment_date__lte=cutoff,
    ), default=ZERO))


def customer_aging(cutoff):
    for inv in client_invoices(cutoff).order_by("client__client_name", "due_date", "pk"):
        outstanding = inv.total_amount - inv.received
        if outstanding > 0:
            yield (inv.client.client_name, inv.invoice_number or inv.pk, inv.due_date, inv.total_amount,
                   max(-inv.amendment_amount, ZERO), inv.received, outstanding, *aging(inv.due_date, cutoff))


def supplier_aging(cutoff):
    for inv in supplier_invoices(cutoff).order_by("due_date", "pk"):
        outstanding = inv.total_amount - inv.received
        if outstanding > 0:
            yield (inv.supplier.supplier_name, inv.invoice_number, inv.purchase_order.po_number, inv.due_date,
                   inv.purchase_order.currency, inv.total_amount, inv.received, outstanding,
                   *aging(inv.due_date, cutoff), inv.get_status_display())


def billing(start, end):
    invoices = client_invoices(end).prefetch_related("sites").order_by("invoice_date", "pk")
    covered = defaultdict(set)
    for inv in invoices:
        service_start = inv.billing_start_date or inv.invoice_date
        service_end = inv.billing_end_date or inv.due_date
        sites = list(inv.sites.all())
        if inv.contract_id and service_start <= end and service_end >= start:
            covered[inv.contract_id].update(site.pk for site in sites)
            if not sites:
                covered[inv.contract_id].add(None)
        if inv.invoice_date >= start:
            yield (inv.client.client_name, inv.contract.contract_number if inv.contract else None,
                   inv.invoice_number or inv.pk, service_start, service_end,
                   ", ".join(sorted(site.site_name for site in sites)) or "Contract level", inv.total_amount,
                   inv.received, inv.total_amount - inv.received, "Issued")
    contracts = Contract.objects.exclude(contract_status="terminated").filter(
        contract_start_date__lte=end, contract_end_date__gte=start,
    ).select_related("client").prefetch_related(Prefetch("sites", queryset=Site.objects.filter(status="active")))
    for contract in contracts.order_by("contract_number", "pk"):
        site_ids = covered[contract.pk]
        if None in site_ids:
            continue
        sites = list(contract.sites.all())
        gaps = [site.site_name for site in sites if site.pk not in site_ids]
        if gaps or (not sites and not site_ids):
            yield (contract.client.client_name, contract.contract_number, None, None, None,
                   ", ".join(sorted(gaps)) or "Contract level", None, None, None, "No issued invoice in service period")


def collections(start, end):
    receipts = Payment.objects.filter(payment_date__range=(start, end)).exclude(invoice__status="cancelled")
    for payment in receipts.select_related("invoice__client", "invoice__contract").order_by("payment_date", "pk"):
        inv = payment.invoice
        yield (payment.payment_date, inv.client.client_name, inv.contract.contract_number if inv.contract else None,
               inv.invoice_number or inv.pk, payment.amount, payment.get_payment_method_display(), payment.transaction_ref)


def current_payroll(start, end, include_exceptions=False):
    runs = {}
    for run in PayrollRun.objects.filter(period__start_date__lte=end, period__end_date__gte=start).select_related(
        "period",
    ).prefetch_related("salaries").order_by("created_at", "pk"):
        for salary in run.salaries.all():
            runs[(salary.pk, run.period.start_date, run.period.end_date)] = run.get_status_display()
    for salary in Salary.objects.select_related("employee").order_by("employee__employee_number"):
        first, last = salary.get_period_dates()
        if first > end or last < start:
            continue
        employee = salary.employee
        fixed = employee.uses_fixed_monthly_salary
        recovery = salary.advance_recovery
        yield (employee.employee_number, f"{employee.first_name} {employee.last_name}",
               "Fixed monthly" if fixed else "Attendance", first, last, None if fixed else salary.shifts_worked,
               employee.fixed_monthly_salary if fixed else salary.daily_rate, salary.gross_pay,
               recovery, salary.total_deductions - recovery, salary.total_salary,
               runs.get((salary.pk, first, last), "No linked run"))

    if include_exceptions:
        missing = Employee.objects.filter(status="active", hire_date__lte=end, salary__isnull=True)
        for employee in missing.order_by("employee_number"):
            yield (employee.employee_number, f"{employee.first_name} {employee.last_name}",
                   None, None, None, None, None, None, None, None, None, "Missing salary record")


def profitability(start, end):
    revenue = defaultdict(lambda: ZERO)
    expenses = defaultdict(lambda: ZERO)
    wages = defaultdict(lambda: ZERO)
    for key, total, tax in Invoice.objects.filter(
        invoice_date__range=(start, end), status__in=ISSUED, contract__isnull=False,
    ).values_list("contract_id", "total_amount", "tax_amount"):
        revenue[key] += total - tax
    for key, total in Expense.objects.filter(
        expense_date__range=(start, end), approval_status="approved", contract__isnull=False,
    ).exclude(category="payroll").values_list("contract_id", "amount"):
        expenses[key] += total
    seen = set()
    rows = Attendance.objects.filter(
        date__range=(start, end), present=True, attended_guard__isnull=False,
    ).select_related("attended_guard", "site", "shift").order_by("date", "pk")
    for row in rows.iterator():
        employee = row.attended_guard
        if employee.uses_fixed_monthly_salary or not row.is_payable_shift:
            continue
        shift_key = (employee.pk, row.date, row.shift.shift_type if row.shift_id else None)
        if shift_key in seen:
            continue
        seen.add(shift_key)
        if row.site and row.site.contract_id:
            wages[row.site.contract_id] += employee.daily_rate
    for contract in Contract.objects.filter(pk__in=revenue.keys() | expenses.keys() | wages.keys()).select_related("client").order_by("contract_number", "pk"):
        billed, wage, expense = revenue[contract.pk], wages[contract.pk], expenses[contract.pk]
        contribution = billed - wage - expense
        margin = (contribution * 100 / billed).quantize(Decimal("0.01")) if billed > 0 else None
        yield (contract.client.client_name, contract.contract_number, billed, wage, expense, contribution, margin)


def forecast(start, end, today):
    buckets = defaultdict(lambda: [ZERO] * 5)

    def record(day, amount, column):
        if start <= day <= end:
            buckets[(day - start).days // 7][column] += amount

    cutoff = min(today, end)
    for day, amount in Payment.objects.filter(payment_date__range=(start, cutoff)).exclude(
        invoice__status="cancelled",
    ).values_list("payment_date", "amount"):
        record(day, amount, 0)
    for day, amount in SupplierPayment.objects.filter(
        payment_date__range=(start, cutoff), payment_status="paid",
        supplier_invoice__purchase_order__currency__iexact="UGX",
    ).exclude(supplier_invoice__status="cancelled").values_list("payment_date", "amount"):
        record(day, amount, 1)
    for inv in client_invoices(cutoff):
        record(max(today, inv.due_date), max(inv.total_amount - inv.received, ZERO), 2)
    for inv in supplier_invoices(cutoff).filter(status__in=FORECAST_PAYABLE, purchase_order__currency__iexact="UGX"):
        record(max(today, inv.due_date), max(inv.total_amount - inv.received, ZERO), 3)
    latest = {}
    for run in PayrollRun.objects.filter(
        period__start_date__lte=end,
    ).select_related("period").order_by("created_at", "pk"):
        latest[run.period_id] = run
    for run in latest.values():
        if run.status == "approved" and run.period.status != "paid":
            record(max(today, run.period.end_date), run.total_net, 4)
    for index in range((end - start).days // 7 + 1):
        first = start + timedelta(days=index * 7)
        last = first + timedelta(days=min(6, (end - first).days))
        receipts, paid, incoming, outgoing, payroll = buckets[index]
        yield (first, last, receipts, paid, incoming, outgoing, payroll, receipts - paid + incoming - outgoing - payroll)


def budget_variance(start, end):
    budgets = Budget.objects.filter(approval_status="approved", period_start__lte=end, period_end__gte=start)
    for budget in budgets.order_by("department", "period_start", "pk"):
        approved = budget.expenses.filter(approval_status="approved", expense_date__range=(
            budget.period_start, min(end, budget.period_end),
        )).aggregate(total=Sum("amount", default=ZERO))["total"]
        orders = PurchaseOrder.objects.filter(requisition__budget=budget, order_date__lte=end, currency__iexact="UGX").exclude(
            status__in=("draft", "cancelled", "closed"),
        ).annotate(invoiced=Sum("supplier_invoices__total_amount", filter=Q(
            supplier_invoices__invoice_date__lte=end,
        ) & ~Q(supplier_invoices__status="cancelled"), default=ZERO))
        commitments = sum((max(order.total_amount - order.invoiced, ZERO) for order in orders), ZERO)
        yield (budget.budget_code or budget.budget_title, budget.get_department_display(), budget.get_budget_category_display(),
               budget.period_start, budget.period_end, budget.allocated_amount, approved,
               budget.allocated_amount - approved, commitments)
    unbudgeted = Expense.objects.filter(budget__isnull=True, approval_status="approved",
                                        expense_date__range=(start, end)).values("category").annotate(total=Sum("amount"))
    categories = dict(Expense.CATEGORY_CHOICES)
    for row in unbudgeted.order_by("category"):
        yield ("Unbudgeted expenses", None, categories.get(row["category"], row["category"]),
               start, end, None, row["total"], None, None)


def staff_advances(cutoff):
    recoveries = dict(AdvanceRecovery.objects.filter(period_end_date__lte=cutoff).values(
        "advance_id",
    ).annotate(total=Sum("amount")).values_list("advance_id", "total"))
    for advance in Advance.objects.filter(
        status__in=("disbursed", "recovered"), disbursement_date__lte=cutoff,
    ).select_related("employee").order_by("disbursement_date", "pk"):
        employee = advance.employee
        recovered = recoveries.get(advance.pk, ZERO)
        yield (employee.employee_number, f"{employee.first_name} {employee.last_name}", advance.pk,
               advance.disbursement_date, advance.amount_requested, recovered,
               max(advance.amount_requested - recovered, ZERO), advance.installment_amount)


def reconciliation(start, end):
    receipts = GoodsReceivedNote.objects.filter(received_date__lte=end, status__in=("accepted", "partially_accepted"))
    invoices = SupplierInvoice.objects.filter(invoice_date__lte=end).exclude(status="cancelled").annotate(
        paid=Sum("payments__amount", filter=Q(payments__payment_status="paid", payments__payment_date__lte=end), default=ZERO),
    )
    orders = PurchaseOrder.objects.filter(order_date__range=(start, end)).exclude(status__in=("draft", "cancelled"))
    for order in orders.select_related("supplier").prefetch_related(
        Prefetch("goods_received_notes", queryset=receipts, to_attr="report_receipts"),
        Prefetch("supplier_invoices", queryset=invoices, to_attr="report_invoices"),
    ).order_by("order_date", "pk"):
        invs = order.report_invoices
        received = order.report_receipts
        amount = sum((inv.total_amount for inv in invs), ZERO)
        paid = sum((inv.paid for inv in invs), ZERO)
        flags = []
        if not received:
            flags.append("Awaiting accepted delivery")
        accepted_ids = {note.pk for note in received}
        if any(inv.goods_received_note_id not in accepted_ids for inv in invs):
            flags.append("Invoice lacks accepted delivery evidence")
        if accepted_ids - {inv.goods_received_note_id for inv in invs}:
            flags.append("Delivery awaiting invoice")
        if invs and amount != order.total_amount:
            flags.append("Invoice total differs from PO")
        yield (order.po_number or order.pk, order.supplier.supplier_name, order.order_date, order.currency,
               order.total_amount, len(received), "; ".join(note.quantity_summary for note in received),
               ", ".join(inv.invoice_number for inv in invs), amount, paid,
               amount - order.total_amount if invs else None, "; ".join(flags) or "Matched at order level")


def parse_date(value, fallback):
    try:
        return date.fromisoformat(value)
    except ValueError:
        return fallback


def excel_cell(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


@require_safe
def finance_reports(request):
    user = request.user
    if not user.is_authenticated:
        return redirect_to_login(request.get_full_path(), reverse("webroaster:login"))
    if not user.is_staff or not (user.is_superuser or user.groups.filter(name__in=("Finance Officer", "Head of Finance")).exists()):
        raise PermissionDenied

    today = timezone.localdate()
    month = today.replace(day=1)
    key = request.GET.get("report", "overview")
    if key not in REPORTS:
        key = "overview"
    initial_end = today + timedelta(days=27) if key == "forecast" else today
    end = parse_date(request.GET.get("to", ""), initial_end)
    as_of = key in ("receivables", "payables", "advances")
    start = parse_date(request.GET.get("from", ""), today if key == "forecast" else end.replace(day=1))
    if not as_of and start > end:
        start, end = end, start
    if key == "forecast" and (end - start).days > 366:
        return HttpResponseBadRequest("Select a forecast range of one year or less.")
    builders = {
        "receivables": lambda: customer_aging(end),
        "billing": lambda: billing(start, end),
        "collections": lambda: collections(start, end),
        "payroll": lambda: current_payroll(start, end, include_exceptions=True),
        "profit": lambda: profitability(start, end),
        "payables": lambda: supplier_aging(end),
        "forecast": lambda: forecast(start, end, today),
        "budget": lambda: budget_variance(start, end),
        "advances": lambda: staff_advances(end),
        "procurement": lambda: reconciliation(start, end),
    }
    cards = ()
    rows = ()
    columns = ()
    note = ""
    title = "Finance Dashboard"
    if key == "overview":
        invoiced = Invoice.objects.filter(invoice_date__range=(month, today), status__in=ISSUED).aggregate(total=Sum("total_amount", default=ZERO))["total"]
        collected = Payment.objects.filter(payment_date__range=(month, today)).exclude(invoice__status="cancelled").aggregate(total=Sum("amount", default=ZERO))["total"]
        overdue = sum((row[6] for row in customer_aging(today) if row[7]), ZERO)
        due = sum((row[7] for row in supplier_aging(today) if row[3] <= today and row[4].upper() == "UGX"), ZERO)
        payroll = sum((row[10] for row in current_payroll(month, today)), ZERO)
        profit = sum((row[5] for row in profitability(month, today)), ZERO)
        cards = (("Invoiced this month", invoiced, "billing"), ("Collected this month", collected, "collections"),
                 ("Overdue client balances", overdue, "receivables"), ("Supplier balances due in UGX", due, "payables"),
                 ("Current net payroll", payroll, "payroll"), ("Estimated contract contribution", profit, "profit"))
    else:
        title, note, headings = REPORTS[key]
        columns = headings.split("|")
        rows = builders[key]()
        if request.GET.get("export") == "csv":
            response = HttpResponse("\ufeff", content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = f'attachment; filename="finance-{key}.csv"'
            response["Cache-Control"] = "private, no-store"
            writer = csv.writer(response)
            writer.writerow(columns)
            writer.writerows(tuple(map(excel_cell, row)) for row in rows)
            return response
    response = render_page(request, "webroaster/finance_reports.html", {
        "title": title, "note": note, "report_key": key, "reports": [(k, value[0]) for k, value in REPORTS.items()],
        "cards": cards, "rows": list(rows), "columns": columns, "start": start, "end": end,
        "as_of": as_of,
    }, "paymees")
    response["Cache-Control"] = "private, no-store"
    return response
