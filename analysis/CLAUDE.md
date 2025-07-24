# 📊 Módulo Analysis - Documentação

## 📋 Visão Geral

O módulo Analysis é responsável por calcular todos os indicadores técnicos utilizados pelo bot, incluindo médias móveis, RSI e análise de volume.

## 🏗️ Arquitetura

### Componentes

1. **TechnicalIndicators** (`indicators.py`)
   - Cálculo de médias móveis (MM1, Center)
   - RSI (Relative Strength Index)
   - Detecção de cruzamentos

2. **VolumeAnalyzer** (`volume.py`)
   - Análise de volume em tempo real
   - Detecção de spikes de volume
   - Cálculo de volume médio

3. **SignalGenerator** (`signals.py`)
   - Combina indicadores para gerar sinais
   - Aplica regras de trading
   - Determina força do sinal

## 📊 Indicadores Técnicos

### MM1 (Média Móvel Rápida)
```python
# EMA de 9 períodos
def calculate_mm1(candles, period=9):
    """
    Calcula média móvel exponencial rápida
    Mais responsiva a mudanças de preço
    """
    return ta.ema(candles['close'], period)
```

### Center (Média Móvel Central)
```python
# EMA de 21 períodos
def calculate_center(candles, period=21):
    """
    Calcula média móvel exponencial central
    Linha de tendência principal
    """
    return ta.ema(candles['close'], period)
```

### RSI (Índice de Força Relativa)
```python
# RSI de 14 períodos
def calculate_rsi(candles, period=14):
    """
    Calcula RSI para identificar sobrecompra/sobrevenda
    Valores: 0-100
    """
    return ta.rsi(candles['close'], period)
```

### Análise de Volume
```python
def detect_volume_spike(current_volume, avg_volume, threshold=2.0):
    """
    Detecta aumento súbito de volume
    Spike = volume atual > média * threshold
    """
    return current_volume > (avg_volume * threshold)
```

## 🔄 Fluxo de Análise

### 1. Coleta de Dados
```python
# Timeframes analisados
TIMEFRAMES = {
    "spot": "1m",   # Tempo real
    "2h": "2h",     # Médio prazo
    "4h": "4h"      # Longo prazo
}
```

### 2. Cálculo de Indicadores
```python
indicators = {
    "mm1_spot": calculate_mm1(candles_1m),
    "center_spot": calculate_center(candles_1m),
    "rsi_spot": calculate_rsi(candles_1m),
    "mm1_2h": calculate_mm1(candles_2h),
    "center_2h": calculate_center(candles_2h),
    "rsi_2h": calculate_rsi(candles_2h),
    "mm1_4h": calculate_mm1(candles_4h),
    "center_4h": calculate_center(candles_4h),
    "rsi_4h": calculate_rsi(candles_4h)
}
```

### 3. Detecção de Sinais

#### Cruzamento de Médias
```python
def detect_ma_crossover(mm1_prev, mm1_curr, center_prev, center_curr):
    """
    Detecta cruzamento da MM1 com Center
    Bull cross: MM1 cruza Center de baixo para cima
    Bear cross: MM1 cruza Center de cima para baixo
    """
    if mm1_prev <= center_prev and mm1_curr > center_curr:
        return "BULLISH_CROSS"
    elif mm1_prev >= center_prev and mm1_curr < center_curr:
        return "BEARISH_CROSS"
    return None
```

#### Distância entre Médias
```python
def calculate_ma_distance(mm1, center):
    """
    Calcula distância percentual entre médias
    """
    return abs(mm1 - center) / center
```

## ⚙️ Configurações

```python
ANALYSIS_CONFIG = {
    "MM1_PERIOD": 9,
    "CENTER_PERIOD": 21,
    "RSI_PERIOD": 14,
    "RSI_OVERSOLD": 35,
    "RSI_OVERBOUGHT": 73,
    "VOLUME_SPIKE_THRESHOLD": 2.0,
    "MA_DISTANCE_2H": 0.02,  # 2%
    "MA_DISTANCE_4H": 0.03   # 3%
}
```

## 📈 Geração de Sinais

### Sinal de Compra
```python
signal = "BUY" if any([
    # Regra 1: Cruzamento + RSI
    (bullish_cross_2h or bullish_cross_4h) and (35 <= rsi <= 73),
    # Regra 2: Distância das médias
    mm1_distance_2h >= 0.02 or mm1_distance_4h >= 0.03,
    # Regra 3: Volume + Direção
    volume_spike and mm1 > center
])
```

### Sinal de Venda
```python
signal = "SELL" if any([
    # Regra 1: Cruzamento + RSI
    (bearish_cross_2h or bearish_cross_4h) and (35 <= rsi <= 73),
    # Regra 2: Distância das médias (inversa)
    mm1_distance_2h >= 0.02 or mm1_distance_4h >= 0.03,
    # Regra 3: Volume + Direção
    volume_spike and mm1 < center
])
```

## 🔌 Integração

- **Scanner**: Fornece dados de mercado
- **Trading**: Recebe sinais processados
- **Database**: Armazena histórico de indicadores

## 📊 Estrutura de Dados

### AnalysisResult
```python
{
    "symbol": "BTC/USDT",
    "timestamp": "2024-01-20T10:30:00Z",
    "indicators": {
        "spot": {...},
        "2h": {...},
        "4h": {...}
    },
    "signals": {
        "primary": "BUY",
        "strength": 0.85,
        "rules_triggered": ["crossover_2h", "volume_spike"]
    },
    "volume_analysis": {
        "current": 150000,
        "average": 75000,
        "spike_detected": true
    }
}
```

## 🧪 Testes

```bash
python -m pytest tests/test_analysis.py
```

## 🚨 Validações

- Dados suficientes para cálculo
- Valores dentro de ranges esperados
- Consistência temporal dos dados
- Tratamento de gaps nos candles