"""`check:ci-plan-implementation` P-A1: one finding key per plan on the clock, never one over the set.

THE DEFECT THIS PINS (worklist #08d1e96f, 2026-10-13). P-A1 was a single finding listing every plan on the clock, keyed by a hash of that message. Commit 2b147e4a6 ticked two boxes of a queued plan, which put that plan on the clock, and `P-A1:0c9ea2c3e2ce` became `P-A1:99bbfe3180cd`. No plan the carry in `.ci/config/carried-reds.json` named had changed, and the push guard refused the push all the same.

WHAT MOVED THE OLD KEY, MEASURED. Not a count: `log.finding_key` masks digits, so a tick that left its plan open kept the old key (the second case below passes on the old code too, and stays as the control). The old key moved whenever the SET of plans changed, by a plan leaving the clock or joining it. The third and fourth cases are the ones the old code fails.

EVERY CASE GOES THROUGH THE PATH `main()` TAKES: `open_offenders`, `clock_scope`, `split_by_scope`, `clock_findings`, `key_of`, then the real emitter and the reader the gate ledger uses. The queue head is injected through a stand-in for `rediacc_hooks.plan_gate`, as the gate's own C12 control does.
"""

import importlib.util
import io
import pathlib

import pytest
import wl_planrec

from rediacc_ci import log, paths
from rediacc_ci.ci import gate_ledger
from rediacc_ci.core import ghx

GATE_PATH = paths.repo_root() / ".ci" / "scripts" / "quality" / "check_plan_implementation.py"
FINISHED = frozenset({"done"})
HEAD = "agent/plans/PLAN-head.md"
SIDE = "agent/plans/PLAN-side.md"
THIRD = "agent/plans/PLAN-third.md"


@pytest.fixture(scope="module")
def gate():
    assert GATE_PATH.is_file(), "the gate moved: %s" % GATE_PATH
    paths.on_sys_path(pathlib.Path(GATE_PATH).parent)
    spec = importlib.util.spec_from_file_location("check_plan_implementation_under_test", GATE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(open_sigs, done_sigs=(), status="draft"):
    return {
        "status": status,
        "open": len(open_sigs),
        "open_sigs": list(open_sigs),
        "done_sigs": list(done_sigs),
    }


def _plan_gate(head):
    return type(
        "_Gate",
        (),
        {
            "queue_head": staticmethod(lambda _root: head),
            "pr_plan_set": staticmethod(lambda _root, _body: ((head,) if head else (), [])),
        },
    )


def _keys(gate, base, head_rows):
    """The `::finding::` keys P-A1 emits for `head_rows` against `base`, read back the way the gate ledger reads a log."""
    scope, _notes, problem = gate.clock_scope(_plan_gate(HEAD), "/nonexistent", base, head_rows)
    assert not problem, problem
    on, _off = gate.split_by_scope(gate.open_offenders(head_rows, FINISHED), scope)
    buf = io.StringIO()
    for finding in gate.clock_findings(on):
        log.emit_finding(gate.key_of(finding), buf)
    keys = gate_ledger.finding_keys(buf.getvalue().splitlines())
    assert len(keys) == len(on), "one key per plan on the clock: %r for %r" % (keys, on)
    return set(keys)


#: The queue head with three open boxes, and a side plan the branch ticked one box of and left two open: both on the clock.
BASE = {HEAD: _row(["h1", "h2", "h3"]), SIDE: _row(["s1", "s2", "s3"]), THIRD: _row(["t1", "t2"])}
TWO = {HEAD: _row(["h1", "h2", "h3"]), SIDE: _row(["s2", "s3"], ["s1"]), THIRD: _row(["t1", "t2"])}
TWO_KEYS = {"P-A1:" + HEAD, "P-A1:" + SIDE}


def test_two_plans_with_open_boxes_give_two_keys_named_for_the_plans(gate):
    assert _keys(gate, BASE, TWO) == TWO_KEYS


def test_a_tick_that_leaves_the_plan_open_leaves_the_key_set_identical(gate):
    ticked = dict(TWO, **{HEAD: _row(["h2", "h3"], ["h1"])})
    assert gate.open_offenders(ticked, FINISHED) != gate.open_offenders(TWO, FINISHED)
    assert _keys(gate, BASE, ticked) == _keys(gate, BASE, TWO)


def test_closing_a_plans_last_open_box_removes_exactly_its_key(gate):
    closed = dict(TWO, **{SIDE: _row([], ["s1", "s2", "s3"])})
    before, after = _keys(gate, BASE, TWO), _keys(gate, BASE, closed)
    assert before - after == {"P-A1:" + SIDE}
    assert after - before == set()


def test_a_third_plan_joining_the_clock_adds_exactly_one_key(gate):
    """The 2b147e4a6 shape: the branch ticks one box of a queued plan, which puts it on the clock with its other box still open."""
    joined = dict(TWO, **{THIRD: _row(["t2"], ["t1"])})
    before, after = _keys(gate, BASE, TWO), _keys(gate, BASE, joined)
    assert after - before == {"P-A1:" + THIRD}
    assert before - after == set()


def test_a_queued_plan_the_branch_did_not_tick_has_no_key(gate):
    """CONTROL for the case above: `THIRD` has open boxes in every fixture, so a key per open plan rather than per CLOCKED plan would pass it."""
    assert "P-A1:" + THIRD not in _keys(gate, BASE, TWO)
    assert _keys(gate, BASE, {HEAD: _row([], ["h1", "h2", "h3"])}) == set()


def test_a_path_outside_the_key_alphabet_is_still_keyed_per_plan(gate):
    """`_safe_key` hashes a key the alphabet refuses. The hash covers that plan's own key, so the other plan's key does not move with it."""
    odd = "agent/plans/PLAN with a space.md"
    keys = [gate.key_of(f) for f in gate.clock_findings([(HEAD, 1), (odd, 2)])]
    assert keys[0] == "P-A1:" + HEAD
    assert keys[1].startswith("P-A1:")
    assert log.FINDING_KEY_RE.match(keys[1])
    assert keys[1] == gate.key_of(gate.clock_findings([(odd, 9)])[0])


def test_the_orphan_controls_run_when_the_gate_is_loaded_by_file(gate) -> None:
    """The gate is loaded here with no sys.modules entry, the way an importlib caller loads it; the root swap must not look the module up by name (435ef88e.1)."""
    orphan_ok, ancestor_ok = gate._orphan_commit_controls(wl_planrec)
    assert orphan_ok is False, "a commit that is not an ancestor of HEAD must not resolve"
    assert ancestor_ok is True, "an ancestor must resolve"


# ---- the PR body a LOCAL run judges P-A1 against (PR-TASK 8ed364fe). Before the fix only GITHUB_EVENT_PATH was read, so `npm run ci:quick` was red on a PR whose Operational-Reason line CI admits.
REASON_BODY = "Plan: agent/plans/PLAN-x.md\nOperational-Reason: the last box is the merge\n"


def _gh_runner(calls, stdout="", returncode=0):
    def run(args, **kwargs):
        calls.append((list(args), kwargs))
        return ghx.GhResult(["gh", *args], returncode, stdout, "no pull requests found")

    return run


def test_local_run_reads_the_open_prs_body_and_admits(gate):
    calls: list = []
    body, note = gate.pr_body({}, runner=_gh_runner(calls, REASON_BODY + "\n"), branch="1008-1")
    assert calls, "no gh lookup was attempted outside CI"
    assert calls[0][0][:3] == ["pr", "view", "1008-1"]
    assert body == REASON_BODY.rstrip("\n")
    assert note == ""
    assert gate.pr_admits_open_boxes(gate.load_plan_gate()[0], body)


def test_local_run_without_a_readable_pr_says_so(gate):
    calls: list = []
    body, note = gate.pr_body({}, runner=_gh_runner(calls, "", returncode=1), branch="1008-1")
    assert calls
    assert body is None
    assert "judged without a PR body" in note
    assert not gate.pr_admits_open_boxes(gate.load_plan_gate()[0], body)


def test_the_body_is_read_only_when_a_plan_has_open_boxes(gate):
    reads: list = []

    def reader():
        reads.append(1)
        return REASON_BODY, ""

    assert gate.pr_body_for([], reader) == (None, "")
    assert reads == [], "a run with every box ticked made the PR body lookup"
    assert gate.pr_body_for([("agent/plans/PLAN-x.md", 2)], reader) == (REASON_BODY, "")
    assert reads == [1]


def test_github_actions_never_attempts_the_local_lookup(gate, tmp_path):
    calls: list = []
    event = tmp_path / "event.json"
    event.write_text('{"pull_request": {"body": "from the event"}}', encoding="utf-8")
    env = {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_PATH": str(event)}
    body, note = gate.pr_body(env, runner=_gh_runner(calls, REASON_BODY), branch="b")
    assert calls == []
    assert body == "from the event"
    assert note == ""
    # No payload under Actions (a push or cron run) stays None and silent: the event file is the only source there.
    body, note = gate.pr_body({"GITHUB_ACTIONS": "true"}, runner=_gh_runner(calls, REASON_BODY))
    assert calls == []
    assert body is None
    assert note == ""
