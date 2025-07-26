"""
Asset Information Service
Provides dynamic asset names and metadata with caching and fallbacks
"""

import logging
from typing import Dict, Optional, List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class AssetInfoService:
    """Service to fetch and cache asset information dynamically"""
    
    def __init__(self):
        self.cache = {}
        self.cache_expiry = {}
        self.cache_duration = timedelta(hours=24)  # Cache por 24 horas
        self.fallback_names = self._load_fallback_names()
        
    def _load_fallback_names(self) -> Dict[str, str]:
        """Load basic fallback names for common assets"""
        return {
            'BTC': 'Bitcoin',
            'ETH': 'Ethereum', 
            'BNB': 'BNB',
            'ADA': 'Cardano',
            'XRP': 'XRP',
            'SOL': 'Solana',
            'DOT': 'Polkadot',
            'MATIC': 'Polygon',
            'LTC': 'Litecoin',
            'LINK': 'Chainlink',
            'UNI': 'Uniswap',
            'ATOM': 'Cosmos',
            'VET': 'VeChain',
            'FIL': 'Filecoin',
            'TRX': 'TRON',
            'ETC': 'Ethereum Classic',
            'XLM': 'Stellar',
            'THETA': 'Theta Network',
            'AAVE': 'Aave',
            'EOS': 'EOS',
            'NEAR': 'NEAR Protocol',
            'ALGO': 'Algorand',
            'XTZ': 'Tezos',
            'EGLD': 'MultiversX',
            'FTM': 'Fantom',
            'SAND': 'The Sandbox',
            'MANA': 'Decentraland',
            'CRV': 'Curve DAO',
            'COMP': 'Compound',
            'YFI': 'yearn.finance',
            'SUSHI': 'SushiSwap',
            'ZEC': 'Zcash',
            'DASH': 'Dash',
            'NEO': 'NEO',
            'IOTA': 'IOTA',
            'QTUM': 'Qtum',
            'OMG': 'OMG Network',
            'ZIL': 'Zilliqa',
            'BAT': 'Basic Attention',
            'ZRX': '0x Protocol',
            'WAVES': 'Waves',
            'ICX': 'ICON',
            'ONT': 'Ontology',
            'DOGE': 'Dogecoin',
            'SHIB': 'Shiba Inu',
            'AVAX': 'Avalanche',
            'LUNA': 'Terra',
            'ICP': 'Internet Computer',
            'APE': 'ApeCoin',
            'LDO': 'Lido DAO',
            'APT': 'Aptos',
            'OP': 'Optimism',
            'ARB': 'Arbitrum',
            'SUI': 'Sui',
            'PEPE': 'Pepe',
            'WLD': 'Worldcoin',
            'MKR': 'Maker',
            'RNDR': 'Render',
            'GRT': 'The Graph',
            'IMX': 'Immutable',
            'LRC': 'Loopring',
            'RUNE': 'THORChain',
            'KAVA': 'Kava',
            'FLOW': 'Flow',
            'MINA': 'Mina Protocol',
            'ROSE': 'Oasis Network'
        }
    
    def _is_cache_valid(self, symbol: str) -> bool:
        """Check if cache entry is still valid"""
        if symbol not in self.cache_expiry:
            return False
        return datetime.utcnow() < self.cache_expiry[symbol]
    
    async def get_asset_info_batch(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get asset information for multiple symbols using only BingX data and fallbacks"""
        try:
            result = {}
            
            for symbol in symbols:
                base_currency = symbol.split('/')[0] if '/' in symbol else symbol
                
                # Check cache first
                if self._is_cache_valid(base_currency):
                    result[symbol] = self.cache[base_currency]
                else:
                    # Use fallback names (no external API calls)
                    asset_info = {
                        'name': self.fallback_names.get(base_currency, base_currency),
                        'symbol': base_currency,
                        'source': 'bingx_fallback'
                    }
                    
                    # Cache the fallback
                    self.cache[base_currency] = asset_info
                    self.cache_expiry[base_currency] = datetime.utcnow() + self.cache_duration
                    result[symbol] = asset_info
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting asset info batch: {e}")
            # Return fallbacks for all
            return {
                symbol: {
                    'name': self.fallback_names.get(symbol.split('/')[0], symbol.split('/')[0]),
                    'symbol': symbol.split('/')[0],
                    'source': 'fallback_error'
                }
                for symbol in symbols
            }
    
    async def _fetch_from_bingx(self, symbols: List[str]) -> Dict[str, Dict]:
        """Fetch asset info from BingX using ticker data (future enhancement)"""
        # Future: integrate with BingX client to get market data
        # For now, return empty dict to use fallbacks
        logger.info(f"Using BingX fallback names for {len(symbols)} symbols")
        return {}
    
    def get_asset_display_name(self, symbol: str) -> str:
        """Get cached asset display name or fallback"""
        base_currency = symbol.split('/')[0] if '/' in symbol else symbol
        
        if base_currency in self.cache and self._is_cache_valid(base_currency):
            return self.cache[base_currency]['name']
        
        return self.fallback_names.get(base_currency, base_currency)
    
    async def warmup_cache(self, symbols: List[str]):
        """Pre-warm cache with common symbols using BingX fallback names"""
        try:
            await self.get_asset_info_batch(symbols)
            logger.info(f"BingX asset cache warmed up for {len(symbols)} symbols")
        except Exception as e:
            logger.error(f"Error warming up BingX asset cache: {e}")

# Global instance
asset_info_service = AssetInfoService()