#!/usr/bin/env python3
import sys
from chain import chain

def main():
    """Simple CLI interface for StandardGPT"""
    if len(sys.argv) < 2:
        print("Usage: python cli.py 'your question here'")
        print("Example: python cli.py 'Hva er NS-EN ISO 14155?'")
        return
    
    question = " ".join(sys.argv[1:])
    print(f"🔍 Spørsmål: {question}")
    print("📋 Behandler...")
    
    try:
        result = chain(question)
        print(f"💬 Svar: {result}")
    except Exception as e:
        print(f"❌ Feil: {e}")

if __name__ == "__main__":
    main() 