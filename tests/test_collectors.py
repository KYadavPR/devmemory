"""Phase 6: test + metric collection and regression detection."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from devmemory.adapters.metrics import MetricsAdapter, guess_direction
from devmemory.adapters.tests import TestAdapter
from devmemory.domain.enums import MetricDirection
from devmemory.domain.errors import CollectionError
from devmemory.domain.models import DevelopmentVersion, Metric, TestOutcome
from devmemory.pipeline.regression import RegressionThresholds, detect_regressions

PY = sys.executable


def _emit(text: str) -> str:
    """A shell command that prints ``text`` verbatim - portable across sh and cmd."""
    return f'{PY} -c "import sys; sys.stdout.write({text!r})"'


# --- TestAdapter ---------------------------------------------------------------


def test_run_generic_passing(tmp_path: Path) -> None:
    out = TestAdapter(tmp_path).run(_emit("40 passed, 0 failed\n"))
    assert out.passed == 40
    assert out.failed == 0
    assert out.all_passed
    assert out.exit_code == 0


def test_run_nonzero_exit_marks_failure(tmp_path: Path) -> None:
    out = TestAdapter(tmp_path).run(f'{PY} -c "raise SystemExit(2)"')
    assert out.exit_code == 2
    assert out.errors >= 1
    assert not out.all_passed


def test_run_pytest_summary(tmp_path: Path) -> None:
    text = "=== 3 failed, 128 passed, 2 skipped, 1 error in 4.20s ===\nFAILED tests/test_x.py::test_a\n"
    out = TestAdapter(tmp_path).run(_emit(text), parser="pytest")
    assert out.passed == 128
    assert out.failed == 3
    assert out.errors == 1
    assert out.skipped == 2
    assert "tests/test_x.py::test_a" in out.failing


def test_run_junit_xml(tmp_path: Path) -> None:
    (tmp_path / "report.xml").write_text(
        '<testsuite tests="5" failures="1" errors="0" skipped="1">'
        '<testcase classname="t.M" name="ok"/>'
        '<testcase classname="t.M" name="bad"><failure/></testcase>'
        "</testsuite>",
        encoding="utf-8",
    )
    out = TestAdapter(tmp_path).run(_emit("done\n"), junit_xml="report.xml")
    assert out.total == 5
    assert out.failed == 1
    assert out.passed == 3
    assert out.framework == "junit"
    assert "t.M::bad" in out.failing


def test_run_timeout(tmp_path: Path) -> None:
    with pytest.raises(CollectionError):
        TestAdapter(tmp_path).run(f'{PY} -c "import time; time.sleep(5)"', timeout=1)


# --- MetricsAdapter ----------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("accuracy", MetricDirection.HIGHER_IS_BETTER),
        ("latency_ms", MetricDirection.LOWER_IS_BETTER),
        ("p99", MetricDirection.LOWER_IS_BETTER),
        ("val_loss", MetricDirection.LOWER_IS_BETTER),
        ("throughput", MetricDirection.HIGHER_IS_BETTER),
    ],
)
def test_guess_direction(name: str, expected: MetricDirection) -> None:
    assert guess_direction(name) is expected


def test_metrics_from_file_scalar_and_object(tmp_path: Path) -> None:
    (tmp_path / "m.json").write_text(
        json.dumps({"accuracy": 93.4, "latency": {"before": 420, "after": 310, "unit": "ms"}}),
        encoding="utf-8",
    )
    metrics = {m.name: m for m in MetricsAdapter(tmp_path).collect(file="m.json")}
    assert metrics["accuracy"].after == 93.4
    assert metrics["accuracy"].direction is MetricDirection.HIGHER_IS_BETTER
    assert metrics["latency"].before == 420
    assert metrics["latency"].after == 310
    assert metrics["latency"].unit == "ms"
    assert metrics["latency"].direction is MetricDirection.LOWER_IS_BETTER


def test_metrics_from_command_with_wrapper_key(tmp_path: Path) -> None:
    (tmp_path / "gen.py").write_text(
        "import json; print(json.dumps({'metrics': {'score': 0.8}}))", encoding="utf-8"
    )
    out = MetricsAdapter(tmp_path).collect(command=f"{PY} gen.py")
    assert out[0].name == "score"
    assert out[0].after == 0.8


def test_metrics_direction_override(tmp_path: Path) -> None:
    (tmp_path / "m.json").write_text(json.dumps({"weird": 5}), encoding="utf-8")
    out = MetricsAdapter(tmp_path).collect(
        file="m.json", directions={"weird": MetricDirection.LOWER_IS_BETTER}
    )
    assert out[0].direction is MetricDirection.LOWER_IS_BETTER


def test_metrics_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CollectionError):
        MetricsAdapter(tmp_path).collect(file="nope.json")


# --- regression detection --------------------------------------------------


def _version(**kw: object) -> DevelopmentVersion:
    base: dict[str, object] = {
        "version_id": "v1",
        "version_number": 1,
        "project_id": "p",
        "git_commit": "a" * 40,
        "created_at": datetime.now(UTC),
    }
    base.update(kw)
    return DevelopmentVersion.model_validate(base)


def test_metric_regression_higher_is_better() -> None:
    prev = _version(metrics=[Metric(name="accuracy", after=93.4)])
    regs = detect_regressions(
        metrics=[Metric(name="accuracy", after=76.1)], tests=None, previous=prev
    )
    assert len(regs) == 1
    assert regs[0].kind == "metric"
    assert regs[0].severity == "HIGH"
    assert regs[0].change_percent is not None and regs[0].change_percent < 0


def test_latency_regression_lower_is_better() -> None:
    prev = _version(
        metrics=[Metric(name="latency_ms", after=200, direction=MetricDirection.LOWER_IS_BETTER)]
    )
    regs = detect_regressions(
        metrics=[Metric(name="latency_ms", after=260, direction=MetricDirection.LOWER_IS_BETTER)],
        tests=None,
        previous=prev,
    )
    assert len(regs) == 1
    assert "increase" in regs[0].detail


def test_improvement_is_not_a_regression() -> None:
    prev = _version(metrics=[Metric(name="accuracy", after=80)])
    assert (
        detect_regressions(metrics=[Metric(name="accuracy", after=91)], tests=None, previous=prev)
        == []
    )


def test_small_metric_move_is_ignored() -> None:
    prev = _version(metrics=[Metric(name="accuracy", after=90.0)])
    assert (
        detect_regressions(metrics=[Metric(name="accuracy", after=89.5)], tests=None, previous=prev)
        == []
    )


def test_test_regression_newly_failing() -> None:
    prev = _version(tests=TestOutcome(command="pytest", total=10, passed=10, failed=0))
    regs = detect_regressions(
        metrics=[],
        tests=TestOutcome(command="pytest", total=10, passed=6, failed=4, failing=["t::a", "t::b"]),
        previous=prev,
    )
    assert len(regs) == 1
    assert regs[0].kind == "test"
    assert regs[0].severity == "HIGH"
    assert "t::a" in regs[0].detail


def test_thresholds_are_configurable() -> None:
    prev = _version(metrics=[Metric(name="accuracy", after=100)])
    lenient = RegressionThresholds(metric_pct=10.0)
    assert (
        detect_regressions(
            metrics=[Metric(name="accuracy", after=95)],
            tests=None,
            previous=prev,
            thresholds=lenient,
        )
        == []
    )
