#!/usr/bin/env python3
"""
Teste do novo pós-processamento de símbolos do initial_scanner
"""

import asyncio
import sys
import os

# Adicionar o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Forçar uso do SQLite para teste local
os.environ.pop('DATABASE_URL', None)
os.environ['DB_TYPE'] = 'sqlite'
os.environ['DB_PATH'] = 'test_trading_bot.db'

from scanner.initial_scanner import get_initial_scanner
from database.connection import init_database, create_tables
from utils.logger import get_logger

logger = get_logger(__name__)

async def test_symbols_table_data():
    """Teste do novo método get_all_symbols_data"""
    try:
        print("🚀 Iniciando teste do pós-processamento de símbolos...")
        
        # Inicializar banco de dados
        print("📋 Inicializando banco de dados...")
        if not init_database():
            print("❌ ERRO: Falha ao inicializar banco de dados")
            return False
        
        if not create_tables():
            print("❌ ERRO: Falha ao criar tabelas")
            return False
        
        print("✅ Banco de dados inicializado")
        
        # Obter scanner
        scanner = get_initial_scanner()
        
        # Testar sem dados de mercado (mais rápido)
        print("🔍 Testando busca de dados dos símbolos (sem dados de mercado)...")
        result_basic = await scanner.get_all_symbols_data(
            include_market_data=False,
            max_symbols=10
        )
        
        print(f"📊 RESULTADO BÁSICO:")
        print(f"   • Total de símbolos: {result_basic['total_count']}")
        print(f"   • Fonte: {result_basic['metadata']['source']}")
        print(f"   • Última atualização: {result_basic['last_updated']}")
        
        if result_basic['symbols']:
            print(f"   • Primeiro símbolo: {result_basic['symbols'][0]['symbol']}")
            print(f"   • Status exemplo: {result_basic['symbols'][0]['status_text']}")
            print(f"   • Tem dados live: {result_basic['symbols'][0]['has_live_data']}")
        
        # Testar com dados de mercado (se houver poucos símbolos)
        if result_basic['total_count'] <= 5:
            print("\n🔍 Testando busca com dados de mercado...")
            result_with_market = await scanner.get_all_symbols_data(
                include_market_data=True,
                max_symbols=5
            )
            
            print(f"📊 RESULTADO COM DADOS DE MERCADO:")
            print(f"   • Total de símbolos: {result_with_market['total_count']}")
            print(f"   • Fonte: {result_with_market['metadata']['source']}")
            
            if result_with_market['symbols']:
                symbol_example = result_with_market['symbols'][0]
                print(f"   • Exemplo - Símbolo: {symbol_example['symbol']}")
                print(f"   • Exemplo - Preço: {symbol_example['current_price']}")
                print(f"   • Exemplo - Tem dados live: {symbol_example['has_live_data']}")
        
        print("\n✅ Teste concluído com sucesso!")
        return True
        
    except Exception as e:
        print(f"❌ ERRO durante teste: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_symbols_table_data())
    sys.exit(0 if success else 1)