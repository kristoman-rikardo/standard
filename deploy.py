#!/usr/bin/env python3
"""
StandardGPT Production Deployment Script
Handles production deployment with proper WSGI server, logging, and security
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path


class DeploymentManager:
    """Manages StandardGPT deployment"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.required_env_vars = [
            'OPENAI_API_KEY',
            'ELASTICSEARCH_URL',
            'SECRET_KEY'
        ]
        
    def check_environment(self):
        """Check that all required environment variables are set"""
        missing_vars = []
        for var in self.required_env_vars:
            if not os.environ.get(var):
                missing_vars.append(var)
        
        if missing_vars:
            print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
            print("\nSet them using:")
            for var in missing_vars:
                print(f"export {var}='your_value_here'")
            return False
        
        print("✅ All required environment variables are set")
        return True
    
    def install_dependencies(self):
        """Install production dependencies"""
        print("📦 Installing dependencies...")
        
        # Install gunicorn if not present
        try:
            subprocess.run([sys.executable, '-m', 'pip', 'install', 'gunicorn'], check=True)
            print("✅ Gunicorn installed")
        except subprocess.CalledProcessError:
            print("❌ Failed to install gunicorn")
            return False
        
        # Install other requirements
        requirements_file = self.project_root / 'requirements.txt'
        if requirements_file.exists():
            try:
                subprocess.run([
                    sys.executable, '-m', 'pip', 'install', '-r', str(requirements_file)
                ], check=True)
                print("✅ Dependencies installed from requirements.txt")
            except subprocess.CalledProcessError:
                print("❌ Failed to install dependencies")
                return False
        
        return True
    
    def create_systemd_service(self, port=5000, workers=4):
        """Create systemd service file for production"""
        service_content = f"""[Unit]
Description=StandardGPT Application
After=network.target

[Service]
Type=notify
User=www-data
Group=www-data
WorkingDirectory={self.project_root}
Environment=FLASK_ENV=production
Environment=PORT={port}
ExecStart={sys.executable} -m gunicorn --workers {workers} --bind 0.0.0.0:{port} --timeout 120 --worker-class sync app:app
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
"""
        
        service_file = Path('/etc/systemd/system/standardgpt.service')
        print(f"📝 Creating systemd service file at {service_file}")
        print("Note: You may need to run this with sudo privileges")
        print("\nService file content:")
        print(service_content)
        
        return service_content
    
    def create_nginx_config(self, domain='localhost', port=5000):
        """Create nginx configuration"""
        nginx_config = f"""server {{
    listen 80;
    server_name {domain};
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    
    # Static files
    location /static {{
        alias {self.project_root}/static;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }}
    
    # Application
    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Buffer settings
        proxy_buffering on;
        proxy_buffer_size 4k;
        proxy_buffers 8 4k;
    }}
    
    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/m;
    location /api/ {{
        limit_req zone=api burst=20 nodelay;
        proxy_pass http://127.0.0.1:{port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""
        
        print(f"🌐 Nginx configuration for {domain}:")
        print(nginx_config)
        print(f"\nSave this to: /etc/nginx/sites-available/standardgpt")
        print(f"Then run: sudo ln -s /etc/nginx/sites-available/standardgpt /etc/nginx/sites-enabled/")
        
        return nginx_config
    
    def create_docker_setup(self):
        """Create Docker setup files"""
        
        # Dockerfile
        dockerfile_content = f"""FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    gcc \\
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir gunicorn

# Copy application code
COPY . .

# Create non-root user
RUN useradd --create-home --shell /bin/bash app
RUN chown -R app:app /app
USER app

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \\
    CMD curl -f http://localhost:5000/health || exit 1

# Run application
CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:5000", "--timeout", "120", "app:app"]
"""
        
        # Docker Compose
        docker_compose_content = """version: '3.8'

services:
  web:
    build: .
    ports:
      - "5000:5000"
    environment:
      - FLASK_ENV=production
      - ELASTICSEARCH_URL=http://elasticsearch:9200
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - SECRET_KEY=${SECRET_KEY}
    depends_on:
      - elasticsearch
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.11.0
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - "ES_JAVA_OPTS=-Xms512m -Xmx512m"
    ports:
      - "9200:9200"
    volumes:
      - elasticsearch_data:/usr/share/elasticsearch/data
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf
      - ./static:/app/static
    depends_on:
      - web
    restart: unless-stopped

volumes:
  elasticsearch_data:
"""
        
        print("🐳 Docker setup files:")
        print("\n=== Dockerfile ===")
        print(dockerfile_content)
        print("\n=== docker-compose.yml ===")
        print(docker_compose_content)
        
        return dockerfile_content, docker_compose_content
    
    def run_production_server(self, port=5000, workers=4):
        """Run production server with gunicorn"""
        print(f"🚀 Starting production server on port {port} with {workers} workers")
        
        if not self.check_environment():
            return False
        
        # Set production environment
        os.environ['FLASK_ENV'] = 'production'
        
        # Run gunicorn
        cmd = [
            'gunicorn',
            '--workers', str(workers),
            '--bind', f'0.0.0.0:{port}',
            '--timeout', '120',
            '--worker-class', 'sync',
            '--access-logfile', '-',
            '--error-logfile', '-',
            'app:app'
        ]
        
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to start production server: {e}")
            return False
        except KeyboardInterrupt:
            print("\n👋 Server stopped by user")
            return True
        
        return True


def main():
    """Main deployment script"""
    parser = argparse.ArgumentParser(description='StandardGPT Deployment Manager')
    parser.add_argument('command', choices=[
        'check', 'install', 'systemd', 'nginx', 'docker', 'run'
    ], help='Deployment command')
    parser.add_argument('--port', type=int, default=5000, help='Port to run on')
    parser.add_argument('--workers', type=int, default=4, help='Number of workers')
    parser.add_argument('--domain', default='localhost', help='Domain name for nginx')
    
    args = parser.parse_args()
    
    manager = DeploymentManager()
    
    if args.command == 'check':
        print("🔍 Checking environment...")
        success = manager.check_environment()
        sys.exit(0 if success else 1)
    
    elif args.command == 'install':
        print("📦 Installing dependencies...")
        success = manager.install_dependencies()
        sys.exit(0 if success else 1)
    
    elif args.command == 'systemd':
        print("⚙️ Creating systemd service...")
        manager.create_systemd_service(args.port, args.workers)
    
    elif args.command == 'nginx':
        print("🌐 Creating nginx configuration...")
        manager.create_nginx_config(args.domain, args.port)
    
    elif args.command == 'docker':
        print("🐳 Creating Docker setup...")
        manager.create_docker_setup()
    
    elif args.command == 'run':
        print("🚀 Running production server...")
        success = manager.run_production_server(args.port, args.workers)
        sys.exit(0 if success else 1)


if __name__ == '__main__':
    main() 