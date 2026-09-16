from webroaster.models import Advance, Budget, Expense, Invoice, Payment, Payroll, Salary
from webroaster.views.common import build_crud_views


salary_list_create, salary_detail = build_crud_views(Salary)
advance_list_create, advance_detail = build_crud_views(Advance)
invoice_list_create, invoice_detail = build_crud_views(Invoice)
payment_list_create, payment_detail = build_crud_views(Payment)
payroll_list_create, payroll_detail = build_crud_views(Payroll)
budget_list_create, budget_detail = build_crud_views(Budget)
expense_list_create, expense_detail = build_crud_views(Expense)

