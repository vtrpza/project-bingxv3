# 🤖 Bot de Trading BingX - Documentação Principal

## 📋 Visão Geral

Sistema automatizado de trading para a corretora BingX com escaneamento de ativos, análise técnica em tempo real e gestão automatizada de risco.

## 🏗️ Arquitetura do Sistema

### Componentes Principais

1. **Scanner de Ativos** (`scanner/`)
   - Escaneamento inicial para validação
   - Escaneamento individual contínuo
   - Análise de indicadores técnicos

2. **Motor de Trading** (`trading/`)
   - Execução de ordens
   - Gestão de stop loss e take profit
   - Controle de posições abertas

3. **Análise Técnica** (`analysis/`)
   - Cálculo de médias móveis (MM1, Center)
   - RSI (Índice de Força Relativa)
   - Análise de volume

4. **Interface Web** (`frontend/`)
   - Dashboard com 3 abas (PyScript)
   - Visualização em tempo real
   - Controles de trading

5. **Banco de Dados** (`database/`)
   - PostgreSQL para persistência
   - Cache de dados de mercado
   - Histórico de trades

## 📁 Estrutura de Diretórios

```
project-bingxv3/
├── scanner/              # Módulo de escaneamento
├── trading/             # Motor de execução de trades
├── analysis/            # Análise técnica
├── database/            # Modelos e migrações
├── api/                 # Integração BingX via CCXT
├── frontend/            # Interface PyScript
├── config/              # Configurações
├── utils/               # Utilidades comuns
├── tests/               # Testes automatizados
├── docs/                # Documentação adicional
├── requirements.txt     # Dependências Python
├── docker-compose.yml   # Configuração Docker
├── .env.example         # Variáveis de ambiente
└── render.yaml          # Deploy no Render
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