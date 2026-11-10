FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY elt/ elt/
COPY config/ config/
COPY sql/ sql/

# Pipeline writes NDJSON + lock under ROOT/staging
RUN mkdir -p staging

ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
