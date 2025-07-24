# 💹 Módulo Trading - Documentação

## 📋 Visão Geral

O módulo Trading é o motor de execução de ordens, responsável por executar trades, gerenciar posições e implementar a gestão de risco.

## 🏗️ Arquitetura

### Componentes

1. **TradingEngine** (`engine.py`)
   - Processa sinais de trading
   - Executa ordens na BingX
   - Gerencia limite de trades simultâneos

2. **OrderManager** (`order_manager.py`)
   - Cria e envia ordens
   - Monitora status de execução
   - Gerencia tipos de ordem (market, limit)

3. **RiskManager** (`risk_manager.py`)
   - Implementa stop loss e take profit
   - Trailing stop automático
   - Cálculo de tamanho de posição

4. **PositionTracker** (`position_tracker.py`)
   - Monitora posições abertas
   - Atualiza P&L em tempo real
   - Detecta pontos de ajuste

## 📊 Estrutura de Dados

### Trade
```python
{
    "id": "uuid",
    "symbol": "BTC/USDT",
    "side": "BUY",
    "entry_price": 42000.00,
    "quantity": 0.01,
    "stop_loss": 41160.00,  # -2%
    "take_profit": None,
    "status": "OPEN",
    "entry_time": "2024-01-20T10:30:00Z",
    "pnl": 0,
    "pnl_percentage": 0
}
```

### Order
```python
{
    "order_id": "bingx_order_id",
    "trade_id": "uuid",
    "type": "MARKET",
    "side": "BUY",
    "price": None,
    "quantity": 0.01,
    "status": "FILLED",
    "filled_price": 42000.00,
    "timestamp": "2024-01-20T10:30:00Z"
}
```

## 🔄 Fluxo de Trading

### Entrada no Trade
1. Recebe sinal do Scanner
2. Verifica limite de trades abertos
3. Calcula tamanho da posição
4. Executa ordem a mercado
5. Define stop loss inicial (-2%)
6. Registra trade no banco

### Gestão de Posição
1. Monitora preço em tempo real
2. Quando atinge +1.5%:
   - Ajusta stop loss para breakeven
   - Sinaliza trailing ativo
3. Quando atinge +3%:
   - Ajusta stop loss para +1.5%
   - Define próximo alvo
4. Continua ajustando progressivamente

### Saída do Trade
- Stop loss atingido
- Take profit manual
- Sinal de reversão

## ⚙️ Configurações

```python
TRADING_CONFIG = {
    "MAX_CONCURRENT_TRADES": 5,
    "POSITION_SIZE_PERCENTAGE": 2,  # % do saldo por trade
    "INITIAL_STOP_LOSS": 0.02,      # 2%
    "BREAKEVEN_TRIGGER": 0.015,     # 1.5%
    "TRAILING_STEPS": [
        {"trigger": 0.015, "stop": 0.0},    # Breakeven
        {"trigger": 0.03, "stop": 0.015},   # +3% → SL +1.5%
        {"trigger": 0.05, "stop": 0.03},    # +5% → SL +3%
    ]
}
```

## 📈 Regras de Trading

### Regra 1: Cruzamento de Médias
```python
if (mm1_crosses_center_2h or mm1_crosses_center_4h) and (35 <= rsi <= 73):
    execute_trade()
```

### Regra 2: Distância de Médias
```python
if (mm1_distance_2h >= 0.02) or (mm1_distance_4h >= 0.03):
    execute_trade()
```

### Regra 3: Volume Súbito
```python
if volume_spike > threshold:
    if mm1 > center:
        execute_trade("BUY")
    else:
        execute_trade("SELL")
```

## 🔌 Integração

- **API**: Executa ordens via `api.client`
- **Scanner**: Recebe sinais de trading
- **Database**: Persiste trades e ordens
- **Frontend**: Envia atualizações em tempo real

## 🚨 Gestão de Risco

1. **Validação pré-trade**:
   - Saldo suficiente
   - Limite de trades não excedido
   - Par válido para trading

2. **Proteção de capital**:
   - Stop loss obrigatório
   - Tamanho máximo de posição
   - Diversificação automática

3. **Monitoramento contínuo**:
   - Verificação de conexão
   - Validação de ordens
   - Alertas de anomalias

## 🧪 Testes

```bash
python -m pytest tests/test_trading.py
```

## 📊 Métricas

- Taxa de sucesso
- Profit factor
- Drawdown máximo
- Tempo médio no trade
- P&L por período