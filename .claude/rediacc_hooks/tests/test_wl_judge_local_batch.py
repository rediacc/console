"""The local-batch judge paragraph is told which open boxes are local work (agent/plans/PLAN-stop-hook-retro-20261110.md R20261110.1, R20261110.2).

In the 2026-11-09/10 window JUDGE_LOCAL_BATCH ended with "the next action advances the batch's open boxes locally" on every judge call, and 55 continues ordered box work that did not exist: every open box needed a live system, a CI run, the operator or a push. Two halves fix it:

  R20261110.1  `--plan-investigate ... partial` requires `--owed <kind>` and stores it on the row, so what a partial box still owes is a field and not a free-text note.
  R20261110.2  `wl_checks._batch_box_facts` classes each open box of the batch `non-writer` (by tag), `owed:<kind>` (newest partial row) or `local`; the prompt names them, and with no local box a continue that only orders batch work is read as stop (`wl_judge.settle_batch_no_local`).

Every case has its inverse, differing by one planted fact.
"""

from __future__ import annotations

import json
import stat
import types

import pytest

from rediacc_hooks.tests import wlfix

J = wlfix.import_wl("wl_judge")
R = wlfix.import_wl("wl_planrec")
CK = wlfix.import_wl("wl_checks")
M = wlfix.import_wl("worklist_messages")

REL = "agent/plans/PLAN-batch-fixture.md"
NOTE = "the parser half of this box is in the tree; the rest is a live step on the fleet"

# The 04:13:18 state, in miniature: every open box of the batch waits on something no local edit supplies. Tagged boxes are non-writer; the untagged ones (A1a, A4d, J6, ... carried no tag in PLAN-backup-program.md) carry a partial row with what they owe.
TAGGED = [
    "H3 [hostinger] restore drill on hostinger",
    "L2 [bench] bench round-trip",
    "LP-1 [live] live proof of the backup plane",
    "Q2 [operator] operator window for the key rotation",
    "K10 [post-merge] nightly after the merge",
]
OWED = {
    "A1a a PR preview of the docs page": "post-push",
    "A4d CI run ids recorded for the gate": "ci",
    "J6 suite runs in CI nightly": "ci",
    "J9 the second CI leg is green": "ci",
    "I3 elite live round-trip": "live",
    "P15 the receipts for the batch": "operator",
}


def plan_text(extra=()):
    lines = ["- [ ] %s" % b for b in (*TAGGED, *OWED, *extra)]
    return "# PLAN: batch fixture\nStatus: ready\nUpdated: 2026-11-10\n\n## Tasks\n\n%s\n" % (
        "\n".join(lines)
    )


def sig_of(text, prefix):
    return next(sig for _i, _raw, body, sig in R.open_boxes(text) if body.startswith(prefix))


def write_rows(root, rows):
    ledger = root.joinpath(*R.INVESTIGATION_REL)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def batch_world(root, extra=(), extra_rows=()):
    text = plan_text(extra)
    (root / REL).parent.mkdir(parents=True, exist_ok=True)
    (root / REL).write_text(text, encoding="utf-8")
    rows = [
        {"plan": REL, "sig": sig_of(text, body.split()[0] + " "), "verdict": "partial", "owed": k}
        for body, k in OWED.items()
    ]
    write_rows(root, [*rows, *extra_rows])
    return types.SimpleNamespace(plans=(REL,), finished=0, batch_size=3), text


# ---- R20261110.1: --owed on a partial investigation ---------------------------------------------


@pytest.fixture
def wl(tmp_path):
    fixture = wlfix.Fixture(tmp_path / "hookfix")
    fixture.setup()
    return fixture


def plant_plan(fix):
    body = "B1 the one open box this row investigates"
    (fix.proj / "agent" / "plans").mkdir(parents=True, exist_ok=True)
    (fix.proj / REL).write_text(
        "# PLAN: owed fixture\nStatus: ready\nOwner: %s\nUpdated: 2026-11-10\n\n"
        "## Tasks\n\n- [ ] %s\n" % (fix.sid, body),
        encoding="utf-8",
    )
    (fix.proj / "seed.txt").write_text("seed line\n", encoding="utf-8")
    return R.box_sig(body)


def investigate(fix, sig, verdict, *flags):
    return fix.cli(
        "--plan-investigate",
        wlfix.ME,
        REL,
        sig,
        verdict,
        *flags,
        "fileline:seed.txt:1",
        "plan:%s" % REL,
        "--",
        NOTE,
        "--write",
    )


def ledger_rows(fix):
    path = fix.proj.joinpath(*R.INVESTIGATION_REL)
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_a_partial_without_owed_is_refused_and_the_refusal_names_the_flag(wl):
    sig = plant_plan(wl)
    got = investigate(wl, sig, "partial")
    assert got.rc == 2, (got.rc, got.out, got.err)
    assert "--owed" in got.err, got.err
    assert ledger_rows(wl) == []


def test_a_partial_with_owed_writes_the_kind_on_the_row(wl):
    sig = plant_plan(wl)
    got = investigate(wl, sig, "partial", "--owed", "live")
    assert got.rc == 0, (got.rc, got.out, got.err)
    [row] = ledger_rows(wl)
    assert row["verdict"] == "partial"
    assert row["owed"] == "live"


def test_control_an_absent_verdict_needs_no_owed_and_carries_none(wl):
    sig = plant_plan(wl)
    got = investigate(wl, sig, "absent")
    assert got.rc == 0, (got.rc, got.out, got.err)
    [row] = ledger_rows(wl)
    assert "owed" not in row


@pytest.mark.parametrize(
    ("verdict", "kind", "needle"),
    [("absent", "live", "belongs to a `partial`"), ("partial", "soon", "is not one of")],
)
def test_owed_on_another_verdict_or_an_unknown_kind_is_refused(wl, verdict, kind, needle):
    sig = plant_plan(wl)
    got = investigate(wl, sig, verdict, "--owed", kind)
    assert got.rc == 2, (got.rc, got.out, got.err)
    assert needle in got.err, got.err
    assert ledger_rows(wl) == []


def test_owed_with_no_kind_is_a_usage_error(wl):
    sig = plant_plan(wl)
    got = wl.cli(
        "--plan-investigate", wlfix.ME, REL, sig, "partial", "fileline:seed.txt:1", "--owed"
    )
    assert got.rc == 2, (got.rc, got.out, got.err)
    assert "--owed takes a kind" in got.err, got.err


# ---- R20261110.2: the boxes, classed --------------------------------------------------------------


def test_every_box_of_the_0413_state_is_non_local(tmp_path):
    state, _text = batch_world(tmp_path)
    rows = CK._batch_box_facts(state, tmp_path)
    assert len(rows) == len(TAGGED) + len(OWED)
    classes = {bid: cls for _plan, bid, _sig, cls in rows}
    for body in TAGGED:
        assert classes[body.split()[0]] == "non-writer", classes
    for body, kind in OWED.items():
        assert classes[body.split()[0]] == "owed:" + kind, classes
    assert all(plan == "PLAN-batch-fixture.md" for plan, *_x in rows)


def test_inverse_a_box_with_no_row_is_local(tmp_path):
    state, _text = batch_world(tmp_path, extra=["Z9 a local thing with no row"])
    classes = {bid: cls for _plan, bid, _sig, cls in CK._batch_box_facts(state, tmp_path)}
    assert classes["Z9"] == "local"


@pytest.mark.parametrize(
    ("label", "row_extra"),
    [
        # D1: a partial row written before `owed` existed counts as local until it is re-recorded.
        ("an old partial row with no owed", {"verdict": "partial"}),
        ("a partial row owing code", {"verdict": "partial", "owed": "code"}),
        ("an absent row", {"verdict": "absent"}),
    ],
)
def test_rows_that_owe_code_or_nothing_named_keep_the_box_local(tmp_path, label, row_extra):
    text = plan_text(["Z9 a box with a row"])
    state, _text = batch_world(
        tmp_path,
        extra=["Z9 a box with a row"],
        extra_rows=[{"plan": REL, "sig": sig_of(text, "Z9 "), **row_extra}],
    )
    classes = {bid: cls for _plan, bid, _sig, cls in CK._batch_box_facts(state, tmp_path)}
    assert classes["Z9"] == "local", label


def test_the_newest_row_decides(tmp_path):
    text = plan_text(["Z9 a box re-recorded"])
    sig = sig_of(text, "Z9 ")
    state, _text = batch_world(
        tmp_path,
        extra=["Z9 a box re-recorded"],
        extra_rows=[
            {"plan": REL, "sig": sig, "verdict": "partial"},
            {"plan": REL, "sig": sig, "verdict": "partial", "owed": "live"},
        ],
    )
    classes = {bid: cls for _plan, bid, _sig, cls in CK._batch_box_facts(state, tmp_path)}
    assert classes["Z9"] == "owed:live"


def test_judge_local_batch_carries_open_local_and_rows(tmp_path, monkeypatch):
    state, _text = batch_world(tmp_path, extra=["Z9 a local thing with no row"])
    monkeypatch.setattr(CK, "local_batch_open", lambda *_a: True)
    got = CK._judge_local_batch(state, tmp_path)
    assert got is not None
    assert (got["finished"], got["batch"]) == (0, 3)
    assert got["open"] == len(TAGGED) + len(OWED) + 1
    assert got["local"] == 1
    assert len(got["rows"]) == got["open"]


def test_control_judge_local_batch_is_none_when_no_batch_fills(tmp_path, monkeypatch):
    state, _text = batch_world(tmp_path)
    monkeypatch.setattr(CK, "local_batch_open", lambda *_a: False)
    assert CK._judge_local_batch(state, tmp_path) is None


def test_a_failed_box_read_keeps_the_batch_facts(tmp_path, monkeypatch):
    state, _text = batch_world(tmp_path)
    monkeypatch.setattr(CK, "local_batch_open", lambda *_a: True)

    def boom(*_a):
        raise OSError("unreadable")

    monkeypatch.setattr(CK, "_batch_box_facts", boom)
    assert CK._judge_local_batch(state, tmp_path) == {"finished": 0, "batch": 3}


# ---- R20261110.2: the prompt and the settle, through a canned claude ----------------------------


@pytest.fixture
def judge(tmp_path, monkeypatch):
    """A canned `claude` that records its argv and answers `answer(...)`."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    seen = tmp_path / "argv.json"
    reply = tmp_path / "reply.json"
    script = bindir / "claude"
    script.write_text(
        "#!/usr/bin/env python3\nimport json, sys\n"
        "open(%r, 'w').write(json.dumps(sys.argv[1:]))\n"
        "print(open(%r).read())\n" % (str(seen), str(reply)),
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", "%s:/usr/bin:/bin" % bindir)
    monkeypatch.setenv("TMPDIR", str(tmp_path))

    def answer(out):
        reply.write_text(json.dumps({"is_error": False, "structured_output": out}), "utf-8")

    def prompt():
        got = json.loads(seen.read_text(encoding="utf-8"))
        return got[got.index("-p") + 1]

    return types.SimpleNamespace(answer=answer, prompt=prompt)


# The order the judge gave at 04:17:30, 04:19:22 and 04:21:17.
BATCH_CONTINUE = {
    "verdict": "continue",
    "reason": "0/3 plans finished and the batch's open boxes are never checked.",
    "next_action": "Advance the batch's open boxes locally.",
}


def ask(local_batch, tracked=None):
    return J.run_judge(
        ["[ ] (deadbeef) an open item"],
        0,
        "The 22 open boxes wait on live steps.",
        0,
        "none declared",
        local_batch=local_batch,
        with_riders=False,
        facts={"tracked": tracked or [], "missing_ids": []} if tracked is not None else None,
    )


def facts_for(root, monkeypatch, extra=()):
    state, _text = batch_world(root, extra=extra)
    monkeypatch.setattr(CK, "local_batch_open", lambda *_a: True)
    return CK._judge_local_batch(state, root)


def test_no_local_box_prompt_and_a_batch_continue_settles_to_stop(tmp_path, monkeypatch, judge):
    lb = facts_for(tmp_path / "w", monkeypatch)
    assert lb["local"] == 0
    judge.answer(dict(BATCH_CONTINUE))
    verdict, err = ask(lb)
    assert err is None, err
    prompt = judge.prompt()
    assert "There is NO local box work" in prompt
    assert "H3 [" in prompt
    assert "owed:ci" in prompt
    assert "advances\nthe batch's open boxes locally" not in prompt
    assert verdict["verdict"] == "stop", verdict
    assert "no local work" in verdict["reason"]
    assert verdict["next_action"] == ""


def test_inverse_one_local_box_keeps_the_continue(tmp_path, monkeypatch, judge):
    lb = facts_for(tmp_path / "w", monkeypatch, extra=["Z9 a local thing with no row"])
    assert lb["local"] == 1
    judge.answer(dict(BATCH_CONTINUE))
    verdict, err = ask(lb)
    assert err is None, err
    prompt = judge.prompt()
    assert "There is NO local box work" not in prompt
    assert "1 of the batch's" in prompt
    assert "Z9 [" in prompt
    assert verdict["verdict"] == "continue", verdict


def test_inverse_a_continue_naming_a_tracked_item_stands(tmp_path, monkeypatch, judge):
    lb = facts_for(tmp_path / "w", monkeypatch)
    judge.answer(dict(BATCH_CONTINUE, next_action="Work #a1b2c3d4 locally while the batch waits."))
    verdict, err = ask(lb, tracked=["a1b2c3d4"])
    assert err is None, err
    assert verdict["verdict"] == "continue", verdict


def test_a_continue_naming_an_untracked_id_still_settles(tmp_path, monkeypatch, judge):
    lb = facts_for(tmp_path / "w", monkeypatch)
    judge.answer(dict(BATCH_CONTINUE, next_action="Work #a1b2c3d4 locally in the batch."))
    verdict, err = ask(lb, tracked=["ffff0000"])
    assert err is None, err
    assert verdict["verdict"] == "stop", verdict


def test_inverse_a_continue_not_about_the_batch_stands(tmp_path, monkeypatch, judge):
    lb = facts_for(tmp_path / "w", monkeypatch)
    judge.answer(
        {
            "verdict": "continue",
            "reason": "The message reports a finding in wl_judge.py without fixing it.",
            "next_action": "Fix the finding in wl_judge.py and add its test.",
        }
    )
    verdict, err = ask(lb)
    assert err is None, err
    assert verdict["verdict"] == "continue", verdict


def test_control_without_box_rows_the_prompt_names_no_boxes_and_nothing_settles(judge):
    judge.answer(dict(BATCH_CONTINUE))
    verdict, err = ask({"finished": 0, "batch": 3})
    assert err is None, err
    prompt = judge.prompt()
    assert "TURBO LOCAL BATCH" in prompt
    assert "BATCH BOXES" not in prompt
    assert verdict["verdict"] == "continue", verdict


def test_settle_batch_no_local_alone():
    lb = {"rows": [("P.md", "H3", "12345678", "non-writer")], "local": 0, "open": 1}
    assert J.settle_batch_no_local(dict(BATCH_CONTINUE), lb)["verdict"] == "stop"
    assert J.settle_batch_no_local(dict(BATCH_CONTINUE), dict(lb, local=1))["verdict"] == (
        "continue"
    )
    assert J.settle_batch_no_local(dict(BATCH_CONTINUE), None)["verdict"] == "continue"
    stop = dict(BATCH_CONTINUE, verdict="stop")
    assert J.settle_batch_no_local(stop, lb) == stop
