#!/usr/bin/env python3
"""
Test script para investigar problema de contagem inconsistente no WebSocket
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from database.connection import init_database, create_tables, get_session
from database.repository import AssetRepository, IndicatorRepository, SignalRepository, TradeRepository
from utils.logger import get_logger

logger = get_logger(__name__)


def test_repository_queries():
    """Test the same queries used in broadcast_realtime_data()"""
    logger.info("🔍 Testing repository queries used in WebSocket broadcast...")
    
    try:
        # Initialize database
        if not init_database():
            logger.error("❌ Failed to initialize database")
            return False
        
        if not create_tables():
            logger.error("❌ Failed to create tables")
            return False
        
        # Test asset repository queries
        asset_repo = AssetRepository()
        indicator_repo = IndicatorRepository()
        signal_repo = SignalRepository()
        position_repo = TradeRepository()
        
        with get_session() as session:
            logger.info("📊 TESTING ASSET QUERIES:")
            
            # Test 1: get_valid_assets method
            valid_assets_method = asset_repo.get_valid_assets(session)
            logger.info(f"   • get_valid_assets(): {len(valid_assets_method)} assets")
            
            # Test 2: Direct query like in validation table endpoint
            all_assets = asset_repo.get_all(session, limit=1000)
            valid_assets_direct = [a for a in all_assets if a.is_valid]
            logger.info(f"   • Direct query (is_valid=True): {len(valid_assets_direct)} assets")
            logger.info(f"   • Total assets in DB: {len(all_assets)} assets")
            
            # Compare results
            if len(valid_assets_method) != len(valid_assets_direct):
                logger.error("❌ INCONSISTENCY DETECTED!")
                logger.error(f"   Method result: {len(valid_assets_method)}")
                logger.error(f"   Direct result: {len(valid_assets_direct)}")
                
                # Find the difference
                method_symbols = set(a.symbol for a in valid_assets_method)
                direct_symbols = set(a.symbol for a in valid_assets_direct)
                
                only_in_method = method_symbols - direct_symbols
                only_in_direct = direct_symbols - method_symbols
                
                if only_in_method:
                    logger.error(f"   Only in method: {list(only_in_method)[:5]}")
                if only_in_direct:
                    logger.error(f"   Only in direct: {list(only_in_direct)[:5]}")
            else:
                logger.info("✅ Asset counts are consistent between methods")
            
            logger.info("\n📊 TESTING OTHER QUERIES (like in broadcast_realtime_data):")
            
            # Test latest indicators
            latest_indicators = indicator_repo.get_latest_indicators(session)
            logger.info(f"   • Latest indicators: {len(latest_indicators)} records")
            
            # Test recent signals (last 24 hours)
            active_signals = signal_repo.get_recent_signals(session, hours=24)
            logger.info(f"   • Active signals (24h): {len(active_signals)} records")
            
            # Test open positions
            active_positions = position_repo.get_open_trades(session)
            logger.info(f"   • Active positions: {len(active_positions)} records")
            
            logger.info("\n📊 SAMPLE DATA:")
            
            # Show sample valid assets
            if valid_assets_method:
                logger.info("   Valid assets sample:")
                for i, asset in enumerate(valid_assets_method[:5]):
                    logger.info(f"     {i+1}. {asset.symbol} - Valid: {asset.is_valid} - Last: {asset.last_validation}")
            
            # Show validation table endpoint behavior (limit=50)
            validation_table_assets = asset_repo.get_all(session, limit=50)
            valid_in_table = [a for a in validation_table_assets if a.is_valid]
            logger.info(f"\n   Validation table (limit=50): {len(valid_in_table)} valid out of {len(validation_table_assets)} total")
            
            # This might be the source of the "9" count if only first 50 assets are considered
            if len(valid_in_table) != len(valid_assets_method):
                logger.warning("⚠️ POTENTIAL ISSUE: Validation table shows different count due to limit!")
                logger.warning(f"   Table count: {len(valid_in_table)}")
                logger.warning(f"   Total valid: {len(valid_assets_method)}")
        
        return True
            
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def simulate_broadcast_data():
    """Simulate the broadcast_realtime_data function to identify the issue"""
    logger.info("\n🚀 Simulating broadcast_realtime_data()...")
    
    try:
        indicator_repo = IndicatorRepository()
        signal_repo = SignalRepository()
        position_repo = TradeRepository()
        
        with get_session() as session:
            # Get latest indicators (same as in broadcast function)
            latest_indicators = indicator_repo.get_latest_indicators(session)
            
            # Get recent signals (last 24 hours)
            active_signals = signal_repo.get_recent_signals(session, hours=24)
            
            # Get open positions
            active_positions = position_repo.get_open_trades(session)
        
        # Prepare broadcast data (like in the actual function)
        broadcast_data = {
            "type": "realtime_update",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "indicators": [
                    {
                        "symbol": ind.symbol if hasattr(ind, 'symbol') else 'UNKNOWN',
                        "timeframe": ind.timeframe,
                        "mm1": float(ind.mm1) if ind.mm1 else None,
                        "center": float(ind.center) if ind.center else None,
                        "rsi": float(ind.rsi) if ind.rsi else None,
                        "price": float(ind.price) if hasattr(ind, 'price') and ind.price else None,
                        "timestamp": ind.timestamp.isoformat()
                    }
                    for ind in latest_indicators
                ],
                "active_signals": len(active_signals),
                "active_positions": [
                    {
                        "symbol": pos.symbol if hasattr(pos, 'symbol') else 'UNKNOWN',
                        "side": pos.side,
                        "unrealized_pnl": float(pos.unrealized_pnl) if pos.unrealized_pnl else None,
                        "current_price": float(pos.current_price) if hasattr(pos, 'current_price') and pos.current_price else None
                    }
                    for pos in active_positions
                ]
            }
        }
        
        logger.info("📤 BROADCAST DATA STRUCTURE:")
        logger.info(f"   • Indicators: {len(broadcast_data['data']['indicators'])} records")
        logger.info(f"   • Active signals: {broadcast_data['data']['active_signals']}")
        logger.info(f"   • Active positions: {len(broadcast_data['data']['active_positions'])} records")
        
        # The issue might be that the WebSocket is not broadcasting valid asset count!
        # It's only broadcasting indicators, signals, and positions
        logger.warning("⚠️ ISSUE IDENTIFIED:")
        logger.warning("   The broadcast_realtime_data() function does NOT send valid asset count!")
        logger.warning("   The frontend might be calculating this from indicators or another source.")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Simulation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test function"""
    logger.info("🚀 Starting WebSocket data investigation...\n")
    
    try:
        # Test 1: Repository queries
        logger.info("=" * 60)
        logger.info("TEST 1: REPOSITORY QUERIES")
        logger.info("=" * 60)
        
        repo_success = test_repository_queries()
        
        # Test 2: Simulate broadcast
        logger.info("\n" + "=" * 60)
        logger.info("TEST 2: BROADCAST SIMULATION")
        logger.info("=" * 60)
        
        broadcast_success = asyncio.run(simulate_broadcast_data())
        
        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("INVESTIGATION SUMMARY")
        logger.info("=" * 60)
        
        if repo_success:
            logger.info("✅ Repository queries working correctly")
        else:
            logger.info("❌ Repository queries have issues")
        
        if broadcast_success:
            logger.info("✅ Broadcast simulation completed")
        else:
            logger.info("❌ Broadcast simulation failed")
        
        logger.info("\n🎯 CONCLUSION:")
        logger.info("   The WebSocket broadcast does NOT send valid asset count directly.")
        logger.info("   The frontend must be getting this data from another endpoint.")
        logger.info("   Check the validation table endpoint and frontend JavaScript for the source.")
        
        return repo_success and broadcast_success
        
    except Exception as e:
        logger.error(f"❌ Investigation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)