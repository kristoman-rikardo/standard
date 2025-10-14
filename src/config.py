# -*- coding: utf-8 -*-
"""
Configuration settings for StandardGPT - SECURE VERSION
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Elasticsearch Cloud Configuration
ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "https://my-elasticsearch-project-f89a7b.es.eastus.azure.elastic.cloud:443")
ELASTICSEARCH_INDEX = os.getenv("ELASTICSEARCH_INDEX", "standard_prod")
ELASTICSEARCH_API_ENDPOINT = os.getenv("ELASTICSEARCH_API_ENDPOINT", "")

# API Keys - SECURITY: All keys must come from environment variables
ELASTICSEARCH_API_KEY = os.getenv("ELASTICSEARCH_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Custom Embedding API
EMBEDDING_API_ENDPOINT = os.getenv("EMBEDDING_API_ENDPOINT")
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")

# Keep-alive configuration for preventing cold starts
EMBEDDING_KEEPALIVE_ENABLED = os.getenv("EMBEDDING_KEEPALIVE_ENABLED", "true").lower() == "true"
EMBEDDING_KEEPALIVE_INTERVAL_MINUTES = int(os.getenv("EMBEDDING_KEEPALIVE_INTERVAL_MINUTES", "10"))

# OpenAI Configuration with MAXIMUM token support and deterministic temperature
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.0"))  # Deterministic responses

# Specialized model configuration with MAXIMUM token support
OPENAI_MODEL_DEFAULT = os.getenv("OPENAI_MODEL_DEFAULT", "gpt-4o")  # For optimization, analysis, extraction
OPENAI_MODEL_ANSWER = os.getenv("OPENAI_MODEL_ANSWER", "gpt-4o")  # For final answer generation

# MAXIMUM token configuration
OPENAI_MAX_TOKENS_DEFAULT = int(os.getenv("OPENAI_MAX_TOKENS_DEFAULT", "4000"))  # Maximum for most operations
OPENAI_MAX_TOKENS_ANSWER = int(os.getenv("OPENAI_MAX_TOKENS_ANSWER", "4000"))  # Maximum for answer generation

# Fallback credentials for basic auth
ELASTICSEARCH_USER = os.getenv("ELASTICSEARCH_USER", "")
ELASTICSEARCH_PASSWORD = os.getenv("ELASTICSEARCH_PASSWORD", "")

# Security validation - Fail fast if critical keys are missing
def validate_environment():
    """Validate that all required environment variables are set"""
    required_vars = {
        "ELASTICSEARCH_API_KEY": ELASTICSEARCH_API_KEY,
        "OPENAI_API_KEY": OPENAI_API_KEY,
        "EMBEDDING_API_ENDPOINT": EMBEDDING_API_ENDPOINT
    }
    
    missing_vars = [var for var, value in required_vars.items() if not value]
    
    if missing_vars:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing_vars)}. "
            f"Please set these in your .env file or environment."
        )
    
    return True

# Validate on import
validate_environment() 