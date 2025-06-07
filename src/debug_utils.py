"""
Debug utilities for StandardGPT flow tracking and debugging
"""

def debug_print(step_name, content, debug_mode=True):
    """
    Debug output for tracking flow through the system
    
    Args:
        step_name (str): Name of the current step
        content (str): Content to display
        debug_mode (bool): Whether to show debug output
    """
    if debug_mode:
        print(f"\n🔍 DEBUG - {step_name}:")
        print(f"{'='*50}")
        print(content)
        print(f"{'='*50}")

def log_step_start(step_number, step_name, input_data, debug_mode=True):
    """Log the start of a processing step"""
    if debug_mode:
        debug_print(f"STEG {step_number}: {step_name} - START", f"Input: {input_data}", debug_mode)

def log_step_end(step_number, step_name, output_data, debug_mode=True):
    """Log the end of a processing step"""
    if debug_mode:
        debug_print(f"STEG {step_number}: {step_name} - OUTPUT", output_data, debug_mode)

def log_routing_decision(analysis_result, route_taken, debug_mode=True):
    """Log which route was taken based on analysis"""
    if debug_mode:
        debug_print("ROUTING DECISION", 
                   f"Analysis result: {analysis_result}\nRoute taken: {route_taken}", 
                   debug_mode)

def log_error(step_name, error_message, debug_mode=True):
    """Log errors with context"""
    if debug_mode:
        debug_print(f"❌ ERROR in {step_name}", error_message, debug_mode)

def format_summary(result_data, debug_mode=True):
    """Format final summary for output"""
    if debug_mode:
        return f"""
🤖 StandardGPT Detaljert Svar:
📝 Opprinnelig spørsmål: {result_data['question']}
🔄 Optimalisert spørsmål: {result_data.get('optimized_question', 'N/A')}
🔍 Analyse resultat: {result_data.get('analysis', 'N/A')}
🛤️  Rute tatt: {result_data.get('route_taken', 'N/A')}
📚 Hentet dokumenter: {result_data.get('retrieved_docs', 0)}
📄 Chunks lengde: {result_data.get('chunks_length', 0)} tegn

💬 Finalt svar:
{result_data['answer']}
"""
    else:
        return f"\n💬 Svar:\n{result_data['answer']}" 