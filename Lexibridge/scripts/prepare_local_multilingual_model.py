#!/usr/bin/env python3
"""Explicitly prepare the pinned multilingual E5 snapshot outside the repo."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from huggingface_hub import snapshot_download


ROOT = Path(__file__).resolve().parents[1]
MODEL_ID = "intfloat/multilingual-e5-small"
MODEL_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
ALLOW_PATTERNS = (
    "1_Pooling/config.json",
    "README.md",
    "config.json",
    "model.safetensors",
    "modules.json",
    "sentence_bert_config.json",
    "sentencepiece.bpe.model",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        default=os.environ.get("LEXIBRIDGE_MODEL_CACHE_DIR", ""),
        help="Repository-external Hugging Face cache root.",
    )
    args = parser.parse_args()
    if not args.cache_dir:
        parser.error("--cache-dir or LEXIBRIDGE_MODEL_CACHE_DIR is required")
    cache_dir = Path(args.cache_dir).expanduser().resolve()
    if cache_dir == ROOT or ROOT in cache_dir.parents:
        parser.error("model cache must be outside the repository")
    cache_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=MODEL_ID,
        revision=MODEL_REVISION,
        cache_dir=str(cache_dir),
        allow_patterns=list(ALLOW_PATTERNS),
    )
    print(
        "Pinned multilingual model prepared outside the repository; "
        "set offline mode before application loading."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
