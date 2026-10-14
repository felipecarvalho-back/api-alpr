import os
import modal

# 1. Definicao da imagem no container Linux do Modal
# Instala as dependencias do sistema necessarias para OpenCV e o PyTorch otimizado com EasyOCR
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1", "libglib2.0-0")
    .pip_install(
        "fastapi>=0.110.0",
        "uvicorn[standard]>=0.28.0",
        "python-multipart>=0.0.9",
        "pillow>=10.0.0",
        "numpy>=1.24.0",
        "opencv-python-headless>=4.8.0",
        "pydantic>=2.0.0",
        "pyjwt>=2.8.0",
    )
    # PyTorch compilado apenas para CPU (mais leve e suficiente para boa performance)
    .pip_install(
        "torch",
        "torchvision",
        extra_index_url="https://download.pytorch.org/whl/cpu",
    )
    .pip_install("easyocr>=1.7.0")
    # Pre-baixa e armazena os modelos EasyOCR no cache da imagem durante o build
    # Isso evita cold-starts demorados na primeira requisicao HTTP
    .run_commands(
        "python -c \"import easyocr; easyocr.Reader(['pt', 'en'], gpu=False, quantize=False)\""
    )
    .add_local_python_source("app")
)

# 2. Inicializacao da aplicacao no Modal
app = modal.App("api-placas", image=image)

# 3. Configuracao do endpoint FastAPI ASGI
@app.function(
    memory=2048,           # 2GB de RAM (folga ampla para processamento de tensores)
    cpu=2.0,               # 2 vCPUs dedicadas
    scaledown_window=300,  # Mantem a instancia ativa por 5 minutos apos a ultima chamada
)
@modal.asgi_app()
def fastapi_app():
    from app.main import app as web_app
    return web_app
