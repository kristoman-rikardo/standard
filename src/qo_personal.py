"""
Query object builder for personal handbook search
"""

import json   # bare nødvendig hvis du vil ha en ren JSON-streng til slutt

# ---------------------------------------------------------
# 1. Inndata
vectors = "Vektor som Pythonliste fra custom_embeddings.py"   # eksempel­vektor

# ---------------------------------------------------------
# 2. Bygg spørringen
queryObject = {
    "size": 80,
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
                    "query_vector": vectors
                }
            }
        }
    },
    "_source": ["text", "reference", "page"]
}

# ---------------------------------------------------------
# 3. (Valgfritt) gjøres om til JSON-streng
queryObject_json = json.dumps(queryObject, ensure_ascii=False)

# ---------------------------------------------------------
# 4. Eksempel på bruk
# from elasticsearch import Elasticsearch
# es = Elasticsearch("http://localhost:9200")
# response = es.search(index="ditt_index", body=queryObject)

def create_query(question: str, embeddings: list = None):
    """
    Create query object for personal handbook search
    
    Args:
        question (str): User's question (not used in this query type)
        embeddings (list): Vector embeddings from API
        
    Returns:
        dict: Complete Elasticsearch query object
    """
    
    # If we have valid embeddings, use script_score, otherwise use simple wildcard
    if embeddings and any(x != 0.0 for x in embeddings):
        query_object = {
            "size": 80,
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
        # Fallback to simple wildcard query without embeddings
        query_object = {
            "size": 80,
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
