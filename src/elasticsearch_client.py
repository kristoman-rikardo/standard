"""
Elasticsearch client for StandardGPT with Cloud support
"""

import json
import requests
import base64
import hashlib
import time
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

# Global embedding cache to avoid repeated API calls
embedding_cache = {}
cache_timestamps = {}
CACHE_TTL = 3600  # 1 hour cache

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
        Format Elasticsearch response into chunks for answer generation
        Using correct field names: text, reference, page
        
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
            total_text_length = 0
            
            for i, hit in enumerate(hits):
                source = hit.get("_source", {})
                score = hit.get("_score", 0)
                
                # Extract content and metadata using correct field names
                text = source.get("text", "")
                reference = source.get("reference", "")
                page = source.get("page", "")
                
                # DEBUG: Track text length before formatting
                original_text_length = len(text)
                total_text_length += original_text_length
                
                if debug and i < 3:  # Debug first 3 hits
                    print(f"\n🔍 DEBUG CHUNK {i+1}:")
                    print(f"   Original text length: {original_text_length}")
                    print(f"   Text preview: '{text[:100]}...'")
                
                # Format chunk
                chunk_lines = []
                chunk_lines.append(f"Dokument {i+1} (score: {score:.2f}):")
                
                if reference:
                    chunk_lines.append(f"Referanse: {reference}")
                if page:
                    chunk_lines.append(f"Side: {page}")
                
                # Use multiline text format to preserve all content including newlines
                chunk_lines.append(f"Innhold: {text}")
                chunk_lines.append("---")
                
                formatted_chunk = "\n".join(chunk_lines)
                chunks.append(formatted_chunk)
                
                # DEBUG: Check formatted chunk length
                if debug and i < 3:
                    content_line = f"Innhold: {text}"
                    print(f"   Content line length: {len(content_line)}")
                    print(f"   Content line: '{content_line[:100]}...'")
                    print(f"   Formatted chunk length: {len(formatted_chunk)}")
            
            formatted_chunks = "\n\n".join(chunks)
            
            if debug:
                print(f"\n🔍 FORMAT_CHUNKS SUMMARY:")
                print(f"   Total hits processed: {len(hits)}")
                print(f"   Total original text: {total_text_length:,} chars")
                print(f"   Final formatted chunks: {len(formatted_chunks):,} chars")
                print(f"   First 200 chars of result: '{formatted_chunks[:200]}...'")
            
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
        Get embeddings from custom API endpoint on Render with caching
        
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
            
            # Check cache first
            text_hash = hashlib.md5(text.encode()).hexdigest()
            current_time = time.time()
            
            # Clean up expired cache entries
            expired_keys = [k for k, timestamp in cache_timestamps.items() 
                          if current_time - timestamp > CACHE_TTL]
            for key in expired_keys:
                embedding_cache.pop(key, None)
                cache_timestamps.pop(key, None)
            
            # Return cached result if available
            if text_hash in embedding_cache:
                if debug:
                    debug_print("Embeddings", f"Cache HIT for text hash: {text_hash[:8]}...")
                log_step_end(2, "Get Embeddings", f"Cached: {len(embedding_cache[text_hash])} dimensions", debug)
                return embedding_cache[text_hash]
            
            if debug:
                debug_print("Embeddings", f"Cache MISS for text hash: {text_hash[:8]}...")
            
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
            
            # Cache the result
            embedding_cache[text_hash] = embeddings
            cache_timestamps[text_hash] = current_time
            
            if debug:
                debug_print("Embeddings", f"Received {len(embeddings)} dimensional vector (cached)")
                debug_print("Embeddings", f"Sample values: {embeddings[:3]}")
                debug_print("Embeddings", f"Cache size: {len(embedding_cache)} entries")
            
            log_step_end(2, "Get Embeddings", f"Success: {len(embeddings)} dimensions", debug)
            return embeddings
            
        except Exception as e:
            log_error("Get Embeddings", str(e), debug)
            if debug:
                debug_print("Embeddings", "Falling back to None (no embeddings)")
            return None 