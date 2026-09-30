# Imagem base oficial do Python slim (leve e estavel)
FROM python:3.11-slim

# Evita geracao de arquivos .pyc e garante saida de logs imediata no console do Render
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    TORCH_NUM_THREADS=2 \
    MAX_IMAGE_DIMENSION=1280 \
    EASYOCR_QUANTIZE=True

# Dependencias do sistema operacional necessarias para OpenCV e Pillow
RUN apt-get update && apt-get install --no-install-recommends -y \
    libgl1 \
    libglib2.0-0 \
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

# Pre-baixa e armazena em cache os pesos dos modelos EasyOCR durante o build do Docker.
# Isso evita que o Render tente baixar arquivos pesados na inicializacao (cold start) ou atinja timeout.
RUN python -c "import easyocr; easyocr.Reader(['en'], gpu=False, quantize=True)"

# Copia o codigo da aplicacao
COPY app/ ./app/

# Expoe a porta padrao (o Render sobrescreve via variavel de ambiente $PORT)
EXPOSE 8000

# Executa Uvicorn escutando na porta dinamica $PORT fornecida pelo Render
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
