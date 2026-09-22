"""Fixture isolation, judge-child diagnostics, and the v19 identity ladder: verb refusal, phantom sessions, --reassign, root resolution.

Ported from `.claude/hooks/stop/worklist-cases/18-identity.sh`, one pytest function per numbered bash case.

v19: RUNTIME CALLER IDENTITY. Every `<me>` argument used to be accepted on SHAPE alone (PREFIX_RE), and nothing had ever compared one to reality. THE DEFECT, replayed verbatim by case 184: a session copied a SUB-AGENT's namespace token out of a Task-spawn tool result (`agent_id: search-renet2@session-4c3e095a`) and passed it as its own `<me>` for 26 hours, 219 calls under
4c3e095a and 20 under its real id, from ONE process. Every call SUCCEEDED, because writes and reads key off the same unvalidated string, so one typo splits a session into two internally-consistent halves, and a peer's message waited 34 hours in the half nobody was reading.

CASES 184, 184w AND 185 READ ONE DRIVER and share an xdist group for that reason. Case 185 refuses to type the verb list out: it derives it from `worklist.py`'s own dispatch and checks it against a coverage set the driver records AS IT DRIVES EACH VERB. A table written by hand would be the same bug one layer up, and a coverage set grepped out of this file would pass on a battery
that never ran.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time

import pytest

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

# The literal from the incident: a sub-agent namespace token passed as a session's own `<me>`.
FOREIGN = "4c3e095a"

# Cases 184, 184w and 185 read ONE driver, `l1` below, because the bash ran them against one unbroken world: 184 drove every identity-taking verb, 184w drove the waiter beside it, and 185 read the coverage file both had written. A module-scoped fixture keeps that world, and keeps each of the three selectable on its own.
XDIST_GROUP = "wl-identity-l1"


def l1run(fix, *argv: str, peer: str = "") -> wlfix.Result:
    """The CLI under the fixture, with the STATE body on stdin so `--state` is drivable.

    The bash folded stderr into stdout, so every caller below reads `out + err`.
    """
    env = dict(fix.env)
    env["WORKLIST_JUDGE"] = "off"
    env["WORKLIST_PUBLISH_ROOT"] = str(fix.base)
    env["WORKLIST_PROJECTS_DIR"] = str(fix.base / "l1projects")
    if peer:
        env["WORKLIST_SESSION_ID"] = wlfix.peer_id(peer)
    return fix.python(list(argv), stdin=wlfix.STATE_BODY, env=env)


def both(got: wlfix.Result) -> str:
    """Stdout and stderr together, which is what the bash `2>&1` produced."""
    return got.out + got.err


def added_id(text: str) -> str:
    """The item id `--add` printed."""
    found = re.search(r"^added #([0-9a-f]+)", text, re.MULTILINE)
    return found.group(1) if found else ""


def request_id(text: str) -> str:
    """The request id `--ask` printed."""
    found = re.search(r"#([0-9a-f]{8})", text)
    return found.group(1) if found else ""


def plant_l1_report(fix) -> None:
    """One indexed report the `--reports` rows can mark read and list."""
    store = fix.base / "reports"
    (store / "agenttest").mkdir(parents=True, exist_ok=True)
    (store / "agenttest" / "l1.md").write_text("L1 FIXTURE REPORT\nbody", encoding="utf-8")
    (store / "index.jsonl").write_text(
        json.dumps(
            {
                "ev": "report",
                "id": "l1report0001",
                "at": "2026-08-05T10:00:00Z",
                "branch": "agenttest",
                "agent": "l1-teammate",
                "type": "l1-teammate",
                "session": "deadbeef",
                "body": "agenttest/l1.md",
                "bytes": 900,
                "silent": False,
                "sends": 1,
                "title": "L1 FIXTURE REPORT",
                "transcript": "",
                "src": "hook",
            }
        )
        + "\n",
        encoding="utf-8",
    )


def plant_adopt_chain(fix, previous: str = "adopt111") -> None:
    """A CHAIN for the `--adopt` row.

    `--adopt` is an identity-taking verb so the table must drive it, and CONTROL A demands rc=0, which for an EVIDENCE-GATED verb means planting the evidence. The predecessor's transcript needs the continued-in line, the boundary pair, AND a record this suite's own transcript also carries; without all three the verb refuses, which is the whole point of it.
    """
    projects = fix.base / "l1projects"
    projects.mkdir(parents=True, exist_ok=True)
    prev_sid = "%s-9999-8888-7777-666666666666" % previous
    boundary = "ad0b7ed0-0000-0000-0000-000000000001"
    logical = "ad0b7ed0-0000-0000-0000-000000000002"
    shared = "ad0b7ed0-1111-2222-3333-444444444444"
    (projects / ("%s.jsonl" % fix.sid)).write_text(
        "".join(
            json.dumps(record) + "\n"
            for record in [
                {"type": "mode", "mode": "default"},
                {
                    "type": "system",
                    "subtype": "compact_boundary",
                    "parentUuid": None,
                    "uuid": boundary,
                    "logicalParentUuid": logical,
                },
                {"type": "user", "uuid": shared, "message": {"role": "user", "content": "carried"}},
            ]
        ),
        encoding="utf-8",
    )
    (projects / ("%s.jsonl" % prev_sid)).write_text(
        "".join(
            json.dumps(record) + "\n"
            for record in [
                {"type": "user", "uuid": shared, "message": {"role": "user", "content": "carried"}},
                {
                    "type": "system",
                    "subtype": "compact_boundary",
                    "uuid": boundary,
                    "logicalParentUuid": logical,
                },
                {"type": "continued-in", "continuedInSessionId": fix.sid},
            ]
        ),
        encoding="utf-8",
    )


def probe_phantom(fix) -> str:
    """`wl_checks.phantom_identities` as a library call: "BLIND: <reason>" or "FLAGGED: <prefixes>".

    DRIVEN AS A LIBRARY CALL, not through a Stop event, and that is a real fact about the code rather than test convenience: run_stop writes its OWN `.lastevent-<me8>.json` before this check runs, so on the Stop path the set is never empty.
    """
    code = (
        "import pathlib, sys\n"
        "sys.path.insert(0, %r)\n"
        "import wl_checks as CK, wl_store as S, wl_requests as R\n"
        "wl = pathlib.Path(%r)\n"
        "found, blind = CK.phantom_identities(wl, %r, S.load(wl, sync=False), R.read_requests(wl))\n"
        "print('BLIND: %%s' %% blind if blind else 'FLAGGED: %%s' %% ','.join(f[0] for f in found))"
    ) % (str(wlfix.STOP_DIR), str(fix.wl), wlfix.SID)
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=dict(fix.env),
        check=False,
    )
    return (proc.stdout + proc.stderr).strip()


def test_181_isolation_the_suite_can_never_reach_the_live_worklist(wl):  # noqa: F811
    """Raised by the team lead after a run of this suite came back with failures a clean tree could not reproduce, on the hypothesis that fixture state and live session state were mixing. They were not mixing on DISK, since every invocation passes TMPDIR, but the check belongs here rather than in anyone's memory, because the cost of being wrong is a suite that tests the operator's
    real store. Two halves: the store path resolves inside the fixture, and the ENVIRONMENT the hook reads carries no ambient knob.
    """
    resolved = wl.python(["--path"]).out.strip()
    assert resolved.startswith(str(wl.base / "tmp")), "fixture store escaped to %r" % resolved

    # CONTROL: without the fixture TMPDIR the SAME command resolves somewhere else entirely, so the assertion above is about TMPDIR doing the work and not about the path being unconditionally fixture-shaped.
    elsewhere = wl.python(["--path"], env=dict(wl.env, TMPDIR="/var/tmp")).out.strip()
    assert elsewhere != resolved, "CONTROL: TMPDIR did not move the store (%r)" % elsewhere
    assert elsewhere.startswith("/var/tmp/"), (
        "CONTROL: TMPDIR did not move the store (%r)" % elsewhere
    )

    # The env half. Every WORKLIST_* knob the operator's shell might carry is scrubbed by `wlfix.scrubbed_environ`, and `setup()` re-scrubs the ones cases set, so a stop here runs on the suite's own configuration whatever the launching shell had.
    knobs = (
        "WORKLIST_QUIET_WAKES",
        "WORKLIST_BG_OUTPUT_DIR",
        "WORKLIST_HARNESS_PID",
        "WORKLIST_BG_REPORT_MIN",
        "WORKLIST_FOCUS",
        "WORKLIST_STUCK_ROUNDS",
        "WORKLIST_JUDGE_CACHE_MIN",
    )
    leaked = [name for name in knobs if wl.env.get(name)]
    assert not leaked, "ambient knobs leaked into the case: %s" % leaked
    leaked = [name for name in wlfix.scrubbed_environ() if name.startswith("WORKLIST_")]
    assert not leaked, "the scrub let a WORKLIST_* knob through: %s" % leaked

    # The report store is pinned rather than scrubbed: an UNSET WORKLIST_REPORTS_DIR is not neutral, it points wl_report at the operator's real store under the home directory.
    assert wl.env.get("WORKLIST_REPORTS_DIR") == str(wl.base / "reports"), (
        "report store is %r" % wl.env.get("WORKLIST_REPORTS_DIR", "<unset, reads the REAL store>")
    )


def test_182_sessionstart_source_compact_does_not_re_inject_the_docs_blurb(wl):  # noqa: F811
    """THE BUG (operator, 2026-08-04): a long-running licensing session compacted, Claude Code fired SessionStart with source=compact, and the session was handed "N design doc(s) in docs/ci-overhaul" plus an order to read all of them, material belonging to an unrelated program, injected mid-task. Compaction is handle_post_compact's job: it already re-points at the design docs AND
    hands back the branch's plans, so SessionStart must stay quiet.
    """
    (wl.proj / "docs" / "ci-overhaul").mkdir(parents=True, exist_ok=True)
    (wl.proj / "docs" / "ci-overhaul" / "01-design.md").write_text(
        "# doc\nbody\n", encoding="utf-8"
    )
    (wl.proj / "agent").mkdir(parents=True, exist_ok=True)
    (wl.proj / "agent" / "PLAN-a.md").write_text(
        "# PLAN: a\nStatus: draft\nOwner: t\nUpdated: 2026-08-04\n\nbody\n", encoding="utf-8"
    )

    def ss_out(source: str | None) -> str:
        payload = {"session_id": wl.sid, "cwd": str(wl.proj), "hook_event_name": "SessionStart"}
        if source is not None:
            payload["source"] = source
        return wl.python(["--session-start"], stdin=json.dumps(payload)).out

    assert ss_out("compact") == "", "compact still injects context"

    # THE CONTROL, because a check that can only pass is not a check: the very same fixture must still speak on a genuinely new session, and on an event with no source field at all (the shape every older case in this suite feeds).
    out = ss_out("startup")
    assert "READ ALL OF THEM" in out, "CONTROL: startup lost its context: %s" % out[:300]
    assert "READ EVERY NON-DONE PLAN" in out, "CONTROL: startup lost its context: %s" % out[:300]
    out = ss_out(None)
    assert "READ ALL OF THEM" in out, "CONTROL: a missing source silenced the hook: %s" % out[:300]

    # The marker the judge stamp rides on is set BEFORE the compact return, so a compacted session still gets the full approval reason on its next judged stop.
    for path in (wl.base / "tmp" / "claude-worklist").glob("*.state-*.json"):
        path.unlink()
    ss_out("compact")
    docs = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (wl.base / "tmp" / "claude-worklist").glob("*.state-*.json")
    ]
    assert any(
        doc.get("ctx_fresh", {}).get("why", "").startswith("session-start") for doc in docs
    ), "the compact path stopped marking ctx_fresh: %s" % docs


def test_183_a_failed_judge_child_explains_itself_not_an_empty_stderr():
    """THE BUG (2026-08-05): the Stop gate blocked with "judge exited 1: " and nothing after the colon, which is unactionable.

    wl_judge reported proc.stderr on a non-zero exit, but the claude CLI writes its error ENVELOPE TO STDOUT, stderr is empty, and the is_error branch that would have explained it sits behind returncode == 0, so it was unreachable exactly when needed. The real cause was error_max_budget_usd at $0.1025 against a $0.10 cap. A gate that cannot say why it failed is an escape hatch
    wearing a gate's clothes: the same swallowed-failure class this repo scans for, inside the thing that audits it.
    """
    judge = wlfix.import_wl("wl_judge")

    class Proc:
        def __init__(self, rc: int, out: str, err: str):
            self.returncode, self.stdout, self.stderr = rc, out, err

    # Derive the over-budget cost from the CURRENT constant rather than hardcoding the 0.1025 that was measured against a $0.10 default. The first draft of this case pinned the literal and went red the moment the default was raised to $0.25, a test coupled to a constant it does not own, caught by running it.
    budget = float(judge.JUDGE_BUDGET_USD)
    envelope = json.dumps(
        {
            "is_error": True,
            "subtype": "error_max_budget_usd",
            "stop_reason": "tool_use",
            "total_cost_usd": budget + 0.01,
        }
    )
    msg = judge._explain_failed_exit("judge", Proc(1, envelope, ""))
    # The cause must be NAMED. Asserting merely "non-empty" would have passed on the original defect too, whose message was also non-empty.
    assert "error_max_budget_usd" in msg, msg
    assert "cost=" in msg, msg
    assert "BUDGET EXHAUSTED" in msg, msg

    # CONTROL 0: a failure UNDER budget must NOT cry budget. Without this, a message that always shouted BUDGET EXHAUSTED would satisfy the assertion above.
    under = json.dumps(
        {"is_error": True, "subtype": "error_during_execution", "total_cost_usd": budget / 2}
    )
    m0 = judge._explain_failed_exit("judge", Proc(1, under, ""))
    assert "BUDGET EXHAUSTED" not in m0, m0
    assert "error_during_execution" in m0, m0

    # CONTROL 1: unparseable stdout must still say something concrete rather than falling back to the empty stderr that started all this.
    m2 = judge._explain_failed_exit("judge", Proc(1, "segfault", ""))
    assert "segfault" in m2, m2

    # CONTROL 2: a populated stderr must still be surfaced, so the fix did not trade one blind spot for another.
    m3 = judge._explain_failed_exit("triage", Proc(2, "", "boom: no such model"))
    assert "no such model" in m3, m3

    # CONTROL 3: the label distinguishes the two call sites, which is how an operator knows whether triage or the judge died.
    assert m3.startswith("triage exited 2"), m3

    # CONTROL 4, THE ONE THAT MATTERS, and it was missing from the first draft. Everything above exercises the HELPER. The defect lived in the CALL SITES, which formatted their own message from an empty stderr. Reverting a call site leaves the helper perfect and the bug fully restored, and the planted-defect proof showed exactly that: the case passed with the original defect back
    # in place. A test that cannot see the regression it was written for is the ninth instance of the probe-tests-the-wrong-thing class in this campaign. So assert the wiring, not just the function.
    src = (wlfix.STOP_DIR / "wl_judge.py").read_text(encoding="utf-8")
    code = "\n".join(line for line in src.splitlines() if not line.lstrip().startswith("#"))
    assert code.count("_explain_failed_exit(") >= 3, (
        "both non-zero-exit call sites must route through the helper (definition + 2 uses); found %d"
        % code.count("_explain_failed_exit(")
    )
    assert "exited %d: %s" not in code, (
        "a call site is formatting its own exit message again, which is the 2026-08-05 defect, "
        "reporting an EMPTY stderr because the CLI writes its error envelope to stdout"
    )

    # THE EXIT-ZERO TWIN, 2026-08-26. Everything above is the non-zero path. The failure that actually stopped a session exits ZERO: transport fine, is_error false, structured_output null. The gate said "produced no usable structured_output: None" and nothing else, while the same envelope held the cost and the turn count, and the very next sentence of that block offers to DISABLE
    # the gate, so the unhelpful line is the worst place to be uninformative.
    spent = {
        "subtype": "success",
        "is_error": False,
        "stop_reason": "tool_use",
        "num_turns": 29,
        "total_cost_usd": budget,
    }
    e_spent = judge._explain_no_output("judge", spent, None)
    assert "BUDGET EXHAUSTED" in e_spent, e_spent
    assert "turns=29" in e_spent, e_spent
    assert "cost=" in e_spent, e_spent

    # CONTROL 5: a CHEAP exit-zero failure must not cry budget either. This is the same control as CONTROL 0, on the twin path, and it is what makes the assertion above evidence rather than a slogan.
    cheap = {
        "subtype": "success",
        "is_error": False,
        "stop_reason": "end_turn",
        "num_turns": 2,
        "total_cost_usd": budget / 10,
    }
    e_cheap = judge._explain_no_output("judge", cheap, None)
    assert "BUDGET EXHAUSTED" not in e_cheap, e_cheap
    assert "turns=2" in e_cheap, e_cheap

    # CONTROL 6: no envelope at all must still name the label and the payload rather than raising, because an unparseable stdout reaches here too.
    e_none = judge._explain_no_output("triage", None, None)
    assert e_none.startswith("triage produced no usable"), e_none

    # CONTROL 7, THE WIRING, for the same reason CONTROL 4 exists. The helper can be perfect while a call site still formats its own bare message, which is precisely how the exit-zero path stayed uninformative while the exit-non-zero path was fixed. All FOUR unusable-output sites must route through it.
    assert code.count("_explain_no_output(") >= 5, (
        "every unusable-output call site must route through the helper (definition + 4 uses); found %d"
        % code.count("_explain_no_output(")
    )
    assert "produced no usable structured_output: %s" not in code.replace(
        'bits = ["%s produced no usable structured_output: %s"', ""
    ), "a call site is formatting its own no-output message again"


class L1Drive:
    """What the v19 L1 battery did, recorded so three cases can assert on it independently.

    `covered` is the set of verbs the loop ACTUALLY DROVE, recorded as it drove them. Case 185 reads it, and it is deliberately not a list typed out anywhere: a hand-written table is the same bug the whole battery is about, one layer up.
    """

    def __init__(self):
        self.covered: set[str] = set()
        self.failures: list[str] = []
        self.poll_marker = False
        self.wait_fire: wlfix.Result | None = None
        self.wait_control: wlfix.Result | None = None


def drive_l1(fix) -> L1Drive:
    """Drive every identity-taking verb four ways, then the waiter, against one fixture world."""
    drive = L1Drive()
    fix.brief_now()
    fix.brief_other("cafe1234")
    plant_l1_report(fix)

    def mkitem(text: str) -> str:
        return added_id(both(l1run(fix, "--add", wlfix.ME, text)))

    # Fixtures the write verbs need. Built as deadbeef, which is this suite's own identity, so building them exercises CONTROL A's path before the table runs.
    i_tick = mkitem("l1-tick-item")
    i_defer = mkitem("l1-defer-item")
    i_update = mkitem("l1-update-item")
    i_lease = mkitem("l1-lease-item")
    mkitem("l1-list-item")  # the --list row asserts on the TEXT, not the id
    r_answer = fix.askid_as("cafe1234", "cafe1234", wlfix.ME, "l1-answer-me")
    r_decline = fix.askid_as("cafe1234", "cafe1234", wlfix.ME, "l1-decline-me")
    r_ack = request_id(both(l1run(fix, "--ask", wlfix.ME, "cafe1234", "l1-ack-me")))
    l1run(fix, "--answer", "cafe1234", r_ack, "l1-their-answer", peer="cafe1234")
    for name, value in (
        ("i_tick", i_tick),
        ("i_defer", i_defer),
        ("i_update", i_update),
        ("i_lease", i_lease),
        ("r_answer", r_answer),
        ("r_decline", r_decline),
        ("r_ack", r_ack),
    ):
        assert value, "FIXTURE BROKEN: %s was never created, so its row proves nothing" % name

    # A phantom for the --reassign row: three aged events under an identity that has never stopped, owning open items. This case runs no Stop hook, so no .lastevent- file exists for anybody here, which is exactly the phantom shape.
    fix.phantom_store("phantom1", 90)
    plant_adopt_chain(fix)

    # label, args (@WHO@ is substituted), needle proving the effect happened
    table = [
        ("--add", "--add @WHO@ l1-table-add", "added #"),
        ("--triage", "--triage @WHO@ l1-table-finding", "triaging #"),
        ("--tick", "--tick @WHO@ %s https://ci.invalid/run/1" % i_tick, "ticked #"),
        (
            "--defer",
            "--defer @WHO@ %s q DEFAULT: do-it WHY: needs-an-operator-ruling HOW: operator-answers"
            % i_defer,
            "deferred #",
        ),
        ("--update", "--update @WHO@ %s moved-a-bit" % i_update, "updated #"),
        ("--lease", "--lease @WHO@ %s +30 worker:l1bg" % i_lease, "leased #"),
        ("--list", "--list --open @WHO@", "l1-list-item"),
        ("--state", "--state @WHO@", "STATE.md section written"),
        ("--loop", "--loop @WHO@ 2099-01-01T00:00:00Z 1 l1-label", "loop declared"),
        ("--brief", "--brief @WHO@ l1-brief-text", "brief recorded"),
        ("--intent", "--intent @WHO@ l1-intent-text --for 30", "intent recorded"),
        ("--reap", "--reap @WHO@ l1task9", "reaped 1 task"),
        ("--migrate", "--migrate @WHO@ --candidates", ""),
        ("--ask", "--ask @WHO@ cafe1234 l1-table-ask", "request #"),
        ("--answer", "--answer @WHO@ %s l1-my-answer" % r_answer, "answered #"),
        ("--decline", "--decline @WHO@ %s l1-my-decline" % r_decline, "declined #"),
        ("--ack", "--ack @WHO@ %s" % r_ack, "acked #"),
        ("--poll", "--poll @WHO@", ""),
        ("--reports", "--reports --read @WHO@ l1report0001", "marked 1 report"),
        ("--reports", "--reports --list --as @WHO@", "L1 FIXTURE REPORT"),
        # Both take a `<me>` and both must prove their effect, not merely exit 0.
        ("--epic", "--epic @WHO@ new L1 probe epic", "epic #"),
        ("--publish", "--publish @WHO@ l1probe", "wrote agent/pr/"),
        ("--reassign", "--reassign @WHO@ phantom1", "reassigned phantom1 -> deadbeef"),
        # Evidence-gated, so CONTROL A only passes against the chain planted above.
        ("--adopt", "--adopt @WHO@ adopt111", "adopted"),
        # W12 plan records. Driven in their LISTING mode (a `<me>` and no path), which is the only mode whose effect is a printed line rather than a written file.
        # The write modes need a git repository with a committed plan AND a committed box ledger to reach rc=0, and planting one per verb here would prove the identity rule against a fixture rather than against the verb. The listing
        # runs the same argv parse, the same PREFIX_RE and the same _identity_or_die, which is the whole surface this table is about.
        ("--plan-compact", "--plan-compact @WHO@", "plan record candidates"),
        ("--plan-revive", "--plan-revive @WHO@", "plan records on disk"),
        # Same listing rule, same reason. --plan-tick's write mode needs a plan AND a committed box ledger; its listing mode is where a caller gets the box SIGNATURE the write mode wants, so the read is a prerequisite of the write rather than a convenience, and it runs the identical argv parse.
        ("--plan-tick", "--plan-tick @WHO@", "open boxes that --plan-tick can flip"),
    ]

    for verb, template, needle in table:
        drive.covered.add(verb)
        fire_args = template.replace("@WHO@", FOREIGN).split()
        good_args = template.replace("@WHO@", wlfix.ME).split()
        short_args = template.replace("@WHO@", "dead").split()

        # FIRE: the exact literal from the incident, against this suite's own id.
        got = l1run(fix, *fire_args)
        text = both(got)
        if not (got.rc != 0 and "identity mismatch" in text and wlfix.ME in text):
            drive.failures.append(
                "184 FIRE %s: accepted a foreign `<me>` (rc=%d): %s" % (verb, got.rc, text[:200])
            )

        # CONTROL A: one planted fact changed, the prefix, and the effect lands.
        got = l1run(fix, *good_args)
        text = both(got)
        if not (got.rc == 0 and (not needle or needle in text)):
            drive.failures.append(
                "184 CONTROL A %s: the check broke the verb (rc=%d, needle %r): %s"
                % (verb, got.rc, needle, text[:200])
            )

        # CONTROL B: the instrument BLIND. No id anywhere, so the check cannot know and must say nothing, and the FIRE command then succeeds, which is what proves FIRE was the check firing rather than the command failing anyway.
        blind = dict(fix.env)
        blind.pop("WORKLIST_SESSION_ID", None)
        blind.pop("CLAUDE_CODE_SESSION_ID", None)
        blind["WORKLIST_JUDGE"] = "off"
        blind["WORKLIST_PUBLISH_ROOT"] = str(fix.base)
        got = fix.python(fire_args, stdin="", env=blind)
        text = both(got)
        if "identity mismatch" in text:
            drive.failures.append(
                "184 CONTROL B %s: accused a caller it could not verify: %s" % (verb, text[:200])
            )

        # CONTROL C: the length floor, generalised from --poll's. `dead` IS a prefix of this session's id, so only the floor can refuse it, which is the whole point: same_session's symmetry would have accepted `--add d`.
        got = l1run(fix, *short_args)
        if got.rc == 0:
            drive.failures.append(
                "184 CONTROL C %s: accepted a 4-char `<me>`: %s" % (verb, both(got)[:200])
            )

    # --poll's effect is a FILE, not a line: an empty inbox prints nothing by contract, so CONTROL A above can only check the exit code for it.
    drive.poll_marker = fix.stem(".pollmark-deadbeef").is_file()

    # THE WAITER, on the same world and in the same pass, exactly as the bash drove it. It is a different entry point (wl_wait.py, not worklist.py) and getting it wrong is expensive in a way the others are not: a waiter armed against the wrong slice blocks for MINUTES on an inbox that is not its own, then reports nothing new.
    waitbin = wlfix.STOP_DIR / "wl_wait.py"

    def wait(prefix: str) -> wlfix.Result:
        proc = subprocess.run(
            [sys.executable, str(waitbin), prefix, "--timeout", "0.02"],
            capture_output=True,
            text=True,
            env=dict(fix.env, CLAUDE_PROJECT_DIR=str(fix.proj)),
            check=False,
        )
        return wlfix.Result(proc.stdout, proc.stderr, proc.returncode)

    drive.covered.add("--wait")
    drive.wait_fire = wait(FOREIGN)
    drive.wait_control = wait(wlfix.ME)
    return drive


@pytest.fixture(scope="module")
def l1(tmp_path_factory) -> L1Drive:
    """The L1 battery, run ONCE for the three cases that read it.

    Module-scoped so 184, 184w and 185 see one world without depending on each other's ordering, and pinned to one xdist worker so the battery is paid for once rather than per worker.
    """
    fixture = wlfix.Fixture(tmp_path_factory.mktemp("l1") / "hookfix")
    fixture.setup()
    return drive_l1(fixture)


@pytest.mark.xdist_group(XDIST_GROUP)
def test_184_every_verb_taking_a_me_refuses_an_identity_this_session_is_not(l1):
    """v19 L1: every verb taking a `<me>` refuses an identity this session is not.

    THREE CONTROLS PER VERB, each differing from FIRE in ONE planted fact:
      A  the prefix is this session's        -> accepted, and the effect HAPPENS
      B  the environment cannot name the caller -> accepted (the deliberate silent pass), which also proves FIRE was caused by the CHECK and not by an unrelated failure in the same command
      C  the prefix is too short             -> refused by the length floor
    """
    assert not l1.failures, "\n".join(l1.failures)
    assert l1.poll_marker, "184 CONTROL A --poll: exit 0 but no marker, so the verb did nothing"


@pytest.mark.xdist_group(XDIST_GROUP)
def test_184w_wait_is_on_the_same_rule_and_it_is_the_one_that_blocks_on_the_answer(l1):
    """The waiter is on the same rule, and it is the one that BLOCKS on the answer."""
    assert l1.wait_fire.rc != 0, (
        "FIRE: the waiter armed against a foreign identity: %s" % both(l1.wait_fire)[:200]
    )
    assert "identity mismatch" in both(l1.wait_fire), both(l1.wait_fire)[:200]

    # The heartbeat is UNLINKED on a clean timeout exit, so the effect to assert is the report line naming the session it actually listened for: a waiter armed against the wrong slice would name that one.
    assert l1.wait_control.rc == 0, "CONTROL A: the check broke the waiter (rc=%d): %s" % (
        l1.wait_control.rc,
        both(l1.wait_control)[:200],
    )
    assert "nothing new for deadbeef" in both(l1.wait_control), both(l1.wait_control)[:200]


@pytest.mark.xdist_group(XDIST_GROUP)
def test_185_anti_vacuity_the_verb_list_is_derived_from_the_source_not_typed_here(l1):
    """THE MOST IMPORTANT CASE IN THIS CHANGE.

    The defect's shape is "a rule applied to some call sites and not others", so a hand-written table is the same bug one layer up: add verb 14 next month, forget the table, and the suite stays green over a reopened hole. So the verb list comes from worklist.py's OWN dispatch, and every identity-taking verb must have been DRIVEN by case 184, proven by the coverage set the
    driver recorded at runtime, not by grepping this file, which would pass on a case that never ran.
    """
    assert l1.covered, "the driver recorded no verbs at all, so this case has nothing to check"
    src = (wlfix.STOP_DIR / "worklist.py").read_text(encoding="utf-8")
    verbs: set[str] = set()
    verbs.update(re.findall(r'sys\.argv\[1:2\] == \["(--[a-z-]+)"\]', src))
    verbs.update(re.findall(r'sys\.argv\[1\] == "(--[a-z-]+)"', src))
    for tup in re.findall(r"sys\.argv\[1\] in \(([^)]*)\)", src):
        verbs.update(re.findall(r'"(--?[a-z-]+)"', tup))

    # Verbs that take NO `<me>`, each for a stated reason. Adding to this list is a deliberate act; forgetting to add a NEW identity-taking verb is not, which is the asymmetry that makes this check work.
    no_me = {
        # --git is the mediated git capability. Its argv is <subcommand> [args] [--execute], never a `<me>`: it does not read, write or tick a worklist item, so there is no identity for a table row to substitute @WHO@ into.
        # Its risk is git writes, not identity handling, and that is covered where the risk lives: wl_git.py --selftest, which the hook suite now RUNS (it did not when this
        # exemption was written, so the citation was coverage claimed from a suite nothing executed). IF IT EVER TAKES A `<me>`, delete this line.
        "--git",
        # --store prints the tracked store's directory. Reads no item and writes none, exactly like --path: there is no identity for a table row to substitute.
        "--store",
        # --doctor parses the store files and reports conflict markers, torn lines and secret shapes. It never writes, and its subject is the FILES rather than any session's items.
        "--doctor",
        # --import-tmp relocates bytes this machine already had, from the legacy TMPDIR log into the tracked store. It claims no ownership: every item keeps the owner it already carried, which is why it takes no `<me>`.
        "--import-tmp",
        # The catalogue.
        "--help",
        "-h",
        "help",
        # Store-level queries, no identity.
        "--path",
        "--compact",
        # An unfiltered listing of everybody's requests.
        "--requests",
        # Harness hooks; identity is in the event.
        "--session-start",
        "--post-compact",
        # --teammate-idle is the same shape: a harness hook (TeammateIdle) whose whole input is the event on stdin, carrying session_id and agent_id. It takes no argv at all, so a table row would substitute @WHO@ into a slot that does not exist and assert nothing.
        # Its risk is not identity handling (it writes a per-worker telemetry sidecar, never an item) and it is covered where that
        # risk lives: the never-block and always-exit-0 contract, and the 17 controls in test-teammate-idle.py. IF IT EVER TAKES A `<me>`, delete this line.
        "--teammate-idle",
        # --reports is a CONTAINER: its identity-taking sub-modes are driven explicitly as `--reports --read` and `--reports --list --as`, and it is recorded covered by both.
        "--reports",
        # --plan-why is a pure READ of agent/INDEX.md's edge table: what the compacted plan history says about one path. It writes nothing and touches no item, so there is no identity to mismatch. It ACCEPTS a leading prefix and ignores it, purely so a session that has just typed `--plan-compact `<me>` ...` is not answered with a usage error for typing it again. A table row would
        # assert that a foreign `<me>` is REFUSED, which for a read verb would be the wrong behaviour to pin. Its risk is a wrong ANSWER, not a wrong writer, and that is covered where it lives: the both-direction why_lines controls in stop/test-planrec.py. IF IT EVER WRITES ANYTHING, delete this line.
        "--plan-why",
        # --roundlog takes a BRANCH, not an identity: it splices the STATUS block of reports/pr-babysit-<branch>.md, a single-owner document with no per-session sections to protect. A table row would substitute @WHO@ into the branch slot and assert nothing real. It is covered where its risk actually lives instead: 19 splice controls in `wl_roundlog.py --selftest` and 11 guard cases
        # in the hook suite. IF IT EVER TAKES A `<me>`, delete this line: the exemption would then be hiding real identity handling, which is the hole this check exists to keep shut.
        "--roundlog",
    }

    # The derivation's own control. An empty or broken regex would produce an empty `verbs` and this whole case would pass by finding nothing to check, exactly the can't-fail shape it exists to prevent.
    assert {"--add", "--tick", "--ask", "--poll", "--state", "--brief"} <= verbs, (
        "DERIVATION BROKEN: the dispatch scan found %s" % sorted(verbs)
    )
    gap = sorted((verbs - no_me) - l1.covered)
    assert not gap, "UNCOVERED identity-taking verb(s), add a row to the 184 table: %s" % gap


def test_186_meta_control_the_ambient_scrub_really_happened(wl):  # noqa: F811
    """A CHECK ON A CHECK, and it is not redundant.

    Everything above depends on WORKLIST_SESSION_ID being the ONLY identity in the environment. If `wlfix.scrubbed_environ` ever stops stripping CLAUDE_CODE_SESSION_ID, this suite splits in two: run from inside a Claude session every fixture prefix mismatches and about 110 sites refuse, and run in CI the variable is unset, check_me silently passes, and every identity case above
    passes VACUOUSLY. The second is the dangerous one, because it is green.
    """
    scrubbed = wlfix.scrubbed_environ()
    assert "CLAUDE_CODE_SESSION_ID" not in scrubbed, (
        "the scrub left the ambient session id in place"
    )
    assert "CLAUDE_SESSION_ID" not in scrubbed, "the scrub left the ambient session id in place"
    assert wl.env["WORKLIST_SESSION_ID"] == wlfix.SID, "the fixture id is not the pinned one"

    # The probe: drop WORKLIST_SESSION_ID ONLY, then issue a command that would FIRE against any real session id, and require it to PASS. It can only pass if there is no ambient id left to compare against.
    blind = dict(wl.env)
    blind.pop("WORKLIST_SESSION_ID", None)
    got = wl.python(["--add", FOREIGN, "scrub-probe"], env=blind)
    assert got.rc == 0, (
        "an ambient session id leaked past the scrub, so case 184 is measuring the environment rather than the check: %s"
        % both(got)[:200]
    )
    assert "identity mismatch" not in both(got), both(got)[:200]

    # CONTROL: force one back in and the same command must FIRE. Without this, the probe is satisfied by a check that never runs at all.
    forced = dict(blind)
    forced["CLAUDE_CODE_SESSION_ID"] = "beef0000-9999-8888-7777-666666666666"
    got = wl.python(["--add", FOREIGN, "scrub-probe"], env=forced)
    assert got.rc != 0, "CONTROL: CLAUDE_CODE_SESSION_ID is not read at all: %s" % both(got)[:200]
    assert "beef0000" in both(got), both(got)[:200]


def test_184x_a_short_me_that_exactly_matches_an_explicit_declaration_is_honoured(wl):  # noqa: F811
    """REGRESSION, from a defect the floor itself caused.

    Legacy sub-agents tagged items with their NAME rather than a session prefix, and `w2s-en` is 6 characters. The floor refused it even WITH the override declared, and the refusal then advised a rerun with the exact value it had just rejected. An instruction to retry the thing it refused leaves no next move: the listing path was closed, so the only way to see those items was to
    reassign them BLIND, which is the opposite of inspect-then-decide. A capability reachable only by acting blind is not reachable.

    The floor guards against an UNDER-SPECIFIED GUESS about self. An exact match to an explicit declaration is not a guess, so it is honoured, and the three controls below are what keep that from being a loophole.

    The bash placed this case after 186 so that `setup`'s `rm -rf` could not wipe the coverage file case 185 reads. pytest gives every test its own sandbox, so that constraint no longer binds, and the order is kept only so the two files read the same way.
    """
    declared = dict(wl.env, WORKLIST_SESSION_ID="w2s-en")
    got = wl.python(["--add", "w2s-en", "a legacy agent-named item"], env=declared)
    assert got.rc == 0, "the floor still refuses a declared short identity: %s" % both(got)[:200]
    assert "added #" in both(got), both(got)[:200]

    # ... and the path that was actually closed: READING before deciding ownership.
    got = wl.python(["--list", "--open", "w2s-en"], env=declared)
    assert got.rc == 0, "the listing path is still closed: %s" % both(got)[:200]
    assert "a legacy agent-named item" in both(got), both(got)[:200]

    # CONTROL A: one planted fact, no declaration at all. This is the case the floor was built for, and it must still refuse.
    ambient = dict(wl.env)
    ambient.pop("WORKLIST_SESSION_ID", None)
    ambient["CLAUDE_CODE_SESSION_ID"] = "w2s-en-1111-2222"
    got = wl.python(["--add", "w2s-en", "x"], env=ambient)
    assert got.rc != 0, "CONTROL A: the escape swallowed the whole floor: %s" % both(got)[:200]
    assert "shorter than 8 characters" in both(got), both(got)[:200]

    # CONTROL B: a declaration that does not EXACTLY match. A prefix relationship is not enough, which is what makes this an exact-match rule rather than a second way to express the guess the floor exists to refuse.
    near = dict(wl.env, WORKLIST_SESSION_ID="w2s-en-1111-2222")
    got = wl.python(["--add", "w2s-en", "x"], env=near)
    assert got.rc != 0, "CONTROL B: near-enough counted as exact: %s" % both(got)[:200]
    assert "shorter than 8 characters" in both(got), both(got)[:200]

    # CONTROL C: THE PROPERTY THAT MAKES THE ESCAPE SAFE, and nothing else asserts it. --poll and --wait key SIDECAR FILENAMES off `<me>`[:8], so a short prefix there names a different marker than the Stop hook derives from the full session id and silently disables the fast path. Those two carry their own floor, ahead of check_me, and the escape must not reach them.
    got = wl.python(["--poll", "w2s-en"], env=declared)
    assert got.rc != 0, "CONTROL C: a declared short prefix reached the poll marker: %s" % (
        both(got)[:200],
    )
    assert "8-char" in both(got), both(got)[:200]

    proc = subprocess.run(
        [sys.executable, str(wlfix.STOP_DIR / "wl_wait.py"), "w2s-en", "--timeout", "0.01"],
        capture_output=True,
        text=True,
        env=dict(declared, CLAUDE_PROJECT_DIR=str(wl.proj)),
        check=False,
    )
    assert proc.returncode != 0, "CONTROL C: a declared short prefix armed the waiter"
    assert "8-char" in proc.stdout + proc.stderr, (proc.stdout + proc.stderr)[:200]


def test_187_ask_refuses_a_recipient_that_has_never_briefed_here(wl):  # noqa: F811
    """The same defect from the SENDER'S side, and it cost the same incident 34 hours: peers addressed `4c3e095a`, an identity that never existed, and the request sat until it auto-escalated with "recipient silent for 2062min"."""
    wl.brief_now()
    wl.brief_other("cafe1234")
    got = wl.cli("--ask", wlfix.ME, FOREIGN, "into the void")
    assert got.rc != 0, "posted into an inbox nobody reads: %s" % both(got)[:200]
    assert "has never briefed" in both(got), both(got)[:200]
    assert "cafe1234" in both(got), "the refusal did not list who is real: %s" % both(got)[:200]

    # CONTROL A: one planted fact, the recipient HAS briefed.
    got = wl.cli("--ask", wlfix.ME, "cafe1234", "a real recipient")
    assert got.rc == 0, "CONTROL A: the check refused a real session: %s" % both(got)[:200]
    assert "request #" in both(got), both(got)[:200]

    # CONTROL B: '*' and 'operator' are not roster entries and never will be.
    assert wl.cli("--ask", wlfix.ME, "*", "broadcast").rc == 0, (
        "CONTROL B: the roster check swallowed a broadcast"
    )
    assert (
        wl.cli("--ask", wlfix.ME, "operator", "a question DEFAULT: proceed as planned").rc == 0
    ), "CONTROL B: the roster check swallowed an operator ask"


def test_187_control_c_with_an_empty_roster_the_check_abstains(wl):  # noqa: F811
    """CONTROL C: the INSTRUMENT BLIND. An empty roster means the check has no data (a fresh worktree, a wiped TMPDIR) and refusing every ask there would break the mechanism exactly where nothing is wrong."""
    got = wl.cli("--ask", wlfix.ME, "nobody99", "no roster at all")
    assert got.rc == 0, "an empty roster refused every ask: %s" % both(got)[:200]
    assert "request #" in both(got), both(got)[:200]


def test_188_operator_is_exempt_and_the_exemption_is_narrow(wl):  # noqa: F811
    """The stop report prints `worklist.py --answer operator <id> '<words>'` for the HUMAN, who runs it in whatever shell is open, and if that is a Claude session's Bash the identity check would refuse the one command the mail exists to get run. "operator" is a name, not a session prefix, and was never verifiable."""
    wl.brief_now()
    wl.brief_other("cafe1234")
    rid = wl.askid_as("cafe1234", "cafe1234", wlfix.ME, "for the operator to answer")
    assert rid, "FIXTURE BROKEN: no request was posted"
    got = wl.cli("--answer", "operator", rid, "the human's answer")
    assert got.rc == 0, "the identity check broke the operator's reply path: %s" % both(got)[:200]
    assert "answered #" in both(got), both(got)[:200]

    # CONTROL: the exemption is ONE literal, not "any non-session word".
    got = wl.cli("--answer", "operator2", rid, "an impostor")
    assert got.rc != 0, "CONTROL: the exemption is wider than one literal: %s" % both(got)[:200]
    assert "identity mismatch" in both(got), both(got)[:200]


def test_189_an_identity_that_writes_here_and_has_never_stopped_is_reported(wl):  # noqa: F811
    """v19 L2: the backstop for what L1 cannot reach, history already written, and the deliberate silent-pass where the environment cannot name the caller. The signature is exact and binary: `.lastevent-<prefix>.json` is written at exactly ONE place (run_stop), so no file means no Stop hook has ever run under that identity, and a real session always stops."""
    wl.brief_now()
    wl.hand_now()
    wl.say("all done, nothing outstanding")
    wl.run()  # one real stop, so a .lastevent-deadbeef.json exists
    wl.phantom_store("phantom1", 90)
    wl.newturn()
    wl.say("all done, nothing outstanding")
    got = wl.run()
    assert "PHANTOM IDENTITY IN THE STORE" in got.out, "no phantom section: %s" % got.out[:400]
    assert "phantom1" in got.out, got.out[:400]
    assert "--reassign deadbeef" in got.out, "the exact repair verb is missing: %s" % got.out[:400]
    assert '"decision": "block"' not in got.out, (
        "the phantom report blocked a stop it is not this session's job to fix"
    )


def test_189a_control_a_lastevent_file_means_it_did_stop_so_it_is_a_real_session(wl):  # noqa: F811
    """CONTROL: one planted fact, the `.lastevent-` file, and it goes silent."""
    wl.brief_now()
    wl.hand_now()
    wl.say("all done, nothing outstanding")
    wl.run()
    wl.phantom_store("phantom1", 90)
    wl.stem(".lastevent-phantom1.json").write_text('{"session_id":"phantom1-x"}', encoding="utf-8")
    wl.newturn()
    wl.say("all done, nothing outstanding")
    got = wl.run()
    assert "PHANTOM IDENTITY" not in got.out, (
        "flagged an identity that has stopped: %s" % got.out[:300]
    )


def test_189b_control_a_brand_new_session_writes_before_its_first_stop(wl):  # noqa: F811
    """CONTROL: a 2-minute-old writer is not yet a phantom, because it has not had time to stop."""
    wl.brief_now()
    wl.hand_now()
    wl.say("all done, nothing outstanding")
    wl.run()
    wl.phantom_store("phantom1", 2)  # younger than WORKLIST_PHANTOM_MIN (30)
    wl.newturn()
    wl.say("all done, nothing outstanding")
    got = wl.run()
    assert "PHANTOM IDENTITY" not in got.out, (
        "accused a session that has not had time to stop: %s" % got.out[:300]
    )


def test_189c_control_a_phantom_that_owns_nothing_is_not_worth_a_word(wl):  # noqa: F811
    """This is the gate that keeps real test residue in the operator's live store silent."""
    wl.brief_now()
    wl.hand_now()
    wl.say("all done, nothing outstanding")
    wl.run()
    wl.phantom_store("phantom1", 90)

    # Tick every phantom-owned item: it still WROTE the events, it just owns nothing open. READS the whole store, WRITES to the legacy log, which the reader still unions. Those must be two different paths: the bash used a process substitution, a read-only pipe, and appending to it wrote into a pipe nobody read, so the ticks silently did not happen.
    ids = [
        json.loads(line)["id"]
        for line in wl.wl_events().splitlines()
        if line.strip() and json.loads(line).get("by") == "phantom1"
    ]
    assert ids, "FIXTURE BROKEN: no phantom-owned events to tick"
    # NOW, not a constant. The store reader sorts by timestamp before folding, which is what makes a union of two machines' histories correct, so a tick dated in the past folds BEFORE the add it is meant to close and has no effect. Append order stopped being fold order the day the store became a directory.
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with wl.events.open("a", encoding="utf-8") as handle:
        for ident in ids:
            handle.write(
                json.dumps(
                    {
                        "ev": "state",
                        "id": ident,
                        "at": stamp,
                        "by": "phantom1",
                        "s": "x",
                        "note": "done",
                    }
                )
                + "\n"
            )
    wl.newturn()
    wl.say("all done, nothing outstanding")
    got = wl.run()
    assert "PHANTOM IDENTITY" not in got.out, (
        "flagged an identity with nothing outstanding: %s" % got.out[:300]
    )


def test_189d_control_with_zero_lastevent_files_the_check_says_it_is_blind(wl):  # noqa: F811
    """Asserting silence here would be indistinguishable from the check not running.

    With no `.lastevent-*` anywhere the signature cannot discriminate, since it recognises a phantom by the ABSENCE of one, and it would indict every identity at once, so it must report the blindness in words and flag nobody. Case 189e is its control: same call, one file present, and the phantom is named.
    """
    wl.brief_now()
    wl.hand_now()
    wl.phantom_store("phantom1", 90)
    for path in wl.wl.parent.glob("*.lastevent-*.json"):
        path.unlink()
    out = probe_phantom(wl)
    assert out.startswith("BLIND:"), "a blind check answered anyway: %s" % out[:300]
    assert "is BLIND this stop" in out, out[:300]


def test_189e_control_for_189d_one_lastevent_file_and_the_same_call_flags(wl):  # noqa: F811
    """Without this, 189d is satisfied by a function that never looks at anything.

    The bash reused 189d's world directly; here the identical fixture is rebuilt, because pytest gives each test its own sandbox, and the ONE planted fact that differs from 189d is still the single `.lastevent-` file.
    """
    wl.brief_now()
    wl.hand_now()
    wl.phantom_store("phantom1", 90)
    for path in wl.wl.parent.glob("*.lastevent-*.json"):
        path.unlink()
    wl.stem(".lastevent-deadbeef.json").write_text('{"session_id":"deadbeef-x"}', encoding="utf-8")
    out = probe_phantom(wl)
    assert out == "FLAGGED: phantom1", (
        "the probe cannot flag at all, so 189d proves nothing: %s" % out[:300]
    )


def test_190_reassign_moves_the_open_work_and_leaves_the_history_alone(wl):  # noqa: F811
    """v19 L3. BEFORE AND AFTER in one run. The before-assert is the control: without it the test passes on a store that already contained the item and the request."""
    wl.brief_now()
    wl.hand_now()
    wl.say("all done, nothing outstanding")
    wl.run()
    wl.phantom_store("phantom1", 90)
    # A request the phantom sent, and one sent TO it. The incident's real damage was in .requests, so a repair that leaves those unreachable fixes the symptom nobody complained about and skips the one they did.
    wl.brief_other("phantom1")
    sent = wl.askid_as("phantom1", "phantom1", wlfix.ME, "the message that was lost")
    assert sent, "FIXTURE BROKEN: the phantom's own request was never posted"
    wl.brief_other("cafe1234")
    prid_to = wl.askid_as("cafe1234", "cafe1234", "phantom1", "a question nobody read")
    assert prid_to, "FIXTURE BROKEN: the request TO the phantom was never posted"

    before_list = both(wl.cli("--list", "--open", wlfix.ME))
    before_poll = both(wl.cli("--poll", wlfix.ME))
    assert "phantom-owned item" not in before_list, (
        "BEFORE: the fixture already showed the items, so the after-assert proves nothing"
    )
    assert prid_to not in before_poll, (
        "BEFORE: the fixture already showed the request, so the after-assert proves nothing"
    )

    got = wl.cli("--reassign", wlfix.ME, "phantom1")
    assert got.rc == 0, "--reassign failed: %s" % both(got)[:300]
    assert "reassigned phantom1 -> deadbeef" in both(got), both(got)[:300]

    after_list = both(wl.cli("--list", "--open", wlfix.ME))
    after_poll = both(wl.cli("--poll", wlfix.ME))
    assert "phantom-owned item" in after_list, "the items did not move: %s" % after_list[:300]
    assert prid_to in after_poll, "the lost request is still unreachable: %s" % after_poll[:300]

    # The history must still say the phantom wrote them. A tidy log that lies about who did what is worse than an untidy one.
    events = wl.wl_events()
    assert '"by": "phantom1"' in events or '"by":"phantom1"' in events, (
        "--reassign rewrote history instead of appending to it"
    )


def test_190b_control_reassign_refuses_a_peer_that_is_fresh_but_never_stopped(wl):  # noqa: F811
    """THE REVIEW FINDING THIS PINS (medium, PR #551).

    The `.lastevent-` guard alone does not deliver the guarantee the docstring claims. That file is written at a session's FIRST STOP, so a peer that has added items and not yet stopped has no file either and is indistinguishable from a genuine phantom. Any session can read a peer's prefix out of `--list --open`, and concurrent sessions in one tree are routine here, so without an
    age gate a peer's OPEN items and request routing could be moved onto the caller WHILE that peer was working on them.

    Case 190 ages its target 90 minutes and 190a's target has already stopped; NEITHER covers a merely-fresh, still-working target, so the untested path was the vulnerable one.
    """
    wl.brief_now()
    wl.hand_now()
    wl.say("all done, nothing outstanding")
    wl.run()
    # 2 minutes old and NO .lastevent- file: exactly the mid-first-turn peer.
    wl.phantom_store("fresh999", 2)
    got = wl.cli("--reassign", wlfix.ME, "fresh999")
    assert got.rc != 0, "took over a live peer's work: %s" % both(got)[:300]
    assert "mid-turn" in both(got), both(got)[:300]


def test_190b_control_the_same_prefix_aged_past_the_floor_still_reassigns(wl):  # noqa: F811
    """CONTROL ON THE CONTROL: the SAME prefix, aged past the floor, still moves, so the case above proves an age gate and not a blanket refusal."""
    wl.brief_now()
    wl.hand_now()
    wl.say("all done, nothing outstanding")
    wl.run()
    wl.phantom_store("fresh999", 90)
    got = wl.cli("--reassign", wlfix.ME, "fresh999")
    assert got.rc == 0, "the age gate refuses even a real phantom: %s" % both(got)[:300]
    assert "reassigned fresh999" in both(got), both(got)[:300]


def test_190c_lease_release_accepts_the_hash_this_tools_own_output_prints(wl):  # noqa: F811
    """REVIEW FINDING, PR #551: the release branch read argv[2] raw while every other verb goes through the `.lstrip("#")` at the top of _item_cli.

    So an id copied straight from this tool's OWN output, which prints ids as `#abc123`, appended an unlease event matching nothing, printed "released ##abc123", and left the item `[>]`. A verb that reports success while changing nothing is precisely what this suite exists to catch, and it shipped inside the fix for a different silent no-op.
    """
    wl.brief_now()
    wl.hand_now()
    wl.say("all done, nothing outstanding")
    wl.run()
    rid = added_id(wl.cli("--add", wlfix.ME, "item for the hash-prefix release case").out)
    assert rid, "FIXTURE BROKEN: --add printed no id"
    wl.cli("--lease", wlfix.ME, rid, "+30", "worker:probe-worker", "riding a probe")
    got = wl.cli("--lease", wlfix.ME, "#" + rid, "release", "released with the hash form")
    assert "released #%s" % rid in both(got), "the # form was mangled: %s" % both(got)[:200]
    assert "##%s" % rid not in both(got), "the # form was mangled: %s" % both(got)[:200]

    listing = both(wl.cli("--list", "--open", wlfix.ME))
    found = re.search(r"- \[.\] #%s" % rid, listing)
    assert found, "reported success but the item is not in the open listing at all"
    assert found.group(0) == "- [ ] #%s" % rid, (
        "reported success but the state is %r" % found.group(0)
    )

    # CONTROL: the bare form must keep working, so the fix is a widening and not a swap.
    wl.cli("--lease", wlfix.ME, rid, "+30", "worker:probe-worker", "riding again")
    wl.cli("--lease", wlfix.ME, rid, "release", "released with the bare form")
    listing = both(wl.cli("--list", "--open", wlfix.ME))
    found = re.search(r"- \[.\] #%s" % rid, listing)
    assert found, "CONTROL: the bare form left no open row at all"
    assert found.group(0) == "- [ ] #%s" % rid, "CONTROL: the bare form broke: %r" % found.group(0)


def test_190a_control_reassign_refuses_a_session_that_has_stopped(wl):  # noqa: F811
    """The rule that stops this verb becoming a way to steal a live peer's items."""
    wl.brief_now()
    wl.hand_now()
    wl.say("all done, nothing outstanding")
    wl.run()
    wl.phantom_store("cafe1234", 90)
    wl.stem(".lastevent-cafe1234.json").write_text('{"session_id":"cafe1234-x"}', encoding="utf-8")
    got = wl.cli("--reassign", wlfix.ME, "cafe1234")
    assert got.rc != 0, "took over a live session's work: %s" % both(got)[:300]
    assert "it is a real session" in both(got), both(got)[:300]

    # And `<me>` itself faces the same identity check, so work cannot be reassigned TO a fiction, which would make the problem worse.
    got = wl.cli("--reassign", FOREIGN, "phantom1")
    assert got.rc != 0, "--reassign accepted a foreign `<me>`: %s" % both(got)[:200]
    assert "identity mismatch" in both(got), both(got)[:200]


def test_190b_reassign_survives_a_compaction_which_erases_every_writer_name(wl):  # noqa: F811
    """THE DEFECT, measured on the operator's live store on 2026-09-04.

    compact() re-emits the whole fold through snapshot_events(by="compact"), so after any compaction NO event carries its original writer any more, only the owner survives. Both readers of "which identities does this store know about" (the phantom backstop, and this verb's own age gate) scanned `by` alone, while the code that actually moves the work, three statements further down,
    selects on `owner`. So on a compacted store --reassign refused with "has written no events at all" about items it could see perfectly well, and --tick refused the same items as another session's. Three real items sat in the operator's worklist unreachable through EVERY sanctioned verb at once, reported as open work on every stop, with hand-editing the store the only way out,
    which the standing rules forbid, correctly, because the store is shared.

    Compaction is automatic, so this was not an edge case: it is the state every store reaches. Case 190 above cannot catch it, because its fixture has never been compacted.
    """
    wl.brief_now()
    wl.hand_now()
    wl.say("all done, nothing outstanding")
    wl.run()
    wl.phantom_store("phantom1", 90)
    wl.cli("--compact")

    # CONTROL FIRST, and it is what makes the assert below mean anything: prove the compaction really did erase the writer. Without this the case would pass on a store where `by` still said phantom1, which is the pre-compaction shape it is supposed to be testing, and the bug would sail straight through it.
    events = wl.wl_events()
    assert '"o":"phantom1"' in events, (
        "the store is not in the post-compaction shape, so this proves nothing"
    )
    assert '"by":"phantom1"' not in events, (
        "the store is not in the post-compaction shape, so this proves nothing"
    )

    got = wl.cli("--reassign", wlfix.ME, "phantom1")
    assert got.rc == 0, "--reassign went blind after a compaction: %s" % both(got)[:300]
    assert "reassigned phantom1 -> deadbeef" in both(got), both(got)[:300]
    assert "phantom-owned item" in both(wl.cli("--list", "--open", wlfix.ME)), (
        "--reassign reported success but moved nothing"
    )
