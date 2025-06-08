# StandardGPT Production Dockerfile
FROM python:3.11-slim

# Sett metadata
LABEL maintainer="StandardGPT Team"
LABEL version="1.0.0"
LABEL description="AI-powered search application for Norwegian and international standards"

# Sett miljøvariabler
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    GUNICORN_WORKERS=4 \
    GUNICORN_TIMEOUT=120

# Opprett app bruker for sikkerhet
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Installer system avhengigheter
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Sett arbeidsmappe
WORKDIR /app

# Kopier requirements først for bedre Docker layer caching
COPY requirements.txt .

# Installer Python avhengigheter
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

# Kopier applikasjonskode
COPY . .

# Opprett nødvendige mapper
RUN mkdir -p logs static/css static/js static/img && \
    chown -R appuser:appuser /app

# Bytt til app bruker
USER appuser

# Eksponer port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Start kommando
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "--keep-alive", "5", "--max-requests", "1000", "--max-requests-jitter", "100", "--preload", "app:app"] 