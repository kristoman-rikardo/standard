#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StandardGPT - AI-powered Norwegian Standards Search
Production-ready Flask application with modern architecture
"""

import os
import logging
import time
import hashlib
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from functools import wraps
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from flask import Flask, request, jsonify, render_template, current_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pydantic import BaseModel, Field, validator
import bleach
import openai

# Import our config from ROOT level (not src/)
from config import get_config, HealthCheck, SecurityConfig

# Import our custom Elasticsearch client and FlowManager
from src.flow_manager import FlowManager
import asyncio
import threading

# Initialize Flask app
app = Flask(__name__)

# Load configuration
config_class = get_config()
app.config.from_object(config_class)
config_class.init_app(app)

# Set OpenAI API key - FIXED: Use correct attribute for newer openai version
if app.config.get('OPENAI_API_KEY'):
    openai.api_key = app.config['OPENAI_API_KEY']

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=[app.config['RATELIMIT_DEFAULT']],
    storage_uri=app.config['RATELIMIT_STORAGE_URL']
)

# Global storage for conversation sessions - THREAD SAFE
conversation_sessions: Dict[str, List[Dict[str, Any]]] = {}
conversation_lock = threading.Lock()  # Add thread safety

# Cache storage
cache: Dict[str, Any] = {}
cache_expiry: Dict[str, datetime] = {}

def get_session_id(request_obj):
    """Extract session ID from request headers or generate new one"""
    session_id = request_obj.headers.get('X-Session-ID')
    if not session_id:
        session_id = f"session_{int(time.time())}_{str(uuid.uuid4())[:8]}"
    return session_id

def get_conversation_memory(session_id):
    """Get formatted conversation memory for session - THREAD SAFE"""
    with conversation_lock:
        if session_id not in conversation_sessions or not conversation_sessions[session_id]:
            app.logger.debug(f"🧠 No conversation memory for session {session_id}")
            return "0"
        
        history = conversation_sessions[session_id]
        if not history:
            app.logger.debug(f"🧠 Empty conversation history for session {session_id}")
            return "0"
        
        # Format last 5 exchanges (to keep within token limits)
        formatted_parts = []
        for entry in history[-5:]:
            # Clean messages for prompt safety but keep them readable
            user_clean = entry['user'].replace('\n', ' ').replace('\r', ' ').strip()
            system_clean = entry['system'].replace('\n', ' ').replace('\r', ' ').strip()
            
            # Use the format expected by analysis prompt: USER: ...\nSYSTEM: ...
            formatted_parts.append(f"USER: {user_clean}")
            formatted_parts.append(f"SYSTEM: {system_clean}")
        
        # Join with newlines as expected by the analysis prompt
        memory_text = "\n".join(formatted_parts)
        app.logger.debug(f"🧠 Retrieved conversation memory for session {session_id}: {len(memory_text)} chars, {len(history)} exchanges")
        app.logger.debug(f"🧠 Memory format preview: {memory_text[:200]}...")
        return memory_text

def update_conversation_memory(session_id, user_message, system_response):
    """Update conversation memory with new exchange - THREAD SAFE"""
    with conversation_lock:
        if session_id not in conversation_sessions:
            conversation_sessions[session_id] = []
            app.logger.debug(f"🧠 Created new conversation session: {session_id}")
        
        # Clean messages before storing - keep more of system response for context
        user_clean = user_message.strip()
        system_clean = system_response.strip()[:1000]  # Increased from 400 to 1000 for better context
        
        # Add new exchange
        conversation_sessions[session_id].append({
            'user': user_clean,
            'system': system_clean,
            'timestamp': datetime.utcnow().isoformat()
        })
        
        # Keep only last 5 exchanges to prevent token overflow
        if len(conversation_sessions[session_id]) > 5:
            conversation_sessions[session_id] = conversation_sessions[session_id][-5:]
        
        app.logger.debug(f"🧠 Updated conversation memory for session {session_id}: {len(conversation_sessions[session_id])} exchanges")
        app.logger.debug(f"🧠 Latest exchange - User: {user_clean[:50]}... System: {system_clean[:100]}...")

def clear_conversation_memory(session_id):
    """Clear conversation memory for session - THREAD SAFE"""
    with conversation_lock:
        if session_id in conversation_sessions:
            del conversation_sessions[session_id]

def cache_key(text):
    """Generate cache key from text"""
    return hashlib.md5(text.encode()).hexdigest()

def get_from_cache(key):
    """Get value from cache if not expired"""
    if key in cache and key in cache_expiry:
        if datetime.now() < cache_expiry[key]:
            return cache[key]
        else:
            # Remove expired item
            del cache[key]
            del cache_expiry[key]
    return None

def set_cache(key, value, ttl_seconds=3600):
    """Set value in cache with TTL"""
    cache[key] = value
    cache_expiry[key] = datetime.now() + timedelta(seconds=ttl_seconds)

def cache_response(ttl_seconds=3600):
    """Decorator for caching responses"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            cache_data = {
                'func': func.__name__,
                'args': args,
                'kwargs': kwargs
            }
            key = cache_key(json.dumps(cache_data, sort_keys=True, default=str))
            
            # Try to get from cache first
            cached_result = get_from_cache(key)
            if cached_result is not None:
                return cached_result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            set_cache(key, result, ttl_seconds)
            return result
        return wrapper
    return decorator

# Initialize FlowManager instead of the old service
try:
    flow_manager = FlowManager()
    app.logger.info("✅ FlowManager initialized successfully")
except Exception as e:
    app.logger.error(f"❌ Failed to initialize FlowManager: {e}")
    flow_manager = None

# Warmup function to avoid cold starts
async def warmup_services():
    """Warmup services to avoid cold start delays - robust version"""
    if flow_manager:
        try:
            app.logger.info("🔥 Starting service warmup...")
            
            # Warmup embedding API with a simple query - make it optional
            try:
                embedding_client = flow_manager.elasticsearch_client
                warmup_embedding = await asyncio.get_event_loop().run_in_executor(
                    None, embedding_client.get_embeddings_from_api, "warmup query", False
                )
                if warmup_embedding:
                    app.logger.info("✅ Embedding API warmed up successfully")
                else:
                    app.logger.info("ℹ️ Embedding API warmup skipped (endpoint not available/configured)")
            except Exception as embedding_error:
                app.logger.info(f"ℹ️ Embedding API warmup skipped: {embedding_error}")
            
            # Warmup OpenAI with a simple semantic optimization - FIXED: Use correct async method
            try:
                prompt_manager = flow_manager.prompt_manager
                warmup_openai = await prompt_manager.optimize_semantic("warmup", "")
                if warmup_openai:
                    app.logger.info("✅ OpenAI API warmed up successfully")
                else:
                    app.logger.warning("⚠️ OpenAI API warmup returned empty result")
            except Exception as openai_error:
                app.logger.warning(f"⚠️ OpenAI API warmup failed: {openai_error}")
            
            # Test Elasticsearch health
            try:
                es_health = flow_manager.elasticsearch_client.health_check(debug=False)
                if es_health:
                    app.logger.info("✅ Elasticsearch health check passed")
                else:
                    app.logger.warning("⚠️ Elasticsearch health check failed")
            except Exception as es_error:
                app.logger.warning(f"⚠️ Elasticsearch health check error: {es_error}")
                
            app.logger.info("🔥 Service warmup completed")
            
        except Exception as e:
            app.logger.warning(f"⚠️ Service warmup failed: {e}")

# Run warmup in background if FlowManager is available
if flow_manager:
    def run_warmup():
        """Run warmup in a separate thread"""
        try:
            asyncio.run(warmup_services())
        except Exception as e:
            app.logger.warning(f"⚠️ Background warmup failed: {e}")
    
    # Start warmup in background thread
    warmup_thread = threading.Thread(target=run_warmup, daemon=True)
    warmup_thread.start()
    app.logger.info("🚀 Background warmup started")

class QueryRequest(BaseModel):
    """Pydantic model for validating query requests"""
    question: str = Field(..., min_length=3, max_length=1000)
    
    @validator('question')
    def validate_question(cls, v):
        if not v or not v.strip():
            raise ValueError('Question cannot be empty')
        
        # Sanitize input - FIXED: Handle cases where current_app context might not be available
        try:
            allowed_tags = current_app.config.get('ALLOWED_HTML_TAGS', [])
            min_length = current_app.config.get('MIN_QUESTION_LENGTH', 3)
        except RuntimeError:
            # Fallback if outside application context
            allowed_tags = []
            min_length = 3
        
        sanitized = bleach.clean(
            v.strip(),
            tags=allowed_tags,
            strip=True
        )
        
        if len(sanitized) < min_length:
            raise ValueError(f'Question must be at least {min_length} characters long')
        
        return sanitized


@app.before_request
def before_request():
    """Execute before each request"""
    # Log request details in debug mode
    if app.debug:
        app.logger.debug(f"Request: {request.method} {request.path} from {request.remote_addr}")


@app.after_request
def after_request(response):
    """Execute after each request"""
    # Apply security headers
    response = SecurityConfig.apply_security_headers(response)
    
    # Add cache headers for static content
    if request.endpoint == 'static':
        response.headers['Cache-Control'] = 'public, max-age=31536000'  # 1 year
    
    # Log response in debug mode
    if app.debug:
        app.logger.debug(f"Response: {response.status_code}")
    
    return response


@app.route('/')
def index():
    """Serve the main application page"""
    return render_template('index.html')


@app.route('/health')
def health_check():
    """Enhanced health check endpoint - robust for production"""
    try:
        # Get system status with error handling
        status = {}
        
        # Test FlowManager availability
        try:
            if flow_manager:
                flow_health = flow_manager.health_check(debug=False)
                status.update(flow_health)
                status['flowmanager'] = True
            else:
                status['flowmanager'] = False
                status['elasticsearch'] = False
                status['prompts'] = False
                status['query_builders'] = False
        except Exception as e:
            app.logger.warning(f"FlowManager health check failed: {e}")
            status['flowmanager'] = False
            status['elasticsearch'] = False
            status['prompts'] = False
            status['query_builders'] = False
        
        # Test OpenAI API availability
        try:
            if app.config.get('OPENAI_API_KEY'):
                status['openai'] = True  # Assume available if key is set
            else:
                status['openai'] = False
        except Exception:
            status['openai'] = False
        
        # Add cache information
        status['cache'] = {
            'entries': len(cache),
            'memory_usage': f"{len(str(cache))} bytes",
            'session_count': len(conversation_sessions)
        }
        
        # Add application information
        status['application'] = {
            'flask_env': app.config.get('FLASK_ENV', 'development'),
            'debug_mode': app.debug,
            'version': app.config.get('VERSION', '1.0.0')
        }
        
        # Determine overall health - be more lenient
        # Only require FlowManager and basic functionality
        is_healthy = status.get('flowmanager', False)
        
        # Add warnings for services that are down but not critical
        warnings = []
        if not status.get('elasticsearch', False):
            warnings.append("Elasticsearch connection issues")
        if not status.get('openai', False):
            warnings.append("OpenAI API issues")
        
        response_data = {
            'status': 'healthy' if is_healthy else 'unhealthy',
            'timestamp': datetime.utcnow().isoformat(),
            'services': status
        }
        
        if warnings:
            response_data['warnings'] = warnings
        
        # Return 200 even if some services are down, 503 only if core functionality is broken
        status_code = 200 if is_healthy else 503
        
        return jsonify(response_data), status_code
        
    except Exception as e:
        # Fallback health check response
        app.logger.error(f"Health check endpoint error: {e}")
        return jsonify({
            'status': 'error',
            'timestamp': datetime.utcnow().isoformat(),
            'error': 'Health check failed',
            'services': {
                'flowmanager': False,
                'elasticsearch': False,
                'openai': False,
                'prompts': False,
                'query_builders': False
            }
        }), 503


@app.route('/api/query', methods=['POST'])
@limiter.limit("10 per minute")
def api_query():
    """Main API endpoint for processing queries with full debug support and session management"""
    start_time = time.time()
    
    try:
        # Get request data
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        # Get or generate session ID
        session_id = get_session_id(request)
        conversation_memory = get_conversation_memory(session_id)
        
        app.logger.info(f"📥 Received data: {data}")
        app.logger.info(f"🔑 Session ID: {session_id}")
        app.logger.info(f"🧠 Conversation memory length: {len(conversation_memory)} chars")
        
        # Validate input using Pydantic
        try:
            query_input = QueryRequest(**data)
            sanitized_question = query_input.question
            was_sanitized = sanitized_question != data.get('question', '').strip()
            
            app.logger.info(f"✅ Validated question: {sanitized_question}")
            app.logger.info(f"🔒 Input was sanitized: {was_sanitized}")
            
        except Exception as validation_error:
            app.logger.warning(f"❌ Validation failed: {validation_error}")
            return jsonify({'error': str(validation_error)}), 400
        
        # Check if FlowManager is available
        if not flow_manager:
            return jsonify({'error': 'FlowManager not available'}), 503
        
        # Check cache first (include session_id in cache key for memory-based queries)
        query_cache_key = cache_key(f"query:{session_id}:{sanitized_question}")
        cached_response = get_from_cache(query_cache_key)
        if cached_response and not app.debug:  # Skip cache in debug mode
            app.logger.info("🚀 Returning cached response")
            cached_response['from_cache'] = True
            cached_response['processing_time'] = time.time() - start_time
            cached_response['session_id'] = session_id
            return jsonify(cached_response)
        
        # Process query through FlowManager with conversation memory
        # Optimize debug setting: only enable in development environment
        enable_debug = app.debug and app.config.get('FLASK_ENV') != 'production'
        
        try:
            result = asyncio.run(flow_manager.process_query(
                sanitized_question, 
                conversation_memory=conversation_memory,
                debug=enable_debug
            ))
        except Exception as e:
            app.logger.error(f"❌ FlowManager error: {str(e)}")
            return jsonify({
                'error': f'Processing failed: {str(e)}',
                'processing_time': time.time() - start_time,
                'success': False,
                'session_id': session_id
            }), 500
        
        # Calculate processing time
        processing_time = time.time() - start_time
        
        # Get the answer for memory storage
        final_answer = result.get('answer', 'Kunne ikke generere svar')
        
        # Update conversation memory
        update_conversation_memory(session_id, sanitized_question, final_answer)
        
        # Prepare comprehensive debug information
        debug_info = {
            'processing_time': processing_time,
            'input_sanitized': was_sanitized,
            'question_length': len(sanitized_question),
            'cache_entries': len(cache),
            'session_id': session_id,
            'conversation_memory_length': len(conversation_memory),
            'conversation_entries': len(conversation_sessions.get(session_id, [])),
            
            # Flow-specific debug info from FlowManager
            'route_taken': result.get('route_taken', 'unknown'),
            'analysis_result': result.get('analysis', 'unknown'),
            'optimized_question': result.get('optimized', sanitized_question),
            'embeddings_dimensions': len(result.get('embeddings', [])) if result.get('embeddings') else 0,
            'standard_numbers': result.get('standard_numbers', []),
            'memory_terms': result.get('memory_terms', []),  # NEW: Memory-extracted terms
            
            # Query object (this is what you really want to see!)
            'query_object': result.get('query_object', {}),
            
            # Elasticsearch response info
            'elasticsearch_response': {
                'total_hits': result.get('elasticsearch_response', {}).get('hits', {}).get('total', {}).get('value', 0),
                'took': result.get('elasticsearch_response', {}).get('took', 0),
                'max_score': result.get('elasticsearch_response', {}).get('hits', {}).get('max_score', 0)
            },
            
            # Chunk info
            'chunks_info': {
                'chunk_count': len(result.get('elasticsearch_response', {}).get('hits', {}).get('hits', [])),
                'chunks_preview': [
                    {
                        'score': hit.get('_score', 0),
                        'reference': hit.get('_source', {}).get('reference', 'N/A')[:50] + '...',
                        'text_preview': hit.get('_source', {}).get('text', 'N/A')[:100] + '...'
                    }
                    for hit in result.get('elasticsearch_response', {}).get('hits', {}).get('hits', [])[:3]
                ]
            },
            
            # Answer info
            'answer_length': len(result.get('answer', '')),
        }
        
        # Prepare response with comprehensive debug (only in development)
        response_data = {
            'answer': final_answer,
            'debug': debug_info if enable_debug else None,
            'processing_time': processing_time,
            'security_sanitized': was_sanitized,
            'success': True,
            'from_cache': False,
            'session_id': session_id,
            
            # Additional debug fields for UI (only in development)
            'flow_debug': {
                'route': result.get('route_taken', 'unknown'),
                'analysis': result.get('analysis', 'unknown'),
                'optimized': result.get('optimized', sanitized_question),
                'embeddings_dim': len(result.get('embeddings', [])) if result.get('embeddings') else 0,
                'standards': result.get('standard_numbers', []),
                'memory_terms': result.get('memory_terms', []),  # NEW: Memory terms
                'conversation_memory': conversation_memory if enable_debug else None,  # NEW: Memory debug
                'query_object': result.get('query_object', {}) if enable_debug else {},
                'chunks_count': len(result.get('elasticsearch_response', {}).get('hits', {}).get('hits', [])),
                'chunks': result.get('chunks', '') if enable_debug else ''
            } if enable_debug else {
                'route': result.get('route_taken', 'unknown'),
                'analysis': result.get('analysis', 'unknown'),
                'standards': result.get('standard_numbers', []),
                'memory_terms': result.get('memory_terms', []),
                'chunks_count': len(result.get('elasticsearch_response', {}).get('hits', {}).get('hits', []))
            }
        }
        
        # Cache the response (include session for memory-based caching)
        set_cache(query_cache_key, response_data, current_app.config.get('CACHE_TIMEOUT', 3600))
        
        # Log successful processing
        app.logger.info(f"✅ Query processed via FlowManager in {processing_time:.2f}s")
        app.logger.info(f"🛤️ Route taken: {result.get('route_taken', 'unknown')}")
        app.logger.info(f"📊 Chunks retrieved: {len(result.get('elasticsearch_response', {}).get('hits', {}).get('hits', []))}")
        app.logger.info(f"🧠 Memory terms: {result.get('memory_terms', [])}")
        
        return jsonify(response_data)
        
    except Exception as e:
        processing_time = time.time() - start_time
        error_message = str(e)
        
        app.logger.error(f"❌ Error processing query: {error_message}")
        
        return jsonify({
            'error': error_message,
            'processing_time': processing_time,
            'success': False,
            'session_id': get_session_id(request)
        }), 500


@app.route('/api/cache/clear', methods=['POST'])
def clear_cache():
    """Clear the application cache (debug only)"""
    if not app.debug:
        return jsonify({'error': 'Cache clearing only available in debug mode'}), 403
    
    cache.clear()
    cache_expiry.clear()
    
    return jsonify({
        'message': 'Cache cleared successfully',
        'timestamp': datetime.utcnow().isoformat()
    })


@app.route('/api/session/clear', methods=['POST'])
def clear_session():
    """Clear conversation memory for the current session - ROBUST VERSION"""
    try:
        # Get session ID from header eller fra request body
        session_id = request.headers.get('X-Session-ID')
        if not session_id:
            data = request.get_json() or {}
            session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({'error': 'No session ID provided'}), 400
        
        # Clear session memory (don't fail if session doesn't exist)
        cleared = False
        if session_id in conversation_sessions:
            clear_conversation_memory(session_id)
            cleared = True
        
        app.logger.info(f"🧹 Session memory clear requested for {session_id} - {'cleared' if cleared else 'not found (OK)'}")
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'was_cleared': cleared,
            'message': 'Session memory cleared successfully' if cleared else 'Session not found (clean slate)'
        })
        
    except Exception as e:
        app.logger.error(f"❌ Error clearing session: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/session/stats')
def session_stats():
    """Get session and conversation memory statistics"""
    session_id = get_session_id(request)
    conversation_memory = get_conversation_memory(session_id)
    
    return jsonify({
        'session_id': session_id,
        'total_sessions': len(conversation_sessions),
        'current_session_exchanges': len(conversation_sessions.get(session_id, [])),
        'conversation_memory_length': len(conversation_memory),
        'conversation_memory_preview': conversation_memory[:200] + '...' if len(conversation_memory) > 200 else conversation_memory,
        'sessions_list': list(conversation_sessions.keys())[:10] if app.debug else []  # Only show in debug
    })


@app.route('/api/cache/stats')
def cache_stats():
    """Get cache statistics"""
    return jsonify({
        'total_entries': len(cache),
        'cache_keys': list(cache.keys())[:10],  # Show first 10 keys
        'memory_estimate': f"{len(str(cache))} bytes",
        'expired_entries': len([k for k in cache_expiry if datetime.now() > cache_expiry[k]]),
        'session_count': len(conversation_sessions),
        'total_conversations': sum(len(sessions) for sessions in conversation_sessions.values())
    })


@app.route('/api/stream/<session_id>')
def stream_response(session_id):
    """SSE endpoint for streaming responses"""
    from src.sse_manager import create_sse_response
    return create_sse_response(session_id)

@app.route('/api/query/stream', methods=['POST'])
@limiter.limit("5 per minute")
def api_query_stream():
    """Streaming version av query API"""
    start_time = time.time()
    debug_enabled = request.args.get('debug', 'false').lower() == 'true'
    
    # Omfattende logging
    app.logger.info("🚀 STREAM API: Request received")
    app.logger.info(f"🚀 STREAM API: Debug enabled: {debug_enabled}")
    app.logger.info(f"🚀 STREAM API: Request headers: {dict(request.headers)}")
    
    try:
        # Valider request
        if not request.is_json:
            app.logger.error("❌ STREAM API: Request is not JSON")
            return jsonify({'error': 'Request must be JSON'}), 400
        
        data = request.get_json()
        app.logger.info(f"🚀 STREAM API: Request data: {data}")
        
        # Valider input
        try:
            query_req = QueryRequest(**data)
            app.logger.info(f"✅ STREAM API: Question validated: {query_req.question}")
        except Exception as e:
            app.logger.error(f"❌ STREAM API: Validation failed: {e}")
            return jsonify({'error': f'Invalid request data: {e}'}), 400
        
        # Sjekk FlowManager
        if not flow_manager:
            app.logger.error("❌ STREAM API: FlowManager not available")
            return jsonify({'error': 'FlowManager not available'}), 503
        
        # Import SSE manager
        try:
            from src.sse_manager import sse_manager, ProgressStage
            app.logger.info("✅ STREAM API: SSE manager imported successfully")
        except Exception as e:
            app.logger.error(f"❌ STREAM API: Failed to import SSE manager: {e}")
            return jsonify({'error': f'SSE manager not available: {e}'}), 503
        
        # VIKTIG: Bruk SAMME session ID fra frontend for memory continuity
        frontend_session_id = get_session_id(request)
        if not frontend_session_id or frontend_session_id == 'default':
            # Generate new session if none provided
            frontend_session_id = f"session_{int(time.time())}_{str(uuid.uuid4())[:8]}"
        
        # For SSE, generer separat stream session ID
        stream_session_id = f"sse_{int(time.time())}_{str(uuid.uuid4())[:8]}"
        
        app.logger.info(f"🔑 STREAM API: Frontend session ID: {frontend_session_id}")
        app.logger.info(f"🔑 STREAM API: Stream session ID: {stream_session_id}")
        
        # Opprett SSE session
        try:
            sse_manager.create_session(stream_session_id)
            app.logger.info(f"✅ STREAM API: SSE session created: {stream_session_id}")
        except Exception as e:
            app.logger.error(f"❌ STREAM API: Failed to create SSE session: {e}")
            return jsonify({'error': f'Failed to create session: {e}'}), 500
        
        # Get conversation memory using frontend session ID
        conversation_memory = get_conversation_memory(frontend_session_id)
        app.logger.info(f"🧠 STREAM API: Using frontend session ID for memory: {frontend_session_id}")
        app.logger.info(f"🧠 STREAM API: Conversation memory length: {len(conversation_memory)}")
        
        # Start async processing i bakgrunnen med threading
        def process_async():
            app.logger.info(f"🔄 ASYNC: Starting processing for stream session {stream_session_id}")
            
            # FORBEDRET: Proper Flask app context management
            with app.app_context():
                try:
                    start_processing_time = time.time()
                    
                    # Sjekk at FlowManager er tilgjengelig
                    if not flow_manager:
                        app.logger.error(f"❌ ASYNC: FlowManager not available for session {stream_session_id}")
                        sse_manager.send_error(stream_session_id, "FlowManager ikke initialisert")
                        return
                    
                    app.logger.info(f"🔄 ASYNC: FlowManager available for session {stream_session_id}")
                    app.logger.info(f"🔄 ASYNC: Frontend session ID: {frontend_session_id}")
                    app.logger.info(f"🔄 ASYNC: Question: {query_req.question}")
                    
                    # Create new event loop for this thread
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    app.logger.info(f"🔄 ASYNC: Created event loop for session {stream_session_id}")
                    
                    # Sett timeout for hele prosessen (maksimum 45 sekunder for komplekse spørsmål)
                    try:
                        app.logger.info(f"🔄 ASYNC: Starting flow_manager.process_query_with_sse for session {stream_session_id}")
                        
                        result = asyncio.wait_for(
                            flow_manager.process_query_with_sse(
                                query_req.question, 
                                conversation_memory, 
                                stream_session_id, 
                                debug_enabled
                            ),
                            timeout=45.0  # Økt til 45 sekunder for komplekse spørsmål
                        )
                        result = loop.run_until_complete(result)
                        
                        app.logger.info(f"✅ ASYNC: Process completed successfully for session {stream_session_id}")
                        app.logger.info(f"✅ ASYNC: Result keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
                        app.logger.info(f"✅ ASYNC: Answer length: {len(result.get('answer', '')) if isinstance(result, dict) else 'N/A'}")
                        
                    except asyncio.TimeoutError:
                        error_msg = "Prosesseringen tok for lang tid. Prøv med et enklere spørsmål."
                        app.logger.error(f"⏰ ASYNC: Processing timeout for session {stream_session_id}")
                        sse_manager.send_error(stream_session_id, error_msg)
                        return
                    except Exception as processing_error:
                        error_msg = f"Feil under behandling: {str(processing_error)}"
                        app.logger.error(f"❌ ASYNC: Processing error for session {stream_session_id}: {processing_error}")
                        app.logger.error(f"❌ ASYNC: Processing error traceback:")
                        import traceback
                        app.logger.error(traceback.format_exc())
                        sse_manager.send_error(stream_session_id, error_msg)
                        return
                    finally:
                        try:
                            loop.close()
                            app.logger.info(f"🔄 ASYNC: Event loop closed for session {stream_session_id}")
                        except Exception as loop_error:
                            app.logger.warning(f"⚠️ ASYNC: Error closing loop for session {stream_session_id}: {loop_error}")
                    
                    processing_time = time.time() - start_processing_time
                    app.logger.info(f"✅ ASYNC: Processing completed for session {stream_session_id} in {processing_time:.2f}s")
                    
                    # FORBEDRET: Simplified memory saving logic
                    has_valid_question = query_req and query_req.question and len(query_req.question.strip()) > 0
                    has_some_answer = result.get('answer') and len(result.get('answer', '').strip()) > 0
                    
                    should_save_memory = has_valid_question and has_some_answer
                    
                    app.logger.info(f"🧠 ASYNC: Memory decision - Valid question: {has_valid_question}, Has answer: {has_some_answer}, Should save: {should_save_memory}")
                    app.logger.info(f"🧠 ASYNC: Question: '{query_req.question[:50]}...'")
                    app.logger.info(f"🧠 ASYNC: Answer: '{result.get('answer', '')[:50]}...'")
                    
                    if should_save_memory:
                        try:
                            # VIKTIG: Lagre til database med conversation_id hvis tilgjengelig
                            conversation_id = data.get('conversation_id')  # Fra frontend request
                            
                            from src.session_manager import session_manager
                            
                            if conversation_id:
                                # Legg til i eksisterende samtale
                                app.logger.info(f"💾 ASYNC: Adding to existing conversation {conversation_id}")
                                session_manager.add_to_conversation(
                                    conversation_id,
                                    query_req.question, 
                                    result['answer']
                                )
                            else:
                                # Opprett ny samtale
                                app.logger.info(f"💾 ASYNC: Creating new conversation")
                                new_conversation_id = session_manager.save_interaction(
                                    query_req.question, 
                                    result['answer']
                                )
                                app.logger.info(f"✅ ASYNC: Created new conversation {new_conversation_id}")
                            
                            # VIKTIG: Oppdater conversation memory - bruk frontend session ID!
                            app.logger.info(f"🧠 ASYNC: Updating conversation memory for frontend session {frontend_session_id}")
                            app.logger.info(f"🧠 ASYNC: Memory before update: {len(get_conversation_memory(frontend_session_id))} chars")
                            
                            update_conversation_memory(
                                frontend_session_id, 
                                query_req.question, 
                                result['answer']
                            )
                            
                            memory_after = get_conversation_memory(frontend_session_id)
                            app.logger.info(f"✅ ASYNC: Updated conversation memory for session {frontend_session_id}")
                            app.logger.info(f"✅ ASYNC: Memory after update: {len(memory_after)} chars")
                            app.logger.info(f"✅ ASYNC: Memory preview: '{memory_after[:100]}...'")
                            
                        except Exception as save_error:
                            app.logger.error(f"⚠️ ASYNC: Failed to save conversation: {save_error}")
                            import traceback
                            app.logger.error(f"⚠️ ASYNC: Save error traceback: {traceback.format_exc()}")
                    else:
                        app.logger.warning(f"⚠️ ASYNC: Skipping memory save for session {stream_session_id}")
                        app.logger.warning(f"⚠️ ASYNC: Reason - has_valid_question: {has_valid_question}, has_some_answer: {has_some_answer}")
                    
                except Exception as e:
                    app.logger.error(f"❌ ASYNC: Unexpected error for session {stream_session_id}: {e}")
                    import traceback
                    app.logger.error(f"❌ ASYNC: Full traceback: {traceback.format_exc()}")
                    sse_manager.send_error(stream_session_id, f"Uventet feil: {str(e)}")
                finally:
                    app.logger.info(f"🏁 ASYNC: Thread completed for session {stream_session_id}")
        
        # Start processing i bakgrunnstråd med daemon=False for robusthet
        import threading
        processing_thread = threading.Thread(
            target=process_async, 
            daemon=False,  # Ikke daemon for å sikre fullføring
            name=f"ProcessingThread-{stream_session_id}"
        )
        processing_thread.start()
        app.logger.info(f"🚀 STREAM API: Started background processing thread for session {stream_session_id}")
        
        # Return frontend session_id for conversation memory continuity
        response_data = {
            'session_id': frontend_session_id,  # Return frontend session_id for memory continuity
            'stream_session_id': stream_session_id,    # Stream session for SSE functionality
            'stream_url': f'/api/stream/{stream_session_id}',
            'status': 'started',
            'debug': debug_enabled
        }
        
        app.logger.info(f"✅ STREAM API: Returning response: {response_data}")
        app.logger.info(f"🔑 STREAM API: Frontend session_id: {frontend_session_id}, Stream session_id: {stream_session_id}")
        return jsonify(response_data)
        
    except Exception as e:
        processing_time = time.time() - start_time
        error_msg = f"Stream API error: {str(e)}"
        app.logger.error(f"❌ STREAM API: {error_msg}")
        app.logger.error(f"❌ STREAM API: Processing time: {processing_time:.2f}s")
        
        return jsonify({
            'error': 'Internal server error', 
            'debug_error': error_msg if app.debug else None,
            'processing_time': processing_time
        }), 500

@app.route('/api/conversations')
def get_conversations():
    """Hent samtalehistorikk"""
    from src.session_manager import session_manager
    
    try:
        conversations = session_manager.get_conversation_history()
        
        # Konverter til JSON format
        result = []
        for conv in conversations:
            result.append({
                'id': conv.id,
                'title': conv.title,
                'created_at': conv.created_at.isoformat(),
                'last_message_at': conv.last_message_at.isoformat(),
                'message_count': conv.message_count
            })
        
        return jsonify({'conversations': result})
        
    except Exception as e:
        app.logger.error(f"Get conversations error: {e}")
        return jsonify({'error': 'Could not fetch conversations'}), 500

@app.route('/api/conversations/<conversation_id>')
def get_conversation(conversation_id):
    """Hent spesifikk samtale med meldinger"""
    from src.session_manager import session_manager
    
    try:
        conversation = session_manager.get_conversation_by_id(conversation_id)
        if not conversation:
            return jsonify({'error': 'Conversation not found'}), 404
        
        messages = session_manager.get_conversation_messages(conversation_id)
        
        result = {
            'id': conversation.id,
            'title': conversation.title,
            'created_at': conversation.created_at.isoformat(),
            'last_message_at': conversation.last_message_at.isoformat(),
            'messages': [
                {
                    'id': msg.id,
                    'question': msg.question,
                    'answer': msg.answer,
                    'timestamp': msg.timestamp.isoformat()
                }
                for msg in messages
            ]
        }
        
        return jsonify(result)
        
    except Exception as e:
        app.logger.error(f"Get conversation error: {e}")
        return jsonify({'error': 'Could not fetch conversation'}), 500

@app.route('/api/conversations', methods=['POST'])
def create_new_conversation():
    """Start ny samtale"""
    try:
        # Generer ny session ID
        new_session_id = f"session_{int(time.time())}_{str(uuid.uuid4())[:8]}"
        
        # Clear conversation memory for new session
        clear_conversation_memory(new_session_id)
        
        return jsonify({
            'session_id': new_session_id,
            'status': 'created'
        })
        
    except Exception as e:
        app.logger.error(f"Create conversation error: {e}")
        return jsonify({'error': 'Could not create conversation'}), 500

@app.route('/api/session/save-memory', methods=['POST'])
def save_conversation_memory():
    """
    Eksplisitt lagring av konversasjonsminne fra frontend
    Dette sikrer at minnet blir lagret selv når streaming feiler
    """
    try:
        data = request.get_json()
        session_id = get_session_id(request)
        
        if not data or 'user_message' not in data or 'system_response' not in data:
            return jsonify({'error': 'Missing required fields: user_message, system_response'}), 400
        
        user_message = data['user_message'].strip()
        system_response = data['system_response'].strip()
        
        if not user_message or not system_response:
            return jsonify({'error': 'Both user_message and system_response must be non-empty'}), 400
        
        # Lagre conversation memory
        update_conversation_memory(session_id, user_message, system_response)
        
        # Hent oppdatert memory for bekreftelse
        memory = get_conversation_memory(session_id)
        
        app.logger.info(f"✅ MANUAL SAVE: Conversation memory saved for session {session_id}")
        app.logger.info(f"✅ MANUAL SAVE: Memory length: {len(memory)} chars")
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'memory_length': len(memory),
            'message': 'Conversation memory saved successfully'
        })
        
    except Exception as e:
        app.logger.error(f"❌ MANUAL SAVE: Failed to save conversation memory: {e}")
        return jsonify({'error': f'Failed to save memory: {str(e)}'}), 500

@app.route('/api/session/rebuild', methods=['POST'])
def rebuild_conversation_memory():
    """
    Gjenoppbygg conversation memory fra eksisterende meldinger
    Brukes når brukeren bytter til en eksisterende samtale
    """
    try:
        data = request.get_json()
        session_id = get_session_id(request)
        
        if not data or 'conversation_id' not in data or 'messages' not in data:
            return jsonify({'error': 'Missing required fields: conversation_id, messages'}), 400
        
        conversation_id = data['conversation_id']
        messages = data['messages']
        
        app.logger.info(f"🔄 REBUILD: Starting memory rebuild for conversation {conversation_id}")
        app.logger.info(f"🔄 REBUILD: Session ID: {session_id}")
        app.logger.info(f"🔄 REBUILD: Messages to rebuild: {len(messages)}")
        
        # Først, rydd eksisterende memory for denne sessionen
        clear_conversation_memory(session_id)
        
        # Gjenoppbygg memory fra meldinger (bare de siste 5 for å ikke overfylle)
        recent_messages = messages[-5:] if len(messages) > 5 else messages
        
        for msg in recent_messages:
            if 'question' in msg and 'answer' in msg:
                update_conversation_memory(session_id, msg['question'], msg['answer'])
                app.logger.debug(f"🔄 REBUILD: Added exchange - Q: {msg['question'][:50]}...")
        
        # Hent den gjenoppbygde memoryen for bekreftelse
        rebuilt_memory = get_conversation_memory(session_id)
        
        app.logger.info(f"✅ REBUILD: Memory rebuilt successfully for conversation {conversation_id}")
        app.logger.info(f"✅ REBUILD: Rebuilt memory length: {len(rebuilt_memory)} chars")
        app.logger.info(f"✅ REBUILD: Memory preview: {rebuilt_memory[:150]}...")
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'conversation_id': conversation_id,
            'messages_processed': len(recent_messages),
            'memory_length': len(rebuilt_memory),
            'memory_preview': rebuilt_memory[:200] + '...' if len(rebuilt_memory) > 200 else rebuilt_memory,
            'message': 'Conversation memory rebuilt successfully'
        })
        
    except Exception as e:
        app.logger.error(f"❌ REBUILD: Failed to rebuild conversation memory: {e}")
        import traceback
        app.logger.error(f"❌ REBUILD: Traceback: {traceback.format_exc()}")
        return jsonify({'error': f'Failed to rebuild memory: {str(e)}'}), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors - redirect web requests to main page, return JSON for API requests"""
    # For API requests (starts with /api/), return JSON
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Endpoint not found'}), 404
    
    # For web requests, redirect to main application
    return render_template('index.html'), 200


@app.route('/favicon.ico')
def favicon():
    """Handle favicon requests"""
    return '', 204


@app.route('/<path:path>')
def catch_all(path):
    """Catch all routes and serve main app for non-API paths"""
    # Don't catch API routes
    if path.startswith('api/'):
        return jsonify({'error': 'API endpoint not found'}), 404
    
    # Serve main app for all other paths
    return render_template('index.html')


@app.errorhandler(429)
def ratelimit_handler(e):
    """Handle rate limit exceeded"""
    return jsonify({
        'error': 'Rate limit exceeded. Please wait before making more requests.',
        'retry_after': getattr(e, 'retry_after', None)
    }), 429


@app.errorhandler(500)
def internal_error(error):
    """Handle internal server errors"""
    app.logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    # Sørg for at AI-titler er initialisert
    try:
        from src.session_manager import session_manager
        if session_manager.ai_titles_enabled:
            app.logger.info("✅ AI-genererte samtale-titler aktivert i produksjon")
        else:
            app.logger.info("⚠️ AI-titler ikke aktivert - bruker fallback-metoder")
    except Exception as e:
        app.logger.warning(f"⚠️ Kunne ikke sjekke AI-titler status: {e}")
    
    # Railway og produksjon konfigurasjon
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    
    # Detekter Railway miljø
    is_railway = os.environ.get('RAILWAY_ENVIRONMENT') is not None
    is_production = app.config.get('FLASK_ENV') == 'production'
    
    if is_railway:
        app.logger.info(f"🚄 Kjører på Railway - Port: {port}")
        app.logger.info(f"🤖 AI-titler: {'Aktivert' if session_manager.ai_titles_enabled else 'Fallback-modus'}")
    
    if is_production and not is_railway:
        # Bruk Gunicorn for produksjon (ikke Railway)
        app.logger.info("🚀 Produksjonsmodus - bruk Gunicorn for beste ytelse")
        app.logger.info(f"Eksempel: gunicorn --bind {host}:{port} --workers 4 app:app")
    else:
        # Development eller Railway (Railway håndterer Gunicorn automatisk)
        app.run(host=host, port=port, debug=False)
    
    # Log konfigurasjon
    app.logger.info(f"🌐 Server kjører på http://{host}:{port}")
    if app.config.get('OPENAI_API_KEY'):
        app.logger.info("🤖 OpenAI: Konfigurert")
    else:
        app.logger.warning("⚠️ OpenAI: Ikke konfigurert") 