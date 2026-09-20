from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [
        ("webroaster", "0090_alter_attendance_remarks"),
    ]

    operations = [
        migrations.AlterField(
            model_name="advance",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("disbursed", "Disbursed"),
                    ("recovered", "Recovered"),
                    ("rejected", "Rejected"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="AdvanceNotification",
            fields=[
                ("notification_id", models.AutoField(primary_key=True, serialize=False)),
                ("recipient_group", models.CharField(max_length=50)),
                (
                    "notification_type",
                    models.CharField(
                        choices=[
                            ("approval_requested", "Approval Requested"),
                            ("advance_approved", "Advance Approved"),
                            ("advance_rejected", "Advance Rejected"),
                            ("finance_update", "Finance Update"),
                        ],
                        max_length=40,
                    ),
                ),
                ("message", models.TextField()),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "Pending"), ("read", "Read"), ("actioned", "Actioned")],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("decision", models.CharField(blank=True, default="", max_length=20)),
                ("decided_at", models.DateTimeField(blank=True, null=True)),
                ("notified_at", models.DateTimeField(default=timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "advance",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="webroaster.advance"),
                ),
                (
                    "recipient",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="advance_notifications", to="webroaster.employee"),
                ),
            ],
            options={
                "db_table": "advance_notifications",
                "ordering": ["-notified_at", "-notification_id"],
            },
        ),
        migrations.AddConstraint(
            model_name="advancenotification",
            constraint=models.UniqueConstraint(
                fields=("advance", "recipient", "recipient_group", "notification_type"),
                name="unique_advance_notification",
            ),
        ),
    ]
