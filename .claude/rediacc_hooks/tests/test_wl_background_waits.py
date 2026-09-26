"""Background waiting: check-ins, impure waits, roster reaping, and the transcript join that finds the task store.

Ported from `.claude/hooks/stop/worklist-cases/14-background-waits.sh`, one pytest function per numbered bash case, and one more wherever a bash block called `setup` again mid-case.

EVERY FIRE CASE IS PAIRED WITH A SILENT CONTROL differing by one planted fact. The inbox-waiter cases (163r, 161, 163z, 163q, 163w, 13f) were removed with cross-session messaging on 2026-09-24. `confirmed` means the operating system can see a live descendant carrying the command, so a fixture that only claimed the command would prove the string match and not the verdict.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

BW1 = [{"id": "bw1", "type": "shell", "status": "running", "description": "long CI watch"}]

SAID_163 = "answer\n\n## Remaining\n- #7 waiting on the nightly (in_progress)"
SAID_163Y = "answer\n\n## Remaining\n- #7 fully planned and unblocked (pending)"
SAID_163Y_C = (
    "answer\n\n## Remaining\n- #6 the prerequisite (pending)\n- #7 parked behind 6 (pending)"
)
SAID_163X = "answer\n\n## Remaining\n- #21 the mismatch fixture task (pending)"
SAID_163X_C = "answer\n\n## Remaining\n(nothing tracked here)"
SAID_MATES = "answer\n\n## Remaining\n- #7 waiting on the teammates (in_progress)"


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


def backdate(path, minutes: float) -> None:
    old = time.time() - minutes * 60
    os.utime(path, (old, old))


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
    # First sight SEEDS the clock silently. Since the poll-backoff advisory went (2026-09-24) this stop is a clean allow with ZERO bytes, so check_quiet's non-empty guard does not apply; the fire below, on the same fixture, is what proves the needle can appear at all.
    assert seed.rc == 0, "163 seed: rc=%d err=%s" % (seed.rc, seed.err[:200])
    assert "PURE BACKGROUND WAIT" not in seed.out, "163 seed: first sight of the wait state fired"

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
    # A latched stop may now be a zero-byte allow (the poll-backoff advisory that used to fill it is gone), so the anti-vacuity guard of check_quiet does not apply; the fire above on this same fixture proves the needle can appear.
    again = wl.run()
    assert again.rc == 0, "163 CONTROL: rc=%d err=%s" % (again.rc, again.err[:200])
    assert "PURE BACKGROUND WAIT" not in again.out, (
        "163 CONTROL: a second check-in fired inside the 15-minute window: %s" % again.out[:300]
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

    That roster drives _in_pure_wait and the 15-minute check-in, so a stale one means a session is told it supervises twenty workers forever and confirms phantoms every quarter hour. There is NO JOIN from a task id to an agent (a task carries only id, type, status and description, the description is the prompt truncated to about 50 characters, and that prefix is
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


# ---- plan stop-hook-overhaul 1.3: every live wait with an automatic liveness answer stands the check-in down ----

MATE_ROSTER = [
    {"id": "tm1", "type": "teammate", "status": "running", "description": "writer one"},
    {"id": "tm2", "type": "teammate", "status": "running", "description": "writer two"},
]
MARK = "<- POSSIBLY STUCK"


def overdue_stop(fix, said: str = SAID_MATES):
    """Seed the wait clock, backdate it past the 15-minute window, and return the stop that is due.

    The first stop only SEEDS the clock, so asserting silence on it is vacuous; every 1.3 case asserts on the second.
    """
    fix.task(7, "in_progress", "waiting on the workers")
    fix.say(said)
    fix.run()
    seed_bgwait(fix)
    fix.newturn()
    fix.say(said)
    return fix.run()


def mate_world(fix, ages) -> None:
    """A two-teammate roster with NO `.output` streams, one transcript per age in minutes, all in THIS session."""
    fix.brief_now()
    fix.hand_now()
    bgout(fix)
    for n, age in enumerate(ages):
        mk_mate(fix, wlfix.SID, "mate%d" % n, age)
    fix.env["CLAUDE_CONFIG_DIR"] = str(fix.base / "claude")
    fix.bg = json.dumps(MATE_ROSTER)


def test_13a_a_fully_fresh_teammate_roster_owes_no_check_in(wl):  # noqa: F811
    """1.3: stream-less teammates whose transcripts are all still growing have an automatic liveness answer, so the overdue check-in stands down.

    Goes red under the old predicate, which fired for any roster that was not wholly confirmed inbox waiters. Case 13b is the paired control: one transcript aged past TEAMMATE_FRESH_MIN and the same fixture fires.
    """
    mate_world(wl, [0, 0])
    got = overdue_stop(wl)
    assert "PURE BACKGROUND WAIT" not in got.out, (
        "13a: a roster its fresh transcripts fully cover still got the check-in: %r" % got.out[:400]
    )


def test_13b_control_one_teammate_aged_past_the_fresh_window_fires_and_is_marked(wl):  # noqa: F811
    """CONTROL for 13a: one transcript aged past TEAMMATE_FRESH_MIN (15) leaves 1 fresh for 2 claimed, so the roster is NOT covered.

    Aging EVERY transcript is not the control: `prune_background` reaps a wholly-stale roster (case 163v), leaving nothing to supervise. The per-row marker is the needle, not a bare "POSSIBLY STUCK": V_BG_REPORT's fixed text names that phrase on every check-in.
    """
    mate_world(wl, [0, 20])
    got = overdue_stop(wl)
    label = "13b CONTROL: a partly-stale teammate roster must still get the check-in"
    assert_in(got, "PURE BACKGROUND WAIT", label)
    assert_in(got, MARK + ": 1 of 2 teammate transcript(s) fresh", label)


def test_13c_control_an_unreadable_transcript_store_fires(wl):  # noqa: F811
    """CONTROL: no projects store at all is "cannot tell", never "all alive", so the check-in fires and says so."""
    wl.brief_now()
    wl.hand_now()
    bgout(wl)
    (wl.base / "emptyclaude").mkdir(parents=True, exist_ok=True)
    wl.env["CLAUDE_CONFIG_DIR"] = str(wl.base / "emptyclaude")
    wl.bg = json.dumps(MATE_ROSTER)
    got = overdue_stop(wl)
    label = "13c CONTROL: an unverifiable roster must get the check-in"
    assert_in(got, "PURE BACKGROUND WAIT", label)
    assert_in(got, MARK + ": unknown of 2 teammate transcript(s) fresh", label)


SLEEP_ARG = "3727272727"


def sleeper_row() -> dict:
    return {
        "id": "sj1",
        "type": "shell",
        "status": "running",
        "description": "long build",
        "command": "sleep %s" % SLEEP_ARG,
    }


def test_13d_an_os_confirmed_ordinary_shell_job_owes_no_check_in(wl):  # noqa: F811
    """1.3: the widening is not waiter-specific. Any shell job the OS CONFIRMS is alive exits into a harness notification, so its liveness is already answered."""
    wl.brief_now()
    wl.hand_now()
    bgout(wl)
    stream(wl, "sj1")
    proc = subprocess.Popen(
        ["sleep", SLEEP_ARG], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    wl.env["WORKLIST_HARNESS_PID"] = str(os.getpid())
    try:
        liveness = wlfix.import_wl("wl_liveness")
        verdict = liveness.verify_background([sleeper_row()], ancestors={os.getpid()}).get("sj1")
        assert verdict == "confirmed", "13d premise: verdict %r, so the case is vacuous" % verdict
        wl.bg = json.dumps([sleeper_row()])
        got = overdue_stop(wl, SAID_163)
        assert "PURE BACKGROUND WAIT" not in got.out, (
            "13d: a confirmed shell job still got the check-in: %r" % got.out[:400]
        )
    finally:
        proc.kill()
        proc.wait()


def test_13e_control_the_same_shell_job_dead_fires(wl):  # noqa: F811
    """CONTROL for 13d: the same declared command with NO process behind it is `suspect`, which answers nothing."""
    wl.brief_now()
    wl.hand_now()
    bgout(wl)
    stream(wl, "sj1")
    wl.env["WORKLIST_HARNESS_PID"] = str(os.getpid())
    wl.bg = json.dumps([sleeper_row()])
    got = overdue_stop(wl, SAID_163)
    assert_in(got, "PURE BACKGROUND WAIT", "13e CONTROL: a dead shell job must get the check-in")


SUBAGENT_ROSTER = [
    {
        "id": "a1111222233334444",
        "type": "subagent",
        "status": "running",
        "description": "writer one",
        "agent_type": "general-purpose",
    },
    {
        "id": "a5555666677778888",
        "type": "subagent",
        "status": "running",
        "description": "writer two",
        "agent_type": "Plan",
    },
]


def subagent_world(fix, ages, linked=None) -> None:
    """A `type: "subagent"` roster in today's harness shape, one transcript per age in minutes.

    The meta carries NO `taskKind` (0 of 306 live metas did, 2026-09-24), so `live_teammate_transcripts` never counts these. The harness's `tasks/<id>.output` is a SYMLINK to `subagents/agent-<id>.jsonl`, which is the id-to-transcript join the predicate rides; `linked` names which rows get one.
    """
    fix.brief_now()
    fix.hand_now()
    bgout(fix)
    root = fix.base / "claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(fix.proj))
    folder = root / wlfix.SID / "subagents"
    folder.mkdir(parents=True, exist_ok=True)
    for row, age in zip(SUBAGENT_ROSTER, ages, strict=True):
        tid = row["id"]
        (folder / ("agent-%s.meta.json" % tid)).write_text(
            json.dumps(
                {
                    "agentType": row["agent_type"],
                    "description": row["description"],
                    "spawnDepth": 1,
                    "requestShape": "background",
                    "model": "opus",
                }
            ),
            encoding="utf-8",
        )
        transcript = folder / ("agent-%s.jsonl" % tid)
        transcript.write_text(json.dumps({"type": "assistant"}) + "\n", encoding="utf-8")
        backdate(transcript, age)
        if linked is None or tid in linked:
            (fix.base / "bgout" / ("%s.output" % tid)).symlink_to(transcript)
    fix.env["CLAUDE_CONFIG_DIR"] = str(fix.base / "claude")
    fix.bg = json.dumps(SUBAGENT_ROSTER)


def test_13g_a_subagent_roster_with_fresh_joined_transcripts_owes_no_check_in(wl):  # noqa: F811
    """1.3, in the shape today's Stop event actually carries: `type: "subagent"` rows, no taskKind. Each id joins to its own transcript through the `.output` symlink, so a fresh stream is an automatic liveness answer."""
    subagent_world(wl, [0, 1])
    got = overdue_stop(wl)
    assert "PURE BACKGROUND WAIT" not in got.out, (
        "13g: a fully-fresh subagent roster still got the check-in: %r" % got.out[:400]
    )


def test_13h_control_one_subagent_transcript_stale_fires(wl):  # noqa: F811
    """CONTROL for 13g: one transcript quiet past BG_STALE_MIN (15) and the SAME roster fires, with that row accused."""
    subagent_world(wl, [0, 20])
    got = overdue_stop(wl)
    label = "13h CONTROL: a stale subagent transcript must get the check-in"
    assert_in(got, "PURE BACKGROUND WAIT", label)
    assert_in(got, "a5555666677778888 (writer two): output last grew 20m ago", label)
    assert_in(got, "<- POSSIBLY STUCK, investigate or restart", label)


def test_13i_control_a_subagent_with_no_stream_fires(wl):  # noqa: F811
    """CONTROL for 13g: a subagent whose `.output` join is missing is unverifiable, never live."""
    subagent_world(wl, [0, 0], linked={"a1111222233334444"})
    got = overdue_stop(wl)
    label = "13i CONTROL: a subagent with no stream must get the check-in"
    assert_in(got, "PURE BACKGROUND WAIT", label)
    assert_in(got, MARK + ": no transcript stream for this subagent", label)
