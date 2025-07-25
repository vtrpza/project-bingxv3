# 🤖 Bot de Trading BingX - Documentação Principal

## 📋 Visão Geral

Sistema automatizado de trading para a corretora BingX com escaneamento de ativos, análise técnica em tempo real e gestão automatizada de risco. Deploy principal no Render: https://bingx-trading-bot-3i13.onrender.com/

## 🏗️ Arquitetura do Sistema

### Componentes Principais

1. **API Server** (`api/`)
   - FastAPI com endpoints REST
   - WebSocket para atualizações em tempo real
   - Integração CCXT com BingX
   - Health checks e monitoramento

2. **Scanner de Ativos** (`scanner/`)
   - Escaneamento inicial para validação
   - Escaneamento individual contínuo
   - Análise de indicadores técnicos
   - Progresso em tempo real via WebSocket

3. **Motor de Trading** (`trading/`)
   - Execução de ordens
   - Gestão de stop loss e take profit
   - Controle de posições abertas

4. **Análise Técnica** (`analysis/`)
   - Cálculo de médias móveis (MM1, Center)
   - RSI (Índice de Força Relativa)
   - Análise de volume

5. **Interface Web** (`frontend/`)
   - Dashboard com 3 abas (PyScript)
   - Visualização em tempo real
   - Controles de trading
   - Otimização de inicialização

6. **Banco de Dados** (`database/`)
   - PostgreSQL para produção (Render)
   - SQLite para desenvolvimento local
   - Cache de dados de mercado
   - Histórico de trades

## 📁 Estrutura de Diretórios

```
project-bingxv3/
├── api/                 # API Server (FastAPI)
│   ├── __main__.py      # Entry point para Render
│   ├── web_api.py       # Endpoints REST e WebSocket
│   └── client.py        # Cliente BingX (CCXT)
├── scanner/             # Módulo de escaneamento
│   ├── initial_scanner.py # Scanner com progresso em tempo real
│   └── enhanced_worker.py # Worker otimizado
├── trading/             # Motor de execução de trades
├── analysis/            # Análise técnica
├── database/            # Modelos e migrações
│   └── connection.py    # Gestão de conexões DB
├── frontend/            # Interface PyScript
│   ├── index.html       # Dashboard otimizado
│   └── static/js/       # API client e componentes
├── config/              # Configurações
├── utils/               # Utilidades comuns
├── tests/               # Testes automatizados
├── docs/                # Documentação adicional
├── requirements.txt     # Dependências Python
├── render.yaml          # Configuração Render
├── render_health_check.py # Diagnóstico Render
├── render_debug.py      # Debug deployment
├── startup_test.py      # Teste de inicialização
├── main.py              # Bot completo (local)
└── .env.example         # Variáveis de ambiente
```

## 🚀 Funcionalidades Principais

### 1. Escaneamento Inicial
- Separa ativos válidos e inválidos
- Critério por volume de negociação
- Lista persistente de validação

### 2. Escaneamento Individual
- Monitoramento contínuo de ativos válidos
- Indicadores em tempo real (spot, 2h, 4h)
- Detecção automática de sinais

### 3. Regras de Trading

#### Regra 1: Cruzamento de Médias
- MM1 cruza Center (2h ou 4h)
- RSI entre 35 e 73
- Execução: ordem a mercado

#### Regra 2: Distância das Médias
- MM1 ≥ 2% da Center (2h) ou ≥ 3% (4h)
- Sem consulta ao RSI
- Execução: ordem a mercado

#### Regra 3: Volume Súbito
- Aumento expressivo de volume
- Direção: MM1 > Center = Compra, MM1 < Center = Venda
- Execução: ordem a mercado

### 4. Gestão de Risco
- Stop Loss inicial: ±2%
- Trailing Stop: ativa em +1.5% (breakeven)
- Take Profit progressivo: 3%, 5%, etc.

## 🛠️ Stack Tecnológica

### Backend
- **Python**: 3.11+
- **Framework**: FastAPI com WebSocket
- **API Exchange**: CCXT (BingX)
- **Banco de Dados**: PostgreSQL (prod) / SQLite (dev)
- **Deploy**: Render (multi-service)

### Frontend
- **Framework**: PyScript
- **API Client**: Fetch com fallback
- **Real-time**: WebSocket + polling fallback
- **UI**: Responsive CSS Grid

### Infraestrutura
- **Deploy**: Render.com
- **Monitoring**: Health checks
- **Logs**: Structured logging
- **Caching**: Redis (planned)

## 🚀 Deploy no Render

### URL de Produção
**https://bingx-trading-bot-3i13.onrender.com/**

### Configuração Render
- **Main Service**: Web server (FastAPI)
- **Workers**: Scanner, Analysis, Maintenance
- **Database**: PostgreSQL
- **Redis**: Para cache (opcional)

### Variáveis de Ambiente Obrigatórias
```bash
# BingX API
BINGX_API_KEY=your_api_key
BINGX_SECRET_KEY=your_secret_key

# Database (auto-configurado pelo Render)
DATABASE_URL=postgresql://...

# Server (auto-configurado pelo Render)
PORT=10000
HOST=0.0.0.0
```

### Entry Points
```yaml
# render.yaml
services:
  - type: web
    name: bingx-trading-bot
    startCommand: python -m api  # Usa api/__main__.py
    healthCheckPath: /health
    
  - type: worker
    name: bingx-scanner-worker
    startCommand: python -m scanner.enhanced_worker
```

## 🔧 Desenvolvimento Local

### Configuração Inicial
```bash
# Clone e instale dependências
git clone <repo>
cd project-bingxv3
pip install -r requirements.txt

# Configure variáveis de ambiente
cp .env.example .env
# Edite .env com suas credenciais

# Rode localmente
python -m api  # API server apenas
# ou
python main.py  # Bot completo
```

### Testes e Diagnóstico
```bash
# Teste de inicialização
python startup_test.py

# Health check local
python render_health_check.py

# Debug completo
python render_debug.py

# Testes unitários
python -m pytest tests/
```

## 📊 Monitoramento e Logs

### Health Check
- **Endpoint**: `/health`
- **Status**: Verifica DB, API, componentes
- **Response**: JSON com status detalhado

### Logs Estruturados
- **Format**: JSON + timestamp
- **Levels**: DEBUG, INFO, WARNING, ERROR
- **Locations**: `/var/log/` (Render)

### Performance Metrics
- **API Response Time**: < 200ms
- **WebSocket Latency**: < 50ms  
- **Database Queries**: < 100ms
- **Scanner Speed**: ~10s para 1000+ ativos

## 🚨 Troubleshooting

### Problemas Comuns

#### 502 Bad Gateway (Render)
```bash
# Verificar logs de build e runtime no Render
# Testar localmente:
python render_health_check.py
python -m api
```

#### WebSocket não conecta
- Fallback automático para polling
- Verifica CORS e protocolo (ws/wss)
- Logs no browser console

#### Scanner lento/travado
- Progress bar com atualizações em tempo real
- Logs detalhados no backend
- Rate limiting automático

#### Database connection issues
```bash
# Verificar DATABASE_URL
echo $DATABASE_URL

# Testar conexão
python -c "from database.connection import init_database; print(init_database())"
```

### Scripts de Diagnóstico
- `render_health_check.py`: Teste rápido de componentes
- `render_debug.py`: Diagnóstico completo do ambiente
- `startup_test.py`: Teste de inicialização

## 🔒 Segurança

### Credenciais
- **Nunca** commitar API keys
- Usar variáveis de ambiente sempre
- Render dashboard para configuração segura

### Validação
- Inputs sanitizados
- Rate limiting nas APIs
- Logs de auditoria detalhados

### CORS
- Configurado para domínio específico
- WebSocket com origem validada
- Headers de segurança

## 📈 Performance

### Otimizações Aplicadas
- **Dashboard init**: Endpoint consolidado (`/api/dashboard/init`)
- **API calls**: Batch requests quando possível
- **WebSocket**: Real-time com fallback inteligente
- **Database**: Connection pooling
- **Scanner**: Progress em tempo real
- **Frontend**: Loading states otimizados

### Métricas Target
- **Page Load**: < 3s
- **API Response**: < 200ms
- **WebSocket Reconnect**: < 5s
- **Scanner Progress**: Updates em 1s
- **Database Queries**: < 100ms