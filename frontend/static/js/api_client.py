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
        self.ws_url = f"ws://{document.location.host}/ws"
        self.is_connected = False
        self.callbacks = {}
        self.reconnect_interval = 5000
        
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
        """Make POST request to API"""
        try:
            headers = {"Content-Type": "application/json"}
            body = json.dumps(data) if data else None
            
            response = await fetch(
                f"{self.base_url}/api{endpoint}",
                method="POST",
                headers=headers,
                body=body
            )
            
            if response.ok:
                return (await response.json()).to_py()
            else:
                console.error(f"API Error: {response.status} - {await response.text()}")
                return None
        except Exception as e:
            console.error(f"Request failed: {str(e)}")
            return None
    
    # Asset endpoints
    async def get_assets(self, valid_only=True, limit=100):
        """Get list of assets"""
        params = f"?valid_only={str(valid_only).lower()}&limit={limit}"
        return await self.get(f"/assets{params}")
    
    async def get_asset_details(self, symbol):
        """Get detailed information about a specific asset"""
        return await self.get(f"/assets/{symbol}")
    
    async def get_validation_table(self, limit=50, include_invalid=True):
        """Get comprehensive asset validation table with all metrics"""
        params = f"?limit={limit}&include_invalid={str(include_invalid).lower()}"
        return await self.get(f"/assets/validation-table{params}")
    
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
        console.log("WebSocket connected")
        self.update_connection_status(True)
        
        # Send ping to keep connection alive
        if self.websocket:
            ping_message = json.dumps({"type": "ping"})
            self.websocket.send(ping_message)
    
    def on_websocket_close(self, event):
        """Handle WebSocket connection close"""
        self.is_connected = False
        console.log("WebSocket disconnected")
        self.update_connection_status(False)
        
        # Attempt to reconnect after delay
        setTimeout = document.defaultView.setTimeout
        setTimeout(create_proxy(self.connect_websocket), self.reconnect_interval)
    
    def on_websocket_error(self, event):
        """Handle WebSocket error"""
        console.error("WebSocket error:", event)
        self.is_connected = False
        self.update_connection_status(False)
    
    def connect_websocket(self):
        """Connect to WebSocket server"""
        try:
            self.websocket = WebSocket.new(self.ws_url)
            self.websocket.onopen = create_proxy(self.on_websocket_open)
            self.websocket.onmessage = create_proxy(self.on_websocket_message)
            self.websocket.onclose = create_proxy(self.on_websocket_close)
            self.websocket.onerror = create_proxy(self.on_websocket_error)
        except Exception as e:
            console.error(f"WebSocket connection error: {str(e)}")
    
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
        """Send message through WebSocket"""
        if self.websocket and self.is_connected:
            try:
                self.websocket.send(json.dumps(message))
            except Exception as e:
                console.error(f"WebSocket send error: {str(e)}")
        else:
            console.warn("WebSocket not connected")


# Global API client instance
api_client = APIClient()