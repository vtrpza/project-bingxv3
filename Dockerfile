FROM python:3.11-slim

# Metadados
LABEL maintainer="BingX Trading Bot"
LABEL version="1.0.0"
LABEL description="Bot de trading automatizado para BingX"

# Variáveis de ambiente
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Diretório de trabalho
WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primeiro para cache
COPY requirements.txt .

# Instalar dependências Python
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copiar código da aplicação
COPY . .

# Criar diretórios necessários
RUN mkdir -p /app/logs /app/data

# Usuário não-root
RUN useradd -m -u 1000 trader && \
    chown -R trader:trader /app

USER trader

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health')"

# Expor portas
EXPOSE 8080 8081

# Comando padrão
CMD ["python", "main.py"]