"""The judge is handed the facts its checklist used to make it read for (agent/plans/PLAN-stop-hook-retro-20261110.md R20261110.4, .5, .7).

  R20261110.4  MISSING IDS is a set difference against the message, and WAKE TIMER comes from a live wl_wake lock. At 20:36:18 and 08:20:57 the judge objected that a message said only "wake timer is armed", while the hook's own lock held the fire time.
  R20261110.5  ITEM WORKERS names every worker a remaining item was leased to, with its agent type and report title. At 23:20:25 the judge demanded a Plan agent for K1.7's root cause, which diagnosis agent ab68f85bb599acb4a had already returned.
  R20261110.7  A content-free continue ("Duplicate call ignored." / "Ignore.", 21:21:06) reads as stop and is reported as the `judge-contentless` advisory.

Every case has its inverse, and the last two drive the real Stop hook.
"""

from __future__ import annotations

import calendar
import json
import stat
import subprocess
import sys
import tempfile
import time
import types

import pytest

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_roster import mk_sub, plant_lease

J = wlfix.import_wl("wl_judge")
CK = wlfix.import_wl("wl_checks")
M = wlfix.import_wl("worklist_messages")
WAKE = wlfix.import_wl("wl_wake")
REPORT = wlfix.import_wl("wl_report")

ME = wlfix.ME
WAKE_AT = calendar.timegm((2026, 11, 10, 8, 50, 0))
# The 08:20:57 message: the timer is named, its time is not.
MSG_0820 = (
    "Waiting on #a1a1a1a1 (the drill) and #b2b2b2b2 (the bench run); wake timer is armed.\n\n"
    "## Remaining\n- #a1a1a1a1 drill, ongoing\n- #b2b2b2b2 bench run, ongoing"
)
RECS = [
    {"id": "a1a1a1a1", "state": ">", "worker": "bxyz12345", "lease_workers": ["bxyz12345"]},
    {"id": "b2b2b2b2", "state": " "},
    {"id": "c3c3c3c3", "state": "?"},
]
K17_WORKER = "ab68f85bb599acb4a"


@pytest.fixture
def tmpdir_root(tmp_path, monkeypatch):
    """tempfile.gettempdir() under tmp_path, so the wake lock is the fixture's."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    return tmp_path


@pytest.fixture
def waker():
    """A live process whose argv carries `wl_wake`, the test wl_wake.is_waker_pid makes."""
    proc = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.read()", "wl_wake.py"],
        stdin=subprocess.PIPE,
    )
    # Popen returns after fork: until the child execs, /proc/<pid>/cmdline is still pytest's own,
    # so a loaded host judged the lock dead (ci:quick 1112s). Wait for the exec, bounded.
    deadline = time.monotonic() + 30
    while not WAKE.is_waker_pid(proc.pid):
        assert time.monotonic() < deadline, "the waker child never exec'd"
        time.sleep(0.01)
    try:
        yield proc
    finally:
        assert proc.stdin is not None
        proc.stdin.close()
        proc.wait(timeout=30)


def plant_wake(pid):
    WAKE.lock_path(ME).write_text(
        json.dumps({"pid": pid, "start": WAKE_AT - 1800, "until": WAKE_AT, "minutes": 30}),
        encoding="utf-8",
    )


def facts(message, recs=RECS, reports=(), read_only=frozenset({"Plan", "Explore"})):
    return CK._judge_facts(
        ME, message, recs, ["7"], "/nonexistent", reports=list(reports), read_only=read_only
    )


# ---- R20261110.4: MISSING IDS ---------------------------------------------------------------------


@pytest.mark.usefixtures("tmpdir_root")
def test_missing_ids_is_the_set_difference_against_the_message():
    got = facts(MSG_0820)
    assert got["tracked"] == ["a1a1a1a1", "b2b2b2b2", "c3c3c3c3", "7"]
    assert got["missing_ids"] == ["c3c3c3c3", "7"]


@pytest.mark.usefixtures("tmpdir_root")
def test_inverse_a_message_naming_every_id_misses_none():
    got = facts(MSG_0820 + "\n- #c3c3c3c3 parked\n- task #7 pending")
    assert got["missing_ids"] == []


@pytest.mark.usefixtures("tmpdir_root")
def test_a_bare_id_counts_and_a_longer_hex_run_does_not():
    got = facts("a1a1a1a1 b2b2b2b2ff #c3c3c3c3 7")
    assert got["missing_ids"] == ["b2b2b2b2"]


# ---- R20261110.4: WAKE TIMER ----------------------------------------------------------------------


@pytest.mark.usefixtures("tmpdir_root")
def test_a_live_wake_lock_gives_its_fire_time(waker):
    plant_wake(waker.pid)
    assert facts(MSG_0820)["wake_until"] == WAKE_AT


@pytest.mark.usefixtures("tmpdir_root")
def test_inverse_a_dead_lock_pid_gives_none():
    dead = subprocess.Popen([sys.executable, "-c", "pass", "wl_wake.py"])
    dead.wait(timeout=30)
    plant_wake(dead.pid)
    assert facts(MSG_0820)["wake_until"] is None


@pytest.mark.usefixtures("tmpdir_root")
def test_control_no_lock_gives_none():
    assert facts(MSG_0820)["wake_until"] is None


# ---- R20261110.5: ITEM WORKERS --------------------------------------------------------------------


def k17(atype):
    rec = {"id": "k17k17k1", "state": " ", "worker": "", "lease_workers": [K17_WORKER]}
    row = {
        "id": REPORT.short_id(K17_WORKER),
        "type": atype,
        "title": "K1.7 diagnosis: the stall is the fsync in the chunk writer",
    }
    return rec, row


@pytest.mark.usefixtures("tmpdir_root")
def test_k17_finished_diagnosis_worker_is_named_with_type_and_title():
    rec, row = k17("general-purpose")
    [w] = facts("", recs=[rec], reports=[row])["item_workers"]["k17k17k1"]
    assert w == {
        "id": K17_WORKER,
        "current": False,
        "type": "general-purpose",
        "kind": "writer",
        "title": row["title"],
    }


@pytest.mark.usefixtures("tmpdir_root")
@pytest.mark.parametrize(("atype", "kind"), [("Plan", "Plan"), ("Explore", "read-only")])
def test_plan_and_read_only_workers_are_told_apart(atype, kind):
    rec, row = k17(atype)
    [w] = facts("", recs=[rec], reports=[row])["item_workers"]["k17k17k1"]
    assert w["kind"] == kind


@pytest.mark.usefixtures("tmpdir_root")
def test_inverse_an_item_never_leased_has_no_workers():
    got = facts("", recs=[{"id": "k17k17k1", "state": " "}])
    assert got["item_workers"] == {}


@pytest.mark.usefixtures("tmpdir_root")
def test_the_current_worker_and_the_placeholders():
    rec = {
        "id": "d4d4d4d4",
        "state": ">",
        "worker": "a2222222222222222",
        "lease_workers": ["queue", "lead", K17_WORKER, "a2222222222222222"],
    }
    got = facts("", recs=[rec])["item_workers"]["d4d4d4d4"]
    assert [(w["id"], w["current"], w["kind"]) for w in got] == [
        (K17_WORKER, False, ""),
        ("a2222222222222222", True, ""),
    ]


def test_the_report_index_is_read_from_the_store_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    store = tmp_path / "reports"
    store.mkdir()
    monkeypatch.setenv("WORKLIST_REPORTS_DIR", str(store))
    rec, row = k17("general-purpose")
    (store / "index.jsonl").write_text(json.dumps(dict(row, ev="report")) + "\n", "utf-8")
    got = CK._judge_facts(ME, "", [rec], [], str(tmp_path), read_only=frozenset({"Plan"}))
    assert got["item_workers"]["k17k17k1"][0]["title"] == row["title"]


def test_remaining_recs_finds_the_open_records_behind_the_lines():
    store = wlfix.import_wl("wl_store")
    base = {"owner": ME, "text": "", "lastnote": ""}
    a = dict(base, id="a1a1a1a1", state=" ", basetext="the drill")
    b = dict(base, id="b2b2b2b2", state=" ", basetext="not in scope")
    c = dict(base, id="c3c3c3c3", state=" ", basetext="the drill", owner="cafe1234")
    d = dict(base, id="d4d4d4d4", state="?", basetext="parked")
    fold = types.SimpleNamespace(items=[a, b, c, d])
    lines = [store.brief_line(a) + "   <- a suffix classify_items adds"]
    got = CK._remaining_recs(fold, wlfix.SID, lines, [d], [])
    assert [r["id"] for r in got] == ["a1a1a1a1", "d4d4d4d4"]


# ---- the prompt, through a canned claude ----------------------------------------------------------


@pytest.fixture
def judge(tmp_path, monkeypatch):
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


STOP = {
    "verdict": "stop",
    "reason": "Named live waits on #a1a1a1a1 and #b2b2b2b2.",
    "next_action": "",
}


def ask(message, got_facts):
    return J.run_judge(
        ["- [>] (deadbeef) the drill", "- [ ] (deadbeef) the bench run"],
        1,
        message,
        0,
        "none declared",
        with_riders=False,
        facts=got_facts,
    )


@pytest.mark.usefixtures("tmpdir_root")
def test_the_0820_prompt_says_the_schedule_check_passed(waker, judge):
    plant_wake(waker.pid)
    judge.answer(dict(STOP))
    verdict, err = ask(MSG_0820, facts(MSG_0820, recs=RECS[:2]))
    assert err is None, err
    prompt = judge.prompt()
    assert "WAKE TIMER: armed, fires at 2026-11-10T08:50Z" in prompt
    assert "MISSING IDS (tracked ids the message never names): #7" in prompt
    assert "WAKE TIMER armed with a fire time, this check\n    PASSES" in prompt
    assert "never claim an omission it does not list" in prompt
    assert verdict["verdict"] == "stop"


@pytest.mark.usefixtures("tmpdir_root")
def test_inverse_a_dead_lock_says_none_armed(judge):
    dead = subprocess.Popen([sys.executable, "-c", "pass", "wl_wake.py"])
    dead.wait(timeout=30)
    plant_wake(dead.pid)
    judge.answer(dict(STOP))
    _verdict, err = ask(MSG_0820, facts(MSG_0820))
    assert err is None, err
    assert "WAKE TIMER: none armed" in judge.prompt()


@pytest.mark.usefixtures("tmpdir_root")
def test_the_k17_worker_reaches_the_prompt(judge):
    rec, row = k17("general-purpose")
    judge.answer(dict(STOP))
    _verdict, err = ask("K1.7 is diagnosed.", facts("", recs=[rec], reports=[row]))
    assert err is None, err
    prompt = judge.prompt()
    assert "#k17k17k1: past worker %s (general-purpose, writer) report:" % K17_WORKER in prompt
    assert "names a Plan or writer worker is already\n    delegated" in prompt


def test_control_without_facts_the_prompt_has_no_section(judge):
    judge.answer(dict(STOP))
    _verdict, err = ask(MSG_0820, None)
    assert err is None, err
    assert "MEASURED FACTS," not in judge.prompt()


# ---- R20261110.7: the content-free verdict --------------------------------------------------------

CONTENTLESS = {"verdict": "continue", "reason": "Duplicate call ignored.", "next_action": "Ignore."}


def test_the_2121_verdict_reads_as_stop_with_an_advisory():
    got = J.settle_contentless(dict(CONTENTLESS))
    assert got["verdict"] == "stop"
    assert got["next_action"] == ""
    assert "JUDGE CONTENTLESS" in got["contentless"]
    assert "Duplicate call ignored." in got["contentless"]


@pytest.mark.parametrize("action", ["none", "N/A", "Nothing.", "", "  ignore!  "])
def test_a_non_order_reads_as_stop(action):
    out = {"verdict": "continue", "reason": "A" * 60, "next_action": action}
    assert J.settle_contentless(out)["verdict"] == "stop"


def test_a_short_reason_naming_nothing_with_a_bare_order_reads_as_stop():
    out = {"verdict": "continue", "reason": "Not done.", "next_action": "Keep going."}
    got = J.settle_contentless(out)
    assert got["verdict"] == "stop"
    assert "a reason that names nothing" in got["reason"]


@pytest.mark.parametrize(
    "action",
    ["Fix the failing test in foo.py", "Wait for CI, then flip the PR ready", "Fix #a1b2c3d4"],
)
def test_inverse_a_short_reason_beside_a_real_order_stands(action):
    out = {"verdict": "continue", "reason": "a test is red", "next_action": action}
    assert J.settle_contentless(out)["verdict"] == "continue"


@pytest.mark.parametrize(
    "reason",
    [
        "Fix #a1b2c3d4 first.",
        "wl_judge.py is broken.",
        "See .claude/hooks/x.",
        "CI run 19283746 is red.",
    ],
)
def test_inverse_a_short_reason_that_names_something_stands(reason):
    out = {"verdict": "continue", "reason": reason, "next_action": "Fix it and add the test."}
    assert J.settle_contentless(out)["verdict"] == "continue"


def test_inverse_a_substantive_continue_stands():
    out = {
        "verdict": "continue",
        "reason": "The message reports the wl_judge.py finding without fixing it.",
        "next_action": "Fix the finding and add its regression test.",
    }
    assert J.settle_contentless(out) == out


def test_control_a_stop_is_untouched():
    out = dict(CONTENTLESS, verdict="stop")
    assert J.settle_contentless(out) == out


def test_run_judge_reads_the_2121_verdict_as_stop(judge):
    judge.answer(dict(CONTENTLESS))
    verdict, err = ask("Waiting.", None)
    assert err is None, err
    assert verdict["verdict"] == "stop"
    assert verdict["contentless"]


# ---- the real Stop hook: facts reach the prompt, a contentless continue is an advisory ---------


@pytest.fixture
def wl(tmp_path):
    fixture = wlfix.Fixture(tmp_path / "hookfix")
    fixture.setup()
    return fixture


def hook_world(fix, out):
    """One live leased writer; the canned claude records its prompt and answers `out`."""
    fix.settings(effort="high")
    fix.brief_now()
    fix.hand_now()
    mk_sub(fix, "a1111111111111111", "general-purpose", 0)
    plant_lease(fix, "jw01abcd", "a1111111111111111")
    seen = fix.base / "prompt.json"
    script = fix.base / "binonly" / "claude"
    script.write_text(
        "#!/usr/bin/env python3\nimport json, sys\n"
        "open(%r, 'w').write(json.dumps(sys.argv[1:]))\n"
        "print(%r)\n" % (str(seen), json.dumps({"is_error": False, "structured_output": out})),
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    fix.say("waiting on the writer\n\n## Remaining\n- the writer's item")
    return seen


def queued(fix):
    path = fix.wl.with_suffix(".state-%s.json" % ME)
    doc = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return {
        str(e.get("key")).split(":")[0]: str(e.get("text"))
        for e in (doc.get("outq") or {}).get("items") or []
    }


def test_the_stop_hook_hands_the_judge_its_facts_and_queues_a_contentless_continue(wl):
    seen = hook_world(wl, dict(CONTENTLESS))
    got = wl.runj()
    assert "judge says continue" not in got.out, got.out[:800]
    argv = json.loads(seen.read_text(encoding="utf-8"))
    prompt = argv[argv.index("-p") + 1]
    assert "MEASURED FACTS," in prompt
    assert "MISSING IDS (tracked ids the message never names): #jw01abcd" in prompt
    assert "#jw01abcd: current worker a1111111111111111" in prompt
    # Queued, then drained onto this allow's report or kept for the next one.
    shown = got.out + "".join(queued(wl).values())
    assert "JUDGE CONTENTLESS" in shown, got.out[:1500]


def test_inverse_the_stop_hook_blocks_on_a_substantive_continue(wl):
    hook_world(
        wl,
        {
            "verdict": "continue",
            "reason": "The message reports the wl_judge.py finding without fixing it.",
            "next_action": "Fix the finding and add its regression test.",
        },
    )
    got = wl.runj()
    assert got.decision == "block", got.out[:800]
    assert "judge says continue" in got.out, got.out[:800]
    assert "judge-contentless" not in queued(wl)
