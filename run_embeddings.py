#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Starter den lokale embedding-tjenesten for StandardGPT med fastembed
"""
import os
import sys

# Sett miljøvariabler for lokal embedding
os.environ["EMBEDDING_API_ENDPOINT"] = "http://127.0.0.1:8001/embed"
os.environ["EMBED_MODEL"] = "BAAI/bge-small-en-v1.5"

if __name__ == "__main__":
    print("🚀 Starter StandardGPT fastembed embedding-tjeneste...")
    print("📍 URL: http://127.0.0.1:8001")
    print("🤖 Model: BAAI/bge-small-en-v1.5 (fastembed)")
    print("📏 Dimensjoner: 384")
    print("💡 Samme modell som brukt i Elasticsearch")
    print("⚡ Bruk Ctrl+C for å stoppe\n")
    
    # Import og kjør embedding-tjenesten
    try:
        import uvicorn
        
        uvicorn.run(
            "src.custom_embeddings:app",  # Bruk import string i stedet for app objekt
            host="127.0.0.1", 
            port=8001, 
            reload=False,  # Deaktiver reload for å unngå problemer
            log_level="info"
        )
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Sørg for at du har installert FastAPI og uvicorn:")
        print("python3 -m pip install fastapi uvicorn")
        print("For fastembed, prøv: python3 -m pip install fastembed==0.3.1")
    except Exception as e:
        print(f"❌ Feil ved oppstart: {e}") 