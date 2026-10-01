from services import ocr


def test_tesseract_tsv_parser_preserves_bbox_confidence_and_unicode_text():
    tsv = "\n".join([
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
        "5\t1\t1\t1\t1\t1\t10\t20\t90\t25\t96.4\tFourier",
        "5\t1\t1\t1\t1\t2\t105\t20\t120\t25\t94.0\tTransform",
        "5\t1\t2\t1\t1\t1\t12\t80\t100\t30\t89.5\t傅里叶变换",
        "5\t1\t2\t1\t1\t2\t118\t80\t70\t30\t-1\t",
    ])

    blocks = ocr.parse_tesseract_tsv(tsv, page_number=7)
    text = ocr.join_tesseract_blocks_text(blocks)

    assert len(blocks) == 3
    assert blocks[0]["page_number"] == 7
    assert blocks[0]["block_number"] == 1
    assert blocks[0]["left"] == 10
    assert blocks[0]["top"] == 20
    assert blocks[0]["width"] == 90
    assert blocks[0]["height"] == 25
    assert blocks[0]["confidence"] == 96.4
    assert "Fourier Transform" in text
    assert "傅里叶变换" in text


def test_tesseract_tsv_parser_ignores_malformed_rows_and_invalid_confidence():
    tsv = "\n".join([
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
        "5\t1\t1\t1\t1\t1\t1\t2\t3\t4\tnot-a-number\tVoltage",
        "5\t1\t1\t1\t1\t2\tbad\t2\t3\t4\t93.0\tDivider",
        "5\t1\t1\t1\t1\t3\t20\t2\t3\t4\t92.0\t",
    ])

    blocks = ocr.parse_tesseract_tsv(tsv, page_number=2)

    assert len(blocks) == 1
    assert blocks[0]["text"] == "Voltage"
    assert blocks[0]["confidence"] is None


def test_tesseract_tsv_parser_rejects_missing_required_header():
    assert ocr.parse_tesseract_tsv("not\ta\ttsv\n1\t2\t3\n", page_number=1) == []
