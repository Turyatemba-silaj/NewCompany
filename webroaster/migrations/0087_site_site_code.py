from django.db import migrations, models
import re


def client_code(client_name):
    letters = re.sub(r"[^A-Za-z0-9]", "", client_name or "Client").upper()
    return (letters[:3] or "CLI").ljust(3, "X")


def populate_contract_and_site_codes(apps, schema_editor):
    Contract = apps.get_model("webroaster", "Contract")
    Site = apps.get_model("webroaster", "Site")

    for contract in Contract.objects.select_related("client").order_by("contract_id"):
        contract.contract_number = f"{client_code(contract.client.client_name)}-{contract.contract_id:06d}"
        contract.save(update_fields=["contract_number"])

    for contract in Contract.objects.order_by("contract_id"):
        sites = Site.objects.filter(contract=contract).order_by("site_id")
        for index, site in enumerate(sites, start=1):
            site.site_code = f"{contract.contract_number}-S{index:03d}"
            site.save(update_fields=["site_code"])


def clear_site_codes(apps, schema_editor):
    Site = apps.get_model("webroaster", "Site")
    Site.objects.update(site_code=None)


class Migration(migrations.Migration):

    dependencies = [
        ('webroaster', '0086_alter_training_provider'),
    ]

    operations = [
        migrations.AddField(
            model_name='site',
            name='site_code',
            field=models.CharField(blank=True, editable=False, max_length=40, null=True, unique=True),
        ),
        migrations.RunPython(populate_contract_and_site_codes, clear_site_codes),
    ]
