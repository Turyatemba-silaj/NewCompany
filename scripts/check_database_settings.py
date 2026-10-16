"""Check database selection and production configuration without connecting to a DB."""
import os
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured

SETTINGS_PATH = Path(__file__).resolve().parents[1] / "settings.py"


def load_settings(**environment):
    with patch.dict(os.environ, environment, clear=True):
        return runpy.run_path(str(SETTINGS_PATH))


class DatabaseSettingsTests(unittest.TestCase):
    def test_development_defaults_to_existing_sqlite_database(self):
        settings = load_settings()
        self.assertEqual(settings["DATABASES"]["default"]["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(settings["DATABASES"]["default"]["NAME"], SETTINGS_PATH.parent.parent / "db.sqlite3")
        self.assertEqual(settings["MIGRATION_MODULES"]["webroaster"], "NewCompany.sqlite_migrations")

    def test_sqlite_path_can_be_overridden(self):
        settings = load_settings(SQLITE_PATH=":memory:")
        self.assertEqual(settings["DATABASES"]["default"]["NAME"], ":memory:")

    def test_namecheap_uses_mysql_and_secure_defaults(self):
        settings = load_settings(
            DJANGO_ENV="namecheap", SECRET_KEY="test-only-secret",
            DB_NAME="test_database", DB_USER="test_user", DB_PASSWORD="test_password",
        )
        database = settings["DATABASES"]["default"]
        self.assertEqual(database["ENGINE"], "django.db.backends.mysql")
        self.assertEqual(database["NAME"], "test_database")
        self.assertEqual(database["HOST"], "localhost")
        self.assertEqual(database["PORT"], "3306")
        self.assertEqual(settings["MIGRATION_MODULES"]["webroaster"], "NewCompany.mysql_migrations")
        self.assertFalse(settings["DEBUG"])
        self.assertTrue(settings["SESSION_COOKIE_SECURE"])

    def test_mysql_can_be_selected_locally(self):
        settings = load_settings(
            DJANGO_DB_ENGINE="mysql", DB_NAME="test_database", DB_USER="test_user",
            DB_PASSWORD="test_password", DB_HOST="127.0.0.1", DB_PORT="3307",
        )
        self.assertEqual(settings["DATABASES"]["default"]["PORT"], "3307")

    def test_incomplete_mysql_configuration_does_not_fall_back_to_sqlite(self):
        with self.assertRaisesRegex(ImproperlyConfigured, "DB_NAME, DB_USER, DB_PASSWORD"):
            load_settings(DJANGO_DB_ENGINE="mysql")

    def test_namecheap_rejects_missing_secret_debug_and_sqlite(self):
        for overrides in (
            {},
            {"SECRET_KEY": "test-only-secret", "DJANGO_DEBUG": "true"},
            {"SECRET_KEY": "test-only-secret", "DJANGO_DB_ENGINE": "sqlite"},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ImproperlyConfigured):
                load_settings(DJANGO_ENV="namecheap", **overrides)

    def test_unknown_engine_is_rejected(self):
        with self.assertRaisesRegex(ImproperlyConfigured, "sqlite or mysql"):
            load_settings(DJANGO_DB_ENGINE="typo")


if __name__ == "__main__":
    unittest.main()
