# ⚙️ Módulo Config - Configurações do Sistema

## 📋 Visão Geral

Centraliza todas as configurações do sistema, incluindo parâmetros de trading, conexões, limites e estratégias.

## 🏗️ Arquitetura

### Componentes

1. **Settings** (`settings.py`)
   - Configurações gerais do sistema
   - Variáveis de ambiente
   - Validação de configurações

2. **TradingConfig** (`trading_config.py`)
   - Parâmetros de estratégia
   - Limites de risco
   - Regras de entrada/saída

3. **DatabaseConfig** (`database_config.py`)
   - Conexão PostgreSQL
   - Pool de conexões
   - Configurações de cache

## 📊 Estrutura de Configurações

### Configurações Gerais
```python
# settings.py
import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Ambiente
    ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    
    # API BingX
    BINGX_API_KEY = os.getenv("BINGX_API_KEY")
    BINGX_SECRET_KEY = os.getenv("BINGX_SECRET_KEY")
    BINGX_TESTNET = os.getenv("BINGX_TESTNET", "False").lower() == "true"
    
    # Banco de Dados
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql://user:pass@localhost:5432/bingx_trading"
    )
    
    # Redis Cache (opcional)
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "logs/trading_bot.log")
```

### Configurações de Trading
```python
# trading_config.py

class TradingConfig:
    # Limites Gerais
    MAX_CONCURRENT_TRADES = 5
    MIN_ORDER_SIZE_USDT = 10.0
    MAX_POSITION_SIZE_PERCENT = 2.0  # % do saldo total
    
    # Gestão de Risco
    INITIAL_STOP_LOSS_PERCENT = 0.02  # 2%
    BREAKEVEN_TRIGGER_PERCENT = 0.015  # 1.5%
    
    # Trailing Stop Levels
    TRAILING_STOP_LEVELS = [
        {"trigger": 0.015, "stop": 0.0},     # 1.5% → Breakeven
        {"trigger": 0.03, "stop": 0.015},    # 3% → SL +1.5%
        {"trigger": 0.05, "stop": 0.03},     # 5% → SL +3%
        {"trigger": 0.08, "stop": 0.05},     # 8% → SL +5%
        {"trigger": 0.10, "stop": 0.08},     # 10% → SL +8%
    ]
    
    # Indicadores Técnicos
    MM1_PERIOD = 9
    CENTER_PERIOD = 21
    RSI_PERIOD = 14
    
    # Regras de Trading
    RSI_MIN = 35
    RSI_MAX = 73
    MA_DISTANCE_2H_PERCENT = 0.02  # 2%
    MA_DISTANCE_4H_PERCENT = 0.03  # 3%
    VOLUME_SPIKE_THRESHOLD = 2.0    # 2x média
    
    # Scanner
    SCAN_INTERVAL_SECONDS = 30
    MIN_VOLUME_24H_USDT = 100000
    MAX_ASSETS_TO_SCAN = 100
    
    # Timeframes
    ANALYSIS_TIMEFRAMES = ["2h", "4h"]
    SPOT_TIMEFRAME = "1m"
```

### Configurações do Scanner
```python
# scanner_config.py

class ScannerConfig:
    # Validação de Ativos
    VALIDATION_CRITERIA = {
        "min_volume_24h": 100000,
        "min_trades_24h": 1000,
        "max_spread_percent": 0.005,  # 0.5%
        "required_quote": "USDT"
    }
    
    # Intervalo de Escaneamento
    INITIAL_SCAN_INTERVAL = 300  # 5 minutos
    CONTINUOUS_SCAN_INTERVAL = 30  # 30 segundos
    
    # Priorização
    PRIORITY_SYMBOLS = [
        "BTC/USDT", "ETH/USDT", "BNB/USDT",
        "SOL/USDT", "ADA/USDT", "DOT/USDT"
    ]
    
    # Cache
    CACHE_TTL_SECONDS = 60
    USE_CACHE = True
```

### Configurações de Análise
```python
# analysis_config.py

class AnalysisConfig:
    # Períodos de Cálculo
    INDICATOR_PERIODS = {
        "mm1": 9,
        "center": 21,
        "rsi": 14,
        "volume_sma": 20
    }
    
    # Limites de Sinal
    SIGNAL_THRESHOLDS = {
        "strong_buy": 0.8,
        "buy": 0.6,
        "neutral": 0.4,
        "sell": 0.2,
        "strong_sell": 0.0
    }
    
    # Pesos das Regras
    RULE_WEIGHTS = {
        "ma_crossover": 0.4,
        "ma_distance": 0.3,
        "volume_spike": 0.3
    }
```

## 🔐 Variáveis de Ambiente (.env)

```bash
# Ambiente
ENVIRONMENT=production
DEBUG=False

# BingX API
BINGX_API_KEY=sua_api_key_aqui
BINGX_SECRET_KEY=sua_secret_key_aqui
BINGX_TESTNET=False

# Banco de Dados
DATABASE_URL=postgresql://user:password@localhost:5432/bingx_trading
DB_POOL_SIZE=20
DB_POOL_TIMEOUT=30

# Redis (opcional)
REDIS_URL=redis://localhost:6379/0

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/trading_bot.log

# Notificações (opcional)
TELEGRAM_BOT_TOKEN=seu_token_aqui
TELEGRAM_CHAT_ID=seu_chat_id_aqui

# Performance
MAX_WORKERS=4
ENABLE_PROFILING=False
```

## 🚀 Configurações para Deploy (Render)

### render.yaml
```yaml
services:
  - type: web
    name: bingx-trading-bot
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: python main.py
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: bingx-db
          property: connectionString
      - key: PYTHON_VERSION
        value: 3.11
    
  - type: worker
    name: bingx-scanner
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: python scanner/worker.py
    
databases:
  - name: bingx-db
    databaseName: bingx_trading
    user: bingx_user
```

## 📊 Validação de Configurações

```python
# config_validator.py

class ConfigValidator:
    @staticmethod
    def validate_all():
        """Valida todas as configurações na inicialização"""
        errors = []
        
        # API Keys
        if not Settings.BINGX_API_KEY:
            errors.append("BINGX_API_KEY não configurada")
            
        # Trading Limits
        if TradingConfig.MAX_CONCURRENT_TRADES < 1:
            errors.append("MAX_CONCURRENT_TRADES deve ser >= 1")
            
        # Risk Management
        if TradingConfig.INITIAL_STOP_LOSS_PERCENT >= 0.1:
            errors.append("Stop loss muito alto (>= 10%)")
            
        # Database
        if not Settings.DATABASE_URL:
            errors.append("DATABASE_URL não configurada")
            
        if errors:
            raise ConfigurationError("\n".join(errors))
```

## 🔄 Hot Reload de Configurações

```python
class ConfigManager:
    def __init__(self):
        self._config_cache = {}
        self._last_reload = None
        
    def get_config(self, key, default=None):
        """Obtém configuração com possibilidade de reload"""
        if self._should_reload():
            self._reload_configs()
        return self._config_cache.get(key, default)
        
    def _should_reload(self):
        """Verifica se deve recarregar configs"""
        if not self._last_reload:
            return True
        return (datetime.now() - self._last_reload).seconds > 300
```

## 🧪 Testes

```bash
python -m pytest tests/test_config.py
```

## 📈 Monitoramento de Configurações

- Log de mudanças de configuração
- Alertas em valores anormais
- Backup de configurações
- Auditoria de alterações