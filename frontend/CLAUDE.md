# 🖥️ Módulo Frontend - Interface PyScript

## 📋 Visão Geral

Interface web desenvolvida em PyScript que fornece visualização em tempo real do bot de trading através de 3 abas principais: Validação, Escaneamento e Trades.

## 🏗️ Arquitetura

### Estrutura de Arquivos
```
frontend/
├── index.html          # Página principal
├── static/
│   ├── css/
│   │   └── styles.css  # Estilos da aplicação
│   └── js/
│       └── app.py      # Lógica PyScript
├── components/         # Componentes reutilizáveis
│   ├── validation_tab.py
│   ├── scanner_tab.py
│   └── trades_tab.py
└── services/          # Comunicação com backend
    └── api_client.py
```

## 🎨 Layout da Interface

### Estrutura HTML Principal
```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Bot Trading BingX</title>
    <link rel="stylesheet" href="https://pyscript.net/releases/2024.1.1/core.css">
    <script type="module" src="https://pyscript.net/releases/2024.1.1/core.js"></script>
    <link rel="stylesheet" href="static/css/styles.css">
</head>
<body>
    <py-config>
        packages = ["pandas", "plotly", "asyncio"]
        [[fetch]]
        from = "./static/js/"
        files = ["app.py"]
    </py-config>
    
    <div id="app">
        <!-- Conteúdo carregado via PyScript -->
    </div>
    
    <py-script src="./static/js/app.py"></py-script>
</body>
</html>
```

## 📑 Aba 1: Validação de Ativos

### Funcionalidades
- Lista de todos os ativos escaneados
- Separação entre válidos e inválidos
- Data/hora da última validação
- Botão para forçar revalidação

### Estrutura de Dados
```python
validation_data = {
    "valid_assets": [
        {
            "symbol": "BTC/USDT",
            "volume_24h": 1500000000,
            "last_validation": "2024-01-20 10:30:00",
            "criteria_met": {
                "volume": True,
                "active": True,
                "spread": True
            }
        }
    ],
    "invalid_assets": [
        {
            "symbol": "XYZ/USDT",
            "reason": "Volume insuficiente",
            "volume_24h": 50000,
            "last_check": "2024-01-20 10:30:00"
        }
    ]
}
```

### Interface
```python
def render_validation_tab():
    return f"""
    <div class="validation-tab">
        <h2>Validação de Ativos</h2>
        
        <div class="stats-row">
            <div class="stat-card">
                <h3>Ativos Válidos</h3>
                <span class="stat-value">{len(valid_assets)}</span>
            </div>
            <div class="stat-card">
                <h3>Ativos Inválidos</h3>
                <span class="stat-value">{len(invalid_assets)}</span>
            </div>
            <div class="stat-card">
                <h3>Última Validação</h3>
                <span class="stat-value">{last_validation}</span>
            </div>
        </div>
        
        <div class="assets-grid">
            <div class="valid-assets">
                <h3>✅ Ativos Válidos</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Símbolo</th>
                            <th>Volume 24h</th>
                            <th>Validado em</th>
                        </tr>
                    </thead>
                    <tbody>{render_valid_assets()}</tbody>
                </table>
            </div>
            
            <div class="invalid-assets">
                <h3>❌ Ativos Inválidos</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Símbolo</th>
                            <th>Motivo</th>
                            <th>Verificado em</th>
                        </tr>
                    </thead>
                    <tbody>{render_invalid_assets()}</tbody>
                </table>
            </div>
        </div>
        
        <button onclick="force_revalidation()">🔄 Forçar Revalidação</button>
    </div>
    """
```

## 📈 Aba 2: Escaneamento Individual

### Funcionalidades
- Dados em tempo real dos ativos válidos
- Indicadores para spot, 2h e 4h
- Sinalização visual de oportunidades
- Controle de número máximo de trades

### Estrutura de Dados
```python
scan_data = {
    "BTC/USDT": {
        "timestamp": "2024-01-20 10:35:45",
        "spot": {
            "price": 42150.50,
            "mm1": 42100.00,
            "center": 42050.00,
            "rsi": 58.5
        },
        "2h": {
            "price": 42000.00,
            "mm1": 41950.00,
            "center": 41900.00,
            "rsi": 55.2,
            "candle": "🟢"  # Verde/Vermelho
        },
        "4h": {
            "price": 41800.00,
            "mm1": 41750.00,
            "center": 41700.00,
            "rsi": 52.8,
            "candle": "🔴"
        },
        "signal": "COMPRA",
        "signal_strength": 0.85
    }
}
```

### Interface
```python
def render_scanner_tab():
    return f"""
    <div class="scanner-tab">
        <h2>Escaneamento Individual</h2>
        
        <div class="controls">
            <label>Máximo de Trades Simultâneos:</label>
            <input type="number" id="max-trades" value="5" min="1" max="20">
            <span>Trades Ativos: {active_trades}/{max_trades}</span>
        </div>
        
        <div class="scanner-grid">
            {render_asset_cards()}
        </div>
    </div>
    """

def render_asset_card(symbol, data):
    signal_class = "buy" if data["signal"] == "COMPRA" else "sell" if data["signal"] == "VENDA" else "neutral"
    
    return f"""
    <div class="asset-card {signal_class}">
        <div class="card-header">
            <h3>{symbol}</h3>
            <span class="timestamp">{data["timestamp"]}</span>
        </div>
        
        <div class="indicators-grid">
            <div class="timeframe">
                <h4>Spot</h4>
                <div>Preço: ${data["spot"]["price"]}</div>
                <div>MM1: ${data["spot"]["mm1"]}</div>
                <div>Center: ${data["spot"]["center"]}</div>
                <div>RSI: {data["spot"]["rsi"]}</div>
            </div>
            
            <div class="timeframe">
                <h4>2H {data["2h"]["candle"]}</h4>
                <div>Preço: ${data["2h"]["price"]}</div>
                <div>MM1: ${data["2h"]["mm1"]}</div>
                <div>Center: ${data["2h"]["center"]}</div>
                <div>RSI: {data["2h"]["rsi"]}</div>
            </div>
            
            <div class="timeframe">
                <h4>4H {data["4h"]["candle"]}</h4>
                <div>Preço: ${data["4h"]["price"]}</div>
                <div>MM1: ${data["4h"]["mm1"]}</div>
                <div>Center: ${data["4h"]["center"]}</div>
                <div>RSI: {data["4h"]["rsi"]}</div>
            </div>
        </div>
        
        <div class="signal-indicator">
            <span class="signal-type">{data["signal"]}</span>
            <span class="signal-strength">Força: {data["signal_strength"]*100:.0f}%</span>
        </div>
    </div>
    """
```

## 💰 Aba 3: Trades Ativos

### Funcionalidades
- Lista de todos os trades abertos
- Monitoramento de P&L em tempo real
- Status de stop loss e trailing
- Indicadores de próximos alvos

### Estrutura de Dados
```python
trades_data = [
    {
        "id": "uuid-1234",
        "symbol": "BTC/USDT",
        "side": "COMPRA",
        "entry_price": 42000.00,
        "current_price": 42630.00,
        "quantity": 0.01,
        "stop_loss": 41160.00,
        "stop_loss_status": "BREAKEVEN",
        "pnl": 6.30,
        "pnl_percentage": 1.5,
        "next_target": {
            "price": 43260.00,
            "percentage": 3.0,
            "new_stop": 42630.00
        },
        "duration": "00:45:30"
    }
]
```

### Interface
```python
def render_trades_tab():
    return f"""
    <div class="trades-tab">
        <h2>Trades Ativos</h2>
        
        <div class="summary-row">
            <div class="summary-card">
                <h3>Total P&L</h3>
                <span class="{pnl_class}">${total_pnl:.2f}</span>
            </div>
            <div class="summary-card">
                <h3>Taxa de Sucesso</h3>
                <span>{win_rate:.1f}%</span>
            </div>
            <div class="summary-card">
                <h3>Trades Hoje</h3>
                <span>{trades_today}</span>
            </div>
        </div>
        
        <table class="trades-table">
            <thead>
                <tr>
                    <th>Ativo</th>
                    <th>Operação</th>
                    <th>Entrada</th>
                    <th>Atual</th>
                    <th>P&L</th>
                    <th>Stop Loss</th>
                    <th>Status SL</th>
                    <th>Próximo Alvo</th>
                    <th>Duração</th>
                    <th>Ações</th>
                </tr>
            </thead>
            <tbody>
                {render_trade_rows()}
            </tbody>
        </table>
    </div>
    """

def render_trade_row(trade):
    pnl_class = "profit" if trade["pnl"] > 0 else "loss"
    
    return f"""
    <tr>
        <td>{trade["symbol"]}</td>
        <td class="{trade["side"].lower()}">{trade["side"]}</td>
        <td>${trade["entry_price"]:.2f}</td>
        <td>${trade["current_price"]:.2f}</td>
        <td class="{pnl_class}">
            ${trade["pnl"]:.2f} ({trade["pnl_percentage"]:.1f}%)
        </td>
        <td>${trade["stop_loss"]:.2f}</td>
        <td class="sl-status-{trade["stop_loss_status"].lower()}">
            {trade["stop_loss_status"]}
        </td>
        <td>
            ${trade["next_target"]["price"]:.2f} 
            ({trade["next_target"]["percentage"]:.1f}%)
        </td>
        <td>{trade["duration"]}</td>
        <td>
            <button onclick="close_trade('{trade["id"]}')">Fechar</button>
        </td>
    </tr>
    """
```

## 🔄 Atualização em Tempo Real

### WebSocket Connection
```python
class RealtimeUpdater:
    def __init__(self):
        self.ws_url = "ws://localhost:8000/ws"
        self.reconnect_interval = 5000
        
    async def connect(self):
        self.ws = await asyncio.create_connection(self.ws_url)
        await self.subscribe_channels()
        
    async def subscribe_channels(self):
        await self.ws.send(json.dumps({
            "action": "subscribe",
            "channels": ["validation", "scanner", "trades"]
        }))
        
    async def handle_message(self, message):
        data = json.loads(message)
        
        if data["channel"] == "scanner":
            update_scanner_display(data["payload"])
        elif data["channel"] == "trades":
            update_trades_display(data["payload"])
        elif data["channel"] == "validation":
            update_validation_display(data["payload"])
```

## 🎨 Estilos CSS

```css
/* Tema escuro para trading */
:root {
    --bg-primary: #0d1117;
    --bg-secondary: #161b22;
    --text-primary: #c9d1d9;
    --text-secondary: #8b949e;
    --accent-buy: #2ea043;
    --accent-sell: #f85149;
    --accent-neutral: #6e7681;
}

/* Cards responsivos */
.asset-card {
    background: var(--bg-secondary);
    border-radius: 8px;
    padding: 16px;
    margin: 8px;
    border: 2px solid transparent;
    transition: all 0.3s;
}

.asset-card.buy {
    border-color: var(--accent-buy);
}

.asset-card.sell {
    border-color: var(--accent-sell);
}

/* Tabelas */
.trades-table {
    width: 100%;
    border-collapse: collapse;
}

.trades-table th {
    background: var(--bg-secondary);
    padding: 12px;
    text-align: left;
}

/* Indicadores visuais */
.profit { color: var(--accent-buy); }
.loss { color: var(--accent-sell); }

/* Responsividade */
@media (max-width: 768px) {
    .scanner-grid {
        grid-template-columns: 1fr;
    }
}
```

## 🚨 Notificações

```python
def show_notification(title, message, type="info"):
    """
    Mostra notificação no canto da tela
    type: info, success, warning, error
    """
    notification_html = f"""
    <div class="notification notification-{type}">
        <h4>{title}</h4>
        <p>{message}</p>
    </div>
    """
    
    Element("notifications").element.innerHTML += notification_html
    
    # Auto-remove após 5 segundos
    setTimeout(lambda: remove_notification(), 5000)
```

## 🧪 Testes

```bash
python -m pytest tests/test_frontend.py
```