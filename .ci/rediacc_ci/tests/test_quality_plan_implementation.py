"""`check:ci-plan-implementation` P-A1: one finding key per plan on the clock, never one over the set.

THE DEFECT THIS PINS (worklist #08d1e96f, 2026-10-13). P-A1 was a single finding listing every plan on the clock, keyed by a hash of that message. Commit 2b147e4a6 ticked two boxes of a queued plan, which put that plan on the clock, and `P-A1:0c9ea2c3e2ce` became `P-A1:99bbfe3180cd`. No plan the carry in `.ci/config/carried-reds.json` named had changed, and the push guard refused the push all the same.

WHAT MOVED THE OLD KEY, MEASURED. Not a count: `log.finding_key` masks digits, so a tick that left its plan open kept the old key (the second case below passes on the old code too, and stays as the control). The old key moved whenever the SET of plans changed, by a plan leaving the clock or joining it. The third and fourth cases are the ones the old code fails.

EVERY CASE GOES THROUGH THE PATH `main()` TAKES: `open_offenders`, `clock_scope`, `split_by_scope`, `clock_findings`, `key_of`, then the real emitter and the reader the gate ledger uses. The queue head is injected through a stand-in for `rediacc_hooks.plan_gate`, as the gate's own C12 control does.
"""

import importlib.util
import io
import json
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


# ---- PUSH VERSUS MERGE (agent/plans/PLAN-ciquick-green-then-batch.md G1). Open boxes are backlog at push and a finding at the merge; a ticked box whose evidence does not resolve is red at push all the same. Every case runs the functions main() runs: clock_scope, split_by_scope, run_context, clock_verdict, tick_findings, key_of.


def _verdict_keys(gate, context, base, head_rows, admitted=False):
    scope, _notes, problem = gate.clock_scope(_plan_gate(HEAD), "/nonexistent", base, head_rows)
    on, _off = gate.split_by_scope(gate.open_offenders(head_rows, FINISHED), scope)
    findings, info = gate.clock_verdict(context, problem, on, admitted)
    return {gate.key_of(f) for f in findings}, info


def test_open_boxes_alone_do_not_refuse_a_push_and_stay_visible(gate):
    keys, info = _verdict_keys(gate, gate.CONTEXT_PUSH, BASE, TWO)
    assert keys == set(), "open boxes alone refused a push: %r" % keys
    assert len(info) == 1, info
    assert "P-A1 BACKLOG" in info[0]
    assert HEAD + " (3)" in info[0]
    assert SIDE + " (2)" in info[0]


def test_open_boxes_still_refuse_in_the_merge_context(gate):
    keys, info = _verdict_keys(gate, gate.CONTEXT_MERGE, BASE, TWO)
    assert keys == TWO_KEYS
    assert info == []


def test_an_operational_reason_admits_at_the_merge(gate):
    keys, info = _verdict_keys(gate, gate.CONTEXT_MERGE, BASE, TWO, admitted=True)
    assert keys == set()
    assert "Operational-Reason" in info[0]


def test_a_scope_problem_refuses_a_push(gate):
    findings, _info = gate.clock_verdict(gate.CONTEXT_PUSH, "a planted Depends-On cycle", [], False)
    assert [f.split(":", 1)[0] for f in findings] == ["P-A1 NO SCOPE"]


@pytest.mark.parametrize(
    ("payload", "argv", "expected"),
    [
        ({"pull_request": {"draft": False}}, [], "merge"),
        ({"pull_request": {"draft": True}}, [], "push"),
        ({"ref": "refs/heads/main"}, [], "push"),
        ({"pull_request": {"draft": True}}, ["--merge"], "merge"),
    ],
)
def test_the_context_is_read_from_the_event_or_the_flag(gate, tmp_path, payload, argv, expected):
    event = tmp_path / "event.json"
    event.write_text(json.dumps(payload), encoding="utf-8")
    context, why = gate.run_context(argv, {"GITHUB_EVENT_PATH": str(event)})
    assert context == expected, why
    assert why


@pytest.mark.parametrize(
    "payload", [{"pull_request": {}}, {"pull_request": {"draft": "no"}}, {"ref": "x"}]
)
def test_a_pull_request_payload_that_cannot_be_judged_is_the_merge(gate, tmp_path, payload):
    """Fail closed (e8304e45.1): a pull_request event whose payload lacks a boolean `draft` is the stricter context, with the real reason."""
    event = tmp_path / "event.json"
    event.write_text(json.dumps(payload), encoding="utf-8")
    env = {"GITHUB_EVENT_PATH": str(event), "GITHUB_EVENT_NAME": "pull_request"}
    context, why = gate.run_context([], env)
    assert context == gate.CONTEXT_MERGE, why
    assert "fail closed" in why
    assert "draft PR or not a pull_request" not in why


@pytest.mark.parametrize("content", [None, "{not json"])
def test_an_unreadable_pull_request_payload_is_the_merge_but_a_push_payload_is_not(
    gate, tmp_path, content
):
    event = tmp_path / "event.json"
    if content is not None:
        event.write_text(content, encoding="utf-8")
    pr_env = {"GITHUB_EVENT_PATH": str(event), "GITHUB_EVENT_NAME": "pull_request"}
    context, why = gate.run_context([], pr_env)
    assert context == gate.CONTEXT_MERGE, why
    assert "cannot be read" in why
    push_context, push_why = gate.run_context([], dict(pr_env, GITHUB_EVENT_NAME="push"))
    assert push_context == gate.CONTEXT_PUSH, push_why


def test_a_pull_request_run_with_no_payload_path_is_the_merge(gate):
    """Review 0911a576.1: an empty GITHUB_EVENT_PATH on a pull_request run fails closed; on a push or a local run it is a push."""
    context, why = gate.run_context(
        [], {"GITHUB_EVENT_PATH": "", "GITHUB_EVENT_NAME": "pull_request"}
    )
    assert context == gate.CONTEXT_MERGE, why
    assert (
        gate.run_context([], {"GITHUB_EVENT_PATH": "", "GITHUB_EVENT_NAME": "push"})[0]
        == gate.CONTEXT_PUSH
    )
    assert gate.run_context([], {})[0] == gate.CONTEXT_PUSH


def test_a_push_event_carrying_a_pull_request_object_without_draft_stays_a_push(gate, tmp_path):
    """Review 0911a576.2: the no-boolean-draft branch fails closed only for a pull_request event."""
    event = tmp_path / "event.json"
    event.write_text('{"pull_request": {"number": 7}}', encoding="utf-8")
    push = gate.run_context([], {"GITHUB_EVENT_PATH": str(event), "GITHUB_EVENT_NAME": "push"})
    assert push[0] == gate.CONTEXT_PUSH, push[1]
    pr = gate.run_context(
        [], {"GITHUB_EVENT_PATH": str(event), "GITHUB_EVENT_NAME": "pull_request"}
    )
    assert pr[0] == gate.CONTEXT_MERGE, pr[1]


def _drive_main(gate, monkeypatch, capsys, argv):
    """main() on the real tree's config and ledger, with the controls, the scope and the open-box set stood in: one plan on the clock with two open boxes."""
    monkeypatch.delenv("GITHUB_EVENT_PATH", raising=False)
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    monkeypatch.setattr(gate, "controls_fired", lambda *_a, **_k: ([], gate.MIN_CONTROLS))
    monkeypatch.setattr(gate, "prefetch_partial_clone", lambda _root: "")
    monkeypatch.setattr(gate, "open_offenders", lambda _plans, _fin: [(HEAD, 2)])
    monkeypatch.setattr(gate, "load_plan_gate", lambda: (_plan_gate(HEAD), ""))
    monkeypatch.setattr(gate, "pr_body_for", lambda _o, _r=None: (None, ""))
    monkeypatch.setattr(gate, "clock_scope", lambda *_a, **_k: ({HEAD: "queue head"}, [], ""))
    gate.main(argv)
    out = capsys.readouterr()
    return out.out + out.err


def test_main_with_merge_refuses_an_open_box_and_without_it_does_not(gate, monkeypatch, capsys):
    merged = _drive_main(gate, monkeypatch, capsys, ["--merge"])
    assert "P-A1 context: merge" in merged
    assert "P-A1:" + HEAD in merged, merged
    pushed = _drive_main(gate, monkeypatch, capsys, [])
    assert "P-A1 context: push" in pushed
    assert "P-A1:" + HEAD not in pushed, pushed
    assert "P-A1 BACKLOG" in pushed


def test_a_local_run_is_the_push_context(gate):
    assert gate.run_context([], {})[0] == gate.CONTEXT_PUSH
    assert gate.run_context(["--merge"], {})[0] == gate.CONTEXT_MERGE


#: One box of SIDE moved open -> done on the branch, ticked after the baseline; one box of SIDE stays open.
TICK_BASE = {SIDE: _row(["s1", "s2"])}
TICK_HEAD = {SIDE: _row(["s2"], ["s1"])}
TICK_ROW = {
    "plan": SIDE,
    "sig": "s1",
    "head": "H0",
    "verdict": "present",
    "pointers": [["commit", "deadbeefcafe"]],
}


def _tick_keys(gate, evidence, row, resolves):
    return {
        gate.key_of(f)
        for f in gate.tick_findings(
            gate.moved_to_done(TICK_BASE, TICK_HEAD),
            lambda _r, _s: evidence,
            lambda _r, _s: row,
            lambda _k, _t: (resolves, "ok" if resolves else "no such commit"),
            lambda _r, _s: "C1",
            lambda _c: "2026-11-08",
            lambda _a, _b: True,
            "2026-01-01",
            lambda _c: None,
            lambda _c: "",
        )
    }


def test_a_ticked_box_whose_evidence_does_not_resolve_still_refuses_at_push(gate):
    """In the push context P-A1 is silent on the box left open in SIDE, and the tick's own evidence is still judged: a pointer that does not resolve, a missing row and a missing evidence line each red."""
    context, _why = gate.run_context([], {})
    assert context == gate.CONTEXT_PUSH
    pa1_keys, _info = _verdict_keys(gate, context, TICK_BASE, TICK_HEAD)
    assert pa1_keys == set()
    assert _tick_keys(gate, "ran the gate, exit 0", TICK_ROW, True) == set(), (
        "CONTROL: a healthy tick was reported"
    )
    assert _tick_keys(gate, "ran the gate, exit 0", TICK_ROW, False) == {
        gate.box_key("P-A3", SIDE, "s1", "commit:deadbeefcafe")
    }
    assert _tick_keys(gate, "ran the gate, exit 0", None, True) == {
        gate.box_key("P-A2:no-row", SIDE, "s1")
    }
    assert _tick_keys(gate, "", TICK_ROW, True) == {gate.box_key("P-A2:no-evidence", SIDE, "s1")}
