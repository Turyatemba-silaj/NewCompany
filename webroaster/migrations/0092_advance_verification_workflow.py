from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [
        ("webroaster", "0091_advancenotification_and_rejected_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="advance",
            name="verification_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending Verification"),
                    ("verified", "Verified"),
                    ("rejected", "Rejected"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="advance",
            name="verified_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="advance",
            name="verified_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="advances_verified",
                to="webroaster.employee",
            ),
        ),
        migrations.AlterField(
            model_name="advancenotification",
            name="notification_type",
            field=models.CharField(
                choices=[
                    ("verification_requested", "Verification Requested"),
                    ("approval_requested", "Approval Requested"),
                    ("advance_verified", "Advance Verified"),
                    ("advance_approved", "Advance Approved"),
                    ("advance_rejected", "Advance Rejected"),
                    ("finance_update", "Finance Update"),
                    ("payment_requested", "Payment Requested"),
                    ("advance_paid", "Advance Paid"),
                ],
                max_length=40,
            ),
        ),
    ]
