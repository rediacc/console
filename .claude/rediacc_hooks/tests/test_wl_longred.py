"""wl_longred: the landing PR's per-round ledger and the long-red verdict (agent/plans/PLAN-simple-two-tree-loop.md D4, box B6).

Every verdict is driven by a synthetic ledger AT its threshold and one round (or one minute) short of it, the control: a rule that fired on both would pass a one-sided test while ignoring its threshold. The stuck rule also carries a planted mutant (fixes counted for any check, not the named one), which the control case must catch.
"""

from __future__ import annotations

import datetime
import json

import pytest
import wl_longred as L

T0 = datetime.datetime(2026, 11, 21, 12, 0, 0, tzinfo=datetime.UTC)


def at(hours: float = 0.0, minutes: float = 0.0) -> str:
    return (T0 + datetime.timedelta(hours=hours, minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def red(check: str, category: str = "code-likely", signature: str = "gate-finding") -> dict:
    return {"check": check, "category": category, "signature": signature}


def outage(check: str = "Quality / Static", signature: str = "registry-refused") -> dict:
    return red(check, "infra-likely", signature)


def row(n, utc, reds=(), kind="push", fix=(), greens=(), regressed=(), pr=900, opened=None):
    return {
        "pr": pr,
        "round": n,
        "utc": utc,
        "kind": kind,
        "run_id": 1000 + n,
        "heads": "sha%d" % n,
        "fix_target": list(fix),
        "reds": list(reds),
        "greens": list(greens),
        "delta": {"newly_green": [], "newly_red": [], "regressed": list(regressed), "repeat": []},
        "open_hours": 0.0,
        "opened_at": opened or at(0),
        "trigger": "stop",
        "ids": {},
    }


def e2e_retryable(name: str) -> bool:
    return "E2E" in name


# ---- the gap sequence ------------------------------------------------------------------------


def test_the_outage_gap_sequence_is_10_20_40_80_then_120():
    assert [L.next_gap_min(n) for n in range(1, 8)] == [10, 20, 40, 80, 120, 120, 120]


@pytest.mark.parametrize(("n", "gap"), [(1, 10), (2, 20), (3, 40), (4, 80), (5, 120)])
def test_outage_retry_names_the_gap_for_its_round(n, gap):
    rows = [row(i + 1, at(minutes=10 * i), [outage()], kind="rerun") for i in range(n)]
    v = L.verdict(rows, now=at(minutes=10 * n))
    assert v.kind == "outage-retry", v
    assert v.next_gap_min == gap
    assert v.due_utc == at(minutes=10 * (n - 1) + gap)
    assert not v.ask


def test_control_a_round_with_one_code_red_is_no_outage():
    rows = [row(1, at(0), [outage(), red("Quality / Code")])]
    assert L.verdict(rows, now=at(minutes=5)).kind == "none"


def test_control_slow_setup_is_infra_but_no_outside_outage():
    rows = [row(1, at(0), [red("E2E", "infra-likely", "slow-setup")])]
    assert L.verdict(rows, now=at(minutes=5)).kind == "none"


# ---- outage-ask at 24 h ---------------------------------------------------------------------------


def _outage_rows(span_h: float):
    return [
        row(1, at(0), [outage()], kind="rerun"),
        row(2, at(span_h / 2), [outage()], kind="rerun"),
        row(3, at(span_h), [outage()], kind="rerun"),
    ]


def test_outage_rounds_for_24_hours_ask_the_operator():
    v = L.verdict(_outage_rows(23), now=at(24))
    assert v.kind == "outage-ask", v
    assert v.ask
    assert v.rounds == [1, 2, 3]


def test_control_one_minute_short_of_24_hours_still_retries():
    v = L.verdict(_outage_rows(23), now=at(23, 59))
    assert v.kind == "outage-retry", v


def test_control_a_code_round_breaks_the_outage_run():
    rows = _outage_rows(23)
    rows[1]["reds"] = [red("Quality / Code")]
    v = L.verdict(rows, now=at(24))
    assert v.kind == "outage-retry", v
    assert v.rounds == [3]


# ---- operator-only ----------------------------------------------------------------------------------


def test_an_operator_only_red_asks_at_once():
    rows = [row(1, at(0), [red("Quality / Security", "operator-only", "auth-401"), outage()])]
    v = L.verdict(rows, now=at(minutes=1))
    assert v.kind == "operator-only", v
    assert v.ask
    assert v.check == "Quality / Security"
    assert "ask the operator now" in L.render(v)


def test_control_the_same_check_as_infra_retries_instead():
    rows = [row(1, at(0), [outage("Quality / Security", "github-api-5xx")])]
    assert L.verdict(rows, now=at(minutes=1)).kind == "outage-retry"


# ---- stuck: 3 fixes aimed at one check ---------------------------------------------------------


def _stuck_rows(fixes: int, target: str = "Quality / Static"):
    rows = [row(1, at(0), [red("Quality / Static")])]
    rows.extend(
        row(i + 2, at(i + 1), [red("Quality / Static")], fix=[target]) for i in range(fixes)
    )
    return rows


def test_three_fixes_aimed_at_one_check_hand_it_over():
    v = L.verdict(_stuck_rows(3), now=at(4))
    assert v.kind == "stuck", v
    assert v.check == "Quality / Static"
    assert v.rounds == [2, 3, 4]
    trig = L.handover_trigger(v)
    assert trig is not None
    assert trig["kind"] == "stuck"
    assert trig["check"] == "Quality / Static"
    assert trig["pr"] == 900
    assert trig["rounds"] == [2, 3, 4]
    assert "landing-rounds.jsonl" in trig["evidence"]


def test_control_two_fixes_are_one_short():
    assert L.verdict(_stuck_rows(2), now=at(3)).kind == "none"


def test_control_fixes_aimed_at_another_check_do_not_count():
    assert L.verdict(_stuck_rows(3, target="Quality / Code"), now=at(4)).kind == "none"


def test_the_mutant_counting_fixes_for_any_check_turns_the_control_red(monkeypatch):
    """The plant: count every push with any fix_target while the check is red. The control above must then read `stuck`, which proves it pins the named-check rule."""

    def mutant(rows, check):
        return [
            r.get("round")
            for r in rows
            if r.get("kind") == "push" and r.get("fix_target") and check in L.red_names(r)
        ]

    monkeypatch.setattr(L, "stuck_rounds", mutant)
    assert L.verdict(_stuck_rows(3, target="Quality / Code"), now=at(4)).kind == "stuck"


# ---- churn: 2 regressions in 4 rounds ------------------------------------------------------------


def _churn_rows(regressions: int, kind: str = "push"):
    return [
        row(1, at(0), [red("A")], greens=["B", "C"]),
        row(
            2,
            at(1),
            [red("B")],
            greens=["A"],
            regressed=["B"] if regressions >= 1 else [],
            kind=kind,
        ),
        row(
            3,
            at(2),
            [red("C")],
            greens=["A", "B"],
            regressed=["C"] if regressions >= 2 else [],
            kind=kind,
        ),
        row(4, at(3), [red("D")], greens=["A", "B", "C"]),
    ]


def test_two_regressing_fixes_in_four_rounds_consult_the_development_session():
    v = L.verdict(_churn_rows(2), now=at(4))
    assert v.kind == "churn", v
    assert v.rounds == [2, 3]
    assert L.handover_trigger(v)["kind"] == "churn"
    assert "keep, change or undo" in L.render(v)


def test_control_one_regression_is_one_short():
    assert L.verdict(_churn_rows(1), now=at(4)).kind == "none"


def test_control_a_rerun_that_flips_a_check_is_a_flake_not_churn():
    assert L.verdict(_churn_rows(2, kind="rerun"), now=at(4)).kind == "none"


def test_control_regressions_outside_the_last_four_rounds_do_not_count():
    rows = [*_churn_rows(2), row(5, at(4), [red("D")]), row(6, at(5), [red("D")])]
    assert L.verdict(rows, now=at(6)).kind == "none"


# ---- wall at 72 h -----------------------------------------------------------------------------------


def test_red_72_hours_after_the_pr_opened_asks_with_default_keep_fixing():
    rows = [row(1, at(0), [red("A")]), row(2, at(70), [red("A")])]
    v = L.verdict(rows, now=at(72))
    assert v.kind == "wall-ask", v
    assert v.ask
    assert v.default == "keep fixing"
    assert "DEFAULT: keep fixing" in L.render(v)


def test_control_one_minute_short_of_72_hours_is_no_wall():
    rows = [row(1, at(0), [red("A")]), row(2, at(70), [red("A")])]
    assert L.verdict(rows, now=at(71, 59)).kind == "none"


def test_control_a_green_latest_round_is_no_verdict_at_any_age():
    rows = [row(1, at(0), [red("A")]), row(2, at(70), [], greens=["A"])]
    assert L.verdict(rows, now=at(100)).kind == "none"


# ---- the row: kind, delta, fix target, the ledger file ---------------------------------------


def test_round_kind_push_rerun_watchdog_and_already_recorded():
    prev = {"heads": "h1", "ids": {"Quality / Static": 1, "E2E Workers (1/8)": 2}}
    assert L.round_kind(None, "h1", {}, e2e_retryable) == "push"
    assert L.round_kind(prev, "h2", prev["ids"], e2e_retryable) == "push"
    assert L.round_kind(prev, "h1", dict(prev["ids"]), e2e_retryable) is None
    retried = {"Quality / Static": 1, "E2E Workers (1/8)": 3}
    assert L.round_kind(prev, "h1", retried, e2e_retryable) == "watchdog-retry"
    rerun = {"Quality / Static": 5, "E2E Workers (1/8)": 2}
    assert L.round_kind(prev, "h1", rerun, e2e_retryable) == "rerun"


def test_fix_targets_read_trailers_first_then_named_reds():
    trailer = "fix: x\n\nFix-Target: Quality / Static, Quality / Code\n"
    assert L.fix_targets(trailer, ["Other"]) == ["Quality / Code", "Quality / Static"]
    named = "fix(ci): quality / static shell format\n"
    assert L.fix_targets(named, ["Quality / Static", "E2E"]) == ["Quality / Static"]
    assert L.fix_targets("chore: unrelated\n", ["Quality / Static"]) == []


def test_build_row_numbers_rounds_and_computes_the_delta():
    first = L.build_row(
        [], pr=7, kind="push", run_id=1, heads="h1", reds=[red("A")], greens=["B"], now=at(0)
    )
    assert first["round"] == 1
    assert first["open_hours"] == 0.0
    second = L.build_row(
        [first],
        pr=7,
        kind="push",
        run_id=2,
        heads="h2",
        reds=[red("B")],
        greens=["A"],
        fix_target=["A"],
        now=at(2),
    )
    assert second["round"] == 2
    assert second["delta"] == {
        "newly_green": ["A"],
        "newly_red": ["B"],
        "regressed": ["B"],
        "repeat": [],
    }
    assert second["fix_target"] == ["A"]
    assert second["open_hours"] == 2.0
    rerun = L.build_row(
        [first], pr=7, kind="rerun", run_id=1, heads="h1", reds=[], greens=["A"], fix_target=["A"]
    )
    assert rerun["fix_target"] == []
    for key in (
        "round",
        "utc",
        "kind",
        "run_id",
        "heads",
        "fix_target",
        "reds",
        "greens",
        "delta",
        "open_hours",
        "trigger",
    ):
        assert key in second, key


def test_the_ledger_is_created_on_first_write_and_read_back_per_pr(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    path = tmp_path / "agent" / "ledgers" / "landing-rounds.jsonl"
    assert not path.exists()
    L.append_row(tmp_path, row(1, at(0), [red("A")], pr=1))
    L.append_row(tmp_path, row(1, at(1), [], pr=2))
    assert path.exists()
    assert [json.loads(x)["pr"] for x in path.read_text(encoding="utf-8").splitlines()] == [1, 2]
    assert [r["pr"] for r in L.read_rows(tmp_path, pr=2)] == [2]
    assert L.read_rows(tmp_path / "absent") == []


def test_handover_trigger_is_none_for_every_non_handover_kind():
    for kind in ("none", "outage-retry", "outage-ask", "operator-only", "wall-ask"):
        assert L.handover_trigger(L.Verdict(kind)) is None
    assert L.render(L.Verdict()) == ""


def test_the_verdict_reads_only_the_latest_prs_rows():
    rows = _stuck_rows(3)
    for r in rows:
        r["pr"] = 1
    rows.append(row(1, at(5), [red("Quality / Static")], pr=2))
    assert L.verdict(rows, now=at(6)).kind == "none"
