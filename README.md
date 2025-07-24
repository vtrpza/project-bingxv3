# 🤖 Bot de Trading BingX

Sistema automatizado de trading para a corretora BingX com análise técnica em tempo real e gestão automatizada de risco.

## 🚀 Características Principais

- ✅ Escaneamento automático de ativos válidos
- 📊 Análise técnica multi-timeframe (spot, 2h, 4h)
- 🎯 3 estratégias de entrada automatizadas
- 🛡️ Gestão de risco com trailing stop progressivo
- 🖥️ Interface web em tempo real com PyScript
- 📈 Integração completa com BingX via CCXT
- 🐘 Persistência em PostgreSQL
- 🚀 Pronto para deploy no Render

## 📋 Requisitos

- Python 3.11+
- PostgreSQL 14+
- Conta BingX com API habilitada
- Redis (opcional, para cache)

## 🛠️ Instalação Local

1. Clone o repositório:
```bash
git clone https://github.com/seu-usuario/bingx-trading-bot.git
cd bingx-trading-bot
```

2. Configure as variáveis de ambiente:
```bash
cp .env.example .env
# Edite .env com suas credenciais
```

3. Instale as dependências:
```bash
pip install -r requirements.txt
```

4. Configure o banco de dados:
```bash
python -m alembic upgrade head
```

5. Execute o bot:
```bash
python main.py
```

## 🐳 Docker

```bash
docker-compose up -d
```

## 📊 Estratégias de Trading

### 1. Cruzamento de Médias + RSI
- MM1 cruza Center (2h ou 4h)
- RSI entre 35 e 73

### 2. Distância entre Médias
- MM1 ≥ 2% da Center (2h)
- MM1 ≥ 3% da Center (4h)

### 3. Spike de Volume
- Aumento súbito de volume
- Direção baseada em MM1 vs Center

## 🛡️ Gestão de Risco

- Stop Loss inicial: 2%
- Trailing Stop progressivo:
  - +1.5% → Breakeven
  - +3.0% → SL +1.5%
  - +5.0% → SL +3.0%

## 🖥️ Interface

Acesse `http://localhost:8080` após iniciar o bot.

### Abas Disponíveis:
1. **Validação**: Lista de ativos válidos/inválidos
2. **Escaneamento**: Monitoramento em tempo real
3. **Trades**: Posições abertas e gestão

## 📚 Documentação

- [Arquitetura do Sistema](CLAUDE.md)
- [Fluxo de Trading](docs/trading_flow.md)
- [Documentação dos Módulos](*/CLAUDE.md)

## ⚠️ Avisos Importantes

- **OPERE POR SUA CONTA E RISCO**
- Este bot é para fins educacionais
- Sempre teste em conta demo primeiro
- Monitore ativamente suas posições
- Configure limites de perda adequados

## 📝 Licença

MIT License - veja LICENSE para detalhes.

## 🤝 Contribuições

Contribuições são bem-vindas! Por favor, leia CONTRIBUTING.md primeiro.

## 📞 Suporte

Para dúvidas e suporte, abra uma issue no GitHub.