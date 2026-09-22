"""Handoff checklists: zero overhead when absent, missing deliverables, foreign and door-parked waves, ticks, statuses, the shape gate.

Ported from `.claude/hooks/stop/worklist-cases/19-checklists.sh`, one pytest function per numbered bash case, except where a bash leg continued its predecessor's world with no fresh `setup`: those legs stay inside one function, where the sequence is visible in one place.

193-203 pin the v20 /handoff checklist gate (agent/programs/<slug>/CHECKLIST.md). THE GAP THEY PIN: /handoff wrote a design suite and then TOLD the next session, in prose inside PROMPT.md, to seed the worklist. Prose gates nothing, so a handoff whose PROMPT.md was ignored or compacted away dropped program work silently. CHECKLIST.md is the machine-readable half, and its two halves
are enforced by DIFFERENT means: deliverables are FILE-VERIFIED (the tick is bookkeeping, the file is the truth) while waves are tick-on-trust with store linkage through the `cl:<slug>/<wN>` token. Every case below is paired with a clean-fixture control, because a gate nobody has watched stay silent is a gate nobody knows fires for the right reason.

The bash file closes with a commentary block for cases 204-206, which live in `20-advisories-rotation.sh` and are ported beside them, not here.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

# --- the checklist bodies the cases plant -----------------------------------

CL_PRODUCING_MINE = """# Handoff checklist: demo
Status: producing
Owner: deadbeef

## Deliverables
- [ ] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
"""

CL_PRODUCING_FOREIGN = CL_PRODUCING_MINE.replace("Owner: deadbeef", "Owner: cafe0000")

CL_EXECUTING = """# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
"""

CL_EXECUTING_SECRETS = """# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: set the production secrets and cut over
"""

CL_EXECUTING_ALL_TICKED = """# Handoff checklist: demo
Status: executing

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [x] w1 Wave A: wire the thing
"""

CL_DONE_HONEST = """# Handoff checklist: demo
Status: done

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [x] w1 Wave A: wire the thing
"""

CL_DONE_LYING = """# Handoff checklist: demo
Status: done

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [ ] w1 Wave A: wire the thing
"""

CL_SUPERSEDED = """# Handoff checklist: demo
Status: superseded

## Deliverables
- [ ] d1 file:docs/demo/GONE.md

## Waves
- [ ] w1 Wave A: wire the thing
"""

CL_GOOD = """# Handoff checklist: good
Status: done

## Deliverables
- [x] d1 file:docs/good/README.md

## Waves
- [x] w1 Wave A: the finished one
"""

CL_BROKEN = """# Handoff checklist: broken
Owner: deadbeef

## Deliverables
- [ ] d1 nothing verifies this one
- [ ] d1 file:docs/broken/README.md
- [ ] w9 a wave id under the deliverables

## Waves
- [z] w1 a state character that does not exist
"""

CL_SESSION_START = """# Handoff checklist: demo
Status: executing
Owner: cafe0000

## Deliverables
- [x] d1 file:docs/demo/README.md

## Waves
- [x] w1 Wave A: wire the thing
- [ ] w2 Wave B: land the rest
"""

CL_LIVE_ANSWER = "answer\n\n## Remaining\n- nothing of mine"


# --- the two helpers the bash defined here, and 23-priority-ladder.sh reused -


def clfile(fix, slug: str, body: str) -> None:
    """`clfile <slug>`: a CHECKLIST.md at agent/programs/<slug>/.

    Follows wl_checklist.py's glob, which moved out of docs/ with the rest of the agent working tree. Left behind, these fixtures write somewhere the gate no longer looks and every case below passes over an empty scan, which is why case 193 exists to prove the silence is cheap, not dead.
    """
    folder = fix.proj / "agent" / "programs" / slug
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "CHECKLIST.md").write_text(body, encoding="utf-8")


def cldeliver(fix, relpath: str, content: str = "x") -> None:
    """`cldeliver <relpath> [content]`: a deliverable file under the repo."""
    target = fix.proj / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def pyprobe(fix, code: str, env_extra=None, cwd=None) -> subprocess.CompletedProcess:
    """One `python3 - <<PYEOF` probe, in a subprocess exactly as the bash ran it.

    Local to this module: the harness drives the hook as a whole, while cases 191, 192 and 202 import one `wl_*` module and call into it directly. A subprocess keeps that import out of the pytest process, where it would leave module state behind for whatever runs next.
    """
    env = dict(fix.env)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd) if cwd else None,
        check=False,
    )


def additem(result) -> str:
    """The id the `--add` printed, as the bash `grep -oE '#[0-9a-f]+' | tr -d '#'` read it."""
    found = re.search(r"#([0-9a-f]+)", result.out)
    return found.group(1) if found else ""


PROBE_191 = """
import os
import sys

sys.path.insert(0, os.environ["HOOKDIR"])
import wl_core as C

base = os.environ["NESTBASE"]
nested = os.path.join(base, "outer", "nested")
event = {"cwd": nested}
print("CONTROL", C.project_root(event.get("cwd") or os.getcwd()))
print("FIRE", C.project_root(C.project_start(event)))
# Rung 2: with no CLAUDE_PROJECT_DIR at all, a CLI run must anchor on the hook
# FILE's own repo, not on wherever the shell happens to be standing.
del os.environ["CLAUDE_PROJECT_DIR"]
os.chdir(nested)
print("CLI", C.project_start(), C.hook_repo_root())
"""

PROBE_192 = """
import sys
sys.path.insert(0, ".")
import wl_checks as W

POLL = {"schedule": "37 * * * *", "prompt": "run .claude/hooks/stop/worklist.py --poll d136ac61"}
WORK = {"schedule": "17 * * * *", "prompt": "pr-babysit HEARTBEAT: check CI, fix reds"}

checks = {
    "poll-offminute": W.is_poll_cron(POLL) is True,
    "work-hourly-not-poll": W.is_poll_cron(WORK) is False,
    "shape-still-sufficient": W.is_poll_cron({"schedule": "*/5 * * * *"}) is True,
    "shape-zero-still-works": W.is_poll_cron({"schedule": "0 * * * *"}) is True,
    "no-prompt-degrades": W.is_poll_cron({"schedule": "37 * * * *"}) is False,
    "daily-not-poll": W.is_poll_cron({"schedule": "0 9 * * *"}) is False,
}
bad = [k for k, v in checks.items() if not v]
print("CLASSIFY", "OK" if not bad else "BAD:" + ",".join(bad))
print("CANON", W.canonical_poll_schedule("37 * * * *"))
print("TIP", repr(W.poll_backoff_tip([POLL], 9999, False)))
"""

PROBE_202 = """
import os
import sys

sys.path.insert(0, ".")
import wl_checklist as CL

root = os.environ["CLROOT"]
path = os.path.join(root, "agent", "programs", "locked", "CHECKLIST.md")
try:
    open(path).read()
    print("READABLE yes")
except OSError:
    print("READABLE no")
print("SIG", CL.checklists_sig(root))
v, a, live = CL.checklist_findings(root, None, "deadbeef-1111", "")
print("V", v[0][0], v[0][1], live)
print("TEXT", "THIS IS A HOOK BUG" in v[0][2])
"""


def test_191_root_resolution_must_not_walk_into_a_repo_nested_in_the_repo(wl):  # noqa: F811
    """THE DEFECT, measured live on 2026-08-06: the Stop event's cwd is wherever the session last worked, and this tree holds repos INSIDE the repo, submodules (private/renet) and gitignored non-submodule siblings (private/growth). Every root resolution started from that cwd, so project_root() stopped at the NESTED repo and the branch check read ITS branch: a session on 0804-1 was
    ordered to bootstrap agent/main/ because private/growth happened to be on main.

    CONTROL FIRST, and it is the pre-fix expression itself rather than a mutation: if `event.cwd or getcwd()` does NOT resolve to the nested repo on this fixture, the fixture is not reproducing the bug and the FIRE below proves nothing.
    """
    nestbase = wl.base / "nesting"
    if nestbase.exists():
        shutil.rmtree(nestbase)
    (nestbase / "outer" / ".claude" / "hooks" / "stop").mkdir(parents=True, exist_ok=True)
    (nestbase / "outer" / "nested").mkdir(parents=True, exist_ok=True)
    # a FILE, as a worktree or submodule writes it
    (nestbase / "outer" / ".git").write_text("", encoding="utf-8")
    (nestbase / "outer" / "nested" / ".git").write_text("", encoding="utf-8")

    probe = pyprobe(
        wl,
        PROBE_191,
        {
            "HOOKDIR": str(wlfix.STOP_DIR),
            "NESTBASE": str(nestbase),
            "CLAUDE_PROJECT_DIR": str(nestbase / "outer"),
        },
    )
    out = probe.stdout
    assert "CONTROL %s/outer/nested" % nestbase in out, (
        "191 CONTROL: fixture does not reproduce the bug, so FIRE proves nothing: %s"
        % (out + probe.stderr)[:300]
    )
    nested_fire = "191 FIRE: still resolving into the nested repo: %s" % (out + probe.stderr)[:300]
    assert "FIRE %s/outer" % nestbase in out, nested_fire
    assert "FIRE %s/outer/nested" % nestbase not in out, nested_fire
    cli_line = [line for line in out.splitlines() if line.startswith("CLI ")]
    fields = cli_line[0].split() if cli_line else []
    cli_start = fields[1] if len(fields) > 1 else ""
    cli_hook = fields[2] if len(fields) > 2 else ""
    anchored = "191 FIRE: a CLI run still anchors on cwd (start=%s hook=%s)" % (cli_start, cli_hook)
    assert cli_hook, anchored
    assert cli_start == cli_hook, anchored

    # The store path is the thing a wrong root DESTROYS: it is slugged from the root, so a root that moves orphans every open item in the old file. Pin it.
    env = dict(wl.env)
    env["TMPDIR"] = str(wl.base / "tmp")
    env["CLAUDE_PROJECT_DIR"] = str(nestbase / "outer")

    def path_from(cwd):
        return subprocess.run(
            [sys.executable, str(wl.hook), "--path"],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(cwd),
            check=False,
        ).stdout

    path_outer = path_from(nestbase / "outer")
    path_nested = path_from(nestbase / "outer" / "nested")
    assert path_outer == path_nested, "191 FIRE: --path moved with cwd (%s vs %s)" % (
        path_outer,
        path_nested,
    )


def test_192_an_hourly_poll_cron_parked_off_the_hour_is_still_a_poll_cron(wl):  # noqa: F811
    """THE INCIDENT (2026-08-07): CronCreate tells every session to avoid the :00 and :30 marks so the fleet does not hit the API on one instant, and offers "hourly -> 7 * * * *" as its example. is_poll_cron knew the hourly rung only as `0 * * * *`, so a session obeying both instructions had its poll cron counted as a second WORK cron, and the next stop ordered it to CronDelete the
    cron the previous stop had ordered it to create.

    THE FIRST FIX WAS WRONG and this case exists to keep it wrong: widening the schedule regex to any `<minute> * * * *` took this harness from 1 failure to 168, because an hourly WORK cron is indistinguishable from an hourly poll by schedule alone. Hence the negative assertions in the probe, which are not padding but the guard rail that reverted change would trip.
    """
    probe = pyprobe(wl, PROBE_192, cwd=wlfix.STOP_DIR)
    out = probe.stdout
    classify = [line for line in out.splitlines() if line.startswith("CLASSIFY")]
    assert "CLASSIFY OK" in out, "192: poll-cron classification wrong: %s" % (classify or out[:200])
    assert "CANON 0 * * * *" in out, (
        "192: canonical_poll_schedule did not map :37 to the hourly rung: %s" % out[:200]
    )
    assert "TIP ''" in out, (
        "192: poll_backoff_tip mis-handled an off-minute hourly poll: %s" % out[:200]
    )


def test_193_zero_overhead_a_repo_with_no_checklist_never_hears_the_word(wl):  # noqa: F811
    """The cost claim in wl_checklist's docstring is that a repo keeping no handoffs pays one glob and says nothing. That is only half a control: a silent gate and a dead gate look identical from here, so the second leg plants one checklist into the SAME fixture and demands the words appear."""
    wl.say("done for now")
    wl.brief_now()
    wl.hand_now()
    got = wl.run()
    quiet = "193: the gate talked about checklists that do not exist: %s" % got.out[:300]
    assert "handoff" not in got.out.lower(), quiet
    assert "CHECKLIST" not in got.out, quiet

    clfile(wl, "demo", CL_PRODUCING_MINE)
    got = wl.run()
    # CONTROL-FOR-THE-CONTROL: one planted checklist and the same fixture speaks, so the silence above was a cheap gate rather than a dead one.
    dead = "193 CONTROL: the silence above was a DEAD gate, not a cheap one: %s" % got.out[:300]
    assert "agent/programs/demo/CHECKLIST.md" in got.out, dead
    assert "handoff" in got.out.lower(), dead


def test_194_a_missing_deliverable_blocks_its_owner_then_the_flip_is_all_that_remains(wl):  # noqa: F811
    """194: producing plus a missing deliverable blocks its OWNER, and the row names the file and the verdict. 194b continues on the same world: with everything verified, ONE step is left and it is the status flip."""
    wl.say("done for now")
    wl.brief_now()
    wl.hand_now()
    clfile(wl, "demo", CL_PRODUCING_MINE)
    got = wl.run()
    unnamed = "194: the producing block did not name the missing deliverable: %s" % got.out[:400]
    assert "DO NOT VERIFY" in got.out, unnamed
    assert "d1 docs/demo/README.md -- MISSING" in got.out, unnamed
    wl.check(
        "block",
        "0 of 1 are present",
        "194: and the decision is block, not a note on an allowed stop",
    )

    cldeliver(wl, "docs/demo/README.md", "the readme")
    got = wl.run()
    flip = "194b: the flip demand is wrong: %s" % got.out[:400]
    assert "ONE step remains and it is the flip" in got.out, flip
    assert "'Status: producing' to 'Status: executing'" in got.out, flip
    assert "DO NOT VERIFY" not in got.out, flip


def test_195_a_foreign_producing_checklist_is_reported_never_blocked_on(wl):  # noqa: F811
    """195: another session's producing handoff rides the report and blocks nobody, and a LIVE owner gets no adoption hint, which would be a land grab. 195b continues on the same world with the owner's transcript DEAD: projects_dir is the transcript's own directory (wl_checks.py:1678), so an aged cafe0000*.jsonl beside the fixture transcript is exactly what owner_age_hours reads.
    Planted rather than mocked, for that reason.
    """
    wl.say("done for now")
    wl.brief_now()
    wl.hand_now()
    clfile(wl, "demo", CL_PRODUCING_FOREIGN)
    got = wl.run()
    misjudged = "195: a foreign producing checklist was mis-adjudicated: %s" % got.out[:400]
    assert got.rc == 0, misjudged
    assert '"decision": "block"' not in got.out, misjudged
    assert "that session's to finish" in got.out, misjudged
    # CONTROL: the adoption hint must stay away from a live owner.
    assert "adopt it by editing" not in got.out, (
        "195 CONTROL: the adoption hint fired on a live owner: %s" % got.out[:400]
    )

    dead = wl.base / "cafe0000-dead.jsonl"
    dead.write_text("", encoding="utf-8")
    old = time.time() - 48 * 3600
    os.utime(dead, (old, old))
    got = wl.run()
    orphan = "195b: no adoption hint for an abandoned handoff: %s" % got.out[:500]
    assert "adopt it by editing the 'Owner:' line" in got.out, orphan
    assert "agent/programs/demo/CHECKLIST.md" in got.out, orphan
    assert "superseded" in got.out, orphan


def test_196_a_ticked_box_does_not_save_a_deliverable_that_is_not_on_disk(wl):  # noqa: F811
    """196: the file is the truth, the tick is bookkeeping. The wave is claimed by a peer rather than ticked, so the deliverable check is the ONLY thing that can speak here and the control below is a real allow instead of a different violation wearing the same fixture. 196b continues: EMPTY is not MISSING, and the row says which."""
    wl.say("done for now")
    wl.brief_now()
    wl.hand_now()
    clfile(wl, "demo", CL_EXECUTING)
    wl.cli_as("cafe0000", "--add", "cafe0000", "cl:demo/w1 Wave A: wire the thing")
    got = wl.run()
    ticked = "196: the ticked-but-missing deliverable passed: %s" % got.out[:400]
    assert "reality disagrees" in got.out, ticked
    assert "d1 docs/demo/README.md -- MISSING" in got.out, ticked

    cldeliver(wl, "docs/demo/README.md", "")
    got = wl.run()
    truncated = "196b: the truncated deliverable was mis-named: %s" % got.out[:400]
    assert "d1 docs/demo/README.md -- EMPTY" in got.out, truncated
    assert "-- MISSING" not in got.out, truncated

    cldeliver(wl, "docs/demo/README.md", "the readme")
    wl.check("allow", "", "196b CONTROL: a non-empty file clears the check entirely")


def test_197_an_uncovered_wave_blocks_then_the_add_moves_it_into_the_open_items_check(wl):  # noqa: F811
    """197: an UNCOVERED wave blocks and carries its own one-command exit. 197b continues on the same world and asserts DISJOINTNESS, not merely absence: the cl-waves needle must go while the open item it created appears, because a gate that stopped firing AND took the work with it would look identical from a one-needle assertion."""
    wl.say("done for now")
    wl.brief_now()
    wl.hand_now()
    cldeliver(wl, "docs/demo/README.md", "the readme")
    clfile(wl, "demo", CL_EXECUTING)
    got = wl.run()
    noexit = "197: the uncovered wave has no runnable exit: %s" % got.out[:500]
    assert "w1 UNCOVERED" in got.out, noexit
    assert "cl:demo/w1" in got.out, noexit
    assert "--add deadbeef 'cl:demo/w1 Wave A: wire the thing'" in got.out, noexit

    wl.cli("--add", "deadbeef", "cl:demo/w1 Wave A: wire the thing")
    got = wl.run({"WORKLIST_FOCUS": "off"})
    disjoint = "197b: coverage either did not register or swallowed the work: %s" % got.out[:500]
    assert "UNCOVERED" not in got.out, disjoint
    assert "OPEN worklist item" in got.out, disjoint
    assert "cl:demo/w1" in got.out, disjoint


def test_197c_a_peers_item_covers_the_wave_for_everybody(wl):  # noqa: F811
    """Which is the point: once ANY session claims the wave, the redundant block on the others lifts."""
    wl.say("done for now")
    wl.brief_now()
    wl.hand_now()
    cldeliver(wl, "docs/demo/README.md", "the readme")
    clfile(wl, "demo", CL_EXECUTING)
    wl.cli_as("cafe0000", "--add", "cafe0000", "cl:demo/w1 Wave A: wire the thing")
    got = wl.run()
    claimed = "197c: a peer-claimed wave still blocked this session: %s" % got.out[:400]
    assert got.rc == 0, claimed
    assert "UNCOVERED" not in got.out, claimed
    assert '"decision": "block"' not in got.out, claimed


def test_198_done_but_unticked_the_store_settled_it_and_the_box_did_not(wl):  # noqa: F811
    """A ticked store item with an unticked box is called out, with the box to tick named."""
    wl.say("done for now")
    wl.brief_now()
    wl.hand_now()
    cldeliver(wl, "docs/demo/README.md", "the readme")
    clfile(wl, "demo", CL_EXECUTING)
    iid = additem(wl.cli("--add", "deadbeef", "cl:demo/w1 Wave A: wire the thing"))
    wl.cli("--tick", "deadbeef", iid, "wave A landed, suite run green, exit 0")
    got = wl.run()
    settled = "198: the settled wave did not demand its tick: %s" % got.out[:500]
    assert "w1 DONE-BUT-UNTICKED" in got.out, settled
    assert "#%s" % iid in got.out, settled
    assert "tick '- [x] w1' in agent/programs/demo/CHECKLIST.md" in got.out, settled


def test_198c_a_wave_closed_through_a_door_must_not_be_told_to_tick_its_box(wl):  # noqa: F811
    """A door-closed wave is covered and correctly unticked, so demanding a tick would demand a FALSE one for work no session did."""
    wl.say("done for now")
    wl.brief_now()
    wl.hand_now()
    cldeliver(wl, "docs/demo/README.md", "the readme")
    clfile(wl, "demo", CL_EXECUTING_SECRETS)
    iid = additem(
        wl.cli("--add", "deadbeef", "cl:demo/w1 Wave A: set the production secrets and cut over")
    )
    wl.cli(
        "--tick",
        "deadbeef",
        iid,
        "door:operator-only - needs secrets no session holds; brief at docs/demo/RUNBOOK.md:12",
    )
    got = wl.run()
    assert "w1 DONE-BUT-UNTICKED" not in got.out, (
        "198c: the gate demanded a FALSE tick for work no session did: %s" % got.out[:500]
    )


def test_198d_control_the_same_wave_without_a_door_still_demands_its_tick(wl):  # noqa: F811
    """198d is the CONTROL for 198c: it fires, so 198c passes because of the door and not because the check went silent. 198b continues on the same world: every box ticked under 'executing' means the status is stale, and the checklist is asked for the last edit it needs."""
    wl.say("done for now")
    wl.brief_now()
    wl.hand_now()
    cldeliver(wl, "docs/demo/README.md", "the readme")
    clfile(wl, "demo", CL_EXECUTING_SECRETS)
    iid = additem(
        wl.cli("--add", "deadbeef", "cl:demo/w1 Wave A: set the production secrets and cut over")
    )
    wl.cli("--tick", "deadbeef", iid, "cut over on host-1, verified, exit 0")
    got = wl.run()
    assert "w1 DONE-BUT-UNTICKED" in got.out, (
        "198d: the door exemption swallowed a genuinely settled wave: %s" % got.out[:500]
    )

    clfile(wl, "demo", CL_EXECUTING_ALL_TICKED)
    got = wl.run()
    assert "everything is settled; set 'Status: done'" in got.out, (
        "198b: a finished program was left at executing forever: %s" % got.out[:400]
    )


def test_199_done_is_inactive_and_is_gated_on_being_honestly_done(wl):  # noqa: F811
    """199: a genuinely done handoff costs a later session nothing at all, while 'done' with an unticked wave is a lie the next session would believe. 199b continues on the same world: 'superseded' is the terminal escape and adjudicates nothing, so an abandoned program stops costing anything the moment it says so."""
    wl.say("done for now")
    wl.brief_now()
    wl.hand_now()
    cldeliver(wl, "docs/demo/README.md", "the readme")
    clfile(wl, "demo", CL_DONE_HONEST)
    got = wl.run()
    talking = "199: a done checklist is still talking: %s" % got.out[:400]
    assert got.rc == 0, talking
    assert "CHECKLIST" not in got.out, talking
    assert '"decision": "block"' not in got.out, talking

    clfile(wl, "demo", CL_DONE_LYING)
    got = wl.run()
    dishonest = "199: a dishonest done header passed: %s" % got.out[:400]
    assert "reality disagrees" in got.out, dishonest
    assert "wave w1 is not ticked, yet the checklist claims done" in got.out, dishonest

    clfile(wl, "demo", CL_SUPERSEDED)
    got = wl.run()
    abandoned = "199b: superseded still adjudicated: %s" % got.out[:400]
    assert got.rc == 0, abandoned
    assert "CHECKLIST" not in got.out, abandoned
    assert '"decision": "block"' not in got.out, abandoned


def test_200_the_shape_gate_collects_every_defect_and_scopes_itself_to_the_bad_file(wl):  # noqa: F811
    """One error per stop would cost one turn per typo, so the parser collects them all. The clean checklist alongside is the control: a malformed file must not smear its verdict over its neighbours."""
    wl.say("done for now")
    wl.brief_now()
    wl.hand_now()
    cldeliver(wl, "docs/good/README.md", "the readme")
    clfile(wl, "good", CL_GOOD)
    clfile(wl, "broken", CL_BROKEN)
    got = wl.run()
    needles = [
        "no 'Status:' line in the first 10 lines",
        "does not belong under that section",
        "carries no 'file:<path>' token",
        "duplicate id 'd1'",
        "not a checklist item",
    ]
    nrows = sum(1 for needle in needles if needle in got.out)
    thin = "200: shape diagnosis is thin (rows=%d): %s" % (nrows, got.out[:600])
    assert "is MALFORMED" in got.out, thin
    assert nrows >= 3, thin
    # CONTROL: the clean checklist beside it is never mentioned.
    smear = "200 CONTROL: the shape verdict smeared onto a healthy file: %s" % got.out[:600]
    assert "agent/programs/broken/CHECKLIST.md is MALFORMED" in got.out, smear
    assert "agent/programs/good/CHECKLIST.md" not in got.out, smear


def test_201_the_poll_fast_path_forfeits_on_a_live_checklist(wl):  # noqa: F811
    """STAT-ONLY. The banked pollbase carries clsig and cl_live (wl_checks.bank_pollbase). This leg banks a LIVE-but-non-blocking world (wave claimed by a peer), so cl_live=1 with an unchanged signature, which is the only thing that can make the silent path forfeit here. The two controls below are the same dance with no checklist at all, and with a settled one.

    PADDED to at least 4 competing advisory sections (the checklist plus a foreign brief, a stale peer transcript and an orphaned item) so the assertion holds regardless of which 3 the fixed-3-per-stop randomized drain releases: at least one of the 4 always survives into the poll's own stop, keeping output non-empty."""
    wl.brief_now()
    wl.hand_now()
    cldeliver(wl, "docs/demo/README.md", "the readme")
    clfile(wl, "demo", CL_EXECUTING)
    wl.cli_as("cafe0000", "--add", "cafe0000", "cl:demo/w1 Wave A: wire the thing")
    wl.brief_other("cafe1234")
    peer = wl.base / "cafe1234.jsonl"
    peer.write_text("", encoding="utf-8")
    aged = time.time() - 48 * 3600
    os.utime(peer, (aged, aged))
    wl.add_item("- [ ] (cafe1234) their abandoned item")
    wl.say(CL_LIVE_ANSWER)
    wl.check("allow", "", "201: the full stop allows and banks the checklist world")

    bank = wl.stem(".pollbase-deadbeef").read_text(encoding="utf-8")
    unbanked = "201: the checklist world was not banked: %s" % bank
    assert '"cl_live": 1' in bank, unbanked
    assert re.search(r'"clsig": "[0-9a-f]{16}"', bank), unbanked

    wl.cli("--poll", "deadbeef")
    got = wl.run()
    assert got.out, "201: the poll went silent while a live handoff was outstanding"


def test_201_control_a_repo_with_no_handoffs_keeps_the_poll_free(wl):  # noqa: F811
    """CONTROL for 201: a repo with no handoffs banks cl_live=0, which is what keeps polls free, and the poll stop stays perfectly silent, so the gate has not broken the silent path for everyone."""
    wl.brief_now()
    wl.hand_now()
    wl.say(CL_LIVE_ANSWER)
    wl.check("allow", "", "201 CONTROL: baseline stop with no checklist at all")

    bank = wl.stem(".pollbase-deadbeef").read_text(encoding="utf-8")
    assert '"cl_live": 0' in bank, "201 CONTROL: an empty repo banked a live count: %s" % bank

    wl.cli("--poll", "deadbeef")
    got = wl.run()
    broke = "201 CONTROL: the gate broke the silent path for everyone: rc=%d %r" % (
        got.rc,
        got.out[:200],
    )
    assert got.rc == 0, broke
    assert not got.out, broke


def test_201_control_a_settled_checklist_costs_polls_nothing_until_it_moves(wl):  # noqa: F811
    """CONTROL for 201: a done program costs polls nothing, exactly as promised. Then the last leg edits it: the banked cl_live is still 0, so the ONLY thing that can forfeit the silent path on the next poll is the moved signature, and the battery it pays for is what catches the un-tick that edit smuggled in."""
    wl.brief_now()
    wl.hand_now()
    cldeliver(wl, "docs/demo/README.md", "the readme")
    clfile(wl, "demo", CL_DONE_HONEST)
    wl.say(CL_LIVE_ANSWER)
    wl.check("allow", "", "201 CONTROL: baseline stop with a SETTLED checklist")

    wl.cli("--poll", "deadbeef")
    got = wl.run()
    charged = "201 CONTROL: a settled checklist still charged the poll: rc=%d %r" % (
        got.rc,
        got.out[:200],
    )
    assert got.rc == 0, charged
    assert not got.out, charged

    clfile(wl, "demo", CL_DONE_LYING)
    wl.cli("--poll", "deadbeef")
    got = wl.run()
    assert "reality disagrees" in got.out, (
        "201: an edited checklist slipped past the poll fast path: %r" % got.out[:200]
    )


def test_202_checklists_sig_is_stat_only_and_the_unreadable_file_proves_it(wl):  # noqa: F811
    """A contract, not an optimisation: the poll path compares this value, and a version that opened files would pay exactly the cost the fast path exists to avoid. A chmod-000 checklist is the instrument, since stat still answers where read cannot, so the signature must come back while the ADJUDICATION (which does read) fails closed into the ALWAYS-tier unreadable violation. The
    key it fails closed UNDER is asserted too, and it is per-slug (`cl-shape:locked`) for the reason case 204 pins: one unreadable checklist must not evict a second one from the rotation.
    """
    folder = wl.proj / "agent" / "programs" / "locked"
    folder.mkdir(parents=True, exist_ok=True)
    locked = folder / "CHECKLIST.md"
    locked.write_text("Status: executing\n", encoding="utf-8")
    locked.chmod(0o000)
    try:
        probe = pyprobe(wl, PROBE_202, {"CLROOT": str(wl.proj)}, cwd=wlfix.STOP_DIR)
    finally:
        locked.chmod(0o644)
    out = probe.stdout
    # CONTROL: the fixture really is unreadable, so the leg below means something.
    assert "READABLE no" in out, (
        "202 CONTROL: chmod 000 did not deny this process (running as root?): %s"
        % (out + probe.stderr)[:200]
    )
    assert re.search(r"(?m)^SIG [0-9a-f]{16}$", out), (
        "202: the stat-only signature raised or came back malformed: %s"
        % (out + probe.stderr)[:300]
    )
    closed = "202: an unreadable checklist did not fail closed: %s" % (out + probe.stderr)[:300]
    assert "V cl-shape:locked True 1" in out, closed
    assert "TEXT True" in out, closed
    locked.unlink()


def test_203_session_start_hands_a_new_session_the_live_checklists(wl):  # noqa: F811
    """The listing carries status, owner and both progress fractions, and the CONTROL that follows keeps a settled checklist out of it: a done handoff is not context anyone needs handed back."""
    cldeliver(wl, "docs/demo/README.md", "the readme")
    clfile(wl, "demo", CL_SESSION_START)
    payload = '{"session_id":"%s","cwd":"%s"}' % (wl.sid, wl.proj)
    out = wl.python(["--session-start"], stdin=payload).out
    handback = "203: SessionStart did not hand back the live checklist: %s" % out[:400]
    row = (
        "agent/programs/demo/CHECKLIST.md [executing] owner=cafe0000 "
        "deliverables 1/1 verified, waves 1/2 settled"
    )
    assert "LIVE HANDOFF CHECKLISTS" in out, handback
    assert row in out, handback

    clfile(wl, "demo", CL_DONE_HONEST)
    out = wl.python(["--session-start"], stdin=payload).out
    assert "LIVE HANDOFF CHECKLISTS" not in out, (
        "203 CONTROL: the listing surfaced a done handoff: %s" % out[:400]
    )
