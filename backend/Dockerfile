# Agentic GRC API image for Azure Container Apps (see docs/deployment.md).
# Build from the backend directory: docker build -t agentic-grc-api backend
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

# Uploaded evidence is written to local disk, which is ephemeral in Container Apps. Only the
# extracted text (stored in PostgreSQL) is used after upload.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser \
    && mkdir uploaded_evidence \
    && chown appuser uploaded_evidence
USER appuser

EXPOSE 8000

# Container Apps terminates TLS at its ingress; trust its X-Forwarded-* headers so redirects
# keep the https scheme.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
