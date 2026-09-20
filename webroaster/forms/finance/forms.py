from webroaster.forms.common import BaseModelForm
from webroaster.models import Advance, Budget, Expense, Invoice, Payment, Payroll, Salary


class SalaryForm(BaseModelForm):
    class Meta:
        model = Salary
        fields = "__all__"


class AdvanceForm(BaseModelForm):
    class Meta:
        model = Advance
        fields = "__all__"
        widgets = {"disbursement_date": forms.DateInput(attrs={"type": "date", "class": "form-control"})}


class InvoiceForm(BaseModelForm):
    class Meta:
        model = Invoice
        fields = "__all__"


class PaymentForm(BaseModelForm):
    class Meta:
        model = Payment
        fields = "__all__"


class PayrollForm(BaseModelForm):
    class Meta:
        model = Payroll
        fields = "__all__"


class BudgetForm(BaseModelForm):
    class Meta:
        model = Budget
        fields = "__all__"


class ExpenseForm(BaseModelForm):
    class Meta:
        model = Expense
        fields = "__all__"

