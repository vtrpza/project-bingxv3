# 🗄️ Módulo Database - Documentação

## 📋 Visão Geral

O módulo Database gerencia toda a persistência de dados usando PostgreSQL, incluindo ativos, trades, ordens e histórico de análises.

## 🏗️ Arquitetura

### Componentes

1. **Models** (`models.py`)
   - Definição de tabelas SQLAlchemy
   - Relacionamentos entre entidades
   - Validações de dados

2. **Repository** (`repository.py`)
   - Operações CRUD
   - Queries otimizadas
   - Cache de consultas

3. **Migrations** (`migrations/`)
   - Versionamento do schema
   - Scripts de migração Alembic

## 📊 Esquema do Banco de Dados

### Tabela: assets (Ativos)
```sql
CREATE TABLE assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol VARCHAR(20) NOT NULL UNIQUE,
    base_currency VARCHAR(10) NOT NULL,
    quote_currency VARCHAR(10) NOT NULL,
    is_valid BOOLEAN DEFAULT true,
    min_order_size DECIMAL(20,8),
    last_validation TIMESTAMP WITH TIME ZONE,
    validation_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_assets_symbol ON assets(symbol);
CREATE INDEX idx_assets_valid ON assets(is_valid);
```

### Tabela: market_data (Dados de Mercado)
```sql
CREATE TABLE market_data (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES assets(id),
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    open DECIMAL(20,8) NOT NULL,
    high DECIMAL(20,8) NOT NULL,
    low DECIMAL(20,8) NOT NULL,
    close DECIMAL(20,8) NOT NULL,
    volume DECIMAL(20,8) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(asset_id, timestamp, timeframe)
);

CREATE INDEX idx_market_data_asset_time ON market_data(asset_id, timestamp DESC);
```

### Tabela: indicators (Indicadores Técnicos)
```sql
CREATE TABLE indicators (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES assets(id),
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    mm1 DECIMAL(20,8),
    center DECIMAL(20,8),
    rsi DECIMAL(5,2),
    volume_sma DECIMAL(20,8),
    additional_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(asset_id, timestamp, timeframe)
);

CREATE INDEX idx_indicators_asset_time ON indicators(asset_id, timestamp DESC);
```

### Tabela: trades (Operações)
```sql
CREATE TABLE trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES assets(id),
    side VARCHAR(10) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    entry_price DECIMAL(20,8) NOT NULL,
    quantity DECIMAL(20,8) NOT NULL,
    stop_loss DECIMAL(20,8),
    take_profit DECIMAL(20,8),
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    entry_reason VARCHAR(50),
    entry_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    exit_time TIMESTAMP WITH TIME ZONE,
    exit_price DECIMAL(20,8),
    exit_reason VARCHAR(50),
    pnl DECIMAL(20,8),
    pnl_percentage DECIMAL(10,4),
    fees DECIMAL(20,8),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_trades_status ON trades(status);
CREATE INDEX idx_trades_asset ON trades(asset_id);
CREATE INDEX idx_trades_entry_time ON trades(entry_time DESC);
```

### Tabela: orders (Ordens)
```sql
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trade_id UUID REFERENCES trades(id),
    exchange_order_id VARCHAR(100) UNIQUE,
    type VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    price DECIMAL(20,8),
    quantity DECIMAL(20,8) NOT NULL,
    status VARCHAR(20) NOT NULL,
    filled_quantity DECIMAL(20,8),
    average_price DECIMAL(20,8),
    fees DECIMAL(20,8),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_orders_trade ON orders(trade_id);
CREATE INDEX idx_orders_status ON orders(status);
```

### Tabela: signals (Sinais de Trading)
```sql
CREATE TABLE signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID REFERENCES assets(id),
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    signal_type VARCHAR(10) NOT NULL,
    strength DECIMAL(5,2),
    rules_triggered TEXT[],
    indicators_snapshot JSONB,
    trade_id UUID REFERENCES trades(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_signals_asset_time ON signals(asset_id, timestamp DESC);
```

### Tabela: system_config (Configurações)
```sql
CREATE TABLE system_config (
    key VARCHAR(100) PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

## 🔄 Relacionamentos

```
assets 1:N market_data
assets 1:N indicators
assets 1:N trades
assets 1:N signals
trades 1:N orders
signals N:1 trades
```

## ⚙️ Configuração de Conexão

```python
DATABASE_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", 5432),
    "database": os.getenv("DB_NAME", "bingx_trading"),
    "user": os.getenv("DB_USER", "trading_bot"),
    "password": os.getenv("DB_PASSWORD"),
    "pool_size": 20,
    "max_overflow": 40,
    "pool_timeout": 30,
    "pool_recycle": 3600
}
```

## 📈 Queries Importantes

### Trades Abertos
```sql
SELECT t.*, a.symbol 
FROM trades t
JOIN assets a ON t.asset_id = a.id
WHERE t.status = 'OPEN'
ORDER BY t.entry_time DESC;
```

### Performance por Ativo
```sql
SELECT 
    a.symbol,
    COUNT(t.id) as total_trades,
    SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
    AVG(t.pnl_percentage) as avg_pnl_percentage,
    SUM(t.pnl) as total_pnl
FROM trades t
JOIN assets a ON t.asset_id = a.id
WHERE t.status = 'CLOSED'
GROUP BY a.symbol
ORDER BY total_pnl DESC;
```

### Últimos Indicadores
```sql
SELECT DISTINCT ON (asset_id, timeframe)
    i.*, a.symbol
FROM indicators i
JOIN assets a ON i.asset_id = a.id
WHERE a.is_valid = true
ORDER BY asset_id, timeframe, timestamp DESC;
```

## 🔌 Repository Pattern

```python
class AssetRepository:
    def get_valid_assets(self):
        """Retorna todos os ativos válidos"""
        
    def update_validation_status(self, symbol, is_valid, data):
        """Atualiza status de validação"""

class TradeRepository:
    def create_trade(self, trade_data):
        """Cria novo trade"""
        
    def get_open_trades(self):
        """Retorna trades abertos"""
        
    def update_trade_status(self, trade_id, status, exit_data):
        """Atualiza status do trade"""
```

## 🧪 Testes

```bash
python -m pytest tests/test_database.py
```

## 🚨 Backup e Manutenção

- Backup automático diário
- Vacuum semanal
- Análise de queries lentas
- Monitoramento de tamanho