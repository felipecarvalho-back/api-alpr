from app.utils import (
    clean_text,
    classify_plate,
    extract_plate_from_text,
    format_plate,
    process_ocr_results,
)


def test_classify_plate():
    assert classify_plate("ABC1D23") == "Mercosul"
    assert classify_plate("BRA2E19") == "Mercosul"
    assert classify_plate("ABC1234") == "Antigo"
    assert classify_plate("XYZ9999") == "Antigo"
    assert classify_plate("ABC123") is None
    assert classify_plate("ABC12345") is None


def test_format_plate():
    assert format_plate("ABC1234", "Antigo") == "ABC-1234"
    assert format_plate("BRA2E19", "Mercosul") == "BRA2E19"


def test_extract_plate_from_text():
    # Placa isolada
    assert extract_plate_from_text("ABC1D23") == ("ABC1D23", "Mercosul")
    assert extract_plate_from_text("ABC-1234") == ("ABC1234", "Antigo")

    # Placa com texto ao redor (ex: BRASIL ou estado)
    assert extract_plate_from_text("BRASIL BRA2E19") == ("BRA2E19", "Mercosul")
    assert extract_plate_from_text("SP - SAO PAULO ABC-1234") == ("ABC1234", "Antigo")

    # Correcao de caractere OCR (ex: 'O' no lugar de '0' na parte numerica do Mercosul)
    assert extract_plate_from_text("ABC1D2O") == ("ABC1D20", "Mercosul")


def test_process_ocr_results_single_box():
    dummy_ocr = [
        ([[10, 10], [100, 10], [100, 40], [10, 40]], "BRA2E19", 0.98)
    ]
    res = process_ocr_results(dummy_ocr)
    assert res["encontrada"] is True
    assert res["placa"] == "BRA2E19"
    assert res["padrao"] == "Mercosul"
    assert res["confianca"] == 0.98


def test_process_ocr_results_split_boxes():
    dummy_ocr = [
        ([[10, 10], [50, 10], [50, 40], [10, 40]], "ABC", 0.95),
        ([[55, 10], [100, 10], [100, 40], [55, 40]], "1234", 0.93)
    ]
    res = process_ocr_results(dummy_ocr)
    assert res["encontrada"] is True
    assert res["placa"] == "ABC1234"
    assert res["padrao"] == "Antigo"
    assert res["placa_formatada"] == "ABC-1234"


if __name__ == "__main__":
    test_classify_plate()
    test_format_plate()
    test_extract_plate_from_text()
    test_process_ocr_results_single_box()
    test_process_ocr_results_split_boxes()
    print("Todos os testes unitarios passaram com sucesso!")
