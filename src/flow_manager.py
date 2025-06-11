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
        """Initialize all components"""
        self.prompt_manager = PromptManager()
        self.query_builder = QueryObjectBuilder()
        self.elasticsearch_client = ElasticsearchClient()
        self.validator = InputValidator()
        
        # Setup secure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('standardgpt.log', mode='a')
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    async def process_query(self, question: str, conversation_memory: str = "0", debug: bool = True) -> Dict[str, Any]:
        """
        Process query through the complete flow with multi-standard support and memory
        
        Args:
            question: User's question
            conversation_memory: Formatted conversation memory string
            debug: Enable debug output
            
        Returns:
            dict: Complete processing result with answer
        """
        start_time = time.time()
        result = {"answer": "Kunne ikke generere svar"}
        debug_output = []
        
        try:
            debug_output.append("=== StandardGPT Query Processing ===")
            debug_output.append(f"Question: {question}")
            debug_output.append(f"Memory: {conversation_memory[:100]}{'...' if len(conversation_memory) > 100 else ''}")
            
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
            
            # Use sanitized input
            sanitized_question = validation_result.sanitized_input
            
            if debug:
                print(f"\n🔒 DEBUG - STEG 0: Input Validation - OUTPUT:")
                print("=" * 50)
                print(f"✅ Input validated and sanitized")
                print(f"Original length: {len(question)}, Sanitized length: {len(sanitized_question)}")
                print("=" * 50)
            
            # 1. Parallel optimization and analysis (SAFE TO RUN TOGETHER)
            debug_output.append("\n=== PARALLEL OPTIMIZATION & ANALYSIS PHASE ===")
            
            # Run optimize_semantic and analyze_question in parallel - these are independent
            optimization_task = self.prompt_manager.optimize_semantic(sanitized_question, conversation_memory)
            analysis_task = self.prompt_manager.analyze_question(sanitized_question, conversation_memory)
            
            optimized, analysis = await asyncio.gather(optimization_task, analysis_task)
            
            debug_output.append(f"✓ Semantic optimization: {optimized}")
            debug_output.append(f"✓ Question analysis: {analysis}")
            result["optimized"] = optimized
            result["analysis"] = analysis
            
            # 3. Extract terms AFTER analysis determines the route (CRITICAL CONSTRAINT)
            debug_output.append("\n=== EXTRACTION PHASE (POST-ANALYSIS) ===")
            
            # Based on analysis, extract appropriate terms
            if analysis.lower() == "memory":
                # Extract terms from memory context
                memory_terms = await self.prompt_manager.extract_from_memory(sanitized_question, conversation_memory)
                standard_numbers = []
                result["memory_terms"] = memory_terms
                debug_output.append(f"✓ Extracted {len(memory_terms)} term(s) from memory: {memory_terms}")
            else:
                # Extract standard numbers normally
                standard_numbers = await self.prompt_manager.extract_standard_numbers(sanitized_question)
                if isinstance(standard_numbers, str) and standard_numbers.strip():
                    # Convert single standard to list for consistent handling
                    standard_numbers = [s.strip() for s in standard_numbers.split(',') if s.strip()]
                elif not isinstance(standard_numbers, list):
                    standard_numbers = []
                
                memory_terms = []
                result["memory_terms"] = []
                debug_output.append(f"✓ Extracted {len(standard_numbers)} standard number(s): {standard_numbers}")
            
            # Validate extracted terms
            if analysis.lower() == "memory":
                # Validate memory terms (reuse standard validation)
                validation_result = self.validator.validate_standard_numbers(memory_terms)
                if not validation_result.is_valid:
                    error_msg = f"Memory terms validation failed: {validation_result.error_message}"
                    self.logger.warning(f"Invalid memory terms rejected: {error_msg}")
                    return {
                        "answer": "Beklager, det oppstod en feil under behandling av samtaleminnet. Vennligst prøv igjen senere.",
                        "error": error_msg,
                        "processing_time": time.time() - start_time,
                        "debug": "\n".join(debug_output) if debug else "",
                        "security_sanitized": True
                    }
                sanitized_filter_terms = validation_result.sanitized_input
                result["memory_terms"] = sanitized_filter_terms
            else:
                # Validate standard numbers
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
            
            # 4. Routing decision based on analysis
            if debug:
                print(f"\n🛤️ DEBUG - ROUTING DECISION:")
                print(f"Analysis result: '{analysis}'")
                print(f"Available routes: memory, including, personal, without")
            
            if analysis.lower() == "memory":
                route = "memory"
                debug_output.append(f"✓ Route: MEMORY - Using terms from conversation: {result['memory_terms']}")
            elif analysis.lower() == "including" and standard_numbers and len(standard_numbers) > 0:
                route = "including"
                debug_output.append(f"✓ Route: FILTER - Focusing on standard(s): {', '.join(result['standard_numbers'])}")
            elif "personal" in analysis.lower() or "personalhåndbok" in analysis.lower():
                route = "personal"
                debug_output.append("✓ Route: PERSONAL - Searching personal handbook")
            elif analysis.lower() == "without":
                route = "without"
                debug_output.append("✓ Route: TEXTUAL - General text search")
            else:
                # Handle unexpected analysis results with fallback
                route = "without"
                debug_output.append(f"⚠️ Route: FALLBACK TO TEXTUAL - Unexpected analysis: '{analysis}'")
                if debug:
                    print(f"⚠️ Unexpected analysis result: '{analysis}', falling back to 'without'")
            
            result["route_taken"] = route
            
            # Ensure standard_numbers is set for non-memory routes
            if route != "memory" and "standard_numbers" not in result:
                result["standard_numbers"] = sanitized_standard_numbers if 'sanitized_standard_numbers' in locals() else []
            
            # 4.5. OPTIMIZED EMBEDDINGS - Only get if needed for this route
            embeddings = None
            debug_output.append("\n=== SMART EMBEDDINGS PHASE ===")
            
            # Only get embeddings for routes that actually use them
            if route in ["without", "personal"]:  # Memory and including use simple wildcard matching
                embeddings = self.elasticsearch_client.get_embeddings_from_api(optimized, debug)
                debug_output.append(f"✓ Embeddings retrieved for {route} route: {len(embeddings) if embeddings else 0} dimensions")
            else:
                debug_output.append(f"✓ Skipping embeddings for {route} route (uses wildcard matching)")
            
            result["embeddings"] = embeddings or []
            
            # 5. Build query based on route
            debug_output.append(f"\n=== QUERY BUILDING PHASE ===")
            
            if route == "memory":
                # Memory filter query (same as including but with memory terms)
                result["query_object"] = self.query_builder.build_memory_query(
                    result["memory_terms"], 
                    sanitized_question, 
                    result["embeddings"], 
                    debug
                )
                debug_output.append(f"✓ Built memory query for {len(result['memory_terms'])} term(s)")
                
            elif route == "including":
                # Multi-standard filter query
                result["query_object"] = self.query_builder.build_filter_query(
                    result["standard_numbers"], 
                    sanitized_question, 
                    result["embeddings"], 
                    debug
                )
                debug_output.append(f"✓ Built filter query for {len(result['standard_numbers'])} standard(s)")
                
            elif route == "without":
                # Textual search query
                optimized_text = await self.prompt_manager.optimize_textual(sanitized_question, conversation_memory)
                result["query_object"] = self.query_builder.build_textual_query(
                    optimized_text, 
                    result["embeddings"], 
                    debug
                )
                debug_output.append(f"✓ Built textual query with optimized text: {optimized_text}")
                
            else:  # personal
                # Personal handbook query
                result["query_object"] = self.query_builder.build_personal_query(
                    sanitized_question, 
                    result["embeddings"], 
                    debug
                )
                debug_output.append("✓ Built personal handbook query")
            
            # Validate query object
            self.query_builder.validate_query_object(result["query_object"], route)
            
            # 6. Execute Elasticsearch search
            debug_output.append("\n=== SEARCH PHASE ===")
            elasticsearch_response = self.elasticsearch_client.search(result["query_object"], debug)
            result["elasticsearch_response"] = elasticsearch_response
            
            # Format chunks from response
            chunks = self.elasticsearch_client.format_chunks(elasticsearch_response, debug)
            result["chunks"] = chunks
            
            # DEBUG: Check chunks immediately after format_chunks
            if debug:
                print(f"\n🔍 DEBUG - CHUNKS AFTER FORMAT_CHUNKS:")
                print(f"   📏 Chunks length: {len(chunks):,} characters")
                chunk_sections = chunks.split('\n\n')
                if chunk_sections:
                    first_chunk = chunk_sections[0]
                    
                    # Extract content correctly - handle multiline text
                    lines = first_chunk.split('\n')
                    content_started = False
                    content_lines = []
                    
                    for line in lines:
                        if line.startswith('Innhold: '):
                            content_started = True
                            content_lines.append(line[9:])  # Remove "Innhold: " prefix
                        elif content_started and line == '---':
                            break  # End of content
                        elif content_started:
                            content_lines.append(line)
                    
                    content = '\n'.join(content_lines)
                    print(f"   📄 First content length: {len(content)} chars")
                    print(f"   📄 First content: '{content[:100]}...'")
            
            hits = elasticsearch_response.get('hits', {}).get('hits', [])
            debug_output.append(f"✓ Search completed: {len(hits)} hits returned")
            debug_output.append(f"✓ Formatted {len(chunks)} chunks for answer generation")
            
            # Sample chunks for debugging
            for i, hit in enumerate(hits[:3]):
                source = hit.get("_source", {})
                score = hit.get("_score", 0)
                debug_output.append(f"  - Chunk {i+1}: Score={score:.2f}, Ref={source.get('reference', 'N/A')[:50]}...")
            
            # DEBUG: Check chunks just before generate_answer
            if debug:
                print(f"\n🔍 DEBUG - CHUNKS BEFORE GENERATE_ANSWER:")
                print(f"   📏 Chunks length: {len(chunks):,} characters")
                chunk_sections = chunks.split('\n\n')
                if chunk_sections:
                    first_chunk = chunk_sections[0]
                    
                    # Extract content correctly - handle multiline text
                    lines = first_chunk.split('\n')
                    content_started = False
                    content_lines = []
                    
                    for line in lines:
                        if line.startswith('Innhold: '):
                            content_started = True
                            content_lines.append(line[9:])  # Remove "Innhold: " prefix
                        elif content_started and line == '---':
                            break  # End of content
                        elif content_started:
                            content_lines.append(line)
                    
                    content = '\n'.join(content_lines)
                    print(f"   📄 First content length: {len(content)} chars")
                    print(f"   📄 First content: '{content[:100]}...'")
            
            # 7. Generate final answer
            debug_output.append("\n=== ANSWER GENERATION PHASE ===")
            answer = await self.prompt_manager.generate_answer(sanitized_question, chunks, conversation_memory)
            result["answer"] = answer or "Kunne ikke generere et fullstendig svar basert på tilgjengelig informasjon."
            
            debug_output.append(f"✓ Final answer generated ({len(result['answer'])} characters)")
            debug_output.append("\n=== PROCESSING COMPLETE ===")
            
            if debug:
                for line in debug_output:
                    print(line)
            
            return result
            
        except Exception as e:
            error_msg = f"Query processing failed: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return {
                "answer": "Beklager, det oppstod en feil under behandling av spørsmålet ditt. Vennligst prøv igjen senere.",
                "error": error_msg,
                "processing_time": time.time() - start_time
            }
    
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