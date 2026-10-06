FROM python:3.11-slim
WORKDIR /app
COPY chaos-engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY chaos-engine/app ./app
COPY common ./common
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
