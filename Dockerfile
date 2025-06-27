# StandardGPT Railway Production Dockerfile
FROM python:3.11-slim

# Sett metadata
LABEL maintainer="StandardGPT Team"
LABEL version="2.0.0"
LABEL description="AI-powered search application for Norwegian standards with AI-generated conversation titles"

# Sett miljøvariabler for Railway og produksjon
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Installer system avhengigheter
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Sett arbeidsmappe
WORKDIR /app

# Kopier requirements først for bedre Docker layer caching
COPY requirements.txt .

# SIMPLIFIED: Single step installation - no duplicates, dependencies ordered in requirements.txt
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Kopier applikasjonskode
COPY . .

# Opprett nødvendige mapper og sett rettigheter
RUN mkdir -p logs static/css static/js static/img && \
    chmod -R 755 /app

# Railway bruker automatisk PORT miljøvariabel - dokumentasjon
EXPOSE 8000

# Health check forenklet - Railway vil automatisk sjekke på riktig port
HEALTHCHECK --interval=30s --timeout=15s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:$PORT/health || exit 1

# Railway start kommando med eksplisitt shell for miljøvariabel ekspansjon
CMD /bin/sh -c "exec gunicorn --bind 0.0.0.0:${PORT:-8000} --workers ${GUNICORN_WORKERS:-2} --timeout ${GUNICORN_TIMEOUT:-120} --keep-alive 5 --max-requests 1000 --max-requests-jitter 100 --preload --access-logfile - --error-logfile - app:app"
