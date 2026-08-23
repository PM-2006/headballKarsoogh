FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Static files are collected at build time so the image can run with DEBUG=0.
RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/data \
    && chmod +x /app/docker-entrypoint.sh \
    && chown -R app:app /app
USER app

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Batch tests (100 simulated matches) are CPU-bound, hence the raised timeout.
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "120", \
     "--access-logfile", "-"]
