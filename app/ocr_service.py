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

# Otimizacoes de threads para ambientes em nuvem/containers (como Render)
TORCH_NUM_THREADS = int(os.getenv("TORCH_NUM_THREADS", "2"))
try:
    torch.set_num_threads(TORCH_NUM_THREADS)
except Exception as e:
    logger.warning(f"Nao foi possivel definir torch.set_num_threads: {e}")

MAX_IMAGE_DIMENSION = int(os.getenv("MAX_IMAGE_DIMENSION", "1280"))
EASYOCR_QUANTIZE = os.getenv("EASYOCR_QUANTIZE", "True").lower() in ("true", "1", "t")


class OCRService:
    def __init__(
        self,
        languages: Optional[list] = None,
        max_dimension: int = MAX_IMAGE_DIMENSION,
        quantize: bool = EASYOCR_QUANTIZE
    ):
        # 'en' carrega o modelo latino que atende perfeitamente A-Z e 0-9 das placas brasileiras
        # sem a sobrecarga de carregar multiplos pacotes de reconhecimento desnecessarios.
        if languages is None:
            languages = ["en"]
        self.languages = languages
        self.reader: Optional[easyocr.Reader] = None
        self.gpu = torch.cuda.is_available()
        self.max_dimension = max_dimension
        self.quantize = quantize if not self.gpu else False

    def load_model(self) -> None:
        """Carrega o modelo EasyOCR na memoria e realiza o aquecimento inicial (warm-up)."""
        if self.reader is None:
            logger.info(
                f"Carregando EasyOCR (Idiomas: {self.languages}, GPU: {self.gpu}, Quantize: {self.quantize})..."
            )
            self.reader = easyocr.Reader(
                self.languages,
                gpu=self.gpu,
                quantize=self.quantize
            )
            # Aquecimento inicial (warm-up) para evitar atraso na primeira requisicao do usuario
            try:
                logger.info("Realizando warm-up do modelo...")
                dummy_img = np.zeros((64, 64, 3), dtype=np.uint8)
                with torch.inference_mode():
                    self.reader.readtext(dummy_img, mag_ratio=1.0)
                logger.info("Warm-up concluido com sucesso.")
            except Exception as ex:
                logger.warning(f"Aviso durante warm-up do OCR: {ex}")

            logger.info("Modelo EasyOCR pronto para operacao!")

    def preprocess_image(self, image_bytes: bytes) -> np.ndarray:
        """
        Carrega imagem de bytes, ajusta orientacao EXIF (fotos de celular),
        redimensiona proporcionalmente para evitar estouro de memoria (OOM)
        e converte para array NumPy RGB.
        """
        pil_image = Image.open(io.BytesIO(image_bytes))

        # Corrige a rotacao caso a foto tenha metadados EXIF
        pil_image = ImageOps.exif_transpose(pil_image)

        # Converte para RGB
        if pil_image.mode != "RGB":
            pil_image = pil_image.convert("RGB")

        # Otimizacao de Performance:
        # Fotos de celulares modernos chegam com 12MP a 48MP (ex: 4000x3000), o que consumiria
        # mais de 1.5GB de RAM e 15 a 30s de CPU.
        # Redimensionar para no maximo 1280px mantem os caracteres da placa nitidos
        # e reduz o tempo de OCR em mais de 10x, cabendo tranquilamente no limite do Render.
        w, h = pil_image.size
        maior_lado = max(w, h)
        if maior_lado > self.max_dimension:
            escala = self.max_dimension / float(maior_lado)
            novo_w = max(1, int(w * escala))
            novo_h = max(1, int(h * escala))
            pil_image = pil_image.resize((novo_w, novo_h), Image.Resampling.BILINEAR)

        return np.array(pil_image)

    def detect_plate(self, image_bytes: bytes) -> Dict[str, Any]:
        """Executa a leitura de OCR com alta performance e retorna os dados da placa identificada."""
        self.load_model()
        image_np = self.preprocess_image(image_bytes)

        # Executa EasyOCR com inferencia otimizada (sem grafos de gradiente)
        with torch.inference_mode():
            raw_results = self.reader.readtext(
                image_np,
                batch_size=4,
                mag_ratio=1.0,  # Evita upscaling desnecessario de 1.5x que consome CPU e RAM
                canvas_size=self.max_dimension
            )

        # Analisa os textos procurando padroes de placas
        result = process_ocr_results(raw_results)
        return result


# Instancia singleton do servico OCR
ocr_service = OCRService()
