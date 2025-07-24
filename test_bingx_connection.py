#!/usr/bin/env python3
"""
Teste simples para verificar conectividade com BingX e obtenção de mercados
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

# Adicionar o diretório do projeto ao path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_bingx_connection():
    """Testa a conexão com BingX e lista mercados disponíveis."""
    try:
        # Importar após configurar o path
        from api.client import get_client
        from config.settings import Settings
        
        logger.info("=== Teste de Conexão BingX ===")
        
        # Verificar se as credenciais estão configuradas
        if not Settings.BINGX_API_KEY or Settings.BINGX_API_KEY == "your_bingx_api_key_here":
            logger.error("❌ Credenciais da API BingX não configuradas")
            logger.info("Configure BINGX_API_KEY e BINGX_SECRET_KEY no arquivo .env")
            return False
        
        logger.info(f"✅ Credenciais encontradas (Testnet: {Settings.BINGX_TESTNET})")
        
        # Inicializar cliente
        client = get_client()
        logger.info("Inicializando cliente BingX...")
        
        success = await client.initialize()
        if not success:
            logger.error("❌ Falha ao inicializar cliente BingX")
            return False
        
        logger.info("✅ Cliente BingX inicializado com sucesso")
        
        # Testar fetch_markets
        logger.info("Buscando mercados disponíveis...")
        markets = await client.fetch_markets()
        
        if not markets:
            logger.error("❌ Nenhum mercado encontrado")
            return False
        
        logger.info(f"✅ {len(markets)} mercados USDT encontrados")
        
        # Mostrar alguns mercados como exemplo
        logger.info("Primeiros 10 mercados:")
        for i, market in enumerate(markets[:10]):
            logger.info(f"  {i+1}. {market['symbol']} - Ativo: {market['active']}")
        
        # Testar fetch_ticker com BTC/USDT
        btc_symbol = "BTC/USDT"
        btc_market = next((m for m in markets if m['symbol'] == btc_symbol), None)
        
        if btc_market:
            logger.info(f"Testando ticker para {btc_symbol}...")
            try:
                ticker = await client.fetch_ticker(btc_symbol)
                logger.info(f"✅ Ticker {btc_symbol}: ${ticker['last']} (Vol: {ticker['quote_volume']})")
            except Exception as e:
                logger.error(f"❌ Erro ao obter ticker {btc_symbol}: {e}")
        else:
            logger.warning("⚠️ BTC/USDT não encontrado nos mercados")
        
        # Listar todos os símbolos encontrados
        all_symbols = [market['symbol'] for market in markets]
        logger.info(f"Total de símbolos disponíveis: {len(all_symbols)}")
        
        # Verificar se temos símbolos populares
        popular_symbols = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'ADA/USDT', 'SOL/USDT']
        found_popular = [sym for sym in popular_symbols if sym in all_symbols]
        logger.info(f"Símbolos populares encontrados: {found_popular}")
        
        # Fechar cliente
        await client.close()
        logger.info("✅ Cliente fechado com sucesso")
        
        logger.info("=== Teste Concluído com Sucesso ===")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro durante o teste: {e}")
        logger.exception("Detalhes do erro:")
        return False

async def test_market_data_api():
    """Testa especificamente a API de dados de mercado."""
    try:
        from api.market_data import get_market_data_api
        
        logger.info("=== Teste MarketDataAPI ===")
        
        market_api = get_market_data_api()
        
        # Testar get_usdt_markets
        logger.info("Testando get_usdt_markets()...")
        markets = await market_api.get_usdt_markets()
        
        if not markets:
            logger.error("❌ Nenhum mercado USDT encontrado via MarketDataAPI")
            return False
        
        logger.info(f"✅ {len(markets)} mercados USDT via MarketDataAPI")
        
        # Testar market summary
        if markets:
            first_symbol = markets[0]['symbol']
            logger.info(f"Testando market summary para {first_symbol}...")
            try:
                summary = await market_api.get_market_summary(first_symbol)
                logger.info(f"✅ Market summary {first_symbol}: Preço ${summary['price']}")
            except Exception as e:
                logger.error(f"❌ Erro ao obter market summary: {e}")
        
        logger.info("=== MarketDataAPI Teste Concluído ===")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro no teste MarketDataAPI: {e}")
        logger.exception("Detalhes do erro:")
        return False

if __name__ == "__main__":
    async def main():
        # Testar client básico
        success1 = await test_bingx_connection()
        
        print("\n" + "="*50 + "\n")
        
        # Testar market data API
        success2 = await test_market_data_api()
        
        if success1 and success2:
            print("\n🎉 TODOS OS TESTES PASSARAM!")
            print("O problema pode estar na inicialização do scanner ou na interface web.")
        else:
            print("\n❌ ALGUNS TESTES FALHARAM!")
            print("Verifique as configurações de API e conexão.")
    
    asyncio.run(main())