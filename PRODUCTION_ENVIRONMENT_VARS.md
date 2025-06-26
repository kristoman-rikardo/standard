# Miljøvariabler for Railway Produksjon - StandardGPT

## 🔑 Påkrevde Miljøvariabler for Railway

Kopier og lim inn disse i Railway Dashboard under "Variables" fanen:

### OpenAI Configuration
```
OPENAI_API_KEY=sk-proj-your-openai-api-key-here
OPENAI_MODEL=gpt-4o
```

### Elasticsearch Configuration
```
ELASTICSEARCH_API_ENDPOINT=https://my-elasticsearch-project-f89a7b.es.eastus.azure.elastic.cloud:443/standard_prod/_search
ELASTICSEARCH_API_KEY=ApiKey UktaQ0I1Y0JuRWlsdGhiTlFRNG06ZXhSZkczenlydk5tOHk1WklYUUFNQQ==
```

### Embedding API
```
EMBEDDING_API_ENDPOINT=https://fastembed-api.onrender.com/embed
```

### Flask Production Configuration
```
FLASK_ENV=production
SECRET_KEY=change-this-to-a-secure-random-key-for-production
```

### AI-titler og Performance
```
AI_TITLES_ENABLED=true
PYTHONUNBUFFERED=1
PYTHONDONTWRITEBYTECODE=1
```

## 🛠️ Railway-spesifikke Optimiseringer

Disse variablene er allerede konfigurert i `railway.json`, men kan overstyres om ønskelig:

```
GUNICORN_WORKERS=2
GUNICORN_TIMEOUT=120
```

## ⚡ Quick Deploy Steps

1. **Gå til [Railway Dashboard](https://railway.app/dashboard)**
2. **Klikk "New Project" → "Deploy from GitHub repo"**
3. **Velg denne repository**
4. **Legg til alle miljøvariabler fra listen over**
5. **VIKTIG: Erstatt placeholder-verdier med dine faktiske API-nøkler**
6. **Deploy automatisk starter!**

## 🔒 Sikkerhetsnote

**VIKTIG:** Endre `SECRET_KEY` til en sikker, tilfeldig nøkkel for produksjon:

```bash
# Generer sikker SECRET_KEY:
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**VIKTIG:** Erstatt `OPENAI_API_KEY` med din faktiske nøkkel fra OpenAI dashboard.

## ✅ Verifisering

Etter deployment, test at alt fungerer:

```bash
# Health check
curl https://your-app.railway.app/health

# Test AI-titler
curl -X POST https://your-app.railway.app/api/query \
  -H "Content-Type: application/json" \
  -d '{"question":"Hva sier NS-EN 1090 om stålkonstruksjoner?"}'
```

## 🎯 Forventet Respons

Health check skal returnere:
```json
{
  "status": "healthy",
  "timestamp": "2025-06-26T20:34:10Z",
  "services": {
    "elasticsearch": true,
    "openai": true
  }
}
```

## 📊 Railway Costs

- **Free Tier**: $5/måned inkludert
- **AI-titler**: ~$0.0001 per tittel (neglisjerbar)
- **Elasticsearch**: Ekstern tjeneste (dine eksisterende kostnader)

---

**StandardGPT er nå 100% klar for Railway produksjon! 🚀** 