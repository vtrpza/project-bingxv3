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
        self.connection_id = None
        self.server_version = None
        self.last_ping_time = None
        self.auto_subscribe_channels = ["general", "trading_data"]  # Default subscriptions
        
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
        """Enhanced WebSocket message handler with improved error handling and message validation."""
        try:
            data = json.loads(event.data)
            message_type = data.get("type")
            
            # Log received message for debugging
            console.log(f"WebSocket received: {message_type}")
            
            # Handle connection establishment
            if message_type == "connection_established":
                connection_info = data.get("data", {})
                self.connection_id = connection_info.get("connection_id")
                self.server_version = connection_info.get("server_version")
                console.log(f"Connection established: {self.connection_id}")
                
                # Auto-subscribe to default channels if configured
                if hasattr(self, 'auto_subscribe_channels'):
                    for channel in self.auto_subscribe_channels:
                        self.subscribe_to_channel(channel)
            
            # Handle subscription confirmations
            elif message_type == "subscribed":
                channel_info = data.get("data", {})
                channel = channel_info.get("channel", "unknown")
                console.log(f"Subscribed to channel: {channel}")
                
            # Handle unsubscription confirmations
            elif message_type == "unsubscribed":
                channel_info = data.get("data", {})
                channel = channel_info.get("channel", "unknown")
                console.log(f"Unsubscribed from channel: {channel}")
                
            # Handle errors
            elif message_type == "error":
                error_info = data.get("error", "unknown_error")
                error_message = data.get("message", "Unknown error occurred")
                console.error(f"WebSocket error ({error_info}): {error_message}")
                
                # Show user-friendly error message
                try:
                    from components import ui_components
                    ui_components.show_notification(
                        "Erro de Conexão", 
                        error_message, 
                        "error"
                    )
                except:
                    pass
            
            # Handle ping requests (server asking for pong)
            elif message_type == "ping":
                server_time = data.get("timestamp")
                console.log("Ping received from server - sending pong response")
                # Send pong response
                pong_message = {
                    "type": "pong",
                    "timestamp": datetime.now().isoformat(),
                    "server_timestamp": server_time
                }
                self.send_websocket_message(pong_message)
                
            # Handle pong responses
            elif message_type == "pong":
                server_time = data.get("timestamp")
                if server_time:
                    # Calculate latency if we have a ping timestamp
                    if hasattr(self, 'last_ping_time') and self.last_ping_time is not None:
                        try:
                            latency = (datetime.now() - self.last_ping_time).total_seconds() * 1000
                            console.log(f"WebSocket latency: {latency:.2f}ms")
                        except (TypeError, AttributeError) as e:
                            console.warn(f"Latency calculation failed: {e}")
                            # Reset ping time on error
                            self.last_ping_time = None
                        
            # Handle custom callbacks
            elif message_type in self.callbacks:
                self.callbacks[message_type](data)
                
            # Handle real-time updates (legacy compatibility)
            elif message_type == "realtime_update":
                if "realtime_update" in self.callbacks:
                    self.callbacks["realtime_update"](data.get("data", {}))
            
            # Handle broadcast messages
            elif message_type and "broadcast_info" in data:
                broadcast_info = data.get("broadcast_info", {})
                channel = broadcast_info.get("channel", "general")
                
                # Route to channel-specific callback if available
                channel_callback = f"channel_{channel}"
                if channel_callback in self.callbacks:
                    self.callbacks[channel_callback](data)
                elif message_type in self.callbacks:
                    self.callbacks[message_type](data)
                    
            else:
                console.warn(f"Unhandled WebSocket message type: {message_type}")
            
        except json.JSONDecodeError as json_error:
            console.error(f"WebSocket JSON decode error: {str(json_error)}")
        except Exception as e:
            console.error(f"WebSocket message processing error: {str(e)}")
    
    def on_websocket_open(self, event):
        """Handle WebSocket connection open with enhanced coordination"""
        self.is_connected = True
        self.reconnect_attempts = 0  # Reset reconnection attempts on successful connection
        console.log("PyScript WebSocket connected successfully")
        self.update_connection_status(True)
        
        # Stop polling if it was active
        if hasattr(self, 'polling_active') and self.polling_active:
            self.stop_polling_fallback()
            console.log("Stopped polling fallback - WebSocket connected")
        
        # Stop health check polling if it was active
        if hasattr(self, 'health_check_active') and self.health_check_active:
            self.stop_health_check_polling()
            console.log("Stopped health check polling - WebSocket connected")
        
        # Subscribe to channels that PyScript needs
        self.subscribe_to_channel('general')
        self.subscribe_to_channel('trading_data')
        
        # Send ping to keep connection alive
        if self.websocket:
            try:
                ping_message = json.dumps({
                    "type": "ping",
                    "source": "pyscript_websocket",
                    "timestamp": datetime.now().isoformat()
                })
                self.websocket.send(ping_message)
                console.log("Initial ping sent successfully")
            except Exception as e:
                console.error(f"Failed to send initial ping: {e}")
    
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
        """Handle WebSocket error with enhanced debugging"""
        console.error("PyScript WebSocket error:", event)
        self.is_connected = False
        self.update_connection_status(False)
        
        # Check for specific error conditions
        error_type = getattr(event, 'type', 'unknown')
        error_code = getattr(event, 'code', None)
        
        console.log(f"WebSocket error details - Type: {error_type}, Code: {error_code}")
        
        # If JavaScript WebSocket is available, gracefully fall back
        if hasattr(document.defaultView, 'tradingWebSocket'):
            js_ws = document.defaultView.tradingWebSocket
            if js_ws and js_ws.isConnected:
                console.log("Falling back to JavaScript WebSocket for real-time updates")
                self.handle_websocket_unavailable()
            else:
                console.log("JavaScript WebSocket also unavailable - enabling polling")
                self.handle_websocket_unavailable()
    
    def connect_websocket(self):
        """Connect to WebSocket server with enhanced error handling and connection state management"""
        # Prevent multiple connection attempts
        if self.websocket and self.is_connected:
            console.log("PyScript WebSocket already connected - skipping connection attempt")
            return
            
        # Check if JavaScript WebSocket is already active and working
        try:
            if hasattr(document.defaultView, 'tradingWebSocket') and document.defaultView.tradingWebSocket:
                js_ws = document.defaultView.tradingWebSocket
                if hasattr(js_ws, 'isConnected') and js_ws.isConnected:
                    console.log("JavaScript WebSocket is active and connected - using polling fallback for PyScript")
                    self.handle_websocket_unavailable()
                    return
                elif hasattr(js_ws, 'isConnecting') and js_ws.isConnecting:
                    console.log("JavaScript WebSocket is connecting - waiting before attempting PyScript connection")
                    # Wait a bit for JS WebSocket to finish connecting
                    setTimeout = document.defaultView.setTimeout
                    def retry_after_js_attempt():
                        self.connect_websocket()
                    setTimeout(create_proxy(retry_after_js_attempt), 2000)
                    return
        except Exception as e:
            console.warn(f"Error checking JavaScript WebSocket status: {e}")
            # Continue with PyScript connection attempt
        
        try:
            # Clean up any existing connection
            if self.websocket:
                self.websocket.close()
                self.websocket = None
                
            # Get WebSocket URL using improved method
            self.ws_url = self.get_websocket_url()
            console.log(f"Attempting PyScript WebSocket connection to: {self.ws_url}")
            
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
        """Update connection status indicator in UI - coordinated with JavaScript WebSocket"""
        # Check if JavaScript WebSocket is handling the connection
        try:
            if hasattr(document.defaultView, 'tradingWebSocket') and document.defaultView.tradingWebSocket:
                js_ws = document.defaultView.tradingWebSocket
                if hasattr(js_ws, 'isConnected') and js_ws.isConnected:
                    console.log("JavaScript WebSocket is connected - not updating status from PyScript")
                    return  # Don't override JavaScript WebSocket status
        except Exception as e:
            console.warn(f"Error checking JavaScript WebSocket for status update: {e}")
        
        # Use the same selector as JavaScript WebSocket to avoid conflicts
        status_indicator = document.querySelector("#connection-status .status-indicator")
        status_text = document.querySelector("#connection-status span:last-child")
        
        if status_indicator and status_text:
            if connected:
                status_indicator.className = "status-indicator online"
                status_text.textContent = "Conectado"
                console.log("PyScript WebSocket status: Connected")
            else:
                # Only set to disconnected if JavaScript WebSocket is also not connected
                try:
                    if hasattr(document.defaultView, 'tradingWebSocket') and document.defaultView.tradingWebSocket:
                        js_ws = document.defaultView.tradingWebSocket
                        if hasattr(js_ws, 'isConnected') and js_ws.isConnected:
                            console.log("JavaScript WebSocket still connected - not showing disconnected")
                            return
                except:
                    pass
                    
                status_indicator.className = "status-indicator offline"
                status_text.textContent = "Desconectado"
                console.log("PyScript WebSocket status: Disconnected")
    
    def send_websocket_message(self, message):
        """Enhanced WebSocket message sending with validation and queuing."""
        if not self.websocket:
            console.warn("WebSocket not initialized")
            return False
            
        if not self.is_connected:
            console.warn("WebSocket not connected - attempting reconnection")
            self.connect_websocket()
            return False
        
        # Validate message structure
        if not isinstance(message, dict) or "type" not in message:
            console.error("Invalid message format - must be dict with 'type' field")
            return False
            
        try:
            message_str = json.dumps(message)
            self.websocket.send(message_str)
            console.log(f"WebSocket sent: {message.get('type')}")
            return True
        except Exception as e:
            console.error(f"WebSocket send error: {str(e)}")
            self.is_connected = False
            return False
    
    def subscribe_to_channel(self, channel, send_snapshot=True):
        """Subscribe to a specific WebSocket channel."""
        message = {
            "type": "subscribe",
            "data": {
                "channel": channel,
                "send_snapshot": send_snapshot,
                "timestamp": datetime.now().isoformat()
            }
        }
        return self.send_websocket_message(message)
    
    def unsubscribe_from_channel(self, channel):
        """Unsubscribe from a specific WebSocket channel."""
        message = {
            "type": "unsubscribe",
            "data": {
                "channel": channel,
                "timestamp": datetime.now().isoformat()
            }
        }
        return self.send_websocket_message(message)
    
    def request_manual_update(self, update_type="general", **kwargs):
        """Request a manual update from the server."""
        message = {
            "type": "request_update",
            "data": {
                "type": update_type,
                "timestamp": datetime.now().isoformat(),
                **kwargs
            }
        }
        return self.send_websocket_message(message)
    
    def get_connection_stats(self):
        """Request connection statistics from the server."""
        message = {
            "type": "get_stats",
            "timestamp": datetime.now().isoformat()
        }
        return self.send_websocket_message(message)
    
    def send_ping(self):
        """Send ping to server and measure latency."""
        try:
            self.last_ping_time = datetime.now()
            message = {
                "type": "ping",
                "timestamp": self.last_ping_time.isoformat()
            }
            return self.send_websocket_message(message)
        except Exception as e:
            console.error(f"Failed to send ping: {e}")
            self.last_ping_time = None
            return False
    
    def handle_websocket_unavailable(self):
        """Handle case where WebSocket is not available - use efficient polling fallback"""
        console.log("WebSocket unavailable - JavaScript WebSocket will handle real-time updates")
        
        # Update UI to show we're using polling mode
        self.update_connection_status(False)
        
        # Show user notification about using JS WebSocket instead
        try:
            # Try to show notification if UI components are available
            from components import ui_components
            ui_components.show_notification(
                "Conexão", 
                "Usando conexão JavaScript para atualizações em tempo real.", 
                "info"
            )
        except:
            # Fallback if UI components not available
            console.log("PyScript using JavaScript WebSocket coordination mode")
        
        # Don't start aggressive polling - just mark as unavailable
        # The JavaScript WebSocket will handle real-time updates
        self.polling_active = False
        
        # Set up minimal health check polling (much less frequent)
        self.start_health_check_polling()
    
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
                                "timestamp": datetime.now().isoformat()
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
    
    def start_health_check_polling(self):
        """Start minimal health check polling (much less frequent than full polling)"""
        console.log("Starting minimal health check polling")
        
        # Set health check interval (60 seconds - much less frequent)
        self.health_check_interval = 60000  # milliseconds
        self.health_check_active = True
        
        # Use JavaScript setTimeout for health checks
        setTimeout = document.defaultView.setTimeout
        
        async def health_check():
            """Perform minimal health check"""
            if not self.health_check_active:
                return
            
            try:
                # Just check if API is responsive
                health_data = await self.health_check()
                if health_data:
                    console.log("API health check: OK")
                else:
                    console.warn("API health check: Failed")
                
            except Exception as e:
                console.error(f"Health check error: {str(e)}")
            
            # Schedule next health check
            if self.health_check_active:
                setTimeout(create_proxy(health_check), self.health_check_interval)
        
        # Start initial health check after 5 seconds
        setTimeout(create_proxy(health_check), 5000)
    
    def stop_health_check_polling(self):
        """Stop health check polling"""
        self.health_check_active = False
        console.log("Health check polling stopped")
    
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