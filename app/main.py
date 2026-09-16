import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.ocr_service import ocr_service

# Configuracao de logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("api_placas")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Executa ao iniciar e ao encerrar a aplicacao."""
    logger.info("Inicializando servidor e pre-carregando modelo EasyOCR...")
    ocr_service.load_model()
    logger.info("API pronta para receber requisicoes!")
    yield
    logger.info("Encerrando API...")


app = FastAPI(
    title="API de Reconhecimento de Placas Veiculares",
    description="API para deteccao e extracao de placas brasileiras (Mercosul e Padrao Antigo) usando EasyOCR.",
    version="1.0.0",
    lifespan=lifespan
)

# Habilita CORS para permitir conexoes de aplicativos mobile (React Native, Flutter, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TextoDetectado(BaseModel):
    texto: str
    confianca: float
    bbox: List[List[int]]


class DadosPlaca(BaseModel):
    placa: Optional[str] = Field(None, description="Placa identificada sem caracteres especiais")
    placa_formatada: Optional[str] = Field(None, description="Placa formatada com traco se padrao antigo")
    padrao: Optional[str] = Field(None, description="'Mercosul' ou 'Antigo'")
    confianca: float = Field(..., description="Nivel de confianca do OCR na identificacao")
    todos_candidatos: List[Dict[str, Any]] = []
    textos_encontrados: List[TextoDetectado] = []


class RespostaPlaca(BaseModel):
    sucesso: bool
    mensagem: str
    dados: Optional[DadosPlaca] = None


@app.get("/", summary="Status da API")
async def root():
    return {
        "status": "online",
        "api": "Reconhecimento de Placas Veiculares",
        "versao": "1.0.0",
        "gpu_habilitada": ocr_service.gpu
    }


@app.post(
    "/detectar-placa",
    response_model=RespostaPlaca,
    summary="Detectar placa veicular em foto",
    description="Recebe uma imagem (foto do veiculo/placa) e retorna os dados da placa reconhecida."
)
async def detectar_placa(file: UploadFile = File(...)):
    # Valida se e uma imagem
    content_type = file.content_type or ""
    if not (content_type.startswith("image/") or file.filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp"))):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O arquivo enviado precisa ser uma imagem valida (JPEG, PNG, WEBP, etc.)."
        )

    try:
        conteudo_imagem = await file.read()
        if not conteudo_imagem:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="O arquivo enviado esta vazio."
            )

        resultado = ocr_service.detect_plate(conteudo_imagem)

        if resultado["encontrada"]:
            return RespostaPlaca(
                sucesso=True,
                mensagem=f"Placa {resultado['placa_formatada']} ({resultado['padrao']}) detectada com sucesso!",
                dados=DadosPlaca(**resultado)
            )
        else:
            return RespostaPlaca(
                sucesso=False,
                mensagem="Nenhuma placa veicular valida foi identificada na imagem.",
                dados=DadosPlaca(**resultado)
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Erro ao processar imagem para deteccao de placa")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno ao processar a imagem: {str(e)}"
        )
