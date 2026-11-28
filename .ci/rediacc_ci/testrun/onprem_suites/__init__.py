"""The suite registry of the on-premise scenario runner (PLAN-rmcp-executor-hardening.md, Design 16).

A suite is a module of this package. Importing it registers its scenarios through the `scenario` decorator; `load_all` imports every module, so a sibling plan adds a suite by adding one file here and touching nothing else. A scenario is a function of a `rediacc_ci.testrun.onprem_scenarios.Context` returning a `Result`; the runner turns each into one JSON verdict line.

`targets` names where a scenario can run: `onprem` (the local stack, `.onprem/stack.env`) and `bench` (`./rdc.sh --config eu-bench`). `--compare bench` runs only the scenarios that name both and fails when their verdicts or codes differ, which is the D49 parity tier; a scenario naming only `onprem` (anything that needs the daemon) is listed as skipped in a comparison, never silently dropped.
"""

from __future__ import annotations

import dataclasses
import importlib
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from rediacc_ci.testrun.onprem_scenarios import Context

TARGETS = ("onprem", "bench")


@dataclasses.dataclass(frozen=True)
class Result:
    """One scenario's outcome: pass or fail, the exit code or HTTP status that decided it (None when none did), and a short reason."""

    ok: bool
    code: int | None = None
    detail: str = ""


def passed(detail: str = "", code: int | None = 0) -> Result:
    return Result(True, code, detail)


def failed(detail: str, code: int | None = None) -> Result:
    return Result(False, code, detail)


@dataclasses.dataclass(frozen=True)
class Scenario:
    suite: str
    name: str
    targets: tuple[str, ...]
    run: Callable[[Context], Result]


SUITES: dict[str, dict[str, Scenario]] = {}


def scenario(
    suite: str, name: str, targets: tuple[str, ...] = ("onprem",)
) -> Callable[[Callable[[Context], Result]], Callable[[Context], Result]]:
    """Register `fn` as scenario `name` of `suite`. A duplicate name or an unknown target is a programming error and raises at import."""
    unknown = [t for t in targets if t not in TARGETS]
    if unknown or not targets:
        raise ValueError(
            "scenario %s/%s: targets %r must be drawn from %r" % (suite, name, targets, TARGETS)
        )

    def register(fn: Callable[[Context], Result]) -> Callable[[Context], Result]:
        members = SUITES.setdefault(suite, {})
        if name in members:
            raise ValueError("scenario %s/%s is registered twice" % (suite, name))
        members[name] = Scenario(suite, name, targets, fn)
        return fn

    return register


def load_all() -> dict[str, dict[str, Scenario]]:
    """Import every suite module and return the registry."""
    for info in pkgutil.iter_modules(__path__):
        importlib.import_module("%s.%s" % (__name__, info.name))
    return SUITES
