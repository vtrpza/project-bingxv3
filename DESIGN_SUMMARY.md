# 📐 Resumo do Design - Bot Trading BingX

## 🎯 Visão Geral do Sistema

Sistema completo de trading automatizado desenvolvido em Python com interface PyScript, integração real com BingX via CCXT, e deploy otimizado para Render.

## 🏗️ Arquitetura de Alto Nível

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│  Frontend       │────▶│   Backend API   │────▶│   BingX API     │
│  (PyScript)     │     │   (FastAPI)     │     │   (CCXT)        │
│                 │     │                 │     │                 │
└────────┬────────┘     └────────┬────────┘     └─────────────────┘
         │                       │
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│   WebSocket     │     │   PostgreSQL    │
│   (Real-time)   │     │   Database      │
└─────────────────┘     └─────────────────┘
```

## 📦 Estrutura Modular

### 1. **Scanner Module** (`/scanner`)
- **Responsabilidade**: Validação e monitoramento de ativos
- **Componentes**:
  - `initial_scanner.py`: Validação inicial por volume
  - `continuous_scanner.py`: Monitoramento contínuo
  - `validator.py`: Critérios de validação

### 2. **Trading Module** (`/trading`)
- **Responsabilidade**: Execução de trades e gestão de posições
- **Componentes**:
  - `engine.py`: Motor principal de trading
  - `order_manager.py`: Gerenciamento de ordens
  - `risk_manager.py`: Stop loss e trailing stop
  - `position_tracker.py`: Monitoramento de P&L

### 3. **Analysis Module** (`/analysis`)
- **Responsabilidade**: Cálculo de indicadores técnicos
- **Componentes**:
  - `indicators.py`: MM1, Center, RSI
  - `volume.py`: Análise de volume
  - `signals.py`: Geração de sinais

### 4. **API Module** (`/api`)
- **Responsabilidade**: Integração com BingX
- **Componentes**:
  - `client.py`: Cliente CCXT configurado
  - `market_data.py`: Dados de mercado
  - `trading.py`: Execução de ordens
  - `websocket.py`: Streams em tempo real

### 5. **Database Module** (`/database`)
- **Responsabilidade**: Persistência de dados
- **Modelos**:
  - Assets (ativos válidos/inválidos)
  - Market Data (histórico de preços)
  - Indicators (valores calculados)
  - Trades (operações executadas)
  - Orders (ordens enviadas)
  - Signals (sinais detectados)

### 6. **Frontend Module** (`/frontend`)
- **Responsabilidade**: Interface do usuário
- **Tecnologia**: PyScript (Python no browser)
- **Abas**:
  1. Validação de Ativos
  2. Escaneamento Individual
  3. Trades Ativos

## 🔄 Fluxos Principais

### Fluxo de Escaneamento
```
1. Buscar todos os pares USDT
2. Filtrar por volume mínimo (100k USDT)
3. Salvar lista de válidos
4. Iniciar monitoramento contínuo
```

### Fluxo de Trading
```
1. Detectar sinal (3 regras)
2. Verificar limite de trades
3. Calcular tamanho da posição
4. Executar ordem market
5. Configurar stop loss (-2%)
6. Monitorar e ajustar stops
```

### Regras de Entrada
1. **Cruzamento MA + RSI**: MM1 cruza Center com RSI 35-73
2. **Distância MA**: MM1 ≥2% (2h) ou ≥3% (4h) da Center
3. **Volume Spike**: Aumento súbito com direção das MAs

## 💾 Modelo de Dados

### Tabelas Principais
- `assets`: Ativos e status de validação
- `market_data`: Candles OHLCV
- `indicators`: Valores calculados
- `trades`: Operações executadas
- `orders`: Ordens na exchange
- `signals`: Sinais detectados

## 🚀 Configurações de Deploy

### Render Services
1. **Web Service**: Interface e API principal
2. **Scanner Worker**: Escaneamento contínuo
3. **Analysis Worker**: Cálculo de indicadores
4. **PostgreSQL**: Banco de dados
5. **Redis**: Cache (opcional)

### Variáveis de Ambiente Críticas
```env
BINGX_API_KEY=xxx
BINGX_SECRET_KEY=xxx
DATABASE_URL=postgresql://...
MAX_CONCURRENT_TRADES=5
POSITION_SIZE_PERCENT=2.0
```

## 🛡️ Segurança e Gestão de Risco

### Proteções Implementadas
- Stop loss obrigatório em todos os trades
- Limite máximo de trades simultâneos
- Tamanho máximo de posição (2% do saldo)
- Trailing stop progressivo automático
- Validação de saldo antes de operar
- Rate limiting nas chamadas API

### Monitoramento
- Logs estruturados para auditoria
- Métricas de performance em tempo real
- Alertas de erro e anomalias
- Backup automático do banco de dados

## 📊 Interface PyScript

### Características
- Atualização em tempo real via WebSocket
- 3 abas funcionais (Validação, Scanner, Trades)
- Tema escuro otimizado para trading
- Responsivo para mobile e desktop
- Notificações visuais de eventos

## 🧪 Testes e Qualidade

### Cobertura de Testes
- Testes unitários para cada módulo
- Testes de integração com mock da API
- Testes de stress para o scanner
- Validação de regras de trading

### Padrões de Código
- Type hints em todo o código
- Documentação em português
- Clean Code principles
- SOLID principles

## 📈 Métricas de Performance

### KPIs Monitorados
- Win Rate (taxa de acerto)
- Profit Factor
- Maximum Drawdown
- Average Trade Duration
- Risk/Reward Ratio

## 🔮 Próximos Passos Sugeridos

1. Implementar backtesting histórico
2. Adicionar mais indicadores técnicos
3. Machine Learning para otimização
4. App mobile nativo
5. Integração com mais exchanges

## ⚠️ Considerações Importantes

- Sistema projetado para trading real, sem mocks
- Toda comunicação é feita diretamente com BingX
- Requer monitoramento ativo do operador
- Não é recomendação de investimento
- Teste sempre em conta demo primeiro

---

**Status**: Design Completo ✅
**Pronto para**: Implementação
**Tecnologias**: Python, PyScript, PostgreSQL, CCXT, FastAPI, Docker, Render