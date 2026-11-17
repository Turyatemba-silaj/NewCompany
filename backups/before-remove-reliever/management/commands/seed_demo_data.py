from decimal import Decimal
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import IntegrityError, models
from django.utils import timezone


class Command(BaseCommand):
    help = "Create at least five demo records for each webroaster model table."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=5, help="Minimum records per table.")

    def handle(self, *args, **options):
        self.target_count = options["count"]
        self.created = {}
        self.ensure_demo_users()

        from django.apps import apps

        webroaster_models = list(apps.get_app_config("webroaster").get_models())
        pending = set(webroaster_models)

        for _pass_number in range(12):
            progressed = False
            for model in list(pending):
                before = model.objects.count()
                self.seed_model(model)
                after = model.objects.count()
                if after > before:
                    progressed = True
                if after >= self.target_count:
                    pending.discard(model)
            if not pending or not progressed:
                break

        self.seed_many_to_many()
        self.seed_notification_top_ups()
        self.ensure_demo_files(webroaster_models)
        pending = {model for model in webroaster_models if model.objects.count() < self.target_count}

        if pending:
            self.stdout.write(self.style.WARNING("Some tables could not be fully seeded:"))
            for model in sorted(pending, key=lambda m: m.__name__):
                self.stdout.write(f"  {model.__name__}: {model.objects.count()}")

        self.stdout.write(self.style.SUCCESS("Demo data seeding complete."))
        for model in webroaster_models:
            self.stdout.write(f"{model.__name__}: {model.objects.count()}")

    def ensure_demo_users(self):
        User = get_user_model()
        for index in range(1, self.target_count + 1):
            username = f"demo_user_{index}"
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@example.com",
                    "first_name": "Demo",
                    "last_name": f"User {index}",
                    "is_staff": True,
                    "is_active": True,
                },
            )
            if created:
                user.set_password("DemoPass123!")
                user.save(update_fields=["password"])

    def seed_model(self, model):
        missing = max(self.target_count - model.objects.count(), 0)
        for offset in range(missing):
            index = model.objects.count() + 1
            values = self.values_for_model(model, index)
            if values is None:
                return
            try:
                model.objects.create(**values)
            except Exception:
                try:
                    model.objects.bulk_create([model(**values)])
                except (IntegrityError, Exception):
                    return

    def values_for_model(self, model, index):
        values = {}
        for field in model._meta.local_fields:
            if field.primary_key and isinstance(field, (models.AutoField, models.BigAutoField)):
                continue
            if isinstance(field, (models.AutoField, models.BigAutoField)):
                continue
            if isinstance(field, (models.DateTimeField, models.DateField)) and (field.auto_now or field.auto_now_add):
                values[field.name] = timezone.now() if isinstance(field, models.DateTimeField) else timezone.localdate()
                continue
            if isinstance(field, (models.ForeignKey, models.OneToOneField)):
                related = self.related_object_for(field, model)
                if related is None:
                    if field.null:
                        values[field.name] = None
                        continue
                    return None
                values[field.name] = related
                continue
            values[field.name] = self.value_for_field(field, model, index)
        return values

    def related_object_for(self, field, model):
        related_model = field.remote_field.model
        queryset = related_model.objects.all().order_by(related_model._meta.pk.name)
        if isinstance(field, models.OneToOneField):
            used_ids = set(
                model.objects.exclude(**{f"{field.name}__isnull": True}).values_list(field.attname, flat=True)
            )
            queryset = queryset.exclude(pk__in=used_ids)
        return queryset.first()

    def value_for_field(self, field, model, index):
        if field.choices:
            return list(field.choices)[(index - 1) % len(field.choices)][0]

        if field.default is not models.NOT_PROVIDED:
            return field.default() if callable(field.default) else field.default

        name = field.name.lower()
        model_name = model.__name__.lower()

        if isinstance(field, models.EmailField):
            return f"{model_name}{index}@example.com"
        if isinstance(field, models.FileField):
            if field.name == "passport_photo":
                return f"employee_photos/{model_name}_{index}.svg"
            upload_to = field.upload_to or "demo/"
            upload_to = upload_to if isinstance(upload_to, str) else "demo/"
            upload_to = upload_to.strip("/")
            return f"{upload_to}/{model_name}_{index}.pdf" if upload_to else f"{model_name}_{index}.pdf"
        if isinstance(field, models.GenericIPAddressField):
            return "127.0.0.1"
        if isinstance(field, models.CharField):
            value = self.text_value(name, model_name, index)
            max_length = field.max_length or 255
            return value[:max_length]
        if isinstance(field, models.TextField):
            return f"Demo {model.__name__} notes {index}."
        if isinstance(field, models.DecimalField):
            decimal_places = field.decimal_places or 0
            max_digits = field.max_digits or 10
            integer_digits = max(max_digits - decimal_places, 1)
            max_integer_value = (10 ** integer_digits) - 1
            value = min(index * 10, max_integer_value)
            quantizer = Decimal("1") if decimal_places == 0 else Decimal("1").scaleb(-decimal_places)
            return Decimal(value).quantize(quantizer)
        if isinstance(field, (models.PositiveIntegerField, models.PositiveSmallIntegerField, models.IntegerField)):
            return index
        if isinstance(field, models.BooleanField):
            return True
        if isinstance(field, models.DateTimeField):
            return timezone.now() + timedelta(days=index)
        if isinstance(field, models.DateField):
            return timezone.localdate() + timedelta(days=index)
        if isinstance(field, models.TimeField):
            return time((7 + index) % 24, 0)
        if isinstance(field, models.DurationField):
            return timedelta(hours=index)
        return f"Demo {model.__name__} {index}"

    def text_value(self, name, model_name, index):
        if "email" in name:
            return f"{model_name}{index}@example.com"
        if "phone" in name or "mobile" in name:
            return f"+256700000{index:03d}"
        if "url" in name:
            return f"https://example.com/{model_name}/{index}"
        if "number" in name or "code" in name or "ref" in name:
            return f"DEMO-{model_name[:6].upper()}-{index:03d}"
        if "name" in name or "title" in name:
            return f"Demo {model_name.replace('_', ' ').title()} {index}"
        if "address" in name or "location" in name:
            return f"Kampala Demo Location {index}"
        if "method" in name:
            return "bank_transfer"
        if "currency" in name:
            return "UGX"
        if "gender" in name:
            return "M"
        return f"Demo {name.replace('_', ' ')} {index}"

    def seed_many_to_many(self):
        from webroaster.models import ContractDeliverable, Invoice, Site, Employee

        guards = list(Employee.objects.filter(role__in=["guard", "supervisor"])[: self.target_count])
        Employee.objects.filter(pk__in=[guard.pk for guard in guards]).update(is_reliever=True)
        for site in Site.objects.all()[: self.target_count]:
            try:
                site.guards.add(*guards)
            except Exception:
                continue

        billable_items = list(ContractDeliverable.objects.all()[: self.target_count])
        for invoice in Invoice.objects.all()[: self.target_count]:
            invoice.billable_products.add(*billable_items)

    def seed_notification_top_ups(self):
        from webroaster.models import (
            Budget,
            BudgetNotification,
            DisciplinaryNotification,
            Disciplinary_Action,
            Employee,
            Expense,
            ExpenseNotification,
            JobApplication,
            JobApplicationNotification,
        )

        employees = list(Employee.objects.all()[: self.target_count])
        if not employees:
            return

        self.seed_related_notifications(
            DisciplinaryNotification,
            "disciplinary_action",
            list(Disciplinary_Action.objects.all()[: self.target_count]),
            employees,
            {},
        )
        self.seed_related_notifications(
            ExpenseNotification,
            "expense",
            list(Expense.objects.all()[: self.target_count]),
            employees,
            {"recipient_group": "Finance", "notification_type": "missing_accountability"},
        )
        self.seed_related_notifications(
            BudgetNotification,
            "budget",
            list(Budget.objects.all()[: self.target_count]),
            employees,
            {"recipient_group": "Finance", "notification_type": "low_balance"},
        )
        self.seed_related_notifications(
            JobApplicationNotification,
            "application",
            list(JobApplication.objects.all()[: self.target_count]),
            employees,
            {"recipient_group": "Human Resource", "notification_type": "new_application"},
        )

        for index, employee in enumerate(employees, start=1):
            if not employee.passport_photo:
                employee.passport_photo = f"employee_photos/employee_{index}.svg"
                employee.save(update_fields=["passport_photo", "updated_at"])

    def seed_related_notifications(self, model, related_field, related_objects, employees, extra_values):
        if not related_objects:
            return

        attempts = 0
        while model.objects.count() < self.target_count and attempts < self.target_count * self.target_count:
            index = attempts % len(related_objects)
            employee = employees[attempts % len(employees)]
            related_object = related_objects[index]
            values = {
                related_field: related_object,
                "recipient": employee,
                "message": f"Demo {model.__name__} message {model.objects.count() + 1}.",
                "status": "pending",
                "delivery_note": "",
                "notified_at": timezone.now() + timedelta(minutes=attempts),
                **extra_values,
            }
            try:
                lookup = {
                    related_field: related_object,
                    "recipient": employee,
                }
                if "notification_type" in extra_values:
                    lookup["notification_type"] = extra_values["notification_type"]
                model.objects.get_or_create(
                    **lookup,
                    defaults=values,
                )
            except Exception:
                try:
                    model.objects.create(**values)
                except Exception:
                    pass
            attempts += 1

    def ensure_demo_files(self, webroaster_models):
        media_root = settings.MEDIA_ROOT
        for model in webroaster_models:
            file_fields = [field for field in model._meta.local_fields if isinstance(field, models.FileField)]
            if not file_fields:
                continue
            for record in model.objects.all()[: self.target_count]:
                for field in file_fields:
                    file_value = getattr(record, field.name)
                    if not file_value:
                        continue
                    file_path = media_root / file_value.name
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    if not file_path.exists():
                        if file_path.suffix.lower() == ".svg":
                            file_path.write_text(self.demo_svg_text(record), encoding="utf-8")
                        else:
                            file_path.write_bytes(self.demo_pdf_bytes(model.__name__, field.name))

    def demo_pdf_bytes(self, model_name, field_name):
        title = f"Demo {model_name} {field_name}".encode("ascii", "ignore")[:60].decode("ascii")
        return (
            b"%PDF-1.4\n"
            b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
            b"4 0 obj << /Length 64 >> stream\n"
            + f"BT /F1 14 Tf 36 90 Td ({title}) Tj 0 -24 Td (Placeholder demo file) Tj ET\n".encode("ascii")
            + b"endstream endobj\n"
            b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
            b"xref\n0 6\n0000000000 65535 f \n"
            b"trailer << /Root 1 0 R /Size 6 >>\nstartxref\n0\n%%EOF\n"
        )

    def demo_svg_text(self, record):
        initials = "DP"
        first_name = getattr(record, "first_name", "")
        last_name = getattr(record, "last_name", "")
        if first_name or last_name:
            initials = f"{first_name[:1]}{last_name[:1]}".upper()
        return f"""<svg xmlns="http://www.w3.org/2000/svg" width="300" height="400" viewBox="0 0 300 400">
  <rect width="300" height="400" fill="#dbeafe"/>
  <circle cx="150" cy="130" r="58" fill="#93c5fd"/>
  <path d="M54 340c18-70 68-106 96-106s78 36 96 106" fill="#60a5fa"/>
  <text x="150" y="365" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="42" font-weight="700" fill="#1e40af">{initials}</text>
</svg>
"""
