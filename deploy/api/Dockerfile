FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential wget fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY nickel/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY nickel/ ./nickel/

ENV PYTHONPATH=/app/nickel
ENV PYTHONUNBUFFERED=1

RUN mkdir -p /app/data/uploads /app/data/outputs /app/data/inbox

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app/nickel"]
