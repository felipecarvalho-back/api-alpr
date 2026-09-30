import gc
import io
import logging
import os
from typing import Any, Dict, Optional
import numpy as np
from PIL import Image, ImageOps
import easyocr
import torch

from app.utils import process_ocr_results

logger = logging.getLogger("ocr_service")

# Otimizacao estrita de threads para ambientes em nuvem/containers com 512MB RAM (como Render)
TORCH_NUM_THREADS = int(os.getenv("TORCH_NUM_THREADS", "1"))
try:
    torch.set_num_threads(TORCH_NUM_THREADS)
except Exception as e:
    logger.warning(f"Nao foi possivel definir torch.set_num_threads: {e}")

# 960px e ideal para placas veiculares, mantendo a memoria de tensores do CRAFT muito baixa (<35MB)
MAX_IMAGE_DIMENSION = int(os.getenv("MAX_IMAGE_DIMENSION", "960"))


def liberar_memoria_so():
    """Forca o coletor de lixo do Python e o malloc do SO a liberarem memoria residual."""
    gc.collect()
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
    except Exception:
        pass


class OCRService:
    def __init__(
        self,
        languages: Optional[list] = None,
        max_dimension: int = MAX_IMAGE_DIMENSION,
    ):
        # 'pt' e 'en' usam o modelo latin_g2.pth que atende perfeitamente placas do Brasil
        if languages is None:
            languages = ["pt", "en"]
        self.languages = languages
        self.reader: Optional[easyocr.Reader] = None
        self.gpu = torch.cuda.is_available()
        self.max_dimension = max_dimension

    def load_model(self) -> None:
        """Carrega o modelo EasyOCR sob demanda sem picos de memoria."""
        if self.reader is None:
            logger.info(
                f"Carregando EasyOCR sob demanda (Idiomas: {self.languages}, GPU: {self.gpu})..."
            )
            # quantize=False evita a duplicacao temporaria de modelos na RAM durante a quantizacao dinamica
            self.reader = easyocr.Reader(
                self.languages,
                gpu=self.gpu,
                quantize=False
            )
            liberar_memoria_so()
            logger.info("Modelo EasyOCR carregado com sucesso na memoria.")

    def preprocess_image(self, image_bytes: bytes) -> np.ndarray:
        """
        Carrega imagem de bytes, ajusta orientacao EXIF e
        redimensiona proporcionalmente para manter consumo de RAM minimo.
        """
        pil_image = Image.open(io.BytesIO(image_bytes))

        # Corrige rotacao de fotos de celular
        pil_image = ImageOps.exif_transpose(pil_image)

        # Converte para RGB
        if pil_image.mode != "RGB":
            pil_image = pil_image.convert("RGB")

        w, h = pil_image.size
        maior_lado = max(w, h)
        if maior_lado > self.max_dimension:
            escala = self.max_dimension / float(maior_lado)
            novo_w = max(1, int(w * escala))
            novo_h = max(1, int(h * escala))
            pil_image = pil_image.resize((novo_w, novo_h), Image.Resampling.BILINEAR)

        return np.array(pil_image)

    def detect_plate(self, image_bytes: bytes) -> Dict[str, Any]:
        """Executa a leitura de OCR com alta performance e memoria controlada."""
        self.load_model()
        image_np = self.preprocess_image(image_bytes)

        # Executa EasyOCR com inferencia controlada
        with torch.inference_mode():
            raw_results = self.reader.readtext(
                image_np,
                batch_size=4,
                mag_ratio=1.0,
                canvas_size=self.max_dimension
            )

        # Limpa memoria residual de arrays
        del image_np
        liberar_memoria_so()

        # Analisa os textos procurando padroes de placas
        result = process_ocr_results(raw_results)
        return result


# Instancia singleton do servico OCR
ocr_service = OCRService()
