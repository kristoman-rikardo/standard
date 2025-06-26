# StandardGPT Railway Deployment Guide

## 🚄 Railway Production Deployment

Denne guiden viser hvordan du deployer StandardGPT til Railway med full AI-tittelgenerering support.

## 📋 Forutsetninger

### 1. Required Accounts
- [Railway](https://railway.app) konto
- OpenAI API konto med aktiv nøkkel
- Elasticsearch cluster (anbefalt: Elastic Cloud)

### 2. Miljøvariabler
Du trenger følgende miljøvariabler konfigurert i Railway:

#### 🔑 Påkrevd (Core)
```bash
# OpenAI for hovedfunksjonalitet OG AI-titler
OPENAI_API_KEY=sk-proj-...

# Elasticsearch for søk
ELASTICSEARCH_API_ENDPOINT=https://your-cluster.es.region.gcp.cloud.es.io:443/standard_prod/_search
ELASTICSEARCH_API_KEY=ApiKey base64-encoded-key

# Embedding API for vektor-søk
EMBEDDING_API_ENDPOINT=https://fastembed-api.onrender.com/embed

# Flask konfigurasjon
SECRET_KEY=your-secret-key-here
FLASK_ENV=production
```

#### ⚙️ Valgfri (Optimalisering)
```bash
# AI-titler konfigurasjon
AI_TITLES_ENABLED=true
OPENAI_MODEL=gpt-4o

# Gunicorn konfigurasjon
GUNICORN_WORKERS=2
GUNICORN_TIMEOUT=120

# Performance tuning
PYTHONUNBUFFERED=1
PYTHONDONTWRITEBYTECODE=1
```

## 🚀 Deployment Steps

### 1. Repository Setup
```bash
# Clone repository
git clone <your-repo-url>
cd standard

# Verify files are present
ls -la railway.json Dockerfile requirements.txt
```

### 2. Railway Project Creation
1. Gå til [Railway Dashboard](https://railway.app/dashboard)
2. Klikk "New Project"
3. Velg "Deploy from GitHub repo"
4. Velg din StandardGPT repository

### 3. Environment Variables Configuration
I Railway dashboard:
1. Gå til din project
2. Klikk "Variables" tab
3. Legg til alle miljøvariabler fra listen over

### 4. Custom Domain (Valgfri)
1. Gå til "Settings" tab
2. Under "Domains" seksjon
3. Legg til custom domain eller bruk Railway's genererte URL

## 🔧 Railway Configuration

### railway.json
Prosjektet inkluderer ferdig `railway.json` konfigurasjon:

```json
{
  "build": {
    "builder": "DOCKERFILE",
    "buildCommand": "pip install --no-cache-dir -r requirements.txt"
  },
  "deploy": {
    "startCommand": "gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 --preload app:app",
    "healthcheckPath": "/health",
    "restartPolicyType": "ON_FAILURE"
  }
}
```

### Dockerfile
Railway-optimalisert Dockerfile:
- Python 3.11 base image
- Automatisk PORT miljøvariabel support
- Gunicorn med optimal konfigurasjon
- Health checks aktivert

## 🤖 AI-Titler Konfigurasjon

### Automatisk Aktivering
AI-tittelgenerering aktiveres automatisk når:
1. `OPENAI_API_KEY` er satt
2. `AI_TITLES_ENABLED=true` (default)
3. Internet-tilkobling til OpenAI API

### Fallback System
Hvis AI-titler feiler:
1. Intelligent standarddeteksjon
2. Tema-basert kategorisering
3. Keyword-analyse
4. Original regelbaserte titler

### Performance
- **Første tittel**: ~1-2 sekunder
- **Cached titler**: ~0.001 sekunder (100% raskere)
- **Kostnader**: ~$0.0001 per tittel (neglisjerbar)

## 📊 Monitoring & Logging

### Health Checks
Railway sjekker automatisk `/health` endpoint:
```bash
curl https://your-app.railway.app/health
```

### Logs
Se deployment logs i Railway dashboard:
```bash
✅ AI-genererte samtale-titler aktivert i produksjon
🚄 Kjører på Railway - Port: 3000
🤖 AI-titler: Aktivert
🌐 Server kjører på http://0.0.0.0:3000
```

### Performance Monitoring
Tilgjengelige endpoints:
- `/health` - Health check
- `/api/cache/stats` - Cache statistikk
- `/api/session/stats` - Session statistikk

## 🔒 Security & Best Practices

### Environment Variables
- ✅ Alle hemmeligheter som miljøvariabler
- ✅ Ikke hard-coded API nøkler
- ✅ Produksjon vs development konfigurasjon

### Rate Limiting
Aktivert for alle API endepunkter:
- `/api/query`: 10 requests/minute
- `/api/query/stream`: 5 requests/minute

### Security Headers
Automatisk aktivert:
- CORS headers
- Security headers via Flask-Talisman
- Request validation

## 🐛 Troubleshooting

### Common Issues

#### 1. Build Failures
```bash
# Error: Requirements installation failed
# Fix: Sjekk requirements.txt og Python version
```

#### 2. AI-Titler Fungerer Ikke
```bash
# Logs: "⚠️ AI-titler ikke aktivert"
# Fix: Verifiser OPENAI_API_KEY er satt korrekt
```

#### 3. Database Errors
```bash
# Error: Could not connect to Elasticsearch
# Fix: Sjekk ELASTICSEARCH_API_ENDPOINT og API_KEY
```

#### 4. Port Issues
```bash
# Error: Address already in use
# Fix: Railway håndterer PORT automatisk, ikke hardcode
```

### Deployment Verification
```bash
# Test health endpoint
curl https://your-app.railway.app/health

# Test AI-titler (hvis konfigurert)
curl -X POST https://your-app.railway.app/api/query \
  -H "Content-Type: application/json" \
  -d '{"question":"Hva sier NS-EN 1090 om stålkonstruksjoner?"}'
```

## 🔄 Updates & Maintenance

### Auto-Deployment
Railway deployer automatisk når du pusher til main branch:
```bash
git add .
git commit -m "Update: AI-tittelgenerering forbedringer"
git push origin main
```

### Manual Deployment
I Railway dashboard:
1. Gå til "Deployments" tab
2. Klikk "Deploy Now"

### Database Backups
```bash
# Conversations database backupes automatisk
# Ingen manuell handling påkrevd
```

## 📈 Scaling Considerations

### Resource Limits
Railway free tier:
- 512MB RAM
- 1 vCPU
- $5/måned inkludert

### Performance Optimization
For høy trafikk:
- Øk `GUNICORN_WORKERS` (anbefalt: 2-4)
- Aktiver caching (`AI_TITLES_ENABLED=true`)
- Vurder dedicated Elasticsearch cluster

### Cost Management
- AI-titler: ~$0.0001 per tittel
- Railway: $5-$20/mned avhengig av bruk
- Elasticsearch: Varierer med data/søk volum

## ✅ Success Checklist

- [ ] Repository cloned og Railway project opprettet
- [ ] Alle miljøvariabler konfigurert
- [ ] Health check returnerer 200 OK
- [ ] AI-titler fungerer (hvis aktivert)
- [ ] Elasticsearch tilkobling OK
- [ ] Custom domain konfigurert (valgfri)
- [ ] Monitoring satt opp

## 🎯 Go-Live

Når alt er testet og verifisert:

1. **Test fullstendig funksjonalitet** på staging URL
2. **Konfigurer custom domain** hvis ønsket
3. **Aktiver logging og monitoring**
4. **Dokumenter deployment** for teamet
5. **🚀 Go live!**

## 📞 Support

- **Railway Docs**: https://docs.railway.app
- **StandardGPT Issues**: [Create GitHub Issue]
- **AI-Titler Docs**: Se `TITLE_SYSTEM_README.md`

---

**StandardGPT er nå klar for produksjon på Railway! 🎉** 