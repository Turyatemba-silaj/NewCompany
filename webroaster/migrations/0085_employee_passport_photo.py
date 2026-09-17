from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("webroaster", "0084_repair_demo_seed_column_types"),
    ]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="passport_photo",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="employee_photos/",
                verbose_name="Passport Photo",
            ),
        ),
    ]
