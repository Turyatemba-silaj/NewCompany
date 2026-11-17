"""Preview or apply legacy employee/account numbering changes from the app root."""

import argparse
import os
import re


def build_plan(records):
    highest = max(
        (int(row["employee_number"][4:]) for row in records
         if re.fullmatch(r"HSSL[0-9]+", row["employee_number"] or "")),
        default=0,
    )
    changes = []
    for row in records:
        old = row["employee_number"] or ""
        if re.fullmatch(r"HSSL[0-9]+", old):
            continue
        highest += 1
        changes.append((row["pk"], old, f"HSSL{highest:03d}"))
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "NewCompany.settings")
    import django
    django.setup()
    from django.apps import apps
    from django.contrib.auth import get_user_model
    from django.db import transaction

    Employee = apps.get_model("webroaster", "Employee")
    User = get_user_model()
    with transaction.atomic():
        rows = list(Employee.objects.select_for_update().order_by("pk").values("pk", "employee_number"))
        plan = build_plan(rows)
        accounts = {}
        for pk, old, new in plan:
            user = User.objects.select_for_update().filter(username=old).first() if old else None
            conflict = User.objects.filter(username__iexact=new)
            if user:
                conflict = conflict.exclude(pk=user.pk)
                accounts[pk] = user.pk
            if conflict.exists():
                raise RuntimeError(f"Username {new} already exists. No changes have been applied.")
        print(f"Employee numbers to change: {len(plan)}")
        print(f"Matching login usernames to change: {len(accounts)}")
        for pk, old, new in plan[:20]:
            print(f"Employee ID {pk}: {old or '(empty)'} -> {new}")
        if not args.apply:
            print("Preview only. Stop the Python App, then run this command with --apply.")
            return
        for pk, old, new in plan:
            Employee.objects.filter(pk=pk).update(employee_number=new)
            if pk in accounts:
                User.objects.filter(pk=accounts[pk]).update(username=new)
        print("Applied successfully. Restart the Python App. Updated users log in with HSSL numbers.")


if __name__ == "__main__":
    main()
