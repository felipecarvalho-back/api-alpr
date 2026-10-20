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


def test_fallback_plate_detection_trigger():
    from unittest.mock import MagicMock
    service = OCRService()
    service.reader = MagicMock()

    # Simula imagem vazia
    img_np = np.zeros((300, 500, 3), dtype=np.uint8)

    # Simula raw_results da primeira passada com leitura incompleta de 5 chars (ex: 'F34E2')
    raw_results = [
        ([[100, 100], [400, 100], [400, 200], [100, 200]], "F34E2", 0.35)
    ]

    # No fallback (crop esticado), o reader identifica a placa completa Mercosul
    service.reader.readtext.return_value = [
        ([[0, 0], [100, 0], [100, 50], [0, 50]], "FJB4E12", 0.88)
    ]

    resultado = service.fallback_plate_detection(img_np, raw_results)
    assert resultado is not None
    assert resultado["encontrada"] is True
    assert resultado["placa"] == "FJB4E12"
    assert resultado["padrao"] == "Mercosul"


def test_screen_enhancement_and_center_zoom():
    img_np = np.random.randint(0, 255, (400, 600, 3), dtype=np.uint8)
    enhanced = OCRService.apply_screen_enhancement(img_np)
    assert enhanced.shape == (400, 600, 3)

    zoomed = OCRService.get_center_crop_zoom(enhanced)
    # 60% da altura (240) e 70% da largura (420), ampliado em 1.4x = 336x588
    assert zoomed.shape == (336, 588, 3)


