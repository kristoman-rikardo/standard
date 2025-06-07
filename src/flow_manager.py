"""
Main flow manager for StandardGPT
"""

from typing import Dict, Any, Optional
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

class FlowManager:
    """Main flow manager for StandardGPT query processing"""
    
    def __init__(self):
        """Initialize all components"""
        self.prompt_manager = PromptManager()
        self.query_builder = QueryObjectBuilder()
        self.elasticsearch_client = ElasticsearchClient()
    
    def process_query(self, last_utterance: str, debug: bool = True) -> Dict[str, Any]:
        """
        Process query through the complete flow
        
        Args:
            last_utterance (str): User's question
            debug (bool): Enable debug logging
            
        Returns:
            dict: Result with answer and metadata
        """
        debug_print("FlowManager", "Starting StandardGPT query processing", debug)
        
        try:
            result = {"question": last_utterance}
            
            # Step 1: Optimize semantic 
            result["optimized"] = self.prompt_manager.execute_optimize_semantic(last_utterance, debug)
            
            # Step 2: Get embeddings
            result["embeddings"] = self.elasticsearch_client.get_embeddings_from_api(result["optimized"], debug)
            
            # Step 3: Analysis
            result["analysis"] = self.prompt_manager.execute_analysis(last_utterance, debug)
            
            # Debug routing decision
            if debug:
                debug_print("ROUTING DECISION", f"Analysis result: {result['analysis']}", debug)
                if "including" in result["analysis"].lower():
                    debug_print("ROUTING DECISION", "Route taken: including (standard number search)", debug)
                elif "without" in result["analysis"].lower():
                    debug_print("ROUTING DECISION", "Route taken: without (textual search)", debug)
                else:
                    debug_print("ROUTING DECISION", "Route taken: personal (handbook search)", debug)
            
            # Route to appropriate handler
            if "including" in result["analysis"].lower():
                result = self._handle_including_route(result, last_utterance, debug)
            elif "without" in result["analysis"].lower():
                result = self._handle_without_route(result, last_utterance, debug)
            else:
                result = self._handle_personal_route(result, last_utterance, debug)
            
            # Step 5: Execute Elasticsearch search
            result["elasticsearch_response"] = self.elasticsearch_client.search(result["query_object"], debug)
            
            # Step 5.1: Format chunks from Elasticsearch response
            result["chunks"] = self.elasticsearch_client.format_chunks(result["elasticsearch_response"], debug)
            
            # Debug chunks information
            if debug:
                hits = result.get('elasticsearch_response', {}).get('hits', {}).get('hits', [])
                debug_print("CHUNKS INFORMATION", f"Number of chunks: {len(hits)}", debug)
                debug_print("CHUNKS INFORMATION", f"Formatted chunks length: {len(result['chunks'])}", debug)
                
                # Show sample chunks
                for i, hit in enumerate(hits[:3]):  # Show first 3 chunks
                    source = hit.get("_source", {})
                    score = hit.get("_score", 0)
                    debug_print("CHUNK SAMPLE", f"Chunk {i+1}: Score={score:.2f}, Reference={source.get('reference', 'N/A')}, Content={source.get('text', '')[:200]}...", debug)
            
            # Step 6: Generate final answer
            result["answer"] = self.prompt_manager.execute_answer(last_utterance, result["chunks"], debug)
            
            return result
            
        except Exception as e:
            log_error("FlowManager", f"Error in query processing: {str(e)}", debug)
            return {"answer": f"Beklager, det oppstod en feil under behandling av spørsmålet: {str(e)}"}
    
    def _handle_including_route(self, result: Dict[str, Any], last_utterance: str, debug: bool) -> Dict[str, Any]:
        """
        Handle the 'including' route - standard number search
        
        Args:
            result: Current processing result
            last_utterance: Original user question
            debug: Debug flag
            
        Returns:
            dict: Updated result with query object
        """
        result["route_taken"] = "including (standard number search)"
        log_routing_decision(result["analysis"], result["route_taken"], debug)
        
        # Step 4a: Extract standard numbers
        standard_numbers = self.prompt_manager.execute_extract_standard(last_utterance, debug)
        
        # Build filter query object
        result["query_object"] = self.query_builder.build_filter_query(
            standard_numbers, 
            last_utterance, 
            result["embeddings"], 
            debug
        )
        
        # Validate query object
        self.query_builder.validate_query_object(result["query_object"], "filter")
        
        return result
    
    def _handle_without_route(self, result: Dict[str, Any], last_utterance: str, debug: bool) -> Dict[str, Any]:
        """
        Handle the 'without' route - textual search
        
        Args:
            result: Current processing result
            last_utterance: Original user question
            debug: Debug flag
            
        Returns:
            dict: Updated result with query object
        """
        result["route_taken"] = "without (textual search)"
        log_routing_decision(result["analysis"], result["route_taken"], debug)
        
        # Step 4b: Optimize for textual search
        optimized_text = self.prompt_manager.execute_optimize_textual(last_utterance, debug)
        
        # Build textual query object
        result["query_object"] = self.query_builder.build_textual_query(
            optimized_text, 
            result["embeddings"], 
            debug
        )
        
        # Validate query object
        self.query_builder.validate_query_object(result["query_object"], "textual")
        
        return result
    
    def _handle_personal_route(self, result: Dict[str, Any], last_utterance: str, debug: bool) -> Dict[str, Any]:
        """
        Handle the 'personal' route - personal handbook search
        
        Args:
            result: Current processing result
            last_utterance: Original user question
            debug: Debug flag
            
        Returns:
            dict: Updated result with query object
        """
        result["route_taken"] = "personal (handbook search)"
        log_routing_decision(result["analysis"], result["route_taken"], debug)
        
        # Step 4c: Build personal query object
        result["query_object"] = self.query_builder.build_personal_query(
            last_utterance, 
            result["embeddings"], 
            debug
        )
        
        # Validate query object
        self.query_builder.validate_query_object(result["query_object"], "personal")
        
        return result
    
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