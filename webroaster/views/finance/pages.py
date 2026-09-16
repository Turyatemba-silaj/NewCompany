from webroaster.forms import AdvanceForm, BudgetForm, ExpenseForm, InvoiceForm, PaymentForm, PayrollForm, SalaryForm
from webroaster.models import Advance, Budget, Expense, Invoice, Payment, Payroll, Salary
from webroaster.views.pages import build_page_views


salary_page_list, salary_page_create, salary_page_detail, salary_page_update, salary_page_delete = build_page_views(
    Salary, SalaryForm, department_name="Finance", template_dir="finance", route_base="finance-salary", list_fields=("employee", "pay_period_start", "net_salary", "status")
)
advance_page_list, advance_page_create, advance_page_detail, advance_page_update, advance_page_delete = build_page_views(
    Advance, AdvanceForm, department_name="Finance", template_dir="finance", route_base="finance-advance", list_fields=("employee", "request_date", "amount_requested", "approval_status")
)
invoice_page_list, invoice_page_create, invoice_page_detail, invoice_page_update, invoice_page_delete = build_page_views(
    Invoice, InvoiceForm, department_name="Finance", template_dir="finance", route_base="finance-invoice", list_fields=("invoice_number", "client", "total_amount", "status")
)
payment_page_list, payment_page_create, payment_page_detail, payment_page_update, payment_page_delete = build_page_views(
    Payment, PaymentForm, department_name="Finance", template_dir="finance", route_base="finance-payment", list_fields=("payment_date", "amount", "payment_method", "transaction_ref")
)
payroll_page_list, payroll_page_create, payroll_page_detail, payroll_page_update, payroll_page_delete = build_page_views(
    Payroll, PayrollForm, department_name="Finance", template_dir="finance", route_base="finance-payroll", list_fields=("invoice_number", "client", "total_amount", "status")
)
budget_page_list, budget_page_create, budget_page_detail, budget_page_update, budget_page_delete = build_page_views(
    Budget, BudgetForm, department_name="Finance", template_dir="finance", route_base="finance-budget", list_fields=("year", "department", "category", "remaining_amount")
)
expense_page_list, expense_page_create, expense_page_detail, expense_page_update, expense_page_delete = build_page_views(
    Expense, ExpenseForm, department_name="Finance", template_dir="finance", route_base="finance-expense", list_fields=("expense_date", "category", "amount", "approved_by")
)

