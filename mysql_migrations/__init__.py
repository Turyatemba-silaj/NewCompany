"""MySQL overrides, followed by portable SQLite overrides and original migrations."""
from NewCompany import sqlite_migrations

__path__.extend(sqlite_migrations.__path__)
