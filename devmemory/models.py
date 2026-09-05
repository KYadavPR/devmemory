"""DevMemory data models."""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime


class VersionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    ERROR = "ERROR"
    REGRESSION = "REGRESSION"
    IN_PROGRESS = "IN_PROGRESS"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class FeatureStatus(str, Enum):
    COMPLETE = "COMPLETE"
    IN_PROGRESS = "IN_PROGRESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    NOT_STARTED = "NOT_STARTED"


class DevelopmentVersion(BaseModel):
    """A complete development record — one meaningful change to the project."""

    version_id: int = 0
    project_id: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)

    # Entire context
    checkpoint_id: Optional[str] = None
    session_id: Optional[str] = None
    agent: Optional[str] = None
    intent: Optional[str] = None

    # Git context
    git_commit: str = ""
    parent_commit: Optional[str] = None
    branch: Optional[str] = None
    changed_files: list[str] = Field(default_factory=list)
    additions: int = 0
    deletions: int = 0

    # Results
    feature: Optional[str] = None
    status: VersionStatus = VersionStatus.NEEDS_REVIEW
    tests_passed: Optional[int] = None
    tests_failed: Optional[int] = None
    metrics: dict = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)

    # Analysis
    analysis: Optional[str] = None
    recommendation: Optional[str] = None
    is_regression: bool = False

    # Artifact
    artifact_path: Optional[str] = None


class Feature(BaseModel):
    """A tracked project feature with its evolution history."""

    name: str
    status: FeatureStatus = FeatureStatus.NOT_STARTED
    versions: list[int] = Field(default_factory=list)
    latest_metrics: dict = Field(default_factory=dict)


class ProjectState(BaseModel):
    """Snapshot of the overall project state."""

    project_id: str
    project_name: str
    current_version: int = 0
    total_versions: int = 0
    features: list[Feature] = Field(default_factory=list)
    completion_percentage: float = 0.0
    total_tests_passed: Optional[int] = None
    total_tests_failed: Optional[int] = None
