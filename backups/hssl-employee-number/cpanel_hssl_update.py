"""Run from the live app root with its Python environment activated and app stopped."""

import ast
import json
import os
from datetime import datetime
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "NewCompany.settings")
import django
django.setup()

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction

Employee = apps.get_model("webroaster", "Employee")
User = get_user_model()
root = Path.cwd().resolve()
model_file = Path(Employee.save.__code__.co_filename).resolve()
if not model_file.is_relative_to(root):
    raise RuntimeError("Run from the app root containing manage.py.")
original = model_file.read_text(encoding="utf-8-sig")
tree = ast.parse(original)
employee_class = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Employee")
prefix = next(n for n in employee_class.body if isinstance(n, ast.FunctionDef) and n.name == "employee_number_prefix")
if not any(isinstance(n, ast.Name) and n.id == "property" for n in prefix.decorator_list):
    raise RuntimeError("Unexpected prefix method. No changes made.")
lines = original.splitlines(keepends=True)
lines[prefix.lineno - 1:prefix.end_lineno] = [
    '    def employee_number_prefix(self):\n        return "HSSL"\n'
]
updated = "".join(lines)
compile(updated, str(model_file), "exec")

backup = Path.home() / ".hssl_backups" / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
backup.mkdir(parents=True, mode=0o700)
(backup / "hr.py").write_text(original, encoding="utf-8")
(backup / "hr.py").chmod(0o600)
source_written = False
try:
    with transaction.atomic():
        rows = list(Employee.objects.select_for_update().order_by("pk").values("pk", "employee_number"))
        def is_hssl(value):
            return bool(value and value.startswith("HSSL") and value[4:].isascii() and value[4:].isdigit())
        highest = max((int(r["employee_number"][4:]) for r in rows if is_hssl(r["employee_number"])), default=0)
        changes = []
        for row in rows:
            old = row["employee_number"] or ""
            if is_hssl(old):
                continue
            highest += 1
            new = f"HSSL{highest:03d}"
            if len(new) > Employee._meta.get_field("employee_number").max_length:
                raise RuntimeError("Employee number exceeds field length.")
            user = User.objects.select_for_update().filter(username=old).first() if old else None
            conflict = User.objects.filter(username__iexact=new)
            if user:
                conflict = conflict.exclude(pk=user.pk)
            if conflict.exists():
                raise RuntimeError(f"Username {new} already exists; no employee numbers changed.")
            changes.append({"employee_id": row["pk"], "old": old, "new": new, "user_id": user.pk if user else None})
        mapping = backup / "number_changes.json"
        with mapping.open("x", encoding="utf-8") as output:
            mapping.chmod(0o600)
            json.dump(changes, output, indent=2)
        for change in changes:
            Employee.objects.filter(pk=change["employee_id"]).update(employee_number=change["new"])
            if change["user_id"] is not None:
                User.objects.filter(pk=change["user_id"]).update(username=change["new"])
        source_written = True
        model_file.write_text(updated, encoding="utf-8")
except Exception:
    if source_written:
        model_file.write_text(original, encoding="utf-8")
    raise

print(f"SUCCESS: {len(changes)} employees renumbered.")
print(f"Matching login usernames updated: {sum(c['user_id'] is not None for c in changes)}")
print(f"Source backup and old/new number mapping: {backup}")
print("New employee prefix: HSSL. Passwords are unchanged.")
print("Start/restart the Python App in cPanel now.")
