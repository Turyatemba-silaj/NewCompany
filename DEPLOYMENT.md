# Databases and deployment branches

`main` retains the Vercel configuration and its hosted PostgreSQL database.
`new` uses SQLite for local development and MySQL/MariaDB for Namecheap.
Changing settings on `new` does not change the `main` branch or move existing data.

## Local development on `new`

With no database environment variables set, Django uses the existing
`db.sqlite3` in the parent of the `NewCompany` package. SQLite needs no server
or additional driver. An optional `SQLITE_PATH` overrides the file location.

From this package directory:

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

The `webroaster` application must be present alongside `NewCompany`, as it is
in the local workspace. Currently `new` tracks the configuration package only;
deploying this branch alone is insufficient without the full application.

## Namecheap environment

Use Python 3.12 and a server with MySQL 8.0.11+ or MariaDB 10.6+.
In cPanel, create a database and a user assigned to that database with all
privileges. Use the full cPanel-prefixed database and user names.

Set these variables in **Setup Python App**:

```text
DJANGO_ENV=namecheap
DJANGO_DB_ENGINE=mysql
DJANGO_DEBUG=False
SECRET_KEY=<unique-random-production-key>
DB_NAME=<cpaneluser_database>
DB_USER=<cpaneluser_dbuser>
DB_PASSWORD=<database-password>
DB_HOST=localhost
DB_PORT=3306
DJANGO_ALLOWED_HOSTS=example.com,www.example.com
CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com
```

`DJANGO_ENV=namecheap` defaults to MySQL and disables debug. Missing credentials,
a missing secret, debug mode, or selecting SQLite in this environment stop
startup rather than silently using a development database. Local development
can also select MySQL explicitly with `DJANGO_DB_ENGINE=mysql` and the `DB_*`
variables.

The settings read process environment variables. They do **not** automatically
load `.env` files. Set the same variables in your SSH/cPanel terminal session
before running management commands; do not put credentials in Git.

After activating the Python app's virtual environment, from this package folder:

```bash
python -m pip install -r requirements-namecheap.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
python manage.py check --deploy
```

`mysqlclient` requires MySQL/MariaDB client development libraries on the hosting
server. If its installation fails, resolve the missing libraries with Namecheap
support before migrating.

The application root must contain both `NewCompany/` and `webroaster/`.
The Passenger startup file at that root can contain:

```python
from NewCompany.wsgi import application
```

Configure HTTPS and static/media file serving separately in cPanel, then restart
the Python application. Keep private uploaded documents behind authorized views.
Creating tables does not copy existing SQLite or Vercel data into MySQL.

## Migration compatibility

SQLite keeps its existing migration override package. MySQL uses
`NewCompany.mysql_migrations`, which reuses portable overrides and replaces
backend-specific data updates. Original migration names and dependencies remain
the same. Existing PostgreSQL repair operations are skipped for these databases.
This supports Django-created schemas, rather than arbitrary legacy MySQL imports.

Run the local checks from this package directory:

```powershell
python -B scripts/check_database_settings.py
python -B scripts/check_sqlite_migrations.py
```

For MySQL, set `DJANGO_DB_ENGINE=mysql` and the `DB_*` variables to an empty
disposable database named `test_...`, then run
`python -B scripts/check_mysql_migrations.py`. It creates tables and sample data
and refuses a nonempty database. Use development mode for the local login check.

Keep Vercel's production branch set to `main`. Namecheap should use `new`.
Do not merge Namecheap-specific settings into `main` during routine application
updates; apply shared application changes while retaining each branch's settings.
