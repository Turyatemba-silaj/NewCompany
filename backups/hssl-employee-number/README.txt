HSSL employee numbers
=====================

This package was generated from the supplied hr.py. It has not been uploaded to
or executed on the live server.

hr.py: All roles now use HSSL, so the existing number generator uses one shared
sequence: HSSL001, HSSL002, HSSL003, etc. Seniority and salary calculations retain
their original classification codes. NIN and email remain optional as requested
earlier. Unique supplied NINs are preserved.

renumber_hssl.py: Converts existing legacy employee numbers in employee ID order,
continuing above any existing HSSL number. It also updates login accounts whose
username exactly matches the old employee number. Account IDs, passwords and
permissions are preserved. Conflicting target usernames cause the transaction
to stop before any changes. Running it again keeps existing HSSL numbers.

Deployment
----------
1. Download and back up the existing live webroaster/models/hr.py. Make a cPanel
   database backup before renumbering existing employee/account identifiers.
2. Stop the existing Python App in cPanel while applying this update.
3. Upload hr.py to:
   /home/hippbcvk/admin.hipposecurity.com/webroaster/models/hr.py
4. Upload renumber_hssl.py alongside manage.py:
   /home/hippbcvk/admin.hipposecurity.com/renumber_hssl.py
5. In the same terminal environment where your Django commands already work:

   source /home/hippbcvk/virtualenv/admin.hipposecurity.com/3.12/bin/activate
   cd /home/hippbcvk/admin.hipposecurity.com
   python manage.py check
   python manage.py makemigrations webroaster
   python manage.py migrate
   python renumber_hssl.py

   Review the preview, then apply:

   python renumber_hssl.py --apply

6. Start/restart the existing Python App and reload the employee list.
7. Affected employees use their new HSSL numbers as login usernames with their
   existing passwords. Numbering changes alone need no schema migration; the
   migration commands also apply optional NIN/email fields if still needed.

Numbers are unique and incremental in ordinary sequential saves. The existing
max-plus-one generator is retained; simultaneous employee creation can still
cause a uniqueness error and need a retry. Deleted numbers are not guaranteed
to remain reserved. A persistent database counter would be needed to enforce
non-reuse and concurrent allocation.

Do not replace a more recently edited live file blindly: merge its recent
changes with this supplied-file correction before uploading if needed.
