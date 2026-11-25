"""Sub-agent completion marks and API-error resume (operator ask 2026-11-24, PR-TASK 79b7e92e).

Four mechanisms, each with a firing case and a control that differs by one planted fact:

- the pending-tick queue (wl_planbox): SubagentStop queues `present`/`done` TICK rows, an `applied` event retires one, readiness waits on an unlanded lease commit;
- `worklist.py --apply-ticks <me> [--write]` (wl_cli): a ready row becomes an investigation row plus a tick, a refused row is kept and the verb exits 1;
- the SubagentStop resume (wl_report): an API-error stop with `stop_hook_active` false returns `decision: block`, at most RESUME_SELF_MAX times per agent, and every invocation is logged;
- the Stop-side resume block (wl_roster_resume, check `resume-dead-agent`): a lead agent whose transcript ends in an API error is named with its SendMessage line until the parent transcript shows that SendMessage.

Plus the refusal exit codes of `--plan-tick`/`--plan-investigate --write`, pinned non-zero.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from typing import TYPE_CHECKING

import pytest

from rediacc_hooks.tests import wlfix

if TYPE_CHECKING:
    import pathlib

PB = wlfix.import_wl("wl_planbox")
RP = wlfix.import_wl("wl_report")
RR = wlfix.import_wl("wl_roster_resume")
PR = wlfix.import_wl("wl_planrec")
ROSTER = wlfix.import_wl("wl_roster")
ME = wlfix.ME
REPORT_PY = wlfix.STOP_DIR / "wl_report.py"

PLAN_TEXT = (
    "# PLAN\nStatus: approved\nOwner: deadbeef\nDepends-On: no-dep -- x\nPriority: P2 -- s\n"
    "Concurrency: parallel\nOwns: docs/x/**\n\n## Boxes\n- [ ] O1 an open box sits here\n"
    "  Accept: npm run check:fixture-gate\n"
)


def stamp(minutes_ago: float = 0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(time.time() - minutes_ago * 60))


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )


def mk_repo(root: pathlib.Path) -> str:
    """A git repo with one plan holding one open box; returns the box sig."""
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    plan = root / "agent" / "plans" / "PLAN-fx.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text(PLAN_TEXT, encoding="utf-8")
    (root / ".ci" / "config").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "config" / "plan-boxes.json").write_text(
        json.dumps({"plans": {}}), encoding="utf-8"
    )
    (root / "package.json").write_text(
        json.dumps({"scripts": {"check:fixture-gate": "true"}}), encoding="utf-8"
    )
    git(root, "add", "-A")
    git(root, "commit", "-qm", "chore: seed")
    return PR.open_boxes(plan.read_text(encoding="utf-8"))[0][3]


def tick_rows(sig, state="done", commits="-", owed="-", close="nothing"):
    return PB.parse_tick(
        "Report.\n\nTICK PLAN-fx.md#%s %s commits=%s landed=all owed=%s\n  close: %s\n"
        % (sig, state, commits, owed, close)
    )


# ---- the pending-tick queue ----------------------------------------------------------


def test_queue_holds_done_and_present_rows_once_and_applied_retires_them(tmp_path):
    rows = tick_rows("0123abcd") + tick_rows("89abcdef", state="present")
    wrote = PB.queue_ticks(tmp_path, ME, "a1", rows, "2026-11-24T00:00:00Z")
    assert [r["sig"] for r in wrote] == ["0123abcd", "89abcdef"]
    # The same report seen twice queues nothing new.
    assert PB.queue_ticks(tmp_path, ME, "a1", rows, "2026-11-24T00:00:01Z") == []
    pending = PB.pending_rows(tmp_path, ME)
    assert len(pending) == 2
    PB.mark_applied(tmp_path, ME, pending[0]["key"], "ticked", "2026-11-24T00:00:02Z")
    assert [r["sig"] for r in PB.pending_rows(tmp_path, ME)] == ["89abcdef"]


@pytest.mark.parametrize(
    "body",
    [
        "TICK PLAN-fx.md#0123abcd partial commits=- landed=C1 owed=C2:live\n",
        "TICK PLAN-fx.md#0123abcd done commits=- landed=all owed=C2:live\n",
        "TICK PLAN-fx.md#0123abcd untouched commits=- landed=- owed=-\n",
        # Legacy prose: the state is a guess, so nothing is queued.
        "TICK for agent/plans/PLAN-fx.md box `0123abcd` done in abc1234\n",
    ],
)
def test_control_open_owed_or_legacy_rows_are_not_queued(tmp_path, body):
    assert PB.queue_ticks(tmp_path, ME, "a1", PB.parse_tick(body), "x") == []
    assert not PB.pending_path(tmp_path, ME).exists()


def test_readiness_ready_waiting_landed_by_x_line_and_closed(tmp_path):
    root = tmp_path / "repo"
    sig = mk_repo(root)
    # No commit named: ready at once.
    row = PB.queue_ticks(root, ME, "a1", tick_rows(sig, state="present"), "x")[0]
    assert PB.readiness(root, row)[0] == "ready"
    # A commit on a side branch, not reachable from HEAD: waiting.
    git(root, "switch", "-q", "-c", "lease")
    (root / "w.txt").write_text("w\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "feat: lease work")
    lease = git(root, "rev-parse", "HEAD").stdout.strip()
    git(root, "switch", "-q", "main")
    row = {"plan": "PLAN-fx.md", "sig": sig, "commits": [lease[:10]]}
    verdict, detail, _picks = PB.readiness(root, row)
    assert verdict == "waiting", (verdict, detail)
    assert lease[:10] in detail, (verdict, detail)
    # Landed by `cherry-pick -x`: ready, and the pick names the LANDED sha, never the lease one.
    assert git(root, "cherry-pick", "-x", lease).returncode == 0
    landed = git(root, "rev-parse", "HEAD").stdout.strip()
    verdict, _detail, picks = PB.readiness(root, row)
    assert (verdict, picks) == ("ready", [(".", landed)])
    # An unknown sha is refused, never ready.
    assert PB.readiness(root, dict(row, commits=["abcdef1234"]))[0] == "refused"
    # The box ticked by hand: closed.
    plan = root / "agent" / "plans" / "PLAN-fx.md"
    plan.write_text(PLAN_TEXT.replace("- [ ] O1", "- [x] O1"), encoding="utf-8")
    assert PB.readiness(root, row)[0] == "closed"


# ---- SubagentStop: the queue, the log and the resume decision ---------------------------


def subagent_stop(proj, tmp_path, message, agent="a0000000000000aa", active=False):
    env = wlfix.scrubbed_environ()
    env.update(
        CLAUDE_PROJECT_DIR=str(proj),
        WORKLIST_REPORTS_DIR=str(tmp_path / "reports"),
        PYTHONPATH=os.pathsep.join([str(wlfix.STOP_DIR.parent.parent), str(wlfix.STOP_DIR)]),
    )
    event = {
        "session_id": wlfix.SID,
        "agent_id": agent,
        "agent_type": "general-purpose",
        "agent_transcript_path": "",
        "last_assistant_message": message,
        "stop_hook_active": active,
        "cwd": str(proj),
    }
    got = subprocess.run(
        [sys.executable, str(REPORT_PY), "--subagent-stop"],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert got.returncode == 0, got.stderr
    return got.stdout


def stop_log(proj):
    path = RP.stop_log_path(proj, ME)
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def test_subagent_stop_queues_the_reports_done_tick(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    out = subagent_stop(
        proj, tmp_path, "Done.\n\nTICK PLAN-fx.md#0123abcd done commits=abc1234 landed=all owed=-\n"
    )
    assert out == ""
    rows = PB.pending_rows(proj, ME)
    assert [(r["sig"], r["commits"], r["agent"]) for r in rows] == [
        ("0123abcd", ["abc1234"], "a0000000000000aa")
    ]
    assert stop_log(proj)[-1]["ticks"] == 1


def test_control_subagent_stop_with_a_partial_tick_queues_nothing(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    subagent_stop(
        proj, tmp_path, "TICK PLAN-fx.md#0123abcd partial commits=- landed=C1 owed=C2:live\n"
    )
    assert PB.pending_rows(proj, ME) == []
    assert stop_log(proj)[-1]["ticks"] == 0


API_MSG = "API Error: No response from API (waited 3m, then 10m on the retry)."


def test_subagent_stop_on_an_api_error_blocks_twice_then_stands_down(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    for _ in range(RP.RESUME_SELF_MAX):
        out = subagent_stop(proj, tmp_path, API_MSG)
        decision = json.loads(out)
        assert decision == {"decision": "block", "reason": RP.RESUME_REASON}
    # The cap: the third API-error stop of the same agent is the lead's to see.
    assert subagent_stop(proj, tmp_path, API_MSG) == ""
    log = stop_log(proj)
    assert [r["resumed"] for r in log] == [True] * RP.RESUME_SELF_MAX + [False]
    assert all(r["api_error"] for r in log)


@pytest.mark.parametrize(
    ("message", "active"),
    [
        (API_MSG, True),
        ("The run hit one API Error: and recovered; report follows.", False),
        ("All done, commits abc1234.", False),
    ],
)
def test_control_no_block_when_active_or_not_an_api_error_stop(tmp_path, message, active):
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    assert subagent_stop(proj, tmp_path, message, active=active) == ""
    assert stop_log(proj)[-1]["resumed"] is False


# ---- --apply-ticks end to end ------------------------------------------------------------


def seed_wl(wl):
    wl.reg_repo()
    plan = wl.proj / "agent" / "plans" / "PLAN-fx.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text(PLAN_TEXT, encoding="utf-8")
    (wl.proj / ".ci" / "config").mkdir(parents=True, exist_ok=True)
    (wl.proj / ".ci" / "config" / "plan-boxes.json").write_text(
        json.dumps({"plans": {}}), encoding="utf-8"
    )
    wl.git("add", "-A")
    wl.git("commit", "-qm", "chore: seed plan")
    return PR.open_boxes(plan.read_text(encoding="utf-8"))[0][3]


def test_apply_ticks_dry_run_then_write_ticks_the_box_and_retires_the_row(wl):
    sig = seed_wl(wl)
    PB.queue_ticks(
        wl.proj, ME, "a00000000000000b1", tick_rows(sig, "present", close="see base.txt:1"), "x"
    )
    dry = wl.cli("--apply-ticks", ME)
    assert dry.rc == 0, (dry.out, dry.err)
    assert "READY" in dry.out, dry.out
    assert "--plan-investigate" in dry.out, dry.out
    plan = wl.proj / "agent" / "plans" / "PLAN-fx.md"
    assert "- [ ] O1" in plan.read_text(encoding="utf-8"), "a dry run wrote the plan"
    got = wl.cli("--apply-ticks", ME, "--write")
    assert got.rc == 0, (got.out, got.err)
    assert "OK" in got.out, got.out
    assert "1 ticked" in got.out, got.out
    assert "- [x] O1" in plan.read_text(encoding="utf-8")
    assert PB.pending_rows(wl.proj, ME) == []
    again = wl.cli("--apply-ticks", ME, "--write")
    assert again.rc == 0, again.out
    assert "0 pending row(s)" in again.out, again.out


def test_control_apply_ticks_waits_on_an_unlanded_lease_commit_and_writes_nothing(wl):
    sig = seed_wl(wl)
    wl.git("switch", "-q", "-c", "lease")
    (wl.proj / "w.txt").write_text("w\n", encoding="utf-8")
    wl.git("add", "-A")
    wl.git("commit", "-qm", "feat: lease work")
    lease = wl.git("rev-parse", "HEAD").stdout.strip()
    wl.git("switch", "-q", "-")
    PB.queue_ticks(wl.proj, ME, "a00000000000000b2", tick_rows(sig, commits=lease[:10]), "x")
    got = wl.cli("--apply-ticks", ME, "--write")
    assert got.rc == 0, (got.out, got.err)
    assert "WAIT" in got.out, got.out
    assert "1 waiting" in got.out, got.out
    assert "- [ ] O1" in (wl.proj / "agent" / "plans" / "PLAN-fx.md").read_text(encoding="utf-8")
    assert len(PB.pending_rows(wl.proj, ME)) == 1


def test_apply_ticks_refused_row_is_kept_and_the_verb_exits_1(wl):
    sig = seed_wl(wl)
    # Nothing checkable in the close line and no commit: one pointer kind (plan:), which --plan-investigate refuses.
    PB.queue_ticks(wl.proj, ME, "a00000000000000b3", tick_rows(sig, "present"), "x")
    got = wl.cli("--apply-ticks", ME, "--write")
    assert got.rc == 1, (got.rc, got.out, got.err)
    assert "REFUSED" in got.out, got.out
    assert "--plan-investigate rc=2" in got.out, got.out
    assert len(PB.pending_rows(wl.proj, ME)) == 1


def test_apply_ticks_refuses_a_done_row_over_a_partial_investigation(wl):
    """#8ff75ae1: a writer's done tick does not override the lead's recorded partial verdict."""
    sig = seed_wl(wl)
    head = wl.git("rev-parse", "HEAD").stdout.strip()
    inv = wl.cli(
        "--plan-investigate",
        ME,
        "agent/plans/PLAN-fx.md",
        sig,
        "partial",
        "commit:" + head[:10],
        "fileline:base.txt:1",
        "--owed",
        "code",
        "--write",
        "--",
        "the timing clause of the accept is unmet on the landed tree, owed as code",
    )
    assert inv.rc == 0, (inv.out, inv.err)
    PB.queue_ticks(
        wl.proj, ME, "a00000000000000b4", tick_rows(sig, "done", close="see base.txt:1"), "x"
    )
    got = wl.cli("--apply-ticks", ME, "--write")
    assert got.rc == 1, (got.rc, got.out, got.err)
    assert "records partial, owed code" in got.out, got.out
    assert "- [ ] O1" in (wl.proj / "agent" / "plans" / "PLAN-fx.md").read_text(encoding="utf-8")
    assert len(PB.pending_rows(wl.proj, ME)) == 1


def test_apply_ticks_unknown_flag_is_refused(wl):
    got = wl.cli("--apply-ticks", ME, "--wrte")
    assert got.rc == 2, (got.rc, got.err)
    assert "unknown argument" in got.err, (got.rc, got.err)


# ---- refusals of the record verbs exit non-zero ------------------------------------------


def test_plan_tick_and_plan_investigate_refusals_exit_nonzero_and_a_dry_run_exits_0(wl):
    sig = seed_wl(wl)
    rel = "agent/plans/PLAN-fx.md"
    bad_inv = wl.cli(
        "--plan-investigate",
        ME,
        rel,
        sig,
        "present",
        "fileline:nope.txt:1",
        "plan:%s" % rel,
        "--",
        "a pointer that does not resolve here",
        "--write",
    )
    assert bad_inv.rc != 0, (bad_inv.rc, bad_inv.err)
    assert "Nothing was written" in bad_inv.err, (bad_inv.rc, bad_inv.err)
    bad_tick = wl.cli("--plan-tick", ME, rel, sig, "commit:deadbeef12 base.txt:1 rc=0", "--write")
    assert bad_tick.rc != 0, (bad_tick.rc, bad_tick.err)
    assert "Nothing was written" in bad_tick.err, (bad_tick.rc, bad_tick.err)
    # CONTROL: an accepted dry run exits 0.
    dry = wl.cli(
        "--plan-investigate",
        ME,
        rel,
        sig,
        "present",
        "fileline:base.txt:1",
        "plan:%s" % rel,
        "--",
        "the fixture tree holds the box at base.txt line 1",
    )
    assert dry.rc == 0, (dry.out, dry.err)


# ---- the Stop-side resume block ------------------------------------------------------------


def plant_agent(sub: pathlib.Path, aid: str, last: dict, parent: str = "") -> pathlib.Path:
    sub.mkdir(parents=True, exist_ok=True)
    meta = {"agentType": "general-purpose", "description": "fixture %s" % aid, "spawnDepth": 1}
    if parent:
        meta["parentAgentId"] = parent
    (sub / ("agent-%s.meta.json" % aid)).write_text(json.dumps(meta), encoding="utf-8")
    tx = sub / ("agent-%s.jsonl" % aid)
    recs = [{"type": "user", "message": {"content": "brief"}}, last]
    tx.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    return tx


def api_error_record(minutes_ago=5):
    return {
        "type": "assistant",
        "timestamp": stamp(minutes_ago),
        "isApiErrorMessage": True,
        "apiError": "no_response",
        "message": {"content": [{"type": "text", "text": API_MSG}]},
    }


def done_record():
    return {
        "type": "assistant",
        "timestamp": stamp(1),
        "message": {"stop_reason": "end_turn", "content": [{"type": "text", "text": "done"}]},
    }


def send_record(to, minutes_ago):
    return {
        "type": "assistant",
        "timestamp": stamp(minutes_ago),
        "message": {
            "content": [
                {"type": "tool_use", "name": "SendMessage", "input": {"to": to, "message": "go"}}
            ]
        },
    }


def metas_of(sub):
    return ROSTER.load_metas(sub)


def test_dead_agents_names_an_api_error_death_and_not_its_controls(tmp_path):
    sub = tmp_path / "subagents"
    plant_agent(sub, "adead00000000001", api_error_record())
    plant_agent(sub, "afine00000000002", done_record())
    plant_agent(sub, "anest00000000003", api_error_record(), parent="adead00000000001")
    parent = tmp_path / "lead.jsonl"
    parent.write_text("", encoding="utf-8")
    rows = RR.dead_agents(metas_of(sub), str(parent))
    assert [r["id"] for r in rows] == ["adead00000000001"]
    assert "SendMessage to=adead00000000001" in RR.render(rows)


def test_a_sendmessage_after_the_death_marks_it_resumed_and_one_before_does_not(tmp_path):
    sub = tmp_path / "subagents"
    plant_agent(sub, "adead00000000001", api_error_record(minutes_ago=5))
    parent = tmp_path / "lead.jsonl"
    parent.write_text(json.dumps(send_record("adead00000000001", 30)) + "\n", encoding="utf-8")
    assert [r["id"] for r in RR.dead_agents(metas_of(sub), str(parent))] == ["adead00000000001"]
    with parent.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(send_record("adead00000000001", 1)) + "\n")
    assert RR.dead_agents(metas_of(sub), str(parent)) == []


def test_a_failed_task_notification_alone_names_the_agent(tmp_path):
    note = (
        "<task-notification>\n<task-id>aghost0000000004</task-id>\n<status>failed</status>\n"
        '<summary>Agent "x" failed: Agent terminated early due to an API error: API Error: '
        "Connection lost</summary>\n</task-notification>"
    )
    parent = tmp_path / "lead.jsonl"
    parent.write_text(
        json.dumps({"type": "user", "timestamp": stamp(3), "message": {"content": note}}) + "\n",
        encoding="utf-8",
    )
    assert [r["id"] for r in RR.dead_agents({}, str(parent))] == ["aghost0000000004"]
    # CONTROL: the same notification with status completed names nobody.
    parent.write_text(
        json.dumps(
            {
                "type": "user",
                "timestamp": stamp(3),
                "message": {"content": note.replace(">failed<", ">completed<")},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert RR.dead_agents({}, str(parent)) == []


def fixture_subagents(wl):
    root = wl.base / "claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(wl.proj))
    wl.env["CLAUDE_CONFIG_DIR"] = str(wl.base / "claude")
    return root / wlfix.SID / "subagents"


def test_stop_hook_blocks_with_the_resume_line_until_the_sendmessage_is_seen(wl):
    plant_agent(fixture_subagents(wl), "adead00000000001", api_error_record())
    got = wl.run()
    assert "AGENT CUT BY AN API ERROR" in got.out, got.out[-3000:]
    assert "SendMessage to=adead00000000001" in got.out
    wl.append_transcript(send_record("adead00000000001", 0))
    again = wl.run()
    assert "AGENT CUT BY AN API ERROR" not in again.out, again.out[-3000:]


def test_control_stop_hook_says_nothing_for_an_agent_that_finished(wl):
    plant_agent(fixture_subagents(wl), "afine00000000002", done_record())
    got = wl.run()
    assert "AGENT CUT BY AN API ERROR" not in got.out, got.out[-3000:]


def test_tail_lines_of_an_unreadable_file_is_empty(tmp_path):
    """Review 95861937.2: `wl_core.tail_bytes` answers None for a path it cannot read, and `_tail_lines` turns that into no lines rather than an exception."""
    assert RR._tail_lines(tmp_path / "no-such-transcript.jsonl", 1024) == []


def test_tail_lines_drops_the_partial_first_line_when_the_tail_starts_mid_file(tmp_path):
    path = tmp_path / "t.jsonl"
    lines = ["alpha-record", "bravo-record", "charlie-record"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # 20 bytes from the end begins inside "bravo-record" ("charlie-record\n" is 15 bytes).
    assert RR._tail_lines(path, 20) == ["charlie-record"]


def test_control_tail_lines_keeps_the_first_line_when_the_tail_reaches_the_file_start(tmp_path):
    path = tmp_path / "t.jsonl"
    lines = ["alpha-record", "bravo-record", "charlie-record"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert RR._tail_lines(path, 1024 * 1024) == lines


class _SpawnSeenError(Exception):
    """Raised by the Popen spy once it holds the env the fork parent would start with."""


def _env_the_fork_parent_starts_with(monkeypatch) -> dict[str, str]:
    seen: dict[str, dict[str, str]] = {}

    def spy(*_args, **kwargs):
        seen["env"] = kwargs["env"]
        raise _SpawnSeenError

    monkeypatch.setattr(wlfix._ForkParent, "proc", None)
    monkeypatch.setattr(wlfix.subprocess, "Popen", spy)
    with pytest.raises(_SpawnSeenError):
        wlfix._ForkParent.run(["true"], "", {})
    return seen["env"]


def test_the_fork_parent_starts_with_the_import_time_environment_not_the_cases(
    monkeypatch, tmp_path
):
    """Review f0af10f3.1: a case that monkeypatches its fixture env into os.environ (TMPDIR among it) and is the first to call a hook must not hand that env to the parent, whose scratch dir would then live inside the case's directory."""
    monkeypatch.setenv("TMPDIR", str(tmp_path / "case-fixture-tmp"))
    monkeypatch.setenv("WLFIX_CASE_ONLY_PROBE", "1")
    env = _env_the_fork_parent_starts_with(monkeypatch)
    assert env.get("TMPDIR") != str(tmp_path / "case-fixture-tmp")
    assert "WLFIX_CASE_ONLY_PROBE" not in env


def test_control_the_fork_parent_environment_is_the_pytest_process_as_imported(monkeypatch):
    """The silent control: the parent still gets a real environment (PATH from the pytest process), so the plant above is not satisfied by an empty dict."""
    env = _env_the_fork_parent_starts_with(monkeypatch)
    assert env.get("PATH") == wlfix._PARENT_ENV.get("PATH")
    assert env.get("PATH")
