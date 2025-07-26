#!/usr/bin/env python3
"""
Test script to verify API integration for frontend
Tests the dashboard summary, positions, and trades endpoints
"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import requests
import json
from datetime import datetime

def test_endpoint(url, endpoint_name):
    """Test a single endpoint and print results"""
    print(f"\n🔍 Testing {endpoint_name}: {url}")
    try:
        response = requests.get(url, timeout=10)
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Success - Response keys: {list(data.keys()) if isinstance(data, dict) else 'Non-dict response'}")
            
            # Show sample data structure
            if isinstance(data, dict):
                for key, value in data.items():
                    if isinstance(value, list) and len(value) > 0:
                        print(f"      {key}: {len(value)} items, sample: {type(value[0])}")
                    elif isinstance(value, dict):
                        print(f"      {key}: dict with keys {list(value.keys())}")
                    else:
                        print(f"      {key}: {type(value).__name__} = {value}")
        else:
            print(f"   ❌ Failed - {response.status_code}: {response.text[:200]}")
            
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Connection Error: {e}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

def main():
    """Test all API endpoints used by the frontend"""
    print("🚀 Testing API Integration for Frontend")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Base URL - try local first, then Render
    base_urls = [
        "http://localhost:10000",
        "http://localhost:8000",
        "https://bingx-trading-bot-3i13.onrender.com"
    ]
    
    # Test health first to determine which URL works
    working_url = None
    for base_url in base_urls:
        try:
            response = requests.get(f"{base_url}/health", timeout=5)
            if response.status_code == 200:
                working_url = base_url
                print(f"✅ Connected to: {base_url}")
                break
        except:
            continue
    
    if not working_url:
        print("❌ No server responding - please start the API server")
        return
    
    # Endpoints to test
    endpoints = [
        ("/health", "Health Check"),
        ("/api/dashboard/summary", "Dashboard Summary"),
        ("/api/dashboard/init", "Dashboard Init"),
        ("/api/positions?active_only=true", "Active Positions"), 
        ("/api/trades?limit=20", "Recent Trades"),
        ("/api/assets/trading-data", "Trading Data"),
        ("/api/signals/active", "Active Signals"),
        ("/api/bot/status", "Bot Status"),
        ("/api/scanner/status", "Scanner Status")
    ]
    
    # Test each endpoint
    for endpoint, name in endpoints:
        test_endpoint(f"{working_url}{endpoint}", name)
    
    print(f"\n🏁 Testing completed at {datetime.now().strftime('%H:%M:%S')}")
    print("\n📋 Summary:")
    print("   - Frontend expects these data structures to work correctly")
    print("   - Check server logs if any endpoints fail")
    print("   - Frontend will gracefully handle empty data with fallbacks")

if __name__ == "__main__":
    main()