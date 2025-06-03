import os
from dotenv import load_dotenv

load_dotenv()

# Elasticsearch
ELASTICSEARCH_API_ENDPOINT = os.getenv("ELASTICSEARCH_API_ENDPOINT")
ELASTICSEARCH_API_KEY = os.getenv("ELASTICSEARCH_API_KEY")

# Custom Embedding API  
EMBEDDING_API_ENDPOINT = os.getenv("EMBEDDING_API_ENDPOINT")

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o") 