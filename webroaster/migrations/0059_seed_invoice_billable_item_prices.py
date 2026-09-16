from django.db import migrations


def seed_invoice_billable_item_prices(apps, schema_editor):
    Price = apps.get_model("webroaster", "InvoiceBillableItemPrice")
    defaults = {
        "gun": "50000.00",
        "radio": "50000.00",
        "walk_through_detector": "250000.00",
        "metal_detector": "250000.00",
        "vehicle": "100000.00",
        "dog": "80000.00",
        "other": "0.00",
    }
    for item_name, unit_price in defaults.items():
        Price.objects.get_or_create(
            item_name=item_name,
            defaults={"unit_price": unit_price, "taxable": True, "active": True},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("webroaster", "0058_invoicebillableitemprice"),
    ]

    operations = [
        migrations.RunPython(seed_invoice_billable_item_prices, migrations.RunPython.noop),
    ]


