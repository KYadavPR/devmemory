"""DevMemory configuration management."""

import json
import os
from dataclasses import dataclass, field
from typing import Optional


DEVMEMORY_DIR = ".devmemory"
CONFIG_FILE = "config.json"


@dataclass
class DevMemoryConfig:
    """Project-level DevMemory configuration."""

    project_id: str = ""
    project_name: str = ""
    project_path: str = ""
    databricks_host: Optional[str] = None
    databricks_http_path: Optional[str] = None
    databricks_token: Optional[str] = None
    databricks_catalog: str = "devmemory_analytics"
    databricks_schema: str = "development_intelligence"
    web_host: str = "127.0.0.1"
    web_port: int = 8765

    @classmethod
    def load(cls, project_path: str) -> "DevMemoryConfig":
        """Load config from .devmemory/config.json."""
        config_path = os.path.join(project_path, DEVMEMORY_DIR, CONFIG_FILE)
        if not os.path.exists(config_path):
            # Return defaults with inferred project name
            return cls(
                project_path=project_path,
                project_name=os.path.basename(project_path),
                project_id=os.path.basename(project_path).lower().replace(" ", "-"),
            )
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)

    @classmethod
    def create(
        cls, project_path: str, name: str = "", project_id: str = ""
    ) -> "DevMemoryConfig":
        """Create a new config and save to disk."""
        dm_dir = os.path.join(project_path, DEVMEMORY_DIR)
        os.makedirs(dm_dir, exist_ok=True)
        os.makedirs(os.path.join(dm_dir, "artifacts"), exist_ok=True)

        # Add .devmemory to .gitignore if it exists
        gitignore_path = os.path.join(project_path, ".gitignore")
        _ensure_gitignore(gitignore_path)

        config = cls(
            project_path=project_path,
            project_name=name or os.path.basename(project_path),
            project_id=project_id
            or os.path.basename(project_path).lower().replace(" ", "-"),
        )
        config.save()
        return config

    def save(self):
        """Save config to disk."""
        config_path = os.path.join(self.project_path, DEVMEMORY_DIR, CONFIG_FILE)
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        data = {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "project_path": self.project_path,
            "databricks_host": self.databricks_host,
            "databricks_http_path": self.databricks_http_path,
            "databricks_token": self.databricks_token,
            "databricks_catalog": self.databricks_catalog,
            "databricks_schema": self.databricks_schema,
            "web_host": self.web_host,
            "web_port": self.web_port,
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @property
    def db_path(self) -> str:
        return os.path.join(self.project_path, DEVMEMORY_DIR, "devmemory.db")

    @property
    def artifacts_dir(self) -> str:
        return os.path.join(self.project_path, DEVMEMORY_DIR, "artifacts")

    @property
    def devmemory_dir(self) -> str:
        return os.path.join(self.project_path, DEVMEMORY_DIR)


def _ensure_gitignore(gitignore_path: str):
    """Add .devmemory/ to .gitignore if not already present."""
    entry = ".devmemory/"
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8") as f:
            content = f.read()
        if entry not in content:
            with open(gitignore_path, "a", encoding="utf-8") as f:
                f.write(f"\n# DevMemory local data\n{entry}\n")
    else:
        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.write(f"# DevMemory local data\n{entry}\n")
