"""The `--triage` verb (refusals, degradation, judge path), the plan-file demand, plan listing, and the allow-report diet.

Ported from `.claude/hooks/stop/worklist-cases/16-triage-and-plans.sh`, one pytest function per numbered bash case, and one more wherever a bash block called `setup` again mid-case.

v16 IS THE FIX-IN-SESSION RULE, and these cases are its machinery. A finding is fixed by the session that finds it, so `--triage` answers the size question and hands back the exact next command, `--tick` refuses a completion whose only evidence is an issue reference, and `agent/PLAN-*.md` becomes a durable design record the SessionStart and PostCompact hooks hand back. Every FIRE
case is paired with a SILENT control differing by one planted fact.
"""

from __future__ import annotations

import json
import re
import shutil
import stat
import time

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401


def triage(fix, mode: str, *argv: str, as_peer: str = "") -> wlfix.Result:
    """The `--triage` verb with the judge pinned, which is what the bash helper of this name did.

    LOCAL to this module: `wl.cli` drives the CLI with the fixture environment as it stands, and this verb needs two things on top of it, the shim `claude` on PATH and WORKLIST_JUDGE set per call, because cases 164 to 166 exercise the DEGRADED path and case 167 the judge path from the same fixture.
    """
    env = dict(fix.env)
    env["PATH"] = "%s:%s" % (fix.base / "binonly", fix.env.get("PATH", ""))
    env["WORKLIST_JUDGE"] = mode
    if as_peer:
        env["WORKLIST_SESSION_ID"] = wlfix.peer_id(as_peer)
    return fix.python(["--triage", *argv], env=env)


def shim_judge_out(fix, structured_output: dict) -> None:
    """A canned `claude` serving that exact structured output, plus a CALL COUNTER.

    LOCAL for the same reason it is local to the guide module: `wl.shim_judge` hard-codes the stop verdict and writes no counter, and case 167 needs both a chosen verdict and the number of times the judge was paid.
    """
    payload = {"is_error": False, "structured_output": structured_output}
    body = "#!/bin/bash\necho x >> %s\necho %s\n" % (
        json.dumps(str(fix.base / "judgecalls")),
        json.dumps(json.dumps(payload)),
    )
    script = fix.base / "binonly" / "claude"
    script.write_text(body, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)


def judge_calls(fix) -> int:
    """How many times the shim was invoked."""
    path = fix.base / "judgecalls"
    if not path.is_file():
        return 0
    return len([line for line in path.read_text(encoding="utf-8").splitlines() if line])


def added_id(result: wlfix.Result) -> str:
    """The item id `--add` printed."""
    found = re.search(r"^added #([0-9a-f]+)", result.out, re.MULTILINE)
    assert found, "--add printed no item id: %r" % result.out[:200]
    return found.group(1)


def plan(fix, name: str, body: str) -> None:
    """One `agent/PLAN-<name>.md` in the fixture repo."""
    (fix.proj / "agent").mkdir(parents=True, exist_ok=True)
    (fix.proj / "agent" / ("PLAN-%s.md" % name)).write_text(body, encoding="utf-8")


def session_start(fix) -> wlfix.Result:
    """The SessionStart context hook, fed the event the harness feeds it."""
    payload = json.dumps({"session_id": fix.sid, "cwd": str(fix.proj)})
    return fix.cli("--session-start", stdin=payload)


def test_164_triage_refuses_an_empty_finding_and_appends_no_event(wl):  # noqa: F811
    """A rejected write is not a delivered one, so neither refusal may leave an event behind."""
    empty = triage(wl, "off", "deadbeef")
    merged = empty.out + empty.err
    assert empty.rc != 0, "empty --triage was accepted (rc=%d): %s" % (empty.rc, merged[:200])
    assert "usage:" in merged, "no usage on an empty --triage: %s" % merged[:200]

    blank = triage(wl, "off", "deadbeef", "   ")
    merged = blank.out + blank.err
    assert blank.rc != 0, "blank-text --triage was accepted (rc=%d): %s" % (blank.rc, merged[:200])
    assert "empty finding triages nothing" in merged, (
        "the blank refusal did not name why: %s" % merged[:200]
    )

    assert not wl.wl_events(), "a refused triage still wrote an event: %s" % wl.wl_events()[:200]

    # CONTROL: the same verb WITH a finding does append, so the assertion above could have failed. Without this the no-event check passes on a dead verb.
    triage(wl, "off", "deadbeef", "the retry loop swallows the exit code")
    events = wl.wl_events()
    assert events, "164 CONTROL: the verb appends nothing at all"
    assert '"ev":"add"' in events, "164 CONTROL: no add event: %s" % events[:200]


def test_165_triage_degrades_to_a_self_assessment_and_claims_no_verdict(wl):  # noqa: F811
    """With no judge reachable the verb hands back all three recipes and tracks the finding, but records no verdict it did not produce."""
    got = triage(wl, "off", "deadbeef", "the fork path copies .env into the child repo")
    merged = got.out + got.err
    assert got.rc == 0, "degraded triage wrong (rc=%d): %s" % (got.rc, merged[:300])
    for needle in ("INLINE", "PLAN+SUBAGENT", "OPERATOR-ONLY", "agent/plans/PLAN-<slug>.md"):
        assert needle in merged, "degraded triage is missing %r: %s" % (needle, merged[:300])

    events = wl.wl_events()
    assert '"ev":"add"' in events, "the degraded triage tracked nothing: %s" % events[:200]
    assert '"ev":"triage"' not in events, (
        "165 CONTROL: degraded mode recorded a verdict: %s" % events[:200]
    )


def test_166_triage_id_refuses_another_sessions_item(wl):  # noqa: F811
    """Ownership, not brokenness: the same item triaged by its OWNER reaches the degraded printout."""
    theirs = wl.cli_as("other123", "--add", "other123", "their finding")
    nid = added_id(theirs)

    got = triage(wl, "off", "deadbeef", "--id", nid, "my take on their finding")
    merged = got.out + got.err
    assert got.rc != 0, "cross-session triage was accepted (rc=%d): %s" % (got.rc, merged[:200])
    assert "is owned by other123" in merged, "the refusal did not name the owner: %s" % merged[:200]
    assert '"ev":"triage"' not in wl.wl_events(), (
        "166 CONTROL: a refused triage still recorded a verdict: %s" % wl.wl_events()[:200]
    )

    owner = triage(wl, "off", "other123", "--id", nid, "their own finding", as_peer="other123")
    merged = owner.out + owner.err
    assert owner.rc == 0, "166 CONTROL: --id is broken for the owner too (rc=%d)" % owner.rc
    assert "TRIAGE, SELF-ASSESSED (#%s)" % nid in merged, (
        "166 CONTROL: the owner's triage printed nothing usable: %s" % merged[:200]
    )


def test_167_the_triage_judge_path_records_its_verdict_and_spends_one_call(wl):  # noqa: F811
    """A plan-subagent verdict prints the prefilled plan path and the recipe, records both, and pays the judge exactly once (no retry loop, no double spend)."""
    (wl.base / "judgecalls").write_text("", encoding="utf-8")
    shim_judge_out(wl, {"verdict": "plan-subagent", "reason": "multi-file", "plan_slug": "fix-x"})
    got = triage(wl, "on", "deadbeef", "renet forks inherit the parent buildkit session")
    merged = got.out + got.err
    assert got.rc == 0, "plan-subagent recipe wrong (rc=%d): %s" % (got.rc, merged[:300])
    assert "PLAN+SUBAGENT" in merged, "no recipe: %s" % merged[:300]
    assert "agent/plans/PLAN-fix-x.md" in merged, "no prefilled plan path: %s" % merged[:300]

    events = wl.wl_events()
    for needle in ('"ev":"triage"', '"v":"plan-subagent"', '"plan":"agent/plans/PLAN-fix-x.md"'):
        assert needle in events, "triage event missing %r: %s" % (needle, events[-300:])

    assert judge_calls(wl) == 1, "judge called %d times" % judge_calls(wl)


def test_167_control_an_inline_verdict_orders_the_fix_now_and_records_no_plan(wl):  # noqa: F811
    """CONTROL: one different verdict from the same shim takes the other branch."""
    (wl.base / "judgecalls").write_text("", encoding="utf-8")
    shim_judge_out(wl, {"verdict": "inline", "reason": "one line and one check", "plan_slug": ""})
    got = triage(wl, "on", "deadbeef", "the error message names the wrong flag")
    merged = got.out + got.err
    found = re.search(r"^triaging #([0-9a-f]+)", merged, re.MULTILINE)
    assert found, "167 CONTROL: the verb printed no item id: %s" % merged[:300]
    tid = found.group(1)
    assert "TRIAGE VERDICT: INLINE" in merged, "167 CONTROL: no inline verdict: %s" % merged[:300]
    assert "--tick deadbeef %s" % tid in merged, (
        "167 CONTROL: the inline branch did not order the tick: %s" % merged[:300]
    )
    events = wl.wl_events()
    assert '"v":"inline"' in events, "167 CONTROL: the verdict went unrecorded: %s" % events[-300:]
    assert '"plan":' not in events, (
        "167 CONTROL: an inline verdict recorded a plan: %s" % events[-300:]
    )


def test_168_a_triaged_big_item_with_no_plan_file_on_disk_is_demanded(wl):  # noqa: F811
    """A big finding whose design was never written is demanded, with both exits named, and writing the plan silences the demand and advertises the path."""
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with wl.events.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "ev": "add",
                    "id": "deadbee1",
                    "at": now,
                    "by": "deadbeef",
                    "s": " ",
                    "o": "deadbeef",
                    "t": "forks leak the parent secrets",
                }
            )
            + "\n"
        )
        handle.write(
            json.dumps(
                {
                    "ev": "triage",
                    "id": "deadbee1",
                    "at": now,
                    "by": "deadbeef",
                    "v": "plan-subagent",
                    "reason": "multi-file",
                    "plan": "agent/PLAN-big.md",
                }
            )
            + "\n"
        )

    demanded = wl.cli("--list", "--open", "deadbeef")
    merged = demanded.out + demanded.err
    assert "TRIAGED BIG, plan file missing: agent/PLAN-big.md" in merged, (
        "the plan follow-through never fired: %s" % merged[:300]
    )
    assert "--triage deadbeef --id deadbee1" in merged, (
        "the demand carries no re-triage exit: %s" % merged[:300]
    )

    plan(wl, "big", "# PLAN: big\nStatus: draft\nOwner: t\nUpdated: 2026-07-31\n")
    silenced = wl.cli("--list", "--open", "deadbeef")
    merged = silenced.out + silenced.err
    assert "TRIAGED BIG" not in merged, (
        "168 CONTROL: the probe does not read the disk: %s" % merged[:300]
    )
    assert "plan: agent/PLAN-big.md" in merged, (
        "168 CONTROL: the path is not advertised: %s" % merged[:300]
    )


def test_169_tick_refuses_evidence_that_is_only_an_issue_reference(wl):  # noqa: F811
    """A bare issue URL cannot close a finding, and the refusal names all three doors; the SAME evidence naming its door is accepted, because the door is the exit.

    The gate is narrow, and the regression controls are what keep it narrow: ordinary evidence still ticks, and a URL that is not an issue reference must keep working, because the gate rides on the URL shape completion_evidence already accepts.
    """
    wl.reg_repo()
    head = wl.git("rev-parse", "HEAD").stdout.strip()
    assert head, "FIXTURE BROKEN: the fixture repo has no HEAD"
    nid = added_id(wl.cli("--add", "deadbeef", "the retry loop swallows the exit code"))

    bare = wl.cli("--tick", "deadbeef", nid, "filed as https://github.com/x/y/issues/560")
    merged = bare.out + bare.err
    assert bare.rc != 0, "the bare-issue tick was accepted (rc=%d): %s" % (bare.rc, merged[:300])
    for door in ("door:operator-only", "door:operator-deferred", "door:no-write-access"):
        assert door in merged, "the refusal does not name %s: %s" % (door, merged[:300])
    assert '"ev":"state"' not in wl.wl_events(), (
        "a refused tick still closed the item: %s" % wl.wl_events()[:200]
    )

    doored = wl.cli(
        "--tick",
        "deadbeef",
        nid,
        "filed as https://github.com/x/y/issues/560 door:no-write-access, that repo is not writable here",
    )
    assert doored.rc == 0, "a door-carrying tick was refused: %s" % (doored.out + doored.err)[:300]
    assert '"ev":"state"' in wl.wl_events(), "the door-carrying tick closed nothing"

    second = added_id(wl.cli("--add", "deadbeef", "second finding"))
    exit_code = wl.cli("--tick", "deadbeef", second, "ran the suite, exit 0")
    third = added_id(wl.cli("--add", "deadbeef", "third finding"))
    run_url = wl.cli(
        "--tick",
        "deadbeef",
        third,
        "green on https://github.com/rediacc/console/actions/runs/123456789",
    )
    fourth = added_id(wl.cli("--add", "deadbeef", "fourth finding"))
    verified_sha = wl.cli("--tick", "deadbeef", fourth, "fixed in %s" % head)
    assert (exit_code.rc, run_url.rc, verified_sha.rc) == (0, 0, 0), (
        "169 CONTROLS: the door gate is too wide (rc=%d/%d/%d): %s | %s | %s"
        % (
            exit_code.rc,
            run_url.rc,
            verified_sha.rc,
            (exit_code.out + exit_code.err)[:100],
            (run_url.out + run_url.err)[:100],
            (verified_sha.out + verified_sha.err)[:100],
        )
    )


def test_170_session_start_lists_non_done_plans_with_no_design_docs_dir(wl):  # noqa: F811
    """Draft plans are listed, executed ones collapse to a count, and a plan with no readable Status line surfaces LOUDLY as UNKNOWN.

    THE CONTROL ON THE RESTRUCTURE: a design-docs directory does not exist in this fixture, and the old code RETURNED EARLY on that, which would have eaten the plans block entirely. The design-docs prose must be absent and the plans block present in the SAME output.
    """
    plan(wl, "a", "# PLAN: a\nStatus: draft\nOwner: t\nUpdated: 2026-07-31\n\nbody\n")
    plan(wl, "b", "# PLAN: b\nStatus: done\nOwner: t\nUpdated: 2026-07-31\n\nbody\n")
    plan(wl, "c", "# PLAN: c\nOwner: t\nUpdated: 2026-07-31\n\nbody\n")
    got = session_start(wl)
    out = got.out
    assert "agent/PLAN-a.md [draft]" in out, "the plans listing is wrong: %s" % out[:400]
    assert "PLAN-b.md" not in out, "an executed plan was listed: %s" % out[:400]
    assert "1 done or superseded plan(s)" in out, "no collapsed count: %s" % out[:400]
    assert "agent/PLAN-c.md [UNKNOWN]" in out, "an unparseable Status was hidden: %s" % out[:400]
    assert "READ ALL OF THEM" not in out, (
        "170 CONTROL: the two blocks are still coupled: %s" % out[:400]
    )
    assert "READ EVERY NON-DONE PLAN" in out, (
        "170 CONTROL: the plans block was eaten: %s" % out[:400]
    )

    # And the reverse: with NEITHER, SessionStart stays silent as it always did. The plans left the docs tree when it moved, so removing that directory alone no longer removes them, and this control would then fail for the right reason.
    shutil.rmtree(wl.proj / "docs", ignore_errors=True)
    for stale in (wl.proj / "agent").glob("PLAN-*.md"):
        stale.unlink()
    silent = session_start(wl)
    assert not silent.out.strip(), (
        "170 CONTROL: SessionStart now talks about nothing: %s" % silent.out[:200]
    )


def test_171_post_compact_hands_back_the_executing_plans_status_cursor(wl):  # noqa: F811
    """The compacted session gets the plan listing AND the executing plan's cursor, and only that section: a done plan is never handed back and the excerpt is bounded."""
    wl.hand_now()
    plan(
        wl,
        "exec",
        "# PLAN: exec\nStatus: executing\nOwner: t\nUpdated: 2026-07-31\n\n## Status\n\n"
        "MARKER_EXEC_CURSOR wave two landed, wave three is next.\n\n## Detail\n\nnot the cursor\n",
    )
    plan(
        wl,
        "old",
        "# PLAN: old\nStatus: done\nOwner: t\nUpdated: 2026-07-31\n\n## Status\n\n"
        "MARKER_DONE_PLAN must never be handed back.\n",
    )
    got = wl.post_compact()
    out = got.out
    assert "MARKER_EXEC_CURSOR" in out, "PostCompact plan excerpt missing: %s" % out[:400]
    assert "PLAN-exec.md [executing]" in out, "no plan listing: %s" % out[:400]
    assert "picking up an in-progress session" in out, "no handback framing: %s" % out[:400]
    assert "MARKER_DONE_PLAN" not in out, "171 CONTROL: a done plan was handed back: %s" % out[:400]
    assert "not the cursor" not in out, "171 CONTROL: the excerpt is unbounded: %s" % out[:400]


def test_172_allow_report_diet_the_guide_is_the_single_source_and_advisories_latch(wl):  # noqa: F811
    """Operator, 2026-07-31, on an allow report that had grown large although round robin was already in place.

    The allow report's in-flight section duplicated the guide's own in-flight rows, and week-stable advisories (other sessions' briefs) repeated on every full stop. Now the guide says it once, and slow-moving sections re-show only on content change or after the refresh window.
    """
    # The default two-cron shape also produces a poll-backoff tip, which is another class-2 section; the fixed 3-per-stop budget already covers both, and the per-stop rationing has its own cases in the report-queue module.
    wl.brief_now()
    wl.hand_now()
    iid = added_id(wl.cli("--add", "deadbeef", "carry the CI watch to green"))
    wl.cli("--lease", "deadbeef", iid, "+60", "worker:bw7", "watching the run")
    wl.bg = json.dumps(
        [{"id": "bw7", "type": "shell", "status": "running", "description": "the watch"}]
    )
    with wl.sessions.open("a", encoding="utf-8") as handle:
        handle.write(
            "cafebabe %s building the fixture\n"
            % time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        )
    said = "watching.\n\n## Remaining\n- #%s carry the CI watch to green (in flight)" % iid
    wl.say(said)
    got = wl.run()
    label = "172: the guide carries the lease once; the duplicate section is gone"
    assert "- [>] #%s" % iid in got.out, "%s: %s" % (label, got.out[:400])
    wl.check_quiet("in flight on background work", label, result=got)
    assert "Other sessions in this worktree" in got.out, (
        "172: first sight of the other session was hidden: %s" % got.out[:400]
    )

    wl.newturn()
    wl.cli("--update", "deadbeef", iid, "still watching, run pending")
    wl.say(said)
    wl.check_quiet(
        "Other sessions in this worktree",
        "172: the advisory repeated with unchanged content",
    )

    # CONTROL: changed content re-shows immediately, so the latch is a dedupe rather than a mute.
    with wl.sessions.open("a", encoding="utf-8") as handle:
        handle.write(
            "cafebabe %s pivoted to the deploy fix\n"
            % time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        )
    wl.newturn()
    wl.cli("--update", "deadbeef", iid, "watch still healthy")
    wl.say(said)
    changed = wl.run()
    label = "172 CONTROL: the latch muted a real change"
    assert "Other sessions in this worktree" in changed.out, "%s: %s" % (label, changed.out[:400])
    assert "pivoted to the deploy fix" in changed.out, "%s: %s" % (label, changed.out[:400])
