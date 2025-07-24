# 🔌 Módulo API - Integração BingX

## 📋 Visão Geral

O módulo API gerencia toda a comunicação com a exchange BingX usando a biblioteca CCXT, incluindo autenticação, execução de ordens e coleta de dados de mercado.

## 🏗️ Arquitetura

### Componentes

1. **BingXClient** (`client.py`)
   - Configuração e autenticação CCXT
   - Gerenciamento de conexão
   - Rate limiting automático

2. **MarketDataAPI** (`market_data.py`)
   - Busca de preços e candles
   - Orderbook e trades recentes
   - Informações de mercado

3. **TradingAPI** (`trading.py`)
   - Execução de ordens
   - Consulta de saldo
   - Histórico de ordens

4. **WebSocketClient** (`websocket.py`)
   - Streams em tempo real
   - Atualizações de preço
   - Status de ordens

## 🔐 Configuração e Autenticação

### Configuração CCXT
```python
import ccxt
import os

class BingXClient:
    def __init__(self):
        self.exchange = ccxt.bingx({
            'apiKey': os.getenv('BINGX_API_KEY'),
            'secret': os.getenv('BINGX_SECRET_KEY'),
            'enableRateLimit': True,
            'rateLimit': 50,  # ms entre requisições
            'options': {
                'defaultType': 'spot',  # spot trading
                'adjustForTimeDifference': True,
            }
        })
```

### Variáveis de Ambiente
```bash
BINGX_API_KEY=sua_api_key_aqui
BINGX_SECRET_KEY=sua_secret_key_aqui
BINGX_TESTNET=false  # true para usar testnet
```

## 📊 APIs de Dados de Mercado

### Buscar Mercados Disponíveis
```python
async def fetch_markets(self):
    """
    Retorna todos os pares de trading disponíveis
    """
    markets = await self.exchange.fetch_markets()
    return [
        {
            'symbol': market['symbol'],
            'base': market['base'],
            'quote': market['quote'],
            'active': market['active'],
            'limits': market['limits']
        }
        for market in markets
        if market['quote'] == 'USDT' and market['active']
    ]
```

### Buscar Ticker
```python
async def fetch_ticker(self, symbol):
    """
    Retorna informações atuais do mercado
    """
    ticker = await self.exchange.fetch_ticker(symbol)
    return {
        'symbol': symbol,
        'last': ticker['last'],
        'bid': ticker['bid'],
        'ask': ticker['ask'],
        'volume': ticker['quoteVolume'],  # Volume em USDT
        'change': ticker['percentage']
    }
```

### Buscar Candles
```python
async def fetch_ohlcv(self, symbol, timeframe, limit=100):
    """
    Busca dados históricos OHLCV
    Timeframes: 1m, 5m, 15m, 30m, 1h, 2h, 4h, 1d
    """
    candles = await self.exchange.fetch_ohlcv(
        symbol, 
        timeframe, 
        limit=limit
    )
    return [
        {
            'timestamp': candle[0],
            'open': candle[1],
            'high': candle[2],
            'low': candle[3],
            'close': candle[4],
            'volume': candle[5]
        }
        for candle in candles
    ]
```

## 💹 APIs de Trading

### Consultar Saldo
```python
async def fetch_balance(self):
    """
    Retorna saldo da conta
    """
    balance = await self.exchange.fetch_balance()
    return {
        'USDT': {
            'free': balance['USDT']['free'],
            'used': balance['USDT']['used'],
            'total': balance['USDT']['total']
        },
        # Outros ativos conforme necessário
    }
```

### Criar Ordem Market
```python
async def create_market_order(self, symbol, side, amount):
    """
    Cria ordem a mercado
    side: 'buy' ou 'sell'
    """
    try:
        order = await self.exchange.create_market_order(
            symbol=symbol,
            side=side,
            amount=amount
        )
        return {
            'id': order['id'],
            'symbol': order['symbol'],
            'side': order['side'],
            'price': order['average'],
            'amount': order['amount'],
            'cost': order['cost'],
            'status': order['status'],
            'timestamp': order['timestamp']
        }
    except Exception as e:
        raise TradingAPIError(f"Erro ao criar ordem: {str(e)}")
```

### Criar Ordem Limit (Stop Loss)
```python
async def create_stop_loss_order(self, symbol, side, amount, stop_price):
    """
    Cria ordem stop loss
    """
    order = await self.exchange.create_order(
        symbol=symbol,
        type='stop_market',
        side=side,
        amount=amount,
        stopPrice=stop_price,
        params={'stopLossPrice': stop_price}
    )
    return order
```

### Cancelar Ordem
```python
async def cancel_order(self, order_id, symbol):
    """
    Cancela ordem existente
    """
    return await self.exchange.cancel_order(order_id, symbol)
```

### Buscar Status da Ordem
```python
async def fetch_order(self, order_id, symbol):
    """
    Busca detalhes de uma ordem
    """
    order = await self.exchange.fetch_order(order_id, symbol)
    return {
        'id': order['id'],
        'status': order['status'],
        'filled': order['filled'],
        'remaining': order['remaining'],
        'average': order['average'],
        'trades': order['trades']
    }
```

## 🔄 WebSocket Streams

### Stream de Preços
```python
async def subscribe_ticker(self, symbol, callback):
    """
    Inscreve para atualizações de preço em tempo real
    """
    await self.ws_client.subscribe_ticker(
        symbol=symbol,
        callback=callback
    )
```

### Stream de Trades
```python
async def subscribe_trades(self, symbol, callback):
    """
    Inscreve para trades executados
    """
    await self.ws_client.subscribe_trades(
        symbol=symbol,
        callback=callback
    )
```

## ⚡ Rate Limiting

### BingX Rate Limits (Updated 2024)
- **Market Interfaces**: 100 requests per 10 seconds per IP
- **Account Interfaces**: 1,000 requests per 10 seconds per IP

```python
# Implementação conservadora dos novos limites
RATE_LIMITS = {
    # Market data endpoints (100 req/10s = 10 req/s max)
    'fetch_ticker': 8,       # 8 por segundo (conservativo)
    'fetch_ohlcv': 8,        # 8 por segundo (conservativo)
    'fetch_markets': 5,      # 5 por segundo (menos frequente)
    'fetch_orderbook': 8,    # 8 por segundo (conservativo)
    
    # Account endpoints (1000 req/10s = 100 req/s max)
    'create_order': 50,      # 50 por segundo (conservativo)
    'cancel_order': 50,      # 50 por segundo (conservativo)
    'fetch_balance': 20,     # 20 por segundo (conservativo)
    'fetch_order_status': 30,# 30 por segundo (conservativo)
    'fetch_open_orders': 20, # 20 por segundo (conservativo)
}
```

## 🚨 Tratamento de Erros

### Erros Comuns
```python
class APIErrorHandler:
    @staticmethod
    def handle_error(error):
        if isinstance(error, ccxt.NetworkError):
            # Erro de rede - retry
            return "RETRY"
        elif isinstance(error, ccxt.ExchangeError):
            # Erro da exchange
            if "Insufficient balance" in str(error):
                return "INSUFFICIENT_BALANCE"
            elif "Order not found" in str(error):
                return "ORDER_NOT_FOUND"
        elif isinstance(error, ccxt.RateLimitError):
            # Rate limit excedido
            return "RATE_LIMIT"
        return "UNKNOWN_ERROR"
```

### Retry Strategy
```python
async def execute_with_retry(self, func, *args, max_retries=3):
    """
    Executa função com retry automático
    """
    for attempt in range(max_retries):
        try:
            return await func(*args)
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # Backoff exponencial
```

## 🔌 Integração com Sistema

- **Scanner**: Fornece dados de mercado
- **Trading**: Executa ordens
- **Database**: Armazena histórico
- **Frontend**: Envia atualizações via WebSocket

## 🧪 Testes

```bash
python -m pytest tests/test_api.py
```

## 📊 Monitoramento

- Log de todas as requisições
- Métricas de latência
- Taxa de erro por endpoint
- Uso de rate limit