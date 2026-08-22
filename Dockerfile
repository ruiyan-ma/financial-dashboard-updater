FROM python:3.11-slim

WORKDIR /app
COPY requirements-tracker.txt .
RUN pip install --no-cache-dir -r requirements-tracker.txt
COPY . .

CMD exec gunicorn --bind :$PORT --workers 1 --threads 4 --timeout 60 tracker.app:app
