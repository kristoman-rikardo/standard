import typer
import json
from .chain import chain

def ask(question: str):
    """Still et spørsmål til StandardGPT"""
    try:
        response = chain.invoke({"question": question})
        
        print(f"\n🤖 StandardGPT Svar:")
        print(f"📝 Spørsmål: {response['question']}")
        print(f"🔍 Analyse: {response['analysis']}")
        print(f"✏️  Rewrite: {response['rewrite']}")
        print(f"📚 Hentet dokumenter: {response['retrieved_docs']}")
        print(f"\n💬 Svar:\n{response['answer']}")
        
    except Exception as e:
        typer.echo(f"❌ Feil: {e}", err=True)

if __name__ == "__main__":
    typer.run(ask) 