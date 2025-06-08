"""
Query builders for StandardGPT
"""

import importlib
from typing import Dict, Any, Optional
from src.debug_utils import log_step_start, log_step_end, log_error, debug_print

class QueryObjectBuilder:
    """Builds query objects for different search types"""
    
    def __init__(self):
        """Initialize the query object builder"""
        self.query_objects = self._load_query_objects()
    
    def _load_query_objects(self):
        """Load all query object modules"""
        query_files = {
            "filter": "qo_filter",
            "textual": "qo_textual", 
            "personal": "qo_personal"
        }
        
        query_objects = {}
        
        for name, filename in query_files.items():
            try:
                module = importlib.import_module(f".{filename}", package="src")
                query_objects[name] = module
                debug_print(f"QueryBuilder", f"Loaded {filename}")
            except ImportError as e:
                debug_print(f"QueryBuilder", f"Warning: Could not load {filename}: {e}")
                query_objects[name] = None
        
        return query_objects
    
    def build_filter_query(self, standard_numbers, last_utterance, embeddings=None, debug=True):
        """
        Build query object for standard number filtering with multi-standard support
        
        Args:
            standard_numbers (str or list): Standard numbers to filter by
            last_utterance (str): Original user question
            embeddings (list): Optional embeddings for semantic search
            debug (bool): Enable debug logging
            
        Returns:
            dict: Query object for Elasticsearch filter search
        """
        log_step_start("5a", "Build Filter Query", standard_numbers, debug)
        
        try:
            if not self.query_objects["filter"]:
                raise ImportError("qo_filter module not available")
            
            # Handle both string and list inputs for standard numbers
            if isinstance(standard_numbers, list):
                standards = [s.strip() for s in standard_numbers if s.strip()]
            elif isinstance(standard_numbers, str):
                standards = [s.strip() for s in standard_numbers.split(",") if s.strip()]
            else:
                standards = []
            
            # Create query object using qo_filter
            if hasattr(self.query_objects["filter"], "create_query"):
                query_object = self.query_objects["filter"].create_query(
                    standard_numbers=standards,
                    question=last_utterance,
                    embeddings=embeddings
                )
            else:
                # Fallback to manual creation
                query_object = {
                    "query": {
                        "bool": {
                            "should": [
                                {"terms": {"standard_number": standards}},
                                {"match": {"content": last_utterance}}
                            ],
                            "minimum_should_match": 1
                        }
                    },
                    "size": 80,
                    "_source": ["content", "standard_number", "title"]
                }
                
                if embeddings:
                    query_object["query"]["bool"]["should"].append({
                        "script_score": {
                            "query": {"match_all": {}},
                            "script": {
                                "source": "cosineSimilarity(params.query_vector, 'content_vector') + 1.0",
                                "params": {"query_vector": embeddings}
                            }
                        }
                    })
            
            log_step_end("5a", "Build Filter Query", f"Query for {len(standards)} standards: {standards}", debug)
            return query_object
            
        except Exception as e:
            log_error("Build Filter Query", str(e), debug)
            raise
    
    def build_textual_query(self, optimized_text, embeddings=None, debug=True):
        """
        Build query object for textual search
        
        Args:
            optimized_text (str): Optimized text for search
            embeddings (list): Optional embeddings for semantic search
            debug (bool): Enable debug logging
            
        Returns:
            dict: Query object for Elasticsearch textual search
        """
        log_step_start("5b", "Build Textual Query", optimized_text, debug)
        
        try:
            if not self.query_objects["textual"]:
                raise ImportError("qo_textual module not available")
            
            # Create query object using qo_textual
            if hasattr(self.query_objects["textual"], "create_query"):
                query_object = self.query_objects["textual"].create_query(
                    text=optimized_text,
                    embeddings=embeddings
                )
            else:
                # Fallback to manual creation
                query_object = {
                    "query": {
                        "bool": {
                            "should": [
                                {"match": {"content": {"query": optimized_text, "boost": 2}}},
                                {"match": {"title": {"query": optimized_text, "boost": 1.5}}},
                                {"match_phrase": {"content": optimized_text}}
                            ],
                            "minimum_should_match": 1
                        }
                    },
                    "size": 10,
                    "_source": ["content", "title", "standard_number"]
                }
                
                if embeddings:
                    query_object["query"]["bool"]["should"].append({
                        "script_score": {
                            "query": {"match_all": {}},
                            "script": {
                                "source": "cosineSimilarity(params.query_vector, 'content_vector') + 1.0",
                                "params": {"query_vector": embeddings}
                            }
                        }
                    })
            
            log_step_end("5b", "Build Textual Query", "Textual query created", debug)
            return query_object
            
        except Exception as e:
            log_error("Build Textual Query", str(e), debug)
            raise
    
    def build_personal_query(self, last_utterance, embeddings=None, debug=True):
        """
        Build query object for personal handbook search
        
        Args:
            last_utterance (str): Original user question
            embeddings (list): Optional embeddings for semantic search
            debug (bool): Enable debug logging
            
        Returns:
            dict: Query object for Elasticsearch personal search
        """
        log_step_start("5c", "Build Personal Query", last_utterance, debug)
        
        try:
            if not self.query_objects["personal"]:
                raise ImportError("qo_personal module not available")
            
            # Create query object using qo_personal
            if hasattr(self.query_objects["personal"], "create_query"):
                query_object = self.query_objects["personal"].create_query(
                    text=last_utterance,
                    embeddings=embeddings
                )
            else:
                # Fallback to manual creation for personal handbook
                query_object = {
                    "query": {
                        "bool": {
                            "should": [
                                {"match": {"content": last_utterance}},
                                {"match": {"title": last_utterance}}
                            ],
                            "filter": [
                                {"term": {"document_type": "personal_handbook"}}
                            ],
                            "minimum_should_match": 1
                        }
                    },
                    "size": 10,
                    "_source": ["content", "title", "section"]
                }
                
                if embeddings:
                    query_object["query"]["bool"]["should"].append({
                        "script_score": {
                            "query": {"match_all": {}},
                            "script": {
                                "source": "cosineSimilarity(params.query_vector, 'content_vector') + 1.0",
                                "params": {"query_vector": embeddings}
                            }
                        }
                    })
            
            log_step_end("5c", "Build Personal Query", "Personal query created", debug)
            return query_object
            
        except Exception as e:
            log_error("Build Personal Query", str(e), debug)
            raise
    
    def validate_query_object(self, query_object, query_type="unknown"):
        """
        Validate that a query object has the required structure
        
        Args:
            query_object (dict): The query object to validate
            query_type (str): Type of query for error reporting
            
        Returns:
            bool: True if valid, raises exception if invalid
        """
        if not isinstance(query_object, dict):
            raise ValueError(f"{query_type} query object must be a dictionary")
        
        if "query" not in query_object:
            raise ValueError(f"{query_type} query object must have a 'query' field")
        
        if "size" not in query_object:
            debug_print("QueryBuilder", f"Warning: {query_type} query missing 'size' field")
        
        return True 