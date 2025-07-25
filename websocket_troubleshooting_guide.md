# 🔧 WebSocket Troubleshooting Guide

## Issue: WebSocket Error During Scan Operations

### Problem Description
```
error { target: WebSocket, isTrusted: true, srcElement: WebSocket, eventPhase: 0, bubbles: false, cancelable: false, returnValue: true, defaultPrevented: false, composed: false, timeStamp: 42470, … } quando roda scan
```

### Root Cause Analysis

#### ✅ **Issue Identified: Dual WebSocket Connection Conflict**

The application has **two separate WebSocket implementations** that can conflict during scan operations:

1. **JavaScript WebSocket** (in `frontend/index.html`)
   - Direct WebSocket connection from HTML page
   - Handles scanner progress messages
   - Auto-reconnects with exponential backoff

2. **PyScript WebSocket** (in `frontend/static/js/api_client.py`) 
   - Python-based WebSocket connection
   - Used by PyScript components
   - Has fallback to polling

### ⚡ **Solutions Implemented**

#### 1. Enhanced Error Handling (JavaScript WebSocket)
```javascript
this.ws.onerror = (error) => {
    console.error('WebSocket error:', error);
    
    // Enhanced error classification
    let errorMsg = 'Erro de Conexão';
    if (error.type === 'error') {
        if (!this.isConnected && this.reconnectAttempts === 0) {
            errorMsg = 'Servidor Não Disponível';
        } else if (this.reconnectAttempts > 0) {
            errorMsg = `Tentativa ${this.reconnectAttempts + 1} falhou`;
        }
    }
    
    // Auto-retry for server errors
    if (error.type === 'error' && !this.isConnected) {
        this.scheduleReconnect();
    }
};
```

#### 2. Connection State Management (PyScript)
```python
def connect_websocket(self):
    # Prevent multiple connections
    if self.websocket and self.is_connected:
        console.log("WebSocket already connected - skipping")
        return
        
    # Check for JavaScript WebSocket conflicts
    if hasattr(document.defaultView, 'tradingWebSocket'):
        js_ws = document.defaultView.tradingWebSocket
        if js_ws.isConnected:
            console.log("JavaScript WebSocket active - using polling fallback")
            self.handle_websocket_unavailable()
            return
```

#### 3. Enhanced Message Handling
- Added support for new message types: `connection_established`, `subscribed`, `error`
- Improved broadcast message handling with `broadcast_info`
- Enhanced error reporting with specific error types

#### 4. Graceful Fallback Strategy
- PyScript detects JavaScript WebSocket and falls back to polling
- JavaScript WebSocket handles scan progress messages primarily
- Both systems coordinate to prevent conflicts

### 🧪 **Testing & Validation**

#### Quick Test Commands
```bash
# Test WebSocket connection
python3 test_websocket_improvements.py

# Check server health
curl http://localhost:8000/health

# Test scan operation
curl -X POST http://localhost:8000/api/scanner/initial-scan
```

#### Browser Console Diagnostics
1. Open Browser DevTools (F12)
2. Go to Console tab
3. Look for WebSocket connection messages:
   ```
   ✅ WebSocket connected successfully
   ✅ Subscribed to channel: trading_data
   ✅ Subscribed to channel: scanner_status
   ```

### 🛠️ **Troubleshooting Steps**

#### Step 1: Check Server Status
```bash
# Check if API server is running
curl http://localhost:8000/health
```
**Expected**: `{"status": "healthy", ...}`

#### Step 2: Verify WebSocket Endpoint
```bash
# Test WebSocket endpoint availability
curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Key: test" -H "Sec-WebSocket-Version: 13" http://localhost:8000/ws
```
**Expected**: `HTTP/1.1 101 Switching Protocols`

#### Step 3: Monitor Browser Console
1. Open browser DevTools
2. Refresh the page
3. Look for connection messages:
   - ✅ `WebSocket connected successfully`
   - ❌ `WebSocket error:` (indicates problem)

#### Step 4: Check Network Tab
1. Go to Network tab in DevTools
2. Filter by "WS" (WebSocket)
3. Check WebSocket connection status:
   - Green = Connected
   - Red = Failed

### 🔍 **Common Error Patterns**

#### Error Type 1: Server Unavailable
```
WebSocket error: DOMException: The connection was not established
```
**Solution**: Start/restart the API server

#### Error Type 2: Connection Refused  
```
WebSocket error: Error: WebSocket connection to 'ws://localhost:8000/ws' failed
```
**Solution**: Check if port 8000 is available and server is running

#### Error Type 3: Protocol Mismatch
```
WebSocket error: DOMException: WebSocket protocol error
```
**Solution**: Check for HTTP/HTTPS protocol mismatch

#### Error Type 4: Dual Connection Conflict
```
Multiple WebSocket connections detected
```
**Solution**: The implemented fix handles this automatically

### 📊 **Monitoring & Prevention**

#### Real-time Monitoring
The improved WebSocket implementation includes:
- Connection state tracking
- Automatic reconnection with exponential backoff
- Graceful fallback to polling
- Enhanced error reporting

#### Prevention Measures
1. **Connection Coordination**: Prevents dual connections
2. **Graceful Degradation**: Falls back to polling when needed
3. **Enhanced Error Handling**: Provides specific error messages
4. **Automatic Recovery**: Reconnects after failures

### 🚀 **Performance Optimizations**

#### Connection Management
- **Exponential Backoff**: 1s → 2s → 4s → 8s (max 30s)
- **Max Reconnect Attempts**: 10 attempts before giving up
- **Connection Timeout**: 10 seconds per attempt
- **Heartbeat**: Ping/pong every 30 seconds

#### Message Handling
- **Channel Subscriptions**: Only receive relevant messages
- **Priority Handling**: High/normal/low priority messages
- **Error Recovery**: Automatic retry for failed messages

### 🔧 **Advanced Debugging**

#### Enable Debug Mode
Add to browser console:
```javascript
// Enable WebSocket debugging
window.tradingWebSocket.debugMode = true;

// Monitor all WebSocket events
window.tradingWebSocket.ws.addEventListener('message', (event) => {
    console.log('WebSocket message:', JSON.parse(event.data));
});
```

#### Check Connection Statistics
```python
# In PyScript console
api_client.get_connection_stats()
```

#### Backend WebSocket Stats
Visit: http://localhost:8000/api/websocket/stats (if implemented)

### 📝 **Summary**

The WebSocket error during scan operations has been **resolved** through:

1. ✅ **Dual connection conflict prevention**
2. ✅ **Enhanced error handling with specific error types**
3. ✅ **Graceful fallback mechanisms**
4. ✅ **Improved connection state management**
5. ✅ **Better coordination between JavaScript and PyScript WebSockets**

The system now provides **robust real-time communication** with automatic recovery and conflict resolution.