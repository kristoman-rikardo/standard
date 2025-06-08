#!/usr/bin/env python3
"""
Command line interface for StandardGPT
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.chain import chain

async def main():
    """Main CLI function"""
    if len(sys.argv) < 2:
        print("Usage: python cli.py \"Your question here\"")
        sys.exit(1)
    
    question = " ".join(sys.argv[1:])
    print(f"Question: {question}")
    print("=" * 50)
    
    try:
        answer = await chain(question, debug=True)
        print("\nFinal Answer:")
        print("=" * 50)
        print(answer)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main()) 