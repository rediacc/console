"""The append-only event store: migration, torn tails, write races, tick refusal, the lease ladder, OS worker verification, autonomy.

Ported from `.claude/hooks/stop/worklist-cases/10-event-store.sh`, one pytest function per numbered bash case, splitting where a bash case called `setup` again mid-block.

EVERY FIRE CASE IS PAIRED WITH A SILENT CONTROL off the same fixture shape differing in one planted fact, because a control satisfied by an unbuilt fixture is worse than no control. The ladder cases (137 to 139) and the autonomy cases (141) carry their controls as their own test functions, named `control`, so a control that stops discriminating turns this module red rather than
quietly passing.
"""

from __future__ import annotations

import ast
import collections
import contextlib
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

LEASE_BG = json.dumps(
    [
        {
            "id": "bw1",
            "type": "shell",
            "status": "running",
            "description": "watch",
            "command": "sleep 999",
        }
    ]
)


def stamp(minutes_ago: float, fmt: str = "%Y-%m-%dT%H:%M:%SZ") -> str:
    """A UTC stamp `minutes_ago` in the past, the pytest shape of `date -u -d`."""
    moment = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=minutes_ago)
    return moment.strftime(fmt)


def plant(fix, *records: dict) -> None:
    """Append raw events to the LEGACY log beside the worklist.

    Fixtures plant there rather than in the writer directory for the reason the bash harness gives: the legacy path is still read and unioned by `_read_events`, so a plant is still effective, while the assertions read the WHOLE store through `wl_events`.
    """
    with fix.events.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")


def added_id(result: wlfix.Result) -> str:
    """The item id `--add` printed."""
    found = re.search(r"^added #([0-9a-f]{8})", result.out, re.MULTILINE)
    assert found, "--add printed no item id: %r" % result.out[:200]
    return found.group(1)


def test_132_the_store_markdown_items_fold_into_the_event_log(wl):  # noqa: F811
    """Migration: all four live states fold in, and the `[~]` tombstone reads as deleted."""
    future = stamp(-30, "%Y-%m-%dT%H:%MZ")
    for line in (
        "- [ ] (deadbeef) open thing",
        "- [x] (deadbeef) done thing, exit 0",
        "- [?] (deadbeef) question DEFAULT: pick A",
        "- [>] (deadbeef) until:%s delegated" % future,
        "- [~] (deadbeef) tombstoned relic",
    ):
        wl.add_item(line)
    listing = wl.cli("--list").out
    for needle in (
        "- [ ] (deadbeef) open thing",
        "- [x] (deadbeef) done thing, exit 0",
        "- [?] (deadbeef) question DEFAULT: pick A",
        "delegated",
    ):
        assert needle in listing, "markdown sync lost an item, MISSING %r: %s" % (
            needle,
            listing[:400],
        )
    assert "tombstoned relic" not in listing, (
        "the [~] tombstone was resurrected: %s" % listing[:400]
    )
    assert '"ev":"md"' in wl.wl_events(), (
        "no md event was appended, so the store is a re-parse rather than a log: %s"
        % wl.wl_events()[:400]
    )


def test_133_in_place_markdown_edits_are_honoured_and_cli_state_survives_md_churn(wl):  # noqa: F811
    """The markdown is MUTATED by its writers (ticks flip the state byte in place), which is why the sync is a whole-file diff and not an append offset."""
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n- the parser item")
    wl.add_item("- [ ] (deadbeef) fix the parser crash, verified exit 0")
    wl.check("block", "OPEN worklist item", "the imported open item blocks")

    text = wl.wl.read_text(encoding="utf-8")
    wl.wl.write_text(
        text.replace("- [ ] (deadbeef) fix the parser", "- [x] (deadbeef) fix the parser"),
        encoding="utf-8",
    )
    wl.newturn()
    wl.say("done\n\n## Remaining\nnothing")
    wl.check("allow", "", "an in-place tick (state byte flip) clears the block")

    aid = added_id(wl.cli("--add", "deadbeef", "wire the fixture, run pending"))
    wl.newturn()
    wl.say("working\n\n## Remaining\n- the fixture item")
    wl.check("block", "wire the fixture", "a CLI-added item blocks like any open item")

    wl.cli("--tick", "deadbeef", aid, "suite green, exit 0")
    wl.add_item("- [ ] (deadbeef) a fresh md item to churn the file")
    wl.newturn()
    wl.say("working\n\n## Remaining\n- the churn item")
    got = wl.run()
    assert "a fresh md item to churn" in got.out, "the fresh md item was lost: %s" % got.out[:260]
    assert "wire the fixture" not in got.out, (
        "md churn resurrected a CLI-ticked item: %s" % got.out[:260]
    )


def test_134_a_torn_event_log_tail_is_healed(wl):  # noqa: F811
    """A crash mid-write leaves a fragment with no newline; it must stay its own dead line rather than merging into the next event."""
    wl.cli("--add", "deadbeef", "first item")
    with wl.events.open("a", encoding="utf-8") as handle:
        handle.write('{"ev":"add","id":"tornado1","at":"')
    wl.cli("--add", "deadbeef", "second item")

    adds = bad = merged = 0
    for raw in wl.wl_events().splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            bad += 1
            if "second item" in line:
                merged += 1
            continue
        if event.get("ev") == "add":
            adds += 1
    assert (adds, bad, merged) == (2, 1, 0), "torn-tail healing broke: adds=%d bad=%d merged=%d" % (
        adds,
        bad,
        merged,
    )
    assert "second item" in wl.cli("--list").out, "the fold lost the event after the torn line"


def test_135_race_concurrent_add_writers_lose_nothing(wl):  # noqa: F811
    """Sixteen concurrent adds must yield sixteen parseable events with sixteen distinct ids."""
    procs = []
    for index in range(1, 17):
        prefix = "sess000%d" % index
        env = dict(wl.env)
        env["WORKLIST_SESSION_ID"] = wlfix.peer_id(prefix)
        env["CLAUDE_PROJECT_DIR"] = str(wl.proj)
        env["WORKLIST_TASKS_DIR"] = str(wl.base / "tasks")
        procs.append(
            subprocess.Popen(
                [
                    sys.executable,
                    str(wl.hook),
                    "--add",
                    prefix,
                    "concurrent item %d" % index,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=env,
            )
        )
    for proc in procs:
        proc.wait()

    ids: set = set()
    count = bad = 0
    for raw in wl.wl_events().splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            bad += 1
            continue
        if event.get("ev") == "add":
            count += 1
            ids.add(event.get("id"))
    assert (count, len(ids), bad) == (16, 16, 0), (
        "concurrent adds were lost or torn: adds=%d ids=%d bad=%d" % (count, len(ids), bad)
    )


def test_136_tick_refuses_a_completion_without_evidence(wl):  # noqa: F811
    """Refused loudly (exit nonzero) and nothing written, and the same tick WITH evidence lands."""
    aid = added_id(wl.cli("--add", "deadbeef", "prove the flag binds"))
    refused = wl.cli("--tick", "deadbeef", aid, "done i guess")
    assert refused.rc != 0, "an evidence-free tick was accepted"
    assert "REFUSED" in refused.err, "the refusal was silent: %r" % refused.err[:160]
    assert '"ev":"state"' not in wl.wl_events(), "the refused tick leaked an event"

    landed = wl.cli("--tick", "deadbeef", aid, "suite run green, exit 0")
    assert landed.rc == 0, "an evidenced tick was rejected: %r" % (landed.out + landed.err)[:200]
    assert "- [x]" in wl.cli("--list").out, "the evidenced tick did not land"


def test_137_ladder_rung_1_a_quiet_lease_pings_report_only(wl):  # noqa: F811
    """Forty-five minutes: a lease quiet for fifty still ALLOWS the stop and only pings."""
    wl.brief_now()
    wl.hand_now()
    old = stamp(50)
    until = stamp(-30, "%Y-%m-%dT%H:%MZ")
    plant(
        wl,
        {
            "ev": "add",
            "id": "aaaa1111",
            "at": old,
            "by": "deadbeef",
            "s": " ",
            "o": "deadbeef",
            "t": "long docs job",
        },
        {
            "ev": "lease",
            "id": "aaaa1111",
            "at": old,
            "by": "deadbeef",
            "until": until,
            "worker": "bw1",
        },
    )
    wl.bg = LEASE_BG
    wl.say("answer\n\n## Remaining\n- the docs job rides a lease")
    wl.check("allow", "Liveness ping", "a 50-minute-quiet lease still ALLOWS the stop")


def test_137_control_a_fresh_lease_draws_no_ping(wl):  # noqa: F811
    """CONTROL: the same shape with young stamps draws no ping at all."""
    wl.brief_now()
    wl.hand_now()
    now = stamp(0)
    until = stamp(-30, "%Y-%m-%dT%H:%MZ")
    plant(
        wl,
        {
            "ev": "add",
            "id": "aaaa1112",
            "at": now,
            "by": "deadbeef",
            "s": " ",
            "o": "deadbeef",
            "t": "fresh docs job",
        },
        {
            "ev": "lease",
            "id": "aaaa1112",
            "at": now,
            "by": "deadbeef",
            "until": until,
            "worker": "bw1",
        },
    )
    wl.bg = LEASE_BG
    wl.say("answer\n\n## Remaining\n- the docs job rides a lease")
    wl.check_quiet("Liveness ping", "CONTROL: a fresh lease draws no ping")


def test_138_rung_2_investigate_blocks_once_per_stamp(wl):  # noqa: F811
    """One hundred quiet minutes hits the INVESTIGATE rung, and the rung fires ONCE per stamp rather than on every stop."""
    wl.brief_now()
    wl.hand_now()
    old = stamp(100)
    until = stamp(-30, "%Y-%m-%dT%H:%MZ")
    plant(
        wl,
        {
            "ev": "add",
            "id": "aaaa2221",
            "at": old,
            "by": "deadbeef",
            "s": " ",
            "o": "deadbeef",
            "t": "stalled docs job",
        },
        {
            "ev": "lease",
            "id": "aaaa2221",
            "at": old,
            "by": "deadbeef",
            "until": until,
            "worker": "bw1",
        },
    )
    wl.bg = LEASE_BG
    wl.say("answer\n\n## Remaining\n- the stalled docs job")
    wl.check("block", "IN-FLIGHT WORK HAS GONE QUIET", "100 quiet minutes hits the rung")
    wl.check("allow", "", "the rung fires ONCE per stamp, not every stop")


def test_138_rung_3_resolve_blocks_and_the_default_exit_always_clears(wl):  # noqa: F811
    """One hundred and twenty-five quiet minutes hits the RESOLVE rung, and the `[?]` plus DEFAULT exit clears the top rung, so it has no way to trap."""
    wl.brief_now()
    wl.hand_now()
    old = stamp(125)
    until = stamp(-30, "%Y-%m-%dT%H:%MZ")
    plant(
        wl,
        {
            "ev": "add",
            "id": "aaaa2222",
            "at": old,
            "by": "deadbeef",
            "s": " ",
            "o": "deadbeef",
            "t": "two-hour stall",
        },
        {
            "ev": "lease",
            "id": "aaaa2222",
            "at": old,
            "by": "deadbeef",
            "until": until,
            "worker": "bw1",
        },
    )
    wl.bg = LEASE_BG
    wl.say("answer\n\n## Remaining\n- the two-hour stall")
    wl.check("block", "QUIET FOR TWO HOURS", "125 quiet minutes hits the RESOLVE rung")
    wl.cli(
        "--defer",
        "deadbeef",
        "aaaa2222",
        "keep waiting on the delegate? DEFAULT: stop it and redelegate "
        "WHY: the delegate holds state only it can flush, so killing it loses work "
        "HOW: the operator says stop, or the DEFAULT redelegates",
    )
    wl.newturn()
    wl.say("deferred it\n\n## Remaining\n- the stall, deferred with a default")
    wl.check("allow", "operator may answer", "the [?] plus DEFAULT exit clears the top rung")


def test_139_gone_fires_on_a_vanished_worker(wl):  # noqa: F811
    """`worker_verified: true` is the load-bearing half of this fixture. GONE means DROPPED: the harness could see the worker when the lease was taken and cannot see it now. Without that bit the case was really asserting that any id the harness does not list is dead, which is a different and wrong rule: it accused an Agent leased by NAME, which has no way to appear in a
    background-task list, while that agent was actively writing files."""
    wl.brief_now()
    wl.hand_now()
    now = stamp(0)
    until = stamp(-30, "%Y-%m-%dT%H:%MZ")
    plant(
        wl,
        {
            "ev": "add",
            "id": "aaaa3331",
            "at": now,
            "by": "deadbeef",
            "s": " ",
            "o": "deadbeef",
            "t": "delegated build",
        },
        {
            "ev": "lease",
            "id": "aaaa3331",
            "at": now,
            "by": "deadbeef",
            "until": until,
            "worker": "bogusw1",
            "worker_verified": True,
        },
    )
    wl.bg = "[]"
    wl.say("answer\n\n## Remaining\n- the delegated build (ongoing on its worker)")
    wl.check(
        "block",
        "NOT in the harness background list",
        "a lease whose worker the harness no longer lists blocks with the facts",
    )


def test_139_a_never_verified_worker_is_not_called_dead(wl):  # noqa: F811
    """THE OTHER HALF. This is the case that cost a session several round trips: an Agent leased by name, absent from the background list by construction, reported as finished or stopped while its files were appearing on disk."""
    wl.brief_now()
    wl.hand_now()
    now = stamp(0)
    until = stamp(-30, "%Y-%m-%dT%H:%MZ")
    plant(
        wl,
        {
            "ev": "add",
            "id": "aaaa3333",
            "at": now,
            "by": "deadbeef",
            "s": " ",
            "o": "deadbeef",
            "t": "delegated docs",
        },
        {
            "ev": "lease",
            "id": "aaaa3333",
            "at": now,
            "by": "deadbeef",
            "until": until,
            "worker": "docdelta",
            "worker_verified": False,
        },
    )
    wl.bg = "[]"
    wl.say("answer\n\n## Remaining\n- the delegated docs (ongoing on its agent)")
    wl.check_quiet(
        "NOT in the harness background list",
        "a worker that was never confirmable is not reported as dead",
    )


def test_139_control_an_unverifiable_teammate_is_never_accused(wl):  # noqa: F811
    """THE FALSE-ACCUSATION CONTROL, the one failure mode worse than no check: an UNVERIFIABLE worker (a teammate, for which no OS process exists by design) must not read as gone. Same fixture shape, worker present in the event."""
    wl.brief_now()
    wl.hand_now()
    now = stamp(0)
    until = stamp(-30, "%Y-%m-%dT%H:%MZ")
    plant(
        wl,
        {
            "ev": "add",
            "id": "aaaa3332",
            "at": now,
            "by": "deadbeef",
            "s": " ",
            "o": "deadbeef",
            "t": "delegated design",
        },
        {
            "ev": "lease",
            "id": "aaaa3332",
            "at": now,
            "by": "deadbeef",
            "until": until,
            "worker": "tm1",
        },
    )
    wl.bg = json.dumps(
        [{"id": "tm1", "type": "teammate", "status": "running", "description": "design agent"}]
    )
    wl.say("answer\n\n## Remaining\n- the delegated design (ongoing on its agent)")
    got = wl.run()
    assert got.decision == "allow", "wrong verdict for a teammate lease: %s" % got.out[:260]
    assert "NOT in the harness background list" not in got.out, (
        "an unverifiable (teammate) worker was accused of being dead: %s" % got.out[:260]
    )


def test_140_os_verification_confirmed_suspect_and_unverifiable():
    """Library-level, against the real OS: a spawned child IS found, a killed one is not, and a teammate task is honestly unverifiable."""
    liveness = wlfix.import_wl("wl_liveness")
    command = "sleep 987654321099"
    child = subprocess.Popen(["sleep", "987654321099"])
    try:
        time.sleep(0.2)
        ancestors = {os.getpid()}
        background = [
            {"id": "sh1", "type": "shell", "status": "running", "command": command},
            {"id": "tm1", "type": "teammate", "status": "running", "description": "agent"},
        ]
        first = liveness.verify_background(background, ancestors=ancestors)
        child.kill()
        child.wait()
        time.sleep(0.2)
        second = liveness.verify_background(background, ancestors=ancestors)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
    got = "live=%s teammate=%s dead=%s" % (first.get("sh1"), first.get("tm1"), second.get("sh1"))
    assert got == "live=confirmed teammate=unverifiable dead=suspect", (
        "verification verdicts wrong: %s" % got
    )


def test_141_autonomy_a_default_past_its_window_is_executed_not_restated(wl):  # noqa: F811
    """An aged deferral demands its default be executed, and refreshing the item restarts the window, so the exit is always available."""
    wl.brief_now()
    wl.hand_now()
    plant(
        wl,
        {
            "ev": "add",
            "id": "bbbb1111",
            "at": stamp(130),
            "by": "deadbeef",
            "s": "?",
            "o": "deadbeef",
            "t": "keep the flag? DEFAULT: keep it",
        },
    )
    wl.say("answer\n\n## Remaining\n- the flag decision, deferred with a default")
    wl.check("block", "OUTLIVED their autonomy window", "an aged deferral demands its default")
    wl.cli("--update", "deadbeef", "bbbb1111", "operator pinged; window restarted deliberately")
    wl.newturn()
    wl.say("answer\n\n## Remaining\n- the flag decision, deferred with a default")
    wl.check("allow", "operator may answer", "refreshing the item restarts the window")


def test_141_control_a_fresh_deferral_does_not_demand_execution(wl):  # noqa: F811
    """CONTROL: a fresh deferral just reports (case 3 pins this too; here it is the explicit twin of the aged fixture)."""
    wl.brief_now()
    wl.hand_now()
    plant(
        wl,
        {
            "ev": "add",
            "id": "bbbb1112",
            "at": stamp(0),
            "by": "deadbeef",
            "s": "?",
            "o": "deadbeef",
            "t": "keep the flag? DEFAULT: keep it",
        },
    )
    wl.say("answer\n\n## Remaining\n- the flag decision, deferred with a default")
    wl.check("allow", "operator may answer", "CONTROL: a fresh deferral does not demand execution")


def test_141_drain_cap_five_aged_deferrals_arrive_three_at_a_time(wl):  # noqa: F811
    """DRAIN CAP: five expired deferrals drain three per stop, never as a wall."""
    wl.brief_now()
    wl.hand_now()
    old = stamp(130)
    for index in range(1, 6):
        plant(
            wl,
            {
                "ev": "add",
                "id": "bbbb222%d" % index,
                "at": old,
                "by": "deadbeef",
                "s": "?",
                "o": "deadbeef",
                "t": "aged question %d DEFAULT: option A" % index,
            },
        )
    wl.say("answer\n\n## Remaining\n- five aged deferrals draining")
    got = wl.run()
    assert "OUTLIVED their autonomy window" in got.out, "drain cap wrong: %s" % got.out[:260]
    assert "and 2 more, held back" in got.out, "drain cap wrong: %s" % got.out[:260]


def test_142_the_judge_caches_an_identical_world_and_message(wl):  # noqa: F811
    """One paid call rather than two, and the CONTROL beside it: any change to the world signature re-asks."""
    wl.brief_now()
    wl.hand_now()
    wl.task(7, "pending", "merge the chain")
    wl.say("answer\n\n## Remaining\n| #7 | merge the chain | pending, me |")
    calls = wl.base / "judgecalls"
    script = wl.base / "binonly" / "claude"
    script.write_text(
        '#!/bin/bash\necho call >>"%s"\n'
        'echo \'{"is_error":false,"structured_output":{"verdict":"stop",'
        '"reason":"legitimately parked","next_action":"none"}}\'\n' % calls,
        encoding="utf-8",
    )
    script.chmod(0o755)

    def call_count() -> int:
        if not calls.is_file():
            return 0
        return sum(1 for line in calls.read_text(encoding="utf-8").splitlines() if "call" in line)

    wl.runj()
    first = call_count()
    got = wl.runj()
    second = call_count()
    why = "cache did not hold: calls=%d,%d out=%s" % (first, second, got.out[:200])
    assert (first, second) == (1, 1), why
    assert "cached" in got.out, why

    wl.task(7, "in_progress", "merge the chain")
    wl.newturn()
    wl.say("answer\n\n## Remaining\n| #7 | merge the chain | ongoing, me |")
    wl.runj()
    third = call_count()
    assert third == 2, "CONTROL: a changed world did not re-ask the judge: calls=%d" % third


DEADCODE_REFS = wlfix.STOP_DIR.parents[2] / ".ci" / "scripts" / "quality"
DEADCODE_GUARDS = wlfix.STOP_DIR.parents[1] / "rediacc_hooks" / "guards"


def orphan_defs(directory, refs) -> list[str]:
    """Top-level function defs in the shipped stop-hook modules that nothing names.

    THE REFERENCE HAYSTACK IS WIDER THAN THE DEF CORPUS, and it has to be. The defs still come only from the shipped stop-hook modules, which is what is being policed, but a legitimate CONSUMER of this directory lives outside it: `.ci/scripts/quality/check_plan_boxes.py` and `check_plan_record.py` both import these modules by design (a gate that re-implemented the plan parser would
    drift from the Stop hook, which is exactly what importing prevents). Measured 2026-09-06: `wl_planrec.ledger_at`, `render_index` and `index_rows` are called ONLY from `check_plan_record.py`, and this gate reported all three as dead code. A gate that calls live code dead teaches the next session to DELETE it, which is more expensive than the shipped orphan it exists to catch.

    The haystack path is a PARAMETER and both call sites below pass the real tree, so the planted-orphan control is unaffected: a def named nowhere is named nowhere in either directory.
    """
    sources = {
        path.name: path.read_text(encoding="utf-8") for path in sorted(directory.glob("wl_*.py"))
    }
    sources["worklist.py"] = (directory / "worklist.py").read_text(encoding="utf-8")
    extra = []
    for path in sorted(refs.glob("check_*.py")):
        with contextlib.suppress(OSError):
            extra.append(path.read_text(encoding="utf-8"))
    # The hook GUARDS are the same kind of legitimate outside consumer: `guards/block_agent_cap.py` enforces the writer cap at spawn time by calling `wl_roster.live_writers_estimate`, so that it shares the Stop hook's number and reader types instead of re-deriving them. The planted-orphan control is unaffected, for the reason above.
    for path in sorted(DEADCODE_GUARDS.glob("block_*.py")):
        with contextlib.suppress(OSError):
            extra.append(path.read_text(encoding="utf-8"))
    haystack = "\n".join(list(sources.values()) + extra)
    # COUNTED ONCE OVER WORD TOKENS rather than once per def over the whole haystack. The bash ran `re.findall(r"\\b<name>\\b", haystack)` for each of roughly a thousand defs, which is the same answer computed a thousand times and took 103 seconds of this module's runtime. A `\\b`-delimited identifier matches exactly where that identifier appears as a maximal word token, so one
    # Counter over the tokens is the SAME count, not an approximation of it.
    seen = collections.Counter(re.findall(r"[A-Za-z0-9_]+", haystack))
    orphans = []
    for name, source in sources.items():
        # `seen[...] < 2` because the def line itself is one of the occurrences.
        orphans.extend(
            "%s.%s" % (name, node.name)
            for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and seen[node.name] < 2
        )
    return orphans


def test_143_the_dead_code_gate_every_top_level_def_is_referenced_somewhere(wl):  # noqa: F811
    """No unreferenced top-level function in the shipped modules, and PROVE THE INSTRUMENT: the same gate must FIRE on a planted orphan."""
    shipped = orphan_defs(wlfix.STOP_DIR, DEADCODE_REFS)
    assert not shipped, "dead code shipped: %s" % shipped

    planted = wl.base / "deadcode"
    planted.mkdir(parents=True, exist_ok=True)
    for path in [*wlfix.STOP_DIR.glob("wl_*.py"), wlfix.STOP_DIR / "worklist.py"]:
        shutil.copy(str(path), str(planted / path.name))
    with (planted / "wl_core.py").open("a", encoding="utf-8") as handle:
        handle.write("\n\ndef orphan_zombie_fn():\n    return 1\n")
    found = orphan_defs(planted, DEADCODE_REFS)
    assert found, "CONTROL: the dead-code gate cannot fire (a planted orphan passed)"
    assert any("orphan_zombie_fn" in name for name in found), (
        "CONTROL: the gate failed for the wrong reason: %s" % found
    )


def test_145_a_tick_flood_is_absorbed_as_bookkeeping(wl):  # noqa: F811
    """The v10 upgrade guard: tick identity hashes the RENDERED line, and the store rewrite can re-render history, so the first post-upgrade stop may see hundreds of historical `[x]` as new (791 in the live store). That is drift, not 791 simultaneous fixes: absorb with one note, and never route those lines into the I7 evidence check either."""
    wl.say("done for now")
    wl.brief_now()
    wl.reg_repo()
    wl.run()  # marker init at current HEAD with zero ticks
    for index in range(1, 26):
        wl.add_item("- [x] (deadbeef) historical item %d" % index)
    got = wl.run()
    assert got.decision == "allow", "tick flood mishandled (got=%s): %s" % (
        got.decision,
        got.out[:260],
    )
    assert "absorbed as bookkeeping" in got.out, (
        "25 suddenly-new ticks did not absorb with one note: %s" % got.out[:260]
    )
    again = wl.run()
    assert "absorbed as bookkeeping" not in again.out, "flood note repeated: %s" % again.out[:200]


def test_144_state_document_staleness_is_world_keyed(wl):  # noqa: F811
    """The v9 trap this kills: the 10-minute age limit was outpaced by the 5-minute poll cron, so a QUIET session went stale every other poll. Age alone is not staleness; the world signature must also have moved.

    The write stays INLINE rather than folded into `hand_now`, and the point of the case is that the task dir the stop will read is covered by the signature the `--state` write records. `wlfix.Fixture.python` passes WORKLIST_TASKS_DIR on every invocation, which is what makes the two signatures comparable here.
    """
    wl.brief_now()
    wl.task(7, "pending", "thing")
    wl.say("answer\n\n## Remaining\n| #7 | thing | pending, me |")
    wl.cli(
        "--state",
        "deadbeef",
        stdin=(
            "You are picking up the ci-overhaul session driving PR #543 to green on branch 0728-2. "
            "Round 23 went red on a dead-shell finding, now fixed by running the stop-gate suite "
            "from test-hooks.sh.\n\n## Next action\n\nPush and watch the run, then bump the "
            "submodule pointers to the squash commits before the merge chain closes out.\n"
        ),
    )
    wl.check("allow", "", "fresh STATE.md, settled world: allowed")
    # The heading stamp is the age source, not the file mtime.
    wl.age_state("deadbeef", 25)
    wl.check("allow", "", "an OLD STATE.md with an UNCHANGED world is NOT stale")

    # A NEW HARNESS TASK no longer stales it (P1.2, agent/plans/PLAN-stop-hook-continuity.md): task statuses and HEAD are not judgment facts. CONTROL: before 2026-09-24 this stop blocked.
    wl.task(8, "pending", "the new thing")
    wl.newturn()
    wl.say(
        "answer\n\n## Remaining\n| #7 | thing | pending, me |\n| #8 | the new thing | pending, me |"
    )
    wl.check("allow", "", "a new harness task alone does not stale an old STATE.md")
    # The owned item SET moving does.
    wl.add_item("- [x] (deadbeef) a finished piece of work")
    wl.newturn()
    wl.say(
        "answer\n\n## Remaining\n| #7 | thing | pending, me |\n| #8 | the new thing | pending, me |"
    )
    wl.check("block", "STATE.md is stale", "the same old STATE.md stales once the world moves")
    # 1.4: the verdict must name the CAUSE. It used to print only "(N min old, limit M)", and a session read that as pure wall-clock and concluded the code disagreed with its own documentation. The age is a symptom; the signature moving is the trigger, and a document a week old whose world never moved is never stale.
    got = wl.run()
    assert "your world signature moved since it was written" in got.out, (
        "212: the stale verdict does not say WHY: %s" % got.out[:300]
    )
