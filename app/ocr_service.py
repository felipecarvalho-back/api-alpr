import gc
import io
import logging
import os
from typing import Any, Dict, Optional
import cv2
import numpy as np
from PIL import Image, ImageOps
import easyocr
import torch

from app.utils import extract_plate_from_text, format_plate, process_ocr_results

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

    def fallback_plate_detection(self, image_np: np.ndarray, raw_results: list) -> Optional[Dict[str, Any]]:
        """
        Executa fallback quando o reconhecimento direto nao encontra uma placa completa de 7 caracteres.
        Isola caixas de texto suspeitas, remove ruidos/faixas superiores e estica horizontalmente
        para separar caracteres estreitos ou espacados (como no padrao Mercosul FE-Schrift).
        """
        img_h, img_w = image_np.shape[:2]
        candidatos = []

        for item in raw_results:
            bbox, text, prob = item
            pts = np.array(bbox, dtype=np.int32)
            x_min, y_min = pts.min(axis=0)
            x_max, y_max = pts.max(axis=0)

            bw = x_max - x_min
            bh = y_max - y_min

            if bw < 30 or bh < 12:
                continue

            aspect_ratio = bw / float(bh)
            clean = "".join(c for c in str(text).upper() if c.isalnum())

            # Considera suspeitas caixas com entre 3 e 8 caracteres ou com formato largo de placa
            if not ((3 <= len(clean) <= 8) or (aspect_ratio >= 1.8)):
                continue

            cortes = [
                # 1. Mercosul: corta 16% do topo (faixa azul) e 10px da esquerda (QR/BR)
                (min(img_w - 20, x_min + 10), min(y_max - 10, y_min + int(bh * 0.16)), x_max, y_max, "mercosul_crop"),
                # 2. Padrao antigo ou caixa integral
                (max(0, x_min - 5), max(0, y_min - 5), min(img_w, x_max + 5), min(img_h, y_max + 5), "integral_crop"),
            ]

            for (cx1, cy1, cx2, cy2, modo) in cortes:
                if cy2 <= cy1 or cx2 <= cx1:
                    continue
                crop = image_np[cy1:cy2, cx1:cx2]
                ch, cw = crop.shape[:2]
                if ch < 12 or cw < 25:
                    continue

                # Esticamento horizontal para melhor separacao de caracteres no CRNN
                crop_stretched = cv2.resize(crop, (int(cw * 1.35), ch), interpolation=cv2.INTER_CUBIC)

                with torch.inference_mode():
                    leituras = self.reader.readtext(
                        crop_stretched,
                        allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
                    )

                for _, r_text, r_conf in leituras:
                    found = extract_plate_from_text(r_text)
                    if found:
                        placa, padrao = found
                        candidatos.append({
                            "placa": placa,
                            "placa_formatada": format_plate(placa, padrao),
                            "padrao": padrao,
                            "confianca": round(float(r_conf), 4),
                            "origem": f"fallback_{modo}"
                        })

        if candidatos:
            candidatos.sort(key=lambda x: x["confianca"], reverse=True)
            melhor = candidatos[0]
            return {
                "encontrada": True,
                "placa": melhor["placa"],
                "placa_formatada": melhor["placa_formatada"],
                "padrao": melhor["padrao"],
                "confianca": melhor["confianca"],
                "todos_candidatos": candidatos,
                "textos_encontrados": [],
            }
        return None

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

        # Analisa os textos procurando padroes de placas
        result = process_ocr_results(raw_results)

        # Fallback inteligente se a deteccao direta nao encontrar placa valida
        if not result.get("encontrada"):
            result_fallback = self.fallback_plate_detection(image_np, raw_results)
            if result_fallback and result_fallback.get("encontrada"):
                result_fallback["textos_encontrados"] = result.get("textos_encontrados", [])
                result = result_fallback

        # Limpa memoria residual de arrays
        del image_np
        liberar_memoria_so()
        return result


# Instancia singleton do servico OCR
ocr_service = OCRService()
