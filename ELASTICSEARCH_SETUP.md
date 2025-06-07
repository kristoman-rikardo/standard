# 🔍 Elasticsearch Setup for StandardGPT Testing

## **ALTERNATIV 1: Docker (Anbefalt for testing)**

### Steg 1: Start Elasticsearch med Docker
```bash
# Start Elasticsearch 8.x (nyeste versjon)
docker run -d \
  --name elasticsearch-test \
  -p 9200:9200 \
  -e "discovery.type=single-node" \
  -e "xpack.security.enabled=false" \
  -e "ES_JAVA_OPTS=-Xms512m -Xmx512m" \
  docker.elastic.co/elasticsearch/elasticsearch:8.11.0

# Eller bruk versjon 7.x (enklere oppsett)
docker run -d \
  --name elasticsearch-test \
  -p 9200:9200 \
  -e "discovery.type=single-node" \
  -e "ES_JAVA_OPTS=-Xms512m -Xmx512m" \
  docker.elastic.co/elasticsearch/elasticsearch:7.17.15
```

### Steg 2: Verifiser at Elasticsearch kjører
```bash
# Test tilkobling
curl http://localhost:9200

# Forventet respons:
{
  "name" : "...",
  "cluster_name" : "elasticsearch",
  "version" : {...},
  "tagline" : "You Know, for Search"
}
```

### Steg 3: Opprett test-index med sample data
```bash
# Opprett index
curl -X PUT "localhost:9200/standard_documents" \
  -H "Content-Type: application/json" \
  -d '{
    "mappings": {
      "properties": {
        "content": {"type": "text"},
        "title": {"type": "text"},
        "standard_number": {"type": "keyword"},
        "section": {"type": "keyword"},
        "document_type": {"type": "keyword"},
        "content_vector": {
          "type": "dense_vector",
          "dims": 384
        }
      }
    }
  }'

# Legg til test-dokumenter
curl -X POST "localhost:9200/standard_documents/_doc/1" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "NS-EN ISO 14155 er en standard for kliniske utprøvinger av medisinsk utstyr for mennesker. Standarden gir retningslinjer for planlegging, gjennomføring og rapportering av kliniske utprøvinger.",
    "title": "Kliniske utprøvinger - God klinisk praksis",
    "standard_number": "NS-EN ISO 14155",
    "section": "Innledning",
    "document_type": "standard"
  }'

curl -X POST "localhost:9200/standard_documents/_doc/2" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Temperaturmåling skal utføres i henhold til standard prosedyrer. Måleinstrumentene skal kalibreres regelmessig.",
    "title": "Temperaturmåling og kalibrering",
    "standard_number": "ISO 9001",
    "section": "Kapittel 7",
    "document_type": "standard"
  }'

curl -X POST "localhost:9200/standard_documents/_doc/3" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Personalhandboken inneholder retningslinjer for ansatte. Du finner den på intranett under HR-dokumenter.",
    "title": "HR Retningslinjer",
    "section": "Personalhandbok",
    "document_type": "personal_handbook"
  }'
```

### Steg 4: Oppdater .env fil
```bash
# Legg til i .env filen:
ELASTICSEARCH_URL=http://localhost:9200
ELASTICSEARCH_INDEX=standard_documents
# ELASTICSEARCH_USER=          # Ikke nødvendig for lokal testing
# ELASTICSEARCH_PASSWORD=      # Ikke nødvendig for lokal testing
```

## **ALTERNATIV 2: Elasticsearch Cloud**

### Steg 1: Opprett Elastic Cloud instans
1. Gå til [cloud.elastic.co](https://cloud.elastic.co)
2. Opprett en gratis 14-dagers trial
3. Velg "Create deployment"
4. Velg "General purpose" template
5. Noter ned:
   - Cloud ID
   - Elasticsearch endpoint URL
   - Brukernavn (elastic)
   - Passord

### Steg 2: Oppdater .env fil for Cloud
```bash
ELASTICSEARCH_URL=https://your-deployment.es.region.aws.elastic-cloud.com:9243
ELASTICSEARCH_INDEX=standard_documents
ELASTICSEARCH_USER=elastic
ELASTICSEARCH_PASSWORD=your-generated-password
```

## **ALTERNATIV 3: Lokal installasjon**

### macOS med Homebrew:
```bash
brew install elasticsearch
brew services start elasticsearch
```

### Ubuntu/Debian:
```bash
wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | sudo apt-key add -
echo "deb https://artifacts.elastic.co/packages/8.x/apt stable main" | sudo tee /etc/apt/sources.list.d/elastic-8.x.list
sudo apt-get update && sudo apt-get install elasticsearch
sudo systemctl start elasticsearch
```

## **KJØRE TESTENE**

### 1. Test kun embeddings API
```bash
python3 -c "
from src.elasticsearch_client import ElasticsearchClient
client = ElasticsearchClient()
result = client.get_embeddings_from_api('test text', debug=True)
print(f'Result: {result[:5] if result else None}...')
"
```

### 2. Test kun Elasticsearch
```bash
python3 -c "
from src.elasticsearch_client import ElasticsearchClient
client = ElasticsearchClient()
healthy = client.health_check(debug=True)
print(f'Elasticsearch healthy: {healthy}')
"
```

### 3. Kjør komplett systemtest
```bash
# Gi execute-rettigheter
chmod +x test_complete_system.py

# Kjør testen
python3 test_complete_system.py
```

### 4. Test spesifikke spørsmål
```bash
# Test med standard nummer (including route)
python3 -c "from src.cli import ask; ask('Hva er NS-EN ISO 14155?', debug=True)"

# Test med generelt spørsmål (without route)
python3 -c "from src.cli import ask; ask('Hvordan måler man temperatur?', debug=True)"

# Test med personalhandbok (personal route)
python3 -c "from src.cli import ask; ask('Hvor finner jeg personalhandboken?', debug=True)"
```

## **DEBUGGING TIPS**

### Sjekk Elasticsearch status:
```bash
curl -X GET "localhost:9200/_cluster/health?pretty"
curl -X GET "localhost:9200/standard_documents/_search?pretty"
```

### Sjekk miljøvariabler:
```bash
python3 -c "
import os
print('ELASTICSEARCH_URL:', os.getenv('ELASTICSEARCH_URL'))
print('EMBEDDING_API_ENDPOINT:', os.getenv('EMBEDDING_API_ENDPOINT'))
print('OPENAI_API_KEY:', 'SET' if os.getenv('OPENAI_API_KEY') else 'NOT SET')
"
```

### Stopp og fjern Docker container:
```bash
docker stop elasticsearch-test
docker rm elasticsearch-test
```

## **FORVENTET TESTRESULTAT**

Når alt fungerer skal du se:

```
🧪 STANDARDGPT COMPLETE SYSTEM TEST
================================================================================
🔧 TESTING ENVIRONMENT CONFIGURATION
============================================================
✅ ELASTICSEARCH_URL: http://localhost:9200
✅ ELASTICSEARCH_INDEX: standard_documents
✅ EMBEDDING_API_ENDPOINT: https://your-render-api.com/embed
✅ OPENAI_API_KEY: ***

🔮 TESTING EMBEDDINGS API
============================================================
1. Testing: 'NS-EN ISO 14155'
   ✅ Success: 384 dimensjoner

🔍 TESTING ELASTICSEARCH CONNECTION
============================================================
✅ Elasticsearch is available and healthy!
✅ Search successful, found 3 total documents

🛠️ TESTING QUERY OBJECT BUILDING
============================================================
✅ Filter query built successfully
✅ Textual query built successfully
✅ Personal query built successfully

🚀 TESTING COMPLETE FLOW
============================================================
✅ Query processed successfully
📍 Route: including (standard number search)

📊 FINAL TEST SUMMARY
================================================================================
✅ PASS Environment
✅ PASS Embeddings
✅ PASS Elasticsearch
✅ PASS Query Building
✅ PASS Complete Flow

🎉 All tests passed! System is ready for production.
```

Med disse instruksjonene har du full kontroll over testing av hele systemet! 🚀 