#!/bin/sh
set -e

# Apply DB migrations (creates the game tables, auth, sessions, ...).
python manage.py migrate --noinput

# Create/refresh the admin account from DJANGO_SUPERUSER_* env vars.
# No-op when those vars are unset, so it is always safe to run.
python manage.py bootstrap_admin

exec "$@"
