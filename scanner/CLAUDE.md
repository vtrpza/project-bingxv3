# 🔍 Módulo Scanner - Documentação

## 📋 Visão Geral

O módulo Scanner é responsável por escanear e validar ativos na BingX, mantendo uma lista atualizada de ativos válidos para trading.

## 🏗️ Arquitetura

### Componentes

1. **InitialScanner** (`initial_scanner.py`) 
   - Descobre todos os ativos disponíveis na BingX
   - Coleta dados básicos do mercado
   - Popula o banco de dados com símbolos descobertos
   - Deixa a validação para o ContinuousScanner

2. **ContinuousScanner** (`continuous_scanner.py`)
   - Valida e monitora ativos descobertos
   - Coleta dados de preço e indicadores em tempo real
   - Detecta sinais de trading
   - Aplica critérios de validação por volume

## 📊 Estrutura de Dados

### Asset (Ativo)
```python
{
    "symbol": "BTC/USDT",
    "valid": true,
    "last_validation": "2024-01-20T10:30:00Z",
    "validation_criteria": {
        "volume_24h": 1000000,
        "min_volume_required": 100000,
        "active_trading": true
    }
}
```

### ScanResult (Resultado do Scan)
```python
{
    "asset": "BTC/USDT",
    "timestamp": "2024-01-20T10:30:00Z",
    "price_spot": 42000.50,
    "indicators": {
        "mm1_spot": 41950.00,
        "center_spot": 41900.00,
        "rsi_spot": 55.5,
        "mm1_2h": 41800.00,
        "center_2h": 41700.00,
        "rsi_2h": 52.3,
        "mm1_4h": 41600.00,
        "center_4h": 41500.00,
        "rsi_4h": 48.7
    },
    "volume_change": 15.5,
    "signal": "BUY"
}
```

## 🔄 Fluxo de Operação

### Escaneamento Inicial
1. Busca todos os pares de trading da BingX
2. Filtra por volume mínimo (configurável)
3. Verifica se o par está ativo para trading
4. Salva lista de válidos/inválidos no banco

### Escaneamento Contínuo
1. Carrega lista de ativos válidos
2. Para cada ativo:
   - Busca dados atuais (spot)
   - Busca candles de 2h e 4h
   - Calcula indicadores técnicos
   - Detecta sinais de trading
3. Envia sinais para o motor de trading
4. Atualiza dados no banco

## ⚙️ Configurações

```python
SCANNER_CONFIG = {
    "MIN_VOLUME_24H": 100000,  # Volume mínimo em USDT
    "SCAN_INTERVAL": 30,       # Segundos entre scans
    "MAX_ASSETS": 100,         # Máximo de ativos para monitorar
    "TIMEFRAMES": ["2h", "4h"], # Timeframes para análise
}
```

## 🔌 Integração

- **API**: Usa `api.client` para comunicação com BingX
- **Analysis**: Usa módulo de análise para cálculo de indicadores
- **Database**: Persiste dados via `database.models`
- **Trading**: Envia sinais para `trading.engine`

## 📈 Performance

- Scan inicial: ~10 segundos para 500 ativos
- Scan contínuo: ~0.1 segundo por ativo
- Uso de cache para otimizar chamadas API
- Threading para paralelizar operações

## 🧪 Testes

```bash
python -m pytest tests/test_scanner.py
```

## 🚨 Tratamento de Erros

- Retry automático em falhas de API
- Logging detalhado de erros
- Fallback para último estado válido
- Alertas em caso de falha crítica