#!/bin/bash

# BingX Trading Bot - Render Deployment Test Script
# Tests the key endpoints to verify 502 errors and WebSocket issues are resolved

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default URL
BASE_URL="https://bingx-trading-bot-3i13.onrender.com"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --url)
            BASE_URL="$2"
            shift 2
            ;;
        --local)
            BASE_URL="http://localhost:10000"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [--url <base_url>] [--local]"
            echo "  --url <base_url>  Test custom URL (default: production)"
            echo "  --local           Test local development server (localhost:10000)"
            echo "  --help            Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}🚀 Testing BingX Trading Bot Deployment${NC}"
echo -e "${BLUE}Base URL: ${BASE_URL}${NC}"
echo -e "${BLUE}Timestamp: $(date)${NC}"
echo ""

# Function to test an endpoint
test_endpoint() {
    local endpoint="$1"
    local description="$2"
    local full_url="${BASE_URL}${endpoint}"
    
    echo -e "${YELLOW}Testing: ${description}${NC}"
    echo -e "${BLUE}URL: ${full_url}${NC}"
    echo ""
    
    # Make the request and capture both status code and response
    response=$(curl -s -w "\n%{http_code}\n%{time_total}" "${full_url}" 2>/dev/null) || {
        echo -e "${RED}❌ FAILED: Could not connect to ${full_url}${NC}"
        echo -e "${RED}   Error: Connection failed${NC}"
        echo ""
        return 1
    }
    
    # Parse response
    body=$(echo "$response" | head -n -2)
    http_code=$(echo "$response" | tail -n 2 | head -n 1)
    time_total=$(echo "$response" | tail -n 1)
    
    # Convert time to milliseconds
    time_ms=$(echo "$time_total * 1000" | bc -l 2>/dev/null || echo "$time_total")
    time_ms=$(printf "%.0f" "$time_ms" 2>/dev/null || echo "$time_total")
    
    # Check HTTP status code
    if [[ "$http_code" == "200" ]]; then
        echo -e "${GREEN}✅ SUCCESS: HTTP $http_code (${time_ms}ms)${NC}"
        
        # Try to parse JSON and show key information
        if command -v jq >/dev/null 2>&1; then
            # Use jq if available for pretty JSON
            echo -e "${GREEN}📄 Response:${NC}"
            echo "$body" | jq '.' 2>/dev/null || echo "$body"
        else
            # Fallback: show raw response
            echo -e "${GREEN}📄 Response:${NC}"
            echo "$body" | head -n 10  # Show first 10 lines
            if [[ $(echo "$body" | wc -l) -gt 10 ]]; then
                echo "   ... (truncated)"
            fi
        fi
    else
        echo -e "${RED}❌ FAILED: HTTP $http_code (${time_ms}ms)${NC}"
        echo -e "${RED}📄 Response:${NC}"
        echo "$body" | head -n 5  # Show first 5 lines of error
    fi
    
    echo ""
    echo "----------------------------------------"
    echo ""
    
    # Return success/failure
    [[ "$http_code" == "200" ]]
}

# Test results tracking
total_tests=0
passed_tests=0

# Test 1: Health Check
echo -e "${BLUE}🏥 Test 1: Health Check Endpoint${NC}"
if test_endpoint "/health" "Health Check (should always return 200)"; then
    ((passed_tests++))
fi
((total_tests++))

# Test 2: WebSocket Stats
echo -e "${BLUE}📊 Test 2: WebSocket Statistics${NC}"
if test_endpoint "/ws/stats" "WebSocket Connection Stats"; then
    ((passed_tests++))
fi
((total_tests++))

# Test 3: Readiness Check
echo -e "${BLUE}🔍 Test 3: Readiness Check${NC}"
if test_endpoint "/ready" "Detailed Readiness Check"; then
    ((passed_tests++))
fi
((total_tests++))

# Summary
echo -e "${BLUE}===============================================${NC}"
echo -e "${BLUE}📋 TEST SUMMARY${NC}"
echo -e "${BLUE}===============================================${NC}"
echo ""

success_rate=$(( passed_tests * 100 / total_tests ))
echo -e "📊 Results: ${passed_tests}/${total_tests} tests passed (${success_rate}%)"
echo ""

if [[ $passed_tests -eq $total_tests ]]; then
    echo -e "${GREEN}🎉 ALL TESTS PASSED!${NC}"
    echo -e "${GREEN}✅ Deployment is healthy - 502 errors should be resolved${NC}"
    echo -e "${GREEN}✅ WebSocket endpoints are responding correctly${NC}"
    exit_code=0
elif [[ $passed_tests -gt 0 ]]; then
    echo -e "${YELLOW}⚠️  PARTIAL SUCCESS${NC}"
    echo -e "${YELLOW}Some endpoints are working, but issues remain${NC}"
    exit_code=1
else
    echo -e "${RED}❌ ALL TESTS FAILED${NC}"
    echo -e "${RED}Deployment has serious issues that need investigation${NC}"
    exit_code=2
fi

echo ""
echo -e "${BLUE}💡 Next Steps:${NC}"
if [[ $passed_tests -lt $total_tests ]]; then
    echo -e "   • Check Render service logs for errors"
    echo -e "   • Verify environment variables are set correctly"
    echo -e "   • Ensure database is connected and initialized"
    echo -e "   • Monitor deployment status in Render dashboard"
else
    echo -e "   • Deployment is working correctly!"
    echo -e "   • You can now test the full application"
    echo -e "   • Monitor WebSocket connections via /ws/stats"
fi
echo ""

exit $exit_code