# StandardGPT Lokal Embedding Setup (OpenAI)

## Oversikt
Du har nå byttet fra ekstern embedding-API til lokal embedding-tjeneste som bruker OpenAI API for bedre ytelse og kontroll.

## Systembeskrivelse
- **Lokal embedding-tjeneste**: `src/custom_embeddings.py` (FastAPI)
- **Modell**: text-embedding-3-small (OpenAI)
- **Dimensjoner**: 1536
- **Port**: 8001
- **Hovedapp**: Port 5000

## Forutsetninger
Du må ha en gyldig OpenAI API-nøkkel. Sett den som miljøvariabel:

```bash
export OPENAI_API_KEY="din-api-nøkkel-her"
```

## Trinn-for-trinn oppstart

### 1. Installer avhengigheter
```bash
python3 -m pip install fastapi uvicorn openai
```

### 2. Sett miljøvariabler
```bash
export OPENAI_API_KEY="din-api-nøkkel-her"
```

### 3. Start embedding-tjenesten
```bash
python run_embeddings.py
```
Dette vil:
- Starte embedding-tjenesten på `http://127.0.0.1:8001`
- Bruke OpenAI text-embedding-3-small modell
- Cache embeddings for å redusere API-kall

### 4. Start hovedapplikasjonen (i et nytt terminal)
```bash
python app.py
```

## Verifisering

### Test embedding-tjenesten direkte:
```bash
curl -X POST "http://127.0.0.1:8001/embed" \
     -H "Content-Type: application/json" \
     -d '{"text": "test embedding"}'
```

### Sjekk helsetatus:
```bash
curl http://127.0.0.1:8001/health
```

## Fordeler med OpenAI embeddings
✅ **Høy kvalitet** - State-of-the-art embedding-modell  
✅ **Pålitelig** - Ingen installasjonsproblemer eller avhengigheter  
✅ **Rask** - Optimalisert infrastruktur fra OpenAI  
✅ **Cached** - Automatisk caching for å redusere kostnader  
✅ **Skalerbar** - Håndterer store mengder tekst effektivt  

## Kostnader
- **text-embedding-3-small**: ~$0.00002 per 1K tokens
- **Typisk kostnad per søk**: $0.0001 - $0.001
- **Cache reduserer kostnader** betydelig for gjentatte søk

## Feilsøking

### Problem: "OPENAI_API_KEY not set"
- Sett miljøvariabelen: `export OPENAI_API_KEY="din-nøkkel"`
- Eller legg den i `.env` filen i prosjektmappen

### Problem: "Connection refused" 
- Sjekk at embedding-tjenesten kjører på port 8001
- Verifiser med `curl http://127.0.0.1:8001/health`

### Problem: "OpenAI API error"
- Sjekk at API-nøkkelen er gyldig
- Verifiser at du har credits på OpenAI kontoen

## Konfigurasjon

### Bytt modell (valgfritt):
Rediger `src/custom_embeddings.py` og endre:
```python
EMBEDDING_MODEL = "text-embedding-3-large"  # Større, mer nøyaktig
```

### Tillgjengelige OpenAI modeller:
- `text-embedding-3-small` (1536 dim, rask) ✅ **Anbefalt**
- `text-embedding-3-large` (3072 dim, mest nøyaktig)
- `text-embedding-ada-002` (1536 dim, eldre modell)

## Cache-innstillinger
Cachen reduserer API-kall og kostnader:
- **Cache TTL**: 1 time (3600 sekunder)
- **Automatisk cleanup**: Fjerner utløpte entries
- **Memory-basert**: Rask tilgang til cached embeddings

## Produksjon
For produksjonsmiljø:
- Bruk Redis for persistent caching
- Sett opp backup OpenAI nøkler
- Overvåk API-usage og kostnader
- Vurder rate limiting for høy trafikk 