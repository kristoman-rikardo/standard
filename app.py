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
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
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
    """Main API endpoint for processing queries with full debug support"""
    start_time = time.time()
    
    try:
        # Get request data
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        app.logger.info(f"📥 Received data: {data}")
        
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
        
        # Check cache first
        query_cache_key = cache_key(f"query:{sanitized_question}")
        cached_response = get_from_cache(query_cache_key)
        if cached_response and not app.debug:  # Skip cache in debug mode
            app.logger.info("🚀 Returning cached response")
            cached_response['from_cache'] = True
            cached_response['processing_time'] = time.time() - start_time
            return jsonify(cached_response)
        
        # Process query through FlowManager with full debug
        try:
            result = asyncio.run(flow_manager.process_query(sanitized_question, debug=True))
        except Exception as e:
            app.logger.error(f"❌ FlowManager error: {str(e)}")
            return jsonify({
                'error': f'Processing failed: {str(e)}',
                'processing_time': time.time() - start_time,
                'success': False
            }), 500
        
        # Calculate processing time
        processing_time = time.time() - start_time
        
        # Prepare comprehensive debug information
        debug_info = {
            'processing_time': processing_time,
            'input_sanitized': was_sanitized,
            'question_length': len(sanitized_question),
            'cache_entries': len(cache),
            
            # Flow-specific debug info from FlowManager
            'route_taken': result.get('route_taken', 'unknown'),
            'analysis_result': result.get('analysis', 'unknown'),
            'optimized_question': result.get('optimized', sanitized_question),
            'embeddings_dimensions': len(result.get('embeddings', [])) if result.get('embeddings') else 0,
            'standard_numbers': result.get('standard_numbers', []),
            
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
        
        # Prepare response with comprehensive debug
        response_data = {
            'answer': result.get('answer', 'Kunne ikke generere svar'),
            'debug': debug_info if app.debug else None,
            'processing_time': processing_time,
            'security_sanitized': was_sanitized,
            'success': True,
            'from_cache': False,
            
            # Additional debug fields for UI
            'flow_debug': {
                'route': result.get('route_taken', 'unknown'),
                'analysis': result.get('analysis', 'unknown'),
                'optimized': result.get('optimized', sanitized_question),
                'embeddings_dim': len(result.get('embeddings', [])) if result.get('embeddings') else 0,
                'standards': result.get('standard_numbers', []),
                'query_object': result.get('query_object', {}),
                'chunks_count': len(result.get('elasticsearch_response', {}).get('hits', {}).get('hits', [])),
                'chunks': result.get('chunks', '')
            } if app.debug else None
        }
        
        # Cache the response
        set_cache(query_cache_key, response_data, current_app.config.get('CACHE_TIMEOUT', 3600))
        
        # Log successful processing
        app.logger.info(f"✅ Query processed via FlowManager in {processing_time:.2f}s")
        app.logger.info(f"🛤️ Route taken: {result.get('route_taken', 'unknown')}")
        app.logger.info(f"📊 Chunks retrieved: {len(result.get('elasticsearch_response', {}).get('hits', {}).get('hits', []))}")
        
        return jsonify(response_data)
        
    except Exception as e:
        processing_time = time.time() - start_time
        error_message = str(e)
        
        app.logger.error(f"❌ Error processing query: {error_message}")
        
        return jsonify({
            'error': error_message,
            'processing_time': processing_time,
            'success': False
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


@app.route('/api/cache/stats')
def cache_stats():
    """Get cache statistics"""
    return jsonify({
        'total_entries': len(cache),
        'cache_keys': list(cache.keys())[:10],  # Show first 10 keys
        'memory_estimate': f"{len(str(cache))} bytes",
        'expired_entries': len([k for k in cache_expiry if datetime.now() > cache_expiry[k]])
    })


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