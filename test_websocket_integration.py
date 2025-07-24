#!/usr/bin/env python3
"""
Test script to verify WebSocket integration functionality
"""

import asyncio
import websockets
import json
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.logger import get_logger

logger = get_logger(__name__)


async def test_websocket_connection():
    """Test basic WebSocket connection to the server"""
    logger.info("Testing WebSocket connection...")
    
    try:
        # Try to connect to the WebSocket endpoint
        uri = "ws://localhost:8000/ws"
        
        # Note: This test assumes the server is running
        # In a real scenario, we'd start the server or mock it
        async with websockets.connect(uri) as websocket:
            logger.info("✅ WebSocket connection established")
            
            # Test ping/pong functionality
            ping_message = {"type": "ping", "timestamp": datetime.utcnow().isoformat()}
            await websocket.send(json.dumps(ping_message))
            logger.info("📤 Sent ping message")
            
            # Wait for pong response
            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            response_data = json.loads(response)
            
            if response_data.get("type") == "pong":
                logger.info("✅ Received pong response - WebSocket is working")
                return True
            else:
                logger.warning(f"⚠️ Unexpected response: {response_data}")
                return False
                
    except ConnectionRefusedError:
        logger.error("❌ WebSocket connection refused - Server might not be running")
        logger.info("💡 To test WebSocket, start the server with: python -m api.web_api")
        return False
    except asyncio.TimeoutError:
        logger.error("❌ WebSocket timeout - No response received")
        return False
    except Exception as e:
        logger.error(f"❌ WebSocket connection error: {e}")
        return False


async def test_websocket_subscription():
    """Test WebSocket subscription functionality"""
    logger.info("Testing WebSocket subscription...")
    
    try:
        uri = "ws://localhost:8000/ws"
        
        async with websockets.connect(uri) as websocket:
            # Test subscription
            subscribe_message = {
                "type": "subscribe",
                "data": {"channels": ["validation", "scanner", "trades"]}
            }
            await websocket.send(json.dumps(subscribe_message))
            logger.info("📤 Sent subscription message")
            
            # Wait for subscription confirmation
            response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            response_data = json.loads(response)
            
            if response_data.get("type") == "subscribed":
                logger.info("✅ Subscription confirmed")
                return True
            else:
                logger.warning(f"⚠️ Unexpected subscription response: {response_data}")
                return False
                
    except Exception as e:
        logger.error(f"❌ WebSocket subscription error: {e}")
        return False


async def analyze_websocket_implementation():
    """Analyze the WebSocket implementation for potential issues"""
    logger.info("Analyzing WebSocket implementation...")
    
    issues_found = []
    
    # Check if WebSocket endpoint is properly defined
    try:
        from api.web_api import app
        
        # Check if WebSocket route exists
        websocket_routes = [route for route in app.routes if hasattr(route, 'path') and route.path == '/ws']
        if websocket_routes:
            logger.info("✅ WebSocket endpoint '/ws' is defined")
        else:
            issues_found.append("❌ WebSocket endpoint '/ws' not found in FastAPI routes")
            
    except Exception as e:
        issues_found.append(f"❌ Error importing web API: {e}")
    
    # Check frontend WebSocket URL configuration
    try:
        frontend_api_client_path = project_root / "frontend" / "static" / "js" / "api_client.py"
        if frontend_api_client_path.exists():
            with open(frontend_api_client_path, 'r') as f:
                content = f.read()
                if 'ws://' in content and '/ws' in content:
                    logger.info("✅ Frontend WebSocket URL configuration found")
                else:
                    issues_found.append("❌ Frontend WebSocket URL not properly configured")
        else:
            issues_found.append("❌ Frontend API client file not found")
            
    except Exception as e:
        issues_found.append(f"❌ Error checking frontend WebSocket config: {e}")
    
    # Check for potential PyScript WebSocket compatibility issues
    issues_found.append("⚠️ PyScript WebSocket compatibility: Ensure PyScript can access browser WebSocket API")
    
    # Check if background broadcast task is properly started
    try:
        from api.web_api import broadcast_realtime_data
        logger.info("✅ Background broadcast task function exists")
    except Exception as e:
        issues_found.append(f"❌ Background broadcast task not found: {e}")
    
    return issues_found


async def main():
    """Run all WebSocket tests"""
    logger.info("🚀 Starting WebSocket integration tests...")
    
    # First, analyze the implementation
    logger.info("\n" + "="*50)
    logger.info("WEBSOCKET IMPLEMENTATION ANALYSIS")
    logger.info("="*50)
    
    issues = await analyze_websocket_implementation()
    
    if issues:
        logger.info("Issues found:")
        for issue in issues:
            logger.info(f"  • {issue}")
    else:
        logger.info("✅ No implementation issues detected")
    
    # Test connection (will fail if server not running)
    logger.info("\n" + "="*50)
    logger.info("WEBSOCKET CONNECTION TEST")
    logger.info("="*50)
    
    connection_success = await test_websocket_connection()
    
    if connection_success:
        # Test subscription functionality
        logger.info("\n" + "="*50)
        logger.info("WEBSOCKET SUBSCRIPTION TEST")
        logger.info("="*50)
        
        subscription_success = await test_websocket_subscription()
        
        if subscription_success:
            logger.info("✅ All WebSocket tests passed!")
        else:
            logger.error("❌ WebSocket subscription test failed")
    else:
        logger.info("⏭️ Skipping subscription test due to connection failure")
    
    # Summary
    logger.info("\n" + "="*50)
    logger.info("WEBSOCKET TEST SUMMARY")
    logger.info("="*50)
    
    if not issues and connection_success:
        logger.info("✅ WebSocket implementation appears to be working correctly")
        logger.info("🎯 Ready for real-time data transmission")
    else:
        logger.info("⚠️ WebSocket implementation has potential issues:")
        if issues:
            logger.info("  • Implementation issues detected")
        if not connection_success:
            logger.info("  • Connection test failed (server may not be running)")
        
        logger.info("\n💡 Recommendations:")
        logger.info("  1. Ensure FastAPI server is running on port 8000")
        logger.info("  2. Check browser console for PyScript WebSocket errors")
        logger.info("  3. Verify frontend can access browser WebSocket API")
        logger.info("  4. Test with actual browser environment, not just server-side")


if __name__ == "__main__":
    asyncio.run(main())