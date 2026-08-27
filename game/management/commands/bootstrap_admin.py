"""
Idempotently create (or refresh) a superuser from environment variables.

Run automatically by ``docker-entrypoint.sh`` on container start, so a fresh
deploy always has an admin account without needing shell access:

    DJANGO_SUPERUSER_USERNAME=admin
    DJANGO_SUPERUSER_PASSWORD=change-me
    DJANGO_SUPERUSER_EMAIL=admin@example.com   # optional

If username or password is missing, it does nothing (safe to always run).
"""
from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create/refresh a superuser from DJANGO_SUPERUSER_* environment variables."

    def handle(self, *args, **options):
        username = (os.environ.get("DJANGO_SUPERUSER_USERNAME") or "").strip()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD") or ""
        email = (os.environ.get("DJANGO_SUPERUSER_EMAIL") or "").strip()

        if not username or not password:
            self.stdout.write(
                "bootstrap_admin: DJANGO_SUPERUSER_USERNAME/PASSWORD not set — skipping."
            )
            return

        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username, defaults={"email": email}
        )
        if email:
            user.email = email
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)  # keep the env password authoritative each boot
        user.save()

        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"bootstrap_admin: {verb} superuser '{username}'."))
