"""Check MySQL migrations against an EMPTY disposable test_* database.

Set DJANGO_DB_ENGINE=mysql and DB_NAME/DB_USER/DB_PASSWORD/DB_HOST/DB_PORT.
This creates tables and sample records. Never point it at a live database.
"""
from check_sqlite_migrations import main


if __name__ == "__main__":
    main(engine="mysql")
