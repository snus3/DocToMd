FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends pandoc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "markitdown[pdf]"

WORKDIR /workspace

COPY service /app/service

ENTRYPOINT ["python", "/app/service/convert_service.py"]
