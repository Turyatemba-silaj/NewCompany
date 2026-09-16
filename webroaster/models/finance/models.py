from django.core.exceptions import ValidationError
from django.db import models


class Salary(models.Model):
    employee = models.ForeignKey("webroaster.Employee", on_delete=models.CASCADE, related_name="salary_records")
    pay_period_start = models.DateField()
    pay_period_end = models.DateField()
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2)
    allowances = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    overtime_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_salary = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField(null=True, blank=True)
    payment_method = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=40, default="Pending")

    class Meta:
        ordering = ["-pay_period_start", "employee"]
        unique_together = ("employee", "pay_period_start", "pay_period_end")

    def __str__(self):
        return f"{self.employee} salary {self.pay_period_start} - {self.pay_period_end}"

    def clean(self):
        if self.pay_period_end < self.pay_period_start:
            raise ValidationError({"pay_period_end": "Pay period end cannot be before the start date."})


class Advance(models.Model):
    employee = models.ForeignKey("webroaster.Employee", on_delete=models.CASCADE, related_name="advances")
    request_date = models.DateField()
    amount_requested = models.DecimalField(max_digits=12, decimal_places=2)
    purpose = models.TextField()
    approval_status = models.CharField(max_length=40, default="Pending")
    approved_by = models.ForeignKey(
        "webroaster.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_advances",
    )
    disbursement_date = models.DateField(null=True, blank=True)
    repayment_status = models.CharField(max_length=40, default="Pending")

    class Meta:
        ordering = ["-request_date"]

    def __str__(self):
        return f"{self.employee} advance - {self.amount_requested}"


class Invoice(models.Model):
    client = models.ForeignKey("webroaster.Client", on_delete=models.CASCADE, related_name="invoices")
    invoice_number = models.CharField(max_length=80, unique=True)
    invoice_date = models.DateField()
    due_date = models.DateField()
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=40, default="Unpaid")

    class Meta:
        ordering = ["-invoice_date", "invoice_number"]

    def __str__(self):
        return self.invoice_number

    def clean(self):
        errors = {}
        if self.due_date < self.invoice_date:
            errors["due_date"] = "Due date cannot be before invoice date."
        if self.paid_amount > self.total_amount:
            errors["paid_amount"] = "Paid amount cannot exceed total amount."
        if self.balance_amount != self.total_amount - self.paid_amount:
            errors["balance_amount"] = "Balance amount must equal total amount minus paid amount."
        if errors:
            raise ValidationError(errors)


class Payment(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True, related_name="payments")
    employee = models.ForeignKey(
        "webroaster.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
    )
    payment_date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=60)
    transaction_ref = models.CharField(max_length=120, unique=True, null=True, blank=True)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["-payment_date"]

    def __str__(self):
        return f"Payment {self.amount} on {self.payment_date}"

    def clean(self):
        if not self.invoice and not self.employee:
            raise ValidationError("A payment must be linked to either an invoice or an employee.")


class Payroll(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payroll_items")
    client = models.ForeignKey("webroaster.Client", on_delete=models.CASCADE, related_name="payroll_items")
    invoice_number = models.CharField(max_length=80)
    invoice_date = models.DateField()
    due_date = models.DateField()
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=40, default="Open")

    class Meta:
        ordering = ["-invoice_date", "invoice_number"]

    def __str__(self):
        return f"Payroll {self.invoice_number}"

    def clean(self):
        errors = {}
        if self.due_date < self.invoice_date:
            errors["due_date"] = "Due date cannot be before invoice date."
        if self.paid_amount > self.total_amount:
            errors["paid_amount"] = "Paid amount cannot exceed total amount."
        if self.balance_amount != self.total_amount - self.paid_amount:
            errors["balance_amount"] = "Balance amount must equal total amount minus paid amount."
        if errors:
            raise ValidationError(errors)


class Budget(models.Model):
    class Department(models.TextChoices):
        OPERATIONS = "Operations", "Operations"
        HUMAN_RESOURCE = "Human Resource", "Human Resource"
        FINANCE = "Finance", "Finance"

    year = models.PositiveIntegerField()
    department = models.CharField(max_length=40, choices=Department.choices)
    category = models.CharField(max_length=100)
    allocated_amount = models.DecimalField(max_digits=12, decimal_places=2)
    spent_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    remaining_amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["-year", "department", "category"]
        unique_together = ("year", "department", "category")

    def __str__(self):
        return f"{self.department} {self.category} budget ({self.year})"

    def clean(self):
        errors = {}
        if self.spent_amount > self.allocated_amount:
            errors["spent_amount"] = "Spent amount cannot exceed allocated amount."
        if self.remaining_amount != self.allocated_amount - self.spent_amount:
            errors["remaining_amount"] = "Remaining amount must equal allocated amount minus spent amount."
        if errors:
            raise ValidationError(errors)


class Expense(models.Model):
    class Category(models.TextChoices):
        PAYROLL = "Payroll", "Payroll"
        OPERATIONS = "Operations", "Operations"
        TRAINING = "Training", "Training"
        EQUIPMENT = "Equipment", "Equipment"
        ADMIN = "Admin", "Admin"

    expense_date = models.DateField()
    category = models.CharField(max_length=40, choices=Category.choices)
    description = models.TextField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    approved_by = models.ForeignKey(
        "webroaster.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_expenses",
    )
    receipt_no = models.CharField(max_length=80, blank=True)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["-expense_date", "category"]

    def __str__(self):
        return f"{self.category} expense - {self.amount}"

