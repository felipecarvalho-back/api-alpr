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

# 1600px preserva excelente nitidez para fotos tiradas pelo celular (mesmo mais distantes ou de telas)
MAX_IMAGE_DIMENSION = int(os.getenv("MAX_IMAGE_DIMENSION", "1600"))


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
            pil_image = pil_image.resize((novo_w, novo_h), Image.Resampling.LANCZOS)

        return np.array(pil_image)

    @staticmethod
    def apply_screen_enhancement(image_np: np.ndarray) -> np.ndarray:
        """
        Aplica filtro Anti-Moire (suavizacao de grade de pixels de monitor)
        combinado com equalizacao adaptativa de contraste (CLAHE) para corrigir
        estouro de luz / reflexo em fotos tiradas de telas de computador ou sob sol forte.
        """
        if image_np.ndim == 3:
            gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)
        else:
            gray = image_np.copy()

        # Suaviza a malha de pixels do monitor (efeito Moire) preservando bordas das letras
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)

        # Realca contraste localmente (corrige brilho estourado de telas)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        enhanced = clahe.apply(blurred)

        return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2RGB)

    @staticmethod
    def get_center_crop_zoom(image_np: np.ndarray) -> np.ndarray:
        """
        Recorta os 60% centrais da foto (onde o usuario mira a camera do celular)
        e amplia em 1.4x com nitidez para placas que ficaram pequenas no enquadramento.
        """
        h, w = image_np.shape[:2]
        y1, y2 = int(h * 0.20), int(h * 0.80)
        x1, x2 = int(w * 0.15), int(w * 0.85)
        crop = image_np[y1:y2, x1:x2]
        ch, cw = crop.shape[:2]
        if ch < 20 or cw < 20:
            return image_np
        return cv2.resize(crop, (int(cw * 1.4), int(ch * 1.4)), interpolation=cv2.INTER_CUBIC)

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

            if bw < 25 or bh < 10:
                continue

            aspect_ratio = bw / float(bh)
            clean = "".join(c for c in str(text).upper() if c.isalnum())

            # Considera suspeitas caixas com entre 2 e 9 caracteres ou com formato largo de placa
            if not ((2 <= len(clean) <= 9) or (aspect_ratio >= 1.5)):
                continue

            cortes = [
                # 1. Mercosul: corta 16% do topo (faixa azul) e 10px da esquerda (QR/BR)
                (min(img_w - 20, x_min + 10), min(y_max - 10, y_min + int(bh * 0.16)), x_max, y_max, "mercosul_crop"),
                # 2. Padrao antigo ou caixa integral com margem
                (max(0, x_min - 6), max(0, y_min - 6), min(img_w, x_max + 6), min(img_h, y_max + 6), "integral_crop"),
            ]

            for (cx1, cy1, cx2, cy2, modo) in cortes:
                if cy2 <= cy1 or cx2 <= cx1:
                    continue
                crop = image_np[cy1:cy2, cx1:cx2]
                ch, cw = crop.shape[:2]
                if ch < 10 or cw < 25:
                    continue

                # Esticamento horizontal para melhor separacao de caracteres no CRNN
                fator_y = 2.0 if ch < 35 else 1.0
                crop_stretched = cv2.resize(
                    crop,
                    (int(cw * 1.35 * fator_y), int(ch * fator_y)),
                    interpolation=cv2.INTER_CUBIC
                )

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

    def _run_ocr_pass(self, img_variant: np.ndarray, mag_ratio: float = 1.0) -> Dict[str, Any]:
        """Executa uma passada completa (leitura direta + fallback de recorte) em uma variante da imagem."""
        with torch.inference_mode():
            raw_results = self.reader.readtext(
                img_variant,
                batch_size=4,
                mag_ratio=mag_ratio,
                canvas_size=self.max_dimension
            )

        result = process_ocr_results(raw_results)
        if not result.get("encontrada"):
            result_fallback = self.fallback_plate_detection(img_variant, raw_results)
            if result_fallback and result_fallback.get("encontrada"):
                result_fallback["textos_encontrados"] = result.get("textos_encontrados", [])
                return result_fallback

        return result

    def detect_plate(self, image_bytes: bytes) -> Dict[str, Any]:
        """
        Executa a leitura de OCR em multiplas etapas adaptativas:
        1. Imagem original pre-processada
        2. Filtro Anti-Moire + CLAHE (ideal para fotos tiradas da tela do PC pelo celular)
        3. Zoom central + Anti-Moire (ideal quando a placa esta pequena no centro da foto do celular)
        4. Rotacao 90° e 270° (caso o Laravel/Mobile tenha removido o EXIF de orientacao)
        """
        self.load_model()
        image_np = self.preprocess_image(image_bytes)
        h, w = image_np.shape[:2]

        # Passada 1: Imagem original
        result = self._run_ocr_pass(image_np, mag_ratio=1.0)
        if result.get("encontrada"):
            result["dimensoes_processadas"] = f"{w}x{h}"
            del image_np
            liberar_memoria_so()
            return result

        todos_textos = list(result.get("textos_encontrados", []))

        # Passada 2: Filtro Anti-Moire + CLAHE (corrige grade de pixels de monitor e reflexo)
        img_enhanced = self.apply_screen_enhancement(image_np)
        res_enhanced = self._run_ocr_pass(img_enhanced, mag_ratio=1.2)
        if res_enhanced.get("encontrada"):
            res_enhanced["dimensoes_processadas"] = f"{w}x{h} (anti-moire)"
            del image_np, img_enhanced
            liberar_memoria_so()
            return res_enhanced
        todos_textos.extend(res_enhanced.get("textos_encontrados", []))

        # Passada 3: Zoom na regiao central com filtro Anti-Moire (para fotos de celular mais distantes)
        img_center = self.get_center_crop_zoom(img_enhanced)
        res_center = self._run_ocr_pass(img_center, mag_ratio=1.2)
        del img_center
        if res_center.get("encontrada"):
            res_center["dimensoes_processadas"] = f"{w}x{h} (center-zoom)"
            del image_np, img_enhanced
            liberar_memoria_so()
            return res_center
        todos_textos.extend(res_center.get("textos_encontrados", []))

        # Passada 4: Se nada foi encontrado (ou quase nenhum texto lido), testa rotacoes 90° e 270°
        # (resolve fotos de celular enviadas deitadas pelo mobile/Laravel sem metadados EXIF)
        for rot_code, rot_label in (
            (cv2.ROTATE_90_CLOCKWISE, "rot90"),
            (cv2.ROTATE_90_COUNTERCLOCKWISE, "rot270"),
        ):
            img_rot = cv2.rotate(img_enhanced, rot_code)
            res_rot = self._run_ocr_pass(img_rot, mag_ratio=1.0)
            del img_rot
            if res_rot.get("encontrada"):
                res_rot["dimensoes_processadas"] = f"{w}x{h} ({rot_label})"
                del image_np, img_enhanced
                liberar_memoria_so()
                return res_rot
            todos_textos.extend(res_rot.get("textos_encontrados", []))

        # Limpa memoria residual de arrays
        del image_np, img_enhanced
        liberar_memoria_so()

        result["textos_encontrados"] = todos_textos
        result["dimensoes_processadas"] = f"{w}x{h}"
        return result


# Instancia singleton do servico OCR
ocr_service = OCRService()
