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

# Simple in-memory cache for development
cache = {}
cache_expiry = {}

# Session storage for conversation memory
conversation_sessions = {}

def get_session_id(request_obj) -> str:
    """Generate or retrieve session ID from request headers"""
    session_id = request_obj.headers.get('X-Session-ID')
    if not session_id:
        session_id = f"session_{int(time.time())}_{str(uuid.uuid4())[:8]}"
    return session_id

def get_conversation_memory(session_id: str) -> str:
    """Get formatted conversation memory for session"""
    if session_id not in conversation_sessions or not conversation_sessions[session_id]:
        return "0"
    
    history = conversation_sessions[session_id]
    if not history:
        return "0"
    
    # Format last 10 exchanges (20 messages total)
    formatted_parts = []
    for entry in history[-10:]:
        # Clean and escape user/system messages for prompt safety
        user_clean = entry['user'].replace('`', "'").replace('"', "'").replace('\n', ' ').replace('\r', ' ')
        system_clean = entry['system'].replace('`', "'").replace('"', "'").replace('\n', ' ').replace('\r', ' ')
        
        formatted_parts.append(f"Bruker: `{user_clean}`")
        formatted_parts.append(f"System: `{system_clean}`")
    
    return "; ".join(formatted_parts) + ";"

def update_conversation_memory(session_id: str, user_message: str, system_response: str):
    """Update conversation memory with new exchange"""
    if session_id not in conversation_sessions:
        conversation_sessions[session_id] = []
    
    # Clean messages before storing
    user_clean = user_message.strip()
    system_clean = system_response.strip()[:400]  # Shorter limit to prevent token issues
    
    # Add new exchange
    conversation_sessions[session_id].append({
        'user': user_clean,
        'system': system_clean,
        'timestamp': datetime.utcnow().isoformat()
    })
    
    # Keep only last 10 exchanges
    if len(conversation_sessions[session_id]) > 10:
        conversation_sessions[session_id] = conversation_sessions[session_id][-10:]

def clear_conversation_memory(session_id: str):
    """Clear conversation memory for session"""
    if session_id in conversation_sessions:
        del conversation_sessions[session_id]

def cache_key(text: str) -> str:
    """Generate cache key from text"""
    return hashlib.md5(text.encode()).hexdigest()

def get_from_cache(key: str) -> Optional[Any]:
    """Get value from cache if not expired"""
    if key in cache and key in cache_expiry:
        if datetime.now() < cache_expiry[key]:
            return cache[key]
        else:
            # Remove expired item
            del cache[key]
            del cache_expiry[key]
    return None

def set_cache(key: str, value: Any, ttl_seconds: int = 3600):
    """Set value in cache with TTL"""
    cache[key] = value
    cache_expiry[key] = datetime.now() + timedelta(seconds=ttl_seconds)

def cache_response(ttl_seconds: int = 3600):
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
    """Warmup services to avoid cold start delays"""
    if flow_manager:
        try:
            app.logger.info("🔥 Starting service warmup...")
            
            # Warmup embedding API with a simple query
            embedding_client = flow_manager.elasticsearch_client
            warmup_embedding = await asyncio.get_event_loop().run_in_executor(
                None, embedding_client.get_embeddings_from_api, "warmup query", False
            )
            if warmup_embedding:
                app.logger.info("✅ Embedding API warmed up successfully")
            else:
                app.logger.warning("⚠️ Embedding API warmup returned no results")
            
            # Warmup OpenAI with a simple semantic optimization
            prompt_manager = flow_manager.prompt_manager
            warmup_openai = await asyncio.get_event_loop().run_in_executor(
                None, prompt_manager.execute_optimize_semantic, "warmup", "", False
            )
            if warmup_openai:
                app.logger.info("✅ OpenAI API warmed up successfully")
            else:
                app.logger.warning("⚠️ OpenAI API warmup failed")
                
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
    import threading
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
    """Health check endpoint with cache info"""
    status = HealthCheck.get_system_status(app)
    
    # Add cache information
    status['cache'] = {
        'entries': len(cache),
        'memory_usage': f"{len(str(cache))} bytes"
    }
    
    # Determine overall health
    is_healthy = all([
        status['elasticsearch'] or True,  # Allow ES to be down for development
        status['openai']
    ])
    
    return jsonify({
        'status': 'healthy' if is_healthy else 'degraded',
        'timestamp': datetime.utcnow().isoformat(),
        'services': status
    }), 200 if is_healthy else 503


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
    """Clear conversation memory for specific session"""
    session_id = get_session_id(request)
    clear_conversation_memory(session_id)
    
    return jsonify({
        'message': 'Session memory cleared successfully',
        'session_id': session_id,
        'timestamp': datetime.utcnow().isoformat()
    })


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
        
        # Generer session ID
        session_id = f"stream_{int(time.time())}_{str(uuid.uuid4())[:8]}"
        app.logger.info(f"🔑 STREAM API: Generated session ID: {session_id}")
        
        # Opprett SSE session
        try:
            sse_manager.create_session(session_id)
            app.logger.info(f"✅ STREAM API: SSE session created: {session_id}")
        except Exception as e:
            app.logger.error(f"❌ STREAM API: Failed to create SSE session: {e}")
            return jsonify({'error': f'Failed to create session: {e}'}), 500
        
        # Get conversation memory
        conversation_memory = get_conversation_memory(get_session_id(request))
        app.logger.info(f"🧠 STREAM API: Conversation memory length: {len(conversation_memory)}")
        
        # Start async processing i bakgrunnen med threading
        def process_async():
            app.logger.info(f"🔄 ASYNC: Starting processing for session {session_id}")
            start_processing_time = time.time()
            
            try:
                if flow_manager:
                    # Opprett ny event loop for denne tråden
                    import asyncio
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    app.logger.info(f"🔄 ASYNC: Created event loop for session {session_id}")
                    
                    # Sett timeout for hele prosessen (maksimum 30 sekunder)
                    try:
                        result = asyncio.wait_for(
                            flow_manager.process_query_with_sse(
                                query_req.question, 
                                conversation_memory, 
                                session_id, 
                                debug_enabled
                            ),
                            timeout=30.0  # 30 sekunder timeout
                        )
                        result = loop.run_until_complete(result)
                    except asyncio.TimeoutError:
                        app.logger.error(f"⏰ ASYNC: Processing timeout for session {session_id}")
                        sse_manager.send_error(session_id, "Prosesseringen tok for lang tid. Prøv med et enklere spørsmål.")
                        return
                    
                    processing_time = time.time() - start_processing_time
                    app.logger.info(f"✅ ASYNC: Processing completed for session {session_id} in {processing_time:.2f}s")
                    
                    # Lagre samtale hvis suksessfull
                    if not result.get('error') and result.get('answer'):
                        try:
                            from src.session_manager import session_manager
                            conversation_id = data.get('conversation_id')
                            if conversation_id:
                                session_manager.add_message_to_conversation(
                                    conversation_id, query_req.question, result['answer']
                                )
                                app.logger.info(f"✅ ASYNC: Added message to existing conversation {conversation_id}")
                            else:
                                # Opprett ny samtale
                                new_conversation_id = session_manager.create_conversation(
                                    query_req.question, result['answer']
                                )
                                result['conversation_id'] = new_conversation_id
                                app.logger.info(f"✅ ASYNC: Created new conversation {new_conversation_id}")
                            
                            # Oppdater conversation memory
                            update_conversation_memory(
                                get_session_id(request), 
                                query_req.question, 
                                result['answer']
                            )
                            app.logger.info(f"✅ ASYNC: Updated conversation memory")
                            
                        except Exception as e:
                            app.logger.error(f"⚠️ ASYNC: Failed to save conversation: {e}")
                    
                    loop.close()
                    app.logger.info(f"✅ ASYNC: Event loop closed for session {session_id}")
                    
                else:
                    app.logger.error(f"❌ ASYNC: FlowManager not available for session {session_id}")
                    sse_manager.send_error(session_id, "FlowManager ikke initialisert")
                    
            except Exception as e:
                app.logger.error(f"❌ ASYNC: Error processing session {session_id}: {e}")
                sse_manager.send_error(session_id, f"Feil under behandling: {str(e)}")
            finally:
                # Ensure session cleanup after processing
                try:
                    if 'loop' in locals():
                        loop.close()
                except:
                    pass
        
        # Start processing i bakgrunnstråd
        import threading
        processing_thread = threading.Thread(target=process_async, daemon=True)
        processing_thread.start()
        app.logger.info(f"🚀 STREAM API: Started background processing thread for session {session_id}")
        
        # Returner session info
        response_data = {
            'session_id': session_id,
            'stream_url': f'/api/stream/{session_id}',
            'status': 'started',
            'debug': debug_enabled
        }
        
        app.logger.info(f"✅ STREAM API: Returning response: {response_data}")
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

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({'error': 'Endpoint not found'}), 404


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
    # Development server
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    app.logger.info(f"🚀 Starting StandardGPT on port {port} (debug={debug})")
    app.logger.info(f"🔧 Configuration: {config_class.__name__}")
    
    if flow_manager:
        app.logger.info("🔍 FlowManager: Connected")
    else:
        app.logger.warning("⚠️ FlowManager: Disconnected")
    
    if app.config.get('OPENAI_API_KEY'):
        app.logger.info("🤖 OpenAI: Configured")
    else:
        app.logger.warning("⚠️ OpenAI: Not configured")
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug,
        threaded=True
    ) 