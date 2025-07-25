"""
API Client for BingX Trading Bot Frontend
Handles communication with the FastAPI backend
"""

import asyncio
import json
from datetime import datetime
from js import fetch, WebSocket, console, document
from pyodide.ffi import create_proxy


class APIClient:
    def __init__(self, base_url=""):
        self.base_url = base_url
        self.websocket = None
        self.ws_url = None
        self.is_connected = False
        self.callbacks = {}
        self.reconnect_interval = 5000
        self.max_reconnect_attempts = 5
        self.reconnect_attempts = 0
        
    async def get(self, endpoint):
        """Make GET request to API with enhanced error handling"""
        try:
            response = await fetch(f"{self.base_url}/api{endpoint}")
            if response.ok:
                return (await response.json()).to_py()
            else:
                response_text = await response.text()
                console.error(f"API Error: {response.status} - {response_text}")
                
                # Check for specific scan required errors
                if (response.status == 424 or response.status == 500):
                    try:
                        error_data = json.loads(response_text)
                        error_detail = error_data.get("detail", "")
                        
                        # Check if it's the no_valid_symbols error
                        if "no_valid_symbols" in str(error_detail):
                            # Raise specific exception with scan requirement info
                            raise Exception(f"SCAN_REQUIRED: {error_detail}")
                    except json.JSONDecodeError:
                        # If can't parse JSON, check if text contains scan info  
                        if "no_valid_symbols" in response_text:
                            raise Exception(f"SCAN_REQUIRED: {response_text}")
                
                return None
        except Exception as e:
            error_msg = str(e)
            if error_msg.startswith("SCAN_REQUIRED:"):
                # Re-raise scan required exceptions to be handled by caller
                raise e
            else:
                console.error(f"Request failed: {error_msg}")
                return None
    
    async def post(self, endpoint, data=None):
        """Make POST request to API with improved error handling"""
        try:
            headers = [["Content-Type", "application/json"]]
            body = json.dumps(data) if data else None
            
            response = await fetch(
                f"{self.base_url}/api{endpoint}",
                method="POST",
                headers=headers,
                body=body
            )
            
            response_text = await response.text()
            
            if response.ok:
                try:
                    return json.loads(response_text)
                except json.JSONDecodeError:
                    return {"status": "success", "message": response_text}
            else:
                console.error(f"API Error: {response.status} - {response_text}")
                try:
                    # Try to parse error response
                    error_data = json.loads(response_text)
                    return {"error": True, "status": response.status, "detail": error_data.get("detail", response_text)}
                except json.JSONDecodeError:
                    # Return raw text if not JSON
                    return {"error": True, "status": response.status, "detail": response_text}
        except Exception as e:
            console.error(f"Request failed: {str(e)}")
            return {"error": True, "status": "network_error", "detail": str(e)}
    
    # Asset endpoints
    async def get_assets(self, valid_only=True, limit=100):
        """Get list of assets"""
        params = f"?valid_only={str(valid_only).lower()}&limit={limit}"
        return await self.get(f"/assets{params}")
    
    async def get_asset_details(self, symbol):
        """Get detailed information about a specific asset"""
        return await self.get(f"/assets/{symbol}")
    
    async def get_validation_table(self, page=1, per_page=25, include_invalid=True, search=None, sort_by="symbol", sort_direction="asc", filter_valid_only=False, risk_level_filter=None, priority_only=False, trading_enabled_only=False):
        """Get comprehensive asset validation table with server-side pagination
        
        Args:
            page: Page number (1-based)
            per_page: Number of records per page
            include_invalid: Include invalid assets in results
            search: Search term for filtering assets
            sort_by: Column to sort by
            sort_direction: Sort direction (asc/desc)
            filter_valid_only: Show only valid assets
            risk_level_filter: Filter by risk level (LOW/MEDIUM/HIGH/ALL)
            priority_only: Show only priority assets
            trading_enabled_only: Show only trading enabled assets
        """
        params = []
        params.append(f"page={page}")
        params.append(f"per_page={per_page}")
        params.append(f"include_invalid={str(include_invalid).lower()}")
        params.append(f"filter_valid_only={str(filter_valid_only).lower()}")
        if search and search.strip():
            params.append(f"search={search.strip()}")
        params.append(f"sort_by={sort_by}")
        params.append(f"sort_direction={sort_direction}")
        if risk_level_filter and risk_level_filter.upper() != "ALL":
            params.append(f"risk_level_filter={risk_level_filter}")
        params.append(f"priority_only={str(priority_only).lower()}")
        params.append(f"trading_enabled_only={str(trading_enabled_only).lower()}")
        query_string = "?" + "&".join(params) if params else ""
        return await self.get(f"/assets/validation-table{query_string}")
    
    async def get_validation_table_all(self, include_invalid=True):
        """Get ALL assets for revalidation (using large page size)"""
        params = []
        params.append(f"page=1")
        params.append(f"per_page=10000")  # Large page size to get all
        params.append(f"include_invalid={str(include_invalid).lower()}")
        query_string = "?" + "&".join(params)
        return await self.get(f"/assets/validation-table{query_string}")

    async def force_revalidation(self):
        """Force a full revalidation of all assets"""
        return await self.post("/assets/force-revalidation")
    
    async def get_revalidation_status(self):
        """Get the current status of the revalidation process"""
        return await self.get("/assets/revalidation-status")
    
    # Indicator endpoints
    async def get_indicators(self, symbol=None, timeframe=None, limit=50):
        """Get technical indicators"""
        if symbol:
            params = f"?limit={limit}"
            if timeframe:
                params += f"&timeframe={timeframe}"
            return await self.get(f"/indicators/{symbol}{params}")
        else:
            return await self.get(f"/indicators?limit={limit}")
    
    async def get_latest_indicators(self, limit=100):
        """Get latest indicators for all symbols"""
        return await self.get(f"/indicators?limit={limit}")
    
    # Signal endpoints
    async def get_signals(self, symbol=None, signal_type=None, limit=50):
        """Get trading signals"""
        params = []
        if symbol:
            params.append(f"symbol={symbol}")
        if signal_type:
            params.append(f"signal_type={signal_type}")
        params.append(f"limit={limit}")
        
        query = "?" + "&".join(params) if params else ""
        return await self.get(f"/signals{query}")
    
    async def get_active_signals(self):
        """Get unprocessed signals"""
        return await self.get("/signals/active")
    
    # Trade endpoints
    async def get_trades(self, symbol=None, status=None, limit=50):
        """Get trade history"""
        params = []
        if symbol:
            params.append(f"symbol={symbol}")
        if status:
            params.append(f"status={status}")
        params.append(f"limit={limit}")
        
        query = "?" + "&".join(params) if params else ""
        return await self.get(f"/trades{query}")
    
    # Position endpoints
    async def get_positions(self, active_only=True):
        """Get current positions"""
        params = f"?active_only={str(active_only).lower()}"
        return await self.get(f"/positions{params}")
    
    # Dashboard endpoint
    async def get_dashboard_summary(self):
        """Get dashboard summary data"""
        return await self.get("/dashboard/summary")
    
    # Bot control endpoints
    async def start_bot(self):
        """Start the trading bot"""
        return await self.post("/bot/start")
    
    async def stop_bot(self):
        """Stop the trading bot"""
        return await self.post("/bot/stop")
    
    async def get_bot_status(self):
        """Get current bot status"""
        return await self.get("/bot/status")
    
    async def get_scanner_status(self):
        """Get scanner status to determine if scanning is active"""
        return await self.get("/scanner/status")
    
    async def start_trading(self):
        """Start trading (bot must be running)"""
        return await self.post("/trading/start")
    
    async def stop_trading(self):
        """Stop trading"""
        return await self.post("/trading/stop")
    
    # Health check
    async def health_check(self):
        """Check API health status"""
        # Backend exposes /health without /api prefix
        try:
            response = await fetch(f"{self.base_url}/health")
            if response.ok:
                return (await response.json()).to_py()
            else:
                console.error(f"Health check error: {response.status}")
                return None
        except Exception as e:
            console.error(f"Health check failed: {str(e)}")
            return None
    
    # WebSocket methods
    def get_websocket_url(self):
        """Get WebSocket URL with protocol detection and fallback"""
        try:
            # Detect protocol (ws for http, wss for https)
            protocol = "wss" if document.location.protocol == "https:" else "ws"
            host = document.location.host
            url = f"{protocol}://{host}/ws"
            console.log(f"WebSocket URL constructed: {url}")
            return url
        except Exception as e:
            # Fallback for environments where document.location is not available
            console.warn(f"Could not access document.location: {e}")
            fallback_url = "ws://localhost:8000/ws"
            console.log(f"Using fallback WebSocket URL: {fallback_url}")
            return fallback_url
    
    def on_message(self, event_type, callback):
        """Register callback for WebSocket message type"""
        self.callbacks[event_type] = callback
    
    def on_websocket_message(self, event):
        """Handle WebSocket message"""
        try:
            data = json.loads(event.data)
            message_type = data.get("type")
            
            if message_type in self.callbacks:
                self.callbacks[message_type](data)
            elif message_type == "realtime_update":
                # Handle real-time updates
                if "realtime_update" in self.callbacks:
                    self.callbacks["realtime_update"](data.get("data", {}))
            
        except Exception as e:
            console.error(f"WebSocket message error: {str(e)}")
    
    def on_websocket_open(self, event):
        """Handle WebSocket connection open"""
        self.is_connected = True
        self.reconnect_attempts = 0  # Reset reconnection attempts on successful connection
        console.log("WebSocket connected successfully")
        self.update_connection_status(True)
        
        # Stop polling if it was active
        if hasattr(self, 'polling_active') and self.polling_active:
            self.stop_polling_fallback()
            console.log("Stopped polling fallback - WebSocket connected")
        
        # Send ping to keep connection alive
        if self.websocket:
            ping_message = json.dumps({"type": "ping"})
            self.websocket.send(ping_message)
    
    def on_websocket_close(self, event):
        """Handle WebSocket connection close"""
        self.is_connected = False
        console.log(f"WebSocket disconnected. Code: {event.code}, Reason: {event.reason}")
        self.update_connection_status(False)
        
        # Attempt to reconnect with exponential backoff
        if self.reconnect_attempts < self.max_reconnect_attempts:
            self.reconnect_attempts += 1
            delay = min(self.reconnect_interval * (2 ** (self.reconnect_attempts - 1)), 30000)  # Max 30s
            console.log(f"Attempting reconnection {self.reconnect_attempts}/{self.max_reconnect_attempts} in {delay}ms")
            
            setTimeout = document.defaultView.setTimeout
            
            def reconnect():
                self.connect_websocket()

            setTimeout(create_proxy(reconnect), delay)
        else:
            console.error("Max reconnection attempts reached. WebSocket connection failed.")
            self.handle_websocket_unavailable()
    
    def on_websocket_error(self, event):
        """Handle WebSocket error"""
        console.error("WebSocket error:", event)
        self.is_connected = False
        self.update_connection_status(False)
    
    def connect_websocket(self):
        """Connect to WebSocket server with enhanced error handling"""
        try:
            # Get WebSocket URL using improved method
            self.ws_url = self.get_websocket_url()
            console.log(f"Attempting WebSocket connection to: {self.ws_url}")
            
            self.websocket = WebSocket.new(self.ws_url)
            self.websocket.onopen = create_proxy(self.on_websocket_open)
            self.websocket.onmessage = create_proxy(self.on_websocket_message)
            self.websocket.onclose = create_proxy(self.on_websocket_close)
            self.websocket.onerror = create_proxy(self.on_websocket_error)
        except Exception as e:
            console.error(f"WebSocket connection error: {str(e)}")
            self.handle_websocket_unavailable()
    
    def disconnect_websocket(self):
        """Disconnect from WebSocket server"""
        if self.websocket:
            self.websocket.close()
            self.websocket = None
            self.is_connected = False
    
    def update_connection_status(self, connected):
        """Update connection status indicator in UI"""
        status_indicator = document.querySelector(".status-indicator")
        status_text = document.querySelector(".connection-status span:last-child")
        
        if status_indicator and status_text:
            if connected:
                status_indicator.className = "status-indicator online"
                status_text.textContent = "Conectado"
            else:
                status_indicator.className = "status-indicator offline"
                status_text.textContent = "Desconectado"
    
    def send_websocket_message(self, message):
        """Send message through WebSocket with validation"""
        if not self.websocket:
            console.warn("WebSocket not initialized")
            return False
            
        if not self.is_connected:
            console.warn("WebSocket not connected - attempting reconnection")
            self.connect_websocket()
            return False
            
        try:
            self.websocket.send(json.dumps(message))
            return True
        except Exception as e:
            console.error(f"WebSocket send error: {str(e)}")
            self.is_connected = False
            return False
    
    def handle_websocket_unavailable(self):
        """Handle case where WebSocket is not available"""
        console.warn("WebSocket unavailable - starting polling fallback")
        
        # Update UI to show WebSocket is unavailable
        self.update_connection_status(False)
        
        # Show user notification about degraded functionality
        try:
            # Try to show notification if UI components are available
            from components import ui_components
            ui_components.show_notification(
                "Conexão", 
                "Atualizações em tempo real indisponíveis. Usando modo de atualização automática.", 
                "warning"
            )
        except:
            # Fallback if UI components not available
            console.warn("Real-time updates unavailable - using polling mode")
        
        # Start polling fallback
        self.start_polling_fallback()
    
    def start_polling_fallback(self):
        """Start polling for updates when WebSocket is unavailable"""
        console.log("Starting polling fallback for real-time updates")
        
        # Set polling interval (10 seconds)
        self.polling_interval = 10000  # milliseconds
        self.polling_active = True
        
        # Use JavaScript setTimeout for polling
        setTimeout = document.defaultView.setTimeout
        
        async def poll_updates():
            """Poll for updates from the server"""
            if not self.polling_active:
                return
            
            try:
                # Get latest data
                dashboard_data = await self.get_dashboard_summary()
                positions = await self.get_positions()
                signals = await self.get_active_signals()
                
                # Simulate WebSocket message for consistency
                if dashboard_data:
                    self.on_websocket_message(type("Event", (), {
                        "data": json.dumps({
                            "type": "realtime_update",
                            "data": {
                                "dashboard": dashboard_data,
                                "positions": positions,
                                "signals": signals,
                                "timestamp": datetime.utcnow().isoformat()
                            }
                        })
                    })())
                
            except Exception as e:
                console.error(f"Polling error: {str(e)}")
            
            # Schedule next poll
            if self.polling_active:
                setTimeout(create_proxy(poll_updates), self.polling_interval)
        
        # Start initial poll
        setTimeout(create_proxy(poll_updates), 1000)  # Start after 1 second
    
    def stop_polling_fallback(self):
        """Stop polling fallback"""
        self.polling_active = False
        console.log("Polling fallback stopped")
    
    # Trading API Methods
    async def get_trading_live_data(self, limit=50):
        """Get real-time trading data with indicators and signals"""
        return await self.get(f"/trading/live-data?limit={limit}")
    
    async def execute_signal_trade(self, symbol, signal_type, signal_data):
        """Execute a trade based on signal detection"""
        return await self.post("/trading/execute-signal", {
            "symbol": symbol,
            "signal_type": signal_type,
            "signal_data": signal_data
        })
    
    async def start_auto_trading(self):
        """Start auto trading mode"""
        return await self.post("/trading/auto-trading/start")
    
    async def stop_auto_trading(self):
        """Stop auto trading mode"""
        return await self.post("/trading/auto-trading/stop")
    
    async def get_trading_positions(self):
        """Get current open positions from trading API"""
        return await self.get("/trading/positions")
    
    async def get_trades_history(self, limit=20):
        """Get recent trades history"""
        return await self.get(f"/trading/trades?limit={limit}")
    
    async def close_position(self, position_id):
        """Close a specific position"""
        return await self.post(f"/trading/positions/{position_id}/close")
    
    async def get_trading_summary(self):
        """Get trading summary statistics"""
        return await self.get("/trading/summary")


# Global API client instance
api_client = APIClient()