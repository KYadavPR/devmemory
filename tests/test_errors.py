"""The error taxonomy."""

from __future__ import annotations

import pytest

from devmemory.domain import errors
from devmemory.domain.errors import (
    DevMemoryError,
    EntireNotInstalledError,
    GitRepositoryNotFoundError,
    ProjectNotInitializedError,
)


def test_base_error_carries_message_and_hint() -> None:
    exc = DevMemoryError("something broke", hint="try turning it off and on again")
    assert exc.message == "something broke"
    assert exc.hint == "try turning it off and on again"
    assert str(exc) == "something broke"


@pytest.mark.parametrize(
    "factory",
    [ProjectNotInitializedError, GitRepositoryNotFoundError, EntireNotInstalledError],
)
def test_common_errors_have_actionable_hints(factory: type[DevMemoryError]) -> None:
    exc = factory()
    assert exc.hint
    assert exc.exit_code >= 2


def test_every_public_error_subclasses_the_base() -> None:
    for name in errors.__all__:
        obj = getattr(errors, name)
        assert issubclass(obj, DevMemoryError)


def test_exit_codes_are_distinct_enough() -> None:
    # Different failure classes should not all collapse to exit code 1.
    codes = {
        ProjectNotInitializedError().exit_code,
        GitRepositoryNotFoundError().exit_code,
        EntireNotInstalledError().exit_code,
    }
    assert len(codes) == 3
