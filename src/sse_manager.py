"""
SSE Manager for StandardGPT
Håndterer Server-Sent Events for real-time streaming
"""

import time
import json
import uuid
import threading
from typing import Dict, Optional, Any
from enum import Enum
from flask import Response, stream_template_string
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class ProgressStage(Enum):
    """Progress stages for query processing"""
    STARTED = "started"
    VALIDATION = "validation"
    ANALYSIS = "analysis" 
    EXTRACTION = "extraction"
    ROUTING = "routing"
    SEARCH = "search"
    ANSWER_GENERATION = "answer_generation"
    COMPLETE = "complete"

class SSESession:
    """Individual SSE session"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at = time.time()
        self.is_active = True
        self.last_activity = time.time()
        self.messages = []
        self.current_progress = 0
        
    def add_message(self, data: Dict[str, Any]):
        """Add message to session"""
        self.messages.append({
            'timestamp': time.time(),
            'data': data
        })
        self.last_activity = time.time()
        
    def is_expired(self, timeout: int = 300) -> bool:
        """Check if session is expired (default 5 minutes)"""
        return time.time() - self.last_activity > timeout

class SSEManager:
    """Manages Server-Sent Events for real-time communication"""
    
    def __init__(self):
        self.sessions: Dict[str, SSESession] = {}
        self.session_lock = threading.Lock()
        self.cleanup_interval = 60  # seconds
        self.last_cleanup = time.time()
        
    def create_session(self, session_id: str = None) -> str:
        """Create a new SSE session"""
        if not session_id:
            session_id = f"sse_{int(time.time())}_{str(uuid.uuid4())[:8]}"
            
        with self.session_lock:
            self.sessions[session_id] = SSESession(session_id)
            logger.info(f"Created SSE session: {session_id}")
            
        return session_id
    
    def get_session(self, session_id: str) -> Optional[SSESession]:
        """Get session by ID"""
        with self.session_lock:
            return self.sessions.get(session_id)
    
    def cleanup_expired_sessions(self):
        """Remove expired sessions"""
        if time.time() - self.last_cleanup < self.cleanup_interval:
            return
            
        with self.session_lock:
            expired_sessions = [
                session_id for session_id, session in self.sessions.items()
                if session.is_expired()
            ]
            
            for session_id in expired_sessions:
                del self.sessions[session_id]
                logger.info(f"Cleaned up expired SSE session: {session_id}")
                
        self.last_cleanup = time.time()
    
    def send_event(self, session_id: str, event_type: str, data: Dict[str, Any]):
        """Send SSE event to session"""
        session = self.get_session(session_id)
        if not session or not session.is_active:
            logger.warning(f"Attempted to send to inactive session: {session_id}")
            return False
            
        event_data = {
            'type': event_type,
            'timestamp': datetime.utcnow().isoformat(),
            **data
        }
        
        session.add_message(event_data)
        logger.debug(f"Sent {event_type} event to session {session_id}")
        return True
    
    def send_progress(self, session_id: str, stage: ProgressStage, message: str, progress: int, emoji: str = ""):
        """Send progress update"""
        return self.send_event(session_id, 'progress', {
            'stage': stage.value,
            'message': message,
            'progress': progress,
            'emoji': emoji
        })
    
    def send_token(self, session_id: str, token: str, is_final: bool = False):
        """Send streaming token"""
        return self.send_event(session_id, 'token', {
            'token': token,
            'is_final': is_final
        })
    
    def send_final_answer(self, session_id: str, answer: str):
        """Send final complete answer"""
        return self.send_event(session_id, 'final_answer', {
            'answer': answer
        })
    
    def send_error(self, session_id: str, error_message: str):
        """Send error message"""
        return self.send_event(session_id, 'error', {
            'error': error_message
        })
    
    def close_session(self, session_id: str):
        """Close and remove session"""
        with self.session_lock:
            if session_id in self.sessions:
                self.sessions[session_id].is_active = False
                logger.info(f"Closed SSE session: {session_id}")

# Global SSE manager instance
sse_manager = SSEManager()

def create_sse_response(session_id: str) -> Response:
    """Create SSE response for session"""
    
    def event_stream():
        session = sse_manager.get_session(session_id)
        if not session:
            yield f"data: {json.dumps({'type': 'error', 'error': 'Session not found'})}\n\n"
            return
        
        # Send initial connection confirmation
        yield f"data: {json.dumps({'type': 'connected', 'session_id': session_id})}\n\n"
        
        message_index = 0
        timeout_counter = 0
        max_timeout = 120  # 2 minutter total timeout
        
        try:
            while session.is_active and timeout_counter < max_timeout:
                # Cleanup expired sessions periodically
                if timeout_counter % 30 == 0:  # Hver 30. sekund
                    sse_manager.cleanup_expired_sessions()
                
                # Check for new messages
                if message_index < len(session.messages):
                    while message_index < len(session.messages):
                        message = session.messages[message_index]
                        yield f"data: {json.dumps(message['data'])}\n\n"
                        message_index += 1
                    timeout_counter = 0  # Reset timeout on activity
                else:
                    # Send keepalive every 30 seconds
                    if timeout_counter % 30 == 0 and timeout_counter > 0:
                        yield f"data: {json.dumps({'type': 'keepalive', 'timestamp': time.time()})}\n\n"
                    
                    time.sleep(0.5)  # Sjekk hver 0.5 sekund
                    timeout_counter += 0.5
                    
        except GeneratorExit:
            logger.info(f"SSE client disconnected: {session_id}")
        except Exception as e:
            logger.error(f"SSE stream error for session {session_id}: {e}")
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        finally:
            # Mark session as inactive
            session.is_active = False
            logger.info(f"SSE stream ended for session: {session_id}")
    
    response = Response(
        event_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Cache-Control',
            'X-Accel-Buffering': 'no'  # Disable nginx buffering for real-time streaming
        }
    )
    
    return response

def stream_query_processing(session_id: str, question: str, flow_manager, conversation_memory: str = "0"):
    """
    Stream query processing with progress updates
    This runs in a separate thread with proper Flask context
    """
    import asyncio
    from flask import current_app
    
    # FORBEDRET: Ensure proper Flask application context
    with current_app.app_context():
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            logger.info(f"Starting query processing for session {session_id}")
            
            # Process query with SSE updates
            result = loop.run_until_complete(
                flow_manager.process_query_with_sse(
                    question, 
                    conversation_memory, 
                    session_id, 
                    debug=True
                )
            )
            
            logger.info(f"Query processing completed for session {session_id}")
            
        except Exception as e:
            logger.error(f"Error in stream_query_processing: {e}", exc_info=True)
            sse_manager.send_error(session_id, f"Feil under behandling: {str(e)}")
        finally:
            try:
                loop.close()
            except Exception as e:
                logger.warning(f"Error closing event loop: {e}")
            logger.info(f"Stream processing thread ended for session {session_id}") 