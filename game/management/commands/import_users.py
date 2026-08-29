"""
Bulk-import users from a CSV file with ``username`` and ``password`` columns.

    python manage.py import_users users.csv

Existing users are skipped unless ``--update-existing`` is passed, in which case
their password is reset to the value in the CSV. Use ``--dry-run`` to preview.
"""
from __future__ import annotations

import csv

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Import users from a CSV file containing 'username' and 'password' columns."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", help="Path to the CSV file.")
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Reset the password of users that already exist instead of skipping them.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and report what would happen without writing to the database.",
        )

    def handle(self, *args, **options):
        path = options["csv_path"]
        update_existing = options["update_existing"]
        dry_run = options["dry_run"]

        try:
            handle = open(path, newline="", encoding="utf-8-sig")
        except OSError as exc:
            raise CommandError(f"Cannot open CSV file '{path}': {exc}")

        with handle:
            reader = csv.DictReader(handle)
            fields = {(name or "").strip().lower() for name in (reader.fieldnames or [])}
            missing = {"username", "password"} - fields
            if missing:
                raise CommandError(
                    f"CSV is missing required column(s): {', '.join(sorted(missing))}. "
                    f"Found: {', '.join(reader.fieldnames or []) or '(none)'}"
                )
            rows = list(reader)

        User = get_user_model()
        created = updated = skipped = 0

        with transaction.atomic():
            for line_no, row in enumerate(rows, start=2):  # header is line 1
                normalized = {
                    (key or "").strip().lower(): (value or "").strip()
                    for key, value in row.items()
                }
                username = normalized.get("username", "")
                password = normalized.get("password", "")

                if not username or not password:
                    self.stderr.write(
                        self.style.WARNING(f"line {line_no}: empty username or password — skipped.")
                    )
                    skipped += 1
                    continue

                user = User.objects.filter(username=username).first()
                if user is None:
                    if not dry_run:
                        user = User(username=username)
                        user.set_password(password)
                        user.save()
                    created += 1
                    self.stdout.write(f"line {line_no}: created '{username}'.")
                elif update_existing:
                    if not dry_run:
                        user.set_password(password)
                        user.save(update_fields=["password"])
                    updated += 1
                    self.stdout.write(f"line {line_no}: updated password for '{username}'.")
                else:
                    skipped += 1
                    self.stdout.write(
                        f"line {line_no}: '{username}' already exists — skipped "
                        f"(use --update-existing to reset the password)."
                    )

            if dry_run:
                transaction.set_rollback(True)

        summary = f"created {created}, updated {updated}, skipped {skipped}"
        if dry_run:
            self.stdout.write(self.style.WARNING(f"Dry run — no changes saved ({summary})."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Import finished: {summary}."))
