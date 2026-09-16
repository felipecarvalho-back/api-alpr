"""
Exemplo de cliente para testar a API de deteccao de placas.
Uso:
    python test_client.py caminho/para/foto.jpg [url_da_api]
"""
import sys
import os
import urllib.request
import urllib.error
import json
import mimetypes


def enviar_imagem(caminho_imagem: str, url_api: str = "http://localhost:8000/detectar-placa"):
    if not os.path.exists(caminho_imagem):
        print(f"Erro: Arquivo '{caminho_imagem}' nao foi encontrado.")
        return

    nome_arquivo = os.path.basename(caminho_imagem)
    mime_type = mimetypes.guess_type(caminho_imagem)[0] or "image/jpeg"

    with open(caminho_imagem, "rb") as f:
        file_bytes = f.read()

    # Monta payload multipart/form-data nativo (sem depender de libs externas no cliente)
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(
        f'Content-Disposition: form-data; name="file"; filename="{nome_arquivo}"\r\n'.encode("utf-8")
    )
    body.extend(f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"))
    body.extend(file_bytes)
    body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    req = urllib.request.Request(
        url_api,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "PlacaTestClient/1.0"
        },
        method="POST"
    )

    print(f"Enviando '{caminho_imagem}' para {url_api}...")
    try:
        with urllib.request.urlopen(req) as resp:
            status_code = resp.getcode()
            response_data = json.loads(resp.read().decode("utf-8"))
            print(f"\nStatus: {status_code}")
            print(json.dumps(response_data, indent=2, ensure_ascii=False))
    except urllib.error.HTTPError as e:
        print(f"\nErro HTTP {e.code}: {e.reason}")
        print(e.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"\nErro de conexao: {e.reason}")
        print("Verifique se a API esta rodando (ex: uvicorn app.main:app --reload)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python test_client.py <caminho_da_imagem> [url_opcional]")
        print("Exemplo: python test_client.py foto_carro.jpg")
    else:
        caminho = sys.argv[1]
        url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8000/detectar-placa"
        enviar_imagem(caminho, url)
