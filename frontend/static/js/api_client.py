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
        """Make GET request to API"""
        try:
            response = await fetch(f"{self.base_url}/api{endpoint}")
            if response.ok:
                return (await response.json()).to_py()
            else:
                console.error(f"API Error: {response.status} - {await response.text()}")
                return None
        except Exception as e:
            console.error(f"Request failed: {str(e)}")
            return None
    
    async def post(self, endpoint, data=None):
        """Make POST request to API with improved error handling"""
        try:
            headers = {"Content-Type": "application/json"}
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
    
    async def get_validation_table(self, limit=None, offset=0, include_invalid=True):
        """Get comprehensive asset validation table with all metrics
        
        Args:
            limit: Number of records per page (None = all records)
            offset: Starting record index for pagination
            include_invalid: Include invalid assets in results
        """
        params = []
        if limit is not None:
            params.append(f"limit={limit}")
        if offset > 0:
            params.append(f"offset={offset}")
        params.append(f"include_invalid={str(include_invalid).lower()}")
        query_string = "?" + "&".join(params) if params else ""
        return await self.get(f"/assets/validation-table{query_string}")
    
    async def get_validation_table_all(self, include_invalid=True):
        """Get ALL assets for revalidation (no pagination limit)"""
        params = [f"include_invalid={str(include_invalid).lower()}"]
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
    
    # Health check
    async def health_check(self):
        """Check API health status"""
        return await self.get("/health")
    
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
        console.warn("WebSocket unavailable - real-time updates disabled")
        # TODO: Implement polling fallback for real-time updates if needed
        # self.start_polling_fallback()
        
        # Update UI to show WebSocket is unavailable
        self.update_connection_status(False)
        
        # Show user notification about degraded functionality
        try:
            # Try to show notification if UI components are available
            from components import ui_components
            ui_components.show_notification(
                "Conexão", 
                "Atualizações em tempo real indisponíveis. Usando modo manual.", 
                "warning"
            )
        except:
            # Fallback if UI components not available
            console.warn("Real-time updates unavailable - using manual refresh mode")


# Global API client instance
api_client = APIClient()