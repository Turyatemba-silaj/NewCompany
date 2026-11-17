from datetime import datetime, timedelta
from decimal import Decimal
import re
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from django.utils import timezone
from django.core.validators import MaxValueValidator, MinValueValidator


class Client(models.Model):
    """Manages NewCompany clients."""
    client_id = models.AutoField(primary_key=True)
    client_name = models.CharField(max_length=255)
    contact_person = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20)
    email = models.EmailField()
    address = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.client_name

    class Meta:
        db_table = 'clients'
        verbose_name_plural = "Clients"


class Contract(models.Model):
    """Manages contracts for clients"""
    contract_id = models.AutoField(primary_key=True)
    contract_number = models.CharField(max_length=30, unique=True, blank=True, null=True, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='contracts')
    contract_start_date = models.DateField()
    contract_end_date = models.DateField()
    rate_per_guard = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    contract_value = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    day_shift_guards = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    night_shift_guards = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    

    CONTRACT_STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('pending', 'Pending'),
        ('terminated', 'Terminated'),
    ]
    contract_status = models.CharField(max_length=20, choices=CONTRACT_STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def client_name(self):
        return self.client.client_name

    @property
    def contact_person(self):
        return self.client.contact_person

    @property
    def phone_number(self):
        return self.client.phone_number

    @property
    def email(self):
        return self.client.email

    @property
    def address(self):
        return self.client.address

    @property
    def number_of_sites(self):
        if not self.pk:
            return 0
        return self.sites.count()

    @property
    def number_of_guards(self):
        return self.day_shift_guards + self.night_shift_guards

    @property
    def site_required_guards(self):
        if not self.pk:
            return 0
        return sum(site.number_of_guards for site in self.sites.all())

    @property
    def assigned_guards_count(self):
        if not self.pk:
            return 0
        return sum(site.guards.count() for site in self.sites.all())

    @property
    def remaining_guards(self):
        return max(self.number_of_guards - self.site_required_guards, 0)

    @property
    def guard_contract_value(self):
        return self.number_of_guards * self.rate_per_guard

    @property
    def deliverables_value(self):
        if not self.pk:
            return Decimal("0.00")
        return sum((deliverable.amount for deliverable in self.deliverables.all()), Decimal("0.00"))

    def calculate_contract_value(self):
        return self.guard_contract_value + self.deliverables_value

    def update_contract_value(self):
        self.contract_value = self.calculate_contract_value()
        self.save(update_fields=["contract_value"])

    @staticmethod
    def client_code(client):
        source = getattr(client, "client_name", "") or "Client"
        letters = re.sub(r"[^A-Za-z0-9]", "", source).upper()
        return (letters[:3] or "CLI").ljust(3, "X")

    def generate_contract_number(self):
        return f"{self.client_code(self.client)}-{self.contract_id:06d}"

    def clean(self):
        super().clean()
        if not self.pk:
            return
        allocated_day_guards = sum(site.day_shift_guards for site in self.sites.all())
        allocated_night_guards = sum(site.night_shift_guards for site in self.sites.all())
        if allocated_day_guards > self.day_shift_guards:
            raise ValidationError("Contract day shift guards cannot be less than guards already allocated to sites.")
        if allocated_night_guards > self.night_shift_guards:
            raise ValidationError("Contract night shift guards cannot be less than guards already allocated to sites.")

    def refresh_draft_invoices(self):
        invoice_model = globals().get("Invoice")
        if not invoice_model or not self.pk:
            return
        for invoice in invoice_model.objects.filter(contract=self, status='draft'):
            invoice.save(update_fields=[
                "client",
                "invoice_date",
                "due_date",
                "billing_start_date",
                "billing_end_date",
                "deployed_guards",
                "rate_per_guard",
                "contract_amount",
                "total_amount",
                "description",
                "updated_at",
            ])

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        update_fields = []
        if not self.contract_number:
            self.contract_number = self.generate_contract_number()
            update_fields.append("contract_number")

        calculated_value = self.calculate_contract_value()
        if self.contract_value != calculated_value:
            self.contract_value = calculated_value
            update_fields.append("contract_value")

        if update_fields:
            super().save(update_fields=update_fields)
        self.refresh_draft_invoices()

    def __str__(self):
        return f"{self.contract_number or self.generate_contract_number()} - {self.client.client_name}"

    class Meta:
        db_table = 'contracts'


class ContractDeliverable(models.Model):
    """Manages additional deliverable items included in a contract"""
    DELIVERABLE_CHOICES = [
        ('gun', 'Gun'),
        ('radio', 'Radio'),
        ('walk_through_detector', 'Walk Through Detector'),
        ('dog', 'Dog'),
        ('vehicle', 'Vehicle'),
        ('uniform', 'Uniform'),
        ('other', 'Other'),
    ]

    deliverable_id = models.AutoField(primary_key=True)
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name='deliverables')
    item_name = models.CharField(max_length=100, choices=DELIVERABLE_CHOICES)
    quantity = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        price_config = globals().get("InvoiceBillableItemPrice") and InvoiceBillableItemPrice.active_price_for(self.item_name)
        if price_config:
            self.unit_price = price_config.unit_price
            if hasattr(self, "taxable"):
                self.taxable = price_config.taxable
        self.amount = self.quantity * self.unit_price
        super().save(*args, **kwargs)
        self.contract.update_contract_value()

    def delete(self, *args, **kwargs):
        contract = self.contract
        super().delete(*args, **kwargs)
        contract.update_contract_value()

    def __str__(self):
        return f"{self.item_name} - {self.contract}"

    class Meta:
        db_table = 'contract_deliverables'


class Region(models.Model):
    """Groups sites into deployment regions."""
    region_id = models.AutoField(primary_key=True)
    region_name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.region_name

    class Meta:
        db_table = 'regions'
        verbose_name = 'Region'
        verbose_name_plural = 'Regions'


class Site(models.Model):
    """Manages client sites/locations"""
    site_id = models.AutoField(primary_key=True)
    site_code = models.CharField(max_length=40, unique=True, blank=True, null=True, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, blank=True, null=True, related_name='sites')
    contract = models.ForeignKey(Contract, on_delete=models.SET_NULL, blank=True, null=True, related_name='sites')
    region = models.ForeignKey(Region, on_delete=models.SET_NULL, blank=True, null=True, related_name='sites')
    site_name = models.CharField(max_length=255)
    site_address = models.TextField()
    day_shift_guards = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    night_shift_guards = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    guards = models.ManyToManyField('Employee', blank=True, related_name='assigned_sites')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    LOCATION_REGION_KEYWORDS = {
        'Greater Jinja': ('jinja',),
        'Central Region': ('kampala', 'kampala road', 'entebbe', 'wakiso', 'mukono', 'masaka', 'mpigi', 'mityana'),
        'Western Region': ('mbarara', 'fort portal', 'kabale', 'kasese', 'hoima', 'masindi', 'ntungamo', 'bushenyi'),
        'Eastern Region': ('mbale', 'soroti', 'tororo', 'iganga', 'busia', 'pallisa'),
        'Northern Region': ('gulu', 'lira', 'arua', 'kitgum', 'moyo', 'adjumani', 'nebbi'),
    }

    def infer_region_from_location(self):
        location = f"{self.site_name} {self.site_address}".lower()
        for region_name, keywords in self.LOCATION_REGION_KEYWORDS.items():
            if any(keyword in location for keyword in keywords):
                region = Region.objects.filter(region_name=region_name).first()
                if region:
                    return region
        return None

    def clean(self):
        super().clean()
        if not self.region_id:
            self.region = self.infer_region_from_location()
        if not self.region_id:
            raise ValidationError("Choose a deployment area for this site or include a recognizable site location, for example Kampala Road or Mbarara.")
        if self.client_id and self.site_name:
            duplicate_sites = Site.objects.filter(client_id=self.client_id, site_name__iexact=self.site_name.strip())
            if self.pk:
                duplicate_sites = duplicate_sites.exclude(pk=self.pk)
            if duplicate_sites.exists():
                raise ValidationError({"site_name": "This client already has a site with this name."})
        if self.contract_id:
            if self.client_id and self.contract.client_id != self.client_id:
                raise ValidationError("Selected contract does not belong to the selected client.")
            if self.day_shift_guards > self.contract.day_shift_guards:
                raise ValidationError("Site day shift guards cannot exceed the contract day shift guards.")
            if self.night_shift_guards > self.contract.night_shift_guards:
                raise ValidationError("Site night shift guards cannot exceed the contract night shift guards.")

            other_sites = Site.objects.filter(contract=self.contract)
            if self.pk:
                other_sites = other_sites.exclude(pk=self.pk)
            used_day_guards = sum(site.day_shift_guards for site in other_sites)
            used_night_guards = sum(site.night_shift_guards for site in other_sites)
            if used_day_guards + self.day_shift_guards > self.contract.day_shift_guards:
                raise ValidationError("Total site day shift guards cannot exceed the contract day shift guards.")
            if used_night_guards + self.night_shift_guards > self.contract.night_shift_guards:
                raise ValidationError("Total site night shift guards cannot exceed the contract night shift guards.")

    def save(self, *args, **kwargs):
        if self.contract_id and not self.client_id:
            self.client = self.contract.client
        contract_number = self.contract.contract_number if self.contract_id else ""
        if self.contract_id and (not self.site_code or not self.site_code.startswith(f"{contract_number}-S")):
            self.site_code = self.generate_site_code()
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "site_code"}
        self.full_clean()
        super().save(*args, **kwargs)

    def generate_site_code(self):
        contract_number = self.contract.contract_number or self.contract.generate_contract_number()
        existing_codes = set(
            Site.objects.filter(contract=self.contract)
            .exclude(pk=self.pk)
            .values_list("site_code", flat=True)
        )
        sequence = 1
        while True:
            site_code = f"{contract_number}-S{sequence:03d}"
            if site_code not in existing_codes:
                return site_code
            sequence += 1

    @property
    def number_of_guards(self):
        return self.day_shift_guards + self.night_shift_guards

    @property
    def assigned_guards(self):
        return ", ".join(str(guard) for guard in self.guards.all()) or "-"

    def deployment_area_regions(self):
        region_names = []
        if self.region_id:
            region_names.append(self.region.region_name)
        inferred_region = self.infer_region_from_location()
        if inferred_region:
            region_names.append(inferred_region.region_name)
        return Region.objects.filter(region_name__in=region_names).distinct()

    @property
    def deployment_area_staff(self):
        today = timezone.localdate()
        regions = self.deployment_area_regions()
        if not regions.exists():
            return "-"
        staff = Employee.objects.filter(
            deployment_areas__region__in=regions,
            deployment_areas__status='active',
            deployment_areas__start_date__lte=today,
        ).filter(
            models.Q(deployment_areas__end_date__isnull=True)
            | models.Q(deployment_areas__end_date__gte=today)
        ).distinct().order_by('first_name', 'last_name')
        return ", ".join(str(employee) for employee in staff) or "-"

    @property
    def total_price(self):
        if not self.contract_id:
            return Decimal("0.00")
        return self.number_of_guards * self.contract.rate_per_guard

    def __str__(self):
        return self.site_name

    class Meta:
        db_table = 'sites'
        indexes = [
            models.Index(fields=["region", "site_name"], name="site_region_name_idx"),
            models.Index(fields=["contract", "site_name"], name="site_contract_name_idx"),
            models.Index(fields=["client", "site_name"], name="site_client_name_idx"),
        ]


class SitePost(models.Model):
    """A controlled duty post within a client site."""
    post_id = models.AutoField(primary_key=True)
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="posts")
    post_name = models.CharField(max_length=160)
    description = models.TextField(blank=True, default="")
    required_day_guards = models.PositiveIntegerField(default=0)
    required_night_guards = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def required_guards(self):
        return self.required_day_guards + self.required_night_guards

    def __str__(self):
        return f"{self.site} - {self.post_name}"

    class Meta:
        db_table = "site_posts"
        ordering = ["site__site_name", "post_name"]
        constraints = [
            models.UniqueConstraint(fields=["site", "post_name"], name="uniq_site_post_name"),
        ]


class SiteRiskAssessment(models.Model):
    assessment_id = models.AutoField(primary_key=True)
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="risk_assessments")
    assessed_by = models.ForeignKey("Employee", on_delete=models.SET_NULL, blank=True, null=True, related_name="site_risk_assessments")
    assessment_date = models.DateField(default=timezone.localdate)
    RISK_LEVEL_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("critical", "Critical"),
    ]
    risk_level = models.CharField(max_length=20, choices=RISK_LEVEL_CHOICES, default="medium")
    threats = models.TextField(blank=True, default="")
    vulnerabilities = models.TextField(blank=True, default="")
    recommendations = models.TextField(blank=True, default="")
    next_review_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.site} risk assessment - {self.assessment_date}"

    class Meta:
        db_table = "site_risk_assessments"
        ordering = ["-assessment_date", "site__site_name"]


class Shift(models.Model):
    """Reusable shift template used by deployments."""
    shift_id = models.AutoField(primary_key=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    hours_per_shift = models.DecimalField(max_digits=5, decimal_places=2)

    SHIFT_TYPE_CHOICES = [
        ('day', 'Day'),
        ('night', 'Night'),
    ]
    shift_type = models.CharField(max_length=20, choices=SHIFT_TYPE_CHOICES, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def calculate_hours_per_shift(self):
        if not self.start_time or not self.end_time:
            return Decimal("0.00")
        start = datetime.combine(timezone.now().date(), self.start_time)
        end = datetime.combine(timezone.now().date(), self.end_time)
        if end <= start:
            end += timedelta(days=1)
        hours = Decimal(str((end - start).total_seconds() / 3600))
        return hours.quantize(Decimal("0.01"))

    def save(self, *args, **kwargs):
        if self.start_time:
            self.shift_type = "day" if 7 <= self.start_time.hour < 18 else "night"
        self.hours_per_shift = self.calculate_hours_per_shift()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.get_shift_type_display()

    class Meta:
        db_table = 'shifts'
        constraints = [
            models.UniqueConstraint(
                fields=['start_time', 'end_time', 'hours_per_shift'],
                name='unique_shift_template',
            )
        ]


class Asset(models.Model):
    """Stores all company-owned assets in inventory."""
    asset_id = models.AutoField(primary_key=True)
    ASSET_TYPE_CHOICES = [
        ('vehicle', 'Vehicle'),
        ('equipment', 'Equipment'),
        ('uniform', 'Uniform'),
        ('gun', 'Gun'),
        ('weapon', 'Weapon'),
        ('other', 'Other'),
    ]
    asset_type = models.CharField(max_length=50, choices=ASSET_TYPE_CHOICES)
    asset_name = models.CharField(max_length=255, blank=True, default="")
    asset_number = models.CharField("Serial Number", max_length=100, blank=True)
    make = models.CharField(max_length=120, blank=True, default="")
    model = models.CharField(max_length=120, blank=True, default="")
    engine_number = models.CharField(max_length=120, blank=True, default="")
    chassis_number = models.CharField(max_length=120, blank=True, default="")
    number_plate = models.CharField(max_length=80, blank=True, default="")
    police_number = models.CharField(max_length=120, blank=True, default="")
    color = models.CharField(max_length=80, blank=True, default="")
    size = models.CharField(max_length=80, blank=True, default="")
    CONDITION_CHOICES = [
        ('new', 'New'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
        ('damaged', 'Damaged'),
    ]
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, blank=True, default="")
    storage_location = models.CharField(max_length=160, blank=True, default="")
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        name = self.asset_name or self.get_asset_type_display()
        serial = f" - {self.asset_number}" if self.asset_number else ""
        return f"{name}{serial}"

    @property
    def assets_issued_out(self):
        return sum(assignment.quantity for assignment in self.assignments.filter(status='assigned'))

    @property
    def stock_balance(self):
        return self.quantity - self.assets_issued_out

    @property
    def is_low_stock(self):
        return self.stock_balance <= 10

    @property
    def low_stock_message(self):
        if not self.is_low_stock:
            return "-"
        return f"{self.get_asset_type_display()} is low please refill more {self.asset_name or self.get_asset_type_display()}"

    class Meta:
        db_table = 'assets'


class AssetAssignment(models.Model):
    """Tracks asset issue and accountability without changing company inventory."""
    assignment_id = models.AutoField(primary_key=True)
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='assignments')
    quantity = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    guard = models.ForeignKey('Employee', on_delete=models.SET_NULL, blank=True, null=True, related_name='guard_asset_assignments')
    driver = models.ForeignKey('Employee', on_delete=models.SET_NULL, blank=True, null=True, related_name='vehicle_assignments')
    site = models.ForeignKey(Site, on_delete=models.SET_NULL, blank=True, null=True, related_name='asset_assignments')
    deployment = models.ForeignKey('Deployment', on_delete=models.SET_NULL, blank=True, null=True, related_name='asset_assignments')
    issued_by = models.ForeignKey('Employee', on_delete=models.SET_NULL, blank=True, null=True, related_name='issued_asset_assignments')
    received_by = models.ForeignKey('Employee', on_delete=models.SET_NULL, blank=True, null=True, related_name='received_asset_assignments')
    assigned_date = models.DateField(default=timezone.now)
    acknowledged_at = models.DateTimeField(blank=True, null=True)
    return_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=[('assigned', 'Assigned'), ('returned', 'Returned'), ('lost', 'Lost'), ('damaged', 'Damaged')], default='assigned')
    ACCOUNTABILITY_STATUS_CHOICES = [
        ('pending_acknowledgement', 'Pending Acknowledgement'),
        ('acknowledged', 'Acknowledged'),
        ('cleared', 'Cleared'),
        ('escalated', 'Escalated'),
    ]
    accountability_status = models.CharField(max_length=30, choices=ACCOUNTABILITY_STATUS_CHOICES, default='pending_acknowledgement')
    CONDITION_CHOICES = [
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
        ('damaged', 'Damaged'),
    ]
    condition_issued = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='good')
    condition_returned = models.CharField(max_length=20, choices=CONDITION_CHOICES, blank=True, default='')
    notes = models.TextField(blank=True)
    accountability_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def assigned_to(self):
        return self.guard or self.driver or self.site or self.deployment or "-"

    def clean(self):
        super().clean()
        if self.return_date and self.assigned_date and self.return_date < self.assigned_date:
            raise ValidationError("Return date cannot be earlier than assigned date.")
        if not self.guard_id and not self.driver_id and not self.site_id and not self.deployment_id:
            raise ValidationError("Assign the asset to a guard, driver, site, or deployment.")
        if self.asset_id:
            asset_type = self.asset.asset_type
            if asset_type == "uniform":
                if not self.guard_id:
                    raise ValidationError({"guard": "Uniform assets must be assigned to an employee."})
                if self.driver_id or self.site_id or self.deployment_id:
                    raise ValidationError("Uniform assets can only be assigned to an employee.")
            elif asset_type == "vehicle":
                if not self.driver_id:
                    raise ValidationError({"driver": "Vehicle assets must be assigned to a driver."})
                if self.guard_id or self.site_id or self.deployment_id:
                    raise ValidationError("Vehicle assets can only be assigned to a driver.")
            elif asset_type in ("gun", "weapon", "equipment"):
                if not self.site_id:
                    raise ValidationError({"site": f"{self.asset.get_asset_type_display()} assets must be assigned to a site."})
                if self.guard_id or self.driver_id or self.deployment_id:
                    raise ValidationError(f"{self.asset.get_asset_type_display()} assets can only be assigned to a site.")
        if self.status == 'returned' and not self.return_date:
            raise ValidationError("Return date is required when an asset is returned.")
        if self.status in ('lost', 'damaged') and not self.accountability_notes:
            raise ValidationError("Accountability notes are required for lost or damaged assets.")

    def sync_accountability_status(self):
        if self.status == 'returned':
            self.accountability_status = 'cleared'
        elif self.status in ('lost', 'damaged'):
            self.accountability_status = 'escalated'
        elif self.received_by_id or self.acknowledged_at:
            self.accountability_status = 'acknowledged'
        else:
            self.accountability_status = 'pending_acknowledgement'

    def save(self, *args, **kwargs):
        if self.received_by_id and not self.acknowledged_at:
            self.acknowledged_at = timezone.now()
        self.sync_accountability_status()
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            update_fields = set(update_fields)
            update_fields.update({'accountability_status', 'acknowledged_at'})
            kwargs['update_fields'] = list(update_fields)
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.asset} x {self.quantity}"

    class Meta:
        db_table = 'asset_assignments'


class Incident(models.Model):
    incident_id = models.AutoField(primary_key=True)
    INCIDENT_TYPE_CHOICES = [
        ('theft', 'Theft'),
        ('breach', 'Breach'),
        ('vandalism', 'Vandalism'),
        ('injury', 'Injury'),
        ('other', 'Other'),
    ]
    SEVERITY_LEVEL_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    STATUS_CHOICES = [
        ('reported', 'Reported'),
        ('notified', 'Authorities Notified'),
        ('investigating', 'Under Investigation'),
        ('action_taken', 'Action Taken'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='incidents')
    incident_type = models.CharField(max_length=50, choices=INCIDENT_TYPE_CHOICES)
    description = models.TextField()
    date_time = models.DateTimeField()
    location = models.CharField(max_length=255)
    severity_level = models.CharField(max_length=20, choices=SEVERITY_LEVEL_CHOICES)
    reported_by = models.CharField(max_length=255)
    reported_to = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='reported')
    alleged_stolen_items = models.TextField(blank=True, default='')
    commencement_of_investigations = models.DateField(blank=True, null=True)
    police_case_reference = models.CharField(max_length=255, blank=True, default='')
    suspects = models.TextField(blank=True, default='')
    guards_on_duty = models.TextField(blank=True, default='')
    affected_items_details = models.TextField(
        blank=True,
        default='',
        help_text='Enter one item per line. Use: item | serial number | engraved number.',
    )
    occurrence_summary = models.TextField(blank=True, default='')
    immediate_action_taken = models.TextField(blank=True, default='')
    notification_summary = models.TextField(blank=True, default='')
    investigation_assigned_to = models.ForeignKey('Employee', on_delete=models.SET_NULL, blank=True, null=True, related_name='assigned_incident_investigations')
    investigation_findings = models.TextField(blank=True, default='')
    corrective_action = models.TextField(blank=True, default='')
    conclusion = models.TextField(blank=True, default='')
    closed_by = models.CharField(max_length=255, blank=True, default='')
    closed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_incident_type_display()} at {self.site}"

    class Meta:
        db_table = 'incidents'


class IncidentNotification(models.Model):
    notification_id = models.AutoField(primary_key=True)
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name='notifications')
    recipient = models.ForeignKey('Employee', on_delete=models.CASCADE, related_name='incident_notifications')
    authority_group = models.CharField(max_length=50)
    message = models.TextField()
    notified_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('sent', 'Sent'), ('failed', 'Failed')], default='pending')
    delivery_note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.incident} - {self.recipient}"

    class Meta:
        db_table = 'incident_notifications'
        unique_together = ('incident', 'recipient', 'authority_group')


class Patrol_Log(models.Model):
    patrol_id = models.AutoField(primary_key=True)
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='patrol_logs')
    patrol_date = models.DateField()
    patrol_route = models.CharField(max_length=255)
    quantity = models.IntegerField()
    duration = models.DecimalField(max_digits=5, decimal_places=2, help_text="Duration in hours")
    issue_date = models.DateField()
    return_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Patrol - {self.patrol_date} at {self.site.site_name}"

    class Meta:
        db_table = 'patrol_logs'


class PatrolRoute(models.Model):
    route_id = models.AutoField(primary_key=True)
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="patrol_routes")
    route_name = models.CharField(max_length=160)
    description = models.TextField(blank=True, default="")
    required_frequency_minutes = models.PositiveIntegerField(default=60)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.route_name} - {self.site}"

    class Meta:
        db_table = "patrol_routes"
        ordering = ["site__site_name", "route_name"]
        constraints = [
            models.UniqueConstraint(fields=["site", "route_name"], name="uniq_patrol_route"),
        ]


class PatrolCheckpoint(models.Model):
    checkpoint_id = models.AutoField(primary_key=True)
    route = models.ForeignKey(PatrolRoute, on_delete=models.CASCADE, related_name="checkpoints")
    checkpoint_name = models.CharField(max_length=160)
    sequence = models.PositiveIntegerField(default=1)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    verification_code = models.CharField(max_length=80, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.route} - {self.checkpoint_name}"

    class Meta:
        db_table = "patrol_checkpoints"
        ordering = ["route", "sequence", "checkpoint_name"]
        constraints = [
            models.UniqueConstraint(fields=["route", "sequence"], name="uniq_route_checkpoint_seq"),
        ]


class PatrolSession(models.Model):
    session_id = models.AutoField(primary_key=True)
    route = models.ForeignKey(PatrolRoute, on_delete=models.CASCADE, related_name="sessions")
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="patrol_sessions")
    started_by = models.ForeignKey("Employee", on_delete=models.SET_NULL, blank=True, null=True, related_name="patrol_sessions_started")
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(blank=True, null=True)
    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("missed", "Missed"),
        ("cancelled", "Cancelled"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="scheduled")
    remarks = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def missed_checkpoints(self):
        if not self.pk:
            return 0
        required_ids = set(self.route.checkpoints.filter(is_active=True).values_list("pk", flat=True))
        visited_ids = set(self.checkpoint_visits.values_list("checkpoint_id", flat=True))
        return len(required_ids - visited_ids)

    @property
    def due_at(self):
        return self.started_at + timedelta(minutes=max(self.route.required_frequency_minutes, 1))

    @property
    def is_complete(self):
        return self.pk and self.missed_checkpoints == 0

    def refresh_status_from_visits(self):
        if not self.pk:
            return
        if self.status in ("cancelled", "missed"):
            return
        if self.is_complete:
            self.status = "completed"
            if not self.completed_at:
                self.completed_at = timezone.now()
        elif self.checkpoint_visits.exists():
            self.status = "in_progress"

    def mark_missed_if_overdue(self, now=None):
        now = now or timezone.now()
        if self.status in ("scheduled", "in_progress") and self.due_at < now and self.missed_checkpoints > 0:
            self.status = "missed"
            self.save(update_fields=["status", "updated_at"])
            return True
        return False

    def clean(self):
        super().clean()
        if self.route_id and self.site_id and self.route.site_id != self.site_id:
            raise ValidationError("Selected route does not belong to the selected site.")
        if self.completed_at and self.completed_at < self.started_at:
            raise ValidationError("Completion time cannot be earlier than start time.")

    def save(self, *args, **kwargs):
        self.refresh_status_from_visits()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.route} - {self.started_at:%Y-%m-%d %H:%M}"

    class Meta:
        db_table = "patrol_sessions"
        ordering = ["-started_at"]


class PatrolCheckpointVisit(models.Model):
    visit_id = models.AutoField(primary_key=True)
    session = models.ForeignKey(PatrolSession, on_delete=models.CASCADE, related_name="checkpoint_visits")
    checkpoint = models.ForeignKey(PatrolCheckpoint, on_delete=models.CASCADE, related_name="visits")
    visited_by = models.ForeignKey("Employee", on_delete=models.SET_NULL, blank=True, null=True, related_name="patrol_checkpoint_visits")
    visited_at = models.DateTimeField(default=timezone.now)
    verification_method = models.CharField(max_length=30, choices=[
        ("manual", "Manual"),
        ("gps", "GPS"),
        ("qr", "QR"),
        ("nfc", "NFC"),
        ("rfid", "RFID"),
        ("biometric", "Biometric"),
    ], default="manual")
    latitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    remarks = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        if self.session_id and self.checkpoint_id and self.checkpoint.route_id != self.session.route_id:
            raise ValidationError("Checkpoint does not belong to the selected patrol route.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        self.session.refresh_status_from_visits()
        self.session.save(update_fields=["status", "completed_at", "updated_at"])

    def __str__(self):
        return f"{self.checkpoint} - {self.visited_at:%Y-%m-%d %H:%M}"

    class Meta:
        db_table = "patrol_checkpoint_visits"
        ordering = ["session", "visited_at"]
        constraints = [
            models.UniqueConstraint(fields=["session", "checkpoint"], name="uniq_session_checkpoint"),
        ]


class Deployment(models.Model):
    """Manages deployments of guards to sites"""
    SHIFT_COVERAGE_CHOICES = [
        ('day', 'Day'),
        ('night', 'Night'),
        ('day_night', 'Day and Night'),
    ]
    DEPLOYMENT_STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    deployment_id = models.AutoField(primary_key=True)
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, blank=True, null=True, related_name='deployments')
    guard = models.ForeignKey('Employee', on_delete=models.CASCADE, related_name='guard_deployments', null=True, blank=True)
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name='deployments')
    shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, null=True, related_name='deployments')
    day_guards = models.ManyToManyField('Employee', blank=True, related_name='day_shift_deployments')
    night_guards = models.ManyToManyField('Employee', blank=True, related_name='night_shift_deployments')
    shift_coverage = models.CharField(max_length=20, choices=SHIFT_COVERAGE_CHOICES, default='day_night')
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=DEPLOYMENT_STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def covered_shift_types(self):
        if self.shift_coverage == 'day_night':
            return ('day', 'night')
        return (self.shift_coverage or (self.shift.shift_type if self.shift_id else 'day'),)

    @property
    def shift_summary(self):
        return self.get_shift_coverage_display()

    @property
    def day_guards_summary(self):
        if not self.pk:
            return "-"
        return ", ".join(str(guard) for guard in self.day_guards.all()) or "-"

    @property
    def night_guards_summary(self):
        if not self.pk:
            return "-"
        return ", ".join(str(guard) for guard in self.night_guards.all()) or "-"

    def roster_period_end(self):
        return self.end_date or self.start_date

    def guards_for_shift_type(self, shift_type):
        if not self.pk:
            return Employee.objects.none()
        if shift_type == "day":
            return self.day_guards.filter(status="active").order_by("employee_number", "first_name", "last_name")
        if shift_type == "night":
            return self.night_guards.filter(status="active").order_by("employee_number", "first_name", "last_name")
        return Employee.objects.none()

    @staticmethod
    def shift_for_type(shift_type):
        return Shift.objects.filter(shift_type=shift_type).order_by("shift_id").first()

    @staticmethod
    def shift_window(work_date, shift):
        start_at = timezone.make_aware(datetime.combine(work_date, shift.start_time), timezone.get_current_timezone())
        end_at = timezone.make_aware(datetime.combine(work_date, shift.end_time), timezone.get_current_timezone())
        if end_at <= start_at:
            end_at += timedelta(days=1)
        return start_at, end_at

    def sync_patrol_sessions_for_shift(self, work_date, shift):
        if not self.site_id or not shift:
            return 0
        created = 0
        start_at, end_at = self.shift_window(work_date, shift)
        routes = self.site.patrol_routes.filter(is_active=True)
        for route in routes:
            interval = timedelta(minutes=max(route.required_frequency_minutes, 1))
            scheduled_at = start_at
            while scheduled_at < end_at:
                _session, session_created = PatrolSession.objects.get_or_create(
                    route=route,
                    site=self.site,
                    started_at=scheduled_at,
                    defaults={"status": "scheduled"},
                )
                if session_created:
                    created += 1
                scheduled_at += interval
        return created

    def sync_operational_plan(self):
        """Create roster assignments and expected attendance from this deployment."""
        if not self.pk or self.status != "active" or not self.site_id or not self.start_date:
            return {"rosters": 0, "assignments": 0, "attendance": 0, "patrol_sessions": 0, "skipped": 0}

        period_end = self.roster_period_end()
        created_counts = {"rosters": 0, "assignments": 0, "attendance": 0, "patrol_sessions": 0, "skipped": 0}
        with transaction.atomic():
            roster, roster_created = Roster.objects.get_or_create(
                period_start=self.start_date,
                period_end=period_end,
                deployment_area=self.site.region,
                defaults={"status": "draft"},
            )
            if roster_created:
                created_counts["rosters"] += 1

            work_date = self.start_date
            while work_date <= period_end:
                for shift_type in self.covered_shift_types:
                    shift = self.shift_for_type(shift_type)
                    if not shift:
                        created_counts["skipped"] += self.guards_for_shift_type(shift_type).count()
                        continue
                    created_counts["patrol_sessions"] += self.sync_patrol_sessions_for_shift(work_date, shift)
                    for guard in self.guards_for_shift_type(shift_type):
                        if hasattr(guard, "is_deployment_eligible") and not guard.is_deployment_eligible(work_date):
                            created_counts["skipped"] += 1
                            continue
                        if not Attendance.employee_has_deployment_area(guard, self.site, work_date):
                            created_counts["skipped"] += 1
                            continue
                        existing_assignment = RosterAssignment.objects.filter(
                            guard=guard,
                            date=work_date,
                            shift=shift,
                        ).first()
                        if existing_assignment and existing_assignment.deployment_id not in (None, self.pk):
                            created_counts["skipped"] += 1
                            continue
                        assignment, assignment_created = RosterAssignment.objects.update_or_create(
                            guard=guard,
                            date=work_date,
                            shift=shift,
                            defaults={
                                "roster": roster,
                                "site": self.site,
                                "deployment": self,
                                "assignment_type": "normal",
                                "status": "scheduled",
                            },
                        )
                        if assignment_created:
                            created_counts["assignments"] += 1
                        existing_attendance = Attendance.objects.filter(
                            scheduled_guard=guard,
                            date=work_date,
                            shift__shift_type=shift_type,
                        ).first()
                        if existing_attendance:
                            if existing_attendance.site_id == self.site_id:
                                existing_attendance.roster_assignment = assignment
                                existing_attendance.deployment = self
                                existing_attendance.shift = shift
                                existing_attendance.attendance_source = "deployment_roster"
                                existing_attendance.save(update_fields=["roster_assignment", "deployment", "shift", "attendance_source", "updated_at"])
                            else:
                                created_counts["skipped"] += 1
                            continue
                        Attendance.objects.create(
                            deployment=self,
                            roster_assignment=assignment,
                            site=self.site,
                            shift=shift,
                            scheduled_guard=guard,
                            employee=guard,
                            present=False,
                            reason="Awaiting supervisor verification",
                            date=work_date,
                            time_in=shift.start_time,
                            attendance_source="deployment_roster",
                        )
                        created_counts["attendance"] += 1
                work_date += timedelta(days=1)
        return created_counts

    def clean(self):
        super().clean()
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError("End date cannot be earlier than start date.")
        if self.site_id and not self.client_id and self.site.client_id:
            self.client = self.site.client
        if self.site_id and self.client_id and self.site.client_id and self.site.client_id != self.client_id:
            raise ValidationError("Selected site does not belong to the selected client.")
        if not self.site_id or self.status != 'active' or not self.start_date:
            return

        schedule_end = self.end_date or self.start_date
        if self.site.contract_id:
            contract = self.site.contract
            if self.client_id and contract.client_id != self.client_id:
                raise ValidationError("Selected deployment client does not match the site contract client.")
            if self.start_date < contract.contract_start_date or schedule_end > contract.contract_end_date:
                raise ValidationError("Deployment dates must be within the selected site contract period.")

        for shift_type in self.covered_shift_types:
            required_guards = self.site.day_shift_guards if shift_type == "day" else self.site.night_shift_guards
            if required_guards <= 0:
                raise ValidationError(f"{self.site} does not require a {shift_type} shift deployment under its contract guard allocation.")

        overlapping_deployments = Deployment.objects.filter(
            site=self.site,
            status='active',
            start_date__lte=schedule_end,
        ).filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=self.start_date))
        if self.pk:
            overlapping_deployments = overlapping_deployments.exclude(pk=self.pk)
        requested_coverage = set(self.covered_shift_types)
        for deployment in overlapping_deployments:
            overlap = requested_coverage.intersection(deployment.covered_shift_types)
            if overlap:
                overlap_label = " and ".join(shift_type.title() for shift_type in sorted(overlap))
                raise ValidationError(
                    f"{self.site} already has an active {overlap_label} deployment during this date range."
                )

    def refresh_draft_invoices(self):
        invoice_model = globals().get("Invoice")
        if not invoice_model or not self.site_id or not self.site.contract_id:
            return
        for invoice in invoice_model.objects.filter(contract=self.site.contract, status='draft'):
            invoice.save(update_fields=["client", "deployed_guards", "rate_per_guard", "contract_amount", "total_amount", "description", "updated_at"])

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        self.refresh_draft_invoices()

    def delete(self, *args, **kwargs):
        contract = self.site.contract if self.site_id else None
        result = super().delete(*args, **kwargs)
        invoice_model = globals().get("Invoice")
        if invoice_model and contract:
            for invoice in invoice_model.objects.filter(contract=contract, status='draft'):
                invoice.save(update_fields=["client", "deployed_guards", "rate_per_guard", "contract_amount", "total_amount", "description", "updated_at"])
        return result

    def __str__(self):
        client_name = self.client if self.client_id else "No client"
        return f"{client_name} - {self.site.site_name} - {self.shift_summary} ({self.start_date})"

    class Meta:
        db_table = 'deployments'
        indexes = [
            models.Index(fields=["site", "status", "start_date"], name="dep_site_status_start_idx"),
            models.Index(fields=["site", "status", "end_date"], name="dep_site_status_end_idx"),
            models.Index(fields=["shift_coverage", "status"], name="dep_coverage_status_idx"),
        ]

class DeploymentArea(models.Model):
    """Allocates a guard or supervisor to a deployment work area."""
    deployment_area_id = models.AutoField(primary_key=True)
    employee = models.ForeignKey('Employee', on_delete=models.CASCADE, related_name='deployment_areas')
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name='deployment_areas')
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    transferred_by_hr_manager = models.ForeignKey(
        'Employee',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='approved_deployment_transfers',
        limit_choices_to={'role__in': ['hr_officer', 'manager']},
    )
    transfer_notes = models.TextField(blank=True)

    AREA_STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    status = models.CharField(max_length=20, choices=AREA_STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.employee_id and self.employee.role not in ('guard', 'supervisor'):
            raise ValidationError("Deployment areas can only be assigned to guards and supervisors.")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError("End date cannot be earlier than start date.")
        if self.transferred_by_hr_manager_id and self.transferred_by_hr_manager.role not in ('hr_officer', 'manager'):
            raise ValidationError("Transfers must be approved by a human resource manager.")
        if not self.employee_id or not self.region_id or self.status != 'active' or not self.start_date:
            return

        allocation_end = self.end_date or self.start_date
        overlapping_areas = DeploymentArea.objects.filter(
            employee=self.employee,
            status='active',
            start_date__lte=allocation_end,
        ).filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=self.start_date))
        if self.pk:
            overlapping_areas = overlapping_areas.exclude(pk=self.pk)
        if overlapping_areas.exclude(region=self.region).exists() and not self.transferred_by_hr_manager_id:
            raise ValidationError("Human resource manager approval is required to transfer this employee to another deployment area.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def covers(self, site, work_date):
        if not site or not site.region_id:
            return False
        if self.status != 'active' or self.region_id != site.region_id or self.start_date > work_date:
            return False
        return self.end_date is None or self.end_date >= work_date

    def __str__(self):
        return f"{self.employee} - {self.region} ({self.start_date})"

    class Meta:
        db_table = 'deployment_areas'
        verbose_name = 'Deployment Area'
        verbose_name_plural = 'Deployment Areas'
        indexes = [
            models.Index(fields=["region", "status", "start_date"], name="deparea_region_status_idx"),
            models.Index(fields=["employee", "status", "start_date"], name="deparea_employee_status_idx"),
            models.Index(fields=["region", "end_date"], name="deparea_region_end_idx"),
        ]




class Roster(models.Model):
    roster_id = models.AutoField(primary_key=True)
    period_start = models.DateField()
    period_end = models.DateField()
    deployment_area = models.ForeignKey(Region, on_delete=models.SET_NULL, blank=True, null=True, related_name="rosters")
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("approved", "Approved"),
        ("published", "Published"),
        ("cancelled", "Cancelled"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    prepared_by = models.ForeignKey("Employee", on_delete=models.SET_NULL, blank=True, null=True, related_name="prepared_rosters")
    approved_by = models.ForeignKey("Employee", on_delete=models.SET_NULL, blank=True, null=True, related_name="approved_rosters")
    published_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.period_end and self.period_start and self.period_end < self.period_start:
            raise ValidationError("Roster end date cannot be earlier than start date.")
        if self.status in ("approved", "published") and not self.approved_by_id:
            raise ValidationError("Approved or published rosters require an approver.")
        if self.status == "published" and not self.published_at:
            self.published_at = timezone.now()

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        area = self.deployment_area or "All areas"
        return f"{area} roster {self.period_start} to {self.period_end}"

    class Meta:
        db_table = "rosters"
        ordering = ["-period_start", "deployment_area"]
        indexes = [
            models.Index(fields=["period_start", "period_end"], name="roster_period_idx"),
            models.Index(fields=["deployment_area", "status"], name="roster_area_status_idx"),
        ]


class RosterAssignment(models.Model):
    assignment_id = models.AutoField(primary_key=True)
    roster = models.ForeignKey(Roster, on_delete=models.CASCADE, related_name="assignments")
    guard = models.ForeignKey("Employee", on_delete=models.CASCADE, related_name="roster_assignments")
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="roster_assignments")
    post = models.ForeignKey(SitePost, on_delete=models.SET_NULL, blank=True, null=True, related_name="roster_assignments")
    shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, blank=True, null=True, related_name="roster_assignments")
    deployment = models.ForeignKey(Deployment, on_delete=models.SET_NULL, blank=True, null=True, related_name="roster_assignments")
    date = models.DateField()
    ASSIGNMENT_TYPE_CHOICES = [
        ("normal", "Normal"),
        ("relief", "Relief"),
        ("replacement", "Replacement"),
        ("overtime", "Overtime"),
        ("rest", "Rest"),
    ]
    assignment_type = models.CharField(max_length=20, choices=ASSIGNMENT_TYPE_CHOICES, default="normal")
    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("confirmed", "Confirmed"),
        ("cancelled", "Cancelled"),
        ("completed", "Completed"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="scheduled")
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.roster_id and self.date and not (self.roster.period_start <= self.date <= self.roster.period_end):
            raise ValidationError("Assignment date must fall within the roster period.")
        if self.post_id and self.site_id and self.post.site_id != self.site_id:
            raise ValidationError("Selected post does not belong to the selected site.")
        if self.guard_id and self.site_id and self.date and not Attendance.employee_has_deployment_area(self.guard, self.site, self.date):
            raise ValidationError("This guard is outside the selected site's deployment area.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.guard} - {self.site} - {self.date}"

    class Meta:
        db_table = "roster_assignments"
        ordering = ["date", "site__site_name", "shift__shift_type", "guard__employee_number"]
        indexes = [
            models.Index(fields=["date", "site", "shift"], name="rostassign_date_site_idx"),
            models.Index(fields=["guard", "date"], name="rostassign_guard_date_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["guard", "date", "shift"], name="uniq_guard_roster_shift"),
        ]


class Attendance(models.Model):
    """Manages employee attendance"""
    attendance_id = models.AutoField(primary_key=True)
    deployment = models.ForeignKey(Deployment, on_delete=models.SET_NULL, blank=True, null=True, related_name='attendance_records')
    roster_assignment = models.ForeignKey(RosterAssignment, on_delete=models.SET_NULL, blank=True, null=True, related_name="attendance_records")
    site = models.ForeignKey(Site, on_delete=models.SET_NULL, blank=True, null=True, related_name='attendance_records')
    shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, blank=True, null=True, related_name='attendance_records')
    scheduled_guard = models.ForeignKey('Employee', on_delete=models.SET_NULL, blank=True, null=True, related_name='scheduled_attendance_records')
    attended_guard = models.ForeignKey('Employee', on_delete=models.SET_NULL, blank=True, null=True, related_name='attended_attendance_records')
    present = models.BooleanField(default=False)
    reason = models.CharField(max_length=255, blank=True)
    VERIFICATION_METHOD_CHOICES = [
        ("manual", "Manual"),
        ("supervisor", "Supervisor"),
        ("gps", "GPS"),
        ("qr", "QR"),
        ("rfid", "RFID"),
        ("biometric", "Biometric"),
        ("fingerprint", "Fingerprint"),
    ]
    verification_method = models.CharField(max_length=30, choices=VERIFICATION_METHOD_CHOICES, blank=True, default="")
    VERIFICATION_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("verified", "Verified"),
        ("rejected", "Rejected"),
        ("exception", "Exception"),
    ]
    verification_status = models.CharField(max_length=20, choices=VERIFICATION_STATUS_CHOICES, default="pending")
    verified_by = models.ForeignKey("Employee", on_delete=models.SET_NULL, blank=True, null=True, related_name="verified_attendance_records")
    verified_at = models.DateTimeField(blank=True, null=True)
    check_in_latitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    check_in_longitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    check_out_latitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    check_out_longitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    location_accuracy = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    distance_from_site = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    attendance_source = models.CharField(max_length=40, blank=True, default="manual")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField()
    time_in = models.TimeField()
    time_out = models.TimeField(blank=True, null=True)
    remarks = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @staticmethod
    def refresh_salary_for(employee):
        if employee is None:
            return
        salary, _created = Salary.objects.get_or_create(
            employee=employee,
            defaults={"basic_salary": Decimal("0.00")},
        )
        salary.process_payroll()

    def impacted_salary_employees(self):
        employees = [self.employee, self.scheduled_guard, self.attended_guard]
        if self.pk:
            previous = Attendance.objects.filter(pk=self.pk).select_related("employee", "scheduled_guard", "attended_guard").first()
            if previous:
                employees.extend([previous.employee, previous.scheduled_guard, previous.attended_guard])
        seen = set()
        for employee in employees:
            if employee and employee.pk not in seen:
                seen.add(employee.pk)
                yield employee

    def save(self, *args, **kwargs):
        if self.present and self.attended_guard_id is None:
            self.attended_guard = self.scheduled_guard
        if self.attended_guard_id:
            self.employee = self.attended_guard
        elif self.scheduled_guard_id:
            self.employee = self.scheduled_guard
        self.full_clean()
        impacted_employees = list(self.impacted_salary_employees())
        super().save(*args, **kwargs)
        for employee in impacted_employees:
            self.refresh_salary_for(employee)

    def delete(self, *args, **kwargs):
        impacted_employees = list(self.impacted_salary_employees())
        result = super().delete(*args, **kwargs)
        for employee in impacted_employees:
            self.refresh_salary_for(employee)
        return result

    @staticmethod
    def employee_has_deployment_area(employee, site, work_date):
        if not employee or not site or not work_date or employee.role not in ('guard', 'supervisor'):
            return True
        if site.guards.filter(pk=employee.pk).exists():
            return True
        regions = site.deployment_area_regions()
        if not regions.exists():
            return False
        return DeploymentArea.objects.filter(
            employee=employee,
            region__in=regions,
            status='active',
            start_date__lte=work_date,
        ).filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=work_date)).exists()

    @property
    def is_payable_shift(self):
        return bool(
            self.present
            and self.attended_guard_id
            and self.employee_has_deployment_area(self.attended_guard, self.site, self.date)
        )

    def clean(self):
        super().clean()
        site = self.site or (self.deployment.site if self.deployment_id else None)
        shift_type = self.shift.shift_type if self.shift_id else None
        if self.present and self.attended_guard_id and not self.employee_has_deployment_area(self.attended_guard, site, self.date):
            raise ValidationError("This employee cannot work or earn this shift outside their deployment area unless transferred by Human Resource Manager.")
        if self.scheduled_guard_id and self.date:
            duplicate_schedule = Attendance.objects.filter(
                scheduled_guard=self.scheduled_guard,
                date=self.date,
                shift__shift_type=shift_type,
            )
            if self.pk:
                duplicate_schedule = duplicate_schedule.exclude(pk=self.pk)
            if duplicate_schedule.exists():
                raise ValidationError("This guard is already scheduled on this date. Choose a different guard for the other shift.")
        if self.present and self.attended_guard_id and shift_type and self.date:
            if site:
                required_guards = site.day_shift_guards if shift_type == "day" else site.night_shift_guards
                present_attendance = Attendance.objects.filter(
                    site=site,
                    present=True,
                    date=self.date,
                    shift__shift_type=shift_type,
                )
                if self.pk:
                    present_attendance = present_attendance.exclude(pk=self.pk)
                if required_guards <= 0 or present_attendance.count() >= required_guards:
                    raise ValidationError(
                        f"{site} cannot mark more than {required_guards} present guard(s) for the {shift_type} shift on {self.date}."
                    )
            duplicate_shift = Attendance.objects.filter(
                attended_guard=self.attended_guard,
                present=True,
                date=self.date,
                shift__shift_type=shift_type,
            )
            if self.pk:
                duplicate_shift = duplicate_shift.exclude(pk=self.pk)
            if duplicate_shift.exists():
                raise ValidationError("This employee already has payable attendance for this shift type on this date.")
        if self.scheduled_guard_id and not self.employee_has_deployment_area(self.scheduled_guard, site, self.date):
            raise ValidationError("Scheduled employee is outside their deployment area. Create an HR-approved transfer before scheduling this shift.")

    def __str__(self):
        return f"{self.employee} - {self.date}"
    class Meta:
        db_table = 'attendance'
        indexes = [
            models.Index(fields=["date", "site", "shift"], name="att_date_site_shift_idx"),
            models.Index(fields=["employee", "date"], name="att_employee_date_idx"),
            models.Index(fields=["scheduled_guard", "date"], name="att_scheduled_date_idx"),
            models.Index(fields=["deployment", "date"], name="att_deployment_date_idx"),
        ]


class SupervisorVisit(models.Model):
    visit_id = models.AutoField(primary_key=True)
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="supervisor_visits")
    supervisor = models.ForeignKey("Employee", on_delete=models.SET_NULL, blank=True, null=True, related_name="supervisor_visits")
    visit_started_at = models.DateTimeField(default=timezone.now)
    visit_completed_at = models.DateTimeField(blank=True, null=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    location_accuracy = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("missed", "Missed"),
        ("cancelled", "Cancelled"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="scheduled")
    remarks = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.supervisor_id and self.supervisor.role not in ("supervisor", "manager", "operations_officer"):
            raise ValidationError("Supervisor visits must be performed by supervisors or operations managers.")
        if self.visit_completed_at and self.visit_completed_at < self.visit_started_at:
            raise ValidationError("Visit completion cannot be earlier than the start time.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.site} visit - {self.visit_started_at:%Y-%m-%d %H:%M}"

    class Meta:
        db_table = "supervisor_visits"
        ordering = ["-visit_started_at"]


class GuardPresenceVerification(models.Model):
    verification_id = models.AutoField(primary_key=True)
    supervisor_visit = models.ForeignKey(SupervisorVisit, on_delete=models.CASCADE, related_name="guard_verifications")
    attendance = models.ForeignKey(Attendance, on_delete=models.SET_NULL, blank=True, null=True, related_name="presence_verifications")
    guard = models.ForeignKey("Employee", on_delete=models.CASCADE, related_name="presence_verifications")
    site = models.ForeignKey(Site, on_delete=models.CASCADE, related_name="guard_presence_verifications")
    shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, blank=True, null=True, related_name="guard_presence_verifications")
    verified_at = models.DateTimeField(default=timezone.now)
    verification_method = models.CharField(max_length=30, choices=Attendance.VERIFICATION_METHOD_CHOICES, default="supervisor")
    STATUS_CHOICES = [
        ("present", "Present"),
        ("absent", "Absent"),
        ("wrong_site", "Wrong Site"),
        ("relief", "Relief"),
        ("unverified", "Unverified"),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="present")
    latitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, blank=True, null=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        if self.supervisor_visit_id and self.site_id and self.supervisor_visit.site_id != self.site_id:
            raise ValidationError("Guard verification site must match the supervisor visit site.")
        if self.attendance_id and self.guard_id and self.attendance.attended_guard_id and self.attendance.attended_guard_id != self.guard_id:
            raise ValidationError("Attendance record belongs to a different attended guard.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        if self.attendance_id and self.status == "present":
            self.attendance.verification_method = self.verification_method
            self.attendance.verification_status = "verified"
            self.attendance.verified_by = self.supervisor_visit.supervisor
            self.attendance.verified_at = self.verified_at
            self.attendance.save(update_fields=["verification_method", "verification_status", "verified_by", "verified_at", "updated_at"])

    def __str__(self):
        return f"{self.guard} - {self.site} - {self.status}"

    class Meta:
        db_table = "guard_presence_verifications"
        ordering = ["-verified_at"]
        indexes = [
            models.Index(fields=["site", "verified_at"], name="guardver_site_time_idx"),
            models.Index(fields=["guard", "verified_at"], name="guardver_guard_time_idx"),
        ]

def site_assignment_conflicts(guards, site=None):
    guard_ids = [guard.pk for guard in guards if guard.pk and not guard.is_reliever]
    if not guard_ids:
        return []
    assigned_sites = Site.objects.filter(guards__in=guard_ids).distinct()
    if site and site.pk:
        assigned_sites = assigned_sites.exclude(pk=site.pk)
    conflicts = []
    for guard in Employee.objects.filter(pk__in=guard_ids).order_by("employee_number", "first_name", "last_name"):
        sites = [str(assigned_site) for assigned_site in assigned_sites.filter(guards=guard)]
        if sites:
            conflicts.append((guard, sites))
    return conflicts


@receiver(m2m_changed, sender=Site.guards.through)
def validate_site_guard_assignments(sender, instance, action, pk_set, **kwargs):
    if action != "pre_add" or not pk_set:
        return
    guards = Employee.objects.filter(pk__in=pk_set)
    conflicts = site_assignment_conflicts(guards, site=instance)
    if conflicts:
        guard_messages = [f"{guard} is already assigned to {', '.join(sites)}" for guard, sites in conflicts]
        raise ValidationError("Only relievers may be assigned to more than one site. " + "; ".join(guard_messages))





