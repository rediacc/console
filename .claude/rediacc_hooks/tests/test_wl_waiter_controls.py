"""The phantom-stop guard, unread sub-agent reports, waiter-confirmation controls, and stuck output-stream detection.

Ported from `.claude/hooks/stop/worklist-cases/15-waiter-controls.sh`, one pytest function per numbered bash case, and one more wherever a bash block called `setup` again mid-case.

THE WAITER CONTROLS ARE THE HALF THAT KEEPS CASE 163z HONEST. That case relaxes two supervision demands for a CONFIRMED inbox waiter, and the relaxations are worth nothing unless a dead waiter and a real job running beside a live one both fail to buy them, which is what 163z-c1 and 163z-c2 plant.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

WAIT_PY = wlfix.STOP_DIR / "wl_wait.py"

SAID_INBOX = "answer\n\n## Remaining\n- #7 waiting on the inbox (in_progress)"
SAID_BOTH = "answer\n\n## Remaining\n- #7 waiting on both (in_progress)"
SAID_THING = "answer\n\n## Remaining\n- #7 thing (pending)"
SAID_DONE = "all done, nothing outstanding"
WORK_LOOP_CRONS = [{"id": "c1", "schedule": "*/30 * * * *", "prompt": "work loop"}]


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

    The first stop on a wait state SEEDS this mark silently, so asserting on a seeding stop proves nothing: every case below drives one stop, backdates the mark here, and then drives the stop it asserts on.
    """
    path = fix.stem(".state-deadbeef.json")
    assert path.is_file(), "FIXTURE BROKEN: no state doc at %s to seed the wait clock into" % path
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["bgwait"] = {"at": at}
    path.write_text(json.dumps(doc), encoding="utf-8")


def bgout(fix) -> None:
    """Point the output-stream reader at a fixture directory."""
    (fix.base / "bgout").mkdir(parents=True, exist_ok=True)
    fix.env["WORKLIST_BG_OUTPUT_DIR"] = str(fix.base / "bgout")


def waiter_command() -> str:
    """The command string a declared inbox waiter carries.

    LOCAL to this module although the background-waits module has the same helper: the bash set WAITER_CMD once in `14-background-waits.sh` and the cases here read it across a file boundary, which is the coupling a per-module copy removes. `sys.executable` rather than the bare `python3` the bash used, because the verdict is a substring match against the child's real cmdline.
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


def spawn(fix, argv: list[str], tmpdir_name: str):
    """One real background child of this process, so the liveness verdict has something to see."""
    (fix.base / tmpdir_name).mkdir(parents=True, exist_ok=True)
    env = dict(fix.env)
    env["TMPDIR"] = str(fix.base / tmpdir_name)
    env["CLAUDE_PROJECT_DIR"] = str(fix.base)
    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    fix.env["WORKLIST_HARNESS_PID"] = str(os.getpid())
    return proc


def mk_report(fix, at: str, silent: bool, title: str) -> None:
    """One sub-agent report in the fixture store, replacing whatever index was there."""
    store = fix.base / "reports"
    (store / "agenttest").mkdir(parents=True, exist_ok=True)
    (store / "agenttest" / "r.md").write_text(title + "\nbody", encoding="utf-8")
    (store / "index.jsonl").write_text(
        json.dumps(
            {
                "ev": "report",
                "id": "abcdef123456",
                "at": at,
                "branch": "agenttest",
                "agent": "some-teammate",
                "type": "some-teammate",
                "session": "deadbeef",
                "body": "agenttest/r.md",
                "bytes": 900,
                "silent": silent,
                "sends": 1,
                "title": title,
                "transcript": "",
                "src": "hook",
            }
        )
        + "\n",
        encoding="utf-8",
    )


def stamp(minutes_ago: float = 0.0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - minutes_ago * 60))


def test_163x_no_cli_verb_may_fall_through_to_the_stop_battery(wl):  # noqa: F811
    """THE DEFECT, measured on HEAD before the fix rather than theorised.

    A verb whose guard put the arity check INSIDE the condition did not fail on too few arguments: it fell through to the hook path, which runs the whole battery against an EMPTY event. With stdin closed that returned a genuine block verdict at EXIT 0 and wrote six unknown-session sidecars for a session id that does not exist; with stdin left open it hung forever in json.load. Both
    reproduced. The fix is the CLASS, not the three verbs anyone noticed: any first argument with a leading dash that matched no verb is refused, so a typo can neither emit a verdict nor hang.
    """
    for bad in (["--loop", "x"], ["--brief"], ["--tpyo"], ["--state"]):
        got = wl.cli(*bad)
        merged = got.out + got.err
        assert got.rc == 2, "163x: %r rc=%d verdict=%s" % (bad, got.rc, merged[:120])
        assert '"decision": "block"' not in merged, "163x: %r emitted a verdict: %s" % (
            bad,
            merged[:120],
        )
    # It must not hang either. stdin is a pipe that STAYS OPEN, and the timeout is on the interpreter itself, NOT on a shell wrapping a sleep, which is what made the first measurement of this read as a timeout of the sleep rather than of python.
    read_fd, write_fd = os.pipe()
    env = dict(wl.env)
    env["CLAUDE_PROJECT_DIR"] = str(wl.proj)
    proc = subprocess.Popen(
        [sys.executable, str(wl.hook), "--tpyo"],
        stdin=read_fd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    os.close(read_fd)
    hung = False
    rc = None
    try:
        rc = proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        hung = True
        proc.kill()
        proc.wait()
    finally:
        os.close(write_fd)
    assert not hung, "163x: an unknown verb still hangs reading stdin"
    assert rc != 0, "163x: an unknown verb succeeded, which it must not"


def test_163x_control_the_well_formed_verbs_still_work(wl):  # noqa: F811
    """CONTROL: the legitimate forms still work, so the guards refuse arity and not the verb."""
    declared = wl.cli_as("looppfx1", "--loop", "looppfx1", "2026-01-01T00:00:00Z", "1", "label")
    assert_in(declared, "loop declared", "163x CONTROL: a well-formed --loop still declares")
    recorded = wl.cli_as("briefpf1", "--brief", "briefpf1", "some", "text")
    assert_in(recorded, "brief recorded", "163x CONTROL: a well-formed --brief still records")


def test_163g_a_bare_item_id_is_refused_as_a_brief(wl):  # noqa: F811
    """A LONE ITEM ID is a misread of the verb, not a very short brief.

    The word reads both ways (publish a brief, or brief somebody on a topic) and `--brief <me> <text...>` is `--tick <me> <id> <evidence>` minus the evidence, so the id lands where the sentence goes. Paid for live: a session meaning to READ item 65ce7ca3 published it, and the roster then advertised "65ce7ca3" as that session's live activity to every later reader. Both real id
    widths are covered, since ids are 8 or 12 hex and the code must never assume one width.
    """
    # CAPTURE THEN MATCH, never a pipeline into grep. The bash suite runs under `set -uo pipefail`, so a pipeline carries the FIRST non-zero exit rather than grep's: the refusal exits 2 by design, which made the pipeline false while grep was matching perfectly, and the first version of these cases failed on a green tree and also failed under a mutation that disabled the guard.
    for width in ("65ce7ca3", "a1b2c3d4e5f6"):
        got = wl.cli_as("briefpf2", "--brief", "briefpf2", width)
        merged = got.out + got.err
        assert got.rc == 2, "163g: a bare %d-char id: rc=%d out=%s" % (
            len(width),
            got.rc,
            merged[:90],
        )
        assert "shape of an item id" in merged, "163g: a bare %d-char id: out=%s" % (
            len(width),
            merged[:90],
        )


def test_163g_control_real_briefs_still_record(wl):  # noqa: F811
    """CONTROL: the discriminator is a LONE all-hex token of id width, so anything with a second word, any non-hex character, or a length outside the band must still record."""
    rows = [
        (
            "an id followed by real words",
            ["65ce7ca3", "is", "what", "the", "session", "is", "reading"],
        ),
        ("a short non-hex word", ["triage"]),
        ("a hex string past the id width", ["abcdefabcdefabcde"]),
        ("a hex string under the id width", ["abcde"]),
    ]
    for why, words in rows:
        got = wl.cli_as("briefpf3", "--brief", "briefpf3", *words)
        merged = got.out + got.err
        assert got.rc == 0, "163g CONTROL: %s was wrongly refused (rc=%d)" % (why, got.rc)
        assert "brief recorded" in merged, "163g CONTROL: %s did not record: %s" % (
            why,
            merged[:90],
        )


def test_163x_control_a_bare_invocation_still_runs_the_battery(wl):  # noqa: F811
    """CONTROL 2, THE LOAD-BEARING ONE: the real Stop hook takes NO arguments, so the leading-dash catch-all must not be able to swallow it.

    If this regressed, every stop in the repo would exit 2 instead of running any check at all. The bash asserted a verdict key OR any output at all, which is the same claim as this one: the battery ran.
    """
    wl.brief_now()
    wl.hand_now()
    wl.say("answer")
    wl.task(7, "pending", "something")
    got = wl.run()
    assert got.out.strip(), (
        "163x CONTROL: the catch-all swallowed the real hook: %r" % got.out[:200]
    )


def test_163y_unread_sub_agent_reports_are_surfaced_on_an_ordinary_stop(wl):  # noqa: F811
    """v18. SessionStart and PostCompact are covered by wl_report's own hooks; this is the commoner case they miss, a long-running session whose teammate finished twenty minutes ago and whose SendMessage has scrolled out of reach.

    IT USED TO BE REPORT-ONLY FOREVER, on the stated grounds that no honest evidence of having read one could be demanded at a stop. That grounds was untrue (`wl_report.py --read <me> <id>` is exactly such evidence, and the advisory already printed the command) and the cost was measured: outq_drain runs only on the ALLOW path, so one session carried four unread teammate reports
    through 57 consecutive BLOCKING stops and was never once told. So it graduates: an advisory while it is news, a violation once it is a debt, an invariant at UNREAD_INVARIANT_MIN or on any silent report.
    """
    wl.brief_now()
    wl.hand_now()
    # FRESH: minutes old, so it is still news. Advisory, exactly as before.
    mk_report(wl, stamp(2), False, "SUBSTANTIVE FINDING FROM A TEAMMATE")
    wl.say(SAID_DONE)
    got = wl.run()
    label = "163y: an unread report is surfaced on an ordinary stop, with its title"
    assert_in(got, "UNREAD SUB-AGENT REPORTS", label)
    assert_in(got, "SUBSTANTIVE FINDING FROM A TEAMMATE", label)
    wl.check_quiet(
        '"decision": "block"',
        "163y: while it is still NEWS it is report-only and does not block",
        result=got,
    )

    # AGED past UNREAD_INVARIANT_MIN: the advisory queue has demonstrably failed to deliver it, so it becomes an invariant and blocks.
    wl.newturn()
    mk_report(wl, "2026-01-01T10:00:00Z", False, "SUBSTANTIVE FINDING FROM A TEAMMATE")
    wl.say(SAID_DONE)
    aged = wl.run()
    label = "163y: an unread report old enough to be a debt BLOCKS"
    assert_in(aged, '"decision": "block"', label)
    assert_in(aged, "UNREAD SUB-AGENT REPORTS", label)

    # A silent report blocks regardless of age: an agent that stopped without reporting is the case indistinguishable from a healthy one unless somebody looks, which is the whole reason the flag exists.
    wl.newturn()
    mk_report(wl, stamp(2), True, "SILENT TEAMMATE")
    wl.say(SAID_DONE)
    quiet = wl.run()
    label = "163y: a fresh silent report blocks without waiting out the ladder"
    assert_in(quiet, '"decision": "block"', label)
    assert_in(quiet, "SILENT TEAMMATE", label)

    # Back to a fresh substantive one, so the CONTROLS below read the same shape the original fixture handed them.
    wl.newturn()
    mk_report(wl, stamp(2), False, "SUBSTANTIVE FINDING FROM A TEAMMATE")
    # CONTROL: marked read, the section is gone. Without this the assertion above is satisfied by any section that is simply always emitted.
    (wl.base / "reports" / "read.jsonl").write_text(
        json.dumps(
            {
                "ev": "read",
                "id": "abcdef123456",
                "by": "deadbeef",
                "at": "2026-08-05T10:05:00Z",
                "branch": "agenttest",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    # A fresh, not-yet-shown peer note, so SOMETHING else is queued once the unread-report section clears -- otherwise the fixed 3-per-stop budget can drain everything queued by this point in the fixture, leaving check_quiet with no non-vacuous evidence the hook ran at all.
    wl.brief_other("cafe5678")
    wl.newturn()
    wl.say(SAID_DONE)
    wl.check_quiet(
        "UNREAD SUB-AGENT REPORTS", "163y CONTROL: once marked read, the section is gone"
    )

    # CONTROL: a report on ANOTHER branch is not this branch's business.
    with (wl.base / "reports" / "index.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "ev": "report",
                    "id": "999999999999",
                    "at": "2026-08-05T10:00:00Z",
                    "branch": "some-other-branch",
                    "agent": "elsewhere",
                    "type": "elsewhere",
                    "session": "deadbeef",
                    "body": "x/y.md",
                    "bytes": 900,
                    "silent": False,
                    "sends": 1,
                    "title": "FROM ANOTHER BRANCH",
                    "transcript": "",
                    "src": "hook",
                }
            )
            + "\n"
        )
    wl.newturn()
    wl.say(SAID_DONE)
    foreign = wl.run()
    why = "163y CONTROL: a foreign branch's report leaked in: %r" % foreign.out[:250]
    assert "FROM ANOTHER BRANCH" not in foreign.out, why
    # With both reports out of scope (one read, one on another branch) the stop says nothing at all, which is why `check_quiet` (which refuses to pass on silence) is not the instrument here. The silence is the stronger claim: a leak would surface the unread-reports section, as the first three stops in this case show.
    assert not foreign.out.strip(), why


def test_163z_c1_control_a_waiter_that_is_not_confirmed_buys_nothing(wl):  # noqa: F811
    """CONTROL: same fixture, same command string, but the process is DEAD, so the verdict is `suspect`.

    Without this control, case 163z would equally pass if the code had simply stopped running either check at all.
    """
    wl.brief_now()
    wl.hand_now()
    bgout(wl)
    wl.env["WORKLIST_HARNESS_PID"] = str(os.getpid())
    wl.bg = json.dumps([waiter_row("wt1", "inbox waiter (dead)")])
    wl.crons = json.dumps(WORK_LOOP_CRONS)
    wl.task(7, "in_progress", "waiting on the inbox")
    wl.say(SAID_INBOX)
    wl.run()
    seed_bgwait(wl)
    wl.newturn()
    wl.say(SAID_INBOX)
    got = wl.run()
    assert_in(
        got,
        "PURE BACKGROUND WAIT",
        "163z-c1 CONTROL: the check-in was skipped for a DEAD waiter",
    )


def test_163z_c2_control_a_waiter_does_not_silence_a_real_job_beside_it(wl):  # noqa: F811
    """CONTROL: relaxing on "any waiter present" would let one waiter suppress supervision of everything else.

    The suppression requires EVERY live task to be a confirmed waiter, and this is the case that pins that word.
    """
    wl.brief_now()
    wl.hand_now()
    bgout(wl)
    (wl.base / "bgout" / "bw1.output").write_text("worker stream content\n", encoding="utf-8")
    proc = spawn(wl, [sys.executable, str(WAIT_PY), "deadbeef", "--timeout", "3"], "waittmp2")
    try:
        time.sleep(1)
        wl.bg = json.dumps(
            [
                waiter_row("wt1"),
                {
                    "id": "bw1",
                    "type": "shell",
                    "status": "running",
                    "command": "sleep 999",
                    "description": "long CI watch",
                },
            ]
        )
        wl.task(7, "in_progress", "waiting on both")
        wl.say(SAID_BOTH)
        wl.run()
        seed_bgwait(wl)
        wl.newturn()
        wl.say(SAID_BOTH)
        got = wl.run()
        assert_in(
            got,
            "PURE BACKGROUND WAIT",
            "163z-c2 CONTROL: one waiter silenced supervision of a real job",
        )
    finally:
        proc.kill()
        proc.wait()


def test_163b_a_stale_output_stream_is_flagged_possibly_stuck(wl):  # noqa: F811
    """A stream that has not grown for 25 minutes is direct evidence no self-report can fake, so the check-in calls it out."""
    wl.brief_now()
    wl.hand_now()
    bgout(wl)
    quiet_stream = wl.base / "bgout" / "bw2.output"
    quiet_stream.write_text("old content\n", encoding="utf-8")
    old = time.time() - 25 * 60
    os.utime(quiet_stream, (old, old))
    wl.bg = json.dumps(
        [{"id": "bw2", "type": "shell", "status": "running", "description": "quiet worker"}]
    )
    wl.task(7, "pending", "thing")
    wl.say(SAID_THING)
    wl.run()
    seed_bgwait(wl)
    wl.newturn()
    wl.say(SAID_THING)
    got = wl.run()
    assert_in(got, "POSSIBLY STUCK", "163b: a 25-minute-silent stream is called out")


def test_163c_control_an_open_item_means_normal_battery_no_wait_check_in(wl):  # noqa: F811
    """CONTROL: open work suppresses the wait check-in, because a session with an open item is not waiting on anything."""
    wl.brief_now()
    wl.hand_now()
    bgout(wl)
    wl.bg = json.dumps(
        [{"id": "bw3", "type": "shell", "status": "running", "description": "worker"}]
    )
    wl.add_item("- [ ] (deadbeef) real open work")
    wl.say("answer\n\n## Remaining\n- the open work")
    wl.check_quiet("PURE BACKGROUND WAIT", "163c: check-in fired despite open work")


def test_163d_a_due_check_in_forfeits_the_silent_poll(wl):  # noqa: F811
    """A fresh check-in mark keeps the poll fast path; a due one pays the battery and delivers the worker facts."""
    wl.brief_now()
    wl.hand_now()
    bgout(wl)
    (wl.base / "bgout" / "bw4.output").write_text("stream\n", encoding="utf-8")
    wl.bg = json.dumps(
        [{"id": "bw4", "type": "shell", "status": "running", "description": "watch"}]
    )
    wl.task(6, "in_progress", "the live prerequisite")
    # v19: blocked scenery so the pure-wait premise holds.
    wl.task(7, "pending", "thing", "6")
    wl.say(SAID_THING)
    wl.run()  # establishes the bgwait mark via the first check-in
    wl.cli("--poll", "deadbeef")
    fresh = wl.run()
    assert not fresh.out.strip(), (
        "163d: poll paid the battery inside the window: %r" % fresh.out[:200]
    )

    seed_bgwait(wl)
    wl.cli("--poll", "deadbeef")
    due = wl.run()
    label = "163d CONTROL: a due check-in forfeits the silent poll and delivers the facts"
    assert due.out.strip(), "%s: due check-in stayed silent" % label
    assert_in(due, "PURE BACKGROUND WAIT", label)


def derivation_probe(fix, faketmp, session_id: str) -> str:
    """`wl_liveness.bg_output_facts` with NO override, driven through the real TMPDIR derivation."""
    script = (
        "import os, sys, tempfile\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "tempfile.tempdir = None\n"  # re-read TMPDIR
        "import wl_liveness\n"
        "rows = wl_liveness.bg_output_facts('/x/y', sys.argv[2], "
        "[{'id': 'bw5', 'status': 'running', 'description': 'd'}])\n"
        "print('found' if rows and rows[0][2] is not None else 'missing')\n"
    )
    env = dict(fix.env)
    env.pop("WORKLIST_BG_OUTPUT_DIR", None)
    env["TMPDIR"] = str(faketmp)
    got = subprocess.run(
        [sys.executable, "-c", script, str(wlfix.STOP_DIR), session_id],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return got.stdout.strip()


def test_163e_the_output_stream_path_derivation_finds_the_claude_uid_layout(wl):  # noqa: F811
    """Regression gate for 9b557ab0e: every other background case overrides the base via WORKLIST_BG_OUTPUT_DIR, so the derivation itself was untested and its first live firing missed the claude-<uid> segment.

    This case exercises the real derivation end to end: no override, TMPDIR pointed at a fixture root, and the stream living exactly where the harness writes it.
    """
    faketmp = wl.base / "faketmp"
    session_id = "b9491d9c-full-session-id-fixture"
    munged = "-x-y"  # the non-alphanumeric substitution of cwd "/x/y"
    tasks = faketmp / ("claude-%d" % os.getuid()) / munged / session_id / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    stream = tasks / "bw5.output"
    stream.write_text("stream\n", encoding="utf-8")
    found = derivation_probe(wl, faketmp, session_id)
    assert found == "found", "163e: derivation missed the claude-<uid> layout (got: %r)" % found

    # CONTROL: with the stream ABSENT the same call reports missing, so the case cannot pass vacuously on a derivation that never stats anything.
    stream.unlink()
    missing = derivation_probe(wl, faketmp, session_id)
    assert missing == "missing", "163e CONTROL: vacuous probe (got: %r)" % missing


def test_163f_a_stale_stream_with_a_verified_alive_process_is_not_called_stuck(wl):  # noqa: F811
    """Fired live 2026-07-31: a healthy CI poll loop, silent by design for 29 minutes, was accused POSSIBLY STUCK.

    Two fixes are pinned here at once: _needle must extract a quote-free SEGMENT (the poll-loop command has a quoted middle, so the old whole-line rule made it unverifiable), and the check-in must consult verify_background before accusing.
    """
    wl.brief_now()
    wl.hand_now()
    bgout(wl)
    quiet_stream = wl.base / "bgout" / "bw6.output"
    quiet_stream.write_text("old content\n", encoding="utf-8")
    old = time.time() - 25 * 60
    os.utime(quiet_stream, (old, old))
    probe = subprocess.Popen(
        ["sleep", "3717171717"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    wl.env["WORKLIST_HARNESS_PID"] = str(os.getpid())
    try:
        # The quoted tail is load-bearing: the OLD _needle refused any line carrying a quote, which is exactly how the live worker became unverifiable.
        wl.bg = json.dumps(
            [
                {
                    "id": "bw6",
                    "type": "shell",
                    "status": "running",
                    "description": "silent poll loop",
                    "command": 'sleep 3717171717 "# ci watch tail"',
                }
            ]
        )
        wl.task(7, "pending", "thing")
        wl.say(SAID_THING)
        wl.run()
        seed_bgwait(wl)
        wl.newturn()
        wl.say(SAID_THING)
        got = wl.run()
        label = "163f: a stale stream backed by a live process is reported alive, not stuck"
        assert_in(got, "VERIFIED ALIVE", label)
        # NOT a plain "POSSIBLY STUCK" needle: V_BG_REPORT's fixed instruction text says to restart or replace anything marked POSSIBLY STUCK on every check-in, so only the per-row marker is the accusation.
        wl.check_quiet("<- POSSIBLY STUCK", label, result=got)
    finally:
        probe.kill()
        probe.wait()

    # CONTROL: kill the process and the SAME setup goes back to POSSIBLY STUCK, so the rescue is the verification rather than an unconditional soft-pedal.
    seed_bgwait(wl)
    wl.newturn()
    wl.say(SAID_THING)
    dead = wl.run()
    label = "163f CONTROL: with the process dead the same worker is called out as stuck"
    assert_in(dead, "<- POSSIBLY STUCK", label)
    wl.check_quiet("VERIFIED ALIVE", label, result=dead)
