from langchain_elasticsearch import ElasticsearchStore
from .custom_embeddings import FastEmbedAPI
from .config import ELASTICSEARCH_API_ENDPOINT, ELASTICSEARCH_API_KEY
import re

# Parse URL for separate host and index
def parse_elasticsearch_url(url):
    # URL format: https://host:port/index/_search
    match = re.match(r'(https?://[^/]+)/([^/]+)/_search', url)
    if match:
        return match.group(1), match.group(2)
    else:
        # Fallback hvis format er annerledes
        return url.rsplit('/', 2)[0], "standard_prod"

es_host, es_index = parse_elasticsearch_url(ELASTICSEARCH_API_ENDPOINT)

# Clean API key - remove 'ApiKey ' prefix if present
api_key = ELASTICSEARCH_API_KEY
if api_key.startswith("ApiKey "):
    api_key = api_key[7:]  # Remove 'ApiKey ' prefix

embeddings = FastEmbedAPI()

store = ElasticsearchStore(
    es_url=es_host,
    es_api_key=api_key,
    index_name=es_index,
    embedding=embeddings,
)

retriever = store.as_retriever(
    search_kwargs={
        "k": 6,
    }
) 