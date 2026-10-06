# Build context is the project ROOT (see docker-compose.yml), so that this
# service can also COPY the shared /common package.
FROM python:3.11-slim
WORKDIR /app
COPY sandbox-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY sandbox-api/app ./app
COPY common ./common
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
