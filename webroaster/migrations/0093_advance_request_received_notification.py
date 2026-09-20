from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("webroaster", "0092_advance_verification_workflow"),
    ]

    operations = [
        migrations.AlterField(
            model_name="advancenotification",
            name="notification_type",
            field=models.CharField(
                choices=[
                    ("verification_requested", "Verification Requested"),
                    ("request_received", "Request Received"),
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
