"""`vm_check.leased_main`: vm:check holds core-lease tokens for its battery and drills (PLAN-ciquick-cpu L2, PR-TASK 79b7e92e).

The pool is private (`REDIACC_CORE_LEASE_DIR` under tmp_path, `REDIACC_CORE_LEASE_TOKENS=4`). The run body is a probe standing in for `main`: it asks a SECOND lease client how many tokens are free while the run holds its own. Cases: the run holds `CORE_SLOTS` (a second client sees fewer free); a control without vm_check sees all 4; a read-only flag and a run under a held lease take none; the grant reaches the children's environment and is gone afterwards; a full pool ends the wait and the run goes ahead.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import core_lease
from rediacc_ci.drills import vm_check

if TYPE_CHECKING:
    import pathlib

TOKENS = 4


@pytest.fixture
def env(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    for key in (core_lease.HELD_ENV, core_lease.ENV):
        monkeypatch.delenv(key, raising=False)
    pool = tmp_path / "pool"
    pool.mkdir()
    monkeypatch.setenv(core_lease.DIR_ENV, str(pool))
    monkeypatch.setenv(core_lease.TOKENS_ENV, str(TOKENS))
    return dict(os.environ)


def free_now(env: dict[str, str]) -> int:
    return core_lease.Pool.from_env(env).free_count()


def probe(env: dict[str, str], seen: dict[str, object]):
    def fake_main(_argv, **_kwargs):
        seen["free"] = free_now(env)
        seen["held_env"] = os.environ.get(core_lease.HELD_ENV)
        seen["cores"] = os.environ.get(core_lease.ENV)
        return 0

    return fake_main


def test_control_without_vm_check_sees_every_token(env: dict[str, str]) -> None:
    assert free_now(env) == TOKENS


def test_run_holds_its_tokens_while_a_second_client_sees_fewer(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr(vm_check, "main", probe(env, seen))
    assert vm_check.leased_main(["--changed"], environ=env) == 0
    assert seen["free"] == TOKENS - vm_check.CORE_SLOTS
    assert seen["held_env"] == "1"
    assert seen["cores"] == str(vm_check.CORE_SLOTS)
    assert free_now(env) == TOKENS
    assert core_lease.HELD_ENV not in os.environ
    assert core_lease.ENV not in os.environ


@pytest.mark.parametrize("flag", sorted(vm_check.LEASE_SAFE_FLAGS))
def test_read_only_flags_take_no_tokens(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, flag: str
) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr(vm_check, "main", probe(env, seen))
    assert vm_check.leased_main([flag], environ=env) == 0
    assert seen["free"] == TOKENS


@pytest.mark.usefixtures("env")
def test_a_run_under_a_held_lease_takes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(core_lease.HELD_ENV, "1")
    monkeypatch.setenv(core_lease.ENV, "2")
    held = dict(os.environ)
    seen: dict[str, object] = {}
    monkeypatch.setattr(vm_check, "main", probe(held, seen))
    assert vm_check.leased_main(["--changed"], environ=held) == 0
    assert seen["free"] == TOKENS


def test_a_full_pool_ends_the_wait_and_the_run_goes_ahead(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    pool = core_lease.Pool.from_env(env)
    hog = pool.acquire(TOKENS, TOKENS, label="hog")
    assert len(hog) == TOKENS
    monkeypatch.setattr(vm_check, "CORE_SLOT_WAIT_S", 0.3)
    warned: list[str] = []
    monkeypatch.setattr(vm_check.log, "warn", warned.append)
    seen: dict[str, object] = {}
    monkeypatch.setattr(vm_check, "main", probe(env, seen))
    try:
        assert vm_check.leased_main(["--changed"], environ=env) == 0
    finally:
        pool.release(hog)
    assert seen["free"] == 0
    assert seen["held_env"] is None
    assert len(warned) == 1
    assert "going ahead without the tokens" in warned[0]
