from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda
from langchain_openai import ChatOpenAI
from .retriever import retriever
from .config import OPENAI_MODEL
from pathlib import Path

def load_prompt(name):
    path = Path(__file__).parent / "prompts" / f"{name}.txt"
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    return PromptTemplate.from_template(content)

# Load alle prompts (med faktiske filnavn)
analysis_prompt = load_prompt("analysis")
rewrite_with_number_prompt = load_prompt("rewriteWithNumb")
rewrite_without_number_prompt = load_prompt("rewriteWithOut")  
validate_prompt = load_prompt("validate")
answer_prompt = load_prompt("answer")

llm = ChatOpenAI(model=OPENAI_MODEL, temperature=0)

def parse_analysis_result(analysis_output):
    """Parse analysis output - returnerer true/false som string"""
    result = analysis_output.content.strip().lower()
    return "true" in result

def route_rewrite(input_data):
    """Route til riktig rewrite basert på analysis"""
    if isinstance(input_data, dict):
        analysis_result = input_data.get("analysis_result")
        question = input_data.get("question")
    else:
        # Direkte fra forrige steg
        analysis_result = input_data
        question = None
        
    needs_number = parse_analysis_result(analysis_result)
    
    if needs_number:
        return rewrite_with_number_prompt
    else:
        return rewrite_without_number_prompt

def retrieve_documents(rewrite_output):
    """Hent dokumenter basert på optimized question"""
    optimized_question = rewrite_output.content.strip()
    docs = retriever.invoke(optimized_question)
    
    return {
        "optimized_question": optimized_question,
        "docs": docs,
        "chunks": "\n\n".join([doc.page_content for doc in docs])
    }

def prepare_validate_input(retrieval_output):
    """Prepare input for validation step"""
    return {
        "question": retrieval_output.get("question", ""),
        "chunks": retrieval_output.get("chunks", ""),
        "answer": retrieval_output.get("answer", "")
    }

def prepare_answer_input(retrieval_output):
    """Prepare input for final answer"""
    return {
        "last_utterance": retrieval_output.get("question", ""),
        "chunks": retrieval_output.get("chunks", "")
    }

# Main chain
def create_chain():
    def process_question(input_data):
        question = input_data.get("question") or input_data
        
        # Step 1: Analysis
        analysis_result = analysis_prompt.invoke({"last_utterance": question})
        analysis_output = llm.invoke(analysis_result)
        
        # Step 2: Route til riktig rewrite
        rewrite_prompt = route_rewrite(analysis_output)
        rewrite_input = rewrite_prompt.invoke({"last_utterance": question})
        rewrite_output = llm.invoke(rewrite_input)
        
        # Step 3: Retrieve documents
        retrieval_result = retrieve_documents(rewrite_output)
        retrieval_result["question"] = question
        
        # Step 4: Generate answer
        answer_input = prepare_answer_input(retrieval_result)
        answer_prompt_filled = answer_prompt.invoke(answer_input)
        final_answer = llm.invoke(answer_prompt_filled)
        
        return {
            "question": question,
            "analysis": analysis_output.content,
            "rewrite": rewrite_output.content,
            "retrieved_docs": len(retrieval_result["docs"]),
            "answer": final_answer.content
        }
    
    return RunnableLambda(process_question)

chain = create_chain() 