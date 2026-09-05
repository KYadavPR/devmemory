"""Development memory module: searches previous attempts, finds past failures/regressions, and formats AI context."""

from typing import List, Dict, Any, Optional
import json
from devmemory.database import DevMemoryDB
from devmemory.models import VersionStatus


def _safe_json(val: Any) -> Any:
    if isinstance(val, (dict, list)):
        return val
    if not val:
        return {}
    try:
        return json.loads(val)
    except Exception:
        return {}


def find_similar_attempts(
    db: DevMemoryDB,
    intent: str = "",
    feature: str = "",
) -> List[Dict[str, Any]]:
    """Search previous development versions for failed or regressed attempts related to this feature or intent.

    Provides early warnings to developers and AI agents to prevent repeating known mistakes.
    """
    warnings: List[Dict[str, Any]] = []
    seen_ids = set()

    # 1. Search by feature
    if feature:
        feature_versions = db.get_versions_by_feature(feature)
        for v in feature_versions:
            status = v.get("status")
            is_reg = bool(v.get("is_regression"))
            if status in (VersionStatus.REGRESSION.value, VersionStatus.ERROR.value) or is_reg:
                vid = v.get("version_id")
                if vid not in seen_ids:
                    seen_ids.add(vid)
                    warnings.append({
                        "version_id": vid,
                        "feature": v.get("feature"),
                        "intent": v.get("intent"),
                        "agent": v.get("agent"),
                        "status": status,
                        "is_regression": is_reg,
                        "git_commit": v.get("git_commit", "")[:8],
                        "metrics": _safe_json(v.get("metrics")),
                        "analysis": v.get("analysis") or "Regression or error occurred.",
                        "recommendation": v.get("recommendation") or "Avoid repeating this approach.",
                        "timestamp": v.get("timestamp"),
                    })

    # 2. Search by intent query
    if intent and len(intent.strip()) > 2:
        try:
            matched = db.search_versions(intent.strip())
            for v in matched:
                status = v.get("status")
                is_reg = bool(v.get("is_regression"))
                if status in (VersionStatus.REGRESSION.value, VersionStatus.ERROR.value) or is_reg:
                    vid = v.get("version_id")
                    if vid not in seen_ids:
                        seen_ids.add(vid)
                        warnings.append({
                            "version_id": vid,
                            "feature": v.get("feature"),
                            "intent": v.get("intent"),
                            "agent": v.get("agent"),
                            "status": status,
                            "is_regression": is_reg,
                            "git_commit": v.get("git_commit", "")[:8],
                            "metrics": _safe_json(v.get("metrics")),
                            "analysis": v.get("analysis") or "Failed attempt detected.",
                            "recommendation": v.get("recommendation") or "Review diff before applying similar logic.",
                            "timestamp": v.get("timestamp"),
                        })
        except Exception:
            pass

    # Sort warnings with most recent first
    warnings.sort(key=lambda w: w.get("version_id", 0), reverse=True)
    return warnings


def format_agent_context(
    project_status: Dict[str, Any],
    warnings: List[Dict[str, Any]],
    features: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Format structured development context into a markdown prompt block for AI agents."""
    p_name = project_status.get("project_name", "Unknown Project")
    curr_v = project_status.get("current_version", 0)
    tot_v = project_status.get("total_versions", 0)
    latest_metrics = project_status.get("latest_metrics", {})

    lines = [
        f"### DevMemory Project Context: {p_name} (Current Version: v{curr_v})",
        f"- Total Development Iterations: {tot_v}",
    ]

    if latest_metrics:
        m_str = ", ".join([f"{k}: {v}" for k, v in latest_metrics.items()])
        lines.append(f"- Active Metrics Baseline: {m_str}")

    if features:
        done = [f["name"] for f in features if f.get("status") == "COMPLETE"]
        in_prog = [f["name"] for f in features if f.get("status") != "COMPLETE"]
        if done:
            lines.append(f"- Completed Features: {', '.join(done)}")
        if in_prog:
            lines.append(f"- Incomplete Features: {', '.join(in_prog)}")

    if warnings:
        lines.append("\n⚠️ **DEVELOPMENT MEMORY WARNINGS (Previous Regressions / Errors):**")
        for w in warnings[:5]:
            lines.append(
                f"- **v{w['version_id']} [{w['status']}]** (Feature: `{w.get('feature') or 'all'}`): "
                f"Intent: \"{w.get('intent') or 'N/A'}\". "
                f"Advice: {w.get('recommendation')}"
            )
    else:
        lines.append("\n✅ No relevant previous regressions recorded for this scope.")

    return "\n".join(lines)
