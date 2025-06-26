"""
Advanced prompt manager for StandardGPT with optimization and caching
"""

import asyncio
import time
import hashlib
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from langchain_core.prompts import PromptTemplate
from openai import AsyncOpenAI
import aiohttp

from src.config import (
    OPENAI_API_KEY, 
    OPENAI_MODEL_DEFAULT, 
    OPENAI_TEMPERATURE
)
from src.debug_utils import log_step_start, log_step_end, log_error, debug_print

@dataclass
class CacheEntry:
    """Cache entry with TTL and metadata"""
    value: Any
    created: datetime = field(default_factory=datetime.now)
    hits: int = 0
    
    def is_expired(self, ttl_seconds: int) -> bool:
        return datetime.now() - self.created > timedelta(seconds=ttl_seconds)
    
    def increment_hits(self):
        self.hits += 1

@dataclass
class PromptConfig:
    """Configuration for prompt optimization"""
    max_tokens: int
    temperature: float
    ttl_seconds: int  # Cache TTL
    system_message: str
    
# Optimized prompt configurations based on operation type
PROMPT_CONFIGS = {
    "analysis": PromptConfig(
        max_tokens=20,  # Only need single word response
        temperature=0.1,  # Deterministic routing
        ttl_seconds=3600,  # Cache for 1 hour
        system_message="You are a routing system that analyzes questions and returns exactly one of: 'including', 'without', 'personal', or 'memory'."
    ),
    "extractStandard": PromptConfig(
        max_tokens=100,  # Standard numbers are short
        temperature=0.0,  # Deterministic extraction
        ttl_seconds=1800,  # Cache for 30 minutes
        system_message="You extract standard numbers from questions. Return only the standard numbers, comma separated."
    ),
    "extractFromMemory": PromptConfig(
        max_tokens=100,  # Memory terms are short
        temperature=0.0,  # Deterministic extraction
        ttl_seconds=900,   # Cache for 15 minutes
        system_message="You extract standard numbers from memory context. Return only the standard numbers, comma separated."
    ),
    "optimizeSemantic": PromptConfig(
        max_tokens=200,  # Optimized questions can be longer
        temperature=0.3,  # Some creativity for optimization
        ttl_seconds=1800,  # Cache for 30 minutes
        system_message="You are a helpful assistant that optimizes questions for semantic search."
    ),
    "optimizeTextual": PromptConfig(
        max_tokens=150,  # Textual optimization is shorter
        temperature=0.2,  # Slight creativity
        ttl_seconds=1800,  # Cache for 30 minutes
        system_message="You optimize questions for textual search by extracting key terms."
    ),
    "answer": PromptConfig(
        max_tokens=1500,  # Answers need more space
        temperature=0.4,  # Balanced creativity
        ttl_seconds=900,   # Cache for 15 minutes (answers change more)
        system_message="You are a knowledgeable assistant providing detailed technical answers."
    )
}

class PromptManager:
    """Advanced Prompt Manager with caching and optimization"""
    
    def __init__(self):
        self.prompts = self._load_all_prompts()
        
        # Initialize async OpenAI client with connection pooling
        self.client = AsyncOpenAI(
            api_key=OPENAI_API_KEY,
            max_retries=3,
            timeout=30.0
        )
        
        # Smart caching system
        self.cache: Dict[str, CacheEntry] = {}
        self.cache_stats = {
            "hits": 0,
            "misses": 0,
            "expired": 0
        }
        
        # Connection pooling for HTTP requests
        self.session = None
        self._debug_enabled = False

    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=10, limit_per_host=5)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()

    def _generate_cache_key(self, prompt_type: str, content: str, **kwargs) -> str:
        """Generate cache key from prompt type and content"""
        # For memory-based prompts, include conversation memory in cache key
        cache_data = {
            "type": prompt_type,
            "content": content,
            "kwargs": kwargs
        }
        
        # For prompts that use conversation memory, include it in the cache key
        # to prevent cross-session contamination
        conversation_memory = kwargs.get("conversation_memory", "")
        if conversation_memory and conversation_memory != "0" and conversation_memory != "":
            cache_data["memory_hash"] = hashlib.md5(conversation_memory.encode()).hexdigest()[:8]
        
        # For memory route, include session context to prevent cache sharing
        if prompt_type == "answer" and conversation_memory and conversation_memory != "0":
            cache_data["memory_context"] = True
            
        return hashlib.md5(json.dumps(cache_data, sort_keys=True).encode()).hexdigest()

    def _get_from_cache(self, cache_key: str, ttl_seconds: int) -> Optional[Any]:
        """Get value from cache if not expired"""
        if cache_key in self.cache:
            entry = self.cache[cache_key]
            if entry.is_expired(ttl_seconds):
                del self.cache[cache_key]
                self.cache_stats["expired"] += 1
                return None
            else:
                entry.increment_hits()
                self.cache_stats["hits"] += 1
                return entry.value
        
        self.cache_stats["misses"] += 1
        return None

    def _set_cache(self, cache_key: str, value: Any):
        """Set value in cache"""
        self.cache[cache_key] = CacheEntry(value=value)

    async def _call_openai_optimized(self, prompt_type: str, messages: List[Dict], **kwargs) -> str:
        """
        Optimized OpenAI API call with caching and prompt-specific configuration
        
        Args:
            prompt_type: Type of prompt for optimization
            messages: OpenAI messages
            **kwargs: Additional parameters
            
        Returns:
            str: Generated response content
        """
        config = PROMPT_CONFIGS.get(prompt_type, PROMPT_CONFIGS["answer"])
        
        # Generate cache key
        cache_key = self._generate_cache_key(prompt_type, str(messages), **kwargs)
        
        # Try cache first
        cached_result = self._get_from_cache(cache_key, config.ttl_seconds)
        if cached_result is not None:
            if self._debug_enabled:
                debug_print("Cache", f"HIT for {prompt_type}: {cache_key[:8]}")
            return cached_result
        
        if self._debug_enabled:
            debug_print("Cache", f"MISS for {prompt_type}: {cache_key[:8]}")
            debug_print("OpenAI", f"Using model: {OPENAI_MODEL_DEFAULT} (max_tokens: {config.max_tokens}, temp: {config.temperature})")
        
        try:
            # Use optimized parameters
            response = await self.client.chat.completions.create(
                model=OPENAI_MODEL_DEFAULT,
                messages=messages,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                stream=False
            )
            
            result = response.choices[0].message.content.strip()
            
            # Cache the result
            self._set_cache(cache_key, result)
            
            return result
            
        except Exception as e:
            raise Exception(f"OpenAI API error for {prompt_type}: {e}")

    def _call_openai(self, messages: List[Dict], temperature: float = OPENAI_TEMPERATURE, model: str = None, max_tokens: int = None) -> str:
        """
        LEGACY: Synchronous OpenAI call - kept for backward compatibility
        """
        # Convert to async call
        import asyncio
        return asyncio.run(self._call_openai_optimized("legacy", messages))

    def _load_prompt(self, name):
        """Load a single prompt from file"""
        try:
            path = Path(__file__).parent / "prompts" / f"{name}.txt"
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            return PromptTemplate.from_template(content)
        except Exception as e:
            raise FileNotFoundError(f"Could not load prompt {name}: {e}")
    
    def _load_all_prompts(self):
        """Load all required prompts"""
        prompt_names = [
            "optimizeSemantic",
            "analysis", 
            "extractStandard",
            "optimizeTextual",
            "answer",
            "extractFromMemory"
        ]
        
        prompts = {}
        for name in prompt_names:
            prompts[name] = self._load_prompt(name)
        
        return prompts
    
    def create_prompt_input(self, last_utterance, **kwargs):
        """
        Create standardized input for all prompts
        
        Args:
            last_utterance (str): The user's question
            **kwargs: Additional variables for the prompt
        
        Returns:
            dict: Standardized prompt input
        """
        base_input = {
            "last_utterance": last_utterance,
            "chunks": kwargs.get("chunks", ""),
            "conversation_memory": kwargs.get("conversation_memory", ""),
        }
        base_input.update(kwargs)
        return base_input
    
    async def optimize_semantic(self, question: str, conversation_memory: str = "") -> str:
        """
        Async version of semantic optimization with caching
        
        Args:
            question: User's original question
            conversation_memory: Formatted conversation memory
            
        Returns:
            str: Optimized question for semantic search
        """
        try:
            prompt_input = self.create_prompt_input(question, conversation_memory=conversation_memory)
            prompt_text = self.prompts["optimizeSemantic"].invoke(prompt_input).text
            
            messages = [
                {"role": "system", "content": PROMPT_CONFIGS["optimizeSemantic"].system_message},
                {"role": "user", "content": prompt_text}
            ]
            
            return await self._call_openai_optimized("optimizeSemantic", messages)
            
        except Exception as e:
            raise Exception(f"Semantic optimization failed: {e}")

    async def analyze_question(self, question: str, conversation_memory: str = "") -> str:
        """
        Async version of question analysis with caching and validation
        
        Args:
            question: User's original question
            conversation_memory: Formatted conversation memory
            
        Returns:
            str: Analysis result ("including", "without", "personal", or "memory")
        """
        try:
            prompt_input = self.create_prompt_input(question, conversation_memory=conversation_memory)
            prompt_text = self.prompts["analysis"].invoke(prompt_input).text
            
            messages = [
                {"role": "system", "content": PROMPT_CONFIGS["analysis"].system_message},
                {"role": "user", "content": prompt_text}
            ]
            
            output = await self._call_openai_optimized("analysis", messages)
            
            # Clean and validate output
            output = output.lower().strip().strip('"\'`()[]{}.,!?;: \n\r\t')
            
            # Validate output against known routes
            valid_routes = ["including", "without", "personal", "memory"]
            if output not in valid_routes:
                return "without"  # Safe fallback
            
            return output
            
        except Exception as e:
            return "without"  # Safe fallback on error

    async def extract_standard_numbers(self, question: str) -> List[str]:
        """
        Async version of standard number extraction with caching
        
        Args:
            question: User's question
            
        Returns:
            List[str]: Extracted standard numbers
        """
        try:
            prompt_input = self.create_prompt_input(question)
            prompt_text = self.prompts["extractStandard"].invoke(prompt_input).text
            
            messages = [
                {"role": "system", "content": PROMPT_CONFIGS["extractStandard"].system_message},
                {"role": "user", "content": prompt_text}
            ]
            
            output = await self._call_openai_optimized("extractStandard", messages)
            
            # Parse comma-separated standards
            if output.strip():
                standards = [s.strip() for s in output.split(",") if s.strip()]
                return standards
            return []
            
        except Exception as e:
            return []  # Return empty list on error

    async def extract_from_memory(self, question: str, conversation_memory: str) -> List[str]:
        """
        Async version of memory extraction with caching
        
        Args:
            question: User's question
            conversation_memory: Formatted conversation memory
            
        Returns:
            List[str]: Extracted terms from memory context
        """
        try:
            prompt_input = self.create_prompt_input(question, conversation_memory=conversation_memory)
            prompt_text = self.prompts["extractFromMemory"].invoke(prompt_input).text
            
            messages = [
                {"role": "system", "content": PROMPT_CONFIGS["extractFromMemory"].system_message},
                {"role": "user", "content": prompt_text}
            ]
            
            output = await self._call_openai_optimized("extractFromMemory", messages)
            
            # Parse comma-separated terms
            if output.strip():
                terms = [s.strip() for s in output.split(",") if s.strip()]
                return terms
            return []
            
        except Exception as e:
            return []  # Return empty list on error

    async def optimize_textual(self, question: str, conversation_memory: str = "") -> str:
        """
        Async version of textual optimization with caching
        
        Args:
            question: User's question
            conversation_memory: Formatted conversation memory
            
        Returns:
            str: Optimized text for textual search
        """
        try:
            prompt_input = self.create_prompt_input(question, conversation_memory=conversation_memory)
            prompt_text = self.prompts["optimizeTextual"].invoke(prompt_input).text
            
            messages = [
                {"role": "system", "content": PROMPT_CONFIGS["optimizeTextual"].system_message},
                {"role": "user", "content": prompt_text}
            ]
            
            return await self._call_openai_optimized("optimizeTextual", messages)
            
        except Exception as e:
            # Fallback to original question if optimization fails
            return question

    async def generate_answer(self, question: str, chunks: str, conversation_memory: str = "") -> str:
        """
        Async version of answer generation with caching and chunk length management
        
        Args:
            question: User's original question
            chunks: Formatted chunks from Elasticsearch
            conversation_memory: Formatted conversation memory
            
        Returns:
            str: Final answer
        """
        try:
            # Intelligent chunk truncation to avoid token limits
            max_chunk_length = 15000  # Leave room for question and memory
            if len(chunks) > max_chunk_length:
                # Truncate but try to keep complete chunks
                chunk_sections = chunks.split('\n\n')
                truncated_chunks = []
                current_length = 0
                
                for chunk in chunk_sections:
                    if current_length + len(chunk) <= max_chunk_length:
                        truncated_chunks.append(chunk)
                        current_length += len(chunk)
                    else:
                        break
                
                chunks = '\n\n'.join(truncated_chunks)
                if len(chunks) > max_chunk_length:
                    chunks = chunks[:max_chunk_length] + "..."
            
            prompt_input = self.create_prompt_input(question, chunks=chunks, conversation_memory=conversation_memory)
            prompt_text = self.prompts["answer"].invoke(prompt_input).text
            
            messages = [
                {"role": "system", "content": PROMPT_CONFIGS["answer"].system_message},
                {"role": "user", "content": prompt_text}
            ]
            
            return await self._call_openai_optimized("answer", messages, conversation_memory=conversation_memory)
            
        except Exception as e:
            raise Exception(f"Answer generation failed: {e}")

    async def generate_answer_stream(
        self, 
        question: str, 
        chunks: str, 
        conversation_memory: str = "",
        sse_manager=None,
        session_id: str = None
    ) -> AsyncGenerator[str, None]:
        """
        Stream answer generation with real-time token output
        
        Args:
            question: User's original question
            chunks: Formatted chunks from Elasticsearch
            conversation_memory: Formatted conversation memory
            sse_manager: SSE manager for real-time updates
            session_id: Session ID for SSE updates
            
        Yields:
            str: Individual tokens as they're generated
        """
        try:
            # Intelligent chunk truncation to avoid token limits
            max_chunk_length = 15000  # Leave room for question and memory
            if len(chunks) > max_chunk_length:
                # Truncate but try to keep complete chunks
                chunk_sections = chunks.split('\n\n')
                truncated_chunks = []
                current_length = 0
                
                for chunk in chunk_sections:
                    if current_length + len(chunk) <= max_chunk_length:
                        truncated_chunks.append(chunk)
                        current_length += len(chunk)
                    else:
                        break
                
                chunks = '\n\n'.join(truncated_chunks)
                if len(chunks) > max_chunk_length:
                    chunks = chunks[:max_chunk_length] + "..."
            
            # Prepare prompt
            prompt_input = self.create_prompt_input(question, chunks=chunks, conversation_memory=conversation_memory)
            prompt_text = self.prompts["answer"].invoke(prompt_input).text
            
            config = PROMPT_CONFIGS["answer"]
            messages = [
                {"role": "system", "content": config.system_message},
                {"role": "user", "content": prompt_text}
            ]
            
            # Use streaming OpenAI API
            response = await self.client.chat.completions.create(
                model=OPENAI_MODEL_DEFAULT,
                messages=messages,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                stream=True
            )
            
            # Stream tokens
            async for chunk in response:
                if chunk.choices[0].delta.content is not None:
                    token = chunk.choices[0].delta.content
                    
                    # Send token via SSE if available
                    if sse_manager and session_id:
                        sse_manager.send_token(session_id, token)
                    
                    yield token
                    
        except Exception as e:
            error_msg = f"Streaming answer generation failed: {e}"
            if sse_manager and session_id:
                sse_manager.send_error(session_id, error_msg)
            raise Exception(error_msg)

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics"""
        total_requests = self.cache_stats["hits"] + self.cache_stats["misses"]
        hit_rate = (self.cache_stats["hits"] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "cache_entries": len(self.cache),
            "total_requests": total_requests,
            "cache_hits": self.cache_stats["hits"],
            "cache_misses": self.cache_stats["misses"],
            "expired_entries": self.cache_stats["expired"],
            "hit_rate_percent": round(hit_rate, 2),
            "top_cached_prompts": [
                {
                    "key": key[:8] + "...",
                    "hits": entry.hits,
                    "age_minutes": (datetime.now() - entry.created).total_seconds() / 60
                }
                for key, entry in sorted(
                    self.cache.items(), 
                    key=lambda x: x[1].hits, 
                    reverse=True
                )[:5]
            ]
        }

    def clear_cache(self, older_than_hours: Optional[int] = None):
        """Clear cache entries, optionally only older than specified hours"""
        if older_than_hours is None:
            self.cache.clear()
            self.cache_stats = {"hits": 0, "misses": 0, "expired": 0}
        else:
            cutoff = datetime.now() - timedelta(hours=older_than_hours)
            keys_to_remove = [
                key for key, entry in self.cache.items()
                if entry.created < cutoff
            ]
            for key in keys_to_remove:
                del self.cache[key] 