"""Demo data seeder for DevMemory hackathon demonstration."""

import json
from datetime import datetime, timedelta
from devmemory import init, DevMemoryProject
from devmemory.models import VersionStatus, FeatureStatus


DEMO_VERSIONS = [
    {
        "version_id": 1,
        "timestamp": (datetime.now() - timedelta(hours=7)).isoformat(),
        "checkpoint_id": "01K9TQ8ZP7X3F5M2WVJ4CNRB6D",
        "session_id": "sess_01k9tq8z",
        "agent": "claude-code",
        "intent": "Implement baseline ResNet backbone model and training pipeline",
        "git_commit": "a72c91f043d84f88b02131972a912803bce30b11",
        "parent_commit": None,
        "branch": "main",
        "changed_files": ["model.py", "train.py", "dataset.py"],
        "additions": 340,
        "deletions": 0,
        "feature": "image-classification",
        "status": VersionStatus.SUCCESS.value,
        "tests_passed": 100,
        "tests_failed": 3,
        "metrics": {"accuracy": 84.2, "latency_ms": 320.0, "val_loss": 0.45},
        "errors": [],
        "analysis": "Baseline ResNet-50 initialized and converged over 10 initial epochs.",
        "recommendation": "State is stable. Introduce data augmentations to increase accuracy.",
        "is_regression": 0,
    },
    {
        "version_id": 2,
        "timestamp": (datetime.now() - timedelta(hours=5, minutes=30)).isoformat(),
        "checkpoint_id": "01K9TQ9AP8Y4G6N3XWK5DOSC7E",
        "session_id": "sess_01k9tq9a",
        "agent": "claude-code",
        "intent": "Add RandAugment and CosineAnnealing learning rate schedule",
        "git_commit": "3ef82b1842d04a99c13242083b023914cdf41c22",
        "parent_commit": "a72c91f043d84f88b02131972a912803bce30b11",
        "branch": "main",
        "changed_files": ["train.py", "transforms.py"],
        "additions": 85,
        "deletions": 22,
        "feature": "image-classification",
        "status": VersionStatus.SUCCESS.value,
        "tests_passed": 138,
        "tests_failed": 5,
        "metrics": {"accuracy": 89.2, "latency_ms": 310.0, "val_loss": 0.32},
        "errors": [],
        "analysis": "Accuracy improved: accuracy: 84.20 -> 89.20. Passing tests increased.",
        "recommendation": "State is stable. Proceed to fine-tuning hyperparameters.",
        "is_regression": 0,
    },
    {
        "version_id": 3,
        "timestamp": (datetime.now() - timedelta(hours=4)).isoformat(),
        "checkpoint_id": "01K9TQABC9Z5H7P4YXL6EPTD8F",
        "session_id": "sess_01k9tqab",
        "agent": "cursor-agent",
        "intent": "Increase learning rate to 0.05 and disable gradient clipping for faster training",
        "git_commit": "5d910fe283e15b00d24353194c134025def52d33",
        "parent_commit": "3ef82b1842d04a99c13242083b023914cdf41c22",
        "branch": "main",
        "changed_files": ["train.py", "config.yaml"],
        "additions": 42,
        "deletions": 18,
        "feature": "image-classification",
        "status": VersionStatus.REGRESSION.value,
        "tests_passed": 130,
        "tests_failed": 13,
        "metrics": {"accuracy": 72.1, "latency_ms": 315.0, "val_loss": 0.88},
        "errors": ["Validation Divergence: gradient explosion detected at epoch 4"],
        "analysis": "REGRESSION DETECTED: Test failures increased from 5 to 13; Metric 'accuracy' regressed from 89.20 to 72.10 (-19.2%).",
        "recommendation": "Do not deploy this change! Disabling gradient clipping caused gradient instability. Revert learning rate to 0.001.",
        "is_regression": 1,
    },
    {
        "version_id": 4,
        "timestamp": (datetime.now() - timedelta(hours=3)).isoformat(),
        "checkpoint_id": "01K9TQBDE0A6J8Q5ZYM7FQVE9G",
        "session_id": "sess_01k9tqbd",
        "agent": "claude-code",
        "intent": "Restore gradient clipping, restore LR to 0.001, and apply label smoothing 0.1",
        "git_commit": "7fa210b394f26c11e35464205d245136efa63e44",
        "parent_commit": "5d910fe283e15b00d24353194c134025def52d33",
        "branch": "main",
        "changed_files": ["train.py", "loss.py"],
        "additions": 64,
        "deletions": 30,
        "feature": "image-classification",
        "status": VersionStatus.SUCCESS.value,
        "tests_passed": 143,
        "tests_failed": 5,
        "metrics": {"accuracy": 93.4, "latency_ms": 285.0, "val_loss": 0.24},
        "errors": [],
        "analysis": "Recovery complete. Accuracy climbed to new high of 93.4%.",
        "recommendation": "Image classification baseline is validated and complete. Ready for model serving.",
        "is_regression": 0,
    },
    {
        "version_id": 5,
        "timestamp": (datetime.now() - timedelta(hours=2)).isoformat(),
        "checkpoint_id": "01K9TQCFF1B7K9R6AZN8GRWF0H",
        "session_id": "sess_01k9tqcf",
        "agent": "antigravity-ide",
        "intent": "Export PyTorch model to TensorRT engine for low-latency batch serving",
        "git_commit": "9cb321c405e37d22f46575316e356247fab74f55",
        "parent_commit": "7fa210b394f26c11e35464205d245136efa63e44",
        "branch": "main",
        "changed_files": ["export_trt.py", "inference.py"],
        "additions": 220,
        "deletions": 12,
        "feature": "model-serving",
        "status": VersionStatus.PARTIAL_SUCCESS.value,
        "tests_passed": 140,
        "tests_failed": 8,
        "metrics": {"accuracy": 93.1, "latency_ms": 64.5, "throughput_fps": 450.0},
        "errors": ["Batch dimension mismatch when request batch size != 1"],
        "analysis": "TensorRT export succeeded with 4.4x latency speedup (285ms -> 64.5ms), but dynamic batch test failed.",
        "recommendation": "Fix dynamic batch profile in export_trt.py to support variable request batches.",
        "is_regression": 0,
    },
    {
        "version_id": 6,
        "timestamp": (datetime.now() - timedelta(hours=1, minutes=20)).isoformat(),
        "checkpoint_id": "01K9TQDG02C8L0S7BAO9HSXG1I",
        "session_id": "sess_01k9tqdg",
        "agent": "antigravity-ide",
        "intent": "Enable dynamic shape optimization profile in TensorRT builder for variable batch sizes",
        "git_commit": "b0d432d516f48e33a57686427f467358abc85a66",
        "parent_commit": "9cb321c405e37d22f46575316e356247fab74f55",
        "branch": "main",
        "changed_files": ["export_trt.py", "inference.py"],
        "additions": 48,
        "deletions": 14,
        "feature": "model-serving",
        "status": VersionStatus.SUCCESS.value,
        "tests_passed": 148,
        "tests_failed": 0,
        "metrics": {"accuracy": 93.4, "latency_ms": 58.2, "throughput_fps": 512.0},
        "errors": [],
        "analysis": "All batch test assertions passed. Inference latency dropped to 58.2ms with zero test failures.",
        "recommendation": "Model serving optimization complete. Ready for secure API gateway.",
        "is_regression": 0,
    },
    {
        "version_id": 7,
        "timestamp": (datetime.now() - timedelta(minutes=45)).isoformat(),
        "checkpoint_id": "01K9TQEH13D9M1T8CBP0ITYH2J",
        "session_id": "sess_01k9tqeh",
        "agent": "codex",
        "intent": "Implement JWT authentication and API rate limiting middleware",
        "git_commit": "d1e543e627a59f44b68797538a578469bcd96b77",
        "parent_commit": "b0d432d516f48e33a57686427f467358abc85a66",
        "branch": "main",
        "changed_files": ["api/auth.py", "api/routes.py"],
        "additions": 160,
        "deletions": 5,
        "feature": "api-gateway",
        "status": VersionStatus.ERROR.value,
        "tests_passed": 132,
        "tests_failed": 16,
        "metrics": {"accuracy": 93.4, "latency_ms": 62.0},
        "errors": ["ModuleNotFoundError: No module named 'python_jose'"],
        "analysis": "Execution or build errors encountered. Errors: ModuleNotFoundError: No module named 'python_jose'",
        "recommendation": "Add python-jose cryptography dependency to pyproject.toml and re-run auth tests.",
        "is_regression": 0,
    },
    {
        "version_id": 8,
        "timestamp": (datetime.now() - timedelta(minutes=10)).isoformat(),
        "checkpoint_id": "01K9TQFI24EA02U9DCQ1JUZI3K",
        "session_id": "sess_01k9tqfi",
        "agent": "claude-code",
        "intent": "Add python-jose, implement token blacklisting in memory, and finalize auth endpoints",
        "git_commit": "f2f654f738b60a55c79808649b689570cde07c88",
        "parent_commit": "d1e543e627a59f44b68797538a578469bcd96b77",
        "branch": "main",
        "changed_files": ["pyproject.toml", "api/auth.py", "api/routes.py"],
        "additions": 52,
        "deletions": 8,
        "feature": "api-gateway",
        "status": VersionStatus.SUCCESS.value,
        "tests_passed": 154,
        "tests_failed": 0,
        "metrics": {"accuracy": 93.4, "latency_ms": 60.1, "throughput_fps": 498.0},
        "errors": [],
        "analysis": "All validations and tests passed successfully (154/154 passing).",
        "recommendation": "Project state is completely stable. Ready for production release.",
        "is_regression": 0,
    },
]


def seed_demo_data(project_path: str = "."):
    """Populate DevMemory SQLite storage and Databricks sync queue with demo data."""
    proj = init(project_path, name="VisionAI", project_id="visionai")

    # Clear existing demo versions for a clean slate
    proj.db.conn.execute("DELETE FROM versions")
    proj.db.conn.execute("DELETE FROM features")
    proj.db.conn.execute("DELETE FROM events")
    try:
        proj.db.conn.execute("DELETE FROM versions_fts")
    except Exception:
        pass
    proj.db.conn.commit()

    for item in DEMO_VERSIONS:
        vid = proj.db.create_version(
            project_id=proj.config.project_id,
            timestamp=item["timestamp"],
            checkpoint_id=item["checkpoint_id"],
            session_id=item["session_id"],
            agent=item["agent"],
            intent=item["intent"],
            git_commit=item["git_commit"],
            parent_commit=item["parent_commit"],
            branch=item["branch"],
            changed_files=item["changed_files"],
            additions=item["additions"],
            deletions=item["deletions"],
            feature=item["feature"],
            status=item["status"],
            tests_passed=item["tests_passed"],
            tests_failed=item["tests_failed"],
            metrics=item["metrics"],
            errors=item["errors"],
            analysis=item["analysis"],
            recommendation=item["recommendation"],
            is_regression=item["is_regression"],
            artifact_path=f".devmemory/artifacts/v{item['version_id']}_{item['git_commit'][:7]}.tar.gz",
        )

        # Update feature
        feat_name = item["feature"]
        feat_status = FeatureStatus.IN_PROGRESS.value
        if item["status"] == VersionStatus.SUCCESS.value:
            feat_status = FeatureStatus.COMPLETE.value
        elif item["status"] == VersionStatus.REGRESSION.value:
            feat_status = FeatureStatus.PARTIAL.value
        elif item["status"] == VersionStatus.ERROR.value:
            feat_status = FeatureStatus.FAILED.value

        proj.db.upsert_feature(
            project_id=proj.config.project_id,
            name=feat_name,
            status=feat_status,
            metrics=item["metrics"],
        )

        # Log event
        proj.db.log_event(
            project_id=proj.config.project_id,
            version_id=vid,
            event_type="checkpoint",
            data={"status": item["status"], "agent": item["agent"]},
        )

    proj.db.update_current_version(8)
