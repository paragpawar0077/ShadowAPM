# Build context is the project ROOT (see docker-compose.yml).
FROM python:3.11-slim
WORKDIR /app
COPY sample-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY sample-api/app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
