"""Project snapshots: a compressed archive of the source tree at a version's commit.

Built from ``git archive`` (so it is exactly the committed state - no working-tree
noise), then repacked through Python's ``tarfile`` to apply the configured
exclusions and record a content hash. Git remains the authoritative history; the
snapshot is a reproducibility convenience.
"""

from __future__ import annotations

import hashlib
import io
import tarfile
from datetime import UTC, datetime
from pathlib import Path

from devmemory.adapters.git import GitAdapter
from devmemory.domain.errors import StorageError
from devmemory.domain.models import Artifact
from devmemory.logging import get_logger

_log = get_logger(__name__)

_DEFAULT_EXCLUDE = (".git", ".devmemory", ".venv", "venv", "node_modules", "__pycache__")


class ArtifactStore:
    def __init__(self, artifacts_dir: Path, git: GitAdapter) -> None:
        self._dir = artifacts_dir
        self._git = git

    def create_snapshot(
        self,
        *,
        version_id: str,
        commit_sha: str,
        exclude: list[str] | None = None,
    ) -> Artifact:
        self._dir.mkdir(parents=True, exist_ok=True)
        patterns = tuple(exclude) if exclude is not None else _DEFAULT_EXCLUDE
        raw = self._git.archive_tar(commit_sha)

        out_path = self._dir / f"{version_id}_{commit_sha[:7]}.tar.gz"
        digest = hashlib.sha256()
        kept = 0
        try:
            with (
                tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as src,
                tarfile.open(out_path, mode="w:gz") as dst,
            ):
                for member in src.getmembers():
                    if _excluded(member.name, patterns):
                        continue
                    extracted = src.extractfile(member) if member.isfile() else None
                    data = extracted.read() if extracted is not None else b""
                    if member.isfile():
                        digest.update(member.name.encode())
                        digest.update(data)
                    dst.addfile(member, io.BytesIO(data) if member.isfile() else None)
                    kept += 1
        except (tarfile.TarError, OSError) as exc:
            raise StorageError(f"could not build snapshot for {version_id}: {exc}") from exc

        size = out_path.stat().st_size
        _log.info(
            "artifact.created", version=version_id, path=str(out_path), files=kept, bytes=size
        )
        return Artifact(
            artifact_id=_artifact_id(version_id, commit_sha),
            version_id=version_id,
            path=str(out_path.relative_to(self._dir.parent.parent))
            if _is_relative(out_path, self._dir.parent.parent)
            else str(out_path),
            type="project_snapshot",
            size_bytes=size,
            sha256=digest.hexdigest(),
            created_at=datetime.now(UTC),
        )

    def extract(self, artifact: Artifact, dest: Path) -> None:
        archive = self._resolve(artifact)
        if not archive.is_file():
            raise StorageError(f"artifact archive missing: {archive}")
        dest.mkdir(parents=True, exist_ok=True)
        try:
            with tarfile.open(archive, mode="r:gz") as tf:
                tf.extractall(dest, filter="data")
        except (tarfile.TarError, OSError) as exc:
            raise StorageError(f"could not extract {archive}: {exc}") from exc

    def _resolve(self, artifact: Artifact) -> Path:
        p = Path(artifact.path)
        return p if p.is_absolute() else self._dir.parent.parent / p


def _excluded(name: str, patterns: tuple[str, ...]) -> bool:
    parts = name.replace("\\", "/").split("/")
    return any(p in parts for p in patterns)


def _artifact_id(version_id: str, commit_sha: str) -> str:
    return hashlib.sha256(f"{version_id}:{commit_sha}".encode()).hexdigest()[:16]


def _is_relative(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True


__all__ = ["ArtifactStore"]
