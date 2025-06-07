# -*- coding: utf-8 -*-
"""
Configuration settings for StandardGPT
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Elasticsearch Cloud Configuration
ELASTICSEARCH_URL = "https://my-elasticsearch-project-f89a7b.es.eastus.azure.elastic.cloud:443"
ELASTICSEARCH_INDEX = "standard_prod"

# API Keys - fungerende nøkler
ELASTICSEARCH_API_KEY = "ApiKey UktaQ0I1Y0JuRWlsdGhiTlFRNG06ZXhSZkczenlydk5tOHk1WklYUUFNQQ=="
OPENAI_API_KEY = "sk-proj-oQz5oE3rFJw2xF7MZPjLT3BlbkFJUMnllk5n9uHMfmDLN1pP"

# Custom Embedding API
EMBEDDING_API_ENDPOINT = "https://fastembed-api.onrender.com/embed"
EMBEDDING_API_KEY = ""

# OpenAI Configuration  
OPENAI_MODEL = "gpt-4o"

# Fallback credentials
ELASTICSEARCH_USER = os.getenv("ELASTICSEARCH_USER", "")
ELASTICSEARCH_PASSWORD = os.getenv("ELASTICSEARCH_PASSWORD", "")

# Legacy support
ELASTICSEARCH_API_ENDPOINT = os.getenv("ELASTICSEARCH_API_ENDPOINT", ELASTICSEARCH_URL)
ELASTICSEARCH_API_KEY = os.getenv("ELASTICSEARCH_API_KEY", ELASTICSEARCH_API_KEY)

# Custom Embedding API (Render)
EMBEDDING_API_ENDPOINT = os.getenv("EMBEDDING_API_ENDPOINT")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY")  # If your API requires authentication

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o") 