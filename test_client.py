"""
Cliente de exemplo para testar a API de deteccao de placas veiculares com autenticacao JWT.
Uso:
    python test_client.py caminho/para/foto.jpg [url_da_api] [token_jwt_opcional]
"""
import sys
import os
import urllib.request
import urllib.error
import json
import mimetypes


def obter_token_teste(base_url: str) -> str:
    """Solicita um token de teste temporario ao endpoint /gerar-token."""
    url_token = f"{base_url.rstrip('/')}/gerar-token"
    dados = json.dumps({"identificador": "test-client", "expira_em_minutos": 60}).encode("utf-8")
    req = urllib.request.Request(
        url_token,
        data=dados,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            resultado = json.loads(resp.read().decode("utf-8"))
            return resultado.get("access_token", "")
    except Exception as e:
        print(f"Aviso: Nao foi possivel gerar token automatico: {e}")
        return ""


def enviar_imagem(
    caminho_imagem: str,
    url_api: str = "http://localhost:8000/detectar-placa",
    token: str = ""
):
    if not os.path.exists(caminho_imagem):
        print(f"Erro: Arquivo '{caminho_imagem}' nao foi encontrado.")
        return

    # Se nao foi passado token, tenta gerar um token de teste na propria API
    if not token:
        base_url = "/".join(url_api.split("/")[:3])  # ex: http://localhost:8000
        print("Obtendo token JWT de teste...")
        token = obter_token_teste(base_url)
        if token:
            print("Token obtido com sucesso.")

    nome_arquivo = os.path.basename(caminho_imagem)
    mime_type = mimetypes.guess_type(caminho_imagem)[0] or "image/jpeg"

    with open(caminho_imagem, "rb") as f:
        file_bytes = f.read()

    # Monta payload multipart/form-data nativo
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        f'Content-Disposition: form-data; name="file"; filename="{nome_arquivo}"\r\n'.encode("utf-8")
    )
    body.extend(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))
    body.extend(file_bytes)
    body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "PlacaTestClient/2.0"
    }

    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url_api, data=body, headers=headers, method="POST")

    print(f"Enviando '{caminho_imagem}' para {url_api}...")
    try:
        with urllib.request.urlopen(req) as resp:
            status_code = resp.getcode()
            response_data = json.loads(resp.read().decode("utf-8"))
            print(f"\nStatus: {status_code}")
            print(f"Resposta JSON: {json.dumps(response_data, indent=2, ensure_ascii=False)}")
            if response_data.get("placa"):
                print(f"\n>>> PLACA DETECTADA: {response_data['placa']} <<<\n")
            else:
                print(f"\n>>> AVISO: {response_data.get('mensagem', 'Nenhuma placa identificada')} <<<\n")
    except urllib.error.HTTPError as e:
        print(f"\nErro HTTP {e.code}: {e.reason}")
        print(e.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"\nErro de conexao: {e.reason}")
        print("Verifique se a API esta rodando (ex: uvicorn app.main:app --reload)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python test_client.py <caminho_da_imagem> [url_opcional] [token_jwt_opcional]")
        print("Exemplo: python test_client.py foto_carro.jpg")
    else:
        caminho = sys.argv[1]
        url = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2].startswith("http") else "http://localhost:8000/detectar-placa"
        token_arg = sys.argv[3] if len(sys.argv) > 3 else (sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("http") else "")
        enviar_imagem(caminho, url, token_arg)
