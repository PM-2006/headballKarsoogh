#!/bin/sh
set -e

# contenttypes ships migrations even though this project defines no models.
python manage.py migrate --noinput

exec "$@"
