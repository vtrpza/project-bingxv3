#!/usr/bin/env python3
"""
Test script to validate WebSocket improvements
Tests enhanced connection management, subscription system, and error handling
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
import subprocess
import time
import signal
import websockets

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.logger import get_logger

logger = get_logger(__name__)


class WebSocketTester:
    def __init__(self):
        self.server_process = None
        self.test_results = []
        
    async def start_test_server(self):
        """Start the FastAPI server for testing"""
        logger.info("Starting test server...")
        try:
            # Start server in background
            self.server_process = subprocess.Popen([
                sys.executable, "-m", "api.web_api"
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Wait for server to start
            await asyncio.sleep(3)
            
            # Check if server is running
            if self.server_process.poll() is None:
                logger.info("✅ Test server started successfully")
                return True
            else:
                logger.error("❌ Test server failed to start")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to start test server: {e}")
            return False
    
    def stop_test_server(self):
        """Stop the test server"""
        if self.server_process:
            logger.info("Stopping test server...")
            self.server_process.terminate()
            self.server_process.wait()
            logger.info("✅ Test server stopped")
    
    async def test_basic_connection(self):
        """Test basic WebSocket connection"""
        logger.info("Testing basic WebSocket connection...")
        
        try:
            uri = "ws://localhost:8000/ws"
            async with websockets.connect(uri) as websocket:
                logger.info("✅ WebSocket connection established")
                self.test_results.append("Basic Connection: PASS")
                return True
                
        except Exception as e:
            logger.error(f"❌ WebSocket connection failed: {e}")
            self.test_results.append("Basic Connection: FAIL")
            return False
    
    async def test_ping_pong(self):
        """Test ping/pong functionality"""
        logger.info("Testing ping/pong functionality...")
        
        try:
            uri = "ws://localhost:8000/ws"
            async with websockets.connect(uri) as websocket:
                # Send ping
                ping_message = {
                    "type": "ping", 
                    "timestamp": datetime.utcnow().isoformat()
                }
                await websocket.send(json.dumps(ping_message))
                logger.info("📤 Ping sent")
                
                # Wait for pong
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                response_data = json.loads(response)
                
                if response_data.get("type") == "pong":
                    logger.info("✅ Pong received successfully")
                    logger.info(f"   Server info: {response_data.get('server_info', 'N/A')}")
                    self.test_results.append("Ping/Pong: PASS")
                    return True
                else:
                    logger.warning(f"⚠️ Unexpected response: {response_data}")
                    self.test_results.append("Ping/Pong: FAIL")
                    return False
                    
        except asyncio.TimeoutError:
            logger.error("❌ Ping/pong timeout")
            self.test_results.append("Ping/Pong: TIMEOUT")
            return False
        except Exception as e:
            logger.error(f"❌ Ping/pong error: {e}")
            self.test_results.append("Ping/Pong: ERROR")
            return False
    
    async def test_subscription(self):
        """Test subscription functionality"""
        logger.info("Testing subscription functionality...")
        
        try:
            uri = "ws://localhost:8000/ws"
            async with websockets.connect(uri) as websocket:
                # Wait for connection_established message
                welcome_response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                welcome_data = json.loads(welcome_response)
                
                if welcome_data.get("type") != "connection_established":
                    logger.warning(f"⚠️ Expected welcome message, got: {welcome_data}")
                
                # Send subscription for valid channel
                subscribe_message = {
                    "type": "subscribe",
                    "data": {"channel": "trading_data"}
                }
                await websocket.send(json.dumps(subscribe_message))
                logger.info("📤 Valid subscription sent")
                
                # Wait for confirmation
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                response_data = json.loads(response)
                
                if response_data.get("type") == "subscribed":
                    logger.info("✅ Subscription confirmed")
                    channel = response_data.get('data', {}).get('channel', 'unknown')
                    logger.info(f"   Channel: {channel}")
                    
                    # Test invalid subscription
                    invalid_subscribe = {
                        "type": "subscribe",
                        "data": {"channel": "invalid_channel"}
                    }
                    await websocket.send(json.dumps(invalid_subscribe))
                    
                    # Should get error response
                    error_response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    error_data = json.loads(error_response)
                    
                    if error_data.get("type") == "error":
                        logger.info("✅ Invalid subscription properly rejected")
                        self.test_results.append("Subscription: PASS")
                        return True
                    else:
                        logger.warning(f"⚠️ Expected error for invalid subscription, got: {error_data}")
                        self.test_results.append("Subscription: PARTIAL")
                        return False
                else:
                    logger.warning(f"⚠️ Unexpected subscription response: {response_data}")
                    self.test_results.append("Subscription: FAIL")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Subscription error: {e}")
            self.test_results.append("Subscription: ERROR")
            return False
    
    async def test_enhanced_features(self):
        """Test enhanced WebSocket features"""
        logger.info("Testing enhanced WebSocket features...")
        
        try:
            uri = "ws://localhost:8000/ws"
            async with websockets.connect(uri) as websocket:
                # Skip welcome message
                welcome = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                
                # Test stats request
                stats_message = {"type": "get_stats"}
                await websocket.send(json.dumps(stats_message))
                logger.info("📤 Stats request sent")
                
                stats_response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                stats_data = json.loads(stats_response)
                
                if stats_data.get("type") == "stats":
                    logger.info("✅ Stats request successful")
                    active_connections = stats_data.get('data', {}).get('active_connections', 0)
                    logger.info(f"   Active connections: {active_connections}")
                    
                    # Test invalid message type
                    invalid_message = {"type": "invalid_message_type", "data": {}}
                    await websocket.send(json.dumps(invalid_message))
                    
                    error_response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    error_data = json.loads(error_response)
                    
                    if error_data.get("type") == "error" and error_data.get("error") == "unknown_message_type":
                        logger.info("✅ Unknown message type properly handled")
                        self.test_results.append("Enhanced Features: PASS")
                        return True
                    else:
                        logger.warning(f"⚠️ Expected error response, got: {error_data}")
                        self.test_results.append("Enhanced Features: PARTIAL")
                        return False
                else:
                    logger.warning(f"⚠️ Expected stats response, got: {stats_data}")
                    self.test_results.append("Enhanced Features: FAIL")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Enhanced features test error: {e}")
            self.test_results.append("Enhanced Features: ERROR")
            return False
    
    async def test_reconnection_resilience(self):
        """Test connection resilience and reconnection"""
        logger.info("Testing connection resilience...")
        
        try:
            uri = "ws://localhost:8000/ws"
            
            # First connection
            async with websockets.connect(uri) as websocket:
                # Send ping
                await websocket.send(json.dumps({"type": "ping"}))
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                
                if json.loads(response).get("type") == "pong":
                    logger.info("✅ Initial connection and ping successful")
            
            # Wait a moment
            await asyncio.sleep(1)
            
            # Second connection (simulating reconnection)
            async with websockets.connect(uri) as websocket:
                # Send ping again
                await websocket.send(json.dumps({"type": "ping"}))
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                
                if json.loads(response).get("type") == "pong":
                    logger.info("✅ Reconnection successful")
                    self.test_results.append("Reconnection: PASS")
                    return True
            
            self.test_results.append("Reconnection: FAIL")
            return False
            
        except Exception as e:
            logger.error(f"❌ Reconnection test error: {e}")
            self.test_results.append("Reconnection: ERROR")
            return False
    
    def analyze_frontend_improvements(self):
        """Analyze the frontend improvements made"""
        logger.info("Analyzing frontend WebSocket improvements...")
        
        improvements = []
        
        # Check for enhanced URL construction
        api_client_path = project_root / "frontend" / "static" / "js" / "api_client.py"
        if api_client_path.exists():
            with open(api_client_path, 'r') as f:
                content = f.read()
                
                if "get_websocket_url" in content:
                    improvements.append("✅ Enhanced WebSocket URL construction")
                else:
                    improvements.append("❌ Missing enhanced URL construction")
                
                if "reconnect_attempts" in content:
                    improvements.append("✅ Reconnection attempt limiting")
                else:
                    improvements.append("❌ Missing reconnection limiting")
                
                if "handle_websocket_unavailable" in content:
                    improvements.append("✅ Graceful degradation handling")
                else:
                    improvements.append("❌ Missing graceful degradation")
                
                if "exponential backoff" in content.lower():
                    improvements.append("✅ Exponential backoff for reconnection")
                else:
                    improvements.append("❌ Missing exponential backoff")
        
        return improvements
    
    async def run_all_tests(self):
        """Run all WebSocket tests"""
        logger.info("🚀 Starting comprehensive WebSocket tests...")
        
        # Start server
        server_started = await self.start_test_server()
        if not server_started:
            logger.error("❌ Cannot run tests without server")
            return False
        
        try:
            # Run tests
            tests = [
                ("Basic Connection", self.test_basic_connection),
                ("Ping/Pong", self.test_ping_pong),
                ("Subscription System", self.test_subscription),
                ("Enhanced Features", self.test_enhanced_features),
                ("Reconnection Resilience", self.test_reconnection_resilience),
            ]
            
            passed_tests = 0
            for test_name, test_func in tests:
                logger.info(f"\n{'='*50}")
                logger.info(f"Running: {test_name}")
                logger.info(f"{'='*50}")
                
                try:
                    success = await test_func()
                    if success:
                        passed_tests += 1
                except Exception as e:
                    logger.error(f"Test {test_name} crashed: {e}")
            
            # Analyze improvements
            logger.info(f"\n{'='*50}")
            logger.info("Frontend Improvements Analysis")
            logger.info(f"{'='*50}")
            
            improvements = self.analyze_frontend_improvements()
            for improvement in improvements:
                logger.info(f"  {improvement}")
            
            # Summary
            logger.info(f"\n{'='*50}")
            logger.info("TEST SUMMARY")
            logger.info(f"{'='*50}")
            
            for result in self.test_results:
                logger.info(f"  {result}")
            
            logger.info(f"\nTotal: {passed_tests}/{len(tests)} tests passed")
            
            if passed_tests == len(tests):
                logger.info("🎉 All WebSocket tests PASSED!")
                return True
            else:
                logger.warning("⚠️ Some WebSocket tests FAILED")
                return False
                
        finally:
            self.stop_test_server()


async def main():
    """Main test runner"""
    tester = WebSocketTester()
    
    try:
        success = await tester.run_all_tests()
        
        logger.info("\n" + "="*60)
        logger.info("WEBSOCKET VERIFICATION COMPLETE")
        logger.info("="*60)
        
        if success:
            logger.info("✅ WebSocket implementation is working correctly")
            logger.info("🎯 Real-time communication is ready for production")
        else:
            logger.info("⚠️ WebSocket implementation has issues that need attention")
            logger.info("💡 Check the test results above for specific problems")
        
        return success
        
    except KeyboardInterrupt:
        logger.info("\n⏹️ Tests interrupted by user")
        tester.stop_test_server()
        return False
    except Exception as e:
        logger.error(f"❌ Test runner error: {e}")
        tester.stop_test_server()
        return False


if __name__ == "__main__":
    # Install websockets if not available
    try:
        import websockets
    except ImportError:
        print("Installing websockets library...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets"])
        import websockets
    
    success = asyncio.run(main())
    sys.exit(0 if success else 1)