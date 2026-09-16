from django.core.exceptions import ValidationError
from django.db import models


class Client(models.Model):
    client_name = models.CharField(max_length=150)
    contact_person = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    address = models.TextField()
    contract_start_date = models.DateField()
    contract_end_date = models.DateField(null=True, blank=True)
    contract_status = models.CharField(max_length=40, default="Active")

    class Meta:
        ordering = ["client_name"]

    def __str__(self):
        return self.client_name

    def clean(self):
        if self.contract_end_date and self.contract_end_date < self.contract_start_date:
            raise ValidationError({"contract_end_date": "Contract end date cannot be before the start date."})


class Site(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="sites")
    site_name = models.CharField(max_length=150)
    site_address = models.TextField()
    city = models.CharField(max_length=80)
    state = models.CharField(max_length=80, blank=True)
    security_level = models.CharField(max_length=50)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["client__client_name", "site_name"]
        unique_together = ("client", "site_name")

    def __str__(self):
        return f"{self.site_name} - {self.client}"


class Shift(models.Model):
    shift_name = models.CharField(max_length=80, unique=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    hours_per_shift = models.DecimalField(max_digits=5, decimal_places=2)
    shift_type = models.CharField(max_length=60)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["start_time", "shift_name"]

    def __str__(self):
        return self.shift_name


class Deployment(models.Model):
    guard = models.ForeignKey("webroaster.Guard", on_delete=models.PROTECT, related_name="deployments")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="deployments")
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="deployments")
    supervisor = models.ForeignKey("webroaster.Supervisor", on_delete=models.PROTECT, related_name="deployments")
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name="deployments")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=40, default="Active")

    class Meta:
        ordering = ["-start_date", "guard"]

    def __str__(self):
        return f"{self.guard} at {self.site} ({self.shift})"

    def clean(self):
        errors = {}
        if self.end_date and self.end_date < self.start_date:
            errors["end_date"] = "Deployment end date cannot be before the start date."
        if self.site_id and self.client_id and self.site.client_id != self.client_id:
            errors["site"] = "Selected site must belong to the selected client."
        if errors:
            raise ValidationError(errors)


class Incident(models.Model):
    deployment = models.ForeignKey(Deployment, on_delete=models.CASCADE, related_name="incidents")
    guard = models.ForeignKey("webroaster.Guard", on_delete=models.PROTECT, related_name="incidents")
    incident_type = models.CharField(max_length=80)
    description = models.TextField()
    incident_date = models.DateTimeField()
    location = models.CharField(max_length=150)
    severity_level = models.CharField(max_length=50)
    reported_by = models.ForeignKey("webroaster.Employee", on_delete=models.PROTECT, related_name="reported_incidents")

    class Meta:
        ordering = ["-incident_date"]

    def __str__(self):
        return f"{self.incident_type} on {self.incident_date:%Y-%m-%d}"


class PatrolLog(models.Model):
    guard = models.ForeignKey("webroaster.Guard", on_delete=models.CASCADE, related_name="patrol_logs")
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="patrol_logs")
    patrol_time = models.DateTimeField()
    patrol_route = models.CharField(max_length=180)
    observations = models.TextField(blank=True)
    photos = models.FileField(upload_to="patrol_logs/", null=True, blank=True)

    class Meta:
        ordering = ["-patrol_time"]

    def __str__(self):
        return f"{self.guard} - {self.site} at {self.patrol_time:%Y-%m-%d %H:%M}"


class Asset(models.Model):
    asset_name = models.CharField(max_length=150)
    asset_type = models.CharField(max_length=80)
    serial_number = models.CharField(max_length=120, unique=True)
    quantity = models.PositiveIntegerField(default=1)
    condition = models.CharField(max_length=80)
    assigned_to = models.ForeignKey(
        "webroaster.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_assets",
    )
    issue_date = models.DateField(null=True, blank=True)
    return_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["asset_type", "asset_name"]

    def __str__(self):
        return f"{self.asset_name} ({self.serial_number})"

    def clean(self):
        if self.return_date and self.issue_date and self.return_date < self.issue_date:
            raise ValidationError({"return_date": "Return date cannot be before issue date."})

