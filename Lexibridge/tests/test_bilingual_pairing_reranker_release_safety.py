from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_no_reranker_weights_or_cache_are_tracked():
    forbidden_suffixes = {".bin", ".onnx", ".pt", ".pth", ".safetensors"}
    tracked = [
        Path(path)
        for path in subprocess.check_output(
            ["git", "ls-files"],
            cwd=ROOT,
            text=True,
        ).splitlines()
        if Path(path).suffix.lower() in forbidden_suffixes
    ]
    assert tracked == []


def test_reranker_cache_contract_is_repository_external():
    text = (ROOT / "backend/services/local_bilingual_reranker.py").read_text()
    assert "outside the repository" in text
    assert "local_files_only=True" in text
    assert "trust_remote_code=False" in text
