"""Background waiting: check-ins, impure waits, drained waiters, roster reaping, and the transcript join that finds the task store.

Ported from `.claude/hooks/stop/worklist-cases/14-background-waits.sh`, one pytest function per numbered bash case, and one more wherever a bash block called `setup` again mid-case.

EVERY FIRE CASE IS PAIRED WITH A SILENT CONTROL differing by one planted fact, and the waiter cases run a REAL `wl_wait.py` process rather than a fake command string: `confirmed` means the operating system can see a live descendant carrying the command, so a fixture that only claimed the command would prove the string match and not the verdict.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
import time

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

WAIT_PY = wlfix.STOP_DIR / "wl_wait.py"

BW1 = [{"id": "bw1", "type": "shell", "status": "running", "description": "long CI watch"}]

SAID_161 = "answer\n\n## Remaining\n- #7 operator-gated decision (pending)"
SAID_163 = "answer\n\n## Remaining\n- #7 waiting on the nightly (in_progress)"
SAID_163Y = "answer\n\n## Remaining\n- #7 fully planned and unblocked (pending)"
SAID_163Y_C = (
    "answer\n\n## Remaining\n- #6 the prerequisite (pending)\n- #7 parked behind 6 (pending)"
)
SAID_163X = "answer\n\n## Remaining\n- #21 the mismatch fixture task (pending)"
SAID_163X_C = "answer\n\n## Remaining\n(nothing tracked here)"
SAID_INBOX = "answer\n\n## Remaining\n- #7 waiting on the inbox (in_progress)"
SAID_MATES = "answer\n\n## Remaining\n- #7 waiting on the teammates (in_progress)"
DRAINED_MSG = (
    "all of it is finished and the tree is clean\n\n"
    "## Remaining\n- nothing open, nothing in flight, no pending task"
)
WORK_LOOP_CRONS = [{"id": "c1", "schedule": "*/30 * * * *", "prompt": "work loop"}]
WORK_LOOP_AND_POLL = [*WORK_LOOP_CRONS, {"id": "p", "schedule": "*/5 * * * *"}]


def assert_in(result, needle: str, label: str) -> None:
    """The bash `grep -qF <needle> <<<"$OUT"` arm of a case, with the output quoted back on failure."""
    assert needle in result.out, "%s (needle %r MISSING)\n  out: %s\n  err: %s" % (
        label,
        needle,
        result.out[:400],
        result.err[:300],
    )


def seed_bgwait(fix, at: str = "2026-01-01T00:00:00Z") -> None:
    """Backdate the wait clock so the 15-minute check-in is overdue.

    The first stop on a wait state SEEDS this mark silently: the check-in reports how long the wait has lasted, never that it has started. Asserting on a seeding stop is vacuous, so every fire case below drives one stop, backdates the mark here, and then drives the stop it actually asserts on.
    """
    path = fix.stem(".state-deadbeef.json")
    assert path.is_file(), "FIXTURE BROKEN: no state doc at %s to seed the wait clock into" % path
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["bgwait"] = {"at": at}
    path.write_text(json.dumps(doc), encoding="utf-8")


def bgout(fix) -> None:
    """Point the output-stream reader at a fixture directory and return it."""
    (fix.base / "bgout").mkdir(parents=True, exist_ok=True)
    fix.env["WORKLIST_BG_OUTPUT_DIR"] = str(fix.base / "bgout")


def stream(fix, task_id: str, text: str = "worker stream content\n") -> None:
    """One background task's output stream, which is the progress evidence no self-report can fake."""
    (fix.base / "bgout" / ("%s.output" % task_id)).write_text(text, encoding="utf-8")


def waiter_command() -> str:
    """The command string a declared inbox waiter carries.

    `sys.executable` rather than the bare `python3` the bash used: the verdict is a substring match against the child's real `/proc` cmdline, and the interpreter pytest runs under is the one the child will show.
    """
    return "%s %s deadbeef --timeout 3" % (sys.executable, WAIT_PY)


def waiter_row(task_id: str = "wt1", description: str = "inbox waiter") -> dict:
    return {
        "id": task_id,
        "type": "shell",
        "status": "running",
        "command": waiter_command(),
        "description": description,
    }


def waiter_verdict(task_id: str = "wt1") -> str:
    """The liveness verdict for a declared waiter, asserted rather than assumed.

    If the verdict is not `confirmed` the case built on it is vacuous and would pass for the wrong reason, which is why both 163z and 163q spend a premise assertion on it.
    """
    liveness = wlfix.import_wl("wl_liveness")
    bg = [{"id": task_id, "type": "shell", "status": "running", "command": waiter_command()}]
    return liveness.verify_background(bg, ancestors={os.getpid()}).get(task_id)


@contextlib.contextmanager
def live_waiter(fix, tmpdir_name: str = "waittmp"):
    """A REAL `wl_wait.py` child of this process, torn down however the test leaves.

    Its own TMPDIR and project dir, exactly as the bash launched it: the waiter writes a heartbeat beside the worklist it resolves, and pointing it at the fixture's own would plant the very artifact several of these cases assert about.
    """
    (fix.base / tmpdir_name).mkdir(parents=True, exist_ok=True)
    env = dict(fix.env)
    env["TMPDIR"] = str(fix.base / tmpdir_name)
    env["CLAUDE_PROJECT_DIR"] = str(fix.base)
    proc = subprocess.Popen(
        [sys.executable, str(WAIT_PY), "deadbeef", "--timeout", "3"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    fix.env["WORKLIST_HARNESS_PID"] = str(os.getpid())
    time.sleep(1)
    try:
        yield proc
    finally:
        proc.kill()
        proc.wait()


def nudge(fix) -> None:
    """One PostToolUse nudge through `wl_wait.py --nudge`, the path that decays the ignored count."""
    payload = json.dumps(
        {
            "session_id": fix.sid,
            "cwd": str(fix.proj),
            "transcript_path": str(fix.transcript),
            "tool_name": "Bash",
        }
    )
    env = dict(fix.env)
    env["TMPDIR"] = str(fix.base / "tmp")
    env["CLAUDE_PROJECT_DIR"] = str(fix.proj)
    env["WORKLIST_TASKS_DIR"] = str(fix.base / "tasks")
    subprocess.run(
        [sys.executable, str(WAIT_PY), "--nudge"],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def backdate(path, minutes: float) -> None:
    old = time.time() - minutes * 60
    os.utime(path, (old, old))


def test_161_an_open_operator_request_suppresses_the_stuck_exempt_overrun(wl):  # noqa: F811
    """Terminal-hold shape: all work done, the one question posted to the operator with DEFAULT: hold, long-lived teammate tasks keeping live_bg nonempty.

    The ball is verifiably out of this session's court, so the overrun must not nag it into fake motion; the suppression lifts when the request resolves.
    """
    wl.brief_now()
    wl.hand_now()
    wl.env["WORKLIST_STUCK_ROUNDS"] = "1"
    wl.task(7, "pending", "operator-gated decision")
    wl.cli("--ask", "deadbeef", "operator", "merge the green PR? DEFAULT: hold and do not merge")
    wl.bg = json.dumps(
        [
            {
                "id": "tz1",
                "type": "teammate",
                "status": "running",
                "description": "long-lived teammate",
            }
        ]
    )
    fired = []
    for _ in range(6):
        wl.newturn()
        wl.say(SAID_161)
        got = wl.run()
        if "CONSECUTIVE STOPS" in got.out:
            fired.append(got.out[:250])
    assert not fired, "161: the hold state was nagged as stuck: %s" % fired[0]


def test_161_control_without_the_request_the_exempt_overrun_still_fires(wl):  # noqa: F811
    """CONTROL: the same shape WITHOUT the operator request still overruns.

    WORKLIST_STUCK_ROUNDS stays pinned here because the bash export outlived the `setup` that opened this half, and an unpinned one would make the control pass for want of rounds rather than for want of a request.
    """
    wl.brief_now()
    wl.hand_now()
    wl.env["WORKLIST_STUCK_ROUNDS"] = "1"
    wl.task(7, "pending", "operator-gated decision")
    wl.bg = json.dumps(
        [
            {
                "id": "tz1",
                "type": "teammate",
                "status": "running",
                "description": "long-lived teammate",
            }
        ]
    )
    fired = []
    last = ""
    for _ in range(6):
        wl.newturn()
        wl.say(SAID_161)
        got = wl.run()
        last = got.out
        if "CONSECUTIVE STOPS" in got.out:
            fired.append(got.out[:250])
    assert fired, "161 CONTROL: the overrun never fired: %s" % last[:250]


def test_163_a_pure_background_wait_gets_a_check_in_not_make_work(wl):  # noqa: F811
    """v15: live background jobs, no open items, no expired deferral.

    The hook recognizes the state as legitimate and demands only a bounded check-in whose worker facts it gathered itself from the output streams. v19: an UNBLOCKED pending task now (correctly) makes the wait impure, so this case's parked task is in_progress, the state a watched-by-this-session job actually has, and the unblocked-pending behavior gets case 163y.
    """
    wl.brief_now()
    wl.hand_now()
    bgout(wl)
    stream(wl, "bw1")
    wl.bg = json.dumps(BW1)
    wl.task(7, "in_progress", "waiting on the nightly")
    wl.say(SAID_163)
    seed = wl.run()
    wl.check_quiet("PURE BACKGROUND WAIT", "163 seed: first sight of the wait state", result=seed)

    seed_bgwait(wl)
    wl.newturn()
    wl.say(SAID_163)
    got = wl.run()
    label = "163: after 15 waited minutes the check-in fires with the hook's own stream facts"
    assert_in(got, "PURE BACKGROUND WAIT", label)
    assert_in(got, "bw1 (long CI watch)", label)
    assert_in(got, "output last grew", label)

    # CONTROL: inside the window it does not repeat (latched on fire).
    wl.newturn()
    wl.say(
        "bw1 confirmed: the long CI watch stream matches; nothing stuck.\n\n"
        "## Remaining\n- #7 waiting on the nightly (in_progress)"
    )
    wl.check_quiet(
        "PURE BACKGROUND WAIT", "163 CONTROL: no second check-in inside the 15-minute window"
    )


def test_163y_an_unblocked_pending_task_makes_the_wait_impure(wl):  # noqa: F811
    """Operator, 2026-08-08: a session idled for hours in "pure background wait" beside a fully planned, unblocked pending task; the check-in kept certifying the wait because it never consulted the harness queue.

    Now: pending with no unresolved blocker fires as WORKABLE-TASKS and names it, and pending behind a live blocker keeps the wait pure (the control below).
    """
    wl.brief_now()
    wl.hand_now()
    bgout(wl)
    stream(wl, "bw1")
    wl.bg = json.dumps(BW1)
    wl.task(7, "pending", "fully planned and unblocked")
    wl.say(SAID_163Y)
    wl.run()
    seed_bgwait(wl)
    wl.newturn()
    wl.say(SAID_163Y)
    got = wl.run()
    label = "163y: the check-in names the unblocked pending task instead of certifying the wait"
    assert_in(got, "WORKABLE TASKS", label)
    assert_in(got, "task #7 fully planned and unblocked", label)
    wl.check_quiet("not a demand for other work", label, result=got)


def test_163y_control_a_task_behind_a_live_blocker_keeps_the_wait_pure(wl):  # noqa: F811
    """CONTROL: the blocked task stays unnamed; its live blocker is the one named."""
    wl.brief_now()
    wl.hand_now()
    bgout(wl)
    stream(wl, "bw1")
    wl.bg = json.dumps(BW1)
    wl.task(6, "pending", "the prerequisite")
    wl.task(7, "pending", "parked behind 6", "6")
    wl.say(SAID_163Y_C)
    wl.run()
    seed_bgwait(wl)
    wl.newturn()
    wl.say(SAID_163Y_C)
    got = wl.run()
    label = "163y CONTROL: blocker logic"
    assert_in(got, "WORKABLE TASKS", label)
    assert_in(got, "task #6 the prerequisite", label)
    wl.check_quiet("task #7 parked behind 6", label, result=got)


def test_163x_the_transcript_join_finds_a_renamed_task_store(wl):  # noqa: F811
    """Review finding on #559: the fallback in _resolve_tasks_dir had no committed coverage (the original proof ran as ephemeral scratchpad python).

    This case drives it through the REAL hook: the primary session-deadbeef directory is EMPTY (the fixture creates it bare), the actual tasks live under a differently-named session-* directory, and the only join evidence is a TaskCreate result line in the transcript tail. The workable-tasks check-in naming the task proves the whole chain: resolve, then actionable, then fire.
    """
    wl.brief_now()
    wl.hand_now()
    bgout(wl)
    stream(wl, "bw1")
    wl.bg = json.dumps(BW1)
    other = wl.base / "tasks" / "session-teamzzzz"
    other.mkdir(parents=True, exist_ok=True)
    (other / "21.json").write_text(
        json.dumps(
            {
                "id": "21",
                "status": "pending",
                "subject": "the mismatch fixture task",
                "blockedBy": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    wl.say("Task #21 created successfully: the mismatch fixture task")
    wl.say(SAID_163X)
    wl.run()
    seed_bgwait(wl)
    wl.newturn()
    wl.say(SAID_163X)
    got = wl.run()
    label = "163x: the join resolved the renamed store off the transcript and named its task"
    assert_in(got, "WORKABLE TASKS", label)
    assert_in(got, "task #21 the mismatch fixture task", label)


def test_163x_control_two_candidate_directories_refuse_the_join(wl):  # noqa: F811
    """CONTROL: TWO directories matching the same TaskCreate line, so the join refuses, no task is named, and the wait stays pure.

    A fresh world, so the durable resolution cache from the fire case cannot leak in.
    """
    wl.brief_now()
    wl.hand_now()
    bgout(wl)
    stream(wl, "bw1")
    wl.bg = json.dumps(BW1)
    for name in ("teamzzzz", "teamyyyy"):
        folder = wl.base / "tasks" / ("session-%s" % name)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "21.json").write_text(
            json.dumps(
                {
                    "id": "21",
                    "status": "pending",
                    "subject": "the mismatch fixture task",
                    "blockedBy": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
    wl.say("Task #21 created successfully: the mismatch fixture task")
    wl.say(SAID_163X_C)
    wl.run()
    seed_bgwait(wl)
    wl.newturn()
    wl.say(SAID_163X_C)
    got = wl.run()
    label = "163x CONTROL: ambiguity did not refuse"
    assert_in(got, "PURE BACKGROUND WAIT", label)
    wl.check_quiet("task #21", label, result=got)


def test_163z_a_confirmed_waiter_owes_no_check_in_and_needs_no_poll_cron(wl):  # noqa: F811
    """v18: the waiter blocks until something new arrives for this session and then EXITS, and its exit is the harness notification that wakes the session.

    Its liveness IS its report, so the two supervision demands that exist to make a session account for a silent background job do not apply to it. Both relaxations are keyed on `confirmed` and on nothing weaker.
    """
    wl.brief_now()
    wl.hand_now()
    bgout(wl)
    with live_waiter(wl):
        verdict = waiter_verdict("wt1")
        assert verdict == "confirmed", (
            "163z premise: waiter verdict is %r, not confirmed, so this case is vacuous" % verdict
        )
        wl.bg = json.dumps([waiter_row("wt1")])
        wl.crons = json.dumps(WORK_LOOP_CRONS)
        wl.task(7, "in_progress", "waiting on the inbox")
        wl.say(SAID_INBOX)
        wl.run()
        seed_bgwait(wl)
        wl.newturn()
        wl.say(SAID_INBOX)
        got = wl.run()
        why = "163z: the check-in or the no-poll demand fired at a waiter: %r" % got.out[:250]
        assert "PURE BACKGROUND WAIT" not in got.out, (
            "163z: an overdue check-in must be SUPPRESSED when the only live task is a confirmed waiter. %s"
            % why
        )
        # The needle is lifted VERBATIM from V_NO_POLL_CRON. The first draft of this line grepped for "no inbox poll" and "poll cron", neither of which appears in that message at all, so the assertion was incapable of failing and passed for a reason unrelated to the waiter.
        assert "NOTHING LISTENING FOR CROSS-SESSION MAIL" not in got.out, (
            "163z: a work cron with NO poll cron is accepted beside a confirmed waiter. %s" % why
        )
        # `check_quiet` is deliberately NOT the instrument for those two, and this line is why: both relaxations landing means the stop says NOTHING at all, and a helper that refuses to pass on silence would report the passing state as the failure.
        # The silence is the stronger claim and the one that goes red when either relaxation is removed: case 163z-c1 in the waiter-controls module drives the same fixture with a DEAD waiter and gets the check-in back.
        assert not got.out.strip(), why


def drained_setup(fix) -> None:
    """The common 163q fixture: fresh world, queue drainable.

    The advice is a QUEUED REPORT rather than a violation, and OUTQ_PER_STOP is 1 by default, so without the wider drain the case would be measuring queue position rather than the check.
    """
    fix.brief_now()
    fix.hand_now()
    bgout(fix)
    fix.env["WORKLIST_REPORT_PER_STOP"] = "6"


def test_163q_a_drained_session_is_told_to_stop_its_waiter(wl):  # noqa: F811
    """THE OTHER HALF OF 163z and 163w. Those two force a session with work to LISTEN; nothing ever told a finished one to stop, so a drained session held a process for up to an hour and was nagged on every tool call to relaunch it.

    Observed live 2026-08-19: zero open items, zero background jobs, VMs torn down, and still "NOT LISTENING".
    """
    drained_setup(wl)
    with live_waiter(wl):
        verdict = waiter_verdict("wt9")
        assert verdict == "confirmed", (
            "163q premise: waiter verdict is %r, not confirmed, so this case is vacuous" % verdict
        )
        wl.bg = json.dumps([waiter_row("wt9")])
        wl.say(DRAINED_MSG)
        got = wl.run()
        assert_in(
            got,
            "DRAINED, AND STILL HOLDING A WAITER",
            "163q: a drained session is told to stop its waiter",
        )
        # The remedy must name the task's OWN id. One that does not is a remedy the reader has to guess at, and there is nothing on a Stop event to guess from.
        assert_in(got, "TaskStop wt9", "163q: it names the exact TaskStop command for that task id")
        # GUIDANCE, NEVER A BLOCK. A stop that blocked on this would keep the session alive to argue about the process it is being told to shut down.
        assert got.decision != "block", (
            "163q: a drained session was BLOCKED over its waiter: %s" % got.out[:300]
        )


def test_163q_c1_control_a_session_with_a_pending_task_keeps_its_waiter(wl):  # noqa: F811
    """CONTROL 1: WORK OUTSTANDING, same live waiter, so the advice must not fire.

    A pending harness task rather than an open item, deliberately: an open item BLOCKS, and an absence asserted on a blocking stop proves nothing, because the report queue is not drained on that path.
    """
    drained_setup(wl)
    with live_waiter(wl):
        wl.bg = json.dumps([waiter_row("wt9")])
        wl.task(9, "in_progress", "still doing the thing")
        wl.say("still working\n\n## Remaining\n- #9 still doing the thing (in_progress)")
        wl.check_quiet(
            "DRAINED, AND STILL HOLDING A WAITER",
            "163q-c1 CONTROL: told to stop listening while work was pending",
        )


def test_163q_c2_control_a_drained_session_with_no_waiter_is_told_nothing(wl):  # noqa: F811
    """CONTROL 2: drained, but holding NO waiter. There is nothing to stop, and an advisory that fired here would be telling every finished session in the repo to kill a process it does not have."""
    drained_setup(wl)
    wl.bg = "[]"
    wl.say(DRAINED_MSG)
    wl.check_quiet(
        "DRAINED, AND STILL HOLDING A WAITER",
        "163q-c2 CONTROL: advice fired with no waiter to stop",
    )


def test_163q_c3_control_a_waiter_beside_a_live_worker_is_kept(wl):  # noqa: F811
    """CONTROL 3: a waiter BESIDE another live background job.

    That job's report arrives through this very channel, so telling the session to stop listening would make it deaf to the worker it is supervising. This is what `_only_waiters` guards, and it is the assertion that goes red without it.
    """
    drained_setup(wl)
    with live_waiter(wl):
        wl.bg = json.dumps(
            [
                waiter_row("wt9"),
                {
                    "id": "job1",
                    "type": "teammate",
                    "status": "running",
                    "description": "a writer sub-agent still running",
                },
            ]
        )
        wl.say(
            "waiting on the worker\n\n## Remaining\n"
            "- job1 is still running; its report is what the session is waiting for"
        )
        wl.check_quiet(
            "DRAINED, AND STILL HOLDING A WAITER",
            "163q-c3 CONTROL: told to stop listening while a worker was running",
        )


def mk_mate(fix, session: str, name: str, age_min: float) -> None:
    """One teammate transcript in a fixture projects store, backdated by `age_min`.

    The directory is named for the SESSION ID, which is the real convention: a literal placeholder meant the scoped lookup could not resolve and the case was really exercising the unscoped glob.
    """
    root = fix.base / "claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(fix.proj))
    folder = root / session / "subagents"
    folder.mkdir(parents=True, exist_ok=True)
    aid = "a%s-1111222233334444" % name
    (folder / ("agent-%s.meta.json" % aid)).write_text(
        json.dumps({"agentType": name, "name": name, "taskKind": "in_process_teammate"}),
        encoding="utf-8",
    )
    transcript = folder / ("agent-%s.jsonl" % aid)
    transcript.write_text(
        json.dumps({"type": "assistant", "message": {"content": []}}) + "\n", encoding="utf-8"
    )
    backdate(transcript, age_min)


def test_163v_an_unverifiable_roster_is_reaped_but_only_where_certain(wl):  # noqa: F811
    """THE BUG: after a compaction, or an operator reopening the session, the harness still reports every teammate ever spawned as `running`. Measured live: 20 claimed, exactly 1 transcript still growing.

    That roster drives _in_pure_wait, the 15-minute check-in and confirmed_waiters, so a stale one means a session is told it supervises twenty workers forever and confirms phantoms every quarter hour. There is NO JOIN from a task id to an agent (a task carries only id, type, status and description, the description is the prompt truncated to about 50 characters, and that prefix is
    provably not unique: 10 of 19 collided on a live roster), so the automatic reap fires only where it is a CERTAINTY: not one teammate transcript fresh means every teammate task is dead, whatever its id.
    """
    wl.brief_now()
    wl.hand_now()
    # THIS session's own teammate, stale by hours: the roster is genuinely dead.
    mk_mate(wl, wlfix.SID, "oldmate", 600)
    # A DIFFERENT session in the same project, with a FRESH teammate. This is the cross-session contamination the review found: unscoped, this one transcript made fresh > 0 for EVERY session in the project, so a session whose own roster was 100% phantom was told it still had live workers and the auto-reap never fired. Concurrent sessions in one tree are routine here, so this was
    # the common case rather than an edge one.
    mk_mate(wl, "bystander-9999-8888-7777-666666666666", "freshmate", 0)
    wl.env["CLAUDE_CONFIG_DIR"] = str(wl.base / "claude")
    wl.bg = json.dumps(
        [
            {
                "id": "tm1",
                "type": "teammate",
                "status": "running",
                "description": "You are an Opus writer sub-agent in /home...",
            },
            {
                "id": "tm2",
                "type": "teammate",
                "status": "running",
                "description": "You are an Opus writer sub-agent in /home...",
            },
        ]
    )
    wl.task(7, "in_progress", "waiting on the teammates")
    wl.say(SAID_MATES)
    wl.run()
    # THE CLOCK MUST BE OVERDUE BEFORE THIS PROVES ANYTHING. The check-in does not fire on first sight of the wait state whether or not the roster was pruned, so the assertion passed with the pruning removed entirely (mutation Mk). With the clock overdue the two cases diverge: pruned means the roster is empty, so it is not a pure wait and nothing is owed; unpruned means the
    # check-in fires for two phantoms.
    seed_bgwait(wl)
    wl.newturn()
    wl.say(SAID_MATES)
    dropped = wl.run()
    why = "163v: still supervising phantoms: %r" % dropped.out[:250]
    assert "PURE BACKGROUND WAIT" not in dropped.out, (
        "163v: with zero fresh transcripts the phantom roster is dropped. %s" % why
    )
    # A dropped roster leaves nothing to supervise, so the stop says nothing at all, which is why `check_quiet` (which refuses to pass on silence) is not the instrument. The silence is the stronger claim, and the CONTROL below is what makes it mean something: one fresh transcript and the SAME fixture gets the check-in back.
    assert not dropped.out.strip(), why

    # CONTROL: make one transcript FRESH and the same roster is kept, so the drop is the certainty branch rather than a blanket "teammates never count". THIS SESSION'S OWN transcript, not whichever the glob happens to return first: with a bystander session in the fixture, the other session's file is already fresh, which would leave this session's mate stale and make the control
    # silently assert the opposite of what it means.
    own = wl.base / "claude" / "projects"
    hits = sorted(own.glob("*/%s/subagents/*.jsonl" % wlfix.SID))
    assert hits, "control fixture missing: no transcript for this session"
    now = time.time()
    os.utime(hits[0], (now, now))
    seed_bgwait(wl)
    wl.newturn()
    wl.say(SAID_MATES)
    got = wl.run()
    assert_in(
        got,
        "PURE BACKGROUND WAIT",
        "163v CONTROL: one fresh transcript keeps the roster and the check-in",
    )
    # ...and because 2 are claimed while only 1 is fresh, the overclaim is REPORTED rather than guessed at.
    assert_in(
        got, "ROSTER OVERCLAIMS", "163v: the unresolvable remainder is surfaced, not silently kept"
    )


def test_163v_c1_reap_retires_an_id_and_refuses_one_the_hook_never_saw(wl):  # noqa: F811
    """`--reap` records a task id the roster claims but the session knows is gone, and refuses an id the hook has never been handed."""
    wl.brief_now()
    wl.hand_now()
    wl.bg = json.dumps(
        [{"id": "tm1", "type": "teammate", "status": "running", "description": "a teammate"}]
    )
    wl.task(7, "pending", "waiting")
    wl.say("answer\n\n## Remaining\n- #7 waiting (pending)")
    wl.run()  # banks the lastevent the CLI validates against

    refused = wl.cli("--reap", "deadbeef", "nosuchid")
    assert refused.rc != 0, "163v-c1: an unknown task id was accepted"
    assert "not in the last background-task list" in refused.err, (
        "163v-c1: refusal was unclear: %s" % (refused.err + refused.out)[:120]
    )
    assert not wl.stem(".reaped-deadbeef").exists(), "163v-c1: a rejected reap still recorded an id"

    # CONTROL: a REAL id from that same roster is accepted and takes effect.
    accepted = wl.cli("--reap", "deadbeef", "tm1")
    assert "reaped 1 task" in accepted.out + accepted.err, (
        "163v-c1 CONTROL: a valid reap was refused: %s" % (accepted.out + accepted.err)[:150]
    )

    # THE BASH ASSERTION HERE COULD NOT FAIL, and it is ported as what it meant. The bash drove one more stop and asserted the ABSENCE of "PURE BACKGROUND WAIT": that stop was inside the 15-minute window (the stop above seeded the clock), so the check-in could not have fired whether or not the reap took effect, and with task 7 pending and UNBLOCKED the overdue message would be
    # "WORKABLE TASKS" rather than the needle it grepped for. Seeding the clock overdue and refusing BOTH check-in needles is the assertion the case is about: unreaped, tm1 keeps the session in a wait state and the workable-task check-in fires.
    seed_bgwait(wl)
    wl.newturn()
    wl.say("answer\n\n## Remaining\n- #7 waiting (pending)")
    got = wl.run()
    why = "163v-c1: the reap had no effect: %r" % got.out[:250]
    assert "PURE BACKGROUND WAIT" not in got.out, why
    assert "WORKABLE TASKS" not in got.out, (
        "163v-c1: the reaped task no longer counts as running. %s" % why
    )
    # Measured rather than assumed, because it is what makes the two absences above non-vacuous: with the `--reap tm1` line removed, this same stop BLOCKS with "BACKGROUND WAIT WITH WORKABLE TASKS". With it, there is no live job left, so the stop says nothing.
    assert not got.out.strip(), why


def nudge_file(fix):
    return fix.stem(".waiternudge-deadbeef")


def waiter_file(fix):
    return fix.stem(".waiter-deadbeef")


def test_163w_a_session_that_ignores_the_waiter_nudges_is_blocked(wl):  # noqa: F811
    """v18. The operator asked to "force contexts to run in background". The trigger is deliberately NOT "no confirmed waiter right now": a waiter EXITS every time it fires, so that condition is true in exactly the window the session is supposed to be in, and keying on it blocked correct behaviour and broke 16 cases here.

    It keys on the count of PostToolUse nudges the session has been given and not acted on, which only grows over half an hour of being asked.
    """
    wl.brief_now()
    wl.hand_now()
    wl.brief_other("peer1234")
    wl.crons = json.dumps(WORK_LOOP_AND_POLL)
    wl.say("answer")
    # Below the grace threshold: asked twice, not yet blocked.
    nudge_file(wl).write_text("2 2026-01-01T00:00:00Z\n", encoding="utf-8")
    wl.check_quiet(
        "AND IS NOT LISTENING", "163w: under the grace count the session is not blocked yet"
    )
    # At the threshold: three unheeded nudges is half an hour of being asked.
    nudge_file(wl).write_text("3 2026-01-01T00:00:00Z\n", encoding="utf-8")
    got = wl.run()
    label = "163w: three ignored nudges blocks, and the block carries the command"
    assert_in(got, "AND IS NOT LISTENING", label)
    assert_in(got, "wl_wait.py", label)


def test_163w_c1_control_a_confirmed_waiter_silences_it(wl):  # noqa: F811
    """CONTROL: same ignored count, same peer, same loop, and only a live waiter differs."""
    wl.brief_now()
    wl.hand_now()
    wl.brief_other("peer1234")
    bgout(wl)
    with live_waiter(wl, "wt1"):
        wl.bg = json.dumps([waiter_row("wt1")])
        wl.crons = json.dumps(WORK_LOOP_AND_POLL)
        nudge_file(wl).write_text("9 2026-01-01T00:00:00Z\n", encoding="utf-8")
        wl.say("answer")
        wl.check_quiet(
            "AND IS NOT LISTENING",
            "163w-c1 CONTROL: blocked despite a live waiter at nine ignored nudges",
        )


def test_163w_c2_control_an_unverifiable_waiter_does_not_satisfy_it(wl):  # noqa: F811
    """CONTROL: the case that could silently pass for the wrong reason.

    Same command string, dead process, so the verdict is `suspect` rather than `confirmed`. A waiter nobody can see on the operating system is worth nothing: the whole argument is that its EXIT does the waking.
    """
    wl.brief_now()
    wl.hand_now()
    wl.brief_other("peer1234")
    bgout(wl)
    wl.env["WORKLIST_HARNESS_PID"] = str(os.getpid())
    wl.bg = json.dumps([waiter_row("wt1", "inbox waiter (dead)")])
    wl.crons = json.dumps(WORK_LOOP_AND_POLL)
    nudge_file(wl).write_text("3 2026-01-01T00:00:00Z\n", encoding="utf-8")
    wl.say("answer")
    got = wl.run()
    assert_in(
        got, "AND IS NOT LISTENING", "163w-c2 CONTROL: an unseeable waiter satisfied the check"
    )


def test_163w_c3_control_no_live_peer_no_block(wl):  # noqa: F811
    """CONTROL: the harm of not listening is TO SOMEBODY. With no peer there is nobody whose request could go unseen, so the check has no victim and must stay silent, which is the condition that makes blocking safe at all."""
    wl.brief_now()
    wl.hand_now()
    wl.crons = json.dumps(WORK_LOOP_AND_POLL)
    nudge_file(wl).write_text("9 2026-01-01T00:00:00Z\n", encoding="utf-8")
    wl.say("answer")
    wl.check_quiet("AND IS NOT LISTENING", "163w-c3 CONTROL: blocked with nobody to hear from")


def test_163w_c4_the_tombstone_a_lapsed_waiter_blocks_with_zero_ignored_nudges(wl):  # noqa: F811
    """THE PERVERSE INCENTIVE THIS CLOSES. wait() used to unlink the heartbeat on BOTH of its exits, so a waiter that had died left exactly what a session that never listened leaves: nothing.

    Combined with nudge()'s counter RESET, arming a single 60-minute waiter therefore bought 30+ minutes of guaranteed silence after it lapsed, the cheapest way to be left alone being to arm one waiter every few hours and never relaunch it. Zero nudges here, deliberately: the ignored-count grace is for a session that merely COULD receive work, while a session whose waiter exited
    already volunteered, was told on the way out to relaunch, and did not.
    """
    wl.brief_now()
    wl.hand_now()
    wl.brief_other("peer1234")
    wl.crons = json.dumps(WORK_LOOP_AND_POLL)
    nudge_file(wl).unlink(missing_ok=True)
    waiter_file(wl).write_text("EXPIRED 2026-01-01T00:00:00Z timeout\n", encoding="utf-8")
    # Aged past HEARTBEAT_STALE_S so the marker is a lapse rather than a waiter that exited seconds ago and is about to be relaunched in the same turn.
    backdate(waiter_file(wl), 10)
    wl.say("answer")
    got = wl.run()
    label = "163w-c4: a lapsed waiter blocks at once, and the block names WHICH exit it was"
    assert_in(got, "YOUR WAITER LAPSED", label)
    assert_in(got, "timeout", label)


def test_163w_c5_control_never_armed_and_zero_nudges_is_silent(wl):  # noqa: F811
    """CONTROL: the whole point of the tombstone is that these two states are different. If this fires too, the change has bought nothing and has just made the hook harsher at everybody."""
    wl.brief_now()
    wl.hand_now()
    wl.brief_other("peer1234")
    wl.crons = json.dumps(WORK_LOOP_AND_POLL)
    nudge_file(wl).unlink(missing_ok=True)
    waiter_file(wl).unlink(missing_ok=True)
    wl.say("answer")
    wl.check_quiet(
        "YOUR WAITER LAPSED",
        "163w-c5 CONTROL: never-armed and lapsed are still indistinguishable",
    )


def test_163w_c6_control_a_live_heartbeat_is_not_a_tombstone(wl):  # noqa: F811
    """CONTROL: _is_tombstone reads the CONTENT, because a tombstone is a WRITE and therefore looks `fresh` for its first HEARTBEAT_STALE_S seconds. A live pulse must never be mistaken for one."""
    wl.brief_now()
    wl.hand_now()
    wl.brief_other("peer1234")
    wl.crons = json.dumps(WORK_LOOP_AND_POLL)
    nudge_file(wl).unlink(missing_ok=True)
    waiter_file(wl).write_text("2026-08-28T10:00:00Z\n", encoding="utf-8")
    backdate(waiter_file(wl), 10)
    wl.say("answer")
    wl.check_quiet(
        "YOUR WAITER LAPSED",
        "163w-c6 CONTROL: an ordinary heartbeat was read as a tombstone",
    )


def compliant_window(fix) -> None:
    """One window in which the session complied: the nudge throttle is backdated, a fresh heartbeat is planted, and one nudge runs."""
    if nudge_file(fix).exists():
        # Backdated past NUDGE_EVERY_S, or the throttle returns before the decay.
        backdate(nudge_file(fix), 30)
    waiter_file(fix).write_text("2026-08-28T10:00:00Z\n", encoding="utf-8")
    nudge(fix)


def test_163w_c7_the_nudge_decays_by_one_it_does_not_reset_to_zero(wl):  # noqa: F811
    """The counter used to be UNLINKED the moment a heartbeat looked fresh, which made it resettable BY THE FAILURE: arming one waiter zeroed it, so when that waiter lapsed the Stop-side backstop had to climb from zero over another half hour of nudges.

    Decay keeps it a measure of recent behaviour without letting one act of compliance erase a history of ignoring it.
    """
    nudge_file(wl).write_text("3 2026-01-01T00:00:00Z\n", encoding="utf-8")
    compliant_window(wl)
    count = (
        nudge_file(wl).read_text(encoding="utf-8").split(" ")[0]
        if nudge_file(wl).exists()
        else "GONE"
    )
    assert count == "2", "163w-c7: the counter went to %r instead of 2" % count


def test_163w_c8_control_complying_repeatedly_still_walks_it_all_the_way_down(wl):  # noqa: F811
    """CONTROL: decay must not become a counter with no way back to zero.

    A session doing the right thing for long enough gets back to zero, which is what the reset was rightly for. The bash chained this onto case 163w-c7's world; here the first window is replayed so the case owns its own precondition, and the two further windows are the ones it asserts about.
    """
    nudge_file(wl).write_text("3 2026-01-01T00:00:00Z\n", encoding="utf-8")
    compliant_window(wl)
    for _ in range(2):
        compliant_window(wl)
    assert not nudge_file(wl).exists(), (
        "163w-c8 CONTROL: the counter is stuck at %s"
        % nudge_file(wl).read_text(encoding="utf-8")[:40]
    )


def test_163w_c9_the_ci_waiting_force_must_not_claim_a_reason_the_item_denies():
    """THE FAILURE, 2026-09-04. When the only in-flight work is a CI watch, the force tells a session to execute an aged deferral's DEFAULT "because the wait was the only reason to hold it".

    For a JUSTIFIED deferral that is backwards: a justified one is precisely the one whose reason is written down, and the reason is usually not the run. An item deferred with "what blocks it is not the wait, it is that the remaining act is irreversible and outward-facing" was told to execute its DEFAULT four stops running, and each time the session declined and re-justified, a
    round trip spent arguing with a template. The classifier is asserted directly rather than through a rendered stop, because what is being pinned is the READING of a WHY, and a full-stop fixture would prove it only for whatever phrasing that fixture happened to use.
    """
    checks = wlfix.import_wl("wl_checks")
    cases = [
        (
            "what blocks it is not the wait, it is that the remaining act is irreversible",
            False,
            "a WHY that DENIES the wait",
        ),
        (
            "this deferral is NOT waiting on a CI run -- the mechanical half is finished",
            False,
            "the exact phrasing the failure used",
        ),
        (
            "the packaging is yours because the sweep touches 17 files at once",
            False,
            "a WHY that never mentions a run",
        ),
        ("blocked until the CI run on this head reports", True, "a WHY that really is the wait"),
        (
            "waiting for the pipeline to go green before landing it",
            True,
            "another wait-shaped WHY",
        ),
        ("", False, "an empty WHY falls to the safe side, which asks rather than orders"),
    ]
    bad = []
    for why, want, label in cases:
        rec = {"just": {"why": why, "how": "h"}, "text": "q DEFAULT: d WHY: %s HOW: h" % why}
        if checks.deferral_waits_on_ci(rec) != want:
            bad.append(label)
    assert not bad, "163w-c9: misread WHY(s): %s" % bad
