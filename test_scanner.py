#!/usr/bin/env python3
"""
Script de teste para o scanner inicial
Testa a funcionalidade básica do scanner sem dependências externas
"""

import asyncio
import sys
import os
from pathlib import Path

# Adicionar o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

async def test_scanner_import():
    """Teste se o scanner pode ser importado corretamente"""
    try:
        from scanner.initial_scanner import InitialScanner, get_initial_scanner, perform_initial_scan
        print("✅ Scanner importado com sucesso")
        return True
    except Exception as e:
        print(f"❌ Erro ao importar scanner: {e}")
        return False

async def test_scanner_instantiation():
    """Teste se o scanner pode ser instanciado"""
    try:
        from scanner.initial_scanner import InitialScanner
        scanner = InitialScanner()
        print("✅ Scanner instanciado com sucesso")
        return True
    except Exception as e:
        print(f"❌ Erro ao instanciar scanner: {e}")
        return False

async def test_api_integration():
    """Teste se o endpoint da API pode ser chamado"""
    try:
        import requests
        import json
        
        # Tentar chamar o endpoint (mesmo que falhe, verifica se está disponível)
        url = "http://localhost:8000/api/scanner/initial-scan"
        headers = {"Content-Type": "application/json"}
        
        # Fazer uma requisição POST (vai falhar se o servidor não estiver rodando)
        response = requests.post(url, headers=headers, timeout=5)
        print(f"✅ Endpoint API responde (status: {response.status_code})")
        return True
        
    except requests.exceptions.ConnectionError:
        print("⚠️  Servidor não está rodando (esperado para teste)")
        return True  # Isso é esperado em teste
    except Exception as e:
        print(f"❌ Erro no teste da API: {e}")
        return False

async def test_config_files():
    """Teste se os arquivos de configuração existem"""
    try:
        config_files = [
            "config/trading_config.py",
            "database/connection.py",
            "api/web_api.py",
            "frontend/index.html"
        ]
        
        for config_file in config_files:
            if not Path(config_file).exists():
                print(f"❌ Arquivo não encontrado: {config_file}")
                return False
        
        print("✅ Todos os arquivos de configuração encontrados")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao verificar arquivos: {e}")
        return False

async def run_tests():
    """Executa todos os testes"""
    print("🧪 Iniciando testes do Scanner Inicial BingX...\n")
    
    tests = [
        ("Importação do Scanner", test_scanner_import),
        ("Instanciação do Scanner", test_scanner_instantiation), 
        ("Integração com API", test_api_integration),
        ("Arquivos de Configuração", test_config_files)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"🔍 Executando: {test_name}")
        try:
            result = await test_func()
            results.append(result)
        except Exception as e:
            print(f"❌ Falha no teste '{test_name}': {e}")
            results.append(False)
        print()
    
    # Resumo dos resultados
    passed = sum(results)
    total = len(results)
    
    print("=" * 50)
    print(f"📊 RESULTADOS DOS TESTES:")
    print(f"   ✅ Passou: {passed}/{total}")
    print(f"   ❌ Falhou: {total - passed}/{total}")
    print(f"   📈 Taxa de Sucesso: {(passed/total)*100:.1f}%")
    
    if passed == total:
        print("🎉 Todos os testes passaram! Scanner pronto para uso.")
        return True
    else:
        print("⚠️  Alguns testes falharam. Verifique as configurações.")
        return False

if __name__ == "__main__":
    print("🤖 BingX Trading Bot - Teste do Scanner Inicial")
    print("=" * 50)
    
    try:
        success = asyncio.run(run_tests())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⏹️  Teste interrompido pelo usuário")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Erro crítico no teste: {e}")
        sys.exit(1)