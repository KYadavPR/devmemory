"""The CLI loads a `.env` for credentials; real env vars still win."""

from __future__ import annotations

from pathlib import Path

import pytest

from devmemory.cli.app import _load_dotenv


def test_load_dotenv_reads_a_local_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("DEVMEMORY_TEST_KEY=from-dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEVMEMORY_TEST_KEY", raising=False)

    _load_dotenv()
    import os

    assert os.environ.get("DEVMEMORY_TEST_KEY") == "from-dotenv"


def test_real_env_var_wins_over_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("DEVMEMORY_TEST_KEY=from-dotenv\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEVMEMORY_TEST_KEY", "from-real-env")

    _load_dotenv()
    import os

    assert os.environ.get("DEVMEMORY_TEST_KEY") == "from-real-env"


def test_no_dotenv_is_fine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _load_dotenv()  # no .env anywhere - must not raise
