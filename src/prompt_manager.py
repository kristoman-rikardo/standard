"""
Prompt manager for StandardGPT
"""

import os
import json
import requests
import openai
from langchain.prompts import PromptTemplate
from src.config import OPENAI_MODEL, OPENAI_API_KEY
from src.debug_utils import log_step_start, log_step_end, log_error, debug_print
from typing import Dict, List, Tuple, Optional
from pathlib import Path

class PromptManager:
    """Manages all prompt operations for the StandardGPT system"""
    
    def __init__(self):
        """Initialize the prompt manager with OpenAI client and load all prompts"""
        # Set up OpenAI client with hardcoded API key from config
        self.client = openai.OpenAI(api_key=OPENAI_API_KEY)
        self.model = OPENAI_MODEL
        self.prompts = self._load_all_prompts()
    
    def _call_openai(self, messages: List[Dict], temperature: float = 0) -> str:
        """
        Call OpenAI API with modern syntax
        
        Args:
            messages: List of message dicts for OpenAI
            temperature: Temperature for response generation
            
        Returns:
            str: Generated response content
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=1000
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
            "answer"
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
    
    def execute_optimize_semantic(self, last_utterance, debug=True):
        """
        Execute the optimizeSemantic prompt
        
        Args:
            last_utterance (str): User's original question
            debug (bool): Enable debug logging
            
        Returns:
            str: Optimized question for semantic search
        """
        log_step_start(1, "OptimizeSemantic", last_utterance, debug)
        
        try:
            prompt_input = self.create_prompt_input(last_utterance)
            prompt_text = self.prompts["optimizeSemantic"].invoke(prompt_input).text
            
            messages = [
                {"role": "system", "content": "You are a helpful assistant that optimizes questions for semantic search."},
                {"role": "user", "content": prompt_text}
            ]
            
            output = self._call_openai(messages)
            log_step_end(1, "OptimizeSemantic", output, debug)
            return output
            
        except Exception as e:
            log_error("OptimizeSemantic", str(e), debug)
            raise
    
    def execute_analysis(self, last_utterance, debug=True):
        """
        Execute the analysis prompt to determine routing
        
        Args:
            last_utterance (str): User's original question
            debug (bool): Enable debug logging
            
        Returns:
            str: Analysis result ("including", "without", or "personal")
        """
        log_step_start(3, "Analysis", last_utterance, debug)
        
        try:
            prompt_input = self.create_prompt_input(last_utterance)
            prompt_text = self.prompts["analysis"].invoke(prompt_input).text
            
            messages = [
                {"role": "system", "content": "You are a routing system that analyzes questions and returns exactly one of: 'including', 'without', or 'personal'."},
                {"role": "user", "content": prompt_text}
            ]
            
            output = self._call_openai(messages).lower()
            
            # Remove quotes if present
            output = output.strip('"\'')
            
            log_step_end(3, "Analysis", output, debug)
            return output
            
        except Exception as e:
            log_error("Analysis", str(e), debug)
            raise
    
    def execute_extract_standard(self, last_utterance, debug=True):
        """
        Execute the extractStandard prompt
        
        Args:
            last_utterance (str): User's original question
            debug (bool): Enable debug logging
            
        Returns:
            str: Extracted standard numbers (comma separated)
        """
        log_step_start("4a", "ExtractStandard", last_utterance, debug)
        
        try:
            prompt_input = self.create_prompt_input(last_utterance)
            prompt_text = self.prompts["extractStandard"].invoke(prompt_input).text
            
            messages = [
                {"role": "system", "content": "You extract standard numbers from questions. Return only the standard numbers, comma separated."},
                {"role": "user", "content": prompt_text}
            ]
            
            output = self._call_openai(messages)
            log_step_end("4a", "ExtractStandard", output, debug)
            return output
            
        except Exception as e:
            log_error("ExtractStandard", str(e), debug)
            raise
    
    def execute_optimize_textual(self, last_utterance, debug=True):
        """
        Execute the optimizeTextual prompt
        
        Args:
            last_utterance (str): User's original question
            debug (bool): Enable debug logging
            
        Returns:
            str: Optimized text for textual search
        """
        log_step_start("4b", "OptimizeTextual", last_utterance, debug)
        
        try:
            prompt_input = self.create_prompt_input(last_utterance)
            prompt_text = self.prompts["optimizeTextual"].invoke(prompt_input).text
            
            messages = [
                {"role": "system", "content": "You optimize questions for textual search by extracting key terms and concepts."},
                {"role": "user", "content": prompt_text}
            ]
            
            output = self._call_openai(messages)
            log_step_end("4b", "OptimizeTextual", output, debug)
            return output
            
        except Exception as e:
            log_error("OptimizeTextual", str(e), debug)
            raise
    
    def execute_answer(self, last_utterance, chunks, debug=True):
        """
        Execute the answer prompt to generate final response
        
        Args:
            last_utterance (str): User's original question
            chunks (str): Retrieved document chunks
            debug (bool): Enable debug logging
            
        Returns:
            str: Final answer
        """
        log_step_start(6, "Generate Answer", f"Question: {last_utterance[:50]}...", debug)
        
        try:
            prompt_input = self.create_prompt_input(last_utterance, chunks=chunks)
            prompt_text = self.prompts["answer"].invoke(prompt_input).text
            
            messages = [
                {"role": "system", "content": "You are a helpful assistant that answers questions based on provided document chunks. Answer in Norwegian."},
                {"role": "user", "content": prompt_text}
            ]
            
            output = self._call_openai(messages)
            log_step_end(6, "Generate Answer", "Answer generated", debug)
            return output
            
        except Exception as e:
            log_error("Generate Answer", str(e), debug)
            raise 