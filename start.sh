#!/bin/bash

# BingX Trading Bot - Quick Start Script
# Makes it super easy to run the bot locally

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Print banner
print_banner() {
    echo -e "${PURPLE}
╔══════════════════════════════════════════════════════════════╗
║                   🤖 BingX Trading Bot                       ║
║                      Quick Start                            ║
╚══════════════════════════════════════════════════════════════╝
${NC}"
}

# Logging function
log() {
    local level=$1
    local message=$2
    local timestamp=$(date '+%H:%M:%S')
    
    case $level in
        "INFO")  echo -e "${BLUE}[$timestamp] INFO: $message${NC}" ;;
        "SUCCESS") echo -e "${GREEN}[$timestamp] SUCCESS: $message${NC}" ;;
        "WARNING") echo -e "${YELLOW}[$timestamp] WARNING: $message${NC}" ;;
        "ERROR") echo -e "${RED}[$timestamp] ERROR: $message${NC}" ;;
        "HEADER") echo -e "${CYAN}[$timestamp] $message${NC}" ;;
    esac
}

# Check if Python is available
check_python() {
    if ! command -v python3 &> /dev/null; then
        log "ERROR" "Python 3 is required but not installed"
        exit 1
    fi
    
    local python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    log "INFO" "Python version: $python_version"
}

# Check if Docker is available
check_docker() {
    if command -v docker &> /dev/null && command -v docker-compose &> /dev/null; then
        log "SUCCESS" "Docker and Docker Compose are available"
        return 0
    else
        log "WARNING" "Docker/Docker Compose not found. Will run without containers."
        return 1
    fi
}

# Install Python dependencies
install_deps() {
    log "INFO" "Installing Python dependencies..."
    python3 -m pip install -r requirements.txt
    log "SUCCESS" "Dependencies installed"
}

# Create .env file if it doesn't exist
setup_env() {
    if [ ! -f .env ]; then
        log "INFO" "Creating .env file from template..."
        if [ -f .env.example ]; then
            cp .env.example .env
            # Set development defaults
            sed -i 's/ENVIRONMENT=production/ENVIRONMENT=development/' .env
            sed -i 's/DEBUG=False/DEBUG=True/' .env
            sed -i 's/PAPER_TRADING=False/PAPER_TRADING=True/' .env
            sed -i 's/BINGX_TESTNET=False/BINGX_TESTNET=True/' .env
            sed -i 's/TRADING_ENABLED=True/TRADING_ENABLED=False/' .env
            log "SUCCESS" "Created .env with development defaults"
            log "WARNING" "⚠️  IMPORTANT: Edit .env with your BingX API credentials!"
        else
            log "ERROR" "No .env.example found"
            exit 1
        fi
    else
        log "INFO" ".env file already exists"
    fi
}

# Start PostgreSQL with Docker
start_postgres() {
    log "INFO" "Starting PostgreSQL container..."
    
    # Stop existing container if running
    docker stop bingx_postgres_dev 2>/dev/null || true
    docker rm bingx_postgres_dev 2>/dev/null || true
    
    # Start new container
    docker run -d \
        --name bingx_postgres_dev \
        -e POSTGRES_DB=bingx_trading \
        -e POSTGRES_USER=trading_user \
        -e POSTGRES_PASSWORD=trading_password \
        -p 5432:5432 \
        --restart unless-stopped \
        postgres:16-alpine
    
    log "SUCCESS" "PostgreSQL container started"
    log "INFO" "Waiting for database to be ready..."
    sleep 10
}

# Run database migrations
run_migrations() {
    log "INFO" "Running database migrations..."
    python3 -m alembic upgrade head
    log "SUCCESS" "Migrations completed"
}

# Show help
show_help() {
    echo -e "${CYAN}
BingX Trading Bot - Quick Start

Usage:
  ./start.sh [MODE] [OPTIONS]

Modes:
  web-only     Start only the web interface (default)
  full         Start all components (scanner, analysis, trading)
  docker       Start with Docker Compose
  
Options:
  --setup      Setup environment and database
  --test       Test API connection
  --help       Show this help

Examples:
  ./start.sh                    # Start web interface only
  ./start.sh full               # Start all components
  ./start.sh docker             # Use Docker Compose
  ./start.sh --setup            # Setup environment
  ./start.sh --test             # Test configuration

After starting:
  🌐 Web Dashboard: http://localhost:8000
  📊 API Documentation: http://localhost:8000/docs
${NC}"
}

# Start web interface only
start_web_only() {
    log "HEADER" "Starting web interface only..."
    log "INFO" "🌐 Web Dashboard will be available at: http://localhost:8000"
    log "INFO" "📊 API Documentation: http://localhost:8000/docs"
    log "INFO" "Press Ctrl+C to stop"
    
    export PYTHONPATH=$(pwd)
    python3 -m uvicorn api.web_api:app --host 0.0.0.0 --port 8000 --reload
}

# Start all components
start_full() {
    log "HEADER" "Starting all components..."
    
    # Create log directory
    mkdir -p logs
    
    export PYTHONPATH=$(pwd)
    
    # Start web interface in background
    log "INFO" "Starting web interface..."
    python3 -m uvicorn api.web_api:app --host 0.0.0.0 --port 8000 --reload &
    WEB_PID=$!
    
    sleep 3
    
    # Start scanner worker in background
    log "INFO" "Starting scanner worker..."
    python3 -m scanner.initial_scanner &
    SCANNER_PID=$!
    
    sleep 2
    
    # Start analysis worker in background
    log "INFO" "Starting analysis worker..."
    python3 -m analysis.worker &
    ANALYSIS_PID=$!
    
    sleep 2
    
    # Start trading worker in background  
    log "INFO" "Starting trading worker..."
    python3 -m trading.worker &
    TRADING_PID=$!
    
    log "SUCCESS" "All components started!"
    log "HEADER" "🌐 Web Dashboard: http://localhost:8000"
    log "HEADER" "📊 API Documentation: http://localhost:8000/docs"
    log "INFO" "Press Ctrl+C to stop all components"
    
    # Wait for interrupt
    trap 'kill $WEB_PID $SCANNER_PID $ANALYSIS_PID $TRADING_PID 2>/dev/null; log "INFO" "Stopping all components..."; exit' INT
    wait
}

# Start with Docker Compose
start_docker() {
    log "HEADER" "Starting with Docker Compose..."
    
    # Start database services
    docker-compose up -d postgres redis
    
    log "SUCCESS" "Database services started"
    log "INFO" "Waiting for services to be ready..."
    sleep 15
    
    # Run migrations
    run_migrations
    
    # Start application
    start_full
}

# Test API connection
test_api() {
    log "INFO" "Testing API connection..."
    python3 -c "
import sys
try:
    from config.settings import get_settings
    import ccxt
    
    settings = get_settings()
    
    if not settings.BINGX_API_KEY or settings.BINGX_API_KEY == 'your_bingx_api_key_here':
        print('❌ BingX API credentials not configured')
        print('Please edit .env file with your API credentials')
        sys.exit(1)
    
    exchange = ccxt.bingx({
        'apiKey': settings.BINGX_API_KEY,
        'secret': settings.BINGX_SECRET_KEY,
        'sandbox': settings.BINGX_TESTNET,
        'enableRateLimit': True,
    })
    
    markets = exchange.fetch_markets()
    print(f'✅ API connection successful! Found {len(markets)} markets')
    
except Exception as e:
    print(f'❌ API connection failed: {e}')
    sys.exit(1)
"
}

# Setup environment
setup_environment() {
    log "HEADER" "Setting up development environment..."
    
    check_python
    setup_env
    install_deps
    
    if check_docker; then
        start_postgres
        run_migrations
    else
        log "WARNING" "Docker not available. Please setup PostgreSQL manually:"
        log "INFO" "1. Install PostgreSQL 16+"
        log "INFO" "2. Create database 'bingx_trading'"
        log "INFO" "3. Create user 'trading_user' with password 'trading_password'"
        log "INFO" "4. Update DATABASE_URL in .env file"
        log "INFO" "5. Run: python3 -m alembic upgrade head"
    fi
    
    log "SUCCESS" "Environment setup completed!"
}

# Main script
main() {
    print_banner
    
    case "${1:-web-only}" in
        "web-only"|"")
            check_python
            setup_env
            install_deps
            start_web_only
            ;;
        "full")
            check_python
            setup_env
            install_deps
            start_full
            ;;
        "docker")
            if ! check_docker; then
                log "ERROR" "Docker is required for this mode"
                exit 1
            fi
            setup_env
            start_docker
            ;;
        "--setup")
            setup_environment
            ;;
        "--test")
            check_python
            test_api
            ;;
        "--help"|"-h")
            show_help
            ;;
        *)
            log "ERROR" "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"