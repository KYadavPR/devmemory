"""Feature-level services: status roll-up and per-feature evolution."""

from __future__ import annotations

from pydantic import BaseModel

from devmemory.domain.enums import FeatureStatus, VersionStatus
from devmemory.domain.errors import DevMemoryError
from devmemory.domain.models import DevelopmentVersion, Feature
from devmemory.services.context import ProjectContext
from devmemory.storage.repositories import FeatureRepository
from devmemory.storage.versions import VersionRepository


class FeatureNotFoundError(DevMemoryError):
    exit_code = 9


class FeatureWithHistory(BaseModel):
    feature: Feature
    versions: list[DevelopmentVersion]

    @property
    def rolled_up_status(self) -> FeatureStatus:
        return _roll_up(self.versions)


def list_features(ctx: ProjectContext) -> list[FeatureWithHistory]:
    features = FeatureRepository(ctx.db).list_all(ctx.config.project_id)
    versions = VersionRepository(ctx.db)
    return [
        FeatureWithHistory(feature=f, versions=versions.for_feature(f.feature_id)) for f in features
    ]


def get_feature(ctx: ProjectContext, ref: str) -> FeatureWithHistory:
    repo = FeatureRepository(ctx.db)
    feature = repo.get(ref) or repo.get_by_name(ctx.config.project_id, ref)
    if feature is None:
        # tolerate a slugged id without the project prefix
        feature = repo.get(f"{ctx.config.project_id}:{ref}")
    if feature is None:
        raise FeatureNotFoundError(
            f"No feature matches {ref!r}.",
            hint="Run `devmemory features` to list them.",
        )
    versions = VersionRepository(ctx.db).for_feature(feature.feature_id)
    return FeatureWithHistory(feature=feature, versions=versions)


def refresh_feature_status(ctx: ProjectContext, feature_id: str) -> Feature | None:
    """Recompute and persist a feature's roll-up status from its versions."""
    repo = FeatureRepository(ctx.db)
    feature = repo.get(feature_id)
    if feature is None:
        return None
    versions = VersionRepository(ctx.db).for_feature(feature_id)
    return repo.upsert(
        feature.project_id,
        feature.name,
        status=_roll_up(versions),
        derived_from=feature.derived_from,
    )


def _roll_up(versions: list[DevelopmentVersion]) -> FeatureStatus:
    if not versions:
        return FeatureStatus.NOT_STARTED
    latest = versions[-1]
    if latest.status is VersionStatus.SUCCESS:
        return FeatureStatus.COMPLETE
    if latest.status in (VersionStatus.REGRESSION, VersionStatus.PARTIAL_SUCCESS):
        return FeatureStatus.PARTIAL
    if latest.status is VersionStatus.ERROR:
        return FeatureStatus.FAILED
    return FeatureStatus.IN_PROGRESS


__all__ = [
    "FeatureNotFoundError",
    "FeatureWithHistory",
    "get_feature",
    "list_features",
    "refresh_feature_status",
]
