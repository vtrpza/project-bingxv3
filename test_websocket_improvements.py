#!/usr/bin/env python3
"""
Test script to verify WebSocket improvements and functionality
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
                # Send subscription
                subscribe_message = {
                    "type": "subscribe",
                    "data": {"channels": ["validation", "scanner", "trades"]}
                }
                await websocket.send(json.dumps(subscribe_message))
                logger.info("📤 Subscription sent")
                
                # Wait for confirmation
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                response_data = json.loads(response)
                
                if response_data.get("type") == "subscribed":
                    logger.info("✅ Subscription confirmed")
                    logger.info(f"   Channels: {response_data.get('data', {}).get('channels', [])}")
                    self.test_results.append("Subscription: PASS")
                    return True
                else:
                    logger.warning(f"⚠️ Unexpected subscription response: {response_data}")
                    self.test_results.append("Subscription: FAIL")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Subscription error: {e}")
            self.test_results.append("Subscription: ERROR")
            return False
    
    async def test_multiple_connections(self):
        """Test multiple simultaneous connections"""
        logger.info("Testing multiple WebSocket connections...")
        
        try:
            uri = "ws://localhost:8000/ws"
            connections = []
            
            # Create multiple connections
            for i in range(3):
                ws = await websockets.connect(uri)
                connections.append(ws)
                logger.info(f"Connection {i+1} established")
            
            # Send ping from each connection
            for i, ws in enumerate(connections):
                ping_message = {
                    "type": "ping",
                    "client_id": f"client_{i+1}"
                }
                await ws.send(json.dumps(ping_message))
            
            # Receive pongs
            pongs_received = 0
            for i, ws in enumerate(connections):
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    response_data = json.loads(response)
                    if response_data.get("type") == "pong":
                        pongs_received += 1
                        logger.info(f"✅ Pong {i+1} received")
                except:
                    logger.warning(f"⚠️ No pong from connection {i+1}")
            
            # Close connections
            for ws in connections:
                await ws.close()
            
            if pongs_received == 3:
                logger.info("✅ All multiple connections working")
                self.test_results.append("Multiple Connections: PASS")
                return True
            else:
                logger.warning(f"⚠️ Only {pongs_received}/3 connections responded")
                self.test_results.append("Multiple Connections: PARTIAL")
                return False
                
        except Exception as e:
            logger.error(f"❌ Multiple connections error: {e}")
            self.test_results.append("Multiple Connections: ERROR")
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
                ("Subscription", self.test_subscription),
                ("Multiple Connections", self.test_multiple_connections),
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