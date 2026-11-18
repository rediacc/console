"""The license, transfer and universe drills take a per-run identity from `lib.run_email` (PLAN-push-decoupling.md L4).

Before, license and transfer stamped the address with `int(time.time())`, so two runs in one second shared a user, and universe used the fixed `drill-universe@rediacc.io`, so two concurrent runs always did. Each test freezes the clock and builds two drills in the same process, the worst case: same second, same pid.
"""

from __future__ import annotations

import os
import re
import time

import pytest

from rediacc_ci.drills import lib, transfer, universe
from rediacc_ci.drills import license as lic

FROZEN = 1_763_460_000.0


@pytest.fixture
def frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "time", lambda: FROZEN)


def _license(drill: lib.Drill) -> str:
    return lic.License(drill, lic.Options()).email


def _transfer(drill: lib.Drill) -> str:
    return transfer.Transfer(drill, restart_gateway=False).email


def _universe(drill: lib.Drill) -> str:
    return universe.Universe(drill, restart_gateway=False).email


BUILDERS = {"license": _license, "transfer": _transfer, "universe": _universe}


@pytest.mark.parametrize("name", sorted(BUILDERS))
@pytest.mark.usefixtures("frozen")
def test_two_drills_in_one_second_get_different_emails(name: str) -> None:
    build = BUILDERS[name]
    first = build(lib.Drill(name))
    second = build(lib.Drill(name))
    assert first != second
    for email in (first, second):
        assert email.startswith("drill-%s-" % name)
        assert email.endswith("@rediacc.io")
        assert re.fullmatch(
            r"drill-%s-%d-\d+-[0-9a-f]{4}@rediacc\.io" % (name, int(FROZEN)), email
        ), email


@pytest.mark.usefixtures("frozen")
def test_run_email_carries_seconds_pid_and_random_hex() -> None:
    email = lib.run_email("x")
    assert email.startswith("drill-x-%d-%d-" % (int(FROZEN), os.getpid()))
    # Control: the address is not the old fixed or seconds-only shape.
    assert email not in ("drill-x@rediacc.io", "drill-x-%d@rediacc.io" % int(FROZEN))


def test_universe_no_longer_has_a_fixed_address() -> None:
    assert not hasattr(universe, "EMAIL")
