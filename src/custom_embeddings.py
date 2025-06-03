import requests
from langchain_core.embeddings import Embeddings
from typing import List
from .config import EMBEDDING_API_ENDPOINT

class FastEmbedAPI(Embeddings):
    def __init__(self, api_url: str = None):
        self.api_url = api_url or EMBEDDING_API_ENDPOINT

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of documents."""
        embeddings = []
        for text in texts:
            response = requests.post(
                self.api_url,
                json={"text": text},
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            embedding_data = response.json()
            
            # API returnerer format: {"vectors": [[...]], "model": "...", "dimension": ...}
            if "vectors" in embedding_data and len(embedding_data["vectors"]) > 0:
                embeddings.append(embedding_data["vectors"][0])
            elif "embedding" in embedding_data:
                embeddings.append(embedding_data["embedding"])
            elif isinstance(embedding_data, list):
                embeddings.append(embedding_data)
            else:
                # Fallback - ta første verdi
                embeddings.append(list(embedding_data.values())[0])
        return embeddings

    def embed_query(self, text: str) -> List[float]:
        """Embed a query."""
        response = requests.post(
            self.api_url,
            json={"text": text},
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        embedding_data = response.json()
        
        # API returnerer format: {"vectors": [[...]], "model": "...", "dimension": ...}
        if "vectors" in embedding_data and len(embedding_data["vectors"]) > 0:
            return embedding_data["vectors"][0]
        elif "embedding" in embedding_data:
            return embedding_data["embedding"]
        elif isinstance(embedding_data, list):
            return embedding_data
        else:
            return list(embedding_data.values())[0] 