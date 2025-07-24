# 🚀 Deploy no Render - Configuração de Produção

## Variáveis de Ambiente Obrigatórias no Render

Configure estas variáveis no dashboard do Render:

### 1. API BingX (OBRIGATÓRIAS)
```
BINGX_API_KEY=sua_chave_api_real
BINGX_SECRET_KEY=sua_chave_secreta_real
```

### 2. Performance Scanner (RECOMENDADAS)
```
USE_PARALLEL_SCANNER=true
SCAN_INTERVAL=10
MAX_ASSETS_TO_SCAN=1500
```

### 3. Trading (OPCIONAIS - já tem defaults)
```
MAX_CONCURRENT_TRADES=10
MIN_ORDER_SIZE_USDT=10.0
TRADING_ENABLED=true
PAPER_TRADING=false
```

### 4. Logs para Produção
```
LOG_LEVEL=ERROR
DEBUG=false
ENVIRONMENT=production
```

## ⚡ Otimizações Aplicadas

1. **Scanner Paralelo**: Ativado por padrão com WebSockets
2. **Rate Limiter**: 95% de utilização da API (9.5 req/s)
3. **Cache Inteligente**: TTLs otimizados por tipo de dado
4. **Batch Processing**: 50 assets simultâneos
5. **Scan Interval**: 10 segundos (máxima velocidade)

## 📊 Performance Esperada

- **Velocidade**: 2-3x mais rápido (0.03-0.05s por ativo)
- **Capacidade**: Até 1500 ativos monitorados
- **Latência**: Reduzida com WebSockets em tempo real
- **Eficiência**: 95% de uso da API vs 80% anterior

## 🔧 Comandos Úteis

### Ver logs em tempo real:
```bash
render logs --service bingx-scanner-worker --tail
```

### Restart do scanner:
```bash
render restart --service bingx-scanner-worker
```

## ✅ Checklist Pré-Deploy

- [ ] Configurar BINGX_API_KEY e BINGX_SECRET_KEY no Render
- [ ] Verificar que USE_PARALLEL_SCANNER=true
- [ ] Confirmar SCAN_INTERVAL=10
- [ ] Database já está configurado automaticamente
- [ ] Redis já está configurado automaticamente

## 🎯 Pronto para Deploy!

Faça o commit e push - o Render detectará automaticamente e fará o deploy com as novas otimizações de performance.