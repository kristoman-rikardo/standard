# -*- coding: utf-8 -*-
"""
Lokal FastAPI embedding-tjeneste for StandardGPT
Bruker fastembed med BAAI/bge-small-en-v1.5 (samme som indeksert i Elasticsearch)
Fallback til TF-IDF hvis fastembed ikke er tilgjengelig
"""
from __future__ import annotations

import os
from typing import List, Union
import hashlib
import pickle

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
import uvicorn
import numpy as np

# Prøv å importere fastembed
try:
    from fastembed import TextEmbedding
    FASTEMBED_AVAILABLE = True
except ImportError:
    FASTEMBED_AVAILABLE = False
    print("⚠️ fastembed pakke ikke installert.")

# Fallback: TF-IDF med scikit-learn
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("⚠️ scikit-learn ikke tilgjengelig")

###############################################################################
# 1. Modell- og embedder-oppsett
###############################################################################

MODEL_NAME = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")

# Global embedder instances
EMBEDDER = None
TFIDF_VECTORIZER = None
EMBEDDING_DIM = 384  # Default for BAAI/bge-small-en-v1.5
FALLBACK_DIM = 384   # Fixed dimension for TF-IDF fallback

def initialize_fastembed():
    """Initialiser fastembed embedder"""
    global EMBEDDER, EMBEDDING_DIM
    
    if not FASTEMBED_AVAILABLE:
        return False
        
    try:
        print(f"🔄 Laster fastembed modell: {MODEL_NAME}")
        EMBEDDER = TextEmbedding(model_name=MODEL_NAME, device="cpu")
        
        # Bestem dimensjoner dynamisk
        try:
            EMBEDDING_DIM = EMBEDDER.embedding_dimension
        except AttributeError:
            try:
                test_embedding = next(EMBEDDER.embed(["test"]))
                EMBEDDING_DIM = len(test_embedding)
            except Exception:
                EMBEDDING_DIM = 384  # Default
        
        print(f"✅ Fastembed modell lastet: {MODEL_NAME} ({EMBEDDING_DIM} dimensjoner)")
        return True
        
    except Exception as e:
        print(f"❌ Kunne ikke laste fastembed modell '{MODEL_NAME}': {e}")
        return False

def initialize_tfidf_fallback():
    """Initialiser TF-IDF fallback"""
    global TFIDF_VECTORIZER, EMBEDDING_DIM
    
    if not SKLEARN_AVAILABLE:
        return False
    
    try:
        print("🔄 Initialiserer TF-IDF fallback...")
        TFIDF_VECTORIZER = TfidfVectorizer(
            max_features=FALLBACK_DIM,
            stop_words='english',
            ngram_range=(1, 2),
            lowercase=True
        )
        
        # Tren på noen eksempel-tekster for å initialisere
        sample_texts = [
            "NORSOK standard for sveising",
            "Petroleum industry guidelines",
            "Safety requirements and procedures",
            "Technical specifications",
            "Standard for equipment and materials"
        ]
        TFIDF_VECTORIZER.fit(sample_texts)
        EMBEDDING_DIM = FALLBACK_DIM
        
        print(f"✅ TF-IDF fallback initialisert ({FALLBACK_DIM} dimensjoner)")
        return True
        
    except Exception as e:
        print(f"❌ TF-IDF fallback feilet: {e}")
        return False

def get_embeddings(texts: List[str]) -> List[List[float]]:
    """Generer embeddings med fastembed eller fallback"""
    if EMBEDDER is not None:
        # Bruk fastembed
        try:
            vectors = [vec.tolist() for vec in EMBEDDER.embed(texts)]
            return vectors
        except Exception as e:
            print(f"⚠️ Fastembed feilet: {e}, prøver fallback...")
    
    if TFIDF_VECTORIZER is not None:
        # Bruk TF-IDF fallback
        try:
            tfidf_matrix = TFIDF_VECTORIZER.transform(texts)
            vectors = tfidf_matrix.toarray().tolist()
            return vectors
        except Exception as e:
            print(f"❌ TF-IDF fallback feilet: {e}")
    
    # Siste utvei: generér dummy embeddings
    print("⚠️ Genererer dummy embeddings som fallback")
    vectors = []
    for text in texts:
        # Lav simpel hash-basert embedding
        hash_val = abs(hash(text))
        dummy_vec = [(hash_val >> i) % 256 / 255.0 for i in range(EMBEDDING_DIM)]
        vectors.append(dummy_vec)
    return vectors

###############################################################################
# 2. Pydantic-schemas
###############################################################################

class EmbedRequest(BaseModel):
    """Request-body for embedding."""
    text: Union[str, List[str]] = Field(
        ...,
        description="Streng eller liste med strenger som skal embeddes",
        examples=["Hva krever NORSOK om sveising?", "Hvordan sveiser jeg P235GH-rør?"],
    )

    @field_validator("text", mode="before")
    @classmethod
    def _ensure_list(cls, v):
        if isinstance(v, str):
            return [v]
        if isinstance(v, list) and all(isinstance(s, str) for s in v):
            return v
        raise ValueError("text må være en streng eller en liste av strenger")


class EmbedResponse(BaseModel):
    """Respons-format – én vektor pr. input-streng i samme rekkefølge."""
    model: str
    dimension: int
    vectors: List[List[float]]


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    model: str
    dimension: int
    fastembed_available: bool
    fastembed_loaded: bool
    tfidf_available: bool
    active_backend: str

###############################################################################
# 3. FastAPI-app
###############################################################################

app = FastAPI(
    title="StandardGPT Embedding Tjeneste",
    version="1.0", 
    summary="Lokal embedding-tjeneste med fastembed eller TF-IDF fallback",
    description="Samme embedding-modell som brukes i Elasticsearch-indeksen"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5000", "http://127.0.0.1:5000", "*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health():
    """Helsesjekk for embedding-tjenesten."""
    active_backend = "none"
    if EMBEDDER is not None:
        active_backend = "fastembed"
    elif TFIDF_VECTORIZER is not None:
        active_backend = "tfidf"
    else:
        active_backend = "dummy"
        
    return HealthResponse(
        status="ok",
        model=MODEL_NAME,
        dimension=EMBEDDING_DIM,
        fastembed_available=FASTEMBED_AVAILABLE,
        fastembed_loaded=EMBEDDER is not None,
        tfidf_available=SKLEARN_AVAILABLE,
        active_backend=active_backend
    )


@app.post("/embed", response_model=EmbedResponse, tags=["embed"])
def embed(req: EmbedRequest):
    """Generer embeddings med beste tilgjengelige metode"""
    if not req.text:
        raise HTTPException(status_code=400, detail="text kan ikke være tom")

    try:
        vectors = get_embeddings(req.text)
        
        # Bestém hvilken modell som faktisk ble brukt
        actual_model = MODEL_NAME
        if EMBEDDER is None:
            if TFIDF_VECTORIZER is not None:
                actual_model = "TF-IDF-fallback"
            else:
                actual_model = "dummy-fallback"

        return EmbedResponse(
            model=actual_model,
            dimension=EMBEDDING_DIM,
            vectors=vectors,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Kunne ikke generere embeddings: {str(e)}"
        )


@app.get("/", tags=["meta"])
def root():
    """Root endpoint for kompatibilitet."""
    active_backend = "none"
    if EMBEDDER is not None:
        active_backend = "fastembed"
    elif TFIDF_VECTORIZER is not None:
        active_backend = "tfidf"
    else:
        active_backend = "dummy"
        
    return {
        "service": "StandardGPT Embedding Tjeneste",
        "model": MODEL_NAME,
        "dimension": EMBEDDING_DIM,
        "active_backend": active_backend,
        "fastembed_available": FASTEMBED_AVAILABLE,
        "fastembed_loaded": EMBEDDER is not None,
        "tfidf_available": SKLEARN_AVAILABLE,
        "endpoints": {
            "health": "/health",
            "embed": "/embed"
        },
        "setup_instructions": {
            "preferred": "pip install fastembed==0.3.1",
            "fallback": "pip install scikit-learn",
            "start_service": "python run_embeddings.py"
        }
    }

###############################################################################
# 4. Startup event
###############################################################################

@app.on_event("startup")
async def startup_event():
    """Initialiser beste tilgjengelige embedding-metode"""
    print("\n🔧 Initialiserer embedding-tjeneste...")
    
    # Prøv fastembed først
    if initialize_fastembed():
        print("✅ Fastembed aktiv")
        return
    
    # Fallback til TF-IDF
    if initialize_tfidf_fallback():
        print("⚠️ Bruker TF-IDF fallback (ikke optimal for søk)")
        return
    
    # Siste utvei: dummy embeddings
    print("⚠️ Kun dummy embeddings tilgjengelig - installer fastembed for best ytelse")

###############################################################################
# 5. Lokalkjøring
###############################################################################
if __name__ == "__main__":
    print(f"🚀 Starter embedding-tjeneste med modell: {MODEL_NAME}")
    print(f"📏 Forventede dimensjoner: {EMBEDDING_DIM}")
    print(f"🔧 fastembed tilgjengelig: {'✅' if FASTEMBED_AVAILABLE else '❌'}")
    print(f"🔧 TF-IDF fallback: {'✅' if SKLEARN_AVAILABLE else '❌'}")
    
    uvicorn.run(
        "custom_embeddings:app", 
        host="127.0.0.1", 
        port=8001, 
        reload=False,
        log_level="info"
    )