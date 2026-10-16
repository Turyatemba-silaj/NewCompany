"""Preserve deployment relationships using portable ORM operations."""
from importlib import import_module

from django.db import migrations
from django.db.models import OuterRef, Subquery

original = import_module("NewCompany.sqlite_migrations.0023_deployment_client_site_guards")


def copy_deployment_data(apps, schema_editor):
    alias = schema_editor.connection.alias
    Deployment = apps.get_model("webroaster", "Deployment")
    Site = apps.get_model("webroaster", "Site")
    Deployment.objects.using(alias).filter(client_id__isnull=True, site_id__isnull=False).update(
        client_id=Subquery(Site.objects.using(alias).filter(pk=OuterRef("site_id")).values("client_id")[:1])
    )
    if {"site_id", "employee_id"}.issubset(original.table_columns(schema_editor, "webroaster_site_guards")):
        through = Site._meta.get_field("guards").remote_field.through
        for site_id, guard_id in Deployment.objects.using(alias).filter(
            site_id__isnull=False, guard_id__isnull=False
        ).values_list("site_id", "guard_id").distinct():
            through.objects.using(alias).get_or_create(site_id=site_id, employee_id=guard_id)


class Migration(original.Migration):
    operations = [
        migrations.RunPython(copy_deployment_data, original.noop_reverse)
        if isinstance(operation, migrations.RunPython) and operation.code is original.copy_deployment_data
        else operation
        for operation in original.Migration.operations
    ]
