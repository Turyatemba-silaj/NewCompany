from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("webroaster", "0040_seed_uganda_regions"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="sites",
            field=models.ManyToManyField(blank=True, related_name="invoices", to="webroaster.site"),
        ),
    ]

