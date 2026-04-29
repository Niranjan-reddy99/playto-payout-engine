#!/bin/sh
set -eu

python manage.py migrate --no-input
python manage.py seed_data

# Free-plan Railway workaround:
# run the web server and Celery in the same container when separate worker
# services are not available. `-B` embeds beat in the worker so scheduled retry
# tasks still run.
celery -A playto worker -B -l info -c 2 &
CELERY_PID=$!

gunicorn playto.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 &
GUNICORN_PID=$!

cleanup() {
  kill "$CELERY_PID" "$GUNICORN_PID" 2>/dev/null || true
}

trap cleanup INT TERM

while kill -0 "$CELERY_PID" 2>/dev/null && kill -0 "$GUNICORN_PID" 2>/dev/null; do
  sleep 5
done

cleanup
wait || true
