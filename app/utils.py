import re
from typing import Dict, List, Optional, Tuple, Any

# Expressoes regulares para padroes brasileiros
REGEX_MERCOSUL = re.compile(r"[A-Z]{3}[0-9][A-Z][0-9]{2}")
REGEX_ANTIGO = re.compile(r"[A-Z]{3}[0-9]{4}")

# Mapeamentos para possiveis correcoes de OCR
CHAR_TO_DIGIT = {
    "O": "0", "o": "0",
    "I": "1", "l": "1", "i": "1",
    "Z": "2", "z": "2",
    "B": "8",
    "S": "5", "s": "5",
    "G": "6",
    "A": "4",
}

DIGIT_TO_CHAR = {
    "0": "O",
    "1": "I",
    "2": "Z",
    "8": "B",
    "5": "S",
    "6": "G",
    "4": "A",
}


def clean_text(text: str) -> str:
    """Remove caracteres especiais e espacos, mantendo apenas letras e numeros em maiusculo."""
    if not text:
        return ""
    text_upper = text.upper()
    return re.sub(r"[^A-Z0-9]", "", text_upper)


def classify_plate(candidate: str) -> Optional[str]:
    """Verifica se uma string de 7 caracteres corresponde ao padrao Mercosul ou Antigo."""
    if len(candidate) != 7:
        return None
    if REGEX_MERCOSUL.fullmatch(candidate):
        return "Mercosul"
    if REGEX_ANTIGO.fullmatch(candidate):
        return "Antigo"
    return None


def format_plate(plate: str, padrao: str) -> str:
    """Formata a placa para exibicao amigavel."""
    plate = plate.upper()
    if padrao == "Antigo":
        return f"{plate[:3]}-{plate[3:]}"
    elif padrao == "Mercosul":
        return plate
    return plate


def fix_characters_by_position(text: str, is_mercosul: bool) -> str:
    """
    Ajusta caracteres trocados comuns de OCR com base na posicao esperada da placa.
    Mercosul: L L L D L D D (L = Letra, D = Digito)
    Antigo:   L L L D D D D
    """
    chars = list(text)
    if len(chars) != 7:
        return text

    # Primeiras 3 posicoes sao sempre letras
    for i in range(3):
        if chars[i].isdigit() and chars[i] in DIGIT_TO_CHAR:
            chars[i] = DIGIT_TO_CHAR[chars[i]]

    if is_mercosul:
        # Posicao 3: digito
        if not chars[3].isdigit() and chars[3] in CHAR_TO_DIGIT:
            chars[3] = CHAR_TO_DIGIT[chars[3]]
        # Posicao 4: letra
        if chars[4].isdigit() and chars[4] in DIGIT_TO_CHAR:
            chars[4] = DIGIT_TO_CHAR[chars[4]]
        # Posicoes 5 e 6: digitos
        for i in (5, 6):
            if not chars[i].isdigit() and chars[i] in CHAR_TO_DIGIT:
                chars[i] = CHAR_TO_DIGIT[chars[i]]
    else:
        # Antigo: posicoes 3, 4, 5, 6 sao digitos
        for i in range(3, 7):
            if not chars[i].isdigit() and chars[i] in CHAR_TO_DIGIT:
                chars[i] = CHAR_TO_DIGIT[chars[i]]

    return "".join(chars)


def extract_plate_from_text(raw_text: str) -> Optional[Tuple[str, str]]:
    """
    Busca correspondencias de placas em um texto puro.
    Retorna (placa_limpa, padrao) ou None.
    """
    cleaned = clean_text(raw_text)

    # 1. Busca direta por Mercosul
    match_mercosul = REGEX_MERCOSUL.search(cleaned)
    if match_mercosul:
        return match_mercosul.group(0), "Mercosul"

    # 2. Busca direta por Padrao Antigo
    match_antigo = REGEX_ANTIGO.search(cleaned)
    if match_antigo:
        return match_antigo.group(0), "Antigo"

    # 3. Se houver substring de 7 caracteres que possa ser recuperada por correcao de OCR
    if len(cleaned) >= 7:
        for i in range(len(cleaned) - 6):
            chunk = cleaned[i:i + 7]

            # Testa hipotese Mercosul corrigida
            hypo_mercosul = fix_characters_by_position(chunk, is_mercosul=True)
            if REGEX_MERCOSUL.fullmatch(hypo_mercosul):
                return hypo_mercosul, "Mercosul"

            # Testa hipotese Antigo corrigida
            hypo_antigo = fix_characters_by_position(chunk, is_mercosul=False)
            if REGEX_ANTIGO.fullmatch(hypo_antigo):
                return hypo_antigo, "Antigo"

    return None


def process_ocr_results(ocr_results: List[Any]) -> Dict[str, Any]:
    """
    Processa os resultados retornados pelo EasyOCR [(bbox, text, prob), ...].
    Retorna informacoes detalhadas da melhor placa encontrada.
    """
    textos_detectados = []
    candidatos_placas = []

    # Passo 1: Analisar cada texto detectado individualmente
    for item in ocr_results:
        bbox, text, prob = item
        bbox_serializable = [[int(pt[0]), int(pt[1])] for pt in bbox]
        text_str = str(text).strip()
        confidence = float(prob)

        textos_detectados.append({
            "texto": text_str,
            "confianca": round(confidence, 4),
            "bbox": bbox_serializable
        })

        found = extract_plate_from_text(text_str)
        if found:
            placa, padrao = found
            candidatos_placas.append({
                "placa": placa,
                "placa_formatada": format_plate(placa, padrao),
                "padrao": padrao,
                "confianca": round(confidence, 4),
                "origem": "texto_isolado"
            })

    # Passo 2: Se nenhuma placa foi encontrada individualmente,
    # tentar unir textos consecutivos (as vezes a placa se divide em 2 caixas de texto)
    if not candidatos_placas and len(textos_detectados) > 1:
        textos_limpos = [clean_text(t["texto"]) for t in textos_detectados]
        for i in range(len(textos_limpos)):
            for j in range(i + 1, min(i + 3, len(textos_limpos))):
                texto_combinado = "".join(textos_limpos[i:j + 1])
                found = extract_plate_from_text(texto_combinado)
                if found:
                    placa, padrao = found
                    # Media das confiancas dos pedacos combinados
                    avg_conf = sum(textos_detectados[k]["confianca"] for k in range(i, j + 1)) / (j - i + 1)
                    candidatos_placas.append({
                        "placa": placa,
                        "placa_formatada": format_plate(placa, padrao),
                        "padrao": padrao,
                        "confianca": round(avg_conf, 4),
                        "origem": "combinado"
                    })
                    break
            if candidatos_placas:
                break

    # Escolher o melhor candidato baseado em maior confianca
    if candidatos_placas:
        candidatos_placas.sort(key=lambda x: x["confianca"], reverse=True)
        melhor_candidato = candidatos_placas[0]
        return {
            "encontrada": True,
            "placa": melhor_candidato["placa"],
            "placa_formatada": melhor_candidato["placa_formatada"],
            "padrao": melhor_candidato["padrao"],
            "confianca": melhor_candidato["confianca"],
            "todos_candidatos": candidatos_placas,
            "textos_encontrados": textos_detectados,
        }

    return {
        "encontrada": False,
        "placa": None,
        "placa_formatada": None,
        "padrao": None,
        "confianca": 0.0,
        "todos_candidatos": [],
        "textos_encontrados": textos_detectados,
    }
