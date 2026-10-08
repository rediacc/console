"""THE 2026-10-08 REPLAY (PLAN-gate-scheduling-learned T4): the model, fed the real receipts of branches 1006-2, 1006-3 and 1007-1 (the 50 ci:quick receipts on this machine, 2026-10-06 15:54 to 2026-10-08 05:08 UTC), must reproduce the classes the brief's evidence implies WHERE THE DATA SUPPORTS THEM.

The fixture is data, never configuration: `fixtures/gate_model/20261008/` was written by `python3 -m rediacc_ci.ci.gate_ledger backfill --export <dir> --gates-with-reds` (MANIFEST.json says so), and nothing in the model reads it. Gate ids appear HERE, in the test, because the brief names them; the model under test names none (T9).

WHAT THE DATA SAYS, gate by gate, against the brief:
  - dependency freshness ("overnight releases"): CLOCK. Two onsets, each with its last green before 00:00 UTC and its red after it (10-07 00:01, 10-08 00:00), every key a different tree. Only the UTC-boundary rule can see it.
  - budget freshness ("drift"): CLOCK. Five onsets, every one red at the declared-paths key of the green before it. Only the strong-key rule sees it; the onsets sit at five different hours, so the boundary rule cannot.
  - version pins, web lint, python types, incremental types: REAL. Green again only at a different tree.
  - pytest: CHRONIC. Red in all 50 receipts; its four `pytest-skip:` findings are red in every one of them, so they are chronic too, while the one-off `pytest-fail:` nodes are not.
  - embed-asset freshness ("zot 2.1.22"): REAL, NOT what the brief's "freshness" suggests. One onset (10-08 00:38, last green 00:04, same UTC day) and green again at another tree: a single onset cannot meet CLOCK_MIN_ONSETS, and the key moved. Recorded as the data's answer.
  - the brief's upgrade companion (`--upgrade` moved deps, the version pin and web lint went red next): CANDIDATES at support 1, not reliable. 10-08 00:04 red / 00:38 green for deps, green / red for the other two, once.
  - the gate-manifest gate also lands in the clock set, which the brief does not mention: red at the key of its last green on 10-07, with the tree changed (WEAK: an undeclared input explains it as well).
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from rediacc_ci import paths
from rediacc_ci.ci import gate_ledger as L
from rediacc_ci.ci import gate_model as M

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "gate_model" / "20261008"
# Just after the receipts' last finish; recency weights are taken from here so the replay does not age.
NOW = L.epoch("2026-10-08T05:10:00Z") or 0.0

DEPS = "check:deps"
BUDGET = "check:ci-budget-freshness"
PYTEST = "check:ci-pytest"
EMBED = "check:ci-embed-asset-freshness"
VERSION = "check:version"
LINT_WEB = "check:lint:web"
REAL = (VERSION, LINT_WEB, "check:ci-python-types", "check:types:incremental", EMBED)


def _rows() -> list[dict[str, Any]]:
    return [
        json.loads(ln)
        for ln in (FIXTURE / "outcomes.jsonl").read_text(encoding="utf-8").splitlines()
    ]


def _lock() -> list[dict[str, Any]]:
    return json.loads((FIXTURE / "lock.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def built() -> M.Built:
    return M.build(_rows(), _lock(), paths.repo_root(), now=NOW)


def cls(b: M.Built, gid: str) -> str:
    return str(b.model["gates"][gid]["class"])


def test_the_fixture_is_the_receipt_window() -> None:
    man = json.loads((FIXTURE / "MANIFEST.json").read_text())
    assert man["receipts"] == 50
    assert man["generated_by"].startswith("python3 -m rediacc_ci.ci.gate_ledger backfill --export")
    runs = [r for r in _rows() if r["t"] == "run"]
    assert len(runs) == 50
    assert all(r["whole"] for r in runs)


def test_dependency_freshness_is_clock_by_the_utc_boundary(built: M.Built) -> None:
    assert cls(built, DEPS) == "clock"
    whys = {ep.why for ep in built.episodes if ep.subject == DEPS and ep.side == "local"}
    assert whys == {"2 onsets bracket a UTC day boundary"}


def test_control_without_the_boundary_rule_deps_is_real() -> None:
    b = M.build(_rows(), _lock(), paths.repo_root(), now=NOW, rules=M.Rules(utc_boundary=False))
    assert cls(b, DEPS) == "real"


def test_budget_freshness_is_clock_by_the_strong_key(built: M.Built) -> None:
    assert cls(built, BUDGET) == "clock"
    eps = [ep for ep in built.episodes if ep.subject == BUDGET]
    assert len(eps) == 5
    assert all(ep.why == "red at the input key of the last green" for ep in eps)


def test_control_without_the_strong_key_rule_budget_is_real() -> None:
    b = M.build(_rows(), _lock(), paths.repo_root(), now=NOW, rules=M.Rules(strong_key=False))
    assert cls(b, BUDGET) == "real"
    assert cls(b, DEPS) == "clock", (
        "the controls are independent: the boundary rule still holds deps"
    )


@pytest.mark.parametrize("gid", REAL)
def test_real_reds(built: M.Built, gid: str) -> None:
    assert cls(built, gid) == "real"


def test_pytest_is_chronic_and_descends_to_findings(built: M.Built) -> None:
    g = built.model["gates"][PYTEST]
    assert g["class"] == "chronic"
    assert g["obs"] == 50
    chronic = sorted(k for k, c in g["findings"].items() if c == "chronic")
    assert len(chronic) == 4
    assert all(k.startswith("pytest-skip:") for k in chronic)
    assert any(c != "chronic" for k, c in g["findings"].items() if k.startswith("pytest-fail:"))


def test_clock_set_as_the_data_has_it(built: M.Built) -> None:
    assert built.model["clock_set"] == [BUDGET, "check:ci-gate-manifest", DEPS]


def test_upgrade_companions_are_candidates(built: M.Built) -> None:
    comps = {(c["from"], c["to"]): c for c in built.model["companions"]}
    for to in (VERSION, LINT_WEB):
        assert comps[(DEPS, to)]["support"] == 1
        assert comps[(DEPS, to)]["reliable"] is False


def test_cold_start_counts_the_whole_runs(built: M.Built) -> None:
    """50 whole runs clear MIN_LEDGER_RUNS. The fixture leaves out every gate that was green in all 50 receipts, so per-gate coverage is what keeps ranking off HERE; the live ledger the same receipts built (every gate kept) read `off: 351 of 352 gates have 5+ observations` on 2026-10-08."""
    cold = built.model["cold_start"]
    assert built.model["runs"] == 50
    assert cold["on"] is True
    assert "gates have %d+ observations" % M.MIN_GATE_OBS in cold["reason"], cold
