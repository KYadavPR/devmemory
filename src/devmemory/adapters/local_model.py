"""A bundled on-device LLM (llama.cpp), for a real model with zero setup cost.

Nothing here reaches the network at import time. The GGUF is downloaded once, on
an explicit ``devmemory model pull`` (or the first Ask/analyze that needs it),
into a user-global cache, and every call after that is fully local and offline.

The runtime (`llama-cpp-python`) is an optional extra::

    pip install "devmemory-cli[local-llm]"

so :func:`runtime_available` is ``False`` on a plain install and every caller
degrades to the next provider (a cloud key, or the built-in rules engine).
"""

from __future__ import annotations

import os
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from platformdirs import user_cache_dir

from devmemory.config import LocalModelSettings
from devmemory.domain.errors import DevMemoryError
from devmemory.logging import get_logger

_log = get_logger(__name__)

# llama.cpp is not safe for concurrent calls into one model; serialise everything.
_LOCK = threading.RLock()
_MODELS: dict[str, Any] = {}  # gguf path -> llama_cpp.Llama

_MIN_MODEL_BYTES = 50_000_000  # a real quant is far bigger; guards against a stub
_CHUNK = 1 << 20

ProgressFn = Callable[[int, int], None]


class LocalModelError(DevMemoryError):
    """The local model runtime is missing, or the model is not downloaded."""

    exit_code = 6


# --- filesystem ---------------------------------------------------------------


def models_dir() -> Path:
    d = Path(user_cache_dir("devmemory", appauthor=False)) / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def model_path(settings: LocalModelSettings) -> Path:
    return models_dir() / settings.filename


def is_downloaded(settings: LocalModelSettings) -> bool:
    p = model_path(settings)
    return p.is_file() and p.stat().st_size >= _MIN_MODEL_BYTES


def runtime_available() -> bool:
    try:
        import llama_cpp  # noqa: F401
    except Exception:  # pragma: no cover - import side effects vary by platform
        return False
    return True


def is_ready(settings: LocalModelSettings) -> bool:
    return runtime_available() and is_downloaded(settings)


# --- download ----------------------------------------------------------------


def download_url(settings: LocalModelSettings) -> str:
    return f"https://huggingface.co/{settings.repo}/resolve/main/{settings.filename}?download=true"


def download_model(
    settings: LocalModelSettings, *, on_progress: ProgressFn | None = None
) -> Path:
    """Fetch the GGUF into the cache (resumable). No-op if already present."""
    dest = model_path(settings)
    if is_downloaded(settings):
        return dest

    part = dest.with_name(dest.name + ".part")
    resume_from = part.stat().st_size if part.exists() else 0
    req = urllib.request.Request(  # noqa: S310 - fixed https host, path from config
        download_url(settings),
        headers={"User-Agent": "devmemory-cli"},
    )
    if resume_from:
        req.add_header("Range", f"bytes={resume_from}-")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            declared = int(resp.headers.get("Content-Length") or 0)
            total = declared + resume_from
            downloaded = resume_from
            with part.open("ab" if resume_from else "wb") as fh:
                while True:
                    chunk = resp.read(_CHUNK)
                    if not chunk:
                        break
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if on_progress is not None:
                        on_progress(downloaded, total)
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and part.exists():  # range not satisfiable = already whole
            part.replace(dest)
            return dest
        raise LocalModelError(f"model download failed (HTTP {exc.code}): {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise LocalModelError(f"model download failed: {exc.reason}") from exc

    if part.stat().st_size < _MIN_MODEL_BYTES:
        part.unlink(missing_ok=True)
        raise LocalModelError("downloaded file is too small - the source URL may have moved")
    part.replace(dest)
    _log.info("local_model.downloaded", file=settings.filename, bytes=dest.stat().st_size)
    return dest


def remove_model(settings: LocalModelSettings) -> bool:
    removed = False
    for p in (model_path(settings), model_path(settings).with_name(settings.filename + ".part")):
        if p.exists():
            p.unlink()
            removed = True
    _MODELS.pop(str(model_path(settings)), None)
    return removed


# --- inference -------------------------------------------------------------


def _load(settings: LocalModelSettings) -> Any:
    key = str(model_path(settings))
    cached = _MODELS.get(key)
    if cached is not None:
        return cached
    try:
        from llama_cpp import Llama
    except ImportError as exc:
        raise LocalModelError(
            "the local-llm extra is not installed",
            hint='pip install "devmemory-cli[local-llm]"',
        ) from exc
    if not is_downloaded(settings):
        raise LocalModelError(
            "the local model is not downloaded",
            hint="run `devmemory model pull`",
        )
    llm = Llama(
        model_path=key,
        n_ctx=settings.context_size,
        n_threads=settings.threads or os.cpu_count(),
        n_gpu_layers=settings.gpu_layers,
        chat_format="chatml",
        verbose=False,
    )
    _MODELS[key] = llm
    _log.info("local_model.loaded", file=settings.filename)
    return llm


def generate(
    settings: LocalModelSettings,
    prompt: str,
    *,
    system: str,
    max_tokens: int | None = None,
    temperature: float = 0.0,
    json_object: bool = False,
) -> str:
    """One chat turn against the local model. Serialised across threads."""
    with _LOCK:
        llm = _load(settings)
        kwargs: dict[str, Any] = {}
        if json_object:
            kwargs["response_format"] = {"type": "json_object"}
        out = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens or settings.max_tokens,
            temperature=temperature,
            **kwargs,
        )
    choices = out.get("choices") or []
    if not choices:
        return ""
    return (choices[0].get("message") or {}).get("content") or ""


__all__ = [
    "LocalModelError",
    "download_model",
    "generate",
    "is_downloaded",
    "is_ready",
    "model_path",
    "models_dir",
    "remove_model",
    "runtime_available",
]
