SQLite migration compatibility
==============================

`settings.MIGRATION_MODULES` selects this package for SQLite. It retains the
original migration names and dependencies, including migration 0001, so a
partially initialized database can resume without deleting data or faking
migrations. The package search path loads unchanged migrations from
`webroaster.migrations`; files here override PostgreSQL-specific migrations.

Overrides use Django introspection instead of `information_schema`, portable
casts and ORM backfills, and materialize fields previously recorded only in
migration state. PostgreSQL-only legacy repair operations are skipped because
the SQLite schema is created by the normal model operations.

Run `python -B scripts/check_sqlite_migrations.py` from the NewCompany directory
to migrate an in-memory database, preserve a sample client's contract, check
model columns and foreign keys, and verify the staff login page.
