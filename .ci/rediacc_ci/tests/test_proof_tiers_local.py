"""proof-tiers.json's local routes and GitHub-wait phrases (agent/plans/PLAN-local-first-delivery.md box L1, operator ruling R2).

Every surface names at least one `tiers.live.local_runners` id in `local`, and `tiers.live.github_waits` is a non-empty phrase list; `rediacc_ci.proof.surfaces.parse_map` refuses a map that breaks either. Each refusal is driven against a copy of the committed map with one defect planted, so the committed map itself is the control that parses.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from rediacc_ci.proof import surfaces as S


def _raw() -> dict[str, Any]:
    return json.loads(S.MAP_PATH.read_text(encoding="utf-8"))


def test_the_committed_map_gives_every_surface_a_local_route() -> None:
    parsed = S.parse_map(_raw())
    assert parsed.surfaces
    for name, surface in parsed.surfaces.items():
        assert surface.local, name
        assert all(r in parsed.local_runners for r in surface.local), name
    assert S.MAP.surfaces["renet"].local[:2] == ("vm-check", "hostinger")
    assert "d1-migrations" in S.MAP.surfaces["account"].local


def test_the_committed_map_carries_the_github_wait_phrases() -> None:
    assert S.MAP.github_waits == S.GITHUB_WAITS
    for phrase in ("released", "after the merge", "CD", "nightly", "preview deploy", "CI run"):
        assert phrase in S.GITHUB_WAITS


def test_a_surface_with_no_local_entry_is_refused() -> None:
    raw = _raw()
    del raw["surfaces"]["www"]["local"]
    with pytest.raises(S.MapError, match=r"surfaces\.www\.local is missing"):
        S.parse_map(raw)


@pytest.mark.parametrize(
    ("value", "why"),
    [
        ([], r"surfaces\.proxy\.local is empty"),
        (["no-such-runner"], r"not in tiers\.live\.local_runners"),
        (["deploy-proxy-bench", "deploy-proxy-bench"], r"repeats a runner"),
        ("deploy-proxy-bench", r"not a list"),
    ],
)
def test_a_bad_local_entry_is_refused(value: object, why: str) -> None:
    raw = _raw()
    raw["surfaces"]["proxy"]["local"] = value
    with pytest.raises(S.MapError, match=why):
        S.parse_map(raw)


def test_an_empty_runner_table_is_refused() -> None:
    raw = _raw()
    raw["tiers"]["live"]["local_runners"] = {}
    with pytest.raises(S.MapError, match=r"local_runners is empty"):
        S.parse_map(raw)


@pytest.mark.parametrize(
    ("entry", "why"),
    [
        ({"run": ["x"]}, r"needs a what"),
        ({"what": "w", "run": []}, r"\.run is empty"),
        ({"what": "w"}, r"\.run is not a list"),
    ],
)
def test_a_malformed_runner_is_refused(entry: dict[str, Any], why: str) -> None:
    raw = _raw()
    raw["tiers"]["live"]["local_runners"]["vm-check"] = entry
    with pytest.raises(S.MapError, match=why):
        S.parse_map(raw)


@pytest.mark.parametrize(
    ("value", "why"),
    [
        (None, r"github_waits is not a list"),
        ([], r"github_waits is empty"),
        (["CD", ""], r"github_waits is not a list of non-empty strings"),
        (["nightly", "Nightly"], r"repeats a phrase"),
    ],
)
def test_a_bad_github_waits_list_is_refused(value: object, why: str) -> None:
    raw = _raw()
    live = raw["tiers"]["live"]
    if value is None:
        del live["github_waits"]
    else:
        live["github_waits"] = value
    with pytest.raises(S.MapError, match=why):
        S.parse_map(raw)


def test_no_local_runner_command_is_a_placeholder() -> None:
    """a0287d35.2: a planner runs `run` as written, so an `<angle>` token fails at argument parsing."""
    for rid, runner in S.MAP.local_runners.items():
        for cmd in runner.run:
            assert not re.search(r"<[^>\s]+>", cmd), (rid, cmd)


def test_a_runner_naming_a_machine_uses_the_live_target_config() -> None:
    """a0287d35.1: the hostinger local route reads through the same config as `tiers.live.targets.hostinger`."""
    raw = _raw()
    targets = raw["tiers"]["live"]["targets"]
    named = 0
    for machine, target in targets.items():
        for rid, runner in S.MAP.local_runners.items():
            for cmd in runner.run:
                if re.search(rf"machine \w+ {machine}\b", cmd):
                    named += 1
                    assert f"--config {target['config']} " in cmd, (rid, cmd)
    # Control: the assertion above ran at least once, so a removed route or a changed command shape cannot leave this test passing with no assertion.
    assert named > 0
