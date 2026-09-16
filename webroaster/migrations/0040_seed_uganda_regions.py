from django.db import migrations


UGANDA_REGIONS = [
    ("Central Region", "Official Uganda region covering central districts and Kampala-adjacent operations."),
    ("Eastern Region", "Official Uganda region covering eastern operations."),
    ("Northern Region", "Official Uganda region covering northern operations."),
    ("Western Region", "Official Uganda region covering western operations."),
    ("Kampala Metropolitan", "Operational area for Kampala city and nearby urban assignments."),
    ("Central One", "Central Uganda operational deployment area."),
    ("Central Two", "Central Uganda operational deployment area."),
    ("Central Three", "Central Uganda operational deployment area."),
    ("Greater Masaka", "Operational area covering Masaka and surrounding districts."),
    ("Greater Mukono", "Operational area covering Mukono and surrounding districts."),
    ("Greater Jinja", "Operational area covering Jinja and surrounding districts."),
    ("Busoga", "Eastern Uganda subregion deployment area."),
    ("Bukedi", "Eastern Uganda subregion deployment area."),
    ("Bugisu", "Eastern Uganda subregion deployment area."),
    ("Sebei", "Eastern Uganda subregion deployment area."),
    ("Teso", "Eastern Uganda subregion deployment area."),
    ("Karamoja", "North-eastern Uganda subregion deployment area."),
    ("Acholi", "Northern Uganda subregion deployment area."),
    ("Lango", "Northern Uganda subregion deployment area."),
    ("West Nile", "Northern Uganda subregion deployment area."),
    ("Bunyoro", "Western Uganda subregion deployment area."),
    ("Toro", "Western Uganda subregion deployment area."),
    ("Ankole", "Western Uganda subregion deployment area."),
    ("Kigezi", "Western Uganda subregion deployment area."),
    ("Rwenzori", "Western Uganda subregion deployment area."),
]


def seed_uganda_regions(apps, schema_editor):
    Region = apps.get_model("webroaster", "Region")
    for region_name, description in UGANDA_REGIONS:
        region, created = Region.objects.get_or_create(
            region_name=region_name,
            defaults={"description": description},
        )
        if not created and not region.description:
            region.description = description
            region.save(update_fields=["description"])


def unseed_uganda_regions(apps, schema_editor):
    # Keep user data intact on rollback; regions may already be used by sites and deployments.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("webroaster", "0039_invoice_amendment_amount_invoice_amendment_reason_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_uganda_regions, unseed_uganda_regions),
    ]

