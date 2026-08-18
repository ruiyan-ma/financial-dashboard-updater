# Build: docker compose up -d --build

FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PORT=5001
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD exec gunicorn --bind :$PORT --workers 1 --threads 4 --timeout 600 backend.app:app
