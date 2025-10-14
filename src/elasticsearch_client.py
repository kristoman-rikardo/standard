"""
Elasticsearch client for StandardGPT with Cloud support. Set up currently for the Dalai test cloud environment. 
"""

import json
import requests
import base64
import hashlib
import time
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from src.config import (
    ELASTICSEARCH_URL, 
    ELASTICSEARCH_INDEX, 
    ELASTICSEARCH_API_KEY,
    ELASTICSEARCH_USER,
    ELASTICSEARCH_PASSWORD,
    EMBEDDING_API_ENDPOINT,
    EMBEDDING_API_KEY,
    OPENAI_API_KEY,
    ELASTICSEARCH_API_ENDPOINT
)
from src.debug_utils import log_step_start, log_step_end, log_error, debug_print
from src.embedding_keepalive import embedding_keepalive

@dataclass
class EmbeddingCacheEntry:
    """Enhanced cache entry for embeddings with metadata"""
    vector: List[float]
    created: datetime = field(default_factory=datetime.now)
    hits: int = 0
    dimensions: int = 0
    
    def is_expired(self, ttl_seconds: int) -> bool:
        return datetime.now() - self.created > timedelta(seconds=ttl_seconds)
    
    def increment_hits(self):
        self.hits += 1

# Enhanced embedding cache with longer TTL and better management
embedding_cache: Dict[str, EmbeddingCacheEntry] = {}
cache_timestamps = {}
CACHE_TTL = 7200  # 2 hours for embeddings (they rarely change)
MAX_CACHE_SIZE = 1000  # Limit cache size

class ElasticsearchClient:
    """Enhanced Elasticsearch client with intelligent caching and optimization"""
    
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
        
        # Performance tracking
        self.query_stats = {
            "total_queries": 0,
            "total_time": 0,
            "avg_chunks": 0
        }

    def _clean_embedding_cache(self):
        """Clean expired entries and enforce size limits"""
        current_time = datetime.now()
        
        # Remove expired entries
        expired_keys = [
            k for k, entry in embedding_cache.items()
            if entry.is_expired(CACHE_TTL)
        ]
        for key in expired_keys:
            del embedding_cache[key]
        
        # Enforce size limit by removing oldest entries
        if len(embedding_cache) > MAX_CACHE_SIZE:
            # Sort by creation time and remove oldest
            sorted_entries = sorted(
                embedding_cache.items(),
                key=lambda x: x[1].created
            )
            entries_to_remove = len(embedding_cache) - MAX_CACHE_SIZE
            for key, _ in sorted_entries[:entries_to_remove]:
                del embedding_cache[key]

    def get_embeddings_from_api(self, text: str, debug: bool = True) -> Optional[List[float]]:
        """
        Enhanced embedding generation with intelligent caching and batch optimization
        
        Args:
            text (str): Text to embed
            debug (bool): Enable debug logging
            
        Returns:
            list: Embeddings vector or None if failed
        """
        # Check if we should use internal embeddings (OpenAI) instead of external API
        if not EMBEDDING_API_ENDPOINT or EMBEDDING_API_ENDPOINT == "INTERNAL":
            return self._generate_internal_embeddings(text, debug)
        
        # Generate cache key
        text_hash = hashlib.md5(text.encode()).hexdigest()
        
        # Clean cache periodically
        self._clean_embedding_cache()
        
        # Check cache first
        if text_hash in embedding_cache:
            entry = embedding_cache[text_hash]
            if not entry.is_expired(CACHE_TTL):
                entry.increment_hits()
                if debug:
                    debug_print("Embeddings", f"Cache HIT for text hash: {text_hash[:8]}... ({entry.hits} hits)")
                return entry.vector
            else:
                # Remove expired entry
                del embedding_cache[text_hash]

        if debug:
            debug_print("Embeddings", f"Cache MISS for text hash: {text_hash[:8]}...")
        
        # Determine API type
        is_local_api = "127.0.0.1" in EMBEDDING_API_ENDPOINT or "localhost" in EMBEDDING_API_ENDPOINT
        
        # Try external API with multiple attempts and increasing timeouts
        max_retries = 3
        timeouts = [30, 45, 60]  # Progressive timeouts for Railway stability
        
        for attempt in range(max_retries):
            try:
                # Prepare request data
                payload = {"text": text}
                
                # Setup headers for request
                request_headers = {"Content-Type": "application/json"}
                if EMBEDDING_API_KEY and not is_local_api:
                    request_headers["Authorization"] = f"Bearer {EMBEDDING_API_KEY}"
                
                if debug:
                    api_type = "LOKAL" if is_local_api else "EKSTERN"
                    debug_print("Embeddings", f"Attempt {attempt + 1}/{max_retries}: Calling {api_type} API: {EMBEDDING_API_ENDPOINT}")
                    debug_print("Embeddings", f"Timeout: {timeouts[attempt]}s")
                
                # Make API request with progressive timeout
                response = requests.post(
                    EMBEDDING_API_ENDPOINT,
                    headers=request_headers,
                    json=payload,
                    timeout=timeouts[attempt]
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Extract vectors based on API response format
                    if "vectors" in data and data["vectors"]:
                        # Multiple vectors format
                        vectors = data["vectors"][0]
                    elif "vector" in data:
                        # Single vector format
                        vectors = data["vector"]
                    elif "data" in data and data["data"]:
                        # OpenAI-style format
                        vectors = data["data"][0]["embedding"]
                    else:
                        # Direct vector format
                        vectors = data
                    
                    # Validate vector format
                    if isinstance(vectors, list) and len(vectors) > 0:
                        # Cache the result with enhanced metadata
                        cache_entry = EmbeddingCacheEntry(
                            vector=vectors,
                            dimensions=len(vectors)
                        )
                        embedding_cache[text_hash] = cache_entry
                        
                        if debug:
                            debug_print("Embeddings", f"External API success on attempt {attempt + 1}: {len(vectors)} dimensional vector (cached)")
                        
                        # Update keep-alive activity timestamp
                        embedding_keepalive.update_activity()
                        
                        return vectors
                    else:
                        if debug:
                            debug_print("Embeddings", f"Invalid vector format received: {type(vectors)}")
                        continue  # Try next attempt
                else:
                    error_text = response.text[:200] if response.text else "No error message"
                    if debug:
                        debug_print("Embeddings", f"API error on attempt {attempt + 1}: {response.status_code} - {error_text}")
                    if attempt == max_retries - 1:  # Last attempt
                        raise Exception(f"Embedding API returned {response.status_code}: {error_text}")
                        
            except requests.exceptions.Timeout:
                error_msg = f"API request timed out ({timeouts[attempt]}s) on attempt {attempt + 1}"
                if debug:
                    debug_print("Embeddings", error_msg)
                if attempt == max_retries - 1:  # Last attempt
                    # Fall back to internal embeddings if external API consistently fails
                    if debug:
                        debug_print("Embeddings", "External API failed after all retries, falling back to internal embeddings")
                    return self._generate_internal_embeddings(text, debug)
                    
            except requests.exceptions.ConnectionError as e:
                error_msg = f"Connection error on attempt {attempt + 1}: {str(e)}"
                if debug:
                    debug_print("Embeddings", error_msg)
                if attempt == max_retries - 1:  # Last attempt
                    # Fall back to internal embeddings
                    if debug:
                        debug_print("Embeddings", "Connection failed after all retries, falling back to internal embeddings")
                    return self._generate_internal_embeddings(text, debug)
                    
            except Exception as e:
                error_msg = f"API request failed on attempt {attempt + 1}: {str(e)}"
                if debug:
                    debug_print("Embeddings", error_msg)
                if attempt == max_retries - 1:  # Last attempt
                    # Fall back to internal embeddings
                    if debug:
                        debug_print("Embeddings", "External API failed completely, falling back to internal embeddings")
                    return self._generate_internal_embeddings(text, debug)
        
        # If we reach here, all attempts failed - fallback to internal embeddings
        return self._generate_internal_embeddings(text, debug)

    def _generate_internal_embeddings(self, text: str, debug: bool = True) -> Optional[List[float]]:
        """
        Generate embeddings using OpenAI API as internal fallback
        
        Args:
            text (str): Text to embed
            debug (bool): Enable debug logging
            
        Returns:
            list: Embeddings vector or None if failed
        """
        try:
            import openai
            
            if not OPENAI_API_KEY:
                if debug:
                    debug_print("Embeddings", "OpenAI API key not configured for internal embeddings")
                return None
            
            # Generate cache key for internal embeddings
            text_hash = hashlib.md5(f"internal_{text}".encode()).hexdigest()
            
            # Check cache first
            if text_hash in embedding_cache:
                entry = embedding_cache[text_hash]
                if not entry.is_expired(CACHE_TTL):
                    entry.increment_hits()
                    if debug:
                        debug_print("Embeddings", f"Internal cache HIT for text hash: {text_hash[:8]}...")
                    return entry.vector
            
            if debug:
                debug_print("Embeddings", "Generating embeddings with OpenAI (internal)")
            
            # Initialize OpenAI client
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            
            # Create embedding
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=text,
                encoding_format="float"
            )
            
            if response.data and len(response.data) > 0:
                vectors = response.data[0].embedding
                
                # Cache the result
                cache_entry = EmbeddingCacheEntry(
                    vector=vectors,
                    dimensions=len(vectors)
                )
                embedding_cache[text_hash] = cache_entry
                
                if debug:
                    debug_print("Embeddings", f"Internal OpenAI embedding success: {len(vectors)} dimensions (cached)")
                
                return vectors
            else:
                if debug:
                    debug_print("Embeddings", "No embedding data received from OpenAI")
                return None
                
        except Exception as e:
            if debug:
                debug_print("Embeddings", f"Internal embedding generation failed: {str(e)}")
            return None

    def batch_embeddings(self, texts: List[str], debug: bool = True) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts efficiently
        
        Args:
            texts: List of texts to embed
            debug: Enable debug logging
            
        Returns:
            List of embedding vectors (same order as input)
        """
        if not texts:
            return []
        
        results = []
        cache_hits = 0
        cache_misses = 0
        
        # Check cache for all texts first
        for text in texts:
            text_hash = hashlib.md5(text.encode()).hexdigest()
            if text_hash in embedding_cache:
                entry = embedding_cache[text_hash]
                if not entry.is_expired(CACHE_TTL):
                    entry.increment_hits()
                    results.append(entry.vector)
                    cache_hits += 1
                    continue
            
            # Cache miss - generate embedding
            embedding = self.get_embeddings_from_api(text, debug=False)
            results.append(embedding)
            cache_misses += 1
        
        if debug:
            debug_print("Embeddings", f"Batch processing: {cache_hits} cache hits, {cache_misses} API calls")
        
        return results

    def search(self, query_object: Dict, debug: bool = True) -> Dict:
        """
        Enhanced search with performance tracking
        
        Args:
            query_object (dict): Complete Elasticsearch query object from qo_* files
            debug (bool): Enable debug logging
            
        Returns:
            dict: Raw Elasticsearch response
        """
        start_time = time.time()
        
        try:
            # Support explicit API endpoint override if provided
            if ELASTICSEARCH_API_ENDPOINT:
                url = ELASTICSEARCH_API_ENDPOINT
            else:
                url = f"{self.url}/{self.index}/_search"
            
            # Log the query being sent
            if debug:
                debug_print("Elasticsearch", f"Sending query to: {url}")
                debug_print("Elasticsearch", f"Query size: {query_object.get('size', 'default')}")
                debug_print("Elasticsearch", f"Using API key authentication: {bool(ELASTICSEARCH_API_KEY)}")
            
            # Make the request with API key in headers
            response = requests.post(
                url,
                headers=self.headers,
                json=query_object,
                auth=self.auth,  # Fallback for basic auth
                timeout=60
            )
            
            # Check response status
            if response.status_code != 200:
                raise Exception(f"Elasticsearch returned status {response.status_code}: {response.text}")
            
            # Parse response
            result = response.json()
            
            # Track performance
            query_time = time.time() - start_time
            hits_count = result.get("hits", {}).get("total", {}).get("value", 0)
            
            self.query_stats["total_queries"] += 1
            self.query_stats["total_time"] += query_time
            self.query_stats["avg_chunks"] = (
                (self.query_stats["avg_chunks"] * (self.query_stats["total_queries"] - 1) + hits_count) 
                / self.query_stats["total_queries"]
            )
            
            if debug:
                debug_print("Elasticsearch", f"Query completed in {query_time:.3f}s - {hits_count} documents")
            
            return result
            
        except Exception as e:
            # If ES is unreachable, return an empty result so the pipeline can still generate an answer
            log_error("Elasticsearch Search", str(e), debug)
            if debug:
                debug_print("Elasticsearch", "Returning empty hits due to connection/search error")
            return {
                "took": int((time.time() - start_time) * 1000),
                "timed_out": True,
                "hits": {"total": {"value": 0, "relation": "eq"}, "max_score": 0, "hits": []}
            }

    def format_chunks(self, elasticsearch_response: Dict, debug: bool = True) -> str:
        """
        Enhanced chunk formatting with intelligent truncation
        """
        try:
            hits = elasticsearch_response.get("hits", {}).get("hits", [])
            
            if not hits:
                return "Ingen relevante dokumenter funnet."
            
            chunks = []
            total_text_length = 0
            max_total_length = 200000  # Limit total length for performance
            
            for i, hit in enumerate(hits, 1):
                if total_text_length > max_total_length:
                    break
                
                source = hit.get("_source", {})
                score = hit.get("_score", 0)
                
                # Extract fields with fallbacks
                text = source.get("text", source.get("content", "Ingen tekst tilgjengelig"))
                reference = source.get("reference", source.get("title", "Ukjent referanse"))
                page = source.get("page", source.get("page_number", "Ukjent side"))
                
                # Intelligent truncation for very long texts
                if len(text) > 2000:
                    text = text[:1800] + "..."
                
                chunk = (
                    f"Dokument {i} (score: {score:.2f}):\n"
                    f"Referanse: {reference}\n"
                    f"Side: {page}\n"
                    f"Innhold: {text}\n"
                    f"---"
                )
                
                chunks.append(chunk)
                total_text_length += len(chunk)
            
            formatted_chunks = "\n\n".join(chunks)
            
            if debug:
                debug_print("Format Chunks", f"Processed {len(chunks)} chunks ({total_text_length:,} chars)")
            
            return formatted_chunks
            
        except Exception as e:
            log_error("Format Chunks", str(e), debug)
            raise

    def get_cache_stats(self) -> Dict:
        """Get comprehensive cache and performance statistics"""
        total_entries = len(embedding_cache)
        total_hits = sum(entry.hits for entry in embedding_cache.values())
        
        # Calculate cache efficiency
        if total_entries > 0:
            avg_hits_per_entry = total_hits / total_entries
            oldest_entry = min(embedding_cache.values(), key=lambda x: x.created)
            newest_entry = max(embedding_cache.values(), key=lambda x: x.created)
            cache_age_hours = (newest_entry.created - oldest_entry.created).total_seconds() / 3600
        else:
            avg_hits_per_entry = 0
            cache_age_hours = 0
        
        return {
            "embedding_cache": {
                "total_entries": total_entries,
                "total_hits": total_hits,
                "avg_hits_per_entry": round(avg_hits_per_entry, 2),
                "cache_age_hours": round(cache_age_hours, 2),
                "max_size": MAX_CACHE_SIZE,
                "utilization_percent": round((total_entries / MAX_CACHE_SIZE) * 100, 1)
            },
            "query_performance": {
                "total_queries": self.query_stats["total_queries"],
                "avg_query_time": round(self.query_stats["total_time"] / max(1, self.query_stats["total_queries"]), 3),
                "avg_chunks_returned": round(self.query_stats["avg_chunks"], 1)
            }
        }

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
