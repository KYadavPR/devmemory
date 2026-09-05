"""Test adapter: run the project's configured test command and normalize the result.

DevMemory does not care which framework you use. It runs a shell command and
parses what comes back - a JUnit XML report if one is configured, otherwise the
stdout of pytest / go test / cargo test / a generic "N passed, M failed" line.
The *outcome* is a fact; whether that outcome is good is decided elsewhere.
"""

from __future__ import annotations

import re
import shlex
import subprocess
import time
from pathlib import Path
from xml.etree import ElementTree

from devmemory.domain.errors import CollectionError
from devmemory.domain.models import TestOutcome
from devmemory.logging import get_logger

_log = get_logger(__name__)

_OUTPUT_CAP = 20_000

# pytest summary: "3 failed, 128 passed, 2 skipped, 1 error in 4.20s"
_PYTEST_TOKEN = re.compile(r"(\d+)\s+(passed|failed|skipped|error|errors|xfailed|xpassed)")
_PYTEST_FAIL_LINE = re.compile(r"^(?:FAILED|ERROR)\s+(\S+)", re.MULTILINE)

# go test: "ok  pkg  0.1s" / "--- FAIL: TestFoo"
_GO_FAIL = re.compile(r"^--- FAIL:\s+(\S+)", re.MULTILINE)
_GO_PASS = re.compile(r"^--- PASS:\s+(\S+)", re.MULTILINE)

# generic: "12 passed", "3 failing", "Tests: 5 failed, 40 passed"
_GENERIC = re.compile(
    r"(?P<n>\d+)\s+(?P<kind>passed|passing|failed|failing|skipped|pending|errors?)",
    re.IGNORECASE,
)


class TestAdapter:
    __test__ = False  # this runs tests; it is not itself a pytest test case

    def __init__(self, repo_path: Path | str) -> None:
        self._cwd = Path(repo_path).resolve()

    def run(
        self,
        command: str,
        *,
        parser: str = "auto",
        junit_xml: str | None = None,
        timeout: int = 900,
    ) -> TestOutcome:
        """Execute ``command`` and return a normalized :class:`TestOutcome`."""
        start = time.perf_counter()
        try:
            proc = subprocess.run(  # noqa: S602 - user-configured command, run in their repo
                command,
                cwd=self._cwd,
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise CollectionError(
                f"test command timed out after {timeout}s: {command}",
            ) from exc
        except OSError as exc:
            raise CollectionError(f"could not run test command {command!r}: {exc}") from exc

        duration = round(time.perf_counter() - start, 2)
        combined = f"{proc.stdout}\n{proc.stderr}"

        if junit_xml:
            outcome = self._from_junit(self._cwd / junit_xml)
        else:
            outcome = self._parse(combined, parser)

        outcome.command = command
        outcome.exit_code = proc.returncode
        outcome.duration_seconds = duration
        outcome.output = _tail(combined, _OUTPUT_CAP)

        # A command that exited non-zero with no parsed failures still failed.
        if proc.returncode != 0 and outcome.failed == 0 and outcome.errors == 0:
            outcome.errors = max(outcome.errors, 1)

        _log.info(
            "tests.collected",
            command=command,
            passed=outcome.passed,
            failed=outcome.failed,
            exit_code=proc.returncode,
        )
        return outcome

    # -- parsing --------------------------------------------------------

    def _parse(self, text: str, parser: str) -> TestOutcome:
        chosen = parser
        if chosen == "auto":
            chosen = self._sniff(text)
        if chosen == "pytest":
            return self._parse_pytest(text)
        if chosen == "go":
            return self._parse_go(text)
        if chosen == "junitxml":
            raise CollectionError("parser=junitxml requires tests.junit_xml to be set")
        return self._parse_generic(text)

    @staticmethod
    def _sniff(text: str) -> str:
        head = text[:4000].lower()
        if "=== test session starts ===" in head or "\npassed" in head or "pytest" in head:
            return "pytest"
        if "--- fail:" in head or "--- pass:" in head or "\nok  " in head:
            return "go"
        return "generic"

    def _parse_pytest(self, text: str) -> TestOutcome:
        # Take the last summary line so a mid-run "1 failed" doesn't shadow the total.
        summary_line = ""
        for line in text.splitlines():
            if _PYTEST_TOKEN.search(line) and (
                "passed" in line or "failed" in line or "error" in line
            ):
                summary_line = line
        counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
        for count, kind in _PYTEST_TOKEN.findall(summary_line or text):
            key = "errors" if kind.startswith("error") else kind
            if key in counts:
                counts[key] = max(counts[key], int(count))
        failing = _PYTEST_FAIL_LINE.findall(text)
        total = sum(counts.values())
        return TestOutcome(
            framework="pytest",
            total=total,
            passed=counts["passed"],
            failed=counts["failed"],
            skipped=counts["skipped"],
            errors=counts["errors"],
            failing=failing[:50],
        )

    def _parse_go(self, text: str) -> TestOutcome:
        failing = _GO_FAIL.findall(text)
        passing = _GO_PASS.findall(text)
        return TestOutcome(
            framework="go",
            total=len(failing) + len(passing),
            passed=len(passing),
            failed=len(failing),
            failing=failing[:50],
        )

    def _parse_generic(self, text: str) -> TestOutcome:
        counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
        for m in _GENERIC.finditer(text):
            kind = m.group("kind").lower()
            n = int(m.group("n"))
            if kind in ("passed", "passing"):
                counts["passed"] = max(counts["passed"], n)
            elif kind in ("failed", "failing"):
                counts["failed"] = max(counts["failed"], n)
            elif kind in ("skipped", "pending"):
                counts["skipped"] = max(counts["skipped"], n)
            elif kind.startswith("error"):
                counts["errors"] = max(counts["errors"], n)
        return TestOutcome(
            framework="generic",
            total=sum(counts.values()),
            passed=counts["passed"],
            failed=counts["failed"],
            skipped=counts["skipped"],
            errors=counts["errors"],
        )

    def _from_junit(self, path: Path) -> TestOutcome:
        if not path.is_file():
            raise CollectionError(f"JUnit report not found: {path}")
        try:
            root = ElementTree.parse(path).getroot()  # noqa: S314 - our own CI's report
        except ElementTree.ParseError as exc:
            raise CollectionError(f"could not parse JUnit report {path}: {exc}") from exc

        suites = [root] if root.tag == "testsuite" else root.findall(".//testsuite")
        total = failures = errors = skipped = 0
        failing: list[str] = []
        for suite in suites:
            total += int(suite.get("tests", 0))
            failures += int(suite.get("failures", 0))
            errors += int(suite.get("errors", 0))
            skipped += int(suite.get("skipped", 0))
            for case in suite.findall("testcase"):
                if case.find("failure") is not None or case.find("error") is not None:
                    name = case.get("name", "")
                    classname = case.get("classname", "")
                    failing.append(f"{classname}::{name}" if classname else name)
        return TestOutcome(
            framework="junit",
            total=total,
            passed=total - failures - errors - skipped,
            failed=failures,
            errors=errors,
            skipped=skipped,
            failing=failing[:50],
        )


def _tail(text: str, cap: int) -> str:
    text = text.strip()
    return text if len(text) <= cap else "…(truncated)…\n" + text[-cap:]


def split_command(command: str) -> list[str]:
    """POSIX-ish split for display; execution always uses the shell."""
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return command.split()


__all__ = ["TestAdapter", "split_command"]
