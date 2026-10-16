"""Portable helpers for migrations that also support legacy PostgreSQL schemas."""
from django.db import migrations


def column_names(schema_editor, table_name):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        if table_name not in connection.introspection.table_names(cursor):
            return set()
        return {column.name for column in connection.introspection.get_table_description(cursor, table_name)}


class SQLiteSeparateDatabaseAndState(migrations.SeparateDatabaseAndState):
    """Materialize state-only legacy columns for SQLite and MySQL databases.

    Keep the original class name because existing migrations import it.
    """

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor not in {"sqlite", "mysql"}:
            return super().database_forwards(app_label, schema_editor, from_state, to_state)
        state = from_state.clone()
        for operation in self.state_operations:
            old_state = state.clone()
            operation.state_forwards(app_label, state)
            if isinstance(operation, migrations.AddField):
                model = state.apps.get_model(app_label, operation.model_name)
                field = model._meta.get_field(operation.name)
                if field.column in column_names(schema_editor, model._meta.db_table):
                    continue
            operation.database_forwards(app_label, schema_editor, old_state, state)

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if schema_editor.connection.vendor not in {"sqlite", "mysql"}:
            return super().database_backwards(app_label, schema_editor, from_state, to_state)
        operation = migrations.SeparateDatabaseAndState(database_operations=self.state_operations)
        return operation.database_backwards(app_label, schema_editor, from_state, to_state)
