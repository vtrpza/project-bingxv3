"""
Asset Information Service
Provides dynamic asset names and metadata with caching and fallbacks
"""

import logging
import asyncio
import aiohttp
from typing import Dict, Optional, List
from datetime import datetime, timedelta
import json
import os

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
        """Get asset information for multiple symbols efficiently"""
        try:
            # Filtrar símbolos que precisam ser buscados
            symbols_to_fetch = []
            result = {}
            
            for symbol in symbols:
                base_currency = symbol.split('/')[0] if '/' in symbol else symbol
                
                if self._is_cache_valid(base_currency):
                    result[symbol] = self.cache[base_currency]
                else:
                    symbols_to_fetch.append(base_currency)
            
            # Buscar símbolos não cacheados
            if symbols_to_fetch:
                new_data = await self._fetch_from_coingecko(symbols_to_fetch)
                
                # Atualizar cache
                for symbol, data in new_data.items():
                    self.cache[symbol] = data
                    self.cache_expiry[symbol] = datetime.utcnow() + self.cache_duration
                    
                    # Adicionar ao resultado
                    full_symbol = f"{symbol}/USDT"
                    if full_symbol in symbols:
                        result[full_symbol] = data
            
            # Preencher símbolos não encontrados com fallbacks
            for symbol in symbols:
                if symbol not in result:
                    base_currency = symbol.split('/')[0] if '/' in symbol else symbol
                    result[symbol] = {
                        'name': self.fallback_names.get(base_currency, base_currency),
                        'symbol': base_currency,
                        'source': 'fallback'
                    }
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting asset info batch: {e}")
            # Retornar fallbacks para todos
            return {
                symbol: {
                    'name': self.fallback_names.get(symbol.split('/')[0], symbol.split('/')[0]),
                    'symbol': symbol.split('/')[0],
                    'source': 'fallback_error'
                }
                for symbol in symbols
            }
    
    async def _fetch_from_coingecko(self, symbols: List[str]) -> Dict[str, Dict]:
        """Fetch asset info from CoinGecko API"""
        try:
            # Mapear símbolos para IDs do CoinGecko (símbolos comuns)
            symbol_to_id = {
                'BTC': 'bitcoin',
                'ETH': 'ethereum',
                'BNB': 'binancecoin',
                'ADA': 'cardano',
                'XRP': 'ripple',
                'SOL': 'solana',
                'DOT': 'polkadot',
                'MATIC': 'matic-network',
                'LTC': 'litecoin',
                'LINK': 'chainlink',
                'UNI': 'uniswap',
                'ATOM': 'cosmos',
                'VET': 'vechain',
                'FIL': 'filecoin',
                'TRX': 'tron',
                'DOGE': 'dogecoin',
                'AVAX': 'avalanche-2',
                'SHIB': 'shiba-inu',
                'NEAR': 'near',
                'ALGO': 'algorand',
                'APE': 'apecoin',
                'LDO': 'lido-dao',
                'OP': 'optimism',
                'ARB': 'arbitrum',
                'PEPE': 'pepe',
                'MKR': 'maker',
                'RNDR': 'render-token',
                'GRT': 'the-graph',
                'RUNE': 'thorchain',
                'FLOW': 'flow',
                'MINA': 'mina-protocol'
            }
            
            # Buscar apenas símbolos que temos mapeamento
            ids_to_fetch = []
            symbol_map = {}
            
            for symbol in symbols:
                if symbol in symbol_to_id:
                    coin_id = symbol_to_id[symbol]
                    ids_to_fetch.append(coin_id)
                    symbol_map[coin_id] = symbol
            
            if not ids_to_fetch:
                return {}
            
            # Fazer requisição para CoinGecko
            ids_str = ','.join(ids_to_fetch)
            url = f"https://api.coingecko.com/api/v3/coins/markets"
            params = {
                'vs_currency': 'usd',
                'ids': ids_str,
                'order': 'market_cap_desc',
                'per_page': len(ids_to_fetch),
                'page': 1,
                'sparkline': 'false'
            }
            
            timeout = aiohttp.ClientTimeout(total=10)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        result = {}
                        for coin in data:
                            coin_id = coin['id']
                            if coin_id in symbol_map:
                                symbol = symbol_map[coin_id]
                                result[symbol] = {
                                    'name': coin['name'],
                                    'symbol': coin['symbol'].upper(),
                                    'market_cap_rank': coin.get('market_cap_rank'),
                                    'source': 'coingecko'
                                }
                        
                        return result
                    else:
                        logger.warning(f"CoinGecko API error: {response.status}")
                        return {}
                        
        except asyncio.TimeoutError:
            logger.warning("CoinGecko API timeout")
            return {}
        except Exception as e:
            logger.error(f"Error fetching from CoinGecko: {e}")
            return {}
    
    def get_asset_display_name(self, symbol: str) -> str:
        """Get cached asset display name or fallback"""
        base_currency = symbol.split('/')[0] if '/' in symbol else symbol
        
        if base_currency in self.cache and self._is_cache_valid(base_currency):
            return self.cache[base_currency]['name']
        
        return self.fallback_names.get(base_currency, base_currency)
    
    async def warmup_cache(self, symbols: List[str]):
        """Pre-warm cache with common symbols"""
        try:
            await self.get_asset_info_batch(symbols)
            logger.info(f"Cache warmed up for {len(symbols)} symbols")
        except Exception as e:
            logger.error(f"Error warming up cache: {e}")

# Global instance
asset_info_service = AssetInfoService()