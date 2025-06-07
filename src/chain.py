"""
Simple chain wrapper for backward compatibility with LangChain
"""

from src.flow_manager import FlowManager

# Initialize the flow manager
flow_manager = FlowManager()

def chain(question: str, debug: bool = True) -> str:
    """
    Simple wrapper function for backward compatibility
    
    Args:
        question (str): User's question
        debug (bool): Enable debug output
        
    Returns:
        str: Final answer
    """
    try:
        result = flow_manager.process_query(question, debug=debug)
        # Prøv forskjellige felt for å finne svaret
        answer = result.get("answer", result.get("final_answer", "Ingen svar generert."))
        return answer
    except Exception as e:
        return f"Feil i behandling av spørsmål: {e}"