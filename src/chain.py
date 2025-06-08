"""
Chain module for backward compatibility with existing StandardGPT usage.
This module provides a simple wrapper around the new FlowManager architecture.
"""

import asyncio
import logging
from src.flow_manager import FlowManager

async def chain(question: str, debug: bool = True) -> str:
    """
    Process a question through StandardGPT with async support
    
    Args:
        question (str): The user's question
        debug (bool): Enable debug output
        
    Returns:
        str: The generated answer
    """
    try:
        flow_manager = FlowManager()
        result = await flow_manager.process_query(question, debug)
        return result.get("answer", "Kunne ikke generere svar")
    except Exception as e:
        logging.error(f"Error in chain processing: {str(e)}")
        return f"Beklager, det oppstod en feil: {str(e)}"

def chain_sync(question: str, debug: bool = True) -> str:
    """
    Synchronous wrapper for the async chain function
    
    Args:
        question (str): The user's question
        debug (bool): Enable debug output
        
    Returns:
        str: The generated answer
    """
    try:
        return asyncio.run(chain(question, debug))
    except Exception as e:
        logging.error(f"Error in sync chain processing: {str(e)}")
        return f"Beklager, det oppstod en feil: {str(e)}"