#!/usr/bin/env python3
"""
Health check script to test if the BingX Trading Bot server is running
"""

import asyncio
import aiohttp
import websockets
import sys
import json
from datetime import datetime

async def test_http_health():
    """Test HTTP health endpoint"""
    print("🔍 Testing HTTP health endpoint...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('http://localhost:10000/health') as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ HTTP Health OK: {data}")
                    return True
                else:
                    print(f"❌ HTTP Health failed: {response.status}")
                    return False
    except Exception as e:
        print(f"❌ HTTP Health error: {e}")
        return False

async def test_websocket_connection():
    """Test WebSocket connection"""
    print("🔍 Testing WebSocket connection...")
    try:
        uri = "ws://localhost:10000/ws"
        async with websockets.connect(uri) as websocket:
            # Send ping
            ping_msg = {"type": "ping", "timestamp": datetime.utcnow().isoformat()}
            await websocket.send(json.dumps(ping_msg))
            
            # Wait for pong
            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            data = json.loads(response)
            
            if data.get("type") == "pong":
                print(f"✅ WebSocket OK: {data}")
                return True
            else:
                print(f"❌ WebSocket unexpected response: {data}")
                return False
                
    except asyncio.TimeoutError:
        print("❌ WebSocket timeout - no response from server")
        return False
    except Exception as e:
        print(f"❌ WebSocket error: {e}")
        return False

async def test_production_urls():
    """Test production URLs"""
    print("🔍 Testing production endpoints...")
    production_base = "https://bingx-trading-bot-3i13.onrender.com"
    
    try:
        async with aiohttp.ClientSession() as session:
            # Test HTTP health
            async with session.get(f'{production_base}/health') as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ Production HTTP OK: {data}")
                else:
                    print(f"❌ Production HTTP failed: {response.status}")
            
            # Test WebSocket (this will likely fail due to protocol upgrade)
            try:
                uri = "wss://bingx-trading-bot-3i13.onrender.com/ws"
                async with websockets.connect(uri) as websocket:
                    ping_msg = {"type": "ping", "timestamp": datetime.utcnow().isoformat()}
                    await websocket.send(json.dumps(ping_msg))
                    
                    response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    data = json.loads(response)
                    
                    if data.get("type") == "pong":
                        print(f"✅ Production WebSocket OK: {data}")
                    else:
                        print(f"❌ Production WebSocket unexpected response: {data}")
                        
            except Exception as e:
                print(f"❌ Production WebSocket error: {e}")
                
    except Exception as e:
        print(f"❌ Production test error: {e}")

async def main():
    """Run all health checks"""
    print("🤖 BingX Trading Bot - Server Health Check")
    print("=" * 50)
    
    # Test local server
    print("\n📍 Testing LOCAL server (localhost:10000)...")
    http_ok = await test_http_health()
    ws_ok = await test_websocket_connection()
    
    if http_ok and ws_ok:
        print("\n✅ Local server is healthy!")
    else:
        print("\n❌ Local server has issues")
        print("💡 Make sure the server is running: python -m api.web_api")
    
    # Test production server
    print("\n📍 Testing PRODUCTION server...")
    await test_production_urls()
    
    print("\n" + "=" * 50)
    print("Health check completed!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Health check interrupted")
    except Exception as e:
        print(f"\n❌ Health check failed: {e}")
        sys.exit(1)