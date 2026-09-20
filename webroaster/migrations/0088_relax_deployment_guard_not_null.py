from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("webroaster", "0087_site_site_code"),
    ]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE deployments ALTER COLUMN guard_id DROP NOT NULL;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
