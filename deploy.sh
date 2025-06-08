#!/bin/bash

# StandardGPT Production Deployment Script
# Dette scriptet automatiserer distribusjon av StandardGPT til produksjon

set -e  # Exit on any error

# Farger for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging funksjon
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Sjekk om Docker er installert
check_docker() {
    if ! command -v docker &> /dev/null; then
        error "Docker er ikke installert. Installer Docker først."
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        error "Docker Compose er ikke installert. Installer Docker Compose først."
        exit 1
    fi
    
    success "Docker og Docker Compose er installert"
}

# Sjekk miljøvariabler
check_env() {
    if [ ! -f .env ]; then
        error ".env fil mangler. Opprett .env fil med nødvendige miljøvariabler."
        echo "Se PRODUCTION_GUIDE.md for detaljer."
        exit 1
    fi
    
    # Sjekk kritiske miljøvariabler
    source .env
    
    if [ -z "$OPENAI_API_KEY" ]; then
        error "OPENAI_API_KEY mangler i .env fil"
        exit 1
    fi
    
    if [ -z "$SECRET_KEY" ]; then
        error "SECRET_KEY mangler i .env fil"
        exit 1
    fi
    
    success "Miljøvariabler er konfigurert"
}

# Opprett nødvendige mapper
create_directories() {
    log "Oppretter nødvendige mapper..."
    
    mkdir -p logs
    mkdir -p nginx/ssl
    mkdir -p monitoring
    
    success "Mapper opprettet"
}

# Generer SSL sertifikater (self-signed for testing)
generate_ssl() {
    if [ ! -f nginx/ssl/cert.pem ] || [ ! -f nginx/ssl/key.pem ]; then
        log "Genererer self-signed SSL sertifikater..."
        
        openssl req -x509 -newkey rsa:4096 -keyout nginx/ssl/key.pem -out nginx/ssl/cert.pem -days 365 -nodes \
            -subj "/C=NO/ST=Oslo/L=Oslo/O=StandardGPT/CN=localhost"
        
        success "SSL sertifikater generert"
        warning "Bruk Let's Encrypt eller kjøpte sertifikater i produksjon!"
    else
        log "SSL sertifikater eksisterer allerede"
    fi
}

# Bygg Docker images
build_images() {
    log "Bygger Docker images..."
    
    docker-compose -f docker-compose.prod.yml build --no-cache
    
    success "Docker images bygget"
}

# Start tjenester
start_services() {
    log "Starter tjenester..."
    
    # Stopp eksisterende tjenester først
    docker-compose -f docker-compose.prod.yml down
    
    # Start alle tjenester
    docker-compose -f docker-compose.prod.yml up -d
    
    success "Tjenester startet"
}

# Vent på at tjenester blir klare
wait_for_services() {
    log "Venter på at tjenester blir klare..."
    
    # Vent på Elasticsearch
    log "Venter på Elasticsearch..."
    timeout=60
    while [ $timeout -gt 0 ]; do
        if curl -s http://localhost:9200/_cluster/health > /dev/null 2>&1; then
            break
        fi
        sleep 2
        timeout=$((timeout-2))
    done
    
    if [ $timeout -le 0 ]; then
        error "Elasticsearch startet ikke innen forventet tid"
        exit 1
    fi
    
    # Vent på Flask app
    log "Venter på Flask applikasjon..."
    timeout=60
    while [ $timeout -gt 0 ]; do
        if curl -s http://localhost:5000/health > /dev/null 2>&1; then
            break
        fi
        sleep 2
        timeout=$((timeout-2))
    done
    
    if [ $timeout -le 0 ]; then
        error "Flask applikasjon startet ikke innen forventet tid"
        exit 1
    fi
    
    success "Alle tjenester er klare"
}

# Kjør helsesjekk
health_check() {
    log "Kjører helsesjekk..."
    
    # Sjekk Flask app
    if ! curl -f http://localhost:5000/health > /dev/null 2>&1; then
        error "Flask applikasjon helsesjekk feilet"
        return 1
    fi
    
    # Sjekk Elasticsearch
    if ! curl -f http://localhost:9200/_cluster/health > /dev/null 2>&1; then
        error "Elasticsearch helsesjekk feilet"
        return 1
    fi
    
    # Sjekk Redis
    if ! docker exec standardgpt-redis redis-cli ping > /dev/null 2>&1; then
        error "Redis helsesjekk feilet"
        return 1
    fi
    
    success "Alle helsesjekker bestått"
}

# Vis status
show_status() {
    log "Tjeneste status:"
    docker-compose -f docker-compose.prod.yml ps
    
    echo ""
    log "Tilgjengelige endepunkter:"
    echo "  - Applikasjon: http://localhost (eller https://localhost med SSL)"
    echo "  - API: http://localhost/api/query"
    echo "  - Helsesjekk: http://localhost/health"
    echo "  - Elasticsearch: http://localhost:9200"
    echo "  - Prometheus: http://localhost:9090 (hvis aktivert)"
    echo "  - Grafana: http://localhost:3000 (hvis aktivert)"
}

# Cleanup funksjon
cleanup() {
    log "Rydder opp..."
    docker-compose -f docker-compose.prod.yml down
    docker system prune -f
    success "Opprydding fullført"
}

# Backup funksjon
backup() {
    log "Oppretter backup..."
    
    DATE=$(date +%Y%m%d_%H%M%S)
    BACKUP_DIR="backup_$DATE"
    
    mkdir -p $BACKUP_DIR
    
    # Backup Elasticsearch data
    docker exec standardgpt-elasticsearch curl -X PUT "localhost:9200/_snapshot/backup_repo" -H 'Content-Type: application/json' -d'{"type": "fs", "settings": {"location": "/backup"}}'
    docker exec standardgpt-elasticsearch curl -X PUT "localhost:9200/_snapshot/backup_repo/snapshot_$DATE"
    
    # Backup konfigurasjon
    cp -r .env nginx/ $BACKUP_DIR/
    
    # Backup logs
    cp -r logs/ $BACKUP_DIR/ 2>/dev/null || true
    
    success "Backup opprettet i $BACKUP_DIR"
}

# Hovedfunksjon
main() {
    case "${1:-deploy}" in
        "deploy")
            log "Starter StandardGPT produksjonsdistribusjon..."
            check_docker
            check_env
            create_directories
            generate_ssl
            build_images
            start_services
            wait_for_services
            health_check
            show_status
            success "StandardGPT er nå distribuert og kjører!"
            ;;
        "start")
            log "Starter StandardGPT tjenester..."
            docker-compose -f docker-compose.prod.yml up -d
            wait_for_services
            show_status
            ;;
        "stop")
            log "Stopper StandardGPT tjenester..."
            docker-compose -f docker-compose.prod.yml down
            success "Tjenester stoppet"
            ;;
        "restart")
            log "Restarter StandardGPT tjenester..."
            docker-compose -f docker-compose.prod.yml restart
            wait_for_services
            show_status
            ;;
        "status")
            show_status
            ;;
        "logs")
            docker-compose -f docker-compose.prod.yml logs -f
            ;;
        "health")
            health_check
            ;;
        "backup")
            backup
            ;;
        "cleanup")
            cleanup
            ;;
        "update")
            log "Oppdaterer StandardGPT..."
            docker-compose -f docker-compose.prod.yml down
            build_images
            start_services
            wait_for_services
            health_check
            success "StandardGPT oppdatert!"
            ;;
        *)
            echo "Bruk: $0 {deploy|start|stop|restart|status|logs|health|backup|cleanup|update}"
            echo ""
            echo "Kommandoer:"
            echo "  deploy  - Full distribusjon (standard)"
            echo "  start   - Start tjenester"
            echo "  stop    - Stopp tjenester"
            echo "  restart - Restart tjenester"
            echo "  status  - Vis status"
            echo "  logs    - Vis logger"
            echo "  health  - Kjør helsesjekk"
            echo "  backup  - Opprett backup"
            echo "  cleanup - Rydd opp Docker ressurser"
            echo "  update  - Oppdater applikasjon"
            exit 1
            ;;
    esac
}

# Kjør hovedfunksjon
main "$@" 