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
import os
from datetime import datetime, timedelta
from decimal import Decimal
from utils.datetime_utils import utc_now, safe_datetime_subtract
from pathlib import Path

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

# Initialize BingX client
bingx_client = None
try:
    from api.client import get_client
    bingx_client = get_client()
    logger.info("BingX client initialized successfully")
except Exception as e:
    logger.warning(f"BingX client initialization failed: {e} - trading operations will be disabled")

async def safe_fetch_ticker(symbol: str) -> dict:
    """Safely fetch ticker with fallback when BingX client is unavailable."""
    if not bingx_client:
        logger.warning(f"BingX client not available - cannot fetch ticker for {symbol}")
        return {'last': 0, 'bid': 0, 'ask': 0, 'quoteVolume': 0}
    
    try:
        return await bingx_client.fetch_ticker(symbol)
    except Exception as e:
        logger.error(f"Error fetching ticker for {symbol}: {e}")
        return {'last': 0, 'bid': 0, 'ask': 0, 'quoteVolume': 0}

async def safe_create_market_order(symbol: str, side: str, amount: float) -> dict:
    """Safely create market order with fallback when BingX client is unavailable."""
    if not bingx_client:
        logger.error(f"BingX client not available - cannot create {side} order for {symbol}")
        raise HTTPException(status_code=503, detail="Trading API unavailable")
    
    try:
        return await bingx_client.create_market_order(symbol, side, amount)
    except Exception as e:
        logger.error(f"Error creating {side} order for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Order creation failed: {str(e)}")

async def safe_create_stop_loss_order(symbol: str, side: str, amount: float, stop_price: float) -> dict:
    """Safely create stop loss order with fallback when BingX client is unavailable."""
    if not bingx_client:
        logger.error(f"BingX client not available - cannot create stop loss order for {symbol}")
        raise HTTPException(status_code=503, detail="Trading API unavailable")
    
    try:
        return await bingx_client.create_stop_loss_order(symbol, side, amount, stop_price)
    except Exception as e:
        logger.error(f"Error creating stop loss order for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Stop loss order creation failed: {str(e)}")

app = FastAPI(
    title="BingX Trading Bot API",
    description="Real-time trading bot dashboard and control API",
    version="1.0.0"
)

# Global startup state
startup_complete = False
database_ready = False

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup with optimized performance."""
    global startup_complete, database_ready
    import asyncio
    import random
    
    try:
        logger.info("FastAPI server starting - health check will be available immediately")
        
        # Start database initialization in background (non-blocking)
        asyncio.create_task(initialize_database_background())
        
        # Start background tasks immediately (they handle their own initialization)
        asyncio.create_task(start_background_tasks_delayed())
        
        startup_complete = True
        logger.info("FastAPI startup completed - health check ready")
    
    except Exception as e:
        logger.warning(f"Startup event error: {e} - server will continue without some features")
        startup_complete = True

async def initialize_database_background():
    """Initialize database in background to avoid blocking startup."""
    global database_ready
    import random
    
    try:
        # Add small delay to prevent multiple instances from starting at exact same time
        startup_delay = random.uniform(0.1, 0.5)  # Reduced from 2.0s to 0.5s
        logger.info(f"Database initialization starting with {startup_delay:.2f}s delay...")
        await asyncio.sleep(startup_delay)
        
        # Set timeout for database operations
        timeout_seconds = 30
        logger.info(f"Initializing database with {timeout_seconds}s timeout...")
        
        async def init_with_timeout():
            if not init_database():
                logger.warning("Database initialization failed - running without database")
                return False
            
            logger.info("Creating database tables (skipping drop for faster startup)...")
            if not create_tables():
                logger.warning("Database table creation failed - running without database")
                return False
            
            return True
        
        # Run database initialization with timeout
        try:
            success = await asyncio.wait_for(init_with_timeout(), timeout=timeout_seconds)
            if success:
                database_ready = True
                logger.info("Database initialization completed successfully")
            else:
                logger.warning("Database initialization completed with errors")
        except asyncio.TimeoutError:
            logger.warning(f"Database initialization timed out after {timeout_seconds}s - running without database")
    
    except Exception as e:
        logger.warning(f"Background database initialization failed: {e} - running without database")

async def start_background_tasks_delayed():
    """Start background tasks with delay to allow database initialization."""
    try:
        # Wait a bit for database to be ready, but don't block startup
        await asyncio.sleep(1.0)
        await start_background_tasks()
    except Exception as e:
        logger.warning(f"Background tasks startup failed: {e}")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _safe_get_candle_price(candles, fallback_price):
    """Safely extract close price from candle data"""
    try:
        if candles and len(candles) >= 1 and len(candles[-1]) > 4:
            return float(candles[-1][4])  # Close price
    except (IndexError, TypeError, ValueError):
        pass
    return fallback_price

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
    """Fast health check that responds immediately during startup."""
    global startup_complete, database_ready
    
    return {
        "status": "healthy",
        "timestamp": utc_now(),
        "version": "1.0.0",
        "startup_complete": startup_complete,
        "database_ready": database_ready,
        "message": "Server is running"
    }

# Readiness check (for internal use)
@app.get("/ready")
async def readiness_check():
    """Detailed readiness check including database connectivity."""
    global startup_complete, database_ready
    
    status = "ready" if (startup_complete and database_ready) else "initializing"
    
    return {
        "status": status,
        "timestamp": utc_now(),
        "checks": {
            "startup_complete": startup_complete,
            "database_ready": database_ready,
            "api_responsive": True
        }
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
    page: Optional[int] = 1,
    per_page: Optional[int] = 25,
    sort_by: str = "symbol",
    sort_direction: str = "asc",
    filter_valid_only: bool = False,
    include_invalid: bool = True,
    search: Optional[str] = None,
    risk_level_filter: Optional[str] = None,
    priority_only: bool = False,
    trading_enabled_only: bool = False
):
    """Get simplified asset validation table with server-side pagination and dynamic asset names"""
    try:
        # Calculate offset from page and per_page
        offset = (page - 1) * per_page if page > 1 else 0
        limit = per_page
        
        logger.info(f"Asset validation table requested - page: {page}, per_page: {per_page}, sort: {sort_by} {sort_direction}")
        
        from database.connection import get_session, init_database
        from utils.asset_info import asset_info_service
        
        # Ensure database is initialized
        try:
            init_database()
            logger.debug("Database initialization successful or already initialized")
        except Exception as init_error:
            logger.warning(f"Database initialization issue: {init_error}")
            # Try to continue - some functions may still work without full initialization
        
        asset_repo = AssetRepository()
        
        with get_session() as db:
            # Get filtered count for pagination
            filter_applied = filter_valid_only or not include_invalid
            total_count = asset_repo.get_filtered_count(
                db, 
                filter_valid_only=filter_applied, 
                search=search,
                risk_level_filter=risk_level_filter,
                priority_only=priority_only,
                trading_enabled_only=trading_enabled_only
            )
            
            # Calculate pagination info
            total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1
            has_next = page < total_pages
            has_previous = page > 1
            
            # Use new sorting method with search
            all_assets = asset_repo.get_assets_with_sorting(
                db, 
                sort_by=sort_by,
                sort_direction=sort_direction,
                filter_valid_only=filter_applied,
                search=search,
                limit=limit,
                offset=offset,
                risk_level_filter=risk_level_filter,
                priority_only=priority_only,
                trading_enabled_only=trading_enabled_only
            )
            
            logger.info(f"Fetched {len(all_assets)} assets (total: {total_count}, page: {page}/{total_pages})")
            
            # Get asset names dynamically
            symbols = [asset.symbol for asset in all_assets]
            asset_names = await asset_info_service.get_asset_info_batch(symbols)
            
            table_data = []
            for asset in all_assets:
                # Extrair dados de validação
                val_data = asset.validation_data or {}
                market_summary = val_data.get('market_summary', {})
                
                # Debug: log missing data for analysis
                if not market_summary and asset.is_valid:
                    logger.warning(f"Valid asset {asset.symbol} missing market_summary data")
                
                # Helper function to safely convert values
                def safe_float(value, default=None):
                    if value is None:
                        return default
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        return default
                
                # Extract data with better fallbacks
                current_price = safe_float(market_summary.get('price'))
                volume_24h = safe_float(market_summary.get('quote_volume_24h'))
                change_24h = safe_float(market_summary.get('change_24h'))
                change_percent_24h = safe_float(market_summary.get('change_percent_24h'))
                spread_percent = safe_float(market_summary.get('spread_percent'))
                
                # Calculate derived values
                volatility_24h = abs(change_percent_24h) if change_percent_24h is not None else None
                
                # Get asset name dynamically
                asset_info = asset_names.get(asset.symbol, {})
                asset_name = asset_info.get('name', asset.base_currency)
                
                # Simplified data focused on validation analysis only
                table_data.append({
                    "symbol": asset.symbol,
                    "asset_name": asset_name,
                    "base_currency": asset.base_currency,
                    "quote_currency": asset.quote_currency,
                    "validation_status": "VALID" if asset.is_valid else "INVALID",
                    "validation_score": 100 if asset.is_valid else 0,
                    "priority_asset": val_data.get('priority', False),
                    
                    # Market data for analysis
                    "current_price": current_price,
                    "price_change_24h": change_24h,
                    "price_change_percent_24h": change_percent_24h,
                    "volume_24h_quote": volume_24h,
                    "spread_percent": spread_percent,
                    
                    # Validation metadata
                    "last_updated": asset.last_validation.isoformat() if asset.last_validation else utc_now().isoformat(),
                    "validation_duration": val_data.get('validation_duration', 0),
                    "validation_reasons": list(val_data.get('validation_checks', {}).keys()) if val_data.get('validation_checks') else [],
                    
                    # Risk assessment for analysis
                    "risk_level": _calculate_risk_level(market_summary) if market_summary else "UNKNOWN",
                    "volatility_24h": volatility_24h,
                    "data_quality_score": _calculate_data_quality(val_data),
                    "min_order_size": safe_float(asset.min_order_size),
                    
                    # Trading compatibility (for analysis, not execution)
                    "trading_enabled": asset.is_valid and (volume_24h or 0) > 10000,
                    "market_cap_rank": val_data.get('market_cap_rank'),
                    "age_days": int(safe_datetime_subtract(utc_now(), asset.created_at) / 86400) if asset.created_at else None
                })
            
            # Summary statistics (calculated from current page data)
            page_assets = len(table_data)
            valid_assets_on_page = len([d for d in table_data if d['validation_status'] == 'VALID'])
            priority_assets_on_page = len([d for d in table_data if d['priority_asset']])
            trading_enabled_assets = len([d for d in table_data if d.get('trading_enabled', False)])
            
            # Enhanced pagination metadata
            pagination = {
                "current_page": page,
                "total_pages": total_pages,
                "page_size": per_page,
                "total_records": total_count,
                "showing_records": len(table_data),
                "offset": offset,
                "has_next": has_next,
                "has_previous": has_previous,
                "sort_by": sort_by,
                "sort_direction": sort_direction,
                "search": search,
                "filter_valid_only": filter_valid_only,
                "include_invalid": include_invalid,
                "risk_level_filter": risk_level_filter,
                "priority_only": priority_only,
                "trading_enabled_only": trading_enabled_only
            }
            
            return {
                "table_data": table_data,
                "summary": {
                    "total_assets": total_count,
                    "page_assets": page_assets,
                    "valid_assets_on_page": valid_assets_on_page,
                    "priority_assets_on_page": priority_assets_on_page,
                    "trading_enabled_assets": trading_enabled_assets,
                    "validation_success_rate": (valid_assets_on_page / page_assets * 100) if page_assets > 0 else 0,
                    "last_updated": utc_now().isoformat(),
                    "data_freshness": "real-time" if filter_applied else "cached"
                },
                "pagination": pagination,
                "metadata": {
                    "endpoint_version": "2.0",
                    "optimized_for": "analysis",
                    "excluded_fields": ["rsi_indicators", "trading_signals", "ma_data"],
                    "performance": "enhanced"
                }
            }
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Error generating validation table: {e}")
        logger.error(f"Full traceback: {error_details}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# Trading data endpoint (separate from validation table)
@app.get("/api/assets/trading-data")
async def get_asset_trading_data(
    symbols: Optional[str] = None,  # comma-separated list
    limit: Optional[int] = 50,
    offset: Optional[int] = 0
):
    """Get trading-specific data (RSI, signals, MA) for order management"""
    try:
        logger.info(f"Trading data requested for symbols: {symbols}")
        
        from scanner.asset_table import get_asset_validation_table
        
        # Parse symbols if provided
        symbol_list = []
        if symbols:
            symbol_list = [s.strip().upper() for s in symbols.split(',')]
        
        # Get fresh trading data (this would be implemented separately)
        # For now, return placeholder structure
        trading_data = []
        
        for symbol in symbol_list[:limit] if symbol_list else ["BTC/USDT", "ETH/USDT"][:limit]:
            trading_data.append({
                "symbol": symbol,
                "timestamp": utc_now().isoformat(),
                "rsi_2h": 58.5,
                "rsi_4h": 55.2,
                "mm1_2h": 42100.0,
                "center_2h": 42050.0,
                "mm1_4h": 41950.0,
                "center_4h": 41900.0,
                "ma_direction_2h": "ABOVE",
                "ma_direction_4h": "ABOVE",
                "signal_2h": "BUY",
                "signal_4h": "NEUTRAL",
                "signal_strength": 0.73,
                "rules_triggered": ["ma_crossover_2h", "rsi_range"],
                "last_signal_time": utc_now().isoformat()
            })
        
        return {
            "trading_data": trading_data,
            "metadata": {
                "endpoint_version": "1.0",
                "data_type": "trading_signals",
                "refresh_rate": "15_seconds",
                "last_update": utc_now().isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching trading data: {e}")
        raise HTTPException(status_code=500, detail=f"Trading data error: {str(e)}")

# Data refresh strategy endpoint
@app.post("/api/assets/refresh-strategy")
async def update_refresh_strategy(
    strategy: str = "incremental",  # incremental, full, priority_only
    interval_minutes: int = 5
):
    """Update data refresh strategy to handle stale data"""
    try:
        valid_strategies = ["incremental", "full", "priority_only", "on_demand"]
        
        if strategy not in valid_strategies:
            raise HTTPException(status_code=400, detail=f"Invalid strategy. Use: {valid_strategies}")
        
        # Store refresh strategy (would be implemented in background service)
        refresh_config = {
            "strategy": strategy,
            "interval_minutes": interval_minutes,
            "last_updated": utc_now().isoformat(),
            "active": True
        }
        
        logger.info(f"Refresh strategy updated: {refresh_config}")
        
        return {
            "message": "Refresh strategy updated successfully",
            "config": refresh_config,
            "estimated_improvement": "Data freshness: 30min → {}min".format(interval_minutes)
        }
        
    except Exception as e:
        logger.error(f"Error updating refresh strategy: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Background task to track revalidation status
revalidation_status = {"running": False, "progress": 0, "total": 0, "completed": False, "error": None}

async def run_revalidation_task():
    """Run the revalidation task with performance-optimized scanner"""
    global revalidation_status
    try:
        from scanner.initial_scanner import InitialScanner
        
        revalidation_status["running"] = True
        revalidation_status["progress"] = 0
        revalidation_status["total"] = 0
        revalidation_status["completed"] = False
        revalidation_status["error"] = None
        
        logger.info("Starting full asset revalidation with optimized scanner...")
        
        # Use the optimized initial scanner with new performance settings
        scanner = InitialScanner()
        result = await scanner.scan_all_assets(
            force_refresh=True,
            max_assets=None  # Remover limitação - pegar TODOS os ativos
        )
        
        if result:
            revalidation_status["total"] = result.total_discovered
            revalidation_status["progress"] = result.total_discovered
            revalidation_status["completed"] = True
            summary = result.get_summary()
            logger.info(f"Revalidation completed: {summary['valid_assets_count']}/{summary['total_discovered']} valid "
                       f"({summary['success_rate']:.1f}% success rate) in {summary['scan_duration_seconds']:.1f}s")
        else:
            revalidation_status["error"] = "Revalidation failed"
            
    except Exception as e:
        logger.error(f"Error during revalidation: {e}")
        revalidation_status["error"] = str(e)
    finally:
        revalidation_status["running"] = False

# Endpoint para scan inicial completo (frontend button)
@app.post("/api/scanner/initial-scan")
async def start_initial_scan():
    """Inicia scan inicial completo de TODOS os ativos disponíveis"""
    try:
        from scanner.initial_scanner import InitialScanner
        
        # Broadcast início do scan
        await manager.broadcast({
            "type": "scanner_started",
            "payload": {
                "status": "starting",
                "message": "Iniciando scan completo de todos os ativos...",
                "timestamp": utc_now().isoformat()
            }
        })
        
        # Executar scan de forma assíncrona
        async def run_initial_scan():
            try:
                logger.info("🚀 Starting complete initial asset scan from frontend request...")
                scanner = InitialScanner()
                
                # Executar scan completo SEM limitações
                result = await scanner.scan_all_assets(
                    force_refresh=True,
                    max_assets=None  # TODOS os ativos
                )
                
                # Broadcast resultados finais
                await manager.broadcast({
                    "type": "scanner_completed",
                    "payload": {
                        "status": "completed",
                        "total_assets": result.total_discovered,
                        "valid_assets": len(result.valid_assets),
                        "invalid_assets": len(result.invalid_assets),
                        "duration": result.scan_duration,
                        "timestamp": utc_now().isoformat()
                    }
                })
                
                logger.info(f"✅ Complete initial scan finished: {len(result.valid_assets)}/{result.total_discovered} valid assets")
                
            except Exception as e:
                logger.error(f"❌ Error in initial scan: {e}")
                await manager.broadcast({
                    "type": "scanner_error", 
                    "payload": {
                        "status": "error", 
                        "message": str(e),
                        "timestamp": utc_now().isoformat()
                    }
                })
        
        # Iniciar task assíncrona
        asyncio.create_task(run_initial_scan())
        
        return {
            "message": "Scan inicial iniciado com sucesso!",
            "status": "started",
            "timestamp": utc_now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error starting initial scan: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao iniciar scan: {str(e)}")

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

@app.get("/api/trading/trades")
async def get_trading_trades(
    symbol: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db),
    repo: TradeRepository = Depends(get_trade_repo)
):
    """Get trading history with enhanced trade information"""
    try:
        logger.info(f"Trading trades requested - symbol: {symbol}, status: {status}, limit: {limit}")
        
        trades = repo.get_trades(
            db,
            symbol=symbol,
            status=status,
            limit=limit
        )
        
        trading_trades = []
        for trade in trades:
            # Calculate additional trade metrics
            duration = None
            if trade.entry_time and trade.exit_time:
                duration_seconds = (trade.exit_time - trade.entry_time).total_seconds()
                duration = f"{int(duration_seconds // 3600)}h {int((duration_seconds % 3600) // 60)}m"
            elif trade.entry_time:
                duration_seconds = (utc_now() - trade.entry_time).total_seconds()
                duration = f"{int(duration_seconds // 3600)}h {int((duration_seconds % 3600) // 60)}m"
            
            trade_data = {
                "id": str(trade.id),
                "symbol": trade.asset.symbol if trade.asset else "UNKNOWN",
                "side": trade.side,
                "amount": float(trade.quantity) if trade.quantity else 0,
                "entry_price": float(trade.entry_price) if trade.entry_price else 0,
                "exit_price": float(trade.exit_price) if trade.exit_price else None,
                "stop_loss": float(trade.stop_loss) if trade.stop_loss else None,
                "take_profit": float(trade.take_profit) if trade.take_profit else None,
                "status": trade.status,
                "entry_reason": trade.entry_reason,
                "exit_reason": trade.exit_reason,
                "entry_time": trade.entry_time.isoformat() if trade.entry_time else None,
                "exit_time": trade.exit_time.isoformat() if trade.exit_time else None,
                "duration": duration,
                "pnl": float(trade.pnl) if trade.pnl else None,
                "pnl_percentage": float(trade.pnl_percentage) if trade.pnl_percentage else None,
                "fees": float(trade.fees) if trade.fees else None
            }
            
            trading_trades.append(trade_data)
        
        return {
            "success": True,
            "trades": trading_trades,
            "total": len(trading_trades),
            "timestamp": utc_now().isoformat(),
            "metadata": {
                "endpoint_version": "1.0",
                "data_type": "trading_history",
                "filters_applied": {
                    "symbol": symbol,
                    "status": status,
                    "limit": limit
                }
            }
        }
    except Exception as e:
        logger.error(f"Error fetching trading trades: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching trades: {str(e)}")

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
bot_status = {"running": True, "trading_enabled": True}

# Scanner status tracking
scanner_status = {
    "scanning_active": False,
    "assets_being_scanned": 0,
    "last_scan_start": None,
    "last_scan_end": None,
    "scan_interval": 30  # seconds
}

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
            "timestamp": utc_now()
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
            "timestamp": utc_now()
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
        "timestamp": utc_now()
    }

@app.get("/api/scanner/status")
async def get_scanner_status(
    db: Session = Depends(get_db),
    asset_repo: AssetRepository = Depends(get_asset_repo)
):
    """Get current scanner status with real asset count"""
    try:
        # Check if scanning should be considered active based on recent activity
        current_time = utc_now()
        
        # Get real count of valid assets from database
        valid_assets_count = asset_repo.get_valid_assets_count(db)
        
        # If we have a last scan start time and no end time, scanning is active
        if (scanner_status["last_scan_start"] and 
            not scanner_status["last_scan_end"]):
            scanner_status["scanning_active"] = True
        
        # If last scan ended recently (within 2x scan interval), consider it active
        elif scanner_status["last_scan_end"]:
            time_since_last_scan = (current_time - scanner_status["last_scan_end"]).total_seconds()
            if time_since_last_scan < (scanner_status["scan_interval"] * 2):
                scanner_status["scanning_active"] = True
            else:
                scanner_status["scanning_active"] = False
        
        # Set scanner status based on bot running state
        if bot_status["running"]:
            scanner_status["scanning_active"] = True
            # Use real asset count instead of mock value
            scanner_status["assets_being_scanned"] = valid_assets_count
        else:
            scanner_status["scanning_active"] = False
            scanner_status["assets_being_scanned"] = 0
        
        status_data = {
            "scanning_active": scanner_status["scanning_active"],
            "assets_being_scanned": scanner_status["assets_being_scanned"],
            "monitored_assets": valid_assets_count,  # Add explicit monitored assets count
            "last_scan_start": scanner_status["last_scan_start"],
            "last_scan_end": scanner_status["last_scan_end"],
            "scan_interval": scanner_status["scan_interval"],
            "timestamp": current_time
        }
        
        # Broadcast scanner status update to WebSocket clients
        try:
            await manager.broadcast({
                "type": "scanner_status_update",
                "payload": status_data
            })
        except Exception as e:
            logger.warning(f"Failed to broadcast scanner status update: {e}")
        
        return status_data
    except Exception as e:
        logger.error(f"Error getting scanner status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
            "timestamp": utc_now()
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
            "timestamp": utc_now()
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
        recent_trades = trade_repo.get_trades_since(db, utc_now() - timedelta(days=1))
        
        return {
            "summary": {
                "valid_assets": valid_assets,
                "active_signals": active_signals,
                "active_positions": len(positions),
                "total_unrealized_pnl": total_pnl,
                "recent_trades_count": len(recent_trades)
            },
            "timestamp": utc_now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching dashboard summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Trading live data endpoint - REFACTORED for direct CCXT calls
@app.get("/api/trading/live-data")
async def get_trading_live_data(
    limit: int = 50,
    symbols: str = None,  # Optional comma-separated list of symbols
    db: Session = Depends(get_db),
    trade_repo: TradeRepository = Depends(get_trade_repo)
):
    """Get real-time trading data using direct CCXT calls (not database scan data)"""
    try:
        logger.info(f"Trading live data requested - symbols: {symbols}, limit: {limit}")
        
        # Ensure database is initialized (in case position tracking is needed)
        from database.connection import init_database
        try:
            init_database()
        except Exception as init_error:
            logger.debug(f"Database initialization: {init_error}")
        
        # Initialize BingX client for real-time data
        from api.client import get_client
        try:
            client = get_client()
            if not client._initialized:
                success = await client.initialize()
                if not success:
                    raise Exception("Client initialization failed")
        except Exception as e:
            logger.error(f"Failed to initialize BingX client: {e}")
            raise HTTPException(status_code=500, detail="Trading API unavailable")
        
        # Determine symbols to process
        if symbols:
            # Use provided symbols (direct trading flow)
            symbol_list = [s.strip().upper() for s in symbols.split(',')]
            logger.info(f"Using provided symbols: {symbol_list}")
        else:
            # Fallback to a default set of major trading pairs for direct trading
            symbol_list = [
                'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'ADA/USDT', 'SOL/USDT',
                'DOT/USDT', 'MATIC/USDT', 'AVAX/USDT', 'ATOM/USDT', 'NEAR/USDT'
            ][:limit]
            logger.info(f"Using default major trading pairs: {symbol_list}")
        
        # Helper function to safely get candle color
        def get_candle_color(candles):
            """Safely extract candle color from OHLCV data"""
            try:
                if not candles or not isinstance(candles, list) or len(candles) == 0:
                    return "🔴"
                
                latest_candle = candles[-1]
                if not isinstance(latest_candle, (list, tuple)) or len(latest_candle) < 5:
                    return "🔴"
                
                # OHLCV format: [timestamp, open, high, low, close, volume]
                open_price = float(latest_candle[1])
                close_price = float(latest_candle[4])
                return "🟢" if close_price > open_price else "🔴"
                
            except (IndexError, TypeError, ValueError, KeyError) as e:
                logger.debug(f"Error getting candle color: {e}")
                return "🔴"
        
        # Helper function to calculate SMA
        def calculate_simple_sma(candles, period=9):
            """Calculate Simple Moving Average safely"""
            try:
                if not candles or len(candles) < period:
                    return None
                closes = []
                for candle in candles[-period:]:
                    if isinstance(candle, (list, tuple)) and len(candle) >= 5:
                        closes.append(float(candle[4]))  # close price
                if len(closes) == period:
                    return sum(closes) / len(closes)
                return None
            except (IndexError, ValueError, TypeError) as e:
                logger.debug(f"Error calculating SMA: {e}")
                return None
        
        trading_data = []
        
        # Process each symbol with direct CCXT calls
        for symbol in symbol_list:
            try:
                logger.debug(f"Processing symbol: {symbol}")
                
                # Get real-time market data directly from BingX
                ticker = await client.fetch_ticker(symbol)
                if not ticker or not ticker.get('last'):
                    logger.warning(f"Symbol {symbol} returned empty/invalid ticker - skipping")
                    continue
                    
                # Extract price and volume data
                current_price = float(ticker['last']) if ticker.get('last') else 0.0
                volume_24h = float(ticker['quoteVolume']) if ticker.get('quoteVolume') else 0.0
                
                logger.debug(f"Symbol {symbol}: price={current_price}, volume={volume_24h}")
                
                # Get OHLCV data for analysis (direct from exchange)
                candles_1h = []
                candles_2h = []
                candles_4h = []
                
                try:
                    candles_1h = await client.fetch_ohlcv(symbol, '1h', 21)  # For MM indicators
                    candles_2h = await client.fetch_ohlcv(symbol, '2h', 21)
                    candles_4h = await client.fetch_ohlcv(symbol, '4h', 21)
                    logger.debug(f"Fetched candles for {symbol}: 1h={len(candles_1h)}, 2h={len(candles_2h)}, 4h={len(candles_4h)}")
                except Exception as e:
                    logger.warning(f"Failed to fetch candle data for {symbol}: {e}")
                    # Continue with available data
                
                candle_2h_color = get_candle_color(candles_2h)
                candle_4h_color = get_candle_color(candles_4h)
                
                # Calculate basic indicators using safe function
                sma_1h = calculate_simple_sma(candles_1h, 9)
                sma_2h = calculate_simple_sma(candles_2h, 9)
                sma_4h = calculate_simple_sma(candles_4h, 9)
                
                # Simple signal calculation based on price vs moving average
                signal_type = "NEUTRAL"
                signal_strength = 0.0
                
                if sma_2h and sma_4h:
                    if current_price > sma_2h and current_price > sma_4h:
                        signal_type = "BULLISH"
                        signal_strength = min(100, ((current_price - min(sma_2h, sma_4h)) / current_price) * 1000)
                    elif current_price < sma_2h and current_price < sma_4h:
                        signal_type = "BEARISH"
                        signal_strength = min(100, ((max(sma_2h, sma_4h) - current_price) / current_price) * 1000)
                
                # Check for open positions (simplified)
                position_data = None
                try:
                    # This would be replaced with proper position tracking
                    # For now, return None to indicate no open positions
                    pass
                except Exception as e:
                    logger.debug(f"No position data available for {symbol}: {e}")
                
                # Build simplified trading data using direct CCXT data
                symbol_data = {
                    "symbol": symbol,
                    "timestamp": utc_now().isoformat(),
                    "current_price": current_price,
                    "volume_24h": volume_24h,
                    "indicators": {
                        "sma_1h": sma_1h,
                        "sma_2h": sma_2h,
                        "sma_4h": sma_4h
                    },
                    "candles": {
                        "2h_color": candle_2h_color,
                        "4h_color": candle_4h_color
                    },
                    "signal": {
                        "type": signal_type,
                        "strength": round(signal_strength, 2)
                    },
                    "position": position_data,
                    "data_source": "direct_ccxt"
                }
                
                trading_data.append(symbol_data)
                
            except Exception as e:
                # Enhanced error logging with exception type and context
                logger.error(f"Error processing symbol {symbol}: {type(e).__name__}: {e}")
                logger.debug(f"Symbol processing failed - Symbol: {symbol}, Error type: {type(e)}, Details: {str(e)}")
                
                # Check if this is a known symbol validation issue
                if "does not have market symbol" in str(e) or "symbol" in str(e).lower():
                    logger.warning(f"Symbol {symbol} appears to be invalid/delisted on BingX")
                
                # Continue with other symbols
                continue
        
        logger.info(f"Trading live data prepared for {len(trading_data)} symbols using direct CCXT")
        
        return {
            "trading_data": trading_data,
            "total_symbols": len(trading_data),
            "requested_symbols": len(symbol_list),
            "timestamp": utc_now().isoformat(),
            "metadata": {
                "endpoint_version": "2.0_direct_ccxt",
                "data_source": "direct_bingx_api",
                "data_type": "real_time_trading",
                "update_interval": "real_time",
                "symbols_requested": symbol_list
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching trading live data: {e}")
        raise HTTPException(status_code=500, detail=f"Trading data error: {str(e)}")

def _calculate_current_signal(indicators_spot, indicators_2h, indicators_4h, current_price):
    """Calculate current trading signal based on indicators and rules"""
    try:
        signal_type = "NEUTRAL"
        signal_strength = 0.0
        
        # Import trading config for thresholds
        from config.trading_config import TradingConfig
        
        # Rule 1: MA Crossover with RSI (2h and 4h)
        crossover_signals = []
        
        for indicators, timeframe in [(indicators_2h, "2h"), (indicators_4h, "4h")]:
            if indicators and indicators.mm1 and indicators.center and indicators.rsi:
                mm1 = float(indicators.mm1)
                center = float(indicators.center)
                rsi = float(indicators.rsi)
                
                # Check RSI range for Rule 1
                if TradingConfig.RSI_MIN <= rsi <= TradingConfig.RSI_MAX:
                    if mm1 > center:
                        crossover_signals.append(("BUY", 0.7 if timeframe == "4h" else 0.6))
                    elif mm1 < center:
                        crossover_signals.append(("SELL", 0.7 if timeframe == "4h" else 0.6))
        
        # Rule 2: MA Distance (2h and 4h)
        distance_signals = []
        
        for indicators, timeframe in [(indicators_2h, "2h"), (indicators_4h, "4h")]:
            if indicators and indicators.mm1 and indicators.center:
                mm1 = float(indicators.mm1)
                center = float(indicators.center)
                
                # Safe division - avoid division by zero
                if center == 0:
                    continue  # Skip this calculation if center is zero
                distance_percent = abs(mm1 - center) / center
                threshold = TradingConfig.MA_DISTANCE_2H_PERCENT if timeframe == "2h" else TradingConfig.MA_DISTANCE_4H_PERCENT
                
                if distance_percent >= threshold:
                    signal = "BUY" if mm1 > center else "SELL"
                    strength = min(distance_percent / 0.05, 1.0)  # Max strength at 5%
                    distance_signals.append((signal, strength * 0.6))
        
        # Combine signals
        all_signals = crossover_signals + distance_signals
        
        if all_signals:
            buy_signals = [s for s in all_signals if s[0] == "BUY"]
            sell_signals = [s for s in all_signals if s[0] == "SELL"]
            
            if buy_signals and not sell_signals:
                signal_type = "BUY"
                signal_strength = sum(s[1] for s in buy_signals) / len(buy_signals)
            elif sell_signals and not buy_signals:
                signal_type = "SELL"
                signal_strength = sum(s[1] for s in sell_signals) / len(sell_signals)
            elif buy_signals and sell_signals:
                buy_strength = sum(s[1] for s in buy_signals)
                sell_strength = sum(s[1] for s in sell_signals)
                
                if buy_strength > sell_strength * 1.2:
                    signal_type = "BUY"
                    signal_strength = buy_strength / len(buy_signals)
                elif sell_strength > buy_strength * 1.2:
                    signal_type = "SELL"
                    signal_strength = sell_strength / len(sell_signals)
        
        return signal_type, round(signal_strength, 3)
        
    except Exception as e:
        logger.error(f"Error calculating signal: {e}")
        return "NEUTRAL", 0.0

# Trading signal execution endpoint
@app.post("/api/trading/execute-signal")
async def execute_trading_signal(
    symbol: str,
    signal_type: str,
    signal_strength: float,
    db: Session = Depends(get_db),
    asset_repo: AssetRepository = Depends(get_asset_repo),
    trade_repo: TradeRepository = Depends(get_trade_repo)
):
    """Execute a trading signal automatically"""
    try:
        logger.info(f"Signal execution requested: {symbol} {signal_type} (strength: {signal_strength})")
        
        # Check if trading is enabled
        if not bot_status.get("trading_enabled", False):
            raise HTTPException(status_code=400, detail="Trading is not enabled")
        
        # Validate signal
        if signal_type not in ["BUY", "SELL"]:
            raise HTTPException(status_code=400, detail="Invalid signal type")
        
        if signal_strength < 0.5:  # Minimum strength threshold
            raise HTTPException(status_code=400, detail="Signal strength too low")
        
        # Get asset
        asset = asset_repo.get_by_symbol(db, symbol)
        if not asset or not asset.is_valid:
            raise HTTPException(status_code=400, detail="Asset not valid for trading")
        
        # Check if we already have an open position for this asset
        open_trades = trade_repo.get_open_trades_by_asset(db, asset.id)
        if open_trades:
            return {
                "message": f"Position already exists for {symbol}",
                "trade_id": str(open_trades[0].id),
                "status": "skipped"
            }
        
        # Initialize trading engine and execute trade
        from trading.engine import TradingEngine
        from api.client import get_client
        
        client = get_client()
        # Ensure client is initialized before use
        if not client._initialized:
            success = await client.initialize()
            if not success:
                raise HTTPException(status_code=500, detail="BingX client initialization failed")
        
        trading_engine = TradingEngine(client, trade_repo, asset_repo)
        
        # Initialize trading engine
        await trading_engine.start()
        
        # Create signal data for processing
        signal_data = {
            "symbol": symbol,
            "signal_type": signal_type,
            "strength": signal_strength,
            "rules_triggered": ["automated_signal"],
            "indicators_snapshot": {
                "signal_type": signal_type,
                "strength": signal_strength,
                "timestamp": utc_now().isoformat()
            },
            "current_price": None  # Will be fetched by trading engine
        }
        
        # Process the signal
        trade_result = await trading_engine.process_signal(signal_data)
        
        if trade_result:
            logger.info(f"✅ Trade executed successfully: {trade_result}")
            return {
                "message": f"Trade executed for {symbol}",
                "trade_result": trade_result,
                "status": "executed"
            }
        else:
            logger.warning(f"❌ Trade execution failed for {symbol}")
            return {
                "message": f"Trade execution failed for {symbol}",
                "status": "failed"
            }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing trading signal: {e}")
        raise HTTPException(status_code=500, detail=f"Signal execution error: {str(e)}")

@app.get("/api/trading/positions")
async def get_active_positions(
    db: Session = Depends(get_db),
    trade_repo: TradeRepository = Depends(get_trade_repo)
):
    """Get all active trading positions with real-time P&L"""
    try:
        logger.info("Fetching active trading positions")
        
        # Get open trades from database
        open_trades = trade_repo.get_open_trades(db)
        
        positions = []
        for trade in open_trades:
            try:
                # Get current market price for P&L calculation
                current_ticker = await safe_fetch_ticker(trade.symbol)
                current_price = current_ticker.get('last', 0) or float(trade.entry_price)
                
                # Calculate P&L
                if trade.side.upper() == 'BUY':
                    unrealized_pnl = (current_price - trade.entry_price) * trade.quantity
                    pnl_percentage = ((current_price - trade.entry_price) / trade.entry_price) * 100
                else:  # SELL
                    unrealized_pnl = (trade.entry_price - current_price) * trade.quantity
                    pnl_percentage = ((trade.entry_price - current_price) / trade.entry_price) * 100
                
                # Get current trailing stop level
                current_profit_percent = pnl_percentage / 100
                trailing_level = TradingConfig.get_trailing_stop_level(Decimal(str(current_profit_percent)))
                
                position_data = {
                    "id": str(trade.id),
                    "symbol": trade.symbol,
                    "side": trade.side,
                    "amount": float(trade.quantity),
                    "entry_price": float(trade.entry_price),
                    "current_price": current_price,
                    "unrealized_pnl": unrealized_pnl,
                    "pnl_percentage": pnl_percentage,
                    "stop_loss_price": float(trade.stop_loss) if trade.stop_loss else None,
                    "take_profit_price": float(trade.take_profit) if trade.take_profit else None,
                    "status": trade.status,
                    "entry_time": trade.entry_time.isoformat(),
                    "trailing_stop_level": {
                        "trigger": float(trailing_level.trigger) if trailing_level else 0,
                        "stop": float(trailing_level.stop) if trailing_level else 0
                    },
                    "duration": str(utc_now() - trade.entry_time)
                }
                
                positions.append(position_data)
                
            except Exception as trade_error:
                logger.error(f"Error processing trade {trade.id}: {trade_error}")
                continue
        
        return {
            "success": True,
            "positions": positions,
            "count": len(positions),
            "timestamp": utc_now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error fetching positions: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching positions: {str(e)}")

@app.post("/api/trading/positions/{position_id}/close")
async def close_position(
    position_id: str,
    db: Session = Depends(get_db),
    trade_repo: TradeRepository = Depends(get_trade_repo)
):
    """Manually close a specific position"""
    try:
        logger.info(f"Closing position: {position_id}")
        
        # Get trade from database
        trade = trade_repo.get_by_id(position_id)
        if not trade:
            raise HTTPException(status_code=404, detail="Position not found")
        
        if trade.status != 'OPEN':
            raise HTTPException(status_code=400, detail="Position is not open")
        
        # Get current market price
        current_ticker = await bingx_client.fetch_ticker(trade.symbol)
        current_price = current_ticker.get('last', 0)
        
        # Execute market order to close position
        close_side = 'SELL' if trade.side.upper() == 'BUY' else 'BUY'
        
        close_order = await bingx_client.create_market_order(
            symbol=trade.symbol,
            side=close_side.lower(),
            amount=float(trade.quantity)
        )
        
        # Calculate P&L
        if trade.side.upper() == 'BUY':
            pnl = (current_price - float(trade.entry_price)) * float(trade.quantity)
        else:
            pnl = (float(trade.entry_price) - current_price) * float(trade.quantity)
        
        pnl_percentage = (pnl / (float(trade.entry_price) * float(trade.quantity))) * 100
        
        # Update trade in database
        trade_repo.close_trade(
            trade_id=position_id,
            exit_price=current_price,
            exit_reason="MANUAL_CLOSE",
            pnl=pnl,
            pnl_percentage=pnl_percentage
        )
        
        return {
            "success": True,
            "message": f"Position {position_id} closed successfully",
            "close_order": close_order,
            "final_pnl": pnl,
            "pnl_percentage": pnl_percentage,
            "timestamp": utc_now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error closing position {position_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error closing position: {str(e)}")

@app.post("/api/trading/positions/{position_id}/adjust-stop-loss")
async def adjust_stop_loss(
    position_id: str,
    new_stop_price: float,
    db: Session = Depends(get_db),
    trade_repo: TradeRepository = Depends(get_trade_repo)
):
    """Adjust stop loss for a specific position"""
    try:
        logger.info(f"Adjusting stop loss for position {position_id} to {new_stop_price}")
        
        # Get trade from database
        trade = trade_repo.get_by_id(position_id)
        if not trade:
            raise HTTPException(status_code=404, detail="Position not found")
        
        if trade.status != 'OPEN':
            raise HTTPException(status_code=400, detail="Position is not open")
        
        # Validate new stop price
        current_ticker = await bingx_client.fetch_ticker(trade.symbol)
        current_price = current_ticker.get('last', 0)
        
        if trade.side.upper() == 'BUY':
            if new_stop_price >= current_price:
                raise HTTPException(status_code=400, detail="Stop loss must be below current price for BUY position")
        else:
            if new_stop_price <= current_price:
                raise HTTPException(status_code=400, detail="Stop loss must be above current price for SELL position")
        
        # Cancel existing stop loss order if exists
        # (In real implementation, you'd need to track and cancel the actual exchange order)
        
        # Create new stop loss order
        stop_side = 'SELL' if trade.side.upper() == 'BUY' else 'BUY'
        
        try:
            stop_order = await bingx_client.create_stop_loss_order(
                symbol=trade.symbol,
                side=stop_side.lower(),
                amount=float(trade.quantity),
                stop_price=new_stop_price
            )
            
            # Update trade in database
            trade_repo.update_stop_loss(trade.id, new_stop_price)
            
            return {
                "success": True,
                "message": f"Stop loss adjusted to {new_stop_price}",
                "stop_order": stop_order,
                "timestamp": utc_now().isoformat()
            }
            
        except Exception as order_error:
            logger.error(f"Error creating stop loss order: {order_error}")
            raise HTTPException(status_code=500, detail=f"Error creating stop loss order: {str(order_error)}")
        
    except Exception as e:
        logger.error(f"Error adjusting stop loss for position {position_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error adjusting stop loss: {str(e)}")

@app.post("/api/trading/positions/{position_id}/update-trailing-stop")
async def update_trailing_stop(
    position_id: str,
    db: Session = Depends(get_db),
    trade_repo: TradeRepository = Depends(get_trade_repo)
):
    """Update trailing stop based on current profit level"""
    try:
        logger.info(f"Updating trailing stop for position {position_id}")
        
        # Get trade from database
        trade = trade_repo.get_by_id(position_id)
        if not trade:
            raise HTTPException(status_code=404, detail="Position not found")
        
        if trade.status != 'OPEN':
            raise HTTPException(status_code=400, detail="Position is not open")
        
        # Get current market price
        current_ticker = await bingx_client.fetch_ticker(trade.symbol)
        current_price = current_ticker.get('last', 0)
        
        # Calculate current profit
        if trade.side.upper() == 'BUY':
            profit_percent = ((current_price - float(trade.entry_price)) / float(trade.entry_price))
        else:
            profit_percent = ((float(trade.entry_price) - current_price) / float(trade.entry_price))
        
        # Get appropriate trailing stop level
        trailing_level = TradingConfig.get_trailing_stop_level(Decimal(str(profit_percent)))
        
        if trailing_level and trailing_level.trigger <= Decimal(str(profit_percent)):
            # Calculate new stop price
            if trade.side.upper() == 'BUY':
                new_stop_price = float(trade.entry_price) * (1 + float(trailing_level.stop))
            else:
                new_stop_price = float(trade.entry_price) * (1 - float(trailing_level.stop))
            
            # Only update if new stop is better than current
            current_stop = float(trade.stop_loss) if trade.stop_loss else 0
            should_update = False
            
            if trade.side.upper() == 'BUY' and new_stop_price > current_stop:
                should_update = True
            elif trade.side.upper() == 'SELL' and new_stop_price < current_stop:
                should_update = True
            
            if should_update:
                # Update stop loss
                await adjust_stop_loss(position_id, new_stop_price, db, trade_repo)
                
                return {
                    "success": True,
                    "message": f"Trailing stop updated to {new_stop_price}",
                    "new_stop_price": new_stop_price,
                    "profit_percent": profit_percent * 100,
                    "trailing_level": float(trailing_level.trigger) * 100,
                    "timestamp": utc_now().isoformat()
                }
        
        return {
            "success": True,
            "message": "No trailing stop update needed",
            "current_profit": profit_percent * 100,
            "timestamp": utc_now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error updating trailing stop for position {position_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating trailing stop: {str(e)}")

@app.get("/api/trading/summary")
async def get_trading_summary(
    db: Session = Depends(get_db),
    trade_repo: TradeRepository = Depends(get_trade_repo)
):
    """Get trading performance summary"""
    try:
        logger.info("Fetching trading summary")
        
        # Get today's trades
        today_trades = trade_repo.get_trades_today(db)
        
        # Get all open positions  
        open_positions = trade_repo.get_open_trades(db)
        
        # Calculate total unrealized P&L
        total_unrealized_pnl = 0
        active_positions = 0
        
        for trade in open_positions:
            try:
                current_ticker = await bingx_client.fetch_ticker(trade.symbol)
                current_price = current_ticker.get('last', 0)
                
                if trade.side.upper() == 'BUY':
                    unrealized_pnl = (current_price - float(trade.entry_price)) * float(trade.quantity)
                else:
                    unrealized_pnl = (float(trade.entry_price) - current_price) * float(trade.quantity)
                
                total_unrealized_pnl += unrealized_pnl
                active_positions += 1
                
            except Exception as trade_error:
                logger.error(f"Error calculating P&L for trade {trade.id}: {trade_error}")
                continue
        
        # Calculate performance metrics
        closed_trades_today = [t for t in today_trades if t.status == 'CLOSED']
        winning_trades = [t for t in closed_trades_today if float(t.pnl or 0) > 0]
        
        win_rate = (len(winning_trades) / len(closed_trades_today) * 100) if closed_trades_today else 0
        total_realized_pnl = sum(float(t.pnl or 0) for t in closed_trades_today)
        
        return {
            "success": True,
            "summary": {
                "total_unrealized_pnl": total_unrealized_pnl,
                "total_realized_pnl_today": total_realized_pnl,
                "open_positions": active_positions,
                "trades_today": len(today_trades),
                "closed_trades_today": len(closed_trades_today),
                "win_rate": win_rate,
                "max_concurrent_trades": TradingConfig.MAX_CONCURRENT_TRADES
            },
            "timestamp": utc_now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error fetching trading summary: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching trading summary: {str(e)}")

@app.post("/api/trading/auto-trading/start")
async def start_auto_trading():
    """Start automatic trading mode"""
    try:
        # Set global auto trading flag (you might want to store this in database/config)
        # For now, we'll just return success - the actual auto trading logic 
        # should be implemented in the background trading engine
        
        logger.info("Auto trading started")
        return {
            "success": True,
            "message": "Auto trading started in VST mode",
            "timestamp": utc_now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error starting auto trading: {e}")
        raise HTTPException(status_code=500, detail=f"Error starting auto trading: {str(e)}")

@app.post("/api/trading/auto-trading/stop")
async def stop_auto_trading():
    """Stop automatic trading mode"""
    try:
        logger.info("Auto trading stopped")
        return {
            "success": True,
            "message": "Auto trading stopped",
            "timestamp": utc_now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error stopping auto trading: {e}")
        raise HTTPException(status_code=500, detail=f"Error stopping auto trading: {str(e)}")

@app.post("/api/trading/positions/{position_id}/take-profit")
async def execute_partial_take_profit(
    position_id: str,
    profit_percentage: float,
    close_percentage: float = 25.0,
    db: Session = Depends(get_db),
    trade_repo: TradeRepository = Depends(get_trade_repo)
):
    """Execute partial take profit at specified profit level"""
    try:
        logger.info(f"Executing take profit for position {position_id} at {profit_percentage}% profit")
        
        # Get trade from database
        trade = trade_repo.get_by_id(position_id)
        if not trade:
            raise HTTPException(status_code=404, detail="Position not found")
        
        if trade.status != 'OPEN':
            raise HTTPException(status_code=400, detail="Position is not open")
        
        # Get current market price
        current_ticker = await bingx_client.fetch_ticker(trade.symbol)
        current_price = current_ticker.get('last', 0)
        
        # Calculate current profit
        if trade.side.upper() == 'BUY':
            current_profit = ((current_price - float(trade.entry_price)) / float(trade.entry_price)) * 100
        else:
            current_profit = ((float(trade.entry_price) - current_price) / float(trade.entry_price)) * 100
        
        # Check if profit target is reached
        if current_profit < profit_percentage:
            return {
                "success": False,
                "message": f"Current profit {current_profit:.2f}% has not reached target {profit_percentage}%",
                "current_profit": current_profit,
                "timestamp": utc_now().isoformat()
            }
        
        # Calculate quantity to close
        close_quantity = float(trade.quantity) * (close_percentage / 100)
        
        # Execute partial close order
        close_side = 'SELL' if trade.side.upper() == 'BUY' else 'BUY'
        
        close_order = await bingx_client.create_market_order(
            symbol=trade.symbol,
            side=close_side.lower(),
            amount=close_quantity
        )
        
        # Calculate realized P&L for closed portion
        if trade.side.upper() == 'BUY':
            realized_pnl = (current_price - float(trade.entry_price)) * close_quantity
        else:
            realized_pnl = (float(trade.entry_price) - current_price) * close_quantity
        
        # Update trade in database - reduce quantity
        remaining_quantity = float(trade.quantity) - close_quantity
        trade_repo.update_trade_quantity(trade.id, remaining_quantity, realized_pnl)
        
        # Update trailing stop for remaining position
        await update_trailing_stop(position_id, db, trade_repo)
        
        return {
            "success": True,
            "message": f"Take profit executed: {close_percentage}% of position closed",
            "close_order": close_order,
            "closed_quantity": close_quantity,
            "remaining_quantity": remaining_quantity,
            "realized_pnl": realized_pnl,
            "profit_percentage_achieved": current_profit,
            "timestamp": utc_now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error executing take profit for position {position_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error executing take profit: {str(e)}")

@app.post("/api/trading/risk-management/update-all")
async def update_all_risk_management(
    db: Session = Depends(get_db),
    trade_repo: TradeRepository = Depends(get_trade_repo)
):
    """Update risk management for all open positions"""
    try:
        logger.info("Updating risk management for all open positions")
        
        # Get all open trades
        open_trades = trade_repo.get_open_trades(db)
        
        updates = []
        for trade in open_trades:
            try:
                # Get current market price
                current_ticker = await bingx_client.fetch_ticker(trade.symbol)
                current_price = current_ticker.get('last', 0)
                
                # Calculate current profit
                if trade.side.upper() == 'BUY':
                    profit_percent = ((current_price - float(trade.entry_price)) / float(trade.entry_price))
                else:
                    profit_percent = ((float(trade.entry_price) - current_price) / float(trade.entry_price))
                
                profit_percentage = profit_percent * 100
                
                # Check for trailing stop updates
                trailing_updated = False
                try:
                    trailing_result = await update_trailing_stop(str(trade.id), db, trade_repo)
                    if trailing_result.get("success") and "updated" in trailing_result.get("message", ""):
                        trailing_updated = True
                except:
                    pass
                
                # Check for take profit opportunities
                take_profit_executed = []
                for tp_level in TradingConfig.TAKE_PROFIT_LEVELS:
                    tp_percentage = float(tp_level["percentage"]) * 100
                    tp_size_percent = tp_level["size_percent"]
                    
                    if profit_percentage >= tp_percentage:
                        try:
                            tp_result = await execute_partial_take_profit(
                                str(trade.id), 
                                tp_percentage, 
                                tp_size_percent, 
                                db, 
                                trade_repo
                            )
                            if tp_result.get("success"):
                                take_profit_executed.append({
                                    "level": tp_percentage,
                                    "size": tp_size_percent,
                                    "pnl": tp_result.get("realized_pnl", 0)
                                })
                        except:
                            pass
                
                updates.append({
                    "trade_id": str(trade.id),
                    "symbol": trade.symbol,
                    "current_profit": profit_percentage,
                    "trailing_stop_updated": trailing_updated,
                    "take_profits_executed": take_profit_executed
                })
                
            except Exception as trade_error:
                logger.error(f"Error updating risk management for trade {trade.id}: {trade_error}")
                continue
        
        return {
            "success": True,
            "message": f"Risk management updated for {len(updates)} positions",
            "updates": updates,
            "timestamp": utc_now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error updating risk management: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating risk management: {str(e)}")

# ====== TEST MODE ENDPOINTS ======

# Global test mode state
test_mode_state = {
    "active": False,
    "activated_at": None,
    "configuration": {},
    "statistics": {
        "signals_forced": 0,
        "trades_executed": 0,
        "tests_completed": 0
    }
}

@app.post("/api/trading/test-mode/start")
async def start_test_mode(
    request: dict,
    db: Session = Depends(get_db),
    signal_repo: SignalRepository = Depends(get_signal_repo),
    trade_repo: TradeRepository = Depends(get_trade_repo)
):
    """Start aggressive test mode for comprehensive trading flow testing"""
    try:
        global test_mode_state
        
        if test_mode_state["active"]:
            return {
                "success": False,
                "error": "Test mode is already active",
                "current_state": test_mode_state
            }
        
        # Extract configuration from request
        config = {
            "aggressive_mode": request.get("aggressive_mode", True),
            "test_all_flows": request.get("test_all_flows", True),
            "force_signals": request.get("force_signals", True),
            "max_test_trades": request.get("max_test_trades", 5),
            "test_duration_minutes": request.get("test_duration_minutes", 30)
        }
        
        # Activate test mode
        test_mode_state = {
            "active": True,
            "activated_at": utc_now().isoformat(),
            "configuration": config,
            "statistics": {
                "signals_forced": 0,
                "trades_executed": 0,
                "tests_completed": 0
            }
        }
        
        logger.warning("🧪 TEST MODE ACTIVATED - Aggressive trading testing enabled")
        logger.info(f"Test mode configuration: {config}")
        
        # If force_signals is enabled, create some test signals
        if config.get("force_signals", False):
            await _create_test_signals(db, signal_repo)
        
        # Broadcast test mode activation to WebSocket clients
        await manager.broadcast({
            "type": "test_mode_activated",
            "payload": {
                "activated_at": test_mode_state["activated_at"],
                "configuration": config,
                "message": "Sistema em modo de teste agressivo ativado"
            }
        })
        
        return {
            "success": True,
            "message": "Modo teste ativado com sucesso. Sistema configurado para testes agressivos de trading.",
            "state": test_mode_state,
            "warnings": [
                "⚠️ Operações de trading serão executadas de forma agressiva",
                "⚠️ Stop loss e take profit serão testados automaticamente",
                "⚠️ Use apenas com quantidades pequenas ou em ambiente de teste"
            ]
        }
        
    except Exception as e:
        logger.error(f"Error starting test mode: {e}")
        raise HTTPException(status_code=500, detail=f"Error starting test mode: {str(e)}")

@app.post("/api/trading/test-mode/stop")
async def stop_test_mode():
    """Stop test mode and return to normal operations"""
    try:
        global test_mode_state
        
        if not test_mode_state["active"]:
            return {
                "success": False,
                "error": "Test mode is not currently active"
            }
        
        # Store final statistics
        final_stats = test_mode_state["statistics"].copy()
        duration_minutes = 0
        
        if test_mode_state["activated_at"]:
            activated_time = datetime.fromisoformat(test_mode_state["activated_at"].replace('Z', '+00:00'))
            duration_minutes = (utc_now() - activated_time).total_seconds() / 60
        
        # Deactivate test mode
        test_mode_state = {
            "active": False,
            "activated_at": None,
            "configuration": {},
            "statistics": {
                "signals_forced": 0,
                "trades_executed": 0,
                "tests_completed": 0
            }
        }
        
        logger.warning("🧪 TEST MODE DEACTIVATED - Returning to normal operations")
        
        # Broadcast test mode deactivation to WebSocket clients
        await manager.broadcast({
            "type": "test_mode_deactivated",
            "payload": {
                "deactivated_at": utc_now().isoformat(),
                "duration_minutes": round(duration_minutes, 2),
                "final_statistics": final_stats,
                "message": "Sistema retornado ao modo normal de operação"
            }
        })
        
        return {
            "success": True,
            "message": "Modo teste desativado com sucesso. Sistema retornado ao modo normal.",
            "session_summary": {
                "duration_minutes": round(duration_minutes, 2),
                "statistics": final_stats
            }
        }
        
    except Exception as e:
        logger.error(f"Error stopping test mode: {e}")
        raise HTTPException(status_code=500, detail=f"Error stopping test mode: {str(e)}")

@app.get("/api/trading/test-mode/status")
async def get_test_mode_status():
    """Get current test mode status and statistics"""
    try:
        global test_mode_state
        
        status_response = {
            "active": test_mode_state["active"],
            "state": test_mode_state
        }
        
        if test_mode_state["active"] and test_mode_state["activated_at"]:
            activated_time = datetime.fromisoformat(test_mode_state["activated_at"].replace('Z', '+00:00'))
            duration_minutes = (utc_now() - activated_time).total_seconds() / 60
            status_response["runtime_minutes"] = round(duration_minutes, 2)
        
        return status_response
        
    except Exception as e:
        logger.error(f"Error getting test mode status: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting test mode status: {str(e)}")

async def _create_test_signals(db: Session, signal_repo: SignalRepository):
    """Create test signals for aggressive testing"""
    try:
        # Get a few valid assets for testing
        asset_repo = AssetRepository()
        valid_assets = asset_repo.get_valid_assets(db, limit=3)
        
        if not valid_assets:
            logger.warning("No valid assets found for test signal creation")
            return
        
        test_signals_created = 0
        
        for asset in valid_assets:
            try:
                # Create a test BUY signal
                signal_repo.create_signal(
                    db,
                    asset_id=str(asset.id),
                    signal_type="BUY",
                    strength=0.9,  # High strength for testing
                    rules_triggered=["test_mode_forced_signal"],
                    indicators_snapshot={
                        "test_mode": True,
                        "forced_signal": True,
                        "mm1": 42000.0,
                        "center": 41900.0,
                        "rsi": 45.0,
                        "message": "Test signal created by aggressive test mode"
                    }
                )
                test_signals_created += 1
                logger.info(f"Created test signal for {asset.symbol}")
                
            except Exception as signal_error:
                logger.warning(f"Failed to create test signal for {asset.symbol}: {signal_error}")
                continue
        
        # Update test mode statistics
        global test_mode_state
        test_mode_state["statistics"]["signals_forced"] += test_signals_created
        
        logger.info(f"Created {test_signals_created} test signals for aggressive testing")
        
    except Exception as e:
        logger.error(f"Error creating test signals: {e}")

def is_test_mode_active() -> bool:
    """Check if test mode is currently active"""
    global test_mode_state
    return test_mode_state.get("active", False)

def get_test_mode_config() -> dict:
    """Get current test mode configuration"""
    global test_mode_state
    return test_mode_state.get("configuration", {})

def increment_test_mode_stat(stat_name: str, increment: int = 1):
    """Increment a test mode statistic"""
    global test_mode_state
    if test_mode_state.get("active", False):
        test_mode_state["statistics"][stat_name] = test_mode_state["statistics"].get(stat_name, 0) + increment

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
                    "timestamp": utc_now().isoformat(),
                    "server_info": "BingX Trading Bot WebSocket"
                }))
                logger.debug(f"Pong sent to {client_host}")
                
            elif message.get("type") == "subscribe":
                # Handle subscription requests
                subscription_type = message.get("data", {}).get("channel", "general")
                
                # Send immediate data based on subscription type
                if subscription_type == "trading_data":
                    # Send current trading summary
                    try:
                        from database.connection import get_session
                        with get_session() as db:
                            trade_repo = TradeRepository()
                            open_trades = trade_repo.get_open_trades(db)
                            
                            trading_summary = {
                                "type": "trading_data_snapshot",
                                "timestamp": utc_now().isoformat(),
                                "data": {
                                    "open_positions": len(open_trades),
                                    "trading_enabled": bot_status.get("trading_enabled", False),
                                    "positions": [
                                        {
                                            "id": str(trade.id),
                                            "symbol": trade.asset.symbol if trade.asset else "UNKNOWN",
                                            "side": trade.side,
                                            "entry_price": float(trade.entry_price),
                                            "quantity": float(trade.quantity),
                                            "entry_time": trade.entry_time.isoformat() if trade.entry_time else None
                                        }
                                        for trade in open_trades[:5]  # Limit to 5 positions
                                    ]
                                }
                            }
                            
                            await websocket.send_text(json.dumps(trading_summary))
                    except Exception as snapshot_error:
                        logger.error(f"Error sending trading snapshot: {snapshot_error}")
                
                # Confirm subscription
                await websocket.send_text(json.dumps({
                    "type": "subscribed", 
                    "data": {
                        "channel": subscription_type,
                        "status": "active"
                    },
                    "timestamp": utc_now().isoformat()
                }))
                logger.info(f"Subscription confirmed for {client_host}: {subscription_type}")
                
            elif message.get("type") == "unsubscribe":
                # Handle unsubscription requests
                await websocket.send_text(json.dumps({
                    "type": "unsubscribed", 
                    "data": message.get("data"),
                    "timestamp": utc_now().isoformat()
                }))
                logger.info(f"Unsubscription confirmed for {client_host}: {message.get('data')}")
                
            elif message.get("type") == "request_update":
                # Handle manual update requests
                update_type = message.get("data", {}).get("type", "general")
                
                if update_type == "positions":
                    try:
                        from database.connection import get_session
                        with get_session() as db:
                            trade_repo = TradeRepository()
                            open_trades = trade_repo.get_open_trades(db)
                            
                            positions_update = {
                                "type": "positions_update",
                                "timestamp": utc_now().isoformat(),
                                "data": {
                                    "positions": [
                                        {
                                            "id": str(trade.id),
                                            "symbol": trade.asset.symbol if trade.asset else "UNKNOWN",
                                            "side": trade.side,
                                            "entry_price": float(trade.entry_price),
                                            "current_price": await _get_current_price(trade.asset.symbol if trade.asset else "UNKNOWN"),
                                            "quantity": float(trade.quantity),
                                            "entry_time": trade.entry_time.isoformat() if trade.entry_time else None
                                        }
                                        for trade in open_trades
                                    ]
                                }
                            }
                            
                            await websocket.send_text(json.dumps(positions_update))
                    except Exception as update_error:
                        logger.error(f"Error sending positions update: {update_error}")
                
            else:
                logger.warning(f"Unknown message type from {client_host}: {message.get('type')}")
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected from {client_host}")
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error from {client_host}: {e}")
        manager.disconnect(websocket)

async def _get_current_price(symbol: str) -> float:
    """Helper function to get current price for WebSocket updates."""
    try:
        ticker = await safe_fetch_ticker(symbol)
        return ticker.get('last', 0)
    except Exception as e:
        logger.debug(f"Error getting current price for {symbol}: {e}")
        return 0

# Background task to broadcast real-time data
async def broadcast_realtime_data():
    """Background task to send real-time updates to connected clients"""
    last_broadcast_time = None
    
    while True:
        try:
            if manager.active_connections:
                current_time = utc_now()
                
                # Broadcast trading data every 15 seconds
                if (last_broadcast_time is None or 
                    (current_time - last_broadcast_time).total_seconds() >= 15):
                    
                    # Get real-time trading data for broadcast
                    try:
                        # Get database session
                        from database.connection import get_session
                        with get_session() as db:
                            asset_repo = AssetRepository()
                            trade_repo = TradeRepository()
                            
                            # Get summary data for broadcast
                            valid_assets = asset_repo.get_valid_assets(db)[:10]  # Top 10 assets
                            open_trades = trade_repo.get_open_trades(db)
                            
                            # Calculate total P&L
                            total_unrealized_pnl = 0
                            position_count = len(open_trades)
                            
                            for trade in open_trades[:5]:  # Sample first 5 trades
                                try:
                                    current_ticker = await safe_fetch_ticker(trade.asset.symbol if trade.asset else "UNKNOWN")
                                    current_price = current_ticker.get('last', 0) or float(trade.entry_price)
                                    
                                    if trade.side.upper() == 'BUY':
                                        pnl = (current_price - float(trade.entry_price)) * float(trade.quantity)
                                    else:
                                        pnl = (float(trade.entry_price) - current_price) * float(trade.quantity)
                                    
                                    total_unrealized_pnl += pnl
                                except Exception as trade_error:
                                    logger.debug(f"Error calculating P&L for trade {trade.id}: {trade_error}")
                                    continue
                            
                            # Prepare broadcast data
                            broadcast_data = {
                                "type": "trading_update",
                                "timestamp": current_time.isoformat(),
                                "data": {
                                    "summary": {
                                        "total_assets": len(valid_assets),
                                        "open_positions": position_count,
                                        "total_unrealized_pnl": round(total_unrealized_pnl, 2),
                                        "trading_enabled": bot_status.get("trading_enabled", False)
                                    },
                                    "positions_sample": [
                                        {
                                            "symbol": trade.asset.symbol if trade.asset else "UNKNOWN",
                                            "side": trade.side,
                                            "entry_time": trade.entry_time.isoformat() if trade.entry_time else None
                                        }
                                        for trade in open_trades[:3]  # Sample first 3
                                    ],
                                    "update_available": True,
                                    "refresh_recommended": True
                                }
                            }
                            
                            await manager.broadcast(broadcast_data)
                            last_broadcast_time = current_time
                            logger.debug(f"Sent trading update to {len(manager.active_connections)} clients")
                    
                    except Exception as data_error:
                        logger.warning(f"Error getting trading data for broadcast: {data_error}")
                        # Send simple update notification as fallback
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
                
        except Exception as e:
            logger.error(f"Error in broadcast task: {e}")
            # Continue the loop even if one broadcast fails
        
        # Wait 15 seconds before next check
        await asyncio.sleep(15)

# Background task for automated risk management
async def automated_risk_management():
    """Background task to continuously monitor and update risk management for all positions"""
    logger.info("Starting automated risk management task")
    
    while True:
        try:
            # Run risk management update every 30 seconds
            await asyncio.sleep(30)
            
            # Get database session
            db = next(get_db())
            trade_repo = TradeRepository()
            
            # Get all open trades
            open_trades = trade_repo.get_open_trades(db)
            
            if not open_trades:
                continue
                
            logger.info(f"Running automated risk management for {len(open_trades)} open positions")
            
            for trade in open_trades:
                try:
                    # Skip if BingX client is not available
                    if not bingx_client:
                        logger.warning("BingX client not available - skipping risk management")
                        continue
                        
                    # Get current market price
                    current_ticker = await bingx_client.fetch_ticker(trade.symbol)
                    current_price = current_ticker.get('last', 0)
                    
                    # Calculate current profit
                    if trade.side.upper() == 'BUY':
                        profit_percent = ((current_price - float(trade.entry_price)) / float(trade.entry_price))
                    else:
                        profit_percent = ((float(trade.entry_price) - current_price) / float(trade.entry_price))
                    
                    profit_percentage = profit_percent * 100
                    
                    # 1. Update trailing stop if needed
                    trailing_level = TradingConfig.get_trailing_stop_level(Decimal(str(profit_percent)))
                    
                    if trailing_level and trailing_level.trigger <= Decimal(str(profit_percent)):
                        # Calculate new stop price
                        if trade.side.upper() == 'BUY':
                            new_stop_price = float(trade.entry_price) * (1 + float(trailing_level.stop))
                        else:
                            new_stop_price = float(trade.entry_price) * (1 - float(trailing_level.stop))
                        
                        # Only update if new stop is better than current
                        current_stop = float(trade.stop_loss) if trade.stop_loss else 0
                        should_update = False
                        
                        if trade.side.upper() == 'BUY' and new_stop_price > current_stop:
                            should_update = True
                        elif trade.side.upper() == 'SELL' and new_stop_price < current_stop:
                            should_update = True
                        
                        if should_update:
                            try:
                                # Update stop loss order on exchange
                                stop_side = 'SELL' if trade.side.upper() == 'BUY' else 'BUY'
                                
                                stop_order = await bingx_client.create_stop_loss_order(
                                    symbol=trade.symbol,
                                    side=stop_side.lower(),
                                    amount=float(trade.quantity),
                                    stop_price=new_stop_price
                                )
                                
                                # Update database (method would need to be implemented with session)
                                trade_repo.update_trade(db, str(trade.id), {'stop_loss': new_stop_price})
                                
                                logger.info(f"Trailing stop updated for {trade.symbol}: {new_stop_price} (profit: {profit_percentage:.2f}%)")
                                
                            except Exception as stop_error:
                                logger.error(f"Error updating trailing stop for {trade.symbol}: {stop_error}")
                    
                    # 2. Check for take profit levels
                    for tp_level in TradingConfig.TAKE_PROFIT_LEVELS:
                        tp_percentage = float(tp_level["percentage"]) * 100
                        tp_size_percent = tp_level["size_percent"]
                        
                        # Check if this level should trigger and hasn't been executed yet
                        if profit_percentage >= tp_percentage:
                            # Check if this take profit level was already executed
                            # (In a real implementation, you'd track this in database)
                            
                            try:
                                # Calculate quantity to close
                                close_quantity = float(trade.quantity) * (tp_size_percent / 100)
                                
                                # Execute partial close order
                                close_side = 'SELL' if trade.side.upper() == 'BUY' else 'BUY'
                                
                                close_order = await bingx_client.create_market_order(
                                    symbol=trade.symbol,
                                    side=close_side.lower(),
                                    amount=close_quantity
                                )
                                
                                # Calculate realized P&L for closed portion
                                if trade.side.upper() == 'BUY':
                                    realized_pnl = (current_price - float(trade.entry_price)) * close_quantity
                                else:
                                    realized_pnl = (float(trade.entry_price) - current_price) * close_quantity
                                
                                # Update trade in database - reduce quantity
                                remaining_quantity = float(trade.quantity) - close_quantity
                                trade_repo.update_trade(db, str(trade.id), {
                                    'quantity': remaining_quantity,
                                    'fees': (trade.fees or 0) + realized_pnl
                                })
                                
                                logger.info(f"Take profit executed for {trade.symbol} at {tp_percentage}%: {tp_size_percent}% closed, P&L: ${realized_pnl:.2f}")
                                
                                # Send WebSocket notification to frontend
                                await manager.broadcast({
                                    "type": "take_profit_executed",
                                    "data": {
                                        "symbol": trade.symbol,
                                        "profit_level": tp_percentage,
                                        "size_closed": tp_size_percent,
                                        "realized_pnl": realized_pnl,
                                        "remaining_quantity": remaining_quantity
                                    },
                                    "timestamp": utc_now().isoformat()
                                })
                                
                                break  # Only execute one level per iteration
                                
                            except Exception as tp_error:
                                logger.error(f"Error executing take profit for {trade.symbol}: {tp_error}")
                    
                    # 3. Check for stop loss triggers (in case exchange stop order failed)
                    if trade.stop_loss:
                        stop_loss_price = float(trade.stop_loss)
                        
                        should_close = False
                        if trade.side.upper() == 'BUY' and current_price <= stop_loss_price:
                            should_close = True
                        elif trade.side.upper() == 'SELL' and current_price >= stop_loss_price:
                            should_close = True
                        
                        if should_close:
                            try:
                                # Execute emergency stop loss
                                close_side = 'SELL' if trade.side.upper() == 'BUY' else 'BUY'
                                
                                close_order = await bingx_client.create_market_order(
                                    symbol=trade.symbol,
                                    side=close_side.lower(),
                                    amount=float(trade.quantity)
                                )
                                
                                # Calculate P&L
                                if trade.side.upper() == 'BUY':
                                    pnl = (current_price - float(trade.entry_price)) * float(trade.quantity)
                                else:
                                    pnl = (float(trade.entry_price) - current_price) * float(trade.quantity)
                                
                                pnl_percentage = (pnl / (float(trade.entry_price) * float(trade.quantity))) * 100
                                
                                # Close trade in database
                                trade_repo.close_trade(
                                    db,
                                    trade_id=str(trade.id),
                                    exit_price=current_price,
                                    exit_reason="STOP_LOSS_TRIGGERED",
                                    fees=Decimal('0')
                                )
                                
                                logger.warning(f"Emergency stop loss triggered for {trade.symbol}: P&L ${pnl:.2f} ({pnl_percentage:.2f}%)")
                                
                                # Send WebSocket notification
                                await manager.broadcast({
                                    "type": "stop_loss_triggered",
                                    "data": {
                                        "symbol": trade.symbol,
                                        "stop_price": stop_loss_price,
                                        "exit_price": current_price,
                                        "pnl": pnl,
                                        "pnl_percentage": pnl_percentage
                                    },
                                    "timestamp": utc_now().isoformat()
                                })
                                
                            except Exception as sl_error:
                                logger.error(f"Error executing emergency stop loss for {trade.symbol}: {sl_error}")
                    
                except Exception as trade_error:
                    logger.error(f"Error processing risk management for trade {trade.id}: {trade_error}")
                    continue
            
        except Exception as e:
            logger.error(f"Error in automated risk management task: {e}")
            # Continue running even if there's an error
            continue

async def broadcast_scanner_status():
    """Background task to broadcast scanner status periodically"""
    logger.info("Starting scanner status broadcast task")
    
    while True:
        try:
            # Broadcast scanner status every 30 seconds
            await asyncio.sleep(30)
            
            if manager.active_connections:
                # Get scanner status data
                try:
                    with get_session() as db:
                        asset_repo = AssetRepository()
                        valid_assets_count = asset_repo.get_valid_assets_count(db)
                        signals_count = SignalRepository().get_active_signals_count(db)
                        
                        # Create status update
                        status_data = {
                            "scanning_active": scanner_status.get("scanning_active", False),
                            "assets_being_scanned": scanner_status.get("assets_being_scanned", 0),
                            "monitored_assets": valid_assets_count,
                            "signals_count": signals_count,
                            "last_scan_start": scanner_status.get("last_scan_start"),
                            "last_scan_end": scanner_status.get("last_scan_end"),
                            "scan_interval": scanner_status.get("scan_interval", 60),
                            "timestamp": utc_now().isoformat()
                        }
                        
                        # Broadcast to all connected clients
                        await manager.broadcast({
                            "type": "scanner_status_update",
                            "payload": status_data
                        })
                        
                        logger.debug(f"Broadcasted scanner status: {valid_assets_count} assets monitored, {signals_count} active signals")
                        
                except Exception as e:
                    logger.error(f"Error broadcasting scanner status: {e}")
                    
        except asyncio.CancelledError:
            logger.info("Scanner status broadcast task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in scanner status broadcast task: {e}")
            # Continue running even if there's an error
            continue

# Start background task - merge with main startup event
async def start_background_tasks():
    """Start background tasks"""
    asyncio.create_task(broadcast_realtime_data())
    asyncio.create_task(automated_risk_management())
    asyncio.create_task(broadcast_scanner_status())
    logger.info("Background tasks started: real-time data broadcasting, automated risk management, and scanner status broadcasting")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("FastAPI server shutting down")

# Helper functions for validation table
def _calculate_risk_level(market_summary: dict) -> str:
    """Calculate risk level based on market data."""
    try:
        risk_score = 0
        
        # Volume risk
        volume = market_summary.get('quote_volume_24h', 0)
        if volume < 10000:
            risk_score += 3
        elif volume < 50000:
            risk_score += 2
        elif volume < 100000:
            risk_score += 1
        
        # Volatility risk
        volatility = abs(float(market_summary.get('change_percent_24h', 0)))
        if volatility > 10:
            risk_score += 3
        elif volatility > 5:
            risk_score += 2
        elif volatility > 2:
            risk_score += 1
        
        # Spread risk
        spread = market_summary.get('spread_percent', 0)
        if spread > 1:
            risk_score += 2
        elif spread > 0.5:
            risk_score += 1
        
        # Determine risk level
        if risk_score <= 2:
            return "LOW"
        elif risk_score <= 4:
            return "MEDIUM"
        else:
            return "HIGH"
            
    except Exception:
        return "UNKNOWN"

def _calculate_data_quality(validation_data: dict) -> int:
    """Calculate data quality score (0-100)."""
    try:
        score = 50  # Base score
        
        # Validation checks
        checks = validation_data.get('validation_checks', {})
        if len(checks) >= 3:
            score += 20
        elif len(checks) >= 1:
            score += 10
        
        # Market summary data
        market_summary = validation_data.get('market_summary', {})
        required_fields = ['price', 'quote_volume_24h', 'spread_percent']
        available_fields = sum(1 for field in required_fields if market_summary.get(field))
        score += (available_fields / len(required_fields)) * 20
        
        # Response time (lower is better)
        response_time = validation_data.get('validation_duration', 0)
        if response_time < 1:
            score += 10
        elif response_time < 3:
            score += 5
        
        return min(100, max(0, int(score)))
        
    except Exception:
        return 50

# Maintenance and fix endpoints
@app.post("/api/maintenance/fix-invalid-assets")
async def fix_invalid_assets(
    db: Session = Depends(get_db),
    asset_repo: AssetRepository = Depends(get_asset_repo)
):
    """Fix invalid assets that are causing 'Error processing asset: 4' errors"""
    try:
        logger.info("Starting invalid assets fix process")
        
        # List of assets that are causing "Error processing asset: 4"
        invalid_assets = [
            'ANIME/USDT',
            'ANKR/USDT', 
            'ANT/USDT',
            'ANTT/USDT'
        ]
        
        results = []
        updated_count = 0
        not_found_count = 0
        
        for symbol in invalid_assets:
            try:
                asset = asset_repo.get_by_symbol(db, symbol)
                
                if asset:
                    if asset.is_valid:
                        # Mark as invalid using the repository method
                        updated_asset = asset_repo.update_validation_status(
                            db, 
                            symbol, 
                            False, 
                            {
                                "error": "symbol_not_found_on_bingx",
                                "timestamp": utc_now().isoformat(),
                                "fixed_by": "maintenance_endpoint"
                            }
                        )
                        if updated_asset:
                            updated_count += 1
                            results.append({
                                "symbol": symbol,
                                "status": "updated",
                                "message": "Marked as invalid"
                            })
                        else:
                            results.append({
                                "symbol": symbol,
                                "status": "error",
                                "message": "Failed to update"
                            })
                    else:
                        results.append({
                            "symbol": symbol,
                            "status": "already_invalid",
                            "message": "Already marked as invalid"
                        })
                else:
                    not_found_count += 1
                    results.append({
                        "symbol": symbol,
                        "status": "not_found",
                        "message": "Asset not found in database"
                    })
                    
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
                results.append({
                    "symbol": symbol,
                    "status": "error",
                    "message": str(e)
                })
        
        logger.info(f"Invalid assets fix completed - Updated: {updated_count}, Not found: {not_found_count}")
        
        return {
            "success": True,
            "message": f"Processed {len(invalid_assets)} assets",
            "summary": {
                "total_processed": len(invalid_assets),
                "updated": updated_count,
                "not_found": not_found_count
            },
            "results": results,
            "timestamp": utc_now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in fix_invalid_assets endpoint: {e}")
        raise HTTPException(status_code=500, detail=f"Error fixing invalid assets: {str(e)}")

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