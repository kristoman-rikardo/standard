"""
Query object builder for textual search, user query without standard name/number. 
"""

def create_query(text: str, embeddings: list = None):
    """
    Create query object for textual search
    
    Args:
        text (str): Optimized text from optimizeTextual
        embeddings (list): Vector embeddings from API
        
    Returns:
        dict: Complete Elasticsearch query object
    """
    
    # If we have valid embeddings, use script_score, otherwise use simple multi_match
    if embeddings and any(x != 0.0 for x in embeddings):
        query_object = {
            "size": 60,
            "query": {
                "script_score": {
                    "query": {
                        "multi_match": {
                            "query": text,
                            "fields": ["text^2", "reference"]
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
        # Fallback to simple multi_match query without embeddings
        query_object = {
            "size": 60,
            "query": {
                "multi_match": {
                    "query": text,
                    "fields": ["text^2", "reference"]
                }
            },
            "_source": ["text", "reference", "page"]
        }
    
    return query_object
