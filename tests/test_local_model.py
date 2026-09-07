"""The bundled on-device model: cache paths, resumable download, guarded load."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from devmemory.adapters import local_model as lm
from devmemory.cli.app import app
from devmemory.config import LocalModelSettings

runner = CliRunner()


@pytest.fixture
def cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "models"
    d.mkdir()
    monkeypatch.setattr(lm, "models_dir", lambda: d)
    return d


def _settings() -> LocalModelSettings:
    return LocalModelSettings(repo="acme/demo-GGUF", filename="demo-q4.gguf")


def test_model_path_is_under_cache(cache: Path) -> None:
    assert lm.model_path(_settings()) == cache / "demo-q4.gguf"


def test_is_downloaded_needs_a_real_sized_file(cache: Path) -> None:
    s = _settings()
    assert lm.is_downloaded(s) is False
    (cache / "demo-q4.gguf").write_bytes(b"stub")
    assert lm.is_downloaded(s) is False  # too small
    (cache / "demo-q4.gguf").write_bytes(b"0" * (lm._MIN_MODEL_BYTES + 1))
    assert lm.is_downloaded(s) is True


def test_download_streams_and_atomically_renames(
    cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"G" * (lm._MIN_MODEL_BYTES + 10)
    captured: dict[str, object] = {}

    class FakeResp(io.BytesIO):
        headers: dict[str, str] = {"Content-Length": str(len(payload))}  # noqa: RUF012

        def __enter__(self) -> FakeResp:
            return self

        def __exit__(self, *_a: object) -> None:
            return None

    def fake_urlopen(req: object, timeout: int = 0) -> FakeResp:
        captured["url"] = req.full_url  # type: ignore[attr-defined]
        return FakeResp(payload)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    seen: list[tuple[int, int]] = []
    path = lm.download_model(_settings(), on_progress=lambda d, t: seen.append((d, t)))

    assert path.read_bytes() == payload
    assert not path.with_name(path.name + ".part").exists()
    assert seen and seen[-1][0] == len(payload)
    assert "acme/demo-GGUF/resolve/main/demo-q4.gguf" in str(captured["url"])


def test_download_is_a_noop_when_present(cache: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (cache / "demo-q4.gguf").write_bytes(b"0" * (lm._MIN_MODEL_BYTES + 1))

    def boom(*_a: object, **_k: object) -> None:
        raise AssertionError("should not hit the network")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert lm.download_model(_settings()).exists()


def test_generate_without_runtime_raises_a_clean_error(
    cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (cache / "demo-q4.gguf").write_bytes(b"0" * (lm._MIN_MODEL_BYTES + 1))
    monkeypatch.setattr(lm, "_MODELS", {})
    monkeypatch.setitem(sys.modules, "llama_cpp", None)  # force `import llama_cpp` to fail
    with pytest.raises(lm.LocalModelError, match="local-llm extra"):
        lm.generate(_settings(), "hi", system="s")


def test_generate_needs_the_model_downloaded(
    cache: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(lm, "_MODELS", {})
    monkeypatch.setattr(lm, "runtime_available", lambda: True)
    monkeypatch.setitem(sys.modules, "llama_cpp", type(sys)("llama_cpp"))
    sys.modules["llama_cpp"].Llama = object  # type: ignore[attr-defined]
    with pytest.raises(lm.LocalModelError, match="not downloaded"):
        lm.generate(_settings(), "hi", system="s")


def test_generate_routes_through_llama(cache: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeLlama:
        def create_chat_completion(self, **_kw: object) -> dict[str, object]:
            return {"choices": [{"message": {"content": "SELECT 1"}}]}

    monkeypatch.setattr(lm, "_load", lambda _s: FakeLlama())
    assert lm.generate(_settings(), "q", system="s") == "SELECT 1"


def test_remove_model(cache: Path) -> None:
    (cache / "demo-q4.gguf").write_bytes(b"x" * 10)
    assert lm.remove_model(_settings()) is True
    assert lm.remove_model(_settings()) is False


def test_cli_model_status_runs_outside_project(monkeypatch: pytest.MonkeyPatch) -> None:
    result = runner.invoke(app, ["model", "status"])
    assert result.exit_code == 0
    assert "runtime" in result.output


def test_cli_model_pull_without_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lm, "runtime_available", lambda: False)
    result = runner.invoke(app, ["model", "pull"])
    assert result.exit_code == 1
    assert "local-llm" in result.output
