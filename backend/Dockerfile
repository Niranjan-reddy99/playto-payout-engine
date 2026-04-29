FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Run the API plus Celery in one container for platforms/free tiers where
# separate worker services are not available.
CMD ["sh", "/app/start.sh"]
