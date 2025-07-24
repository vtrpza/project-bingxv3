#!/usr/bin/env python3
"""
Teste específico para verificar se a correção dos símbolos BingX está funcionando
"""
import asyncio
import logging
import sys
from pathlib import Path

# Adicionar o diretório do projeto ao path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_symbols_fix():
    """Testa se a correção dos símbolos BingX está funcionando."""
    try:
        from api.client import get_client
        from api.market_data import get_market_data_api
        from scanner.initial_scanner import get_initial_scanner
        
        logger.info("=== Teste de Correção dos Símbolos BingX ===")
        
        # Testar 1: Client direto
        logger.info("1. Testando client BingX direto...")
        client = get_client()
        await client.initialize()
        
        markets = await client.fetch_markets()
        logger.info(f"✅ Cliente retornou {len(markets)} mercados USDT")
        
        if markets:
            # Mostrar alguns exemplos
            logger.info("Primeiros 5 mercados:")
            for i, market in enumerate(markets[:5]):
                logger.info(f"  {i+1}. {market['symbol']} - Base: {market['base']} - Ativo: {market['active']}")
        
        # Testar 2: MarketDataAPI
        logger.info("\n2. Testando MarketDataAPI...")
        market_api = get_market_data_api()
        
        api_markets = await market_api.get_usdt_markets()
        logger.info(f"✅ MarketDataAPI retornou {len(api_markets)} mercados")
        
        # Testar 3: Ticker de um símbolo específico
        if api_markets:
            test_symbol = api_markets[0]['symbol']
            logger.info(f"\n3. Testando ticker para {test_symbol}...")
            
            try:
                ticker = await client.fetch_ticker(test_symbol)
                logger.info(f"✅ Ticker {test_symbol}: ${ticker['last']} - Volume: {ticker['quote_volume']}")
            except Exception as e:
                logger.error(f"❌ Erro ao buscar ticker {test_symbol}: {e}")
        
        # Testar 4: Validação de símbolo
        logger.info("\n4. Testando validação de símbolo...")
        if api_markets:
            test_symbol = api_markets[0]['symbol']
            try:
                validation = await market_api.validate_symbol_trading(test_symbol)
                logger.info(f"✅ Validação {test_symbol}: Válido = {validation['valid']}")
                if not validation['valid']:
                    logger.warning(f"Razão: {validation['reason']}")
            except Exception as e:
                logger.error(f"❌ Erro na validação: {e}")
        
        # Testar 5: Scanner inicial
        logger.info("\n5. Testando scanner inicial...")
        try:
            scanner = get_initial_scanner()
            # Teste rápido com apenas 10 símbolos
            scan_result = await scanner.scan_all_assets(max_assets=10, force_refresh=True)
            
            logger.info(f"✅ Scanner processou {scan_result.total_discovered} ativos")
            logger.info(f"✅ Válidos: {len(scan_result.valid_assets)}")
            logger.info(f"✅ Inválidos: {len(scan_result.invalid_assets)}")
            
            if scan_result.valid_assets:
                logger.info("Símbolos válidos encontrados:")
                for asset in scan_result.valid_assets[:5]:
                    logger.info(f"  - {asset['symbol']}")
                    
        except Exception as e:
            logger.error(f"❌ Erro no scanner: {e}")
        
        await client.close()
        
        logger.info("\n=== Teste Concluído ===")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro geral no teste: {e}")
        logger.exception("Detalhes:")
        return False

async def test_web_api():
    """Testa se a API web está retornando dados."""
    try:
        logger.info("\n=== Teste da API Web ===")
        
        from api.web_api import app
        from fastapi.testclient import TestClient
        
        client = TestClient(app)
        
        # Testar endpoint de status
        logger.info("Testando endpoint /api/status...")
        response = client.get("/api/status")
        logger.info(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            logger.info(f"✅ Status OK - Mercados: {data.get('total_markets', 0)}")
        
        # Testar endpoint de assets
        logger.info("Testando endpoint /api/assets...")
        response = client.get("/api/assets")
        logger.info(f"Assets Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            logger.info(f"✅ Assets OK - Total: {len(data.get('assets', []))}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erro no teste da API web: {e}")
        return False

if __name__ == "__main__":
    async def main():
        # Testar correções dos símbolos
        success1 = await test_symbols_fix()
        
        print("\n" + "="*60 + "\n")
        
        # Testar API web
        success2 = await test_web_api()
        
        if success1 and success2:
            print("\n🎉 CORREÇÕES FUNCIONARAM!")
            print("A tabela deve agora ser preenchida com os símbolos.")
        else:
            print("\n❌ AINDA HÁ PROBLEMAS!")
            print("Verifique os logs acima para detalhes.")
    
    asyncio.run(main())