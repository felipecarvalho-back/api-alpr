# API de Reconhecimento de Placas com EasyOCR e FastAPI

API em Python para processar imagens enviadas por aplicativos (celular / web), identificar e extrair automaticamente placas de veículos no padrão brasileiro (**Mercosul** e **Padrão Antigo**).

---

## 🚀 Tecnologias

- **Python 3.10+** (recomendado Python 3.11 a 3.13 para compatibilidade com PyTorch)
- **FastAPI**: Framework web de alta performance
- **EasyOCR**: Biblioteca de OCR baseada em PyTorch
- **Pillow**: Processamento de imagem e correção automática de rotação EXIF (fotos de smartphone)
- **Uvicorn**: Servidor ASGI

---

## 📦 Instalação

1. Crie e ative um ambiente virtual:

```powershell
python -m venv venv ; .\venv\Scripts\Activate.ps1
```

2. Instale as dependências:

```powershell
pip install -r requirements.txt
```

> **Dica**: No primeiro uso, o EasyOCR baixará automaticamente os modelos de reconhecimento (cerca de 50MB a 100MB).

---

## 🚦 Executando a API

Inicie o servidor com Uvicorn:

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

> **Atenção para testes em dispositivos móveis**: O `--host 0.0.0.0` permite que seu smartphone na mesma rede Wi-Fi acerte a API usando o IP local da sua máquina (ex: `http://192.168.1.50:8000`).

- **Documentação Interativa (Swagger)**: Acesse [http://localhost:8000/docs](http://localhost:8000/docs) no navegador para testar o envio de imagens diretamente pela interface.

---

## 📡 Endpoints

### `POST /detectar-placa`
Envia uma foto (multipart/form-data com o campo `file`) e recebe os dados da placa.

#### Exemplo de Resposta (Sucesso):
```json
{
  "sucesso": true,
  "mensagem": "Placa BRA2E19 (Mercosul) detectada com sucesso!",
  "dados": {
    "placa": "BRA2E19",
    "placa_formatada": "BRA2E19",
    "padrao": "Mercosul",
    "confianca": 0.9654,
    "todos_candidatos": [
      {
        "placa": "BRA2E19",
        "placa_formatada": "BRA2E19",
        "padrao": "Mercosul",
        "confianca": 0.9654,
        "origem": "texto_isolado"
      }
    ],
    "textos_encontrados": [
      {
        "texto": "BRASIL",
        "confianca": 0.892,
        "bbox": [[10, 5], [120, 5], [120, 30], [10, 30]]
      },
      {
        "texto": "BRA2E19",
        "confianca": 0.9654,
        "bbox": [[15, 35], [130, 35], [130, 80], [15, 80]]
      }
    ]
  }
}
```

---

## 📱 Exemplos de Integração com o App

### 1. cURL (Terminal)
```bash
curl -X POST "http://localhost:8000/detectar-placa" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@caminho/para/foto_carro.jpg"
```

### 2. React Native / JavaScript
```javascript
const enviarFoto = async (uriDaFoto) => {
  const formData = new FormData();
  formData.append('file', {
    uri: uriDaFoto,
    name: 'placa.jpg',
    type: 'image/jpeg',
  });

  const resposta = await fetch('http://SEU_IP_LOCAL:8000/detectar-placa', {
    method: 'POST',
    body: formData,
  });

  const json = await resposta.json();
  if (json.sucesso) {
    console.log("Placa identificada:", json.dados.placa_formatada);
  } else {
    console.log("Nenhuma placa encontrada:", json.mensagem);
  }
};
```

### 3. Flutter / Dart (com `http`)
```dart
import 'package:http/http.dart' as http;
import 'dart:convert';

Future<void> enviarFoto(String caminhoArquivo) async {
  var request = http.MultipartRequest(
    'POST',
    Uri.parse('http://SEU_IP_LOCAL:8000/detectar-placa'),
  );
  request.files.add(await http.MultipartFile.fromPath('file', caminhoArquivo));

  var streamedResponse = await request.send();
  var response = await http.Response.fromStream(streamedResponse);

  if (response.statusCode == 200) {
    var data = jsonDecode(response.body);
    print("Placa: ${data['dados']['placa_formatada']}");
  }
}
```

---

## 🧪 Testando com o Script Python Incluso

Você pode testar rapidamente enviando uma foto salva:
```powershell
python test_client.py caminho/para/foto.jpg
```
