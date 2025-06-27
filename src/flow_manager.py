"""
Main flow manager for StandardGPT
"""

from typing import Dict, Any, Optional, List, Tuple
from src.prompt_manager import PromptManager
from src.query_builders import QueryObjectBuilder
from src.elasticsearch_client import ElasticsearchClient
from src.debug_utils import (
    log_step_start,
    log_step_end, 
    log_error,
    debug_print,
    log_routing_decision,
    format_summary
)
import os
import re
import json
import time
import logging
from dataclasses import dataclass
import asyncio

@dataclass
class ValidationResult:
    """Result of input validation"""
    is_valid: bool
    error_message: Optional[str] = None
    sanitized_input: Optional[str] = None

class InputValidator:
    """Comprehensive input validation for StandardGPT"""
    
    # Security patterns to detect potential attacks
    DANGEROUS_PATTERNS = [
        r'<script[^>]*>.*?</script>',  # XSS attempts
        r'javascript:',                # JavaScript injection
        r'data:text/html',            # Data URI attacks
        r'vbscript:',                 # VBScript injection
        r'on\w+\s*=',                 # Event handlers
        r'eval\s*\(',                 # Code evaluation
        r'exec\s*\(',                 # Code execution
        r'import\s+',                 # Python imports
        r'__\w+__',                   # Python dunder methods
        r'\.\./',                     # Path traversal
        r'[<>"\']',                   # Basic HTML/SQL chars
    ]
    
    @staticmethod
    def validate_question(question: str) -> ValidationResult:
        """Validate and sanitize user question"""
        if not question or not isinstance(question, str):
            return ValidationResult(False, "Spørsmål må være en ikke-tom tekst")
        
        # Length validation
        if len(question.strip()) < 3:
            return ValidationResult(False, "Spørsmål må være minst 3 tegn langt")
        
        if len(question) > 1000:
            return ValidationResult(False, "Spørsmål kan ikke være lengre enn 1000 tegn")
        
        # Security validation
        question_lower = question.lower()
        for pattern in InputValidator.DANGEROUS_PATTERNS:
            if re.search(pattern, question_lower, re.IGNORECASE):
                return ValidationResult(False, "Spørsmål inneholder ikke-tillatte tegn eller mønstre")
        
        # Character validation - allow Norwegian characters
        allowed_pattern = r'^[a-zA-ZæøåÆØÅ0-9\s\-\.\,\?\!\:\;\(\)\[\]\/\+\*\=\%\&\#\@\_\~\`\^\$\|\\]*$'
        if not re.match(allowed_pattern, question):
            return ValidationResult(False, "Spørsmål inneholder ikke-tillatte spesialtegn")
        
        # Sanitize input
        sanitized = question.strip()
        sanitized = re.sub(r'\s+', ' ', sanitized)  # Normalize whitespace
        
        return ValidationResult(True, sanitized_input=sanitized)
    
    @staticmethod
    def validate_standard_numbers(standards: List[str]) -> ValidationResult:
        """Validate extracted standard numbers with improved pattern matching"""
        if not standards or not isinstance(standards, list):
            return ValidationResult(True, sanitized_input=[])
        
        sanitized_standards = []
        # FIXED: Improved regex to handle standards like NS 3457-7, EN 1991-1-4, etc.
        # Pattern breakdown:
        # ^[A-Z]{1,10}        - Prefix letters (NS, ISO, EN, etc.)
        # [\s\-]?             - Optional space or hyphen separator
        # [0-9A-Z\-]{1,15}    - Main number part (can include hyphens and letters)
        # (?:[\:\+][0-9A-Z\-]{1,20})? - Optional suffix like :2018 or +A1
        standard_pattern = r'^[A-Z]{1,10}[\s\-]?[0-9A-Z\-]{1,15}(?:[\:\+][0-9A-Z\-]{1,20})?$'
        
        for std in standards:
            if not isinstance(std, str):
                continue
            
            std_clean = std.strip().upper()
            if len(std_clean) > 50:  # Reasonable limit
                continue
            
            if re.match(standard_pattern, std_clean):
                sanitized_standards.append(std_clean)
        
        return ValidationResult(True, sanitized_input=sanitized_standards)

class FlowManager:
    """Main flow manager for StandardGPT query processing"""
    
    def __init__(self):
        """Initialize FlowManager with optimized components"""
        self.prompt_manager = PromptManager()
        self.query_builder = QueryObjectBuilder()
        self.elasticsearch_client = ElasticsearchClient()
        self.validator = InputValidator()
        self.logger = logging.getLogger(__name__)
        
        # Performance tracking
        self.performance_stats = {
            "total_queries": 0,
            "avg_processing_time": 0,
            "cache_hit_rate": 0
        }
    
    async def process_query(self, question: str, conversation_memory: str = "0", debug: bool = True) -> Dict[str, Any]:
        """
        Enhanced query processing with intelligent optimization and caching
        
        Args:
            question: User's question
            conversation_memory: Formatted conversation memory
            debug: Enable debug logging
            
        Returns:
            dict: Complete processing result with answer and metadata
        """
        start_time = time.time()
        result = {}
        debug_output = []
        
        try:
            # Step 0: Input Validation
            if debug:
                print(f"\n🔒 DEBUG - STEG 0: Input Validation - START:")
                print("=" * 50)
                print(f"Input: {question[:100]}{'...' if len(question) > 100 else ''}")
                print(f"Memory: {conversation_memory[:100]}{'...' if len(conversation_memory) > 100 else ''}")
                print("=" * 50)
            
            validation_result = self.validator.validate_question(question)
            if not validation_result.is_valid:
                error_msg = f"Input validation failed: {validation_result.error_message}"
                self.logger.warning(f"Invalid input rejected: {error_msg}")
                
                if debug:
                    print(f"\n🔒 DEBUG - STEG 0: Input Validation - FAILED:")
                    print("=" * 50)
                    print(f"❌ {validation_result.error_message}")
                    print("=" * 50)
                
                return {
                    "answer": validation_result.error_message,
                    "error": error_msg,
                    "processing_time": time.time() - start_time,
                    "debug": "\n".join(debug_output) if debug else "",
                    "security_sanitized": True
                }
            
            sanitized_question = validation_result.sanitized_input
            
            if debug:
                print(f"\n🔒 DEBUG - STEG 0: Input Validation - OUTPUT:")
                print("=" * 50)
                print(f"✅ Input validated and sanitized")
                print(f"Original length: {len(question)}, Sanitized length: {len(sanitized_question)}")
                print("=" * 50)
            
            # PHASE 1: Parallel optimization and analysis (OPTIMIZED WITH CACHING)
            debug_output.append("\n=== PARALLEL OPTIMIZATION & ANALYSIS PHASE ===")
            
            # Use the new async prompt manager with intelligent caching
            optimization_task = self.prompt_manager.optimize_semantic(sanitized_question, conversation_memory)
            analysis_task = self.prompt_manager.analyze_question(sanitized_question, conversation_memory)
            
            optimized, analysis = await asyncio.gather(optimization_task, analysis_task)
            
            debug_output.append(f"✓ Semantic optimization: {optimized}")
            debug_output.append(f"✓ Question analysis: {analysis}")
            result["optimized"] = optimized
            result["analysis"] = analysis
            
            # PHASE 2: Extract terms based on analysis (OPTIMIZED)
            debug_output.append("\n=== EXTRACTION PHASE (POST-ANALYSIS) ===")
            
            if analysis.lower() == "memory":
                # Memory route - extract from memory context
                memory_terms = await self.prompt_manager.extract_from_memory(sanitized_question, conversation_memory)
                
                # Enhanced memory handling - check if extraction was successful
                if isinstance(memory_terms, str):
                    memory_terms = [s.strip() for s in memory_terms.split(",") if s.strip()]
                elif not isinstance(memory_terms, list):
                    memory_terms = []
                
                # CRITICAL: If memory extraction fails or returns empty, fall back to textual search
                if not memory_terms or len(memory_terms) == 0:
                    debug_output.append(f"⚠️ Memory extraction returned empty - falling back to textual search")
                    if debug:
                        print(f"⚠️ Memory extraction failed: {memory_terms}")
                        print(f"   Conversation memory: '{conversation_memory[:100]}...'")
                    analysis = "without"  # Override analysis to use textual search
                    # Don't set route here yet - it will be set later in routing phase
                    standard_numbers = []
                    result["memory_terms"] = []
                    result["memory_fallback"] = True
                    debug_output.append(f"✓ Switched to textual route due to empty memory extraction")
                else:
                    standard_numbers = []
                    result["memory_terms"] = memory_terms
                    debug_output.append(f"✓ Extracted {len(memory_terms)} term(s) from memory: {memory_terms}")
            else:
                # Standard routes - extract standard numbers
                standard_numbers = await self.prompt_manager.extract_standard_numbers(sanitized_question)
                
                # Handle string vs list response from extraction
                if isinstance(standard_numbers, str):
                    standard_numbers = [s.strip() for s in standard_numbers.split(",") if s.strip()]
                elif not isinstance(standard_numbers, list):
                    standard_numbers = []
                
                memory_terms = []
                result["memory_terms"] = []
                debug_output.append(f"✓ Extracted {len(standard_numbers)} standard number(s): {standard_numbers}")
            
            # Validate extracted terms (only if memory route is still active)
            if analysis.lower() == "memory":  # Only validate if still memory analysis
                validation_result = self.validator.validate_standard_numbers(memory_terms)
                if not validation_result.is_valid:
                    debug_output.append(f"⚠️ Memory terms validation failed - falling back to textual search")
                    if debug:
                        print(f"⚠️ Memory validation failed: {validation_result.error_message}")
                    # Fall back to textual search instead of failing
                    analysis = "without"
                    result["memory_terms"] = []
                    result["memory_fallback"] = True
                    debug_output.append(f"✓ Switched to textual route due to memory validation failure")
                else:
                    sanitized_filter_terms = validation_result.sanitized_input
                    result["memory_terms"] = sanitized_filter_terms
            elif analysis.lower() != "memory":  # Standard number validation
                validation_result = self.validator.validate_standard_numbers(standard_numbers)
                if not validation_result.is_valid:
                    error_msg = f"Standard validation failed: {validation_result.error_message}"
                    self.logger.warning(f"Invalid standard rejected: {error_msg}")
                    return {
                        "answer": "Beklager, det oppstod en feil under behandling av standardene. Vennligst prøv igjen senere.",
                        "error": error_msg,
                        "processing_time": time.time() - start_time,
                        "debug": "\n".join(debug_output) if debug else "",
                        "security_sanitized": True
                    }
                sanitized_standard_numbers = validation_result.sanitized_input
                result["standard_numbers"] = sanitized_standard_numbers
            
            # PHASE 3: Intelligent routing (updated to handle memory fallbacks)
            if debug:
                print(f"\n🛤️ DEBUG - ROUTING DECISION:")
                print(f"Analysis result: '{analysis}'")
                print(f"Memory terms: {result.get('memory_terms', [])}")
                print(f"Standard numbers: {standard_numbers}")
                print(f"Available routes: memory, including, personal, without")
            
            # Re-evaluate route based on potentially updated analysis
            if analysis.lower() == "memory" and result.get("memory_terms") and len(result.get("memory_terms")) > 0:
                route = "memory"
                debug_output.append(f"✓ Route: MEMORY - Using terms from conversation: {result['memory_terms']}")
            elif analysis.lower() == "including" and standard_numbers and len(standard_numbers) > 0:
                route = "including"
                debug_output.append(f"✓ Route: FILTER - Focusing on standard(s): {', '.join(result.get('standard_numbers', standard_numbers))}")
            elif "personal" in analysis.lower() or "personalhåndbok" in analysis.lower():
                route = "personal"
                debug_output.append("✓ Route: PERSONAL - Searching personal handbook")
            elif analysis.lower() == "without":
                route = "without"
                debug_output.append("✓ Route: TEXTUAL - General text search")
            else:
                route = "without"
                debug_output.append(f"⚠️ Route: FALLBACK TO TEXTUAL - Unexpected analysis: '{analysis}'")
                if debug:
                    print(f"⚠️ Unexpected analysis result: '{analysis}', falling back to 'without'")
            
            result["route_taken"] = route
            
            # Ensure standard_numbers is set for non-memory routes
            if route != "memory" and "standard_numbers" not in result:
                result["standard_numbers"] = sanitized_standard_numbers if 'sanitized_standard_numbers' in locals() else []
            
            # PHASE 4: Generate embeddings (OPTIMIZED WITH CACHING)
            embeddings = None
            debug_output.append("\n=== EMBEDDINGS PHASE ===")
            
            # Get embeddings for routes that use vector search
            if route in ["without", "personal", "including", "memory"]:
                try:
                    embeddings = self.elasticsearch_client.get_embeddings_from_api(optimized, debug)
                    if embeddings and len(embeddings) > 0:
                        debug_output.append(f"✅ Embeddings generated for '{route}' route: {len(embeddings)} dimensions")
                    else:
                        debug_output.append(f"⚠️ Embeddings returned empty for '{route}' route - continuing with text-only search")
                        embeddings = None
                except Exception as e:
                    debug_output.append(f"⚠️ Embeddings failed for '{route}' route: {str(e)} - continuing with text-only search")
                    embeddings = None
                    if debug:
                        print(f"⚠️ Embedding error: {e}")
            else:
                debug_output.append(f"✅ Skipping embeddings for '{route}' route (not needed)")
            
            result["embeddings"] = embeddings or []
            
            # PHASE 5: Build optimized query
            debug_output.append(f"\n=== QUERY BUILDING PHASE ===")
            
            if route == "memory":
                result["query_object"] = self.query_builder.build_memory_query(
                    result["memory_terms"], 
                    sanitized_question, 
                    result["embeddings"], 
                    debug
                )
                debug_output.append(f"✓ Built memory query for {len(result['memory_terms'])} term(s)")
                
            elif route == "including":
                result["query_object"] = self.query_builder.build_filter_query(
                    result["standard_numbers"], 
                    sanitized_question, 
                    result["embeddings"], 
                    debug
                )
                debug_output.append(f"✓ Built filter query for {len(result['standard_numbers'])} standard(s)")
                
            elif route == "without":
                # Use the optimized textual optimization with caching
                optimized_text = await self.prompt_manager.optimize_textual(sanitized_question, conversation_memory)
                result["query_object"] = self.query_builder.build_textual_query(
                    optimized_text, 
                    result["embeddings"], 
                    debug
                )
                debug_output.append(f"✓ Built textual query with optimized text: {optimized_text}")
                
            else:  # personal
                result["query_object"] = self.query_builder.build_personal_query(
                    sanitized_question, 
                    result["embeddings"], 
                    debug
                )
                debug_output.append("✓ Built personal handbook query")
            
            # Validate query object
            self.query_builder.validate_query_object(result["query_object"], route)
            
            # PHASE 6: Execute search (OPTIMIZED)
            debug_output.append("\n=== SEARCH PHASE ===")
            elasticsearch_response = self.elasticsearch_client.search(result["query_object"], debug)
            result["elasticsearch_response"] = elasticsearch_response
            
            # Format chunks with intelligent truncation
            chunks = self.elasticsearch_client.format_chunks(elasticsearch_response, debug)
            result["chunks"] = chunks
            
            hits = elasticsearch_response.get('hits', {}).get('hits', [])
            debug_output.append(f"✓ Search completed: {len(hits)} hits returned")
            
            # PHASE 7: Generate answer (OPTIMIZED WITH CACHING)
            debug_output.append("\n=== ANSWER GENERATION PHASE ===")
            
            if debug:
                print(f"\n🔍 DEBUG - CHUNKS BEFORE GENERATE_ANSWER:")
                print(f"   📏 Chunks length: {len(chunks):,} characters")
                if chunks:
                    first_100 = chunks[:100] if len(chunks) > 100 else chunks
                    print(f"   📄 First 100 chars: '{first_100}...'")
                print(f"\n🧠 DEBUG - CONVERSATION MEMORY BEFORE GENERATE_ANSWER:")
                print(f"   📏 Memory length: {len(conversation_memory):,} characters")
                print(f"   📄 Memory content: '{conversation_memory[:500]}{'...' if len(conversation_memory) > 500 else ''}'")
                print(f"   🔍 Memory is valid: {conversation_memory != '0' and len(conversation_memory.strip()) > 0}")
            
            # Use the optimized answer generation with intelligent chunk management
            answer = await self.prompt_manager.generate_answer(sanitized_question, chunks, conversation_memory)
            result["answer"] = answer
            
            debug_output.append(f"✓ Final answer generated ({len(answer)} characters)")
            
            # Update performance statistics
            processing_time = time.time() - start_time
            self.performance_stats["total_queries"] += 1
            self.performance_stats["avg_processing_time"] = (
                (self.performance_stats["avg_processing_time"] * (self.performance_stats["total_queries"] - 1) + processing_time)
                / self.performance_stats["total_queries"]
            )
            
            # PHASE 8: Prepare final result
            result.update({
                "processing_time": processing_time,
                "debug": "\n".join(debug_output) if debug else "",
                "success": True,
                "cache_stats": self.prompt_manager.get_cache_stats(),
                "elasticsearch_stats": self.elasticsearch_client.get_cache_stats()
            })
            
            return result
            
        except Exception as e:
            processing_time = time.time() - start_time
            error_message = str(e)
            
            self.logger.error(f"❌ Error processing query: {error_message}")
            
            return {
                "answer": f"Beklager, det oppstod en feil under behandling av spørsmålet: {error_message}",
                "error": error_message,
                "processing_time": processing_time,
                "debug": "\n".join(debug_output) if debug else "",
                "success": False
            }

    def get_comprehensive_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance and cache statistics"""
        prompt_stats = self.prompt_manager.get_cache_stats()
        es_stats = self.elasticsearch_client.get_cache_stats()
        
        return {
            "performance": self.performance_stats,
            "prompt_cache": prompt_stats,
            "elasticsearch": es_stats,
            "system_efficiency": {
                "avg_processing_time": self.performance_stats["avg_processing_time"],
                "prompt_cache_hit_rate": prompt_stats.get("hit_rate_percent", 0),
                "embedding_cache_utilization": es_stats.get("embedding_cache", {}).get("utilization_percent", 0)
            }
        }

    async def process_query_with_sse(self, question: str, conversation_memory: str = "0", session_id: str = None, debug: bool = True) -> Dict[str, Any]:
        """
        Process query med SSE progress updates
        
        Args:
            question: User's question
            conversation_memory: Formatted conversation memory string
            session_id: SSE session ID for progress updates
            debug: Enable debug output
            
        Returns:
            dict: Complete processing result with answer
        """
        # Import lokalt for å unngå sirkulære imports
        try:
            from src.sse_manager import sse_manager, ProgressStage
        except ImportError as e:
            self.logger.error(f"Failed to import sse_manager: {e}")
            # Fallback til vanlig processing uten SSE
            return await self.process_query(question, conversation_memory, debug)
        
        start_time = time.time()
        result = {"answer": "Kunne ikke generere svar"}
        
        try:
            # STEG 1: Start
            if session_id:
                sse_manager.send_progress(session_id, ProgressStage.STARTED, "Starter behandling av spørsmål...", 5, "🚀")
            
            # STEG 2: Validering
            if session_id:
                sse_manager.send_progress(session_id, ProgressStage.VALIDATION, "Validerer inndata...", 10, "🔒")
            
            validation_result = self.validator.validate_question(question)
            if not validation_result.is_valid:
                if session_id:
                    sse_manager.send_error(session_id, validation_result.error_message)
                return {"answer": validation_result.error_message, "error": True}
            
            sanitized_question = validation_result.sanitized_input
            
            # Mark validation completed
            if session_id:
                sse_manager.send_progress(session_id, ProgressStage.VALIDATION, "Inndata validert!", 100, "🔒")
            
            # STEG 3: Analyse
            if session_id:
                sse_manager.send_progress(session_id, ProgressStage.ANALYSIS, "Analyserer spørsmål...", 20, "🔍")
            
            optimization_task = self.prompt_manager.optimize_semantic(sanitized_question, conversation_memory)
            analysis_task = self.prompt_manager.analyze_question(sanitized_question, conversation_memory)
            
            optimized, analysis = await asyncio.gather(optimization_task, analysis_task)
            result["optimized"] = optimized
            result["analysis"] = analysis
            
            # Mark analysis completed
            if session_id:
                sse_manager.send_progress(session_id, ProgressStage.ANALYSIS, "Spørsmål analysert!", 100, "🔍")
            
            # STEG 4: Extraktion
            if session_id:
                sse_manager.send_progress(session_id, ProgressStage.EXTRACTION, "Trekker ut standarder...", 30, "📊")
            
            # Bruk eksisterende logikk fra process_query
            if analysis.lower() == "memory":
                memory_terms = await self.prompt_manager.extract_from_memory(sanitized_question, conversation_memory)
                standard_numbers = []
                result["memory_terms"] = memory_terms
                route = "memory"
            else:
                standard_numbers = await self.prompt_manager.extract_standard_numbers(sanitized_question)
                if isinstance(standard_numbers, str) and standard_numbers.strip():
                    standard_numbers = [s.strip() for s in standard_numbers.split(',') if s.strip()]
                elif not isinstance(standard_numbers, list):
                    standard_numbers = []
                memory_terms = []
                result["memory_terms"] = []
                
                # Determine route
                if analysis.lower() == "including" and standard_numbers and len(standard_numbers) > 0:
                    route = "including"
                elif "personal" in analysis.lower() or "personalhåndbok" in analysis.lower():
                    route = "personal"
                elif analysis.lower() == "without":
                    route = "without"
                else:
                    route = "without"
            
            result["extracted_standards"] = standard_numbers
            result["route_taken"] = route
            
            # STEG 5: Routing
            if session_id:
                sse_manager.send_progress(session_id, ProgressStage.ROUTING, f"Velger søkestrategi: {route}...", 40, "🛣️")
                # Mark extraction as completed
                sse_manager.send_progress(session_id, ProgressStage.EXTRACTION, "Standarder uttrukket!", 100, "📊")
            
            # STEG 6: Embeddings (nytt steg)
            if session_id:
                sse_manager.send_progress(session_id, ProgressStage.SEARCH, "Genererer embeddings...", 50, "🧮")
            
            # Generate embeddings
            embeddings = self.elasticsearch_client.get_embeddings_from_api(optimized, debug)
            if not embeddings:
                error_msg = "Kunne ikke generere embeddings"
                if session_id:
                    sse_manager.send_error(session_id, error_msg)
                return {"answer": error_msg, "error": True}
            result["embeddings"] = embeddings
            
            # STEG 7: Query Building (nytt steg)
            if session_id:
                sse_manager.send_progress(session_id, ProgressStage.SEARCH, "Bygger søkespørring...", 60, "🔧")
            
            # Build query based on route
            if route == "memory":
                query_object = self.query_builder.build_memory_query(
                    result["memory_terms"], 
                    sanitized_question, 
                    embeddings, 
                    debug
                )
            elif route == "including":
                # Validate standard numbers first
                validation_result = self.validator.validate_standard_numbers(standard_numbers)
                if not validation_result.is_valid:
                    error_msg = f"Standard validation failed: {validation_result.error_message}"
                    if session_id:
                        sse_manager.send_error(session_id, error_msg)
                    return {"answer": error_msg, "error": True}
                    
                query_object = self.query_builder.build_filter_query(
                    validation_result.sanitized_input, 
                    sanitized_question, 
                    embeddings, 
                    debug
                )
            elif route == "without":
                optimized_text = await self.prompt_manager.optimize_textual(sanitized_question, conversation_memory)
                query_object = self.query_builder.build_textual_query(
                    optimized_text, 
                    embeddings, 
                    debug
                )
            else:  # personal
                query_object = self.query_builder.build_personal_query(
                    sanitized_question, 
                    embeddings, 
                    debug
                )
            
            result["query_object"] = query_object
            
            # STEG 8: Elasticsearch Search (nytt steg)
            if session_id:
                sse_manager.send_progress(session_id, ProgressStage.SEARCH, "Søker i standarddatabase...", 70, "🔎")
                # Mark routing as completed
                sse_manager.send_progress(session_id, ProgressStage.ROUTING, "Søkestrategi valgt!", 100, "🛣️")
            
            # Execute search
            elasticsearch_response = self.elasticsearch_client.search(query_object, debug)
            if not elasticsearch_response:
                error_msg = "Elasticsearch søk feilet"
                if session_id:
                    sse_manager.send_error(session_id, error_msg)
                return {"answer": error_msg, "error": True}
            
            result["elasticsearch_response"] = elasticsearch_response
            result["standard_numbers"] = standard_numbers  # Add standard numbers to result
            
            # STEG 9: Format chunks (nytt steg)
            if session_id:
                sse_manager.send_progress(session_id, ProgressStage.SEARCH, "Formaterer søkeresultater...", 80, "📄")
            
            # Format chunks
            chunks = self.elasticsearch_client.format_chunks(elasticsearch_response, debug)
            result["chunks"] = chunks
            
            # Mark search completed
            if session_id:
                sse_manager.send_progress(session_id, ProgressStage.SEARCH, "Søk fullført!", 100, "🔎")
            
            # STEG 10: Svar generering
            if session_id:
                sse_manager.send_progress(session_id, ProgressStage.ANSWER_GENERATION, "Genererer svar...", 85, "✨")
            
            # Stream the answer generation with fallback - chunks is already defined above
            answer_tokens = []
            try:
                async for token in self.prompt_manager.generate_answer_stream(
                    sanitized_question, 
                    chunks, 
                    conversation_memory,
                    sse_manager,
                    session_id
                ):
                    answer_tokens.append(token)
                
                # Combine all tokens to get final answer
                answer = ''.join(answer_tokens)
                
            except Exception as streaming_error:
                # FALLBACK: If streaming fails, use regular answer generation
                self.logger.warning(f"Streaming answer generation failed, falling back to regular generation: {streaming_error}")
                if session_id:
                    sse_manager.send_progress(session_id, ProgressStage.ANSWER_GENERATION, "Streaming feilet, bruker vanlig generering...", 90, "⚠️")
                
                try:
                    answer = await self.prompt_manager.generate_answer(
                        sanitized_question, 
                        chunks, 
                        conversation_memory
                    )
                    self.logger.info(f"Fallback answer generation successful: {len(answer)} characters")
                except Exception as fallback_error:
                    # If both fail, return error message but DON'T set error flag
                    # This allows conversation memory to still be saved
                    answer = f"Det oppstod en teknisk feil under svargenerering. Prøv å spørre på nytt eller kontakt support hvis problemet vedvarer. (Feil: {str(fallback_error)})"
                    self.logger.error(f"Both streaming and fallback answer generation failed: {fallback_error}")
            
            result["answer"] = answer
            
            # STEG 11: Fullført
            if session_id:
                sse_manager.send_progress(session_id, ProgressStage.COMPLETE, "Svar generert!", 100, "✅")
                sse_manager.send_final_answer(session_id, answer)
            
            result["processing_time"] = time.time() - start_time
            result["success"] = True  # Mark as success even if streaming failed but we got an answer
            return result
            
        except Exception as e:
            error_msg = f"Feil under behandling: {str(e)}"
            self.logger.error(f"SSE processing error: {error_msg}", exc_info=True)
            if session_id:
                sse_manager.send_error(session_id, error_msg)
            return {"answer": error_msg, "error": True, "processing_time": time.time() - start_time}

    def health_check(self, debug: bool = True) -> Dict[str, bool]:
        """
        Check health of all system components
        
        Args:
            debug: Enable debug output
            
        Returns:
            dict: Health status of each component
        """
        health = {
            "elasticsearch": False,
            "prompts": False,
            "query_builders": False
        }
        
        try:
            # Check Elasticsearch
            health["elasticsearch"] = self.elasticsearch_client.health_check(debug)
            
            # Check prompts
            try:
                test_prompt = self.prompt_manager.prompts.get("analysis")
                health["prompts"] = test_prompt is not None
            except Exception:
                health["prompts"] = False
            
            # Check query builders
            try:
                health["query_builders"] = self.query_builder.query_objects is not None
            except Exception:
                health["query_builders"] = False
            
            if debug:
                for component, status in health.items():
                    debug_print("HealthCheck", f"{component}: {'OK' if status else 'FAILED'}")
            
        except Exception as e:
            log_error("HealthCheck", str(e), debug)
        
        return health 