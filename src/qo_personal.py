"""
Query object builder for personal handbook search, giving the personalhåndbok reference
"""

def create_query(text: str, embeddings: list = None):
    """
    Create query object for personal handbook search exactly as specified by user
    
    Args:
        text (str): Search text (usually last utterance or optimized text)
        embeddings (list): Vector embeddings from API
        
    Returns:
        dict: Complete Elasticsearch query object
    """
    
    # Build query exactly as specified by user for personal handbook
    if embeddings and any(x != 0.0 for x in embeddings):
        query_object = {
            "size": 400,
            "query": {
                "script_score": {
                    "query": {
                        "bool": {
                            "filter": {
                                "wildcard": {
                                    "reference.keyword": {
                                        "value": "*Personalhåndbok*",
                                        "case_insensitive": True
                                    }
                                }
                            }
                        }
                    },
                    "script": {
                        "source": "cosineSimilarity(params.query_vector, 'vector') + 1.0",
                        "params": {
                            "query_vector": embeddings
                        }
                    }
                }
            },
            "_source": ["text", "reference", "page"]
        }
    else:
        # Fallback without embeddings - still needs the filter structure
        query_object = {
            "size": 400,
            "query": {
                "bool": {
                    "filter": {
                        "wildcard": {
                            "reference.keyword": {
                                "value": "*Personalhåndbok*",
                                "case_insensitive": True
                            }
                        }
                    }
                }
            },
            "_source": ["text", "reference", "page"]
        }
    
    return query_object
