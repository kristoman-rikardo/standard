"""
Prompt manager for StandardGPT
"""

import os
import json
import requests
import openai
from langchain.prompts import PromptTemplate
from src.config import OPENAI_MODEL, OPENAI_API_KEY, OPENAI_TEMPERATURE, OPENAI_MODEL_DEFAULT, OPENAI_MODEL_ANSWER
from src.debug_utils import log_step_start, log_step_end, log_error, debug_print
from typing import Dict, List, Tuple, Optional, AsyncGenerator
from pathlib import Path

class PromptManager:
    """Manages all prompt operations for the StandardGPT system"""
    
    def __init__(self):
        """Initialize the prompt manager with OpenAI client and load all prompts"""
        # Set up OpenAI client with hardcoded API key from config
        self.client = openai.OpenAI(api_key=OPENAI_API_KEY)
        self.model = OPENAI_MODEL
        self.prompts = self._load_all_prompts()
    
    def _call_openai(self, messages: List[Dict], temperature: float = OPENAI_TEMPERATURE, model: str = None) -> str:
        """
        Call OpenAI API with modern syntax
        
        Args:
            messages: List of message dicts for OpenAI
            temperature: Temperature for response generation (default from config)
            model: OpenAI model to use (defaults to OPENAI_MODEL_DEFAULT)
            
        Returns:
            str: Generated response content
        """
        if model is None:
            model = OPENAI_MODEL_DEFAULT
            
        # Set max_tokens to 8000 for all prompts consistently
        max_tokens = 8000
            
        try:
            if hasattr(self, '_debug_enabled') and self._debug_enabled:
                debug_print("OpenAI", f"Using model: {model} (max_tokens: {max_tokens})")
                
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            raise Exception(f"OpenAI API error: {e}")
    
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
    
    def execute_optimize_semantic(self, last_utterance, conversation_memory="", debug=True):
        """
        Execute the optimizeSemantic prompt
        
        Args:
            last_utterance (str): User's original question
            conversation_memory (str): Formatted conversation memory
            debug (bool): Enable debug logging
            
        Returns:
            str: Optimized question for semantic search
        """
        log_step_start(1, "OptimizeSemantic", f"{last_utterance} (Model: {OPENAI_MODEL_DEFAULT})", debug)
        
        try:
            prompt_input = self.create_prompt_input(last_utterance, conversation_memory=conversation_memory)
            prompt_text = self.prompts["optimizeSemantic"].invoke(prompt_input).text
            
            messages = [
                {"role": "system", "content": "You are a helpful assistant that optimizes questions for semantic search."},
                {"role": "user", "content": prompt_text}
            ]
            
            output = self._call_openai(messages, model=OPENAI_MODEL_DEFAULT)
            log_step_end(1, "OptimizeSemantic", output, debug)
            return output
            
        except Exception as e:
            log_error("OptimizeSemantic", str(e), debug)
            raise
    
    def execute_analysis(self, last_utterance, conversation_memory="", debug=True):
        """
        Execute the analysis prompt to determine routing
        
        Args:
            last_utterance (str): User's original question
            conversation_memory (str): Formatted conversation memory
            debug (bool): Enable debug logging
            
        Returns:
            str: Analysis result ("including", "without", "personal", or "memory")
        """
        log_step_start(3, "Analysis", f"{last_utterance} (Model: {OPENAI_MODEL_DEFAULT})", debug)
        
        try:
            prompt_input = self.create_prompt_input(last_utterance, conversation_memory=conversation_memory)
            prompt_text = self.prompts["analysis"].invoke(prompt_input).text
            
            if debug:
                print(f"\n🔍 DEBUG - ANALYSIS PROMPT:")
                print(f"Conversation memory: {conversation_memory[:200]}...")
                print(f"Prompt length: {len(prompt_text)} chars")
                print(f"Prompt preview: {prompt_text[:500]}...")
            
            messages = [
                {"role": "system", "content": "You are a routing system that analyzes questions and returns exactly one of: 'including', 'without', 'personal', or 'memory'."},
                {"role": "user", "content": prompt_text}
            ]
            
            output = self._call_openai(messages, model=OPENAI_MODEL_DEFAULT).lower().strip()
            
            # More aggressive cleaning of output
            output = output.strip('"\'`()[]{}.,!?;: \n\r\t')
            
            # Validate output
            valid_routes = ["including", "without", "personal", "memory"]
            if output not in valid_routes:
                if debug:
                    print(f"❌ Invalid analysis output: '{output}', defaulting to 'without'")
                    print(f"Valid routes are: {valid_routes}")
                output = "without"  # Safe fallback
            
            log_step_end(3, "Analysis", output, debug)
            return output
            
        except Exception as e:
            log_error("Analysis", str(e), debug)
            if debug:
                print(f"❌ Analysis failed, defaulting to 'without': {str(e)}")
            return "without"  # Safe fallback
    
    def execute_extract_standard(self, last_utterance, debug=True):
        """
        Execute the extractStandard prompt
        
        Args:
            last_utterance (str): User's original question
            debug (bool): Enable debug logging
            
        Returns:
            str: Extracted standard numbers (comma separated)
        """
        log_step_start("4a", "ExtractStandard", f"{last_utterance} (Model: {OPENAI_MODEL_DEFAULT})", debug)
        
        try:
            prompt_input = self.create_prompt_input(last_utterance)
            prompt_text = self.prompts["extractStandard"].invoke(prompt_input).text
            
            messages = [
                {"role": "system", "content": "You extract standard numbers from questions. Return only the standard numbers, comma separated."},
                {"role": "user", "content": prompt_text}
            ]
            
            output = self._call_openai(messages, model=OPENAI_MODEL_DEFAULT)
            log_step_end("4a", "ExtractStandard", output, debug)
            return output
            
        except Exception as e:
            log_error("ExtractStandard", str(e), debug)
            raise
    
    def execute_extract_from_memory(self, last_utterance, conversation_memory, debug=True):
        """
        Execute the extractFromMemory prompt with GPT-4o
        
        Args:
            last_utterance (str): User's original question
            conversation_memory (str): Formatted conversation memory
            debug (bool): Enable debug logging
            
        Returns:
            str: Extracted terms from memory context (comma separated)
        """
        log_step_start("4c", "ExtractFromMemory", f"{last_utterance[:50]}... (Model: {OPENAI_MODEL_DEFAULT})", debug)
        
        try:
            prompt_input = self.create_prompt_input(last_utterance, conversation_memory=conversation_memory)
            prompt_text = self.prompts["extractFromMemory"].invoke(prompt_input).text
            
            messages = [
                {"role": "system", "content": "You extract standard numbers from memory context. Return only the standard numbers, comma separated."},
                {"role": "user", "content": prompt_text}
            ]
            
            output = self._call_openai(messages, model=OPENAI_MODEL_DEFAULT)
            log_step_end("4c", "ExtractFromMemory", output, debug)
            return output
            
        except Exception as e:
            log_error("ExtractFromMemory", str(e), debug)
            raise
    
    def execute_optimize_textual(self, last_utterance, conversation_memory="", debug=True):
        """
        Execute the optimizeTextual prompt
        
        Args:
            last_utterance (str): User's original question
            conversation_memory (str): Formatted conversation memory
            debug (bool): Enable debug logging
            
        Returns:
            str: Optimized text for textual search
        """
        log_step_start("4b", "OptimizeTextual", f"{last_utterance[:50]}... (Model: {OPENAI_MODEL_DEFAULT})", debug)
        
        try:
            prompt_input = self.create_prompt_input(last_utterance, conversation_memory=conversation_memory)
            prompt_text = self.prompts["optimizeTextual"].invoke(prompt_input).text
            
            messages = [
                {"role": "system", "content": "You optimize questions for textual search by extracting key terms and concepts."},
                {"role": "user", "content": prompt_text}
            ]
            
            output = self._call_openai(messages, model=OPENAI_MODEL_DEFAULT)
            log_step_end("4b", "OptimizeTextual", output, debug)
            return output
            
        except Exception as e:
            log_error("OptimizeTextual", str(e), debug)
            raise
    
    def execute_answer(self, last_utterance, chunks, conversation_memory="", debug=True):
        """
        Execute the answer prompt to generate final response
        
        Args:
            last_utterance (str): User's original question
            chunks (str): Retrieved document chunks
            conversation_memory (str): Formatted conversation memory
            debug (bool): Enable debug logging
            
        Returns:
            str: Final answer
        """
        log_step_start(6, "Generate Answer", f"Question: {last_utterance[:50]}... (Model: {OPENAI_MODEL_ANSWER})", debug)
        
        try:
            prompt_input = self.create_prompt_input(last_utterance, chunks=chunks, conversation_memory=conversation_memory)
            prompt_text = self.prompts["answer"].invoke(prompt_input).text
            
            messages = [
                {"role": "system", "content": "You are a helpful assistant that answers questions based on provided document chunks. Answer in Norwegian."},
                {"role": "user", "content": prompt_text}
            ]
            
            output = self._call_openai(messages, model=OPENAI_MODEL_ANSWER)
            log_step_end(6, "Generate Answer", "Answer generated", debug)
            return output
            
        except Exception as e:
            log_error("Generate Answer", str(e), debug)
            raise
    
    async def optimize_semantic(self, question: str, conversation_memory: str = "") -> str:
        """
        Async wrapper for semantic optimization
        
        Args:
            question: User's question to optimize
            conversation_memory: Formatted conversation memory
            
        Returns:
            str: Optimized question for semantic search
        """
        return self.execute_optimize_semantic(question, conversation_memory, debug=False)
    
    async def analyze_question(self, question: str, conversation_memory: str = "") -> str:
        """
        Async wrapper for question analysis
        
        Args:
            question: User's question to analyze
            conversation_memory: Formatted conversation memory
            
        Returns:
            str: Analysis result for routing
        """
        return self.execute_analysis(question, conversation_memory, debug=False)
    
    async def extract_standard_numbers(self, question: str) -> List[str]:
        """
        Async wrapper for standard number extraction with multi-standard support
        
        Args:
            question: User's question to extract standards from
            
        Returns:
            List[str]: List of extracted standard numbers
        """
        result = self.execute_extract_standard(question, debug=False)
        if isinstance(result, str) and result.strip():
            # Split by comma and clean up each standard number
            standards = [s.strip() for s in result.split(',') if s.strip()]
            return standards
        return []
    
    async def extract_from_memory(self, question: str, conversation_memory: str) -> List[str]:
        """
        Async wrapper for memory-based term extraction
        
        Args:
            question: User's question to extract terms from
            conversation_memory: Formatted conversation memory
            
        Returns:
            List[str]: List of extracted terms from memory context
        """
        result = self.execute_extract_from_memory(question, conversation_memory, debug=False)
        if isinstance(result, str) and result.strip():
            # Split by comma and clean up each term
            terms = [s.strip() for s in result.split(',') if s.strip()]
            return terms
        return []
    
    async def optimize_textual(self, question: str, conversation_memory: str = "") -> str:
        """
        Async wrapper for textual optimization
        
        Args:
            question: User's question to optimize for textual search
            conversation_memory: Formatted conversation memory
            
        Returns:
            str: Optimized text for textual search
        """
        return self.execute_optimize_textual(question, conversation_memory, debug=False)
    
    async def generate_answer(self, question: str, chunks: str, conversation_memory: str = "") -> str:
        """
        Async wrapper for answer generation
        
        Args:
            question: Original user question
            chunks: Formatted chunks from Elasticsearch
            conversation_memory: Formatted conversation memory
            
        Returns:
            str: Generated answer
        """
        return self.execute_answer(question, chunks, conversation_memory, debug=False)
    
    async def generate_answer_stream(self, question: str, chunks: str, conversation_memory: str = "", sse_manager=None, session_id: str = None) -> AsyncGenerator[str, None]:
        """
        Stream answer generation token by token
        
        Args:
            question: Original user question
            chunks: Formatted chunks from Elasticsearch
            conversation_memory: Formatted conversation memory
            sse_manager: SSE manager for sending progress updates
            session_id: Session ID for SSE events
            
        Yields:
            str: Individual tokens from the answer
        """
        from src.sse_manager import ProgressStage
        
        try:
            # Send progress update for answer generation start
            if sse_manager and session_id:
                sse_manager.send_progress(
                    session_id, 
                    ProgressStage.ANSWER_GENERATION, 
                    "Genererer svar token for token...", 
                    85, 
                    "✨"
                )
            
            # Prepare prompt
            prompt_input = self.create_prompt_input(question, chunks=chunks, conversation_memory=conversation_memory)
            prompt_text = self.prompts["answer"].invoke(prompt_input).text
            
            messages = [
                {"role": "system", "content": "You are a helpful assistant that answers questions based on provided document chunks. Answer in Norwegian."},
                {"role": "user", "content": prompt_text}
            ]
            
            # Create streaming response
            response = self.client.chat.completions.create(
                model=OPENAI_MODEL_ANSWER,
                messages=messages,
                temperature=OPENAI_TEMPERATURE,
                max_tokens=8000,
                stream=True  # Enable streaming
            )
            
            full_answer = ""
            token_count = 0
            
            # Stream tokens one by one
            for chunk in response:
                if chunk.choices[0].delta.content is not None:
                    token = chunk.choices[0].delta.content
                    full_answer += token
                    token_count += 1
                    
                    # Send token via SSE if available
                    if sse_manager and session_id:
                        sse_manager.send_token(session_id, token, is_final=False)
                    
                    # Yield token for other consumers
                    yield token
            
            # Send final answer via SSE
            if sse_manager and session_id:
                sse_manager.send_final_answer(session_id, full_answer)
                sse_manager.send_progress(
                    session_id, 
                    ProgressStage.COMPLETE, 
                    f"Svar fullført! ({token_count} tokens)", 
                    100, 
                    "✅"
                )
            
        except Exception as e:
            error_msg = f"Streaming answer generation failed: {str(e)}"
            if sse_manager and session_id:
                sse_manager.send_error(session_id, error_msg)
            raise Exception(error_msg) 