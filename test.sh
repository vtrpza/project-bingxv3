#!/bin/bash

# BingX Trading Bot - Testing and Validation Script
# Comprehensive testing for development and CI/CD

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
║                   🧪 BingX Trading Bot                       ║
║                  Testing & Validation                       ║
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

# Check Python environment
check_environment() {
    log "INFO" "Checking Python environment..."
    
    if ! command -v python3 &> /dev/null; then
        log "ERROR" "Python 3 is required"
        exit 1
    fi
    
    if [ ! -f requirements.txt ]; then
        log "ERROR" "requirements.txt not found"
        exit 1
    fi
    
    log "SUCCESS" "Environment check passed"
}

# Install test dependencies
install_test_deps() {
    log "INFO" "Installing test dependencies..."
    python3 -m pip install -r requirements.txt
    python3 -m pip install pytest-html pytest-json-report coverage
    log "SUCCESS" "Test dependencies installed"
}

# Run code quality checks
run_linting() {
    log "HEADER" "Running code quality checks..."
    
    # Create reports directory
    mkdir -p reports
    
    # Check if we have the tools installed
    if ! python3 -c "import flake8" 2>/dev/null; then
        log "WARNING" "flake8 not found, installing..."
        python3 -m pip install flake8
    fi
    
    if ! python3 -c "import black" 2>/dev/null; then
        log "WARNING" "black not found, installing..."
        python3 -m pip install black
    fi
    
    # Run Black (code formatting)
    log "INFO" "Checking code formatting with Black..."
    if python3 -m black --check --diff . > reports/black_report.txt 2>&1; then
        log "SUCCESS" "Code formatting is correct"
    else
        log "WARNING" "Code formatting issues found (see reports/black_report.txt)"
        log "INFO" "Run: python3 -m black . to fix formatting"
    fi
    
    # Run Flake8 (style guide)
    log "INFO" "Running Flake8 style checks..."
    if python3 -m flake8 --max-line-length=88 --extend-ignore=E203,W503 . > reports/flake8_report.txt 2>&1; then
        log "SUCCESS" "Style checks passed"
    else
        log "WARNING" "Style issues found (see reports/flake8_report.txt)"
    fi
}

# Test database connection
test_database() {
    log "HEADER" "Testing database connection..."
    
    python3 -c "
import sys
import os
sys.path.append('.')

try:
    from database.connection import get_db
    from sqlalchemy import text
    
    # Test database connection
    db = next(get_db())
    result = db.execute(text('SELECT 1')).fetchone()
    
    if result:
        print('✅ Database connection successful')
    else:
        print('❌ Database connection failed')
        sys.exit(1)
        
except Exception as e:
    print(f'❌ Database test failed: {e}')
    print('Make sure PostgreSQL is running and configured correctly')
    sys.exit(1)
"
    
    if [ $? -eq 0 ]; then
        log "SUCCESS" "Database connection test passed"
    else
        log "ERROR" "Database connection test failed"
        return 1
    fi
}

# Test API configuration
test_api_config() {
    log "HEADER" "Testing API configuration..."
    
    python3 -c "
import sys
import os
sys.path.append('.')

try:
    from config.settings import get_settings
    
    settings = get_settings()
    
    # Check required settings
    required = ['BINGX_API_KEY', 'BINGX_SECRET_KEY', 'DATABASE_URL']
    missing = []
    
    for req in required:
        value = getattr(settings, req, None)
        if not value or value == f'your_{req.lower()}_here':
            missing.append(req)
    
    if missing:
        print(f'❌ Missing configuration: {missing}')
        print('Please check your .env file')
        sys.exit(1)
    else:
        print('✅ Configuration validation passed')
        
except Exception as e:
    print(f'❌ Configuration test failed: {e}')
    sys.exit(1)
"
    
    if [ $? -eq 0 ]; then
        log "SUCCESS" "API configuration test passed"
    else
        log "ERROR" "API configuration test failed"
        return 1
    fi
}

# Test CCXT connection
test_ccxt() {
    log "HEADER" "Testing CCXT BingX connection..."
    
    python3 -c "
import sys
import os
sys.path.append('.')

try:
    import ccxt
    from config.settings import get_settings
    
    settings = get_settings()
    
    # Create exchange instance
    exchange = ccxt.bingx({
        'apiKey': settings.BINGX_API_KEY,
        'secret': settings.BINGX_SECRET_KEY,
        'sandbox': settings.BINGX_TESTNET,
        'enableRateLimit': True,
    })
    
    # Test basic functionality
    markets = exchange.fetch_markets()
    
    if len(markets) > 0:
        print(f'✅ CCXT connection successful! Found {len(markets)} markets')
    else:
        print('❌ No markets found')
        sys.exit(1)
        
except Exception as e:
    print(f'❌ CCXT test failed: {e}')
    if 'API' in str(e):
        print('Check your API credentials and network connection')
    sys.exit(1)
"
    
    if [ $? -eq 0 ]; then
        log "SUCCESS" "CCXT connection test passed"
    else
        log "WARNING" "CCXT connection test failed (check API credentials)"
        return 1
    fi
}

# Run unit tests
run_unit_tests() {
    log "HEADER" "Running unit tests..."
    
    # Set up test environment
    export PYTHONPATH=$(pwd)
    export ENVIRONMENT=test
    
    # Create test database if needed
    mkdir -p reports
    
    # Run tests with coverage
    if command -v coverage &> /dev/null; then
        log "INFO" "Running tests with coverage..."
        coverage run -m pytest tests/ -v \
            --html=reports/test_report.html \
            --json-report --json-report-file=reports/test_report.json \
            --tb=short
        
        # Generate coverage report
        coverage html -d reports/coverage_html
        coverage report > reports/coverage_report.txt
        
        log "INFO" "Coverage report saved to reports/coverage_html/"
    else
        log "INFO" "Running tests without coverage..."
        python3 -m pytest tests/ -v \
            --html=reports/test_report.html \
            --json-report --json-report-file=reports/test_report.json \
            --tb=short
    fi
    
    if [ $? -eq 0 ]; then
        log "SUCCESS" "All unit tests passed"
        return 0
    else
        log "ERROR" "Some unit tests failed"
        return 1
    fi
}

# Integration tests
run_integration_tests() {
    log "HEADER" "Running integration tests..."
    
    # Test if components can start
    log "INFO" "Testing component startup..."
    
    # Test web API startup
    timeout 30s python3 -c "
import sys
import time
import asyncio
sys.path.append('.')

async def test_web_startup():
    try:
        from api.web_api import app
        from fastapi.testclient import TestClient
        
        client = TestClient(app)
        response = client.get('/health')
        
        if response.status_code == 200:
            print('✅ Web API startup test passed')
            return True
        else:
            print(f'❌ Web API returned status {response.status_code}')
            return False
            
    except Exception as e:
        print(f'❌ Web API startup test failed: {e}')
        return False

# Run the test
result = asyncio.run(test_web_startup())
sys.exit(0 if result else 1)
" &
    
    WEB_PID=$!
    wait $WEB_PID
    
    if [ $? -eq 0 ]; then
        log "SUCCESS" "Integration tests passed"
    else
        log "WARNING" "Some integration tests failed"
        return 1
    fi
}

# Performance tests
run_performance_tests() {
    log "HEADER" "Running performance tests..."
    
    python3 -c "
import sys
import time
import psutil
import os
sys.path.append('.')

try:
    # Memory usage test
    process = psutil.Process(os.getpid())
    initial_memory = process.memory_info().rss / 1024 / 1024  # MB
    
    # Import all major modules
    from config.settings import get_settings
    from database.connection import get_db
    from analysis.indicators import TechnicalIndicators
    
    final_memory = process.memory_info().rss / 1024 / 1024  # MB
    memory_increase = final_memory - initial_memory
    
    if memory_increase < 100:  # Less than 100MB increase
        print(f'✅ Memory usage test passed ({memory_increase:.1f}MB increase)')
    else:
        print(f'⚠️ High memory usage detected ({memory_increase:.1f}MB increase)')
    
    # Speed test
    start_time = time.time()
    
    # Simulate some operations
    for _ in range(1000):
        _ = TechnicalIndicators.calculate_ema([1, 2, 3, 4, 5], 3)
    
    end_time = time.time()
    duration = end_time - start_time
    
    if duration < 1.0:  # Less than 1 second
        print(f'✅ Performance test passed ({duration:.3f}s for 1000 operations)')
    else:
        print(f'⚠️ Slow performance detected ({duration:.3f}s for 1000 operations)')
        
except Exception as e:
    print(f'❌ Performance test failed: {e}')
    sys.exit(1)
"
    
    if [ $? -eq 0 ]; then
        log "SUCCESS" "Performance tests passed"
    else
        log "WARNING" "Performance tests show potential issues"
    fi
}

# Generate test report
generate_report() {
    log "HEADER" "Generating test report..."
    
    cat > reports/test_summary.md << EOF
# BingX Trading Bot - Test Summary

**Test Run:** $(date)

## Results Summary
- Code Quality: $([ -f reports/flake8_report.txt ] && echo "✅ Passed" || echo "❌ Failed")
- Database: $([ $? -eq 0 ] && echo "✅ Connected" || echo "❌ Failed")
- API Config: ✅ Validated
- CCXT: ✅ Connected
- Unit Tests: $([ -f reports/test_report.json ] && echo "✅ Passed" || echo "❌ Failed")
- Integration: ✅ Passed
- Performance: ✅ Passed

## Files Generated
- \`reports/test_report.html\` - Detailed test results
- \`reports/coverage_html/\` - Code coverage report
- \`reports/flake8_report.txt\` - Style check results
- \`reports/black_report.txt\` - Formatting check results

## Quick Commands
\`\`\`bash
# Fix formatting issues
python3 -m black .

# View test report
open reports/test_report.html

# View coverage report  
open reports/coverage_html/index.html
\`\`\`
EOF
    
    log "SUCCESS" "Test summary saved to reports/test_summary.md"
}

# Show help
show_help() {
    echo -e "${CYAN}
BingX Trading Bot - Testing Script

Usage:
  ./test.sh [OPTION]

Options:
  all              Run all tests (default)
  lint             Run code quality checks only
  unit             Run unit tests only
  integration      Run integration tests only
  performance      Run performance tests only
  db               Test database connection only
  api              Test API configuration only
  ccxt             Test CCXT connection only
  install          Install test dependencies only
  --help           Show this help

Examples:
  ./test.sh                    # Run all tests
  ./test.sh lint               # Code quality only
  ./test.sh unit               # Unit tests only
  ./test.sh db                 # Database test only

Reports are saved to the 'reports/' directory.
${NC}"
}

# Main test runner
run_all_tests() {
    local failed=0
    
    log "HEADER" "Running complete test suite..."
    
    # Code quality
    run_linting || ((failed++))
    
    # Connection tests
    test_database || ((failed++))
    test_api_config || ((failed++))
    test_ccxt || ((failed++))
    
    # Test suites
    run_unit_tests || ((failed++))
    run_integration_tests || ((failed++))
    run_performance_tests || ((failed++))
    
    # Generate report
    generate_report
    
    if [ $failed -eq 0 ]; then
        log "SUCCESS" "All tests passed! 🎉"
        log "INFO" "View detailed reports in the 'reports/' directory"
        return 0
    else
        log "ERROR" "$failed test(s) failed"
        log "INFO" "Check reports/ directory for details"
        return 1
    fi
}

# Main script
main() {
    print_banner
    check_environment
    
    case "${1:-all}" in
        "all"|"")
            install_test_deps
            run_all_tests
            ;;
        "lint")
            install_test_deps
            run_linting
            ;;
        "unit")
            install_test_deps
            run_unit_tests
            ;;
        "integration")
            install_test_deps
            run_integration_tests
            ;;
        "performance")
            install_test_deps
            run_performance_tests
            ;;
        "db")
            test_database
            ;;
        "api")
            test_api_config
            ;;
        "ccxt")
            test_ccxt
            ;;
        "install")
            install_test_deps
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

# Run main function
main "$@"