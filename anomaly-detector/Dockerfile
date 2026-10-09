FROM python:3.11-slim
WORKDIR /app
COPY anomaly-detector/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY anomaly-detector/app ./app
COPY common ./common
CMD ["uvicorn", "app.detector:app", "--host", "0.0.0.0", "--port", "8000"]
