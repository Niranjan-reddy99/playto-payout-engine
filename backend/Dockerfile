FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Run migrations and seed data on every startup, then launch the API server.
# migrate is safe to run repeatedly — Django skips already-applied migrations.
# seed_data is safe to run repeatedly — it uses get_or_create so nothing duplicates.
CMD ["sh", "-c", "python manage.py migrate --no-input && python manage.py seed_data && gunicorn playto.wsgi:application --bind 0.0.0.0:8000 --workers 2"]
