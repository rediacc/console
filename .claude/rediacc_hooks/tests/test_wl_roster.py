"""The parallel-writer roster: the controls for agent/plans/PLAN-parallel-writer-roster.md.

Two layers, both driven here. `wl_roster.roster()` is run DIRECTLY, in a subprocess carrying the fixture environment, for the verdict's own arithmetic (who is live, who writes, who is leased, who owes a status). The Stop hook is run END TO END through `wlfix` for what the verdict does to a real stop: the block keys, the HONEST allow, the poll forfeit.

EVERY FIRE CASE HAS A CONTROL THAT DIFFERS BY ONE PLANTED FACT, and several cases are the incident itself (plan F4 and F5): a lease on a finished parent whose child is still working is COVERED, not dead; a lease on a finished read-only survey with no live descendant IS dead.

The subagent fixtures are the harness's real shape, measured on 2026-09-24: `type: "subagent"` rows in the event, metas carrying `agentType`, `parentAgentId` and `spawnDepth` and NO `taskKind`, one `agent-<id>.jsonl` transcript per agent under `<projects>/<munged root>/<session>/subagents/`, located through `CLAUDE_CONFIG_DIR`.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import time

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

ROSTER_PY = wlfix.STOP_DIR / "wl_roster.py"
GUARD_PY = wlfix.STOP_DIR.parents[1] / "rediacc_hooks" / "guards" / "block_agent_cap.py"

# The subprocess that computes one verdict. It folds the fixture store exactly as the Stop hook does and prints the verdict as JSON.
VERDICT_SNIPPET = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import wl_core as C, wl_store as S, wl_roster as R
ev = json.loads(sys.stdin.read())
wl = C.worklist_for(C.project_start(ev))
fold = S.load(wl, sync=True)
v = R.roster(ev, fold, ev["session_id"], state_doc={}, cwd=ev["cwd"])
v["known_ids"] = sorted(v["known_ids"])
print(json.dumps(v, default=str))
"""


def stamp(minutes_ago: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - minutes_ago * 60))


def until(minutes_ahead: float = 60) -> str:
    return time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(time.time() + minutes_ahead * 60))


def backdate(path, minutes: float) -> None:
    old = time.time() - minutes * 60
    os.utime(path, (old, old))


def subagents_dir(fix):
    root = fix.base / "claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(fix.proj))
    return root / wlfix.SID / "subagents"


def mk_sub(
    fix,
    aid: str,
    agent_type: str,
    age_min: float,
    parent: str | None = None,
    last: str = "tool_use",
    edits: bool = False,
    running: bool = True,
    send_min: float | None = None,
) -> None:
    """One subagent in today's harness shape: meta, transcript, and (when `running`) an event row.

    `last` is the transcript's final record: "tool_use" (mid-turn, in a tool call), "text" (a streaming partial, mid-turn with nothing in flight) or "end_turn" (finished). `age_min` backdates both the transcript and the meta, so it is the spawn age and the quiet time at once. `edits` plants an Edit tool call earlier in the transcript. `send_min` plants a SendMessage that many minutes ago.
    """
    folder = subagents_dir(fix)
    folder.mkdir(parents=True, exist_ok=True)
    meta = {"agentType": agent_type, "description": "fixture %s" % aid, "spawnDepth": 1}
    if parent:
        meta["parentAgentId"] = parent
        meta["spawnDepth"] = 2
    (folder / ("agent-%s.meta.json" % aid)).write_text(json.dumps(meta), encoding="utf-8")
    records = [{"type": "user", "message": {"content": "brief"}}]
    if edits:
        records.append(
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {}}]},
            }
        )
    if send_min is not None:
        records.append(
            {
                "type": "assistant",
                "timestamp": stamp(send_min).replace("Z", ".000Z"),
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "SendMessage",
                            "input": {"to": "main", "message": "progress"},
                        }
                    ]
                },
            }
        )
    if last == "tool_use":
        records.append(
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {}}]},
            }
        )
    elif last == "end_turn":
        records.append(
            {
                "type": "assistant",
                "message": {
                    "stop_reason": "end_turn",
                    "content": [{"type": "text", "text": "done"}],
                },
            }
        )
    else:
        records.append(
            {"type": "assistant", "message": {"content": [{"type": "text", "text": "…"}]}}
        )
    tx = folder / ("agent-%s.jsonl" % aid)
    tx.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    backdate(tx, age_min)
    backdate(folder / ("agent-%s.meta.json" % aid), age_min)
    fix.env["CLAUDE_CONFIG_DIR"] = str(fix.base / "claude")
    if running:
        rows = json.loads(fix.bg)
        rows.append(
            {
                "id": aid,
                "type": "subagent",
                "status": "running",
                "description": "fixture %s" % aid,
                "agent_type": agent_type,
            }
        )
        fix.bg = json.dumps(rows)


def plant_lease(fix, item_id: str, worker: str, lease_age_min: float = 5, owner: str = wlfix.ME):
    """An item and its lease, written straight into the store with the lease BACKDATED.

    Through the CLI the lease would be stamped now, and "a status 21 minutes old" could only be reached by sleeping. The store is append-only JSONL, so a backdated event is exactly what an old lease looks like.
    """
    with fix.events.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ev": "add",
                    "id": item_id,
                    "at": stamp(lease_age_min + 1),
                    "by": owner,
                    "s": " ",
                    "o": owner,
                    "t": "(%s) roster fixture item %s" % (owner, item_id),
                }
            )
            + "\n"
        )
        fh.write(
            json.dumps(
                {
                    "ev": "lease",
                    "id": item_id,
                    "at": stamp(lease_age_min),
                    "by": owner,
                    "until": until(),
                    "worker": worker,
                    "note": "",
                    "worker_verified": True,
                }
            )
            + "\n"
        )


def plant_unlease(fix, item_id: str) -> None:
    with fix.events.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps({"ev": "unlease", "id": item_id, "at": stamp(0), "by": wlfix.ME, "t": "x"})
            + "\n"
        )


def plant_status(fix, worker: str, age_min: float, silent: bool = False, size: int = 0) -> None:
    with fix.events.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ev": "status",
                    "worker": worker,
                    "at": stamp(age_min),
                    "by": wlfix.ME,
                    "size": size,
                    "mtime": time.time(),
                    "inflight": "",
                    "silent": silent,
                }
            )
            + "\n"
        )


def verdict(fix, extra_env: dict | None = None) -> dict:
    env = fix.stop_env(extra_env)
    proc = subprocess.run(
        [sys.executable, "-c", VERDICT_SNIPPET, str(wlfix.STOP_DIR)],
        input=fix.event(),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, "the verdict snippet failed: %s" % proc.stderr[-800:]
    return json.loads(proc.stdout)


def tx_size(fix, aid: str) -> int:
    return (subagents_dir(fix) / ("agent-%s.jsonl" % aid)).stat().st_size


W1, W2, W3, W4, W5 = (
    "a1000000000000001",
    "a1000000000000002",
    "a1000000000000003",
    "a1000000000000004",
    "a1000000000000005",
)
P1, P2 = "a2000000000000001", "a2000000000000002"


def honest_world(fix) -> None:
    """Three leased writers and one Plan reader, every lease 5 minutes old."""
    for i, aid in enumerate((W1, W2, W3)):
        mk_sub(fix, aid, "general-purpose", 3 - i)
        plant_lease(fix, "it%02d" % i, aid)
    mk_sub(fix, P1, "Plan", 1)


# ---- the verdict, driven directly -------------------------------------------------


def test_r1_an_honest_roster_is_honest_and_unleasing_one_item_makes_it_dishonest(wl):  # noqa: F811
    honest_world(wl)
    v = verdict(wl)
    assert v["state"] == "HONEST", v
    assert sorted(v["writers"]) == [W1, W2, W3], v["writers"]
    assert v["readers"] == [P1]
    for key in ("unleased", "leased_dead", "over_cap", "status_due", "silent"):
        assert v[key] == [], "%s: %r" % (key, v[key])
    # POSITIVE CONTROL, one planted fact: release one lease and that writer is unleased.
    plant_unlease(wl, "it01")
    v = verdict(wl)
    assert v["state"] == "DISHONEST", v["state"]
    assert v["unleased"] == [W2], v["unleased"]


def test_r2_an_unleased_live_writer_is_named_and_a_child_inherits_its_parents_lease(wl):  # noqa: F811
    mk_sub(wl, W1, "general-purpose", 2)
    v = verdict(wl)
    assert v["unleased"] == [W1], v
    # CONTROL: the same agent as the child of a leased live parent inherits the lease.
    wl.setup()
    mk_sub(wl, W2, "general-purpose", 5)
    plant_lease(wl, "par1", W2)
    mk_sub(wl, W1, "general-purpose", 2, parent=W2)
    v = verdict(wl)
    assert v["unleased"] == [], v["unleased"]
    assert v["state"] == "HONEST", v["state"]


def test_r3_a_lease_on_a_finished_worker_with_no_live_descendant_is_dead(wl):  # noqa: F811
    """Plan F5: a finished survey agent still holding a lease."""
    mk_sub(wl, W1, "general-purpose", 30, last="end_turn", running=False)
    plant_lease(wl, "dead1", W1)
    v = verdict(wl)
    assert [d[0] for d in v["leased_dead"]] == ["dead1"], v["leased_dead"]
    assert v["state"] == "DISHONEST"


def test_r3b_the_incident_lineage_a_finished_parent_with_a_live_child_is_covered(wl):  # noqa: F811
    """Plan F4: the parent is gone from the event, its child (by parentAgentId) is working. Not dead."""
    mk_sub(wl, W1, "general-purpose", 30, last="end_turn", running=False)
    plant_lease(wl, "par1", W1)
    mk_sub(wl, W2, "general-purpose", 1, parent=W1)
    v = verdict(wl)
    assert v["leased_dead"] == [], v["leased_dead"]
    assert v["covered"] == [["par1", W1, W2]], v["covered"]
    assert v["unleased"] == [], "the child inherits its parent's lease: %r" % v["unleased"]


def test_r3c_a_harness_listed_but_finished_writer_is_not_live(wl):  # noqa: F811
    """Listed by the harness but its transcript ended the turn: not LIVE, so its lease is dead."""
    mk_sub(wl, W1, "general-purpose", 5, last="end_turn")
    plant_lease(wl, "fin1", W1)
    v = verdict(wl)
    assert v["finished"] == [W1], v["finished"]
    assert [d[0] for d in v["leased_dead"]] == ["fin1"]


def plant_shell_wait(fix, aid: str, shell_id: str, running: bool = True) -> None:
    """The waiter shape: the agent's transcript launched background shell `shell_id` before ending its turn, and (when `running`) the event lists that shell as still running with no owner."""
    tx = subagents_dir(fix) / ("agent-%s.jsonl" % aid)
    st = tx.stat()
    launch = {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "content": "Command running in background with ID: %s." % shell_id,
                }
            ]
        },
        "toolUseResult": {"backgroundTaskId": shell_id},
    }
    lines = tx.read_text(encoding="utf-8").splitlines(keepends=True)
    tx.write_text(
        "".join(lines[:-1]) + json.dumps(launch, separators=(",", ":")) + "\n" + lines[-1],
        encoding="utf-8",
    )
    os.utime(tx, (st.st_atime, st.st_mtime))
    if running:
        rows = json.loads(fix.bg)
        rows.append(
            {"id": shell_id, "type": "shell", "status": "running", "description": "receipt run"}
        )
        fix.bg = json.dumps(rows)


def test_r3d_an_agent_waiting_on_its_own_running_shell_is_live_and_fills_a_slot(wl):  # noqa: F811
    """The 2026-09-24 flicker: the babysitter ended its turn waiting on receipt shell bp0oujd2w, the event listed only the shell, and the roster called it finished while a queued item read a free slot."""
    for i, aid in enumerate((W1, W2, W3)):
        mk_sub(wl, aid, "general-purpose", 10 - i)
        plant_lease(wl, "cap%d" % i, aid)
    mk_sub(wl, W4, "pr-babysitter", 30, last="end_turn", running=False)
    plant_shell_wait(wl, W4, "bshell01")
    plant_lease(wl, "wait1", W4)
    plant_lease(wl, "queued1", "queue")
    v = verdict(wl)
    assert v["leased_dead"] == [], v["leased_dead"]
    assert W4 in v["writers"], v["writers"]
    assert ("queued1", "queue", "queue") in [tuple(c) for c in v["covered"]], v["covered"]


def test_r3e_a_waiter_whose_shell_is_gone_is_finished(wl):  # noqa: F811
    """The control's other edge: the same transcript with the shell no longer running is a dead lease, so the waiter rule cannot keep a finished agent alive."""
    mk_sub(wl, W4, "pr-babysitter", 30, last="end_turn", running=False)
    plant_shell_wait(wl, W4, "bshell01", running=False)
    plant_lease(wl, "wait1", W4)
    v = verdict(wl)
    assert [d[0] for d in v["leased_dead"]] == ["wait1"], v["leased_dead"]


WORKFLOW_FACTS_SNIPPET = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import wl_liveness as L
row = {"id": "wtest0001", "type": "workflow", "status": "running", "description": "wf", "name": "demo-flow"}
print(json.dumps(L.bg_output_facts(sys.argv[2], sys.argv[3], [row])))
"""


def workflow_facts(fix, agent_age_min: float | None):
    """bg_output_facts for one running workflow whose run dir holds one agent transcript `agent_age_min` old (None: no run dir at all)."""
    sub = subagents_dir(fix)
    sub.mkdir(parents=True, exist_ok=True)
    fix.env["CLAUDE_CONFIG_DIR"] = str(fix.base / "claude")
    if agent_age_min is not None:
        scripts = sub.parent / "workflows" / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        (scripts / "demo-flow-wf_abc123-def.js").write_text(
            "export const meta = {}\n", encoding="utf-8"
        )
        run = sub / "workflows" / "wf_abc123-def"
        run.mkdir(parents=True, exist_ok=True)
        tx = run / "agent-a1.jsonl"
        tx.write_text("{}\n", encoding="utf-8")
        backdate(tx, agent_age_min)
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            WORKFLOW_FACTS_SNIPPET,
            str(wlfix.STOP_DIR),
            str(fix.proj),
            wlfix.SID,
        ],
        capture_output=True,
        text=True,
        env=fix.stop_env(),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    return json.loads(proc.stdout)[0]


def test_r9_a_running_workflow_is_judged_by_its_agents_transcripts(wl):  # noqa: F811
    """2026-09-24: a workflow's own .output stays empty until it returns, so every live workflow read POSSIBLY STUCK. Its agents' transcripts are the stream."""
    tid, _desc, age, size, stale = workflow_facts(wl, 1)
    assert tid == "wtest0001", tid
    assert age is not None, "no stream found for the workflow"
    assert age <= 2, age
    assert size > 0, size
    assert stale is False, (age, stale)


def test_r9b_a_workflow_whose_agents_went_quiet_is_stale(wl):  # noqa: F811
    """The control: the same run with its only transcript 30 minutes old must still read stale, so r9 cannot pass vacuously."""
    _tid, _desc, age, _size, stale = workflow_facts(wl, 30)
    assert stale is True, (age, stale)
    assert age >= 29, age


WORKER_FACTS_SNIPPET = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import wl_liveness as L
ev = {"cwd": sys.argv[2], "background_tasks": [
    {"id": "wtest0001", "type": "workflow", "status": "running", "description": "wf", "name": "demo-flow"}]}
rows = L.worker_facts(ev, sys.argv[3])
print(json.dumps(rows[0] if isinstance(rows, tuple) else rows))
"""


def test_r9c_the_roster_line_reads_a_workflow_by_its_agents_too(wl):  # noqa: F811
    """`worker_facts` is the second reader of a workflow's quiet time; it read the empty .output and printed 'output quiet 65m' for a live workflow on 2026-09-24."""
    workflow_facts(wl, 1)
    proc = subprocess.run(
        [sys.executable, "-c", WORKER_FACTS_SNIPPET, str(wlfix.STOP_DIR), str(wl.proj), wlfix.SID],
        capture_output=True,
        text=True,
        env=wl.stop_env(),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    line = next(r for r in json.loads(proc.stdout) if "wtest0001" in r)
    assert "output quiet 1m" in line or "output quiet 0m" in line, line


def test_r4_five_leased_writers_exceed_the_cap_and_the_newest_is_the_excess(wl):  # noqa: F811
    for i, aid in enumerate((W1, W2, W3, W4, W5)):
        mk_sub(wl, aid, "general-purpose", 10 - i)
        plant_lease(wl, "cap%d" % i, aid)
    v = verdict(wl)
    assert len(v["writers"]) == 5, v["writers"]
    assert v["over_cap"] == [W5], v["over_cap"]
    assert v["state"] == "DISHONEST"


def test_r4b_four_writers_and_two_plan_agents_are_within_the_cap(wl):  # noqa: F811
    for i, aid in enumerate((W1, W2, W3, W4)):
        mk_sub(wl, aid, "general-purpose", 10 - i)
        plant_lease(wl, "cap%d" % i, aid)
    mk_sub(wl, P1, "Plan", 1)
    mk_sub(wl, P2, "Explore", 1)
    v = verdict(wl)
    assert v["over_cap"] == [], v["over_cap"]
    assert sorted(v["readers"]) == [P1, P2]


def test_r4q_a_queued_item_is_covered_only_while_the_cap_is_full(wl):  # noqa: F811
    """`worker:queue` holds writer work the cap forbids starting; it must never park work behind a cap that is not full."""
    for i, aid in enumerate((W1, W2, W3, W4)):
        mk_sub(wl, aid, "general-purpose", 10 - i)
        plant_lease(wl, "cap%d" % i, aid)
    plant_lease(wl, "queued1", "queue")
    v = verdict(wl)
    assert ("queued1", "queue", "queue") in [tuple(c) for c in v["covered"]], v["covered"]
    assert v["leased_dead"] == [], v["leased_dead"]


def test_r4q3_a_queued_item_never_owes_a_status(wl):  # noqa: F811
    """`queue` has no transcript and cannot report, so an old queue lease must not raise WORKER STATUS DUE (2026-09-24: it blocked a stop with no remedy)."""
    for i, aid in enumerate((W1, W2, W3, W4)):
        mk_sub(wl, aid, "general-purpose", 10 - i)
        plant_lease(wl, "cap%d" % i, aid)
    plant_lease(wl, "queued1", "queue", lease_age_min=25)
    v = verdict(wl)
    assert "queue" not in v["status_due"], v["status_due"]
    assert ("queued1", "queue", "queue") in [tuple(c) for c in v["covered"]], v["covered"]


def test_r4q2_a_queued_item_with_a_free_slot_is_a_defect(wl):  # noqa: F811
    for i, aid in enumerate((W1, W2, W3)):
        mk_sub(wl, aid, "general-purpose", 10 - i)
        plant_lease(wl, "cap%d" % i, aid)
    plant_lease(wl, "queued1", "queue")
    v = verdict(wl)
    assert [tuple(d)[:2] for d in v["leased_dead"]] == [("queued1", "queue")], v["leased_dead"]
    assert v["state"] == "DISHONEST"


def test_r4c_a_depth_two_writer_child_counts_toward_the_cap(wl):  # noqa: F811
    for i, aid in enumerate((W1, W2, W3, W4)):
        mk_sub(wl, aid, "general-purpose", 10 - i)
        plant_lease(wl, "cap%d" % i, aid)
    mk_sub(wl, W5, "general-purpose", 1, parent=W1)
    v = verdict(wl)
    assert v["over_cap"] == [W5], v["over_cap"]


def test_r4d_a_plan_agent_that_edits_is_a_writer(wl):  # noqa: F811
    """A type that claims read-only is promoted by an edit tool call in its own transcript."""
    mk_sub(wl, P1, "Plan", 1, edits=True)
    v = verdict(wl)
    assert v["writers"] == [P1], v
    assert v["unleased"] == [P1]


def test_r5_a_status_21_minutes_old_is_due_and_19_is_not(wl):  # noqa: F811
    mk_sub(wl, W1, "general-purpose", 0)
    plant_lease(wl, "st1", W1, lease_age_min=21)
    v = verdict(wl)
    assert v["status_due"] == [W1], v["status_due"]
    wl.setup()
    mk_sub(wl, W1, "general-purpose", 0)
    plant_lease(wl, "st1", W1, lease_age_min=19)
    v = verdict(wl)
    assert v["status_due"] == [], v["status_due"]


def test_r5b_a_grown_status_event_resets_the_clock_and_a_silent_one_does_not(wl):  # noqa: F811
    mk_sub(wl, W1, "general-purpose", 0)
    plant_lease(wl, "st1", W1, lease_age_min=40)
    plant_status(wl, W1, 2, silent=False, size=tx_size(wl, W1) - 1)
    v = verdict(wl)
    assert v["status_due"] == [], v
    assert v["silent"] == [], v
    # CONTROL: the same status, recorded SILENT against the current size, leaves the clock alone and marks the worker silent.
    wl.setup()
    mk_sub(wl, W1, "general-purpose", 0)
    plant_lease(wl, "st1", W1, lease_age_min=40)
    plant_status(wl, W1, 2, silent=True, size=tx_size(wl, W1))
    v = verdict(wl)
    assert v["status_due"] == [W1], v["status_due"]
    assert v["silent"] == [W1], v["silent"]


def test_r5c_a_workers_own_sendmessage_is_a_status(wl):  # noqa: F811
    mk_sub(wl, W1, "general-purpose", 0, send_min=3)
    plant_lease(wl, "st1", W1, lease_age_min=40)
    v = verdict(wl)
    assert v["status_due"] == [], v["status_due"]
    assert "SendMessage" in v["rows"][W1]["status_src"], v["rows"][W1]


def test_r5d_a_quiet_transcript_with_nothing_in_flight_is_silent_and_a_long_tool_call_is_not(wl):  # noqa: F811
    mk_sub(wl, W1, "general-purpose", 25, last="text")
    plant_lease(wl, "q1", W1, lease_age_min=5)
    v = verdict(wl)
    assert v["silent"] == [W1], v["silent"]
    wl.setup()
    mk_sub(wl, W1, "general-purpose", 25, last="tool_use")
    plant_lease(wl, "q1", W1, lease_age_min=5)
    v = verdict(wl)
    assert v["silent"] == [], "a 25-minute tool call is not silence: %r" % v["silent"]


def test_r6_no_environment_variable_moves_the_cap_or_the_ping(wl):  # noqa: F811
    for i, aid in enumerate((W1, W2, W3, W4, W5)):
        mk_sub(wl, aid, "general-purpose", 10 - i)
        plant_lease(wl, "cap%d" % i, aid, lease_age_min=21)
    hatches = {
        "WORKLIST_WRITER_CAP": "99",
        "WORKLIST_STATUS_PING_MIN": "999",
        "WORKLIST_ROSTER": "off",
        "WORKLIST_FOCUS": "off",
        "WORKLIST_CADENCE": "off",
        "WORKLIST_LADDER_PING_MIN": "9999",
        "WORKLIST_LADDER_INVESTIGATE_MIN": "9999",
        "WORKLIST_LADDER_RESOLVE_MIN": "9999",
        "WORKLIST_BG_REPORT_MIN": "9999",
        "WORKLIST_TEAMMATE_FRESH_MIN": "9999",
        "WORKLIST_IDLE_EDGE_EPSILON_S": "999999",
        "WORKLIST_TEAMMATE_TAIL_BYTES": "0",
    }
    v = verdict(wl, hatches)
    assert v["over_cap"] == [W5], v["over_cap"]
    assert len(v["status_due"]) == 5, v["status_due"]


def test_r6b_the_sealed_modules_read_no_environment_and_the_limits_are_literals():
    for path in (ROSTER_PY, GUARD_PY):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not ({"environ", "getenv"} & (names | attrs)), "%s reads the environment" % path
    consts = {}
    for stmt in ast.parse(ROSTER_PY.read_text(encoding="utf-8")).body:
        if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name):
            consts[stmt.targets[0].id] = stmt.value
    for name, want in (("WRITER_CAP", 4), ("STATUS_PING_MIN", 20)):
        node = consts.get(name)
        shown = ast.unparse(node) if node is not None else "absent"
        assert isinstance(node, ast.Constant), "%s is %s" % (name, shown)
        assert node.value == want, "%s is %s" % (name, shown)


def test_r7_a_blind_store_is_unknown_never_honest(wl):  # noqa: F811
    """No projects store at all: the roster cannot see a single meta, so it claims nothing."""
    wl.bg = json.dumps(
        [{"id": W1, "type": "subagent", "status": "running", "agent_type": "general-purpose"}]
    )
    plant_lease(wl, "b1", W1)
    wl.env["CLAUDE_CONFIG_DIR"] = str(wl.base / "no-such-config")
    v = verdict(wl)
    assert v["blind"] is True
    assert v["state"] != "HONEST", v["state"]


def test_r7b_an_empty_roster_is_not_honest(wl):  # noqa: F811
    """Nothing running and nothing leased must not stand the stuck detector down."""
    (subagents_dir(wl)).mkdir(parents=True, exist_ok=True)
    wl.env["CLAUDE_CONFIG_DIR"] = str(wl.base / "claude")
    v = verdict(wl)
    assert v["state"] == "UNKNOWN", v["state"]


# ---- the Stop hook, end to end ----------------------------------------------------

SAID = "writers are working\n\n## Remaining\n- #it00 #it01 #it02 leased to live writers (in flight)"


def seed_bgwait(fix, at: str = "2026-01-01T00:00:00Z") -> None:
    """Backdate the 15-minute check-in clock, so a stop that would owe it really does."""
    path = fix.stem(".state-deadbeef.json")
    assert path.is_file(), "FIXTURE BROKEN: no state doc at %s" % path
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["bgwait"] = {"at": at}
    path.write_text(json.dumps(doc), encoding="utf-8")


def overdue(fix, extra_env: dict | None = None):
    """Two stops: the first seeds the check-in clock, the second is overdue for it."""
    fix.say(SAID)
    fix.run(extra_env)
    seed_bgwait(fix)
    fix.newturn()
    fix.say(SAID)
    return fix.run(extra_env)


def stop_world(fix, lease_age_min: float = 5) -> None:
    fix.brief_now()
    fix.hand_now()
    for i, aid in enumerate((W1, W2, W3)):
        mk_sub(fix, aid, "general-purpose", 0)
        plant_lease(fix, "it%02d" % i, aid, lease_age_min=lease_age_min)
    mk_sub(fix, P1, "Plan", 0)


def test_s1_an_honest_roster_allows_with_the_roster_and_without_the_old_pushes(wl):  # noqa: F811
    stop_world(wl)
    got = overdue(wl)
    assert got.decision == "allow", wl.why("s1", "allow", got, "ROSTER HONEST")
    assert "ROSTER HONEST: 3 writer(s)/4, 1 reader(s)" in got.out, got.out[:600]
    for needle in ("PURE BACKGROUND WAIT", "IN-FLIGHT WORK", "NOTHING HAS MOVED"):
        assert needle not in got.out, "s1: %r still pushed: %s" % (needle, got.out[:600])
    # POSITIVE CONTROL, one planted fact: release one lease and the same stop blocks, naming the writer.
    plant_unlease(wl, "it01")
    wl.newturn()
    wl.say(SAID)
    got = wl.run()
    assert got.decision == "block", got.out[:400]
    assert "UNLEASED WRITER" in got.out, got.out[:800]
    assert W2 in got.out, got.out[:800]


def test_s2_five_writers_block_on_the_cap_and_no_variable_lifts_it(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    for i, aid in enumerate((W1, W2, W3, W4, W5)):
        mk_sub(wl, aid, "general-purpose", 0)
        plant_lease(wl, "cap%d" % i, aid, lease_age_min=21)
    hatches = {
        "WORKLIST_WRITER_CAP": "99",
        "WORKLIST_STATUS_PING_MIN": "999",
        "WORKLIST_ROSTER": "off",
        "WORKLIST_FOCUS": "off",
        "WORKLIST_CADENCE": "off",
        "WORKLIST_LADDER_PING_MIN": "9999",
        "WORKLIST_LADDER_INVESTIGATE_MIN": "9999",
        "WORKLIST_LADDER_RESOLVE_MIN": "9999",
        "WORKLIST_BG_REPORT_MIN": "9999",
        "WORKLIST_TEAMMATE_FRESH_MIN": "9999",
    }
    for extra in (None, hatches):
        wl.say(SAID)
        got = wl.run(extra)
        label = "s2 (%s)" % ("hatches" if extra else "plain")
        assert got.decision == "block", wl.why(label, "block", got, "CAP")
        assert "PARALLEL-WRITER CAP EXCEEDED: 5 writer agent(s)" in got.out, got.out[:600]
        for aid in (W1, W2, W3, W4, W5):
            assert aid in got.out, "%s: the cap block does not name %s" % (label, aid)
        assert "TaskStop %s" % W5 in got.out, "%s: the newest writer is not the excess" % label
        assert "WORKER STATUS DUE" in got.out, "%s: the 21-minute ping is missing" % label
        wl.newturn()


def test_s2b_four_writers_and_two_readers_draw_no_cap_block(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    for i, aid in enumerate((W1, W2, W3, W4)):
        mk_sub(wl, aid, "general-purpose", 0)
        plant_lease(wl, "cap%d" % i, aid)
    mk_sub(wl, P1, "Plan", 0)
    mk_sub(wl, P2, "Explore", 0)
    wl.say(SAID)
    got = wl.run()
    assert "PARALLEL-WRITER CAP" not in got.out, got.out[:600]
    assert got.out.strip(), "the hook produced no output at all: %r" % got.err[:300]


def test_s3_a_due_ping_is_answered_by_status_on_a_grown_transcript(wl):  # noqa: F811
    stop_world(wl, lease_age_min=21)
    wl.say(SAID)
    got = wl.run()
    assert "WORKER STATUS DUE: 3 leased worker(s)" in got.out, got.out[:600]
    assert "--status deadbeef all" in got.out
    status = wl.cli("--status", wlfix.ME, "all")
    assert status.rc == 0, "--status failed: %s %s" % (status.out[:300], status.err[:300])
    assert "status recorded; the 20-minute clock restarts" in status.out, status.out[:600]
    assert "SILENT" not in status.out, status.out[:600]
    wl.newturn()
    wl.say(SAID)
    got = wl.run()
    assert "WORKER STATUS DUE" not in got.out, got.out[:600]
    assert got.decision == "allow", wl.why("s3 after --status", "allow", got, "ROSTER HONEST")


def test_s3b_status_on_a_transcript_that_did_not_grow_is_silent_and_blocks(wl):  # noqa: F811
    stop_world(wl, lease_age_min=21)
    wl.say(SAID)
    wl.run()
    first = wl.cli("--status", wlfix.ME, W1)
    assert first.rc == 0, first.out[:400]
    assert "status recorded" in first.out, first.out[:400]
    # Nothing written in between, and the transcript's last record is a streaming partial with no tool call in flight.
    tx = subagents_dir(wl) / ("agent-%s.jsonl" % W1)
    with tx.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {"type": "assistant", "message": {"content": [{"type": "text", "text": "hm"}]}}
            )
            + "\n"
        )
    wl.cli("--status", wlfix.ME, W1)  # grew: resets, and records the new size
    second = wl.cli("--status", wlfix.ME, W1)
    assert "SILENT" in second.out, (
        "an unchanged transcript was accepted as a status: %s" % second.out[:400]
    )
    wl.newturn()
    wl.say(SAID)
    got = wl.run()
    assert got.decision == "block", got.out[:400]
    assert "SILENT WORKER" in got.out, got.out[:800]
    assert W1 in got.out, got.out[:800]


def test_s5_the_incident_a_finished_parent_with_a_live_child_draws_neither_dead_nor_gone(wl):  # noqa: F811
    """Plan F4 end to end. The lease was VERIFIED against the harness when taken, the parent is now absent from the event, and its child (by parentAgentId) works on. The old ladder called that `gone`."""
    wl.brief_now()
    wl.hand_now()
    mk_sub(wl, W1, "general-purpose", 30, last="end_turn", running=False)
    plant_lease(wl, "par1", W1)
    mk_sub(wl, W2, "general-purpose", 0, parent=W1)
    wl.say(SAID)
    got = wl.run()
    assert got.out.strip(), "the hook produced no output: %r" % got.err[:300]
    for needle in (
        "LEASED TO A FINISHED WORKER",
        "is NOT in the harness background list",
        "UNLEASED WRITER",
    ):
        assert needle not in got.out, "s5: %r fired for a covered lease: %s" % (
            needle,
            got.out[:800],
        )
    # CONTROL, one planted fact: no child, and the same lease is dead, named by the roster rather than the ladder.
    wl.setup()
    wl.brief_now()
    wl.hand_now()
    mk_sub(wl, W1, "general-purpose", 30, last="end_turn", running=False)
    plant_lease(wl, "par1", W1)
    wl.say(SAID)
    got = wl.run()
    assert got.decision == "block", got.out[:400]
    assert "LEASED TO A FINISHED WORKER" in got.out, got.out[:800]
    assert "#par1" in got.out, got.out[:800]
    assert "is NOT in the harness background list" not in got.out, (
        "the ladder still claims a roster lease"
    )


def test_r8_verified_is_supervised_or_a_fresh_reader_never_a_stale_one(wl):  # noqa: F811
    """`verified` is what may stand the 15-minute check-in down. Leased writers are in it; an unleased reader is in it only while its own transcript moves."""
    honest_world(wl)
    v = verdict(wl)
    assert sorted(v["verified"]) == sorted([W1, W2, W3, P1]), v["verified"]
    # CONTROL, one planted fact: the reader's transcript has been quiet for the whole ping window.
    wl.setup()
    for i, aid in enumerate((W1, W2, W3)):
        mk_sub(wl, aid, "general-purpose", 3 - i)
        plant_lease(wl, "it%02d" % i, aid)
    mk_sub(wl, P1, "Plan", 21, last="text")
    v = verdict(wl)
    assert P1 not in v["verified"], "a reader quiet for 21 minutes was counted as verified"
    assert v["state"] == "HONEST", "an unleased reader is not a defect: %s" % v["state"]
