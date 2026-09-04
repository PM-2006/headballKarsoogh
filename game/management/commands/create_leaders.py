"""
Create the leader (staff) accounts used to run sessions on the real server.

    python manage.py create_leaders

Makes 20 boys' leaders ``BLeader_1`` .. ``BLeader_20`` and 20 girls' leaders
``GLeader_1`` .. ``GLeader_20``. Each account is ``is_staff`` (which is the flag
this project uses to mean "not a student": manual rule editor, raw JSON view and
the message composer) and NEVER ``is_superuser``. Each password is the username
itself, as requested -- treat the roster as a shared secret.

The command is idempotent and safe to re-run: accounts that already exist are
left alone unless ``--update-existing`` is passed. Superuser accounts are never
touched, so a name collision with a real admin cannot demote it or reset its
password.

Common invocations:

    python manage.py create_leaders --dry-run          # preview, writes nothing
    python manage.py create_leaders --csv leaders.csv  # also dump the roster
    python manage.py create_leaders --update-existing  # re-assert flags/passwords
    python manage.py create_leaders --boys 30 --girls 30
"""
from __future__ import annotations

import csv

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Create the BLeader_/GLeader_ staff accounts (password = username)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--boys", type=int, default=20,
            help="How many boys' leaders to create (default: 20).",
        )
        parser.add_argument(
            "--girls", type=int, default=20,
            help="How many girls' leaders to create (default: 20).",
        )
        parser.add_argument(
            "--boy-prefix", default="BLeader_",
            help="Username prefix for boys' leaders (default: BLeader_).",
        )
        parser.add_argument(
            "--girl-prefix", default="GLeader_",
            help="Username prefix for girls' leaders (default: GLeader_).",
        )
        parser.add_argument(
            "--start", type=int, default=1,
            help="First index to use for both groups (default: 1).",
        )
        parser.add_argument(
            "--update-existing", action="store_true",
            help=(
                "For accounts that already exist: reset the password to the "
                "username and re-assert is_staff. Without this they are skipped."
            ),
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report what would happen without writing to the database.",
        )
        parser.add_argument(
            "--csv", dest="csv_path", default=None,
            help=(
                "Also write the full username/password roster to this path. "
                "Written even on --dry-run, so you can review it first."
            ),
        )

    def handle(self, *args, **options):
        boys = options["boys"]
        girls = options["girls"]
        start = options["start"]
        update_existing = options["update_existing"]
        dry_run = options["dry_run"]
        csv_path = options["csv_path"]

        if boys < 0 or girls < 0:
            raise CommandError("--boys and --girls cannot be negative.")
        if boys + girls == 0:
            raise CommandError("Nothing to do: --boys and --girls are both 0.")
        if start < 0:
            raise CommandError("--start cannot be negative.")

        usernames = [
            f"{options['boy_prefix']}{index}"
            for index in range(start, start + boys)
        ] + [
            f"{options['girl_prefix']}{index}"
            for index in range(start, start + girls)
        ]

        duplicates = {name for name in usernames if usernames.count(name) > 1}
        if duplicates:
            raise CommandError(
                "The chosen prefixes/range produce duplicate usernames: "
                + ", ".join(sorted(duplicates))
            )

        User = get_user_model()
        created = updated = skipped = protected = 0

        with transaction.atomic():
            existing = {
                user.username: user
                for user in User.objects.filter(username__in=usernames)
            }

            for username in usernames:
                user = existing.get(username)

                if user is None:
                    if not dry_run:
                        user = User(username=username, is_staff=True, is_superuser=False)
                        user.set_password(username)
                        user.save()
                    created += 1
                    self.stdout.write(f"created  {username}")
                    continue

                # A superuser sharing one of these names is a real admin, not a
                # leader slot. Resetting its password to its username would hand
                # the whole server away, so never write to it.
                if user.is_superuser:
                    protected += 1
                    self.stderr.write(self.style.WARNING(
                        f"skipped  {username} — already exists as a SUPERUSER, left untouched."
                    ))
                    continue

                if not update_existing:
                    skipped += 1
                    self.stdout.write(
                        f"skipped  {username} — already exists "
                        f"(use --update-existing to reset its password)."
                    )
                    continue

                if not dry_run:
                    user.is_staff = True
                    user.is_active = True
                    user.set_password(username)
                    user.save(update_fields=["is_staff", "is_active", "password"])
                updated += 1
                self.stdout.write(f"updated  {username}")

            if dry_run:
                transaction.set_rollback(True)

        if csv_path:
            try:
                with open(csv_path, "w", newline="", encoding="utf-8") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(["username", "password"])
                    for username in usernames:
                        writer.writerow([username, username])
            except OSError as exc:
                raise CommandError(f"Cannot write roster to '{csv_path}': {exc}")
            self.stdout.write(self.style.WARNING(
                f"Roster written to {csv_path} — it holds plaintext passwords, "
                f"so move it off the server once you have handed them out."
            ))

        summary = (
            f"{len(usernames)} requested: created {created}, updated {updated}, "
            f"skipped {skipped}, protected {protected}"
        )
        if dry_run:
            self.stdout.write(self.style.WARNING(f"Dry run — nothing saved ({summary})."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Done: {summary}."))
