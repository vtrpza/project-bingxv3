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

- **Backend**: Python 3.11+
- **Frontend**: PyScript
- **Banco de Dados**: PostgreSQL
- **API Exchange**: CCXT (BingX)
- **Deploy**: Render
- **Containerização**: Docker

## 📝 Configuração

Ver `config/CLAUDE.md` para detalhes de configuração.

## 🔒 Segurança

- Credenciais em variáveis de ambiente
- Validação de todas as operações
- Logs detalhados de auditoria

## 📊 Monitoramento

- Logs estruturados
- Métricas de performance
- Alertas de erro

## 🧪 Testes

```bash
python -m pytest tests/
```

## 🚀 Deploy

Ver `docs/deploy.md` para instruções de deploy no Render.