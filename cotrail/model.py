"""The sentence encoder of the memory: multilingual-e5-base as int8 ONNX, run by onnxruntime (no PyTorch).

Weights: Xenova/multilingual-e5-base (an ONNX export of intfloat/multilingual-e5-base, MIT) at a pinned revision,
`onnx/model_quantized.onnx` (dynamic int8, ~280 MB) + `tokenizer.json`. Downloaded once, only with the user's consent
(`cotrail setup`); after that every process runs with the Hugging Face hub in offline mode, so a memory of private
conversations never touches the network. This module does not import huggingface_hub at module level: its offline
flag is read when it is first imported.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from cotrail.embed import Encoder

REPO = "Xenova/multilingual-e5-base"
REVISION = "1ec9243030a27d1a115d5c340572074c125b58b2"
ONNX_FILE = "onnx/model_quantized.onnx"
FILES = [ONNX_FILE, "tokenizer.json", "config.json"]
SIZE_MB = 300  # model_quantized.onnx 279 MB + tokenizer.json 17 MB
ENCODER = f"e5-base-onnx-int8@{REVISION[:7]}"  # recorded in each store: vectors of another encoder do not mix
URL = f"https://huggingface.co/{REPO}/tree/{REVISION}"


class ModelMissing(RuntimeError):
    pass


class DownloadFailed(RuntimeError):
    pass


def hub_cache() -> Path:
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    return Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"


def snapshot_dir() -> Path:
    return hub_cache() / ("models--" + REPO.replace("/", "--")) / "snapshots" / REVISION


def is_cached() -> bool:
    d = snapshot_dir()
    return all((d / f).exists() for f in FILES)


def go_offline() -> None:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")


def prepare() -> None:
    """Before loading the encoder: offline when the model is cached; otherwise refuse unless downloads were allowed
    (COTRAIL_ALLOW_DOWNLOAD=1) - the MCP server must never start a download nobody agreed to."""
    if is_cached():
        go_offline()
    elif os.environ.get("COTRAIL_ALLOW_DOWNLOAD") != "1":
        raise ModelMissing(f"The encoder model {REPO} is not downloaded yet (~{SIZE_MB} MB). "
                           "Run `cotrail setup` once to download it.")  # fmt: skip
    else:
        download()
        go_offline()


def download(progress: bool = True) -> Path:
    """Fetch the pinned files. A network failure becomes DownloadFailed with a message for people, not a traceback:
    what was not downloaded, from where, and how to retry (a partial download resumes)."""
    if not progress:
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    try:
        from huggingface_hub import snapshot_download

        p = snapshot_download(REPO, revision=REVISION, allow_patterns=FILES)
    except Exception as e:  # noqa: BLE001 - every failure (DNS, proxy, timeout, HTTP 4xx/5xx, disk) gets the same help
        reason = str(e).strip().splitlines()[0][:200] if str(e).strip() else type(e).__name__
        raise DownloadFailed(
            f"Could not download the encoder model {REPO} ({', '.join(FILES)}, ~{SIZE_MB} MB) from {URL}.\n"
            f"Reason: {type(e).__name__}: {reason}\n"
            "Check the internet connection (or set HTTPS_PROXY), then run `cotrail setup` again; "
            "a partial download resumes.") from None  # fmt: skip
    if not is_cached():
        raise DownloadFailed(f"The download of {REPO} finished but files are missing in {snapshot_dir()}; "
                             "run `cotrail setup` again.")  # fmt: skip
    return Path(p)


class OnnxE5Encoder(Encoder):
    """multilingual-e5-base: stored sentences get "passage: ", the question gets "query: "; mean pooling over the
    attention mask, L2-normalised (as sentence-transformers does for this model)."""

    def __init__(self, model_dir: str | Path | None = None, batch: int = 32) -> None:
        super().__init__()
        import onnxruntime as ort
        from tokenizers import Tokenizer

        d = Path(model_dir) if model_dir else snapshot_dir()
        self.tok = Tokenizer.from_file(str(d / "tokenizer.json"))
        self.tok.enable_truncation(512)
        self.tok.enable_padding(pad_id=1, pad_token="<pad>")  # XLM-R pad
        so = ort.SessionOptions()
        so.log_severity_level = 3
        self.sess = ort.InferenceSession(str(d / ONNX_FILE), so, providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.sess.get_inputs()}
        self.batch, self.name, self.dim = batch, ENCODER, 768

    def _encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))  # similar lengths in a batch: less padding
        for b in range(0, len(order), self.batch):
            idx = order[b:b + self.batch]
            enc = self.tok.encode_batch([texts[i] for i in idx])
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self.inputs:
                feed["token_type_ids"] = np.zeros_like(ids)
            h = self.sess.run(None, feed)[0]
            m = mask[..., None].astype(np.float32)
            out[idx] = (h * m).sum(1) / np.clip(m.sum(1), 1e-9, None)
        return out

    def encode(self, texts: list[str]) -> np.ndarray:
        return super().encode([f"passage: {t}" for t in texts])

    def one(self, text: str) -> np.ndarray:
        return super().encode([f"query: {text}"])[0]
