"""SQLite overrides for webroaster's legacy PostgreSQL migrations.

Keep migration names and dependencies so an existing SQLite database can resume
migration normally. Unchanged migrations are loaded from the app's migration
package; overrides in this directory take precedence.
"""
from webroaster import migrations as original_migrations

__path__.extend(original_migrations.__path__)
