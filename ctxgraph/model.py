"""The sentence encoder of the memory: intfloat/multilingual-e5-base at a pinned revision.

Downloaded once, only with the user's consent (`ctxgraph setup`); after that every process runs with the Hugging Face
hub in offline mode, so a memory of private conversations never touches the network. This module does not import
huggingface_hub at module level: its offline flag is read when it is first imported.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO = "intfloat/multilingual-e5-base"
REVISION = "d128750597153bb5987e10b1c3493a34e5a4502a"
# only what sentence-transformers needs (the repo also holds pytorch_model.bin and ONNX copies, ~2 GB more)
FILES = ["model.safetensors", "config.json", "modules.json", "sentence_bert_config.json", "1_Pooling/config.json",
         "sentencepiece.bpe.model", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json"]
SIZE_MB = 1130  # model.safetensors 1.11 GB + tokenizer files


class ModelMissing(RuntimeError):
    pass


def hub_cache() -> Path:
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    return Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"


def snapshot_dir() -> Path:
    return hub_cache() / ("models--" + REPO.replace("/", "--")) / "snapshots" / REVISION


def is_cached() -> bool:
    d = snapshot_dir()
    return all((d / f).exists() for f in ("model.safetensors", "config.json", "modules.json", "tokenizer.json"))


def go_offline() -> None:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def prepare() -> None:
    """Before loading the encoder: offline when the model is cached; otherwise refuse unless downloads were allowed
    (CTXGRAPH_ALLOW_DOWNLOAD=1) - the MCP server must never start a 1 GB download nobody agreed to."""
    if is_cached():
        go_offline()
    elif os.environ.get("CTXGRAPH_ALLOW_DOWNLOAD") != "1":
        raise ModelMissing(f"The encoder model {REPO} is not downloaded yet (~{SIZE_MB / 1000:.1f} GB). "
                           "Run `ctxgraph setup` once to download it.")  # fmt: skip


def download(progress: bool = True) -> Path:
    from huggingface_hub import snapshot_download

    if not progress:
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    p = snapshot_download(REPO, revision=REVISION, allow_patterns=FILES)
    return Path(p)
