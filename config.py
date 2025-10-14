"""
Configuration module for StandardGPT Flask application
Supports different environments: development, production, testing
"""

import os
import logging
from datetime import timedelta
from pathlib import Path


class Config:
    """Base configuration class"""
    
    # Application settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here-change-in-production'
    APP_NAME = 'StandardGPT'
    VERSION = '1.0.0'
    
    # Security settings
    WTF_CSRF_ENABLED = True
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    # Rate limiting
    RATELIMIT_STORAGE_URL = os.environ.get('REDIS_URL', 'memory://')
    RATELIMIT_DEFAULT = "100 per hour"
    RATELIMIT_STRATEGY = "fixed-window"
    
    # ElasticSearch configuration
    ELASTICSEARCH_URL = os.environ.get('ELASTICSEARCH_URL', 'https://my-elasticsearch-project-f89a7b.es.eastus.azure.elastic.cloud:443')
    ELASTICSEARCH_INDEX = os.environ.get('ELASTICSEARCH_INDEX', 'standard_prod')
    ELASTICSEARCH_TIMEOUT = 30
    ELASTICSEARCH_MAX_RETRIES = 3
    
    # OpenAI configuration with MAXIMUM tokens and deterministic temperature
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4o')
    OPENAI_MAX_TOKENS = int(os.environ.get('OPENAI_MAX_TOKENS', '4000'))  # Maximum tokens
    OPENAI_TEMPERATURE = float(os.environ.get('OPENAI_TEMPERATURE', '0.0'))  # Deterministic responses
    
    # Input validation
    MAX_QUESTION_LENGTH = int(os.environ.get('MAX_QUESTION_LENGTH', '1000'))
    MIN_QUESTION_LENGTH = int(os.environ.get('MIN_QUESTION_LENGTH', '3'))
    ALLOWED_HTML_TAGS = []  # No HTML tags allowed by default
    
    # Logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('LOG_FILE', 'standardgpt.log')
    LOG_MAX_BYTES = int(os.environ.get('LOG_MAX_BYTES', '10485760'))  # 10MB
    LOG_BACKUP_COUNT = int(os.environ.get('LOG_BACKUP_COUNT', '5'))

    # UI password protection (simple cookie gate)
    UI_PASSWORD = os.environ.get('UI_PASSWORD', 'standard2025')
    UI_AUTH_COOKIE_NAME = os.environ.get('UI_AUTH_COOKIE_NAME', 'ui_auth')
    UI_AUTH_COOKIE_MAX_AGE_DAYS = int(os.environ.get('UI_AUTH_COOKIE_MAX_AGE_DAYS', '30'))
    
    # Performance
    RESPONSE_TIMEOUT = int(os.environ.get('RESPONSE_TIMEOUT', '30'))
    MAX_SEARCH_RESULTS = int(os.environ.get('MAX_SEARCH_RESULTS', '10'))
    CACHE_TIMEOUT = int(os.environ.get('CACHE_TIMEOUT', '3600'))  # 1 hour
    
    # Static files (for production)
    STATIC_FOLDER = 'static'
    STATIC_URL_PATH = '/static'
    
    # Template settings
    TEMPLATES_AUTO_RELOAD = False
    
    @staticmethod
    def init_app(app):
        """Initialize the application with this configuration"""
        pass


class DevelopmentConfig(Config):
    """Development configuration"""
    
    DEBUG = True
    TESTING = False
    
    # More lenient security for development
    SESSION_COOKIE_SECURE = False
    WTF_CSRF_ENABLED = False
    
    # Template auto-reload for development
    TEMPLATES_AUTO_RELOAD = True
    
    # Logging
    LOG_LEVEL = 'DEBUG'
    
    # Rate limiting - more generous for development
    RATELIMIT_DEFAULT = "1000 per hour"
    
    @staticmethod
    def init_app(app):
        Config.init_app(app)
        
        # Development-specific initialization
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        )


class ProductionConfig(Config):
    """Production configuration"""
    
    DEBUG = False
    TESTING = False
    
    # Strict security for production
    SESSION_COOKIE_SECURE = True
    WTF_CSRF_ENABLED = True
    
    # Logging
    LOG_LEVEL = 'WARNING'
    
    # Performance optimizations
    TEMPLATES_AUTO_RELOAD = False
    
    @staticmethod
    def init_app(app):
        Config.init_app(app)
        
        # Production-specific initialization
        from logging.handlers import RotatingFileHandler
        
        # File logging
        if not os.path.exists('logs'):
            os.mkdir('logs')
        
        file_handler = RotatingFileHandler(
            f'logs/{Config.LOG_FILE}',
            maxBytes=Config.LOG_MAX_BYTES,
            backupCount=Config.LOG_BACKUP_COUNT
        )
        
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info(f'{Config.APP_NAME} startup')


class TestingConfig(Config):
    """Testing configuration"""
    
    DEBUG = True
    TESTING = True
    
    # Disable security features for testing
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    
    # Use in-memory storage for testing
    RATELIMIT_STORAGE_URL = 'memory://'
    
    # Testing-specific settings
    ELASTICSEARCH_INDEX = 'standards_test'
    
    # Faster timeouts for testing
    RESPONSE_TIMEOUT = 5
    ELASTICSEARCH_TIMEOUT = 5
    
    @staticmethod
    def init_app(app):
        Config.init_app(app)


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config():
    """Get the configuration class based on environment"""
    env = os.environ.get('FLASK_ENV', 'development').lower()
    return config.get(env, config['default'])


class HealthCheck:
    """Health check utilities"""
    
    @staticmethod
    def check_elasticsearch(app):
        """Check ElasticSearch connection"""
        try:
            # Use our custom Elasticsearch client
            from src.elasticsearch_client import ElasticsearchClient
            es_client = ElasticsearchClient()
            return es_client.health_check(debug=False)
        except Exception as e:
            app.logger.error(f"ElasticSearch health check failed: {e}")
            return False
    
    @staticmethod
    def check_openai(app):
        """Check OpenAI API"""
        try:
            if not app.config.get('OPENAI_API_KEY'):
                return False
                
            from openai import OpenAI
            client = OpenAI(api_key=app.config['OPENAI_API_KEY'])
            
            # Simple test request - use configured model
            model = app.config.get('OPENAI_MODEL', 'gpt-4o')
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=5
            )
            return True
        except Exception as e:
            app.logger.error(f"OpenAI health check failed: {e}")
            return False
    
    @staticmethod
    def get_system_status(app):
        """Get overall system status"""
        return {
            'elasticsearch': HealthCheck.check_elasticsearch(app),
            'openai': HealthCheck.check_openai(app),
            'timestamp': os.environ.get('BUILD_TIME', 'unknown')
        }


class SecurityConfig:
    """Security-related configuration and utilities"""
    
    # Content Security Policy
    CSP_POLICY = {
        'default-src': "'self'",
        'script-src': "'self' 'unsafe-inline'",
        'style-src': "'self' 'unsafe-inline'",
        'img-src': "'self' data:",
        'font-src': "'self'",
        'connect-src': "'self'",
        'frame-ancestors': "'none'",
    }
    
    # Security headers
    SECURITY_HEADERS = {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block',
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        'Referrer-Policy': 'strict-origin-when-cross-origin'
    }
    
    @staticmethod
    def get_csp_header():
        """Generate Content Security Policy header"""
        return '; '.join([f"{key} {value}" for key, value in SecurityConfig.CSP_POLICY.items()])
    
    @staticmethod
    def apply_security_headers(response):
        """Apply security headers to response"""
        # Apply all security headers
        for header, value in SecurityConfig.SECURITY_HEADERS.items():
            response.headers[header] = value
        
        # Apply CSP
        response.headers['Content-Security-Policy'] = SecurityConfig.get_csp_header()
        
        return response 