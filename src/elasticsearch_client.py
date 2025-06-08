"""
Elasticsearch client for StandardGPT with Cloud support
"""

import json
import requests
import base64
from typing import Dict, List, Optional
from src.config import (
    ELASTICSEARCH_URL, 
    ELASTICSEARCH_INDEX, 
    ELASTICSEARCH_API_KEY,
    ELASTICSEARCH_USER,
    ELASTICSEARCH_PASSWORD,
    EMBEDDING_API_ENDPOINT,
    EMBEDDING_API_KEY
)
from src.debug_utils import log_step_start, log_step_end, log_error, debug_print

class ElasticsearchClient:
    """Custom Elasticsearch client for StandardGPT with Cloud support"""
    
    def __init__(self):
        """Initialize the Elasticsearch client with API key support"""
        self.url = ELASTICSEARCH_URL
        self.index = ELASTICSEARCH_INDEX
        self.auth = None
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Use API key authentication for Elasticsearch Cloud
        if ELASTICSEARCH_API_KEY:
            # For Elasticsearch Cloud - use the complete API key as is
            self.headers = {
                "Authorization": ELASTICSEARCH_API_KEY,  # Use directly as it already contains "ApiKey " prefix
                "Content-Type": "application/json"
            }
        elif ELASTICSEARCH_USER and ELASTICSEARCH_PASSWORD:
            self.auth = (ELASTICSEARCH_USER, ELASTICSEARCH_PASSWORD)
    
    def search(self, query_object: Dict, debug: bool = True) -> Dict:
        """
        Execute a search query against Elasticsearch Cloud
        
        Args:
            query_object (dict): Complete Elasticsearch query object from qo_* files
            debug (bool): Enable debug logging
            
        Returns:
            dict: Raw Elasticsearch response
        """
        log_step_start(5, "Elasticsearch Search", f"Query to {self.index}", debug)
        
        try:
            # Use the full Elasticsearch Cloud URL with _search endpoint
            url = f"{self.url}/{self.index}/_search"
            
            # Log the query being sent
            if debug:
                debug_print("Elasticsearch", f"Sending query to: {url}")
                debug_print("Elasticsearch", f"Query object: {json.dumps(query_object, indent=2, ensure_ascii=False)}")
                debug_print("Elasticsearch", f"Using API key authentication: {bool(ELASTICSEARCH_API_KEY)}")
            
            # Make the request with API key in headers
            response = requests.post(
                url,
                headers=self.headers,
                json=query_object,
                auth=self.auth,  # Fallback for basic auth
                timeout=30
            )
            
            # Check response status
            if response.status_code != 200:
                raise Exception(f"Elasticsearch returned status {response.status_code}: {response.text}")
            
            # Parse response
            result = response.json()
            
            # Log response details
            hits_count = result.get("hits", {}).get("total", {}).get("value", 0)
            log_step_end(5, "Elasticsearch Search", f"Found {hits_count} documents", debug)
            
            return result
            
        except Exception as e:
            log_error("Elasticsearch Search", str(e), debug)
            raise
    
    def format_chunks(self, elasticsearch_response: Dict, debug: bool = True) -> str:
        """
        Format Elasticsearch response into chunks for the answer prompt
        Using the correct field names: text, reference, page
        
        Args:
            elasticsearch_response (dict): Raw Elasticsearch response
            debug (bool): Enable debug logging
            
        Returns:
            str: Formatted chunks for answer generation
        """
        log_step_start("5.1", "Format Chunks", "Processing search results", debug)
        
        try:
            hits = elasticsearch_response.get("hits", {}).get("hits", [])
            
            if not hits:
                log_step_end("5.1", "Format Chunks", "No documents found", debug)
                return "Ingen relevante dokumenter funnet."
            
            chunks = []
            for i, hit in enumerate(hits):
                source = hit.get("_source", {})
                score = hit.get("_score", 0)
                
                # Extract content and metadata using correct field names
                text = source.get("text", "")
                reference = source.get("reference", "")
                page = source.get("page", "")
                
                # Format chunk
                chunk_lines = []
                chunk_lines.append(f"Dokument {i+1} (score: {score:.2f}):")
                
                if reference:
                    chunk_lines.append(f"Referanse: {reference}")
                if page:
                    chunk_lines.append(f"Side: {page}")
                
                chunk_lines.append(f"Innhold: {text}")
                chunk_lines.append("---")
                
                chunks.append("\n".join(chunk_lines))
            
            formatted_chunks = "\n\n".join(chunks)
            
            log_step_end("5.1", "Format Chunks", f"Formatted {len(chunks)} chunks", debug)
            return formatted_chunks
            
        except Exception as e:
            log_error("Format Chunks", str(e), debug)
            raise
    
    def get_document_metadata(self, elasticsearch_response: Dict) -> List[Dict]:
        """
        Extract metadata from Elasticsearch response for debugging
        Using correct field names: text, reference, page
        
        Args:
            elasticsearch_response (dict): Raw Elasticsearch response
            
        Returns:
            list: List of document metadata
        """
        hits = elasticsearch_response.get("hits", {}).get("hits", [])
        metadata = []
        
        for hit in hits:
            source = hit.get("_source", {})
            metadata.append({
                "score": hit.get("_score", 0),
                "reference": source.get("reference", ""),
                "page": source.get("page", ""),
                "content_length": len(source.get("text", ""))
            })
        
        return metadata
    
    def health_check(self, debug: bool = True) -> bool:
        """
        Check if Elasticsearch Cloud is available
        For serverless instances, we test with a simple search instead of cluster health
        
        Args:
            debug (bool): Enable debug logging
            
        Returns:
            bool: True if Elasticsearch is available
        """
        try:
            # For serverless Elasticsearch, use a simple search instead of cluster health
            test_query = {"query": {"match_all": {}}, "size": 1}
            url = f"{self.url}/{self.index}/_search"
            response = requests.post(url, headers=self.headers, auth=self.auth, json=test_query, timeout=10)
            
            if response.status_code == 200:
                result = response.json()
                doc_count = result.get("hits", {}).get("total", {}).get("value", 0)
                
                if debug:
                    debug_print("Elasticsearch", f"Health check: OK, {doc_count} documents available")
                
                return True
            else:
                if debug:
                    debug_print("Elasticsearch", f"Health check failed: {response.status_code}")
                    debug_print("Elasticsearch", f"Response: {response.text[:200]}")
                return False
                
        except Exception as e:
            if debug:
                debug_print("Elasticsearch", f"Health check error: {e}")
            return False
    
    def get_embeddings_from_api(self, text: str, debug: bool = True) -> Optional[List[float]]:
        """
        Get embeddings from custom API endpoint on Render
        
        Args:
            text (str): Text to embed
            debug (bool): Enable debug logging
            
        Returns:
            list: Embeddings vector or None if failed
        """
        log_step_start(2, "Get Embeddings", f"Text: {text[:50]}...", debug)
        
        try:
            if not EMBEDDING_API_ENDPOINT:
                if debug:
                    debug_print("Embeddings", "EMBEDDING_API_ENDPOINT not configured, skipping embeddings")
                log_step_end(2, "Get Embeddings", "Embeddings API not configured", debug)
                return None
            
            # Prepare the request payload
            payload = {
                "text": text,
                "model": "all-MiniLM-L6-v2"  # Default model, can be made configurable
            }
            
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            # Add API key if configured
            if EMBEDDING_API_KEY:
                headers["Authorization"] = f"Bearer {EMBEDDING_API_KEY}"
                # Alternative: headers["X-API-Key"] = EMBEDDING_API_KEY
            
            if debug:
                debug_print("Embeddings", f"Calling API: {EMBEDDING_API_ENDPOINT}")
                debug_print("Embeddings", f"Payload: {json.dumps(payload, ensure_ascii=False)}")
                if EMBEDDING_API_KEY:
                    debug_print("Embeddings", "Using API key authentication")
            
            # Make the API call
            response = requests.post(
                EMBEDDING_API_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=30
            )
            
            # Check response status
            if response.status_code != 200:
                raise Exception(f"Embeddings API returned status {response.status_code}: {response.text}")
            
            # Parse response
            result = response.json()
            
            # Extract embeddings from response
            # Handle Render API format: {"vectors": [[...]], "model": "...", "dimension": 384}
            embeddings = None
            
            if "vectors" in result and isinstance(result["vectors"], list) and len(result["vectors"]) > 0:
                # Handle Render API format - take first vector from array
                embeddings = result["vectors"][0]
            elif "embeddings" in result:
                embeddings = result["embeddings"]
            elif "embedding" in result:
                embeddings = result["embedding"]
            elif "vector" in result:
                embeddings = result["vector"]
            elif isinstance(result, list):
                embeddings = result
            else:
                raise Exception(f"Unexpected embeddings API response format: {list(result.keys())}")
            
            if not isinstance(embeddings, list) or not embeddings:
                raise Exception("Embeddings API returned empty or invalid vector")
            
            if debug:
                debug_print("Embeddings", f"Received {len(embeddings)} dimensional vector")
                debug_print("Embeddings", f"Sample values: {embeddings[:3]}")
            
            log_step_end(2, "Get Embeddings", f"Success: {len(embeddings)} dimensions", debug)
            return embeddings
            
        except Exception as e:
            log_error("Get Embeddings", str(e), debug)
            if debug:
                debug_print("Embeddings", "Falling back to None (no embeddings)")
            return None 