import hashlib
import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
HTML = (FRONTEND / "index.html").read_text(encoding="utf-8")
READER_MODULE = FRONTEND / "js" / "pdfjs-concept-reader.mjs"
MAPPER_MODULE = FRONTEND / "js" / "pdf-selection-mapper.mjs"
MANIFEST = FRONTEND / "vendor" / "pdfjs" / "manifest.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_sha256(root: Path, relative_root: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    for path in files:
        relative = path.relative_to(relative_root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256(path).encode("ascii"))
        digest.update(b"\n")
    return len(files), digest.hexdigest()


def test_pdfjs_is_pinned_self_hosted_and_auditable():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["package"] == "pdfjs-dist"
    assert manifest["version"] == "6.2.108"
    assert manifest["upstream"] == "https://github.com/mozilla/pdf.js"
    assert manifest["license"] == "Apache-2.0"
    for relative_path, expected_hash in manifest["files"].items():
        path = FRONTEND / "vendor" / "pdfjs" / relative_path
        assert path.is_file()
        assert _sha256(path) == expected_hash
    vendor_root = FRONTEND / "vendor" / "pdfjs"
    for relative_path, contract in manifest["asset_directories"].items():
        count, digest = _tree_sha256(vendor_root / relative_path, vendor_root)
        assert count == contract["file_count"]
        assert digest == contract["sha256"]
    license_text = (FRONTEND / "vendor" / "pdfjs" / "LICENSE").read_text(
        encoding="utf-8"
    )
    assert "Apache License" in license_text
    assert "Version 2.0" in license_text


def test_student_reader_uses_local_pdfjs_canvas_and_text_layer_not_iframe():
    reader_section = HTML[
        HTML.index("function renderStudentMaterialReader"):
        HTML.index("function renderSubscription")
    ]
    assert "./js/pdfjs-concept-reader.mjs" in HTML
    assert "student-pdf-canvas" in reader_section
    assert "student-pdf-text-layer" in reader_section
    assert "student-pdf-page" in reader_section
    assert "iframe" not in reader_section.lower()
    assert "可选取的解析文本" not in reader_section
    assert "在 PDF 页面文字上直接选择" in reader_section
    assert "cdn" not in reader_section.lower()
    assert "unpkg" not in HTML.lower()
    assert "jsdelivr" not in HTML.lower()


def test_pdfjs_module_renders_the_same_page_canvas_and_selectable_text_layer():
    source = READER_MODULE.read_text(encoding="utf-8")
    for marker in (
        "pdfjs-dist@6.2.108",
        "getDocument",
        "getPage",
        "getTextContent",
        "new pdfjsLib.TextLayer",
        "page.render",
        "pdf.worker.mjs",
        "capturePdfConceptSelection",
        "mapPdfSelectionToReaderItem",
    ):
        assert marker in source
    assert "fetch(" not in source
    assert "Authorization" not in source


def test_pdf_selection_mapping_is_unique_bounded_and_fail_closed():
    assert shutil.which("node"), "Node.js is part of the controlled frontend runtime"
    program = f"""
      import {{ mapPdfSelectionToReaderItem }} from {json.dumps(MAPPER_MODULE.as_uri())};
      const items = [
        {{chunk_uid: 'c1', page_number: 1, selectable: true,
          text: 'Electric charge is a physical property of matter.'}},
        {{chunk_uid: 'c2', page_number: 1, selectable: true,
          text: 'Electric potential is potential energy per unit charge.'}}
      ];
      const direct = mapPdfSelectionToReaderItem({{
        selectedText: 'Electric charge', pagePrefixText: '',
        pageText: items.map(x => x.text).join(' '), items
      }});
      if (direct.chunkUid !== 'c1' || direct.selectionStart !== 0 ||
          direct.selectionEnd !== 15 || direct.selectedText !== 'Electric charge') {{
        throw new Error(JSON.stringify(direct));
      }}
      const whitespace = mapPdfSelectionToReaderItem({{
        selectedText: 'Electric   potential',
        pagePrefixText: items[0].text + ' ',
        pageText: items.map(x => x.text).join(' '), items
      }});
      if (whitespace.chunkUid !== 'c2' || whitespace.selectedText !== 'Electric potential') {{
        throw new Error(JSON.stringify(whitespace));
      }}
      const omittedLayoutSpace = mapPdfSelectionToReaderItem({{
        selectedText: 'Electricpotential',
        pagePrefixText: items[0].text,
        pageText: items.map(x => x.text.replaceAll(' ', '')).join(''),
        items
      }});
      if (omittedLayoutSpace.chunkUid !== 'c2' ||
          omittedLayoutSpace.selectedText !== 'Electric potential' ||
          omittedLayoutSpace.mappingMode !== 'PDF_TEXT_LAYER_COMPACT_WHITESPACE') {{
        throw new Error(JSON.stringify(omittedLayoutSpace));
      }}
      const repeatedItem = {{chunk_uid: 'repeat', page_number: 1, selectable: true,
        text: 'Electric potential. Electric potential is energy per unit charge.'}};
      const repeated = mapPdfSelectionToReaderItem({{
        selectedText: 'Electric potential',
        pagePrefixText: 'Electric potential. ',
        pageText: repeatedItem.text,
        items: [repeatedItem]
      }});
      if (repeated.chunkUid !== 'repeat' || repeated.selectionStart !== 20) {{
        throw new Error(JSON.stringify(repeated));
      }}
      for (const test of [
        {{selectedText: 'unit charge', pagePrefixText: '', pageText: '',
          items: [items[1], {{...items[1], chunk_uid: 'c3'}}], code: 'PDF_SELECTION_AMBIGUOUS'}},
        {{selectedText: 'not in governed text', pagePrefixText: '', pageText: '',
          items, code: 'PDF_SELECTION_NOT_MAPPED'}},
        {{selectedText: 'x'.repeat(181), pagePrefixText: '', pageText: '',
          items, code: 'PDF_SELECTION_TOO_LONG'}}
      ]) {{
        let code = '';
        try {{ mapPdfSelectionToReaderItem(test); }} catch (error) {{ code = error.code; }}
        if (code !== test.code) throw new Error(`expected ${{test.code}}, got ${{code}}`);
      }}
    """
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", program],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_direct_capture_reuses_existing_authorized_blob_and_query_contract():
    assert "/api/student/concept-materials/${encodeURIComponent(sourceUid)}/file" in HTML
    assert "URL.createObjectURL" in HTML
    assert "URL.revokeObjectURL" in HTML
    assert "/api/student/concept-queries" in HTML
    assert "chunk_uid: active.chunkUid" in HTML
    assert "selection_start: active.selectionStart" in HTML
    assert "selection_end: active.selectionEnd" in HTML
    assert 'headers.Authorization = `Bearer ${state.token}`' in HTML
    assert "?token=" not in HTML
