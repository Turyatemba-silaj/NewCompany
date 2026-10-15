"""Check SQLite migrations and data preservation using an in-memory database."""


def main():
    import os
    import sys
    from pathlib import Path
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "NewCompany.settings")
    import django
    from django.conf import settings
    settings.DATABASES["default"]["NAME"] = ":memory:"
    django.setup()
    from django.core.management import call_command
    # Exercise the same partially applied state as the reported failure.
    call_command("migrate", "webroaster", "0001", verbosity=0, interactive=False)
    from django.db.migrations.executor import MigrationExecutor
    from django.db import connection
    initial_apps = MigrationExecutor(connection).loader.project_state([("webroaster", "0001_initial")]).apps
    Client = initial_apps.get_model("webroaster", "Client")
    client = Client.objects.create(
        client_name="SQLite migration regression",
        contact_person="Migration check", phone_number="000", email="check@example.com",
        address="Test", contract_start_date="2026-01-01", contract_end_date="2026-12-31",
    )
    client_pk = client.pk
    call_command("migrate", verbosity=0, interactive=False)
    from django.apps import apps
    assert apps.get_model("webroaster", "Client").objects.filter(pk=client_pk).exists()
    assert apps.get_model("webroaster", "Contract").objects.filter(client_id=client_pk).exists()
    with connection.cursor() as cursor:
        for model in apps.get_models():
            if not model._meta.managed or model._meta.proxy:
                continue
            columns = {column.name for column in connection.introspection.get_table_description(cursor, model._meta.db_table)}
            missing = {field.column for field in model._meta.local_fields} - columns
            assert not missing, (model._meta.label, missing)
            list(model.objects.all()[:1])
    call_command("makemigrations", check=True, dry_run=True, interactive=False)
    print("All migrations and model schema checks passed.")

    with connection.cursor() as cursor:
        assert cursor.execute("PRAGMA foreign_key_check").fetchall() == []
    from django.test import Client as TestClient
    response = TestClient().get("/staff/login/", HTTP_HOST="localhost")
    assert response.status_code == 200, response.status_code
    print("Existing client data preserved; foreign keys and login page passed.")


if __name__ == "__main__":
    main()
