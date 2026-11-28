import django.db.models.deletion
from django.db import migrations, models


def create_workflow_groups(apps, schema_editor):
    group = apps.get_model("auth", "Group")
    for name in ("General Manager", "CEO", "Cashier"):
        group.objects.using(schema_editor.connection.alias).get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [
        ("webroaster", "0106_alter_advance_options_accesschangelog"),
    ]
    operations = [
        migrations.AddField(
            model_name="employee", name="advance_supervisor",
            field=models.ForeignKey(
                "webroaster.employee", blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL, related_name="advance_reports",
            ),
        ),
        migrations.AddField(
            model_name="employee", name="is_department_head",
            field=models.BooleanField(default=False, verbose_name="Department head"),
        ),
        migrations.AddField(
            model_name="advance", name="routing_path",
            field=models.CharField(max_length=12, blank=True, default="", editable=False),
        ),
        migrations.AddField(
            model_name="advance", name="payment_authorized_by",
            field=models.ForeignKey(
                "webroaster.employee", blank=True, null=True, editable=False,
                on_delete=django.db.models.deletion.SET_NULL, related_name="authorized_advance_payments",
            ),
        ),
        migrations.AddField(
            model_name="advance", name="payment_authorized_at",
            field=models.DateTimeField(blank=True, null=True, editable=False),
        ),
        migrations.AddField(
            model_name="advance", name="decision_at",
            field=models.DateTimeField(blank=True, null=True, editable=False),
        ),
        migrations.AddField(
            model_name="advance", name="paid_by",
            field=models.ForeignKey(
                "webroaster.employee", blank=True, null=True, editable=False,
                on_delete=django.db.models.deletion.SET_NULL, related_name="recorded_advance_payments",
            ),
        ),
        migrations.AddField(
            model_name="advance", name="paid_at",
            field=models.DateTimeField(blank=True, null=True, editable=False),
        ),
        migrations.RunPython(create_workflow_groups, migrations.RunPython.noop),
    ]
