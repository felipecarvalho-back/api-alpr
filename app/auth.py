import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
import jwt
from fastapi import Form, Header, HTTPException, Query, status

# Configuracoes de JWT obtidas por variavel de ambiente ou padroes seguros
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "chave-secreta-padrao-placas-api-render")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
DEFAULT_EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", "1440"))  # 24 horas por padrao


def criar_token_acesso(dados: Dict[str, Any], expira_em_minutos: Optional[int] = None) -> str:
    """Gera um novo token JWT assinado."""
    dados_para_codificar = dados.copy()
    minutos = expira_em_minutos if expira_em_minutos is not None else DEFAULT_EXPIRATION_MINUTES
    expiracao = datetime.now(timezone.utc) + timedelta(minutes=minutos)
    dados_para_codificar.update({"exp": expiracao})
    token = jwt.encode(dados_para_codificar, SECRET_KEY, algorithm=ALGORITHM)
    return token


def verificar_token(token: str) -> Dict[str, Any]:
    """Decodifica e valida a assinatura e expiracao do token JWT."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token JWT expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token JWT invalido.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def validar_token_jwt(
    authorization: Optional[str] = Header(None),
    token_form: Optional[str] = Form(None, alias="token"),
    token_query: Optional[str] = Query(None, alias="token")
) -> Dict[str, Any]:
    """
    Dependencia FastAPI para autenticar requisicoes.
    Aceita o token JWT atraves de:
    1. Header Authorization: Bearer <token>
    2. Campo de formulario 'token' (em multipart/form-data)
    3. Parametro de consulta '?token=<token>'
    """
    token_extraido = None

    if authorization:
        partes = authorization.strip().split()
        if len(partes) == 2 and partes[0].lower() == "bearer":
            token_extraido = partes[1]
        elif len(partes) == 1:
            token_extraido = partes[0]

    if not token_extraido and token_form:
        token_extraido = token_form.strip()

    if not token_extraido and token_query:
        token_extraido = token_query.strip()

    if not token_extraido:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token JWT nao fornecido. Envie o token no header 'Authorization: Bearer <token>' ou no campo 'token'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return verificar_token(token_extraido)
