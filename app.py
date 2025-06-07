#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StandardGPT Web UI - Enkel grensesnitt med full debug output
"""

from flask import Flask, render_template, request, jsonify
import sys
import io
from contextlib import redirect_stdout, redirect_stderr
import traceback
from pathlib import Path

# Legg til src til Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Initialize Flask app
app = Flask(__name__)

class DebugCapture:
    """Fanger opp all debug output"""
    def __init__(self):
        self.debug_log = []
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
    
    def capture_output(self):
        """Start å fange opp output"""
        self.debug_log = []
        self.captured_stdout = io.StringIO()
        self.captured_stderr = io.StringIO()
        sys.stdout = self.captured_stdout
        sys.stderr = self.captured_stderr
    
    def stop_capture(self):
        """Stopp å fange opp output og returner innhold"""
        stdout_content = self.captured_stdout.getvalue()
        stderr_content = self.captured_stderr.getvalue()
        
        # Gjenopprett original output
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        
        return stdout_content, stderr_content

@app.route('/')
def index():
    """Hovedside"""
    return render_template('index.html')

@app.route('/api/query', methods=['POST'])
def process_query():
    """Behandle spørsmål fra brukeren"""
    try:
        data = request.get_json()
        question = data.get('question', '').strip()
        
        if not question:
            return jsonify({
                'error': 'Ingen spørsmål oppgitt',
                'debug_output': '',
                'answer': ''
            })
        
        # Fang opp all debug output
        debug_capture = DebugCapture()
        debug_capture.capture_output()
        
        try:
            # Import og kjør StandardGPT
            from chain import chain
            
            print(f"🎯 STANDARDGPT BEHANDLER SPØRSMÅL")
            print("=" * 60)
            print(f"📝 Spørsmål: {question}")
            print("=" * 60)
            print()
            
            # Kjør med debug=True for å få all informasjon
            answer = chain(question, debug=True)
            
            print()
            print("=" * 60)
            print("✅ BEHANDLING FULLFØRT")
            print("=" * 60)
            
        except Exception as e:
            print(f"❌ FEIL under behandling: {str(e)}")
            print(f"📜 Traceback: {traceback.format_exc()}")
            answer = f"Beklager, det oppstod en feil: {str(e)}"
        
        # Stopp capture og få debug output
        stdout_content, stderr_content = debug_capture.stop_capture()
        
        # Kombiner all debug output
        debug_output = stdout_content
        if stderr_content:
            debug_output += f"\n\n=== STDERR ===\n{stderr_content}"
        
        return jsonify({
            'answer': answer,
            'debug_output': debug_output,
            'question': question
        })
        
    except Exception as e:
        return jsonify({
            'error': f'Server feil: {str(e)}',
            'debug_output': traceback.format_exc(),
            'answer': ''
        })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000) 