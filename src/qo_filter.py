# Bygger query object med filter/reference

import json  

# 1. Forbered inndata ------------------------------------
standards = "Starnards fra extractStandard.py"        # f.eks. en komma-separert streng
vectors   = "Vektor som Pythonliste fra custom_embeddings.py"            # din vektor som Python-liste

# Split + trim (samme som JS .split(',').map(s => s.trim()))
standards = [s.strip() for s in standards.split(',')]

# 2. Bygg spørringen -------------------------------------
queryObject = {
    "size": 40,
    "query": {
        "script_score": {
            "query": {
                "bool": {
                    "should": [
                        {                     # én wildcard-del per standard
                            "wildcard": {
                                "reference.keyword": {
                                    "value": f"*{s}*",
                                    "case_insensitive": True
                                }
                            }
                        }
                        for s in standards
                    ],
                    "minimum_should_match": 1
                }
            },
            "script": {
                "source": "cosineSimilarity(params.query_vector, 'vector') + 1.0",
                "params": {
                    "query_vector": vectors    # kan også være np.array.tolist()
                }
            }
        }
    },
    "_source": ["text", "reference", "page"]
}

# 3. Valgfritt: konverter til JSON-streng -----------------
queryObject_json = json.dumps(queryObject, ensure_ascii=False)

# --- brukseksempel med offisiell klient -----------------
# from elasticsearch import Elasticsearch
# es = Elasticsearch("http://localhost:9200")
# response = es.search(index="ditt_index", body=queryObject)

"""
Query object builder for standard number filtering
"""

def create_query(standard_numbers: list, question: str, embeddings: list = None):
    """
    Create query object for standard number filtering
    
    Args:
        standard_numbers (list): List of standard numbers from extractStandard
        question (str): User's original question
        embeddings (list): Vector embeddings from API
        
    Returns:
        dict: Complete Elasticsearch query object
    """
    
    # Build wildcard queries for each standard number
    wildcard_queries = []
    for standard in standard_numbers:
        wildcard_queries.append({
            "wildcard": {
                "reference.keyword": {
                    "value": f"*{standard.strip()}*",
                    "case_insensitive": True
                }
            }
        })
    
    # If we have valid embeddings, use script_score, otherwise use simple bool query
    if embeddings and any(x != 0.0 for x in embeddings):
        query_object = {
            "size": 40,  # Reduced for latency; still enough for quality
            "query": {
                "script_score": {
                    "query": {
                        "bool": {
                            "should": wildcard_queries,
                            "minimum_should_match": 1
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
        # Fallback to simple bool query without embeddings
        query_object = {
            "size": 40,  # Reduced for latency; still enough for quality
            "query": {
                "bool": {
                    "should": wildcard_queries,
                    "minimum_should_match": 1
                }
            },
            "_source": ["text", "reference", "page"]
        }
    
    return query_object
