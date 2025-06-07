import json  # trengs bare hvis du vil ende opp med en JSON-streng

# ---------------------------------------------------------
# 1. Inndata fra kallet ditt
text    = "Tekstuelt søk fra optimizedTextual"   # eksempeltekst
vectors = "Vektor som Pythonliste fra custom_embeddings.py"      # eksempelvektor

# ---------------------------------------------------------
# 2. Bygg Elasticsearch-spørringen
queryObject = {
    "size": 80,
    "query": {
        "script_score": {
            "query": {
                "multi_match": {
                    "query": text,                # variabelen text
                    "fields": ["text^2", "reference"]
                }
            },
            "script": {
                "source": "cosineSimilarity(params.query_vector, 'vector') + 1.0",
                "params": {
                    "query_vector": vectors       # variabelen vectors
                }
            }
        }
    },
    "_source": ["text", "reference", "page"]
}

# ---------------------------------------------------------
# 3. Valgfritt: gjør det om til en JSON-streng
queryObject_json = json.dumps(queryObject, ensure_ascii=False)

# ---------------------------------------------------------
# 4. (Eksempel på bruk med klient)
# from elasticsearch import Elasticsearch
# es = Elasticsearch("http://localhost:9200")
# response = es.search(index="ditt_index", body=queryObject)

"""
Query object builder for textual search
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
            "size": 80,
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
            "size": 80,
            "query": {
                "multi_match": {
                    "query": text,
                    "fields": ["text^2", "reference"]
                }
            },
            "_source": ["text", "reference", "page"]
        }
    
    return query_object
