# Namecheap deployment record: Hippo Security

Recorded from the deployment conversation on 16 October 2026 (Africa/Kampala).
This document records completed work, reported errors, their remedies, and
instructions that still need confirmation. Passwords and secret keys are omitted.

## 1. Intended setup

| Environment | Git branch | Database | Purpose |
|---|---|---|---|
| Local development | `new` | SQLite | Develop without a database server |
| Namecheap shared hosting | `new` | MariaDB through Django's MySQL backend | Production deployment on cPanel |
| Vercel | `main` | Existing hosted PostgreSQL | Preserve the existing Vercel configuration |

The user initially called the development database “mysqlite”; this was
implemented as SQLite. Namecheap was initially described as MySQL hosting.
The successful Django database check later identified its server as MariaDB.
MariaDB uses Django's `django.db.backends.mysql` backend and the `mysqlclient`
driver; a separate MariaDB Django engine was not required.

### Hosting details established during the session

| Item | Value / status |
|---|---|
| cPanel account | `hippbcvk` |
| Shell server | `server415` |
| Shared hosting IP supplied by user | `104.207.79.167` |
| Existing hosting primary domain | `hipposecurity.com` |
| Correct intended domain, clarified later | `hipposecurityug.com` |
| Admin address used for the subsequent setup | `admin.hipposecurityug.com` |
| Existing application folder | `/home/hippbcvk/admin.hipposecurity.com` |
| Virtual environment | `/home/hippbcvk/virtualenv/admin.hipposecurity.com/3.12` |
| Python | 3.12 |
| Database name entered during troubleshooting | `hippbcvk_hipposecurity` |
| Database username entered during troubleshooting | `hippbcvk_admin` |

The prefixed database names above were entered in the terminal. A successful
database check confirmed working access after cPanel environment changes, but
the final database name and username were not printed again after that fix.
The authoritative account values are those in cPanel Manage My Databases.

The old domain name in the application folder is a filesystem path. It can remain
there while the public application URL changes to the correct domain.

## 2. Repository inspection and branch decisions

1. Inspected `D:\business\NewCompany`, the local Git repository.
2. Found that the checked-out branch was `new`; `origin/main` contained the
   full application, while `new` tracked the Django configuration package.
3. Created a local `main` tracking `origin/main`.
4. Initially created another local branch named `namecheap` from `main`.
5. The user clarified that Namecheap must use the existing `new` branch.
   Work continued on `new`; the extra `namecheap` branch was left unused.
6. Preserved `main` and its Vercel settings.

### Changes implemented on `new`

- SQLite is the default when no database environment variables are supplied.
- `DJANGO_ENV=namecheap` selects MySQL and disables debug by default.
- `DJANGO_DB_ENGINE` supports explicit `sqlite` or `mysql` selection.
- MySQL credentials are read from `DB_NAME`, `DB_USER`, `DB_PASSWORD`,
  `DB_HOST`, and `DB_PORT`.
- `SQLITE_PATH` can override the development database location.
- Namecheap startup rejects missing database credentials, a missing production
  secret, enabled debug, or selecting SQLite in the Namecheap environment.
- Added MySQL requirements and migration overrides for legacy SQL.
- Extended the migration compatibility helper to materialize state-only fields
  for SQLite and MySQL.
- Kept existing migration names and dependencies.
- Added settings checks, a disposable MySQL migration check, and deployment notes.
- Added ignore rules for environment files and SQLite databases.

The settings read process environment variables; they do not automatically load
`.env` files.

### Validation and push

- Seven database-settings tests passed.
- SQLite migration checks passed, including sample client/contract preservation,
  model-column checks, foreign-key checks, and the staff login page.
- The MySQL migration path was tested against a temporary local MariaDB 11.4.5
  server. Full migration, sample data preservation, model checks, and the login
  page passed after the transaction fix described below.
- The temporary database server was stopped after testing.
- Committed and pushed to `origin/new`:

  ```text
  8eb2b230e0de24aa7664fc983d322377619b2493
  Configure SQLite development and Namecheap MySQL deployment
  ```

- Verified the remote `new` branch matched that commit.
- Verified `main` remained at `717f048e322bdf11a149428685ce26196bd5f396`.
- GitHub reported that the repository's preferred URL was
  `https://github.com/Turyatemba-silaj/NewCompany.git`; the push succeeded.

### Full application package

The pushed `new` branch still contained only the configuration package. The
`webroaster` application was outside this checkout, so it was not included in
that push. A clone of `new` alone was therefore insufficient for deployment.

Prepared a complete upload archive using the configuration package and the
adjacent local application:

```text
D:\business\NewCompany\backups\namecheap-deploy-8eb2b23.zip
```

The archive contained 306 files, including 219 Python files that passed syntax
checks. ZIP integrity and required paths were checked. It excluded environment
files, local databases, uploaded media, caches, and private-key file extensions.
The archive also included root-level management, requirements, and Passenger
startup files. It was an upload artifact, not an additional Git push.

## 3. Namecheap application and upload setup

The first File Manager screenshot showed the project under
`/home/hippbcvk/admin.hipposecurity.com`. This existing folder was used instead
of creating the initially suggested `newcompany_app` folder.

Python App settings used for the initial setup:

| Setting | Initial value |
|---|---|
| Python | 3.12 |
| Application root | `admin.hipposecurity.com` |
| Application URL | `admin.hipposecurity.com` |
| URL path | Blank |
| Startup file | `passenger_wsgi.py` |
| Entry point | `application` |

The activation command supplied by the user was:

```bash
source /home/hippbcvk/virtualenv/admin.hipposecurity.com/3.12/bin/activate
cd /home/hippbcvk/admin.hipposecurity.com
```

Required deployed structure:

```text
admin.hipposecurity.com/
    passenger_wsgi.py
    manage.py
    requirements.txt
    requirements-namecheap.txt
    NewCompany/
        __init__.py
        settings.py
        wsgi.py
        migration_compat.py
        mysql_migrations/
        sqlite_migrations/
        static/
    webroaster/
        apps.py
        migrations/
        templates/
```

Passenger startup content supplied in the archive:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from NewCompany.wsgi import application
```

## 4. Errors, warnings, and remedies

### A. cPanel Terminal was missing

**Symptom:** The user could not find Terminal.

**Remedy provided:** Open cPanel Manage Shell, enable SSH access, refresh cPanel,
then open Advanced → Terminal. Namecheap support was the fallback if those
options were unavailable. Python App's Run Pip Install was also explained as
an alternative for dependency installation.

**Outcome:** Later terminal prompts confirmed that shell access was available.
The exact action used to enable it was not separately reported.

### B. MySQL migration package was missing

**Command and error:**

```text
ls passenger_wsgi.py requirements-namecheap.txt NewCompany/mysql_migrations/__init__.py
ls: cannot access 'NewCompany/mysql_migrations/__init__.py': No such file or directory
```

**Finding:** A later screenshot showed `mysql_migrations`, `sqlite_migrations`,
and configuration files directly at the application root instead of inside
`NewCompany/`. The expected complete application layout was not yet present.

**Remedy provided:** Extract the complete deployment ZIP into the existing
application directory, replacing matching project files. The alternative was
to upload the updated migration folders, `settings.py`, and
`migration_compat.py` into `NewCompany/`.

**Outcome:** The user reran the check and all three required paths were listed.
Subsequent Django commands loaded the application successfully.

### C. MySQL transaction error during local migration validation

**Error:**

```text
TransactionManagementError: Executing DDL statements while in a transaction
on databases that can't perform a rollback is prohibited.
```

**Finding:** Legacy `RunPython` operations used the schema editor inside a
transaction that was incompatible with the MySQL backend.

**Fix implemented:** Set `atomic=False` on the relevant schema-editor migration
operations and the MySQL receivables override. SQLite retained its outer
migration transaction.

**Outcome:** Reran the complete disposable MariaDB migration test successfully.
This occurred locally before the branch was pushed, not on the live server.

### D. Dependency installation

**Command:**

```bash
python -m pip install -r requirements-namecheap.txt
```

**Outcome:** Installation succeeded. `mysqlclient` built a Linux Python 3.12
wheel on the hosting server. Reported installed packages included Django 6.0.7,
Django REST Framework 3.18.1, mysqlclient 2.3.0, and reportlab 4.4.5.

The pip upgrade notice was informational; upgrading pip was not necessary to
continue this deployment.

### E. Secret-key input was mishandled

**Symptom:** The shell prompt returned before a secret was entered, and the
secret text was then pasted as part of a shell command. It also appeared in chat.

**Remedy provided:** Generate a replacement key, export it in the shell, and
save the same value in Python App's `SECRET_KEY` variable:

```bash
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')"
```

The user was instructed to copy the generated value privately into cPanel and
not share it in chat. The exposed value is not reproduced here.

**Outcome:** A replacement was instructed. Rotation was not explicitly
confirmed and remains a verification item.

### F. MySQL access denied: error 1045

**Error:**

```text
OperationalError: (1045, "Access denied for user 'admin'@'localhost' (using password: YES)")
```

**Troubleshooting performed:**

1. Checked whether database names and usernames needed cPanel prefixes.
2. Instructed the user to assign the database user ALL PRIVILEGES on the database.
3. Entered prefixed names in the terminal.
4. Corrected password prompt usage. One pasted command omitted the space between
   the prompt text and `DB_PASSWORD`, so it did not update the intended variable.
5. Instructed the user to run each prompt separately and wait before typing its
   value. Hidden password input was explained as normal.

Correct password prompt supplied:

```bash
read -r -s -p "Database password: " DB_PASSWORD; export DB_PASSWORD; printf '\n'
```

**Further finding:** Despite exporting a prefixed username, a diagnostic inside
Python still printed:

```text
Settings module: NewCompany.settings
Environment username: admin
Django username: admin
Database: hipposecurity
Engine: django.db.backends.mysql
```

This established that the Python process was receiving old values. The exact
startup mechanism overriding the shell values was not traced independently.

**Effective remedy:** Update `DB_USER`, `DB_NAME`, and `DB_PASSWORD` in cPanel
Setup Python App, save and restart, then reopen Terminal and reactivate the
virtual environment.

**Outcome:** The next `python manage.py check --database default` reached the
database and returned only the MariaDB warning below. Authentication was resolved.

### G. MariaDB conditional unique-constraint warning

**Warning:**

```text
webroaster.SupplierProformaInvoice: (models.W036)
MariaDB does not support unique constraints with conditions.
HINT: A constraint won't be created.
```

**Explanation:** The hosting database is MariaDB. Django's MySQL backend is
correct for it, but MariaDB cannot create this conditional uniqueness constraint.

**Action:** Continued setup because this was a warning, not a connection error.
No code change was made to enforce an equivalent rule.

**Outcome:** Open production issue. Successful migration does not mean that
this uniqueness rule is enforced by the database. Do not describe it as fixed
or merely silence it without assessing the required business rule.

### H. HTTPS failed and HTTP returned a parking page

**Address tested at that point:** `admin.hipposecurity.com/staff/login/`.

**Observed:** HTTPS failed with a TLS `unrecognized_name` error. HTTP returned
a script navigating to `/lander`, rather than the Django login page.

**DNS findings at the time:**

```text
admin.hipposecurity.com A 76.223.54.146
admin.hipposecurity.com A 13.248.169.48
hipposecurity.com NS ns3.afternic.com
hipposecurity.com NS ns4.afternic.com
```

Those records did not point to the hosting IP supplied by the user.

**Troubleshooting:** Inspected cPanel Domains screenshots, confirmed the old
domain existed in hosting, and distinguished hosting management from domain
registration and authoritative DNS. GoDaddy instructions were initially
provided because the user identified GoDaddy as the registrar. Namecheap
instructions were subsequently discussed when the user asked about that provider.

**Root clarification:** The intended domain was actually `hipposecurityug.com`.
The parking-page tests had been made against the wrong domain. No change to
the old Afternic domain was confirmed or needed for the corrected target.

**Outcome:** Proceeded to configure the correct domain. Successful HTTPS for the
corrected target has not yet been demonstrated.

### I. Personal DNS Server was the wrong settings area

**Symptom:** The user opened the Personal DNS Server nameserver-registration
dropdown in Namecheap.

**Remedy:** Leave that section unchanged. It does not add the application's
ordinary `admin` A record. The screenshot indicated Namecheap Web Hosting DNS,
so subsequent guidance moved to cPanel Zone Editor.

**DNS evidence caveat:** An earlier lookup of `hipposecurityug.com` returned
`dns1.registrar-servers.com` and `dns2.registrar-servers.com`, while the later
account screenshot indicated Web Hosting DNS. The final authoritative delegation
was not rechecked. An edit in cPanel is effective publicly only when the domain's
active DNS delegation uses that hosting zone.

### J. Correct domain missing from cPanel / Zone Editor

**Symptom:** `hipposecurity.com` existed, but `hipposecurityug.com` was not listed.

**Remedy carried out:** cPanel Domains → Create A New Domain, enter
`hipposecurityug.com`, uncheck Share document root, and retain the proposed folder.

**Confirmed result from screenshot:**

```text
Domain created: hipposecurityug.com
Document root: /home/hippbcvk/hipposecurityug.com
```

cPanel also stated that hosting nameservers should be
`dns1.namecheaphosting.com` and `dns2.namecheaphosting.com`, and that SSL
installation for the root domain was in progress. These notices did not confirm
completed DNS propagation or an installed certificate for the admin subdomain.

**Next remedy carried out:** Create `admin.hipposecurityug.com`, uncheck Share
document root, and set its document root to the existing application folder
`admin.hipposecurity.com`. The user reported success.

**Outcome:** Correct domain and admin subdomain were reported added to hosting;
the application files did not need to be moved or reinstalled.

## 5. Database initialization and application commands

The following command sequence was used or provided after virtual-environment
activation and environment configuration:

```bash
python manage.py check --database default
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
```

| Step | Evidence / status |
|---|---|
| Install dependencies | Successful output supplied by user |
| Authenticate and check database | Successful check; one MariaDB warning |
| Apply migrations | User confirmed “done with migrate”; full output not supplied |
| Create superuser | Instructed; completion not explicitly confirmed |
| Collect static files | Instructed; completion not explicitly confirmed |
| Restart Python App | Instructed during troubleshooting; latest domain-switch restart unconfirmed |
| Load corrected public login page | Not yet verified |

No transfer of local SQLite records or existing Vercel/PostgreSQL data to the
Namecheap database was performed or confirmed. Migrations create/update schema;
they do not automatically copy data from another database.

## 6. Final target configuration

The latest instructions were to edit the existing Python App rather than create
another environment or rerun migrations.

| Setting | Target value |
|---|---|
| Application root | `admin.hipposecurity.com` — retain existing filesystem path |
| Application URL | `admin.hipposecurityug.com` |
| URL path | Blank |
| Startup file | `passenger_wsgi.py` |
| Entry point | `application` |

Target environment variables:

```text
DJANGO_ENV=namecheap
DJANGO_DB_ENGINE=mysql
DJANGO_DEBUG=False
SECRET_KEY=<private replacement production secret>
DB_NAME=<full database name from Manage My Databases>
DB_USER=<full database username from Manage My Databases>
DB_PASSWORD=<private database-user password>
DB_HOST=localhost
DB_PORT=3306
DJANGO_ALLOWED_HOSTS=admin.hipposecurityug.com
CSRF_TRUSTED_ORIGINS=https://admin.hipposecurityug.com
```

Required public DNS record at the active authoritative DNS provider:

| Type | Name | Address |
|---|---|---|
| A | `admin.hipposecurityug.com` (`admin` in the domain's host-record editor) | `104.207.79.167` |

Final public login URL:

```text
https://admin.hipposecurityug.com/staff/login/
```

Changing the public domain requires the host/origin configuration and SSL to
match; it does not require recreating the MariaDB database.

## 7. Remaining verification and work

1. Confirm the existing Python App URL was changed to
   `admin.hipposecurityug.com`, its host/origin variables saved, and the app restarted.
2. Verify the current authoritative nameservers for `hipposecurityug.com` and
   that the public `admin` A record resolves to `104.207.79.167`. Resolve any
   delegation mismatch before relying on cPanel Zone Editor changes.
3. Confirm SSL is installed and valid specifically for
   `admin.hipposecurityug.com`; the root-domain certificate notice alone is insufficient.
4. Verify the corrected HTTPS login URL serves Django, then verify login using
   the administrator account without sharing its credentials.
5. Confirm superuser creation, static collection, and actual CSS/JavaScript/image
   delivery. Static file serving was discussed, but its final hosting mapping
   and appearance were not demonstrated.
6. Confirm the exposed secret was replaced and that the active app uses the replacement.
7. Implement and test the supplier-proforma uniqueness rule in a MariaDB-compatible
   way. The warning remains unresolved.
8. Before a future deployment directly from Git, include the full application in
   the deployment source. `new` at the recorded commit contains the configuration
   package only; this session used a separate complete upload archive.
9. Configure and verify any required persistent/private media handling and backups.
   Neither an end-to-end media check nor a production backup setup was confirmed.

## 8. Reference guides consulted

- [Namecheap: deploy Django on shared hosting](https://www.namecheap.com/support/knowledgebase/article.aspx/10753/2182/how-to-deploy-a-django-application-on-shared-servers/)
- [Namecheap: Python App](https://www.namecheap.com/support/knowledgebase/article.aspx/10048/2182/how-to-work-with-python-app/)
- [Namecheap: enable SSH / Terminal](https://www.namecheap.com/support/knowledgebase/article.aspx/10040/2210/how-to-enable-ssh-shell-in-cpanel/)
- [Namecheap: manage databases](https://www.namecheap.com/support/knowledgebase/article.aspx/9363/2180/how-to-create-and-maintain-databases-in-cpanel/)
- [Namecheap: manage domains in cPanel](https://www.namecheap.com/support/knowledgebase/article.aspx/10125/29/how-to-manage-domains-in-cpanel/)
- [Namecheap: DNS host records](https://www.namecheap.com/support/knowledgebase/article.aspx/434/2237/how-do-i-set-up-host-records-for-a-domain/)
- [Namecheap: SSL plugin](https://www.namecheap.com/support/knowledgebase/article.aspx/9387/2218/what-is-namecheap-ssl-and-how-do-i-use-it/)
- [Django 6.0: database backends](https://docs.djangoproject.com/en/6.0/ref/databases/)

These links support the setup procedures. The completion statuses in this
document come from the actual conversation, command outputs, and screenshots.
