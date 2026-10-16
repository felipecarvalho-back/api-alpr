# API de Reconhecimento de Placas com FastAPI, EasyOCR e Docker

API de alta performance em Python desenvolvida para processar fotos de veículos enviadas por aplicativos móveis ou web, identificar a placa brasileira (**Mercosul** ou **Padrão Antigo**) com OCR avançado, validar requisições via **Token JWT** e retornar **somente a placa identificada**.

Pronta para execução em contêineres **Docker** e hospedagem simplificada no **Render**.

---

## ⚡ Otimizações de Performance e Memória

A API foi otimizada para operar com máxima velocidade e baixo consumo de memória (compatível com os limites do plano gratuito do Render de 512MB RAM):
1. **Redimensionamento Proporcional Inteligente**: Fotos tiradas por celulares modernos (12MP a 48MP) são redimensionadas para no máximo 1280px. Isso reduz o tempo de inferência de 20s para cerca de 1s a 1.5s e corta o consumo de RAM em mais de 80%.
2. **PyTorch CPU-Only no Docker**: Instalação dedicada sem os pacotes pesados do CUDA, reduzindo o tamanho da imagem de ~4GB para ~500MB.
3. **Pré-carregamento dos Modelos no Build**: O modelo EasyOCR é pré-baixado durante o `docker build`, eliminando cold start demorado e timeouts no Render.
4. **Quantização de Modelos**: Ativa quantização INT8 na CPU (`quantize=True`), acelerando a inferência e reduzindo ainda mais o uso de memória.
5. **Ajuste de Concorrência de Threads**: O número de threads de CPU do PyTorch é controlado (`TORCH_NUM_THREADS=2`) para evitar sobrecarga de CPU em contêineres em nuvem.
6. **Inference Mode**: Desativação completa dos grafos de autograd do PyTorch durante a leitura do OCR.

---

## 🔐 Autenticação JWT

Todas as requisições para detecção de placas exigem um **Token JWT** válido.

O token pode ser enviado de duas formas:
- **Header HTTP** (recomendado): `Authorization: Bearer <seu_token_jwt>`
- **Campo de Formulário / Form-data**: campo `token` junto com a imagem.

### Variáveis de Ambiente para Configuração:
- `JWT_SECRET_KEY`: Chave secreta usada para assinar e validar os tokens (definir no Render).
- `JWT_ALGORITHM`: Algoritmo de hash (padrão: `HS256`).
- `JWT_EXPIRATION_MINUTES`: Validade do token em minutos (padrão: `1440` = 24h).

---

## 🚀 Como Hospedar no Render

Você pode hospedar esta API no Render de duas formas:

### Opção 1: Via Render Blueprint (Recomendado - 1 Clique)
1. Suba o repositório no seu GitHub.
2. Acesse o [Render Dashboard](https://dashboard.render.com).
3. Clique em **New +** > **Blueprint**.
4. Selecione este repositório. O Render lerá o arquivo `render.yaml` e configurará automaticamente:
   - Serviço Web Docker.
   - Variáveis de ambiente (`JWT_SECRET_KEY`, `TORCH_NUM_THREADS`, etc.).
   - Health check em `/`.
5. Clique em **Apply**.

### Opção 2: Manualmente como Web Service Docker
1. No [Render Dashboard](https://dashboard.render.com), clique em **New +** > **Web Service**.
2. Conecte o repositório GitHub.
3. Escolha o ambiente: **Docker**.
4. Defina o plano: **Free**.
5. Em **Environment Variables**, adicione:
   - `JWT_SECRET_KEY`: uma chave secreta forte (ex: uma hash gerada aleatoriamente).
   - `TORCH_NUM_THREADS`: `2`
   - `MAX_IMAGE_DIMENSION`: `1280`
   - `EASYOCR_QUANTIZE`: `True`
6. Clique em **Deploy Web Service**.

> **Nota sobre o Render**: O Render atribui dinamicamente a porta através da variável `$PORT`. O `Dockerfile` já está configurado com `uvicorn --port ${PORT:-8000}`, funcionando de forma transparente.

---

## ☁️ Como Hospedar no Modal (Serverless)

O arquivo [`modal_app.py`](modal_app.py) permite hospedar a API de forma serverless com 2GB de RAM e inicialização automática:

1. Instale a biblioteca do Modal:
```bash
pip install modal
```

2. Autentique seu ambiente com sua conta do Modal:
```bash
modal setup
```

3. Para testar em desenvolvimento com hot-reload na nuvem:
```bash
modal serve modal_app.py
```

4. Para fazer o deploy definitivo em produção:
```bash
modal deploy modal_app.py
```

---

## 🐳 Executando Localmente com Docker

1. **Construir a imagem**:
```bash
docker build -t api-placas .
```

2. **Rodar o contêiner**:
```bash
docker run -d -p 8000:8000 -e JWT_SECRET_KEY=sua-chave-secreta api-placas
```

Acesse a documentação interativa em: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 💻 Executando Localmente em Ambiente Virtual (Sem Docker)

1. Crie e ative o ambiente virtual:
```powershell
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
```

2. Instale as dependências:
```powershell
pip install -r requirements.txt
```

3. Inicie a API:
```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 📡 Endpoints da API

### 1. `POST /gerar-token`
Gera um token JWT para testes ou integração. É possível gerar tokens temporários ou permanentes (infinitos).

**Corpo da Requisição (opcional):**
```json
{
  "identificador": "meu-app-mobile",
  "expira_em_minutos": 1440,
  "sem_expiracao": false
}
```
> **Dica para Token Infinito**: Para gerar um token que nunca expira, envie `"sem_expiracao": true` ou `"expira_em_minutos": 0`.

**Resposta (Token normal):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "token_type": "bearer",
  "expira_em_minutos": 1440
}
```

**Resposta (Token infinito / sem expiração):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "token_type": "bearer",
  "expira_em_minutos": null
}
```

---

### 2. `POST /detectar-placa`
Envia uma imagem de veículo e recebe **somente a placa identificada**.

**Headers:**
- `Authorization: Bearer <seu_token_jwt>`
- `Content-Type: multipart/form-data`

**Body:**
- `file`: Arquivo de imagem (JPEG, PNG, WEBP, etc.)

**Exemplo de Resposta (HTTP 200):**
```json
{
  "placa": "BRA2E19"
}
```

*(Se a imagem contiver uma placa no padrão antigo, ex: `ABC1234`, retornará `{"placa": "ABC1234"}`)*

**Exemplo de Resposta quando nenhuma placa é encontrada (HTTP 404):**
```json
{
  "detail": "Nenhuma placa veicular valida foi identificada na imagem."
}
```

**Exemplo de Resposta quando o token for inválido ou ausente (HTTP 401):**
```json
{
  "detail": "Token JWT invalido."
}
```

---

## 🧪 Testando com o Script Incluso

O projeto inclui o script `test_client.py` que obtém o token automaticamente e envia uma foto para a API:

```powershell
python test_client.py caminho/para/foto_carro.jpg
```

Para testar na API hospedada no Render:
```powershell
python test_client.py caminho/para/foto_carro.jpg https://sua-api.onrender.com/detectar-placa
```

---

## 📱 Exemplo de Integração Frontend / Mobile

### JavaScript / React Native
```javascript
const identificarPlaca = async (uriDaImagem, tokenJwt) => {
  const formData = new FormData();
  formData.append('file', {
    uri: uriDaImagem,
    name: 'veiculo.jpg',
    type: 'image/jpeg',
  });

  const resposta = await fetch('https://sua-api.onrender.com/detectar-placa', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${tokenJwt}`,
    },
    body: formData,
  });

  if (resposta.ok) {
    const dados = await resposta.json();
    console.log("Placa identificada:", dados.placa);
    return dados.placa;
  } else {
    const erro = await resposta.json();
    console.error("Erro:", erro.detail);
  }
};
```
