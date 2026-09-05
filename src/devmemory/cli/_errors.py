"""Turn :class:`DevMemoryError` into a clean CLI message + hint + exit code.

Applied to every command at registration so ``CliRunner`` (which invokes the
Typer app directly, not ``main()``) still sees the right exit status.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import ParamSpec, TypeVar

import typer

from devmemory.cli._render import err_console
from devmemory.domain.errors import DevMemoryError

_P = ParamSpec("_P")
_R = TypeVar("_R")


def handle_errors(func: Callable[_P, _R]) -> Callable[_P, _R]:
    @functools.wraps(func)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        try:
            return func(*args, **kwargs)
        except DevMemoryError as exc:
            err_console.print(f"[bold red]error:[/bold red] {exc.message}")
            if exc.hint:
                err_console.print(f"[dim]hint:[/dim] {exc.hint}")
            raise typer.Exit(code=exc.exit_code) from exc

    return wrapper


__all__ = ["handle_errors"]
