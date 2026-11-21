from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("webroaster", "0104_site_status_site_status_reason"),
    ]

    operations = [
        migrations.AddField(
            model_name="contract",
            name="notice_days",
            field=models.PositiveIntegerField(default=30),
        ),
        migrations.AddField(
            model_name="contract",
            name="renewal_status",
            field=models.CharField(
                choices=[("not_started", "Not started"), ("in_discussion", "In discussion"), ("renewed", "Renewed"), ("declined", "Declined")],
                default="not_started",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="contract",
            name="responsible_officer",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="responsible_contracts", to="webroaster.employee"),
        ),
        migrations.AddField(
            model_name="contract",
            name="next_action",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="contract",
            name="next_action_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="expense",
            name="contract",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="expenses", to="webroaster.contract"),
        ),
        migrations.AddField(
            model_name="expense",
            name="site",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="expenses", to="webroaster.site"),
        ),
        migrations.CreateModel(
            name="ContractVariation",
            fields=[
                ("variation_id", models.AutoField(primary_key=True, serialize=False)),
                ("effective_date", models.DateField()),
                ("changes_to", models.CharField(max_length=255)),
                ("previous_value", models.CharField(blank=True, default="", max_length=255)),
                ("revised_value", models.CharField(blank=True, default="", max_length=255)),
                ("approval_status", models.CharField(choices=[("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected")], default="pending", max_length=20)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="approved_contract_variations", to="webroaster.employee")),
                ("contract", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="variations", to="webroaster.contract")),
            ],
            options={"db_table": "contract_variations", "ordering": ["-effective_date", "-variation_id"]},
        ),
    ]
