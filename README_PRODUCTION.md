# StandardGPT - Production Deployment Guide

StandardGPT er en moderne, skalerbar webapplikasjon for AI-drevet søk i norske og internasjonale standarder.

## 🚀 Quick Start

### Lokal Utvikling
```bash
# 1. Installer avhengigheter
pip install -r requirements.txt

# 2. Sett miljøvariabler
export OPENAI_API_KEY="your-api-key"
export ELASTICSEARCH_URL="http://localhost:9200"
export SECRET_KEY="your-secret-key"

# 3. Start utviklingsserver
python app.py
```

### Produksjon med Docker
```bash
# 1. Konfigurer miljøvariabler i .env fil
echo "OPENAI_API_KEY=your-key" > .env
echo "SECRET_KEY=your-secret" >> .env

# 2. Start med Docker Compose
docker-compose up -d
```

## 📋 Systemkrav

### Minimum
- Python 3.9+
- 2GB RAM
- 10GB disk
- Ubuntu 20.04+ / CentOS 8+ / Docker

### Anbefalt Produksjon
- Python 3.11+
- 8GB+ RAM
- 50GB+ SSD
- 4+ CPU cores
- Load balancer (nginx/apache)
- SSL/TLS sertifikat

## 🔧 Produksjonsdistribusjon

### Metode 1: Systemd Service (Anbefalt)

1. **Installer systemavhengigheter:**
```bash
sudo apt update
sudo apt install python3-pip python3-venv nginx

# Opprett bruker for appen
sudo useradd -m -s /bin/bash standardgpt
sudo su - standardgpt
```

2. **Konfigurer applikasjon:**
```bash
# Klon prosjektet
git clone <repository-url> /home/standardgpt/app
cd /home/standardgpt/app

# Opprett virtuelt miljø
python3 -m venv venv
source venv/bin/activate

# Installer avhengigheter
pip install -r requirements.txt
```

3. **Sett miljøvariabler:**
```bash
# Opprett .env fil
cat > .env << EOF
FLASK_ENV=production
OPENAI_API_KEY=your-openai-api-key
ELASTICSEARCH_URL=http://localhost:9200
SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
ELASTICSEARCH_INDEX=standards
LOG_LEVEL=INFO
EOF

# Sikre rettigheter
chmod 600 .env
```

4. **Opprett systemd service:**
```bash
# Generer service konfigurasjon
python deploy.py systemd --port 5000 --workers 4

# Kopier til systemd (krever sudo)
sudo cp standardgpt.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable standardgpt
sudo systemctl start standardgpt
```

5. **Konfigurer nginx:**
```bash
# Generer nginx konfigurasjon
python deploy.py nginx --domain yourdomain.com

# Installer nginx konfigurasjon
sudo cp nginx_config /etc/nginx/sites-available/standardgpt
sudo ln -s /etc/nginx/sites-available/standardgpt /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Metode 2: Docker Deployment

1. **Opprett Docker filer:**
```bash
python deploy.py docker
```

2. **Konfigurer miljøvariabler:**
```bash
# Opprett .env fil for Docker
cat > .env << EOF
OPENAI_API_KEY=your-api-key
SECRET_KEY=your-secret-key
ELASTICSEARCH_URL=http://elasticsearch:9200
EOF
```

3. **Start med Docker Compose:**
```bash
docker-compose up -d
```

4. **Verifiser deployment:**
```bash
# Sjekk tjenestestatus
docker-compose ps

# Sjekk logger
docker-compose logs -f web

# Test health endpoint
curl http://localhost/health
```

## 🔒 Sikkerhetskonfigurasjon

### SSL/TLS (Påkrevd for produksjon)

1. **Installer SSL sertifikat (Let's Encrypt):**
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

2. **Automatisk fornyelse:**
```bash
sudo crontab -e
# Legg til:
0 12 * * * /usr/bin/certbot renew --quiet
```

### Brannmur
```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp
sudo ufw enable
```

### Sikkerhetshoder
Applikasjonen inkluderer automatisk sikkerhetshoder:
- X-Frame-Options: DENY
- X-Content-Type-Options: nosniff
- X-XSS-Protection: 1; mode=block
- Strict-Transport-Security
- Content-Security-Policy

## 📊 Overvåkning og Logging

### Health Checks
```bash
# Basis health check
curl http://localhost:5000/health

# Detaljert systemstatus
curl http://localhost:5000/health | jq
```

### Logging
Applikasjonen logger til:
- `logs/standardgpt.log` (rotering aktivert)
- systemd journal (`journalctl -u standardgpt`)
- stdout/stderr for Docker

### Prometheus Metrics (Valgfritt)
```bash
# Installer prometheus-flask-exporter
pip install prometheus-flask-exporter

# Metrics tilgjengelig på /metrics
curl http://localhost:5000/metrics
```

## ⚡ Ytelsesoptimalisering

### Database (Elasticsearch)
```bash
# Optimaliser for produksjon
curl -X PUT "localhost:9200/_settings" -H 'Content-Type: application/json' -d'
{
  "index": {
    "refresh_interval": "30s",
    "number_of_replicas": 1
  }
}'
```

### Redis Cache (Anbefalt)
```bash
# Installer Redis
sudo apt install redis-server

# Konfigurer i .env
echo "RATELIMIT_STORAGE_URL=redis://localhost:6379" >> .env
```

### Load Balancing
For høy belastning, konfigurer flere app-instanser:

```nginx
upstream standardgpt {
    server 127.0.0.1:5000;
    server 127.0.0.1:5001;
    server 127.0.0.1:5002;
    server 127.0.0.1:5003;
}

server {
    location / {
        proxy_pass http://standardgpt;
    }
}
```

## 🔄 Backup og Vedlikehold

### Database Backup
```bash
# Elasticsearch snapshot
curl -X PUT "localhost:9200/_snapshot/backup_repo" -H 'Content-Type: application/json' -d'
{
  "type": "fs",
  "settings": {
    "location": "/backups/elasticsearch"
  }
}'
```

### Oppdatering
```bash
# Stopp tjenesten
sudo systemctl stop standardgpt

# Oppdater koden
cd /home/standardgpt/app
git pull origin main

# Installer nye avhengigheter
source venv/bin/activate
pip install -r requirements.txt

# Start tjenesten
sudo systemctl start standardgpt
```

## 🛠 Feilsøking

### Vanlige Problemer

1. **503 Service Unavailable**
```bash
# Sjekk app status
sudo systemctl status standardgpt
journalctl -u standardgpt -f

# Sjekk nginx konfigurasjon
sudo nginx -t
```

2. **ElasticSearch tilkobling feiler**
```bash
# Test tilkobling
curl http://localhost:9200/_cluster/health

# Sjekk ElasticSearch status
sudo systemctl status elasticsearch
```

3. **OpenAI API feil**
```bash
# Test API key
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
  https://api.openai.com/v1/models
```

### Debug Mode
```bash
# Aktiver debug logging
export LOG_LEVEL=DEBUG
sudo systemctl restart standardgpt
```

## 📈 Skalering

### Horisontal Skalering
- Bruk load balancer med flere app-instanser
- Implementer Redis for session deling
- Bruk ekstern database cluster

### Vertikal Skalering
- Øk antall Gunicorn workers
- Optimaliser database konfigurasjon
- Juster system resource limits

## 🔐 Sikkerhetstiltak

1. **Brukertilgang:** Begrens SSH tilgang, bruk SSH-nøkler
2. **Applikasjonslog:** Overvåk for mistenkelige aktiviteter
3. **Rate Limiting:** Konfigurert på API level
4. **Input Validering:** Automatisk HTML sanitisering
5. **Dependency Updates:** Regelmessig oppdatering av biblioteker

## 📞 Support

For produksjonsstøtte:
- Sjekk applikasjonslogs: `journalctl -u standardgpt -f`
- Overvåk resource usage: `top`, `htop`, `iostat`
- Test API endpoints: Bruk health check og test queries

## 🧪 Testing i Produksjon

```bash
# Kjør system tester
python -m pytest tests/ -v

# Test API endpoints
curl -X POST http://localhost/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "test spørsmål om standarder"}'

# Load testing (valgfritt)
pip install locust
locust -f tests/load_test.py --host http://localhost
``` 