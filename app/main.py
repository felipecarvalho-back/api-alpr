import logging
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field

from app.auth import criar_token_acesso, validar_token_jwt
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
    logger.info("Servidor iniciado com sucesso. Porta liberada para conexoes!")
    yield
    logger.info("Encerrando API...")


# Esquema de autenticacao para documentacao OpenAPI / Swagger
security_scheme = HTTPBearer(auto_error=False)

app = FastAPI(
    title="API de Reconhecimento de Placas Veiculares",
    description=(
        "API de alta performance para deteccao e extracao de placas brasileiras "
        "(Mercosul e Padrao Antigo) com autenticacao JWT e saida direta da placa identificada."
    ),
    version="2.0.0",
    lifespan=lifespan
)

# Habilita CORS para permitir conexoes de aplicacoes web e mobile
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RespostaPlaca(BaseModel):
    placa: str = Field(
        ...,
        description="Placa veicular identificada (sem tracos ou pontuacoes)",
        examples=["ABC1D23", "ABC1234"]
    )


class RequisicaoToken(BaseModel):
    identificador: Optional[str] = Field("app-client", description="Nome ou ID da aplicacao cliente")
    expira_em_minutos: Optional[int] = Field(1440, description="Tempo de expiracao em minutos. Se 0, gera token sem expiracao.")
    sem_expiracao: Optional[bool] = Field(False, description="Se True, gera um token permanente/infinito sem expiracao")


class RespostaToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expira_em_minutos: Optional[int] = Field(None, description="Tempo de expiracao em minutos. Retorna null se for infinito.")


@app.get("/", summary="Status e Health Check da API")
async def root():
    return {
        "status": "online",
        "api": "Reconhecimento de Placas Veiculares",
        "versao": "2.0.0",
        "gpu_habilitada": ocr_service.gpu
    }


@app.post(
    "/gerar-token",
    response_model=RespostaToken,
    summary="Gerar Token JWT para autenticacao",
    description="Endpoint utilitario para gerar tokens JWT para uso nas requisicoes a API."
)
async def gerar_token(dados: Optional[RequisicaoToken] = None):
    sub = dados.identificador if dados and dados.identificador else "app-client"
    payload = {"sub": sub}

    eh_infinito = False
    if dados:
        if dados.sem_expiracao or dados.expira_em_minutos == 0:
            eh_infinito = True

    if eh_infinito:
        token = criar_token_acesso(payload, sem_expiracao=True)
        return RespostaToken(
            access_token=token,
            token_type="bearer",
            expira_em_minutos=None
        )

    minutos = dados.expira_em_minutos if (dados and dados.expira_em_minutos is not None) else 1440
    token = criar_token_acesso(payload, expira_em_minutos=minutos)
    return RespostaToken(
        access_token=token,
        token_type="bearer",
        expira_em_minutos=minutos
    )


@app.post(
    "/detectar-placa",
    response_model=RespostaPlaca,
    summary="Detectar placa veicular em foto",
    description=(
        "Recebe uma imagem (foto do veiculo/placa) e um token JWT valido "
        "(via header 'Authorization: Bearer <token>' ou no campo 'token' do form-data). "
        "Retorna somente a placa identificada."
    )
)
async def detectar_placa(
    file: UploadFile = File(..., description="Arquivo de imagem (JPEG, PNG, WEBP, etc.)"),
    token_valido: dict = Depends(validar_token_jwt)
):
    # Valida se o arquivo enviado possui formato de imagem valido
    content_type = file.content_type or ""
    filename = file.filename or ""
    if not (content_type.startswith("image/") or filename.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp"))):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="O arquivo enviado precisa ser uma imagem valida (JPEG, PNG, WEBP, etc.)."
        )

    try:
        conteudo_imagem = await file.read()
        if not conteudo_imagem:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="O arquivo de imagem enviado esta vazio."
            )

        resultado = ocr_service.detect_plate(conteudo_imagem)

        if resultado.get("encontrada") and resultado.get("placa"):
            return RespostaPlaca(placa=resultado["placa"])
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Nenhuma placa veicular valida foi identificada na imagem."
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Erro ao processar imagem para deteccao de placa")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno ao processar a imagem: {str(e)}"
        )
