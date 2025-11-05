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
        r'[<>]',                        # Basic angle brackets (tags) blocked; quotes allowed
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
        
        # Normalize whitespace BEFORE character validation to allow newlines/tabs by collapsing them
        sanitized = question.strip()
        sanitized = re.sub(r'\s+', ' ', sanitized)

        # Character validation - allow nearly all printable Unicode except angle brackets and control chars
        # By validating the normalized string, inputs with newlines (e.g. multi-line questions) are accepted
        allowed_pattern = r'^[^\x00-\x1F\x7F<>]+$'
        if not re.match(allowed_pattern, sanitized):
            return ValidationResult(False, "Spørsmål inneholder ikke-tillatte spesialtegn")
        
        return ValidationResult(True, sanitized_input=sanitized)
    
    @staticmethod
    def validate_standard_numbers(standards: List[str]) -> ValidationResult:
        """Validate extracted standard numbers with improved pattern matching"""
        if not standards or not isinstance(standards, list):
            return ValidationResult(True, sanitized_input=[])
        
        sanitized_standards = []
        # FIXED: Improved regex to handle multi-part prefixes (NS-EN, EN ISO, ISO/IEC), spaces/hyphens, and suffixes
        # Examples matched: "NS-EN 13141-8:2006", "EN 1991-1-4", "ISO/IEC 27001:2013", "NS 11001-1", "EN ISO 1461"
        # Prefix: 1-4 segments of 1-5 letters separated by space, hyphen or slash (e.g. NS-EN, EN ISO, ISO/IEC)
        # Number part: alphanumeric with hyphens (e.g. 13141-8, 1991-1-4)
        # Optional suffix: :YEAR or +A1 etc.
        standard_pattern = r'^[A-Z]{1,5}(?:[\s/\-][A-Z]{1,5}){0,3}\s+[0-9A-Z\-]{1,20}(?:[:\+][0-9A-Z\-]{1,20})?$'
        
        for std in standards:
            if not isinstance(std, str):
                continue
            
            std_clean = std.strip().upper()
            if len(std_clean) > 50:  # Reasonable limit
                continue
            
            if re.match(standard_pattern, std_clean):
                sanitized_standards.append(std_clean)
        
        return ValidationResult(True, sanitized_input=sanitized_standards)

    @staticmethod
    def extract_standards_from_text(text: str) -> List[str]:
        """Extract likely standard numbers from arbitrary text using the same pattern."""
        if not text or not isinstance(text, str):
            return []
        pattern = re.compile(r'[A-Z]{1,5}(?:[\s/\-][A-Z]{1,5}){0,3}\s+[0-9A-Z\-]{1,20}(?:[:\+][0-9A-Z\-]{1,20})?')
        matches = pattern.findall(text.upper())
        # Deduplicate preserving order
        seen = set()
        result: List[str] = []
        for m in matches:
            if m not in seen and len(m) <= 50:
                seen.add(m)
                result.append(m)
        return result

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
                memory_terms = await self.prompt_manager.extract_from_memory(sanitized_question, conversation_memory)
                if isinstance(memory_terms, str):
                    memory_terms = [s.strip() for s in memory_terms.split(",") if s.strip()]
                elif not isinstance(memory_terms, list):
                    memory_terms = []
                
                if not memory_terms or len(memory_terms) == 0:
                    debug_output.append(f"⚠️ Memory extraction returned empty - falling back to textual search")
                    if debug:
                        print(f"⚠️ Memory extraction failed: {memory_terms}")
                        print(f"   Conversation memory: '{conversation_memory[:100]}...'")
                    analysis = "without"
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
                if isinstance(standard_numbers, str):
                    standard_numbers = [s.strip() for s in standard_numbers.split(",") if s.strip()]
                elif not isinstance(standard_numbers, list):
                    standard_numbers = []
                
                # Fallback: if none extracted from current question and route is likely including,
                # attempt to extract from conversation memory
                if (not standard_numbers or len(standard_numbers) == 0) and analysis.lower() == "including":
                    mem_candidates = self.validator.extract_standards_from_text(conversation_memory)
                    if debug:
                        print(f"🔎 Fallback extracted from memory: {mem_candidates}")
                    if mem_candidates:
                        # validate and use
                        mem_val = self.validator.validate_standard_numbers(mem_candidates)
                        if mem_val.sanitized_input:
                            standard_numbers = mem_val.sanitized_input
                            debug_output.append(f"✓ Using standards from memory: {standard_numbers}")
                
                memory_terms = []
                result["memory_terms"] = []
                debug_output.append(f"✓ Extracted {len(standard_numbers)} standard number(s): {standard_numbers}")
            
            # Validate extracted terms (only if memory route is still active)
            if analysis.lower() == "memory":
                validation_result = self.validator.validate_standard_numbers(memory_terms)
                if not validation_result.is_valid:
                    debug_output.append(f"⚠️ Memory terms validation failed - falling back to textual search")
                    if debug:
                        print(f"⚠️ Memory validation failed: {validation_result.error_message}")
                    analysis = "without"
                    result["memory_terms"] = []
                    result["memory_fallback"] = True
                    debug_output.append(f"✓ Switched to textual route due to memory validation failure")
                else:
                    sanitized_filter_terms = validation_result.sanitized_input
                    result["memory_terms"] = sanitized_filter_terms
            elif analysis.lower() != "memory":
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
                # Robustly determine standards to filter by
                candidate_standards = result.get("standard_numbers", [])
                if not candidate_standards:
                    candidate_standards = standard_numbers if 'standard_numbers' in locals() else []

                validation_again = self.validator.validate_standard_numbers(candidate_standards)
                sanitized_list = validation_again.sanitized_input if validation_again and validation_again.sanitized_input is not None else []

                if not sanitized_list:
                    debug_output.append("⚠️ No valid standards for filter query - falling back to textual search")
                    optimized_text = await self.prompt_manager.optimize_textual(sanitized_question, conversation_memory)
                    result["query_object"] = self.query_builder.build_textual_query(
                        optimized_text,
                        result["embeddings"],
                        debug
                    )
                    route = "without"
                    result["route_taken"] = route
                else:
                    result["standard_numbers"] = sanitized_list
                    result["query_object"] = self.query_builder.build_filter_query(
                        sanitized_list,
                        sanitized_question,
                        result["embeddings"],
                        debug
                    )
                    debug_output.append(f"✓ Built filter query for {len(result['standard_numbers'])} standard(s): {result['standard_numbers']}")
                
            elif route == "without":
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
            # Fallback: if including route yielded zero hits, retry with textual query
            if route == "including" and (not hits or len(hits) == 0):
                debug_output.append("⚠️ Including returned 0 hits - retrying with textual query fallback")
                optimized_text = await self.prompt_manager.optimize_textual(sanitized_question, conversation_memory)
                result["query_object"] = self.query_builder.build_textual_query(
                    optimized_text,
                    result["embeddings"],
                    debug
                )
                elasticsearch_response = self.elasticsearch_client.search(result["query_object"], debug)
                result["elasticsearch_response"] = elasticsearch_response
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
            
            answer = await self.prompt_manager.generate_answer(sanitized_question, chunks, conversation_memory)
            result["answer"] = answer
            
            debug_output.append(f"✓ Final answer generated ({len(answer)} characters)")
            
            processing_time = time.time() - start_time
            self.performance_stats["total_queries"] += 1
            self.performance_stats["avg_processing_time"] = (
                (self.performance_stats["avg_processing_time"] * (self.performance_stats["total_queries"] - 1) + processing_time)
                / self.performance_stats["total_queries"]
            )
            
            result.update({
                "processing_time": processing_time,
                "debug": "\n".join(debug_output) if debug else "",
                "success": True,
                "cache_stats": self.prompt_manager.get_cache_stats(),
                "elasticsearch_stats": self.elasticsearch_client.get_cache_stats(),
                "token_config": {
                    "max_tokens_configured": 4000,
                    "temperature_configured": 0.0,
                    "model_used": "gpt-4o",
                    "token_optimization": "MAXIMUM",
                    "temperature_mode": "DETERMINISTIC"
                }
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

    async def process_query_with_sse(self, question: str, conversation_memory: str = "0", session_id: str = None, debug: bool = True) -> Dict[str, Any]:
        """
        Process query med SSE progress updates
        """
        # Import lokalt for å unngå sirkulære imports
        try:
            from src.sse_manager import sse_manager, ProgressStage
        except ImportError as e:
            self.logger.error(f"Failed to import sse_manager: {e}")
            return await self.process_query(question, conversation_memory, debug)
        
        start_time = time.time()
        result = {"answer": "Kunne ikke generere svar"}
        
        try:
            if session_id:
                sse_manager.send_progress(session_id, ProgressStage.STARTED, "Starter behandling av spørsmål...", 5, "🚀")
            
            if session_id:
                sse_manager.send_progress(session_id, ProgressStage.VALIDATION, "Validerer inndata...", 10, "🔒")
            
            validation_result = self.validator.validate_question(question)
            if not validation_result.is_valid:
                if session_id:
                    sse_manager.send_error(session_id, validation_result.error_message)
                return {"answer": validation_result.error_message, "error": True}
            
            sanitized_question = validation_result.sanitized_input
            
            if session_id:
                sse_manager.send_progress(session_id, ProgressStage.ANALYSIS, "Analyserer spørsmål...", 15, "🔍")
            
            optimization_task = self.prompt_manager.optimize_semantic(sanitized_question, conversation_memory)
            analysis_task = self.prompt_manager.analyze_question(sanitized_question, conversation_memory)
            
            optimized, analysis = await asyncio.gather(optimization_task, analysis_task)
            result["optimized"] = optimized
            result["analysis"] = analysis
            
            if session_id:
                sse_manager.send_progress(session_id, ProgressStage.EXTRACTION, "Trekker ut standarder...", 25, "📊")
            
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

                if (not standard_numbers or len(standard_numbers) == 0) and analysis.lower() == "including":
                    mem_candidates = self.validator.extract_standards_from_text(conversation_memory)
                    if mem_candidates:
                        mem_val = self.validator.validate_standard_numbers(mem_candidates)
                        if mem_val.sanitized_input:
                            standard_numbers = mem_val.sanitized_input
                            if session_id:
                                sse_manager.send_progress(session_id, ProgressStage.EXTRACTION, f"Bruker minne-standarder: {', '.join(standard_numbers)}", 28, "🧠")
                
                memory_terms = []
                result["memory_terms"] = []
                
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
            
            if session_id:
                sse_manager.send_progress(session_id, ProgressStage.ROUTING, "Velger søkestrategi...", 35, "🛣️")
            
            if session_id:
                sse_manager.send_progress(session_id, ProgressStage.SEARCH, "Genererer embeddings...", 45, "🧮")
            
            embeddings = self.elasticsearch_client.get_embeddings_from_api(optimized, debug)
            if not embeddings:
                error_msg = "Kunne ikke generere embeddings"
                if session_id:
                    sse_manager.send_error(session_id, error_msg)
                return {"answer": error_msg, "error": True}
            result["embeddings"] = embeddings
            
            if session_id:
                sse_manager.send_progress(session_id, ProgressStage.SEARCH, "Bygger søkespørring...", 55, "🔧")
            
            if route == "memory":
                query_object = self.query_builder.build_memory_query(
                    result["memory_terms"], 
                    sanitized_question, 
                    embeddings, 
                    debug
                )
            elif route == "including":
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
            
            if session_id:
                self.logger.info(f"📡 Sending search progress to session {session_id}")
                sse_manager.send_progress(session_id, ProgressStage.SEARCH, "Søker i standarddatabase...", 65, "🔎")
                sse_manager.send_progress(session_id, ProgressStage.ROUTING, "Søkestrategi valgt!", 80, "🛣️")
            
            elasticsearch_response = self.elasticsearch_client.search(query_object, debug)
            if not elasticsearch_response:
                error_msg = "Elasticsearch søk feilet"
                if session_id:
                    sse_manager.send_error(session_id, error_msg)
                return {"answer": error_msg, "error": True}
            
            result["elasticsearch_response"] = elasticsearch_response
            result["standard_numbers"] = standard_numbers
            
            if session_id:
                sse_manager.send_progress(session_id, ProgressStage.SEARCH, "Formaterer søkeresultater...", 75, "📄")
            
            chunks = self.elasticsearch_client.format_chunks(elasticsearch_response, debug)
            result["chunks"] = chunks
            
            if session_id:
                sse_manager.send_progress(session_id, ProgressStage.ANSWER_GENERATION, "Genererer svar...", 100, "✨")
            
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
                answer = ''.join(answer_tokens)
            except Exception:
                answer = await self.prompt_manager.generate_answer(
                    sanitized_question, 
                    chunks, 
                    conversation_memory
                )
            
            result["answer"] = answer
            
            if session_id:
                sse_manager.send_final_answer(session_id, answer)
            
            result["processing_time"] = time.time() - start_time
            result["success"] = True
            
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
        """
        health = {
            "elasticsearch": False,
            "prompts": False,
            "query_builders": False
        }
        
        try:
            health["elasticsearch"] = self.elasticsearch_client.health_check(debug)
            try:
                test_prompt = self.prompt_manager.prompts.get("analysis")
                health["prompts"] = test_prompt is not None
            except Exception:
                health["prompts"] = False
            
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