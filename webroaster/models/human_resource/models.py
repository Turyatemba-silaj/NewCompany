from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Employee(models.Model):
    class Department(models.TextChoices):
        OPERATIONS = "Operations", "Operations"
        HUMAN_RESOURCE = "Human Resource", "Human Resource"
        FINANCE = "Finance", "Finance"

    class Gender(models.TextChoices):
        FEMALE = "Female", "Female"
        MALE = "Male", "Male"
        OTHER = "Other", "Other"

    class Status(models.TextChoices):
        ACTIVE = "Active", "Active"
        INACTIVE = "Inactive", "Inactive"

    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=20, choices=Gender.choices)
    phone_number = models.CharField(max_length=30)
    email = models.EmailField(unique=True)
    address = models.TextField()
    national_id = models.CharField(max_length=80, unique=True)
    role_name = models.CharField(max_length=80, blank=True)
    position_title = models.CharField(max_length=120, blank=True)
    department = models.CharField(max_length=40, choices=Department.choices, default=Department.OPERATIONS)
    deployment_area = models.CharField(max_length=150, blank=True)
    hire_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Guard(models.Model):
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, primary_key=True, related_name="guard_profile")
    uniform_size = models.CharField(max_length=20, blank=True)
    qualification = models.CharField(max_length=150, blank=True)
    armed_status = models.BooleanField(default=False)
    training_level = models.CharField(max_length=80, blank=True)
    badge_number = models.CharField(max_length=80, unique=True)
    license_no = models.CharField(max_length=80, unique=True, null=True, blank=True)

    class Meta:
        ordering = ["employee__last_name", "employee__first_name"]

    def __str__(self):
        return f"{self.employee} ({self.badge_number})"


class Supervisor(models.Model):
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, primary_key=True, related_name="supervisor_profile")
    assigned_zone = models.CharField(max_length=120)
    experience_years = models.PositiveIntegerField(default=0)
    authority_level = models.CharField(max_length=80)

    class Meta:
        ordering = ["employee__last_name", "employee__first_name"]

    def __str__(self):
        return f"{self.employee} - {self.assigned_zone}"


class Training(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="trainings")
    training_name = models.CharField(max_length=150)
    provider = models.CharField(max_length=150)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    certificate_no = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=40, default="Scheduled")

    class Meta:
        ordering = ["-start_date", "training_name"]

    def __str__(self):
        return f"{self.training_name} - {self.employee}"

    def clean(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "Training end date cannot be before the start date."})


class Attendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = "Present", "Present"
        ABSENT = "Absent", "Absent"
        LATE = "Late", "Late"

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="attendance_records")
    date = models.DateField()
    time_in = models.TimeField(null=True, blank=True)
    time_out = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["-date", "employee"]
        unique_together = ("employee", "date")

    def __str__(self):
        return f"{self.employee} - {self.date} ({self.status})"

    def clean(self):
        if self.time_in and self.time_out and self.time_out <= self.time_in:
            raise ValidationError({"time_out": "Time out must be after time in."})


class Leave(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="leave_requests")
    leave_type = models.CharField(max_length=80)
    start_date = models.DateField()
    end_date = models.DateField()
    days = models.PositiveIntegerField()
    reason = models.TextField(blank=True)
    approval_status = models.CharField(max_length=40, default="Pending")
    approved_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_leave_requests",
    )

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.employee} - {self.leave_type}"

    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError({"end_date": "Leave end date cannot be before the start date."})


class DisciplinaryAction(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="disciplinary_actions")
    action_type = models.CharField(max_length=80)
    description = models.TextField()
    action_date = models.DateField()
    penalty = models.CharField(max_length=150, blank=True)
    status = models.CharField(max_length=40, default="Open")
    approved_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_disciplinary_actions",
    )

    class Meta:
        ordering = ["-action_date"]

    def __str__(self):
        return f"{self.action_type} - {self.employee}"


class PerformanceEvaluation(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="performance_evaluations")
    eval_date = models.DateField()
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comments = models.TextField(blank=True)
    evaluated_by = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="completed_evaluations")

    class Meta:
        ordering = ["-eval_date"]

    def __str__(self):
        return f"{self.employee} - {self.eval_date} ({self.rating}/5)"


class Document(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="documents")
    doc_type = models.CharField(max_length=80)
    file_path = models.FileField(upload_to="employee_documents/")
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["employee", "doc_type"]

    def __str__(self):
        return f"{self.employee} - {self.doc_type}"

    def clean(self):
        if self.expiry_date and self.issue_date and self.expiry_date < self.issue_date:
            raise ValidationError({"expiry_date": "Expiry date cannot be before issue date."})

