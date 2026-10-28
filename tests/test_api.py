import io
from unittest.mock import patch
from fastapi.testclient import TestClient
from PIL import Image
import pytest

from app.auth import criar_token_acesso, verificar_token
from app.main import app

client = TestClient(app)


def gerar_imagem_bytes(largura: int = 100, altura: int = 100) -> bytes:
    """Gera bytes de uma imagem JPEG valida para testes."""
    img = Image.new("RGB", (largura, altura), color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    dados = response.json()
    assert dados["status"] == "online"
    assert "versao" in dados


def test_gerar_token():
    response = client.post("/gerar-token", json={"identificador": "test-app", "expira_em_minutos": 30})
    assert response.status_code == 200
    dados = response.json()
    assert "access_token" in dados
    assert dados["token_type"] == "bearer"
    # Valida o token gerado
    payload = verificar_token(dados["access_token"])
    assert payload["sub"] == "test-app"
    assert "exp" in payload


def test_gerar_token_infinito():
    # Teste via sem_expiracao=True
    response = client.post("/gerar-token", json={"identificador": "test-infinito", "sem_expiracao": True})
    assert response.status_code == 200
    dados = response.json()
    assert dados["expira_em_minutos"] is None
    payload = verificar_token(dados["access_token"])
    assert payload["sub"] == "test-infinito"
    assert "exp" not in payload

    # Teste via expira_em_minutos=0
    response2 = client.post("/gerar-token", json={"identificador": "test-infinito-zero", "expira_em_minutos": 0})
    assert response2.status_code == 200
    dados2 = response2.json()
    assert dados2["expira_em_minutos"] is None
    payload2 = verificar_token(dados2["access_token"])
    assert payload2["sub"] == "test-infinito-zero"
    assert "exp" not in payload2



def test_auth_sem_token():
    img_bytes = gerar_imagem_bytes()
    response = client.post(
        "/detectar-placa",
        files={"file": ("carro.jpg", img_bytes, "image/jpeg")}
    )
    assert response.status_code == 401
    assert "Token JWT nao fornecido" in response.json()["detail"]


def test_auth_token_invalido():
    img_bytes = gerar_imagem_bytes()
    response = client.post(
        "/detectar-placa",
        headers={"Authorization": "Bearer token-invalido-123"},
        files={"file": ("carro.jpg", img_bytes, "image/jpeg")}
    )
    assert response.status_code == 401
    assert "Token JWT invalido" in response.json()["detail"]


def test_auth_token_expirado():
    img_bytes = gerar_imagem_bytes()
    token_expirado = criar_token_acesso({"sub": "expirado"}, expira_em_minutos=-10)
    response = client.post(
        "/detectar-placa",
        headers={"Authorization": f"Bearer {token_expirado}"},
        files={"file": ("carro.jpg", img_bytes, "image/jpeg")}
    )
    assert response.status_code == 401
    assert "Token JWT expirado" in response.json()["detail"]


def test_detectar_placa_sucesso_retorna_apenas_placa():
    token = criar_token_acesso({"sub": "test-client"})
    img_bytes = gerar_imagem_bytes()

    with patch("app.main.ocr_service.detect_plate") as mock_detect:
        mock_detect.return_value = {
            "encontrada": True,
            "placa": "BRA2E19",
            "placa_formatada": "BRA2E19",
            "padrao": "Mercosul",
            "confianca": 0.99
        }

        response = client.post(
            "/detectar-placa",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("carro.jpg", img_bytes, "image/jpeg")}
        )

        assert response.status_code == 200
        dados = response.json()
        assert dados["placa"] == "BRA2E19"
        assert dados["encontrada"] is True
        assert "mensagem" in dados


def test_detectar_placa_com_token_no_form():
    token = criar_token_acesso({"sub": "form-client"})
    img_bytes = gerar_imagem_bytes()

    with patch("app.main.ocr_service.detect_plate") as mock_detect:
        mock_detect.return_value = {
            "encontrada": True,
            "placa": "ABC1234",
            "placa_formatada": "ABC-1234",
            "padrao": "Antigo",
            "confianca": 0.95
        }

        response = client.post(
            "/detectar-placa",
            data={"token": token},
            files={"file": ("carro.jpg", img_bytes, "image/jpeg")}
        )

        assert response.status_code == 200
        assert response.json()["placa"] == "ABC1234"
        assert response.json()["encontrada"] is True


def test_detectar_placa_nao_encontrada():
    token = criar_token_acesso({"sub": "test-client"})
    img_bytes = gerar_imagem_bytes()

    with patch("app.main.ocr_service.detect_plate") as mock_detect:
        mock_detect.return_value = {
            "encontrada": False,
            "placa": None,
            "confianca": 0.0
        }

        response = client.post(
            "/detectar-placa",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("carro.jpg", img_bytes, "image/jpeg")}
        )

        # Retorna 200 com status indicando que nenhuma placa foi identificada (evita 404 em clientes)
        assert response.status_code == 200
        dados = response.json()
        assert dados["placa"] is None
        assert dados["encontrada"] is False
        assert "Nenhuma placa veicular valida foi identificada" in dados["mensagem"]


def test_detectar_placa_arquivo_nao_imagem():
    token = criar_token_acesso({"sub": "test-client"})
    response = client.post(
        "/detectar-placa",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("arquivo.txt", b"texto qualquer", "text/plain")}
    )
    assert response.status_code == 400


def test_detectar_placa_repasse_laravel_octet_stream_sem_extensao():
    """Garante que arquivos temporarios do PHP/Laravel (ex: php8A2F.tmp com application/octet-stream) sejam aceitos."""
    token = criar_token_acesso({"sub": "laravel-api"})
    img_bytes = gerar_imagem_bytes()

    with patch("app.main.ocr_service.detect_plate") as mock_detect:
        mock_detect.return_value = {
            "encontrada": True,
            "placa": "MER1C23",
            "placa_formatada": "MER1C23",
            "padrao": "Mercosul",
            "confianca": 0.91
        }

        response = client.post(
            "/detectar-placa",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("php8A2F.tmp", img_bytes, "application/octet-stream")}
        )
        assert response.status_code == 200
        assert response.json()["placa"] == "MER1C23"
        assert response.json()["encontrada"] is True


def test_cors_preflight():
    response = client.options(
        "/detectar-placa",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        }
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "POST" in response.headers.get("access-control-allow-methods", "")
