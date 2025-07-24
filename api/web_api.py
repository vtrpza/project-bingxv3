"""
FastAPI Web API for BingX Trading Bot
Provides REST endpoints and WebSocket connections for the frontend
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any, Optional
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from datetime import timedelta

from database.connection import get_db, init_database, create_tables
from database.repository import (
    AssetRepository, IndicatorRepository, 
    SignalRepository, TradeRepository, OrderRepository
)
from sqlalchemy.orm import Session
from utils.logger import get_logger
from config.settings import get_settings

logger = get_logger(__name__)
settings = get_settings()

app = FastAPI(
    title="BingX Trading Bot API",
    description="Real-time trading bot dashboard and control API",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    import asyncio
    import random
    
    try:
        # Add random delay to prevent multiple instances from starting at exact same time
        startup_delay = random.uniform(0.1, 2.0)
        logger.info(f"Starting up with {startup_delay:.2f}s delay to prevent deadlocks...")
        await asyncio.sleep(startup_delay)
        
        logger.info("Initializing database...")
        if not init_database():
            logger.warning("Database initialization failed - running without database")
            return
        
        logger.info("Dropping existing database tables (if any)...")
        from database.connection import db_manager
        if not db_manager.drop_tables():
            logger.warning("Database table dropping failed - continuing anyway")
            # Continue to try creating tables even if dropping fails
        
        logger.info("Creating database tables...")
        if not create_tables():
            logger.warning("Database table creation failed - running without database")
            return
        
        logger.info("Database initialization completed successfully")
        
        # Start background tasks
        await start_background_tasks()
    
    except Exception as e:
        logger.warning(f"Database initialization failed: {e} - running without database")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
frontend_path = Path(__file__).parent.parent / "frontend"
static_path = frontend_path / "static"

# Mount static assets first (more specific routes should come first)
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Add API routes before mounting the frontend root
# (This is done below in the route definitions)

# Mount the frontend directory last to serve index.html and other files
# This should be after all API routes to avoid conflicts
def mount_frontend():
    if frontend_path.exists():
        app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
            self.disconnect(websocket)
    
    async def broadcast(self, message: Dict[str, Any]):
        if not self.active_connections:
            return
            
        message_str = json.dumps(message, default=str)
        disconnected = []
        
        for connection in self.active_connections:
            try:
                await connection.send_text(message_str)
            except Exception as e:
                logger.error(f"Error broadcasting to connection: {e}")
                disconnected.append(connection)
        
        # Remove disconnected connections
        for conn in disconnected:
            self.disconnect(conn)

manager = ConnectionManager()

# Dependency injection
def get_asset_repo():
    return AssetRepository()

def get_indicator_repo():
    return IndicatorRepository()

def get_signal_repo():
    return SignalRepository()

def get_trade_repo():
    return TradeRepository()

def get_position_repo():
    return TradeRepository()

# Note: Root endpoint is now handled by StaticFiles mount above

# Health check
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow(),
        "version": "1.0.0"
    }

@app.get("/api/test-db")
async def test_database():
    """Test database connection and assets"""
    try:
        from database.connection import get_session
        asset_repo = AssetRepository()
        
        with get_session() as db:
            assets = asset_repo.get_all(db, limit=5)
            return {
                "status": "success",
                "assets_count": len(assets),
                "sample_assets": [
                    {
                        "symbol": asset.symbol,
                        "is_valid": asset.is_valid,
                        "last_validation": asset.last_validation.isoformat() if asset.last_validation else None
                    }
                    for asset in assets[:3]
                ]
            }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "type": type(e).__name__
        }


# Asset validation table endpoint
@app.get("/api/assets/validation-table")
async def get_asset_validation_table(
    limit: Optional[int] = None,
    offset: Optional[int] = 0,
    include_invalid: bool = True
):
    """Get comprehensive asset validation table with all metrics from database"""
    try:
        logger.info(f"Asset validation table requested - offset: {offset}, limit: {limit}")
        
        from database.connection import get_session
        asset_repo = AssetRepository()
        
        with get_session() as db:
            # Get total count first
            total_count = asset_repo.get_count(db)
            
            # If no limit specified, return all assets for full revalidation
            # Otherwise use pagination
            if limit is None:
                all_assets = asset_repo.get_all(db, limit=None)
                logger.info(f"Fetching ALL assets for revalidation: {len(all_assets)} total")
            else:
                all_assets = asset_repo.get_paginated(db, limit=limit, offset=offset or 0)
                logger.info(f"Fetching paginated assets: {len(all_assets)} (offset: {offset}, limit: {limit})")
            
            table_data = []
            for asset in all_assets:
                # Extrair dados de validação
                val_data = asset.validation_data or {}
                market_summary = val_data.get('market_summary', {})
                
                table_data.append({
                    "symbol": asset.symbol,
                    "base_currency": asset.base_currency,
                    "quote_currency": asset.quote_currency,
                    "validation_status": "VALID" if asset.is_valid else "INVALID",
                    "validation_score": 100 if asset.is_valid else 0,
                    "priority_asset": val_data.get('priority', False),
                    "current_price": float(market_summary.get('price', 0)) if market_summary.get('price') else None,
                    "price_change_24h": float(market_summary.get('change_24h', 0)) if market_summary.get('change_24h') else None,
                    "price_change_percent_24h": float(market_summary.get('change_percent_24h', 0)) if market_summary.get('change_percent_24h') else None,
                    "volume_24h_quote": float(market_summary.get('quote_volume_24h', 0)) if market_summary.get('quote_volume_24h') else None,
                    "volume_change_percent": None,
                    "volume_spike_detected": False,
                    "volume_trend": None,
                    "spread_percent": float(market_summary.get('spread_percent', 0)) if market_summary.get('spread_percent') else None,
                    "mm1_2h": None,
                    "center_2h": None,
                    "rsi_2h": None,
                    "mm1_4h": None,
                    "center_4h": None,
                    "rsi_4h": None,
                    "ma_distance_2h": None,
                    "ma_distance_4h": None,
                    "ma_direction_2h": None,
                    "ma_direction_4h": None,
                    "rsi_condition_2h": None,
                    "rsi_condition_4h": None,
                    "signal_2h": None,
                    "signal_4h": None,
                    "signal_strength": None,
                    "rules_triggered": [],
                    "risk_level": "LOW" if asset.is_valid else "HIGH",
                    "volatility_24h": abs(float(market_summary.get('change_percent_24h', 0))) if market_summary.get('change_percent_24h') else None,
                    "last_updated": asset.last_validation.isoformat() if asset.last_validation else datetime.utcnow().isoformat(),
                    "data_quality_score": 90 if asset.is_valid else 10,
                    "api_response_time": val_data.get('validation_duration', 0),
                    "validation_reasons": list(val_data.get('validation_checks', {}).keys()) if val_data.get('validation_checks') else []
                })
            
            # Filtrar se necessário
            if not include_invalid:
                table_data = [d for d in table_data if d['validation_status'] == 'VALID']
            
            # Summary statistics
            total_assets = len(table_data)
            valid_assets = len([d for d in table_data if d['validation_status'] == 'VALID'])
            priority_assets = len([d for d in table_data if d['priority_asset']])
            assets_with_signals = len([d for d in table_data if d['signal_2h'] or d['signal_4h']])
            
            # Add pagination metadata
            pagination = {
                "current_page": (offset // limit) + 1 if limit and limit > 0 else 1,
                "total_pages": ((total_count - 1) // limit) + 1 if limit and limit > 0 else 1,
                "page_size": limit or total_count,
                "total_records": total_count,
                "has_next": (offset + len(all_assets)) < total_count if limit else False,
                "has_previous": offset > 0 if limit else False
            }
            
            return {
                "table_data": table_data,
                "summary": {
                    "total_assets": total_assets,
                    "valid_assets": valid_assets,
                    "invalid_assets": total_assets - valid_assets,
                    "priority_assets": priority_assets,
                    "assets_with_signals": assets_with_signals,
                    "validation_success_rate": (valid_assets / total_assets * 100) if total_assets > 0 else 0,
                    "last_updated": datetime.utcnow().isoformat()
                },
                "pagination": pagination
            }
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error generating validation table: {e}")
        logger.error(f"Full traceback: {error_details}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# Background task to track revalidation status
revalidation_status = {"running": False, "progress": 0, "total": 0, "completed": False, "error": None}

async def run_revalidation_task():
    """Run the revalidation task and track its progress"""
    global revalidation_status
    try:
        from scanner.initial_scanner import perform_initial_scan
        
        revalidation_status["running"] = True
        revalidation_status["progress"] = 0
        revalidation_status["total"] = 0
        revalidation_status["completed"] = False
        revalidation_status["error"] = None
        
        logger.info("Starting full asset revalidation...")
        result = await perform_initial_scan(force_refresh=True)
        
        if result:
            revalidation_status["total"] = result.total_discovered
            revalidation_status["progress"] = result.total_discovered
            revalidation_status["completed"] = True
            logger.info(f"Revalidation completed: {result.get_summary()}")
        else:
            revalidation_status["error"] = "Revalidation failed"
            
    except Exception as e:
        logger.error(f"Error during revalidation: {e}")
        revalidation_status["error"] = str(e)
    finally:
        revalidation_status["running"] = False

# Force revalidation endpoint
@app.post("/api/assets/force-revalidation")
async def force_revalidation():
    """Force a full revalidation of all assets"""
    global revalidation_status
    
    try:
        # Check if revalidation is already running
        if revalidation_status.get("running", False):
            return {
                "message": "Revalidation already in progress",
                "status": revalidation_status
            }
        
        # Start revalidation task
        asyncio.create_task(run_revalidation_task())
        
        return {
            "message": "Revalidation process started",
            "status": revalidation_status
        }
    except Exception as e:
        logger.error(f"Error forcing revalidation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Get revalidation status endpoint
@app.get("/api/assets/revalidation-status")
async def get_revalidation_status():
    """Get the current status of the revalidation process"""
    status_copy = revalidation_status.copy()
    if not status_copy["running"] and status_copy["total"] == 0:
        status_copy["message"] = "No revalidation in progress or no assets found."
    elif not status_copy["running"] and status_copy["completed"]:
        status_copy["message"] = "Revalidation completed."
    elif status_copy["running"]:
        status_copy["message"] = "Revalidation in progress."
    return {"status": status_copy}

# Asset endpoints
@app.get("/api/assets")
async def get_assets(
    valid_only: bool = True,
    limit: int = 100,
    repo: AssetRepository = Depends(get_asset_repo)
):
    """Get list of assets"""
    try:
        from database.connection import get_session
        
        with get_session() as db:
            if valid_only:
                assets = repo.get_valid_assets(db)
            else:
                assets = repo.get_all(db, limit=limit)
        return {
            "assets": [
                {
                    "id": str(asset.id),
                    "symbol": asset.symbol,
                    "base_currency": asset.base_currency,
                    "quote_currency": asset.quote_currency,
                    "is_valid": asset.is_valid,
                    "last_validation": asset.last_validation,
                    "validation_data": asset.validation_data
                }
                for asset in assets
            ],
            "total": len(assets)
        }
    except Exception as e:
        logger.error(f"Error fetching assets: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/assets/{symbol}")
async def get_asset_details(
    symbol: str,
    repo: AssetRepository = Depends(get_asset_repo)
):
    """Get detailed information about a specific asset"""
    try:
        asset = await repo.get_asset_by_symbol(symbol)
        if not asset:
            raise HTTPException(status_code=404, detail="Asset not found")
        
        return {
            "id": str(asset.id),
            "symbol": asset.symbol,
            "base_currency": asset.base_currency,
            "quote_currency": asset.quote_currency,
            "is_valid": asset.is_valid,
            "last_validation": asset.last_validation,
            "validation_data": asset.validation_data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching asset {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Indicator endpoints
@app.get("/api/indicators/{symbol}")
async def get_indicators(
    symbol: str,
    timeframe: Optional[str] = None,
    limit: int = 50,
    repo: IndicatorRepository = Depends(get_indicator_repo),
    asset_repo: AssetRepository = Depends(get_asset_repo)
):
    """Get technical indicators for a symbol"""
    try:
        from database.connection import get_session
        
        with get_session() as db:
            # Get asset by symbol first
            asset = asset_repo.get_by_symbol(db, symbol)
            if not asset:
                raise HTTPException(status_code=404, detail=f"Asset {symbol} not found")
            
            # Get indicators for this asset
            indicators = repo.get_latest_indicators(db, asset_id=str(asset.id))
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "indicators": [
                {
                    "id": str(ind.id),
                    "timestamp": ind.timestamp.isoformat() if ind.timestamp else None,
                    "timeframe": ind.timeframe,
                    "mm1": float(ind.mm1) if ind.mm1 else None,
                    "center": float(ind.center) if ind.center else None,
                    "rsi": float(ind.rsi) if ind.rsi else None,
                    "volume_sma": float(ind.volume_sma) if ind.volume_sma else None,
                    "additional_data": ind.additional_data
                }
                for ind in indicators
            ],
            "total": len(indicators)
        }
    except Exception as e:
        logger.error(f"Error fetching indicators for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/indicators")
async def get_latest_indicators(
    limit: int = 100,
    db: Session = Depends(get_db),
    repo: IndicatorRepository = Depends(get_indicator_repo)
):
    """Get latest indicators for all symbols"""
    try:
        latest_indicators = repo.get_latest_indicators_for_all_assets(db, limit=limit)
        return {
            "indicators": [
                {
                    "symbol": ind.asset.symbol,
                    "timeframe": ind.timeframe,
                    "price": ind.center,  # Use center as reference price
                    "mm1": ind.mm1,
                    "center": ind.center,
                    "rsi": ind.rsi,
                    "volume_ratio": ind.volume_sma, # Placeholder
                    "timestamp": ind.timestamp.isoformat()
                }
                for ind in latest_indicators
            ],
            "total": len(latest_indicators)
        }
    except Exception as e:
        logger.error(f"Error fetching latest indicators: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Signal endpoints
@app.get("/api/signals")
async def get_signals(
    symbol: Optional[str] = None,
    signal_type: Optional[str] = None,
    limit: int = 50,
    repo: SignalRepository = Depends(get_signal_repo)
):
    """Get trading signals"""
    try:
        signals = await repo.get_signals(symbol, signal_type, limit)
        return {
            "signals": [
                {
                    "id": str(signal.id),
                    "symbol": signal.symbol,
                    "signal_type": signal.signal_type,
                    "side": signal.side,
                    "strength": float(signal.strength) if signal.strength else None,
                    "confidence": float(signal.confidence) if signal.confidence else None,
                    "price": float(signal.price) if signal.price else None,
                    "data": signal.data,
                    "is_processed": signal.is_processed,
                    "created_at": signal.created_at
                }
                for signal in signals
            ],
            "total": len(signals)
        }
    except Exception as e:
        logger.error(f"Error fetching signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/signals/active")
async def get_active_signals(
    repo: SignalRepository = Depends(get_signal_repo)
):
    """Get unprocessed signals"""
    try:
        signals = await repo.get_unprocessed_signals()
        return {
            "active_signals": [
                {
                    "id": str(signal.id),
                    "symbol": signal.symbol,
                    "signal_type": signal.signal_type,
                    "side": signal.side,
                    "strength": float(signal.strength) if signal.strength else None,
                    "confidence": float(signal.confidence) if signal.confidence else None,
                    "price": float(signal.price) if signal.price else None,
                    "created_at": signal.created_at
                }
                for signal in signals
            ],
            "total": len(signals)
        }
    except Exception as e:
        logger.error(f"Error fetching active signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Trade endpoints
@app.get("/api/trades")
async def get_trades(
    symbol: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    repo: TradeRepository = Depends(get_trade_repo)
):
    """Get trade history"""
    try:
        trades = repo.get_trades(
            db,
            symbol=symbol,
            status=status,
            limit=limit
        )
        return {
            "trades": [
                {
                    "id": str(t.id),
                    "symbol": t.asset.symbol if t.asset else "UNKNOWN",
                    "side": t.side,
                    "amount": float(t.quantity) if t.quantity else 0,
                    "price": float(t.entry_price) if t.entry_price else 0,
                    "status": t.status,
                    "created_at": t.created_at.isoformat() if t.created_at else None
                }
                for t in trades
            ],
            "total": len(trades)
        }
    except Exception as e:
        logger.error(f"Error fetching trades: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Position endpoints
@app.get("/api/positions")
async def get_positions(
    active_only: bool = True,
    db: Session = Depends(get_db),
    repo: TradeRepository = Depends(get_position_repo)
):
    """Get current positions"""
    try:
        if active_only:
            positions = repo.get_open_positions(db)
        else:
            positions = repo.get_all(db, limit=100)  # Get all trades as positions
            
        return {
            "positions": [
                {
                    "id": str(p.id),
                    "symbol": p.symbol,
                    "side": p.side,
                    "amount": p.amount,
                    "entry_price": p.entry_price,
                    "current_price": p.current_price,  # Assuming this is updated
                    "unrealized_pnl": p.unrealized_pnl,
                    "stop_loss_price": p.stop_loss_price,
                    "take_profit_price": p.take_profit_price,
                    "status": p.status
                }
                for p in positions
            ],
            "total": len(positions)
        }
    except Exception as e:
        logger.error(f"Error fetching positions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Bot control endpoints
bot_status = {"running": False, "trading_enabled": False}

@app.post("/api/bot/start")
async def start_bot():
    """Start the bot system"""
    try:
        global bot_status
        if bot_status["running"]:
            raise HTTPException(status_code=400, detail="Bot já está ativo")
        
        # TODO: Implement actual bot startup logic
        # This would start the scanner workers, analysis workers, etc.
        bot_status["running"] = True
        
        logger.info("Bot started via API")
        
        return {
            "message": "Bot iniciado com sucesso",
            "status": bot_status,
            "timestamp": datetime.utcnow()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/bot/stop")
async def stop_bot():
    """Stop the bot system"""
    try:
        global bot_status
        if not bot_status["running"]:
            raise HTTPException(status_code=400, detail="Bot já está parado")
        
        # TODO: Implement actual bot shutdown logic
        # This would stop all workers gracefully
        bot_status["running"] = False
        bot_status["trading_enabled"] = False
        
        logger.info("Bot stopped via API")
        
        return {
            "message": "Bot parado com sucesso",
            "status": bot_status,
            "timestamp": datetime.utcnow()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/bot/status")
async def get_bot_status():
    """Get current bot status"""
    return {
        "status": bot_status,
        "timestamp": datetime.utcnow()
    }

@app.post("/api/trading/start")
async def start_trading():
    """Enable trading operations"""
    try:
        global bot_status
        if not bot_status["running"]:
            raise HTTPException(status_code=400, detail="Bot deve estar ativo para iniciar trading")
        
        if bot_status["trading_enabled"]:
            raise HTTPException(status_code=400, detail="Trading já está ativo")
        
        # TODO: Implement actual trading enable logic
        # This would enable order execution, position management, etc.
        bot_status["trading_enabled"] = True
        
        logger.info("Trading enabled via API")
        
        return {
            "message": "Trading iniciado com sucesso",
            "status": bot_status,
            "timestamp": datetime.utcnow()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting trading: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/trading/stop")
async def stop_trading():
    """Disable trading operations"""
    try:
        global bot_status
        if not bot_status["trading_enabled"]:
            raise HTTPException(status_code=400, detail="Trading já está inativo")
        
        # TODO: Implement actual trading disable logic
        # This would stop new order executions but keep monitoring
        bot_status["trading_enabled"] = False
        
        logger.info("Trading disabled via API")
        
        return {
            "message": "Trading parado com sucesso",
            "status": bot_status,
            "timestamp": datetime.utcnow()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping trading: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Dashboard summary endpoint
@app.get("/api/dashboard/summary")
async def get_dashboard_summary(
    db: Session = Depends(get_db),
    asset_repo: AssetRepository = Depends(get_asset_repo),
    signal_repo: SignalRepository = Depends(get_signal_repo),
    trade_repo: TradeRepository = Depends(get_trade_repo)
):
    """Get dashboard summary data"""
    try:
        valid_assets = asset_repo.get_valid_assets_count(db)
        active_signals = signal_repo.get_active_signals_count(db)
        
        # Get positions and P&L
        positions = trade_repo.get_open_positions(db)
        total_pnl = sum(p.unrealized_pnl for p in positions if p.unrealized_pnl)
        
        # Get recent trades
        recent_trades = trade_repo.get_trades_since(db, datetime.utcnow() - timedelta(days=1))
        
        return {
            "summary": {
                "valid_assets": valid_assets,
                "active_signals": active_signals,
                "active_positions": len(positions),
                "total_unrealized_pnl": total_pnl,
                "recent_trades_count": len(recent_trades)
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching dashboard summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    client_host = websocket.client.host if websocket.client else "unknown"
    logger.info(f"WebSocket connection attempt from {client_host}")
    
    await manager.connect(websocket)
    logger.info(f"WebSocket connected from {client_host}")
    
    try:
        while True:
            # Keep connection alive and handle incoming messages
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle different message types
            if message.get("type") == "ping":
                await websocket.send_text(json.dumps({
                    "type": "pong", 
                    "timestamp": datetime.utcnow().isoformat(),
                    "server_info": "BingX Trading Bot WebSocket"
                }))
                logger.debug(f"Pong sent to {client_host}")
            elif message.get("type") == "subscribe":
                # Handle subscription requests
                await websocket.send_text(json.dumps({
                    "type": "subscribed", 
                    "data": message.get("data"),
                    "timestamp": datetime.utcnow().isoformat()
                }))
                logger.info(f"Subscription confirmed for {client_host}: {message.get('data')}")
            else:
                logger.warning(f"Unknown message type from {client_host}: {message.get('type')}")
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected from {client_host}")
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error from {client_host}: {e}")
        manager.disconnect(websocket)

# Background task to broadcast real-time data
async def broadcast_realtime_data():
    """Background task to send real-time updates to connected clients"""
    last_broadcast_time = None
    
    while True:
        try:
            if manager.active_connections:
                current_time = datetime.utcnow()
                
                # Só faz broadcast a cada 15 segundos para evitar spam e concorrência
                if (last_broadcast_time is None or 
                    (current_time - last_broadcast_time).total_seconds() >= 15):
                    
                    # Simples notificação de que há uma atualização disponível
                    # O frontend fará a chamada API para buscar os dados atualizados
                    broadcast_data = {
                        "type": "realtime_update", 
                        "timestamp": current_time.isoformat(),
                        "data": {
                            "update_available": True,
                            "message": "Data refresh recommended"
                        }
                    }
                    
                    await manager.broadcast(broadcast_data)
                    last_broadcast_time = current_time
                    logger.debug(f"Sent update notification to {len(manager.active_connections)} clients")
                
        except Exception as e:
            logger.error(f"Error in broadcast task: {e}")
            # Continue the loop even if one broadcast fails
        
        # Wait 15 seconds before next check (aumentado de 5 para 15)
        await asyncio.sleep(15)

# Start background task - merge with main startup event
async def start_background_tasks():
    """Start background tasks"""
    asyncio.create_task(broadcast_realtime_data())
    logger.info("Background tasks started")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("FastAPI server shutting down")

# Mount frontend after all API routes are defined
mount_frontend()

if __name__ == "__main__":
    import uvicorn
    import os
    # Render's default port is 10000
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        reload=settings.DEBUG
    )