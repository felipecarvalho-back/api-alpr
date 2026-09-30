# Imagem base oficial do Python slim (leve e estavel)
FROM python:3.11-slim

# Otimizacoes criticas de memoria para o plano gratuito do Render (512MB RAM):
# - jemalloc + MALLOC_ARENA_MAX=2: eliminam a fragmentacao de memoria do glibc padrao no Linux
# - TORCH_NUM_THREADS=1: evita a multiplicacao de buffers de memoria por threads concorrentes
# - MAX_IMAGE_DIMENSION=960: mantem tensores do detector CRAFT abaixo de 35MB
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    MALLOC_ARENA_MAX=2 \
    LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libjemalloc.so.2 \
    TORCH_NUM_THREADS=1 \
    MAX_IMAGE_DIMENSION=960

# Dependencias do sistema operacional necessarias para OpenCV, Pillow e o alocador jemalloc
RUN apt-get update && apt-get install --no-install-recommends -y \
    libgl1 \
    libglib2.0-0 \
    libjemalloc2 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia os requisitos
COPY requirements.txt .

# 1. Instala PyTorch compilado apenas para CPU (reduz o tamanho da imagem de ~4GB para ~500MB)
# 2. Instala as demais dependencias sem cache para otimizar espaco
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Pre-baixa e armazena em cache os modelos CRAFT e latin_g2 durante o build do Docker.
RUN python -c "import easyocr; easyocr.Reader(['pt', 'en'], gpu=False, quantize=False)"

# Copia o codigo da aplicacao
COPY app/ ./app/

# Expoe a porta padrao (sobrescrita pelo Render via $PORT)
EXPOSE 8000

# Executa Uvicorn escutando na porta $PORT fornecida pelo Render
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
