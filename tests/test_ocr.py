import io
from PIL import Image
import numpy as np
from app.ocr_service import OCRService


def test_preprocess_image_resizing():
    service = OCRService(max_dimension=1000)

    # Cria imagem grande (3000 x 2000)
    img_grande = Image.new("RGB", (3000, 2000), color="blue")
    buf = io.BytesIO()
    img_grande.save(buf, format="JPEG")
    img_bytes = buf.getvalue()

    resultado_np = service.preprocess_image(img_bytes)

    # Verifica se a maior dimensao foi reduzida para 1000px
    h, w, c = resultado_np.shape
    assert max(h, w) == 1000
    assert w == 1000
    assert h == int(2000 * (1000 / 3000))
    assert c == 3


def test_preprocess_image_small_not_upscaled():
    service = OCRService(max_dimension=1280)

    # Cria imagem pequena (600 x 400)
    img_pequena = Image.new("RGB", (600, 400), color="red")
    buf = io.BytesIO()
    img_pequena.save(buf, format="JPEG")
    img_bytes = buf.getvalue()

    resultado_np = service.preprocess_image(img_bytes)

    # Nao deve alterar resolucao de imagens ja menores que max_dimension
    h, w, c = resultado_np.shape
    assert w == 600
    assert h == 400
    assert c == 3
