import io
import logging
from typing import Any, Dict, Optional
import numpy as np
from PIL import Image, ImageOps
import easyocr
import torch

from app.utils import process_ocr_results

logger = logging.getLogger("ocr_service")


class OCRService:
    def __init__(self, languages: Optional[list] = None):
        if languages is None:
            # 'en' cobre o alfabeto latino padrao e digitos, 'pt' para suporte a portugues
            languages = ["pt", "en"]
        self.languages = languages
        self.reader: Optional[easyocr.Reader] = None
        self.gpu = torch.cuda.is_available()

    def load_model(self) -> None:
        """Carrega o modelo EasyOCR na memoria se ainda nao estiver carregado."""
        if self.reader is None:
            logger.info(f"Carregando EasyOCR (Idiomas: {self.languages}, GPU: {self.gpu})...")
            self.reader = easyocr.Reader(self.languages, gpu=self.gpu)
            logger.info("Modelo EasyOCR carregado com sucesso.")

    def preprocess_image(self, image_bytes: bytes) -> np.ndarray:
        """
        Carrega imagem de bytes, ajusta orientacao EXIF (essencial para fotos de celular)
        e converte para array NumPy RGB.
        """
        pil_image = Image.open(io.BytesIO(image_bytes))

        # Corrige a rotacao caso a foto tenha metadados EXIF (muito comum em cameras de celular)
        pil_image = ImageOps.exif_transpose(pil_image)

        # Converte para RGB se estiver em RGBA, Escala de cinza, etc.
        if pil_image.mode != "RGB":
            pil_image = pil_image.convert("RGB")

        return np.array(pil_image)

    def detect_plate(self, image_bytes: bytes) -> Dict[str, Any]:
        """Executa a leitura de OCR na imagem e retorna os dados da placa identificada."""
        self.load_model()
        image_np = self.preprocess_image(image_bytes)

        # Executa EasyOCR
        # paragraph=False para obter caixas de texto separadas com precisao
        raw_results = self.reader.readtext(image_np)

        # Analisa os textos procurando padroes de placas
        result = process_ocr_results(raw_results)
        return result


# Instancia singleton do servico OCR
ocr_service = OCRService()
