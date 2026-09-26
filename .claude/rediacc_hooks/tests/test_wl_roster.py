"""The parallel-writer roster: the controls for agent/plans/PLAN-parallel-writer-roster.md.

Two layers, both driven here. `wl_roster.roster()` is run DIRECTLY, in a subprocess carrying the fixture environment, for the verdict's own arithmetic (who is live, who writes, who is leased, who owes a status). The Stop hook is run END TO END through `wlfix` for what the verdict does to a real stop: the block keys, the HONEST allow, the poll forfeit.

EVERY FIRE CASE HAS A CONTROL THAT DIFFERS BY ONE PLANTED FACT, and several cases are the incident itself (plan F4 and F5): a lease on a finished parent whose child is still working is COVERED, not dead; a lease on a finished read-only survey with no live descendant IS dead.

The subagent fixtures are the harness's real shape, measured on 2026-09-24: `type: "subagent"` rows in the event, metas carrying `agentType`, `parentAgentId` and `spawnDepth` and NO `taskKind`, one `agent-<id>.jsonl` transcript per agent under `<projects>/<munged root>/<session>/subagents/`, located through `CLAUDE_CONFIG_DIR`.
"""

from __future__ import annotations

import ast
import json
import os
import pathlib
import re
import shutil
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
    prompt: str = "brief",
) -> None:
    """One subagent in today's harness shape: meta, transcript, and (when `running`) an event row.

    `last` is the transcript's final record: "tool_use" (mid-turn, in a tool call), "text" (a streaming partial, mid-turn with nothing in flight) or "end_turn" (finished). `age_min` backdates both the transcript and the meta, so it is the spawn age and the quiet time at once. `edits` plants an Edit tool call earlier in the transcript. `send_min` plants a SendMessage that many minutes ago. `prompt` is the first user record, which
    auto-lease and the plan-concurrency rules read (`Plan: PLAN-x.md`, `#<id>`).
    """
    folder = subagents_dir(fix)
    folder.mkdir(parents=True, exist_ok=True)
    meta = {"agentType": agent_type, "description": "fixture %s" % aid, "spawnDepth": 1}
    if parent:
        meta["parentAgentId"] = parent
        meta["spawnDepth"] = 2
    (folder / ("agent-%s.meta.json" % aid)).write_text(json.dumps(meta), encoding="utf-8")
    records = [{"type": "user", "message": {"content": prompt}}]
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


def plant_lease(
    fix,
    item_id: str,
    worker: str,
    lease_age_min: float = 5,
    owner: str = wlfix.ME,
    text: str | None = None,
):
    """An item and its lease, written straight into the store with the lease BACKDATED.

    Through the CLI the lease would be stamped now, and "a status 21 minutes old" could only be reached by sleeping. The store is append-only JSONL, so a backdated event is exactly what an old lease looks like. `text` replaces the item's default text, e.g. to link it to a plan with `PLAN-x.md [<8hex>]`.
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
                    "t": text or "(%s) roster fixture item %s" % (owner, item_id),
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


# ---- plans with the priority and concurrency header (agent/plans/PLAN-plan-priority-concurrency.md) ----

PLAN_TEXT = """# PLAN: %(name)s fixture

Status: %(status)s
Owner: %(owner)s
Depends-On: %(dep)s
%(x)s
## Tasks

- [ ] T1 a fixture box for %(name)s
"""


def write_plan(
    fix,
    name: str,
    status: str = "in-progress",
    priority: str | None = None,
    conc: str | None = "parallel",
    owns: str | None = None,
    dep: str = "no-dep -- a fixture plan that stands alone",
    owner: str = wlfix.ME,
) -> str:
    """`agent/plans/PLAN-<name>.md` under the fixture project, returning its basename. `owns` defaults to `src/<name>/**`, so fixture plans are disjoint unless a case says otherwise; None for any X field leaves the line out."""
    x = []
    if priority is not None:
        x.append("Priority: %s\n" % priority)
    if conc is not None:
        x.append("Concurrency: %s\n" % conc)
    owns = "src/%s/**" % name if owns is None else owns
    if owns:
        x.append("Owns: %s\n" % owns)
    folder = fix.proj / "agent" / "plans"
    folder.mkdir(parents=True, exist_ok=True)
    base = "PLAN-%s.md" % name
    (folder / base).write_text(
        PLAN_TEXT % {"name": name, "status": status, "owner": owner, "dep": dep, "x": "".join(x)},
        encoding="utf-8",
    )
    return base


def linked(plan: str, what: str = "work", owner: str = wlfix.ME) -> str:
    """An item text linked to `plan` by the `PLAN-x.md [<8hex>]` convention (wl_plandeps.linked_plan)."""
    return "(%s) %s %s [1a2b3c4d]" % (owner, what, plan)


def plant_item(fix, item_id: str, text: str, age_min: float = 5, owner: str = wlfix.ME) -> None:
    """One plain open item, its `first` stamp backdated by `age_min`."""
    with fix.events.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ev": "add",
                    "id": item_id,
                    "at": stamp(age_min),
                    "by": owner,
                    "s": " ",
                    "o": owner,
                    "t": text,
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


def verdict(fix, extra_env: dict | None = None, stop_dir=None) -> dict:
    """One roster verdict as the Stop hook computes it; `stop_dir` points it at a mutated private copy."""
    env = fix.stop_env(extra_env)
    proc = subprocess.run(
        [sys.executable, "-c", VERDICT_SNIPPET, str(stop_dir or wlfix.STOP_DIR)],
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
    # P1.7 (agent/plans/PLAN-stop-hook-continuity.md): a waiter ended its turn by definition, so its 30-minute-quiet transcript is not silence and it owes no status while its shell runs.
    assert W4 not in v["silent"], v["silent"]
    assert W4 not in v["status_due"], v["status_due"]


def test_r3e_a_waiter_whose_shell_is_gone_is_finished(wl):  # noqa: F811
    """The control's other edge: the same transcript with the shell no longer running is a dead lease, so the waiter rule cannot keep a finished agent alive."""
    mk_sub(wl, W4, "pr-babysitter", 30, last="end_turn", running=False)
    plant_shell_wait(wl, W4, "bshell01", running=False)
    plant_lease(wl, "wait1", W4)
    v = verdict(wl)
    assert [d[0] for d in v["leased_dead"]] == ["wait1"], v["leased_dead"]


def test_r3f_a_waiter_on_a_daemon_past_the_horizon_is_finished(wl):  # noqa: F811
    """2026-09-25, a5469082799b4a5af: a writer armed `./run.sh account dev` (a shell that never exits) and ended its turn. 1010 minutes later it still counted as a live writer and raised UNLEASED WRITER. Differs from r3d by one fact: the transcript is quiet past WAIT_HORIZON_MIN."""
    mk_sub(wl, W4, "general-purpose", 30, last="end_turn", running=False)
    plant_shell_wait(wl, W4, "bdaemon1")
    backdate(subagents_dir(wl) / ("agent-%s.jsonl" % W4), 1010)
    v = verdict(wl)
    assert W4 not in v["writers"], v["writers"]


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
    # Its own key since agent/plans/PLAN-stop-hook-retro-20260924.md R.5: a queue is not a finished worker.
    assert v["queue_start"] == ["queued1"], v["queue_start"]
    assert v["leased_dead"] == [], v["leased_dead"]
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


def test_r5_no_evidence_for_21_minutes_is_due_and_19_is_not(wl):  # noqa: F811
    """The 20-minute number is the operator's and stays; since 2026-09-24 ("Evidence counts as status") the transcript's own last write is evidence, so the fixture's transcript is as old as the lease."""
    mk_sub(wl, W1, "general-purpose", 21, last="text")
    plant_lease(wl, "st1", W1, lease_age_min=21)
    v = verdict(wl)
    assert v["status_due"] == [W1], v["status_due"]
    wl.setup()
    mk_sub(wl, W1, "general-purpose", 19, last="text")
    plant_lease(wl, "st1", W1, lease_age_min=19)
    v = verdict(wl)
    assert v["status_due"] == [], v["status_due"]


def test_r5e_a_growing_transcript_answers_the_ping_with_no_status_call(wl):  # noqa: F811
    """CONTROL for P1.4 (agent/plans/PLAN-stop-hook-continuity.md): a leased agent whose transcript was written a minute ago, with its lease and last --status 25 minutes old, owes nothing. Before the ruling this was `test_r5`'s due shape and blocked on `roster-status`."""
    mk_sub(wl, W1, "general-purpose", 1, last="text")
    plant_lease(wl, "st1", W1, lease_age_min=25)
    plant_status(wl, W1, 25, silent=False, size=1)
    v = verdict(wl)
    assert v["status_due"] == [], v["status_due"]
    assert v["silent"] == [], v["silent"]
    assert "transcript growth" in v["rows"][W1]["status_src"], v["rows"][W1]


def test_r5f_a_tool_call_in_flight_answers_the_ping(wl):  # noqa: F811
    """A worker 25 minutes inside one tool call writes nothing, and that is not silence (the other half of the ruling's evidence)."""
    mk_sub(wl, W1, "general-purpose", 25, last="tool_use")
    plant_lease(wl, "st1", W1, lease_age_min=25)
    v = verdict(wl)
    assert v["status_due"] == [], v["status_due"]
    assert "tool call in flight" in v["rows"][W1]["status_src"], v["rows"][W1]


def test_r5b_a_grown_status_event_resets_the_clock_and_a_silent_one_does_not(wl):  # noqa: F811
    # A status that saw growth 2 minutes ago means the transcript was written then, so the fixture's transcript is 2 minutes old.
    mk_sub(wl, W1, "general-purpose", 2, last="text")
    plant_lease(wl, "st1", W1, lease_age_min=40)
    plant_status(wl, W1, 2, silent=False, size=tx_size(wl, W1) - 1)
    v = verdict(wl)
    assert v["status_due"] == [], v
    assert v["silent"] == [], v
    # CONTROL: the same status, recorded SILENT against the current size, leaves the clock alone and marks the worker silent.
    wl.setup()
    mk_sub(wl, W1, "general-purpose", 40, last="text")
    plant_lease(wl, "st1", W1, lease_age_min=40)
    plant_status(wl, W1, 2, silent=True, size=tx_size(wl, W1))
    v = verdict(wl)
    assert v["status_due"] == [W1], v["status_due"]
    assert v["silent"] == [W1], v["silent"]


def test_r5c_a_workers_own_sendmessage_is_a_status(wl):  # noqa: F811
    mk_sub(wl, W1, "general-purpose", 25, last="text", send_min=3)
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
        mk_sub(wl, aid, "general-purpose", 30 - i, last="text")
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
        mk_sub(wl, aid, "general-purpose", 30 - i, last="text")
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
        assert "SILENT WORKER" in got.out, "%s: the 21-minute ping is missing" % label
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


def test_s3_evidence_answers_the_ping_with_no_status_call(wl):  # noqa: F811
    """P1.4 end to end (operator ruling 2026-09-24, "Evidence counts as status"): leases 21 minutes old, but every worker is inside a tool call, so the stop allows HONEST without a single --status."""
    stop_world(wl, lease_age_min=21)
    wl.say(SAID)
    got = wl.run()
    assert "SILENT WORKER" not in got.out, got.out[:600]
    assert got.decision == "allow", wl.why("s3", "allow", got, "ROSTER HONEST")
    assert "ROSTER HONEST" in got.out, got.out[:600]


def test_s3c_inverse_no_evidence_for_21_minutes_blocks_as_one_silent_key(wl):  # noqa: F811
    """INVERSE: the same world with every transcript 21 minutes quiet and nothing in flight blocks, once, under `roster-silent`; the merged `roster-status` key never appears."""
    wl.brief_now()
    wl.hand_now()
    for i, aid in enumerate((W1, W2, W3)):
        mk_sub(wl, aid, "general-purpose", 21, last="text")
        plant_lease(wl, "it%02d" % i, aid, lease_age_min=21)
    wl.say(SAID)
    got = wl.run()
    assert got.decision == "block", got.out[:400]
    assert "SILENT WORKER: 3 supervised agent(s)" in got.out, got.out[:800]
    assert "WORKER STATUS DUE" not in got.out, got.out[:800]


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


# ---- the liveness siblings (agent/plans/PLAN-stop-hook-continuity.md P1.6-P1.9, and the lead's two notes) ----


def lastevent_file(fix):
    return fix.wl.with_suffix(".lastevent-deadbeef.json")


def waiting_since_the_event(fix) -> str:
    """Three live writers, plus W4: listed running when the last Stop event was written, and since then ended its turn to wait on shell `bshell09`, which that event never saw. Returns an open item id to lease."""
    for i, aid in enumerate((W1, W2, W3)):
        mk_sub(fix, aid, "general-purpose", 1)
        plant_lease(fix, "cap%d" % i, aid)
    mk_sub(fix, W4, "pr-babysitter", 3, last="end_turn")
    lastevent_file(fix).write_text(fix.event(), encoding="utf-8")
    plant_shell_wait(fix, W4, "bshell09", running=False)
    added = fix.cli("--add", wlfix.ME, "(deadbeef) writer work held behind the cap")
    assert added.rc == 0, added.err[:300]
    found = re.search(r"#([0-9a-f]+)", added.out)
    assert found, added.out[:200]
    return found.group(1)


ESTIMATE_SNIPPET = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import wl_roster as R
print(json.dumps([r["id"] for r in R.live_writers_estimate(sys.argv[2], sys.argv[3])]))
"""


def test_q1_a_writer_waiting_since_the_last_event_still_fills_its_slot(wl):  # noqa: F811
    """The lead's note of 2026-09-24: `--lease worker:queue` refused ("3 of 4 busy") in the same minute the spawn guard blocked at 4 of 4, because the estimate read a waiting agent as finished until the next stop refreshed the event. Both callers read `live_writers_estimate`; the lease is the real verb driven here."""
    item = waiting_since_the_event(wl)
    got = wl.cli("--lease", wlfix.ME, item, "+30", "worker:queue", "held for the cap")
    assert got.rc == 0, "the queue lease was refused with the cap full: %s %s" % (
        got.out[:300],
        got.err[:300],
    )
    proc = subprocess.run(
        [sys.executable, "-c", ESTIMATE_SNIPPET, str(wlfix.STOP_DIR), str(wl.proj), wlfix.SID],
        capture_output=True,
        text=True,
        env=wl.stop_env(),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-600:]
    assert W4 in json.loads(proc.stdout), proc.stdout


def test_q1b_control_a_shell_already_reported_back_frees_the_slot(wl):  # noqa: F811
    """CONTROL: the same agent whose transcript carries the shell's completion notification is finished, so the slot is free and the queue lease is refused with the reservation hint."""
    item = waiting_since_the_event(wl)
    tx = subagents_dir(wl) / ("agent-%s.jsonl" % W4)
    st = tx.stat()
    lines = tx.read_text(encoding="utf-8").splitlines(keepends=True)
    note = {
        "type": "user",
        "message": {
            "content": "<task-notification>\n<task-id>bshell09</task-id>\n<status>completed</status>"
        },
    }
    tx.write_text("".join(lines[:-1]) + json.dumps(note) + "\n" + lines[-1], encoding="utf-8")
    os.utime(tx, (st.st_atime, st.st_mtime))
    got = wl.cli("--lease", wlfix.ME, item, "+30", "worker:queue", "held for the cap")
    assert got.rc != 0, got.out[:300]
    assert "3 of 4 writer slots are busy" in got.err, got.err[:400]
    assert "spawn that writer first" in got.err, got.err[:400]


def _shell_stream(wl, text):  # noqa: F811
    """Plant the harness's `tasks/bshell09.output` for the waiter's shell where `shell_ended` derives it from the transcript path, under the fixture's own TMPDIR (the roster reads no other environment). The caller removes it."""
    tx = subagents_dir(wl) / ("agent-%s.jsonl" % W4)
    d = (
        pathlib.Path(wl.env["TMPDIR"])
        / ("claude-%d" % os.getuid())
        / tx.parents[2].name
        / tx.parents[1].name
        / "tasks"
    )
    d.mkdir(parents=True, exist_ok=True)
    (d / "bshell09.output").write_text(text, encoding="utf-8")
    return d.parent


def test_q1c_a_shell_whose_stream_ended_frees_the_slot_without_a_notification(wl):  # noqa: F811
    """A shell killed or exited AFTER its agent finished never reports back into that transcript. Its own stream's terminal marker is the proof (2026-09-25: a finished writer held a slot 67 minutes on a `[killed]` shell)."""
    item = waiting_since_the_event(wl)
    for marker in ("partial output\n[killed]\n", "done\n\n[exited with code 0]\n"):
        planted = _shell_stream(wl, marker)
        try:
            got = wl.cli("--lease", wlfix.ME, item, "+30", "worker:queue", "held for the cap")
        finally:
            shutil.rmtree(planted, ignore_errors=True)
        assert got.rc != 0, (marker, got.out[:300])
        assert "3 of 4 writer slots are busy" in got.err, got.err[:400]


def test_q1d_control_a_stream_still_growing_keeps_the_agent_waiting(wl):  # noqa: F811
    """INVERSE: a stream with no terminal marker is a shell still running, so the agent still fills its slot."""
    item = waiting_since_the_event(wl)
    planted = _shell_stream(wl, "step 3 of 9 ...\n")
    try:
        got = wl.cli("--lease", wlfix.ME, item, "+30", "worker:queue", "held for the cap")
    finally:
        shutil.rmtree(planted, ignore_errors=True)
    assert got.rc == 0, got.err[:400]


def estimate(fix) -> list:
    proc = subprocess.run(
        [sys.executable, "-c", ESTIMATE_SNIPPET, str(wlfix.STOP_DIR), str(fix.proj), wlfix.SID],
        capture_output=True,
        text=True,
        env=fix.stop_env(),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-600:]
    return json.loads(proc.stdout)


def test_q3_a_stopped_agent_quiet_since_the_event_frees_its_slot(wl):  # noqa: F811
    """#b9d4dcb2, 2026-09-24: after TaskStop on the pr-babysitter, the spawn guard kept counting it for WAIT_HORIZON_MIN. The event no longer listed it or its shell, yet its transcript still ended "waiting on a shell" that had died with it. A transcript that has not moved since the event was written is the event's to judge."""
    mk_sub(wl, W4, "pr-babysitter", 5, last="end_turn", running=False)
    plant_shell_wait(wl, W4, "bshell77", running=False)
    lastevent_file(wl).write_text(wl.event(), encoding="utf-8")
    assert W4 not in estimate(wl)
    # CONTROL: the same waiter whose transcript moved AFTER the event armed its shell after it, which the event cannot know, so it still fills a slot.
    tx = subagents_dir(wl) / ("agent-%s.jsonl" % W4)
    future = time.time() + 60
    os.utime(tx, (future, future))
    assert W4 in estimate(wl)


def test_q2_an_expired_lease_on_a_waiter_stays_in_flight(wl):  # noqa: F811
    """P1.8: the event lists only the waiter's shell, so an expired lease on the waiting agent failed closed into an open item while the roster called the same agent live."""
    wl.brief_now()
    wl.hand_now()
    mk_sub(wl, W4, "pr-babysitter", 30, last="end_turn", running=False)
    plant_shell_wait(wl, W4, "bshell01")
    plant_lease(wl, "wait1", W4)
    with wl.events.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ev": "lease",
                    "id": "wait1",
                    "at": stamp(3),
                    "by": wlfix.ME,
                    "until": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(time.time() - 120)),
                    "worker": W4,
                    "note": "",
                    "worker_verified": True,
                }
            )
            + "\n"
        )
    wl.say(SAID)
    got = wl.run()
    assert "lease expired; finish it" not in got.out, (
        "P1.8: the waiter's lease failed closed: %s" % got.out[:800]
    )
    assert "auto-honored" in got.out, got.out[:800]


def test_q2b_control_the_same_expired_lease_with_the_shell_gone_fails_closed(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    mk_sub(wl, W4, "pr-babysitter", 30, last="end_turn", running=False)
    plant_shell_wait(wl, W4, "bshell01", running=False)
    plant_lease(wl, "wait1", W4)
    with wl.events.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ev": "lease",
                    "id": "wait1",
                    "at": stamp(3),
                    "by": wlfix.ME,
                    "until": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(time.time() - 120)),
                    "worker": W4,
                    "note": "",
                    "worker_verified": True,
                }
            )
            + "\n"
        )
    wl.say(SAID)
    got = wl.run()
    assert "lease expired; finish it" in got.out, got.out[:800]


def workflow_world(fix, agent_age_min: float) -> None:
    workflow_facts(fix, agent_age_min)
    fix.bg = json.dumps(
        [
            {
                "id": "wtest0001",
                "type": "workflow",
                "status": "running",
                "description": "wf",
                "name": "demo-flow",
            }
        ]
    )


def test_q3_a_lease_on_a_streaming_workflow_is_covered(wl):  # noqa: F811
    """P1.9: `worker:<workflow id>` on a live, fresh workflow is covered. Before, it read `unknown: no meta and not in the event`, which was false, and dropped the roster to UNKNOWN."""
    workflow_world(wl, 1)
    plant_lease(wl, "wf1", "wtest0001")
    v = verdict(wl)
    assert ("wf1", "wtest0001", "wtest0001") in [tuple(c) for c in v["covered"]], v
    assert v["unknown"] == [], v["unknown"]
    assert "wtest0001" not in v["status_due"], v["status_due"]


def test_q3b_control_a_workflow_whose_agents_went_quiet_is_not_covered(wl):  # noqa: F811
    workflow_world(wl, 30)
    plant_lease(wl, "wf1", "wtest0001")
    v = verdict(wl)
    assert [tuple(u)[:2] for u in v["unknown"]] == [("wf1", "wtest0001")], v["unknown"]


def test_q3c_a_workflow_agent_that_edits_counts_toward_the_cap(wl):  # noqa: F811
    """P1.9's second half: `load_metas` reads `subagents/workflows/<runId>/` too, so a workflow agent is visible to the writer cap."""
    workflow_world(wl, 1)
    run = subagents_dir(wl) / "workflows" / "wf_abc123-def"
    (run / "agent-a3000000000000001.meta.json").write_text(
        json.dumps({"agentType": "general-purpose", "description": "wf writer"}), encoding="utf-8"
    )
    snippet = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import wl_roster as R
print(json.dumps(sorted(R.load_metas(R.session_subagents_dir(sys.argv[2], sys.argv[3])))))
"""
    proc = subprocess.run(
        [sys.executable, "-c", snippet, str(wlfix.STOP_DIR), str(wl.proj), wlfix.SID],
        capture_output=True,
        text=True,
        env=wl.stop_env(),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-600:]
    assert "a3000000000000001" in json.loads(proc.stdout), proc.stdout


def test_q4_a_pure_wait_on_a_streaming_workflow_draws_no_check_in(wl):  # noqa: F811
    """P1.6: `all_waits_live` answered only subagents, teammates and confirmed shells, so the 15-minute check-in fired on a healthy, streaming workflow."""
    wl.brief_now()
    wl.hand_now()
    workflow_world(wl, 1)
    got = overdue(wl)
    assert "PURE BACKGROUND WAIT" not in got.out, got.out[:800]


def test_q4b_inverse_a_pure_wait_on_a_quiet_workflow_still_checks_in(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    workflow_world(wl, 30)
    got = overdue(wl)
    assert "PURE BACKGROUND WAIT" in got.out, got.out[:800]


# ---- R20260925.5: a queued item waiting on another is skipped, not started ----------------------------

BLOCKER = "b10c0001"


def plant_queued(fix, item_id: str, text: str, age_min: float, expired: bool = False) -> None:
    """An item of the lead's on `worker:queue`, its lease `age_min` old and (when `expired`) already past its expiry."""
    lease_until = time.strftime(
        "%Y-%m-%dT%H:%MZ", time.gmtime(time.time() + (-120 if expired else 3600))
    )
    rows = [
        {
            "ev": "add",
            "id": item_id,
            "at": stamp(age_min + 1),
            "by": wlfix.ME,
            "s": " ",
            "o": wlfix.ME,
            "t": text,
        },
        {
            "ev": "lease",
            "id": item_id,
            "at": stamp(age_min),
            "by": wlfix.ME,
            "until": lease_until,
            "worker": "queue",
            "note": "",
            "worker_verified": True,
        },
    ]
    with fix.events.open("a", encoding="utf-8") as fh:
        fh.write("".join(json.dumps(r) + "\n" for r in rows))


def blocked_queue_world(fix, blocker_open: bool = True, expired: bool = False) -> None:
    """3 live writers (1 free slot), an open blocker item, and two queued items: the OLDER one declares BLOCKED_BY the blocker (#bea10927 on 2026-09-24, waiting on A3's golden files)."""
    for i, aid in enumerate((W1, W2, W3)):
        mk_sub(fix, aid, "general-purpose", 10 - i)
        plant_lease(fix, "cap%d" % i, aid)
    plant_lease(fix, BLOCKER, W1)
    if not blocker_open:
        with fix.events.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "ev": "state",
                        "id": BLOCKER,
                        "at": stamp(0),
                        "by": wlfix.ME,
                        "s": "x",
                        "note": "done rc=0",
                    }
                )
                + "\n"
            )
    plant_queued(fix, "q0000old", "(deadbeef) golden update BLOCKED_BY:#%s" % BLOCKER, 30, expired)
    plant_queued(fix, "q0000new", "(deadbeef) independent writer work", 10)


def test_r25_5_a_queued_item_waiting_on_an_open_blocker_is_skipped_for_the_next(wl):  # noqa: F811
    """CONTROL: queue_start took the K oldest with no waiting check, so the one free slot named the blocked item."""
    blocked_queue_world(wl)
    v = verdict(wl)
    assert v["queue_start"] == ["q0000new"], v["queue_start"]
    assert [tuple(x) for x in v["queue_skipped"]] == [("q0000old", "waiting on #%s" % BLOCKER)], v
    assert ("q0000old", "queue", "queue") in [tuple(c) for c in v["covered"]], v["covered"]


def test_r25_5_inverse_the_blocker_closed_and_the_oldest_is_named_again(wl):  # noqa: F811
    blocked_queue_world(wl, blocker_open=False)
    v = verdict(wl)
    assert v["queue_start"] == ["q0000old"], v["queue_start"]
    assert v["queue_skipped"] == [], v["queue_skipped"]


def test_r25_5_an_expired_queue_lease_on_a_waiting_item_reads_as_waiting(wl):  # noqa: F811
    """19:45:03 on 2026-09-24: #bea10927's queue lease expired while it still waited on A3, and open-items blocked on it."""
    blocked_queue_world(wl, expired=True)
    v = verdict(wl)
    assert "q0000old" not in v["open"], v["open"]
    assert "q0000old" not in v["queue_start"], v["queue_start"]


def test_r25_5_inverse_an_expired_queue_lease_with_its_blocker_closed_fails_closed(wl):  # noqa: F811
    blocked_queue_world(wl, blocker_open=False, expired=True)
    v = verdict(wl)
    assert "q0000old" in v["open"], v["open"]


QUEUE_PICK_SNIPPET = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import wl_roster as R
recs = [
    {"id": "a", "lease_at": "2026-09-25T10:00:00Z", "text": ""},
    {"id": "b", "lease_at": "2026-09-25T11:00:00Z", "text": ""},
]
by_id = {r["id"]: r for r in recs}
held = lambda r, _b, _s: "held by PLAN-y.md" if r["id"] == "b" else ""
out = {
    "default": R.queue_pick(recs, 1, by_id, "deadbeef")["start"],
    "order_key": R.queue_pick(recs, 1, by_id, "deadbeef", order_key=lambda r: r["id"] != "b")["start"],
    "skip": R.queue_pick(recs, 2, by_id, "deadbeef", order_key=lambda r: r["id"] != "b", skips=(*R.QUEUE_SKIPS, held)),
}
out["skip"]["hold"] = None
print(json.dumps(out))
"""


def test_r25_5_queue_pick_takes_an_order_key_and_more_skips():
    """The seam PLAN-plan-priority-concurrency.md section 5c builds on: a picker's `order_key` replaces the lease-age order, and a concurrency hold is one more entry in `skips`, reported beside the waiting ones."""
    proc = subprocess.run(
        [sys.executable, "-c", QUEUE_PICK_SNIPPET, str(wlfix.STOP_DIR)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-600:]
    got = json.loads(proc.stdout)
    assert got["default"] == ["a"], got
    assert got["order_key"] == ["b"], got
    assert got["skip"]["start"] == ["a"], got
    assert got["skip"]["skipped"] == [["b", "held by PLAN-y.md"]], got


# ---- R20260925.8: the Stop roster and the spawn guard's estimate agree ------------------------------


def parity(fix) -> tuple[list, list]:
    """(roster() writers from the CURRENT event, live_writers_estimate ids from the LAST Stop event plus the metas), for one fixture."""
    return sorted(verdict(fix)["writers"]), sorted(estimate(fix))


def test_r25_8_parity_a_killed_agent_is_in_neither(wl):  # noqa: F811
    """#b9d4dcb2: a TaskStop-ped writer whose transcript still ends waiting on a shell that died with it. The Stop roster freed its slot while the spawn guard refused three spawns at 19:40:09, 19:44:30 and 19:52:58 on 2026-09-24."""
    mk_sub(wl, W1, "general-purpose", 1)
    mk_sub(wl, W4, "pr-babysitter", 5, last="end_turn", running=False)
    plant_shell_wait(wl, W4, "bshell77", running=False)
    lastevent_file(wl).write_text(wl.event(), encoding="utf-8")
    roster_ids, estimate_ids = parity(wl)
    assert roster_ids == estimate_ids == [W1], (roster_ids, estimate_ids)


def test_r25_8_parity_a_shell_waiter_is_in_both(wl):  # noqa: F811
    mk_sub(wl, W1, "general-purpose", 1)
    mk_sub(wl, W4, "pr-babysitter", 5, last="end_turn", running=False)
    plant_shell_wait(wl, W4, "bshell01")
    lastevent_file(wl).write_text(wl.event(), encoding="utf-8")
    roster_ids, estimate_ids = parity(wl)
    assert roster_ids == estimate_ids == sorted([W1, W4]), (roster_ids, estimate_ids)


def test_r25_8_parity_a_fresh_spawn_the_last_event_never_saw_is_in_both(wl):  # noqa: F811
    """The spawn came after the last Stop event was written: the estimate counts it from its meta, the next event lists it."""
    mk_sub(wl, W1, "general-purpose", 1)
    lastevent_file(wl).write_text(wl.event(), encoding="utf-8")
    backdate(lastevent_file(wl), 2)
    mk_sub(wl, W2, "general-purpose", 0.5)
    roster_ids, estimate_ids = parity(wl)
    assert roster_ids == estimate_ids == sorted([W1, W2]), (roster_ids, estimate_ids)


LEASE_HISTORY_SNIPPET = r"""
import json, sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, sys.argv[1])
import wl_store as S

# Derived from now, never a literal date: the store SORTS by timestamp before folding, so the one-minute spacing is what carries the order.
T0 = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=10)

def at(minute):
    return (T0 + timedelta(minutes=minute)).strftime("%Y-%m-%dT%H:%M:%SZ")

UNTIL = (T0 + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%MZ")

class F:
    def __init__(self, recs):
        self.items, self.lineage, self.focus = list(recs.values()), [], {}

ev = [
    {"ev": "add", "id": "it1", "at": at(0), "by": "deadbeef", "s": " ", "o": "deadbeef", "t": "x"},
    {"ev": "lease", "id": "it1", "at": at(1), "by": "deadbeef", "until": UNTIL, "worker": "aA"},
    {"ev": "unlease", "id": "it1", "at": at(2), "by": "deadbeef", "t": ""},
    {"ev": "lease", "id": "it1", "at": at(3), "by": "deadbeef", "until": UNTIL, "worker": "aB"},
    {"ev": "lease", "id": "it1", "at": at(4), "by": "deadbeef", "until": UNTIL, "worker": "aA"},
    {"ev": "state", "id": "it1", "at": at(5), "by": "deadbeef", "s": "x", "note": "done"},
]
recs = S._fold_events(ev)[0]
for r in recs.values():
    r.setdefault("origin", "cli")
again = S._fold_events(S.snapshot_events(F(recs)))[0]
print(json.dumps([recs["it1"]["lease_workers"], again["it1"].get("lease_workers"), again["it1"]["state"]]))
"""


def test_r25_2_the_lease_history_survives_an_unlease_and_a_compaction():
    """`worker` is only the current lease and an unlease clears it; the judge's `item-writers` fix-set joins on the whole history, so the fold keeps it and a compacted log carries it (`lw`)."""
    proc = subprocess.run(
        [sys.executable, "-c", LEASE_HISTORY_SNIPPET, str(wlfix.STOP_DIR)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-800:]
    folded, compacted, state = json.loads(proc.stdout)
    assert folded == ["aA", "aB"], folded
    assert compacted == ["aA", "aB"], compacted
    assert state == "x", state


# ---- plan concurrency: the queue's hold and the roster-concurrency backstop (agent/plans/PLAN-plan-priority-concurrency.md section 5c) ----


def private_stop(fix, filename: str, old: str, new: str):
    """A private copy of the stop directory with ONE line of `filename` replaced; the line must occur exactly once."""
    dest = fix.base / "hooks" / "stop"
    if not dest.exists():
        shutil.copytree(wlfix.STOP_DIR, dest, ignore=shutil.ignore_patterns("__pycache__"))
    path = dest / filename
    src = path.read_text(encoding="utf-8")
    assert src.count(old) == 1, "MUTATION FIXTURE BROKEN: %r occurs %d times in %s" % (
        old,
        src.count(old),
        filename,
    )
    path.write_text(src.replace(old, new), encoding="utf-8")
    return dest


def mutex_world(fix, holder_running: bool = True) -> tuple[str, str]:
    """W1 is a live writer of EXCLUSIVE plan E (its prompt says `Plan: PLAN-e.md`, and it holds a lease on an E item). Two queue leases: the OLDER one serves plan F, which the mutex holds; the newer serves E itself, which it does not."""
    fix.brief_now()
    fix.hand_now()
    e = write_plan(fix, "e", conc="exclusive -- regenerates every golden file")
    f = write_plan(fix, "f")
    if holder_running:
        mk_sub(fix, W1, "general-purpose", 1, prompt="Plan: %s\nregenerate the goldens" % e)
    else:
        mk_sub(
            fix, W1, "general-purpose", 30, last="end_turn", running=False, prompt="Plan: %s" % e
        )
    plant_lease(fix, "e1000001", W1, text=linked(e, "regenerate goldens"))
    plant_lease(fix, "f1000001", "queue", lease_age_min=40, text=linked(f, "Q_HELD"))
    plant_lease(fix, "e1000002", "queue", lease_age_min=10, text=linked(e, "Q_FREE"))
    return e, f


def test_q1_a_queued_item_of_a_held_plan_is_skipped_and_the_next_unheld_one_is_named(wl):  # noqa: F811
    e, _f = mutex_world(wl)
    v = verdict(wl)
    assert v["queue_start"] == ["e1000002"], v["queue_start"]
    held = dict(v["queue_conc_held"])
    assert list(held) == ["f1000001"], v["queue_conc_held"]
    assert (
        "%s is exclusive -- regenerates every golden file and live (writer %s" % (e, W1)
        in held["f1000001"]
    ), held
    assert v["plan_error"] == "", v["plan_error"]


def test_q1c_control_once_the_holder_finishes_the_held_item_is_named(wl):  # noqa: F811
    mutex_world(wl, holder_running=False)
    v = verdict(wl)
    assert "f1000001" in v["queue_start"], v["queue_start"]
    assert v["queue_conc_held"] == [], v["queue_conc_held"]


def test_q1b_an_overlapping_owns_holds_and_a_disjoint_one_does_not(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    p = write_plan(wl, "p", owns="src/shared/**")
    q = write_plan(wl, "q", owns="src/shared/x.py, docs/q/**")
    r = write_plan(wl, "r", owns="src/r/**")
    mk_sub(wl, W1, "general-purpose", 1, prompt="Plan: %s" % p)
    plant_lease(wl, "a1000001", W1, text=linked(p, "shared work"))
    plant_lease(wl, "a1000002", "queue", lease_age_min=40, text=linked(q, "Q_OVERLAP"))
    plant_lease(wl, "a1000003", "queue", lease_age_min=10, text=linked(r, "Q_DISJOINT"))
    v = verdict(wl)
    assert v["queue_start"] == ["a1000003"], v["queue_start"]
    held = dict(v["queue_conc_held"])
    assert "both claim `src/shared/x.py`" in held.get("a1000002", ""), v["queue_conc_held"]


def test_q1m_without_the_held_skip_q1_names_the_held_item(wl):  # noqa: F811
    mutex_world(wl)
    stop = private_stop(
        wl,
        "wl_roster.py",
        "        skips=(*QUEUE_SKIPS, queue_held_skip(plan_holders, xinfo, conc_held)),\n",
        "        skips=QUEUE_SKIPS,\n",
    )
    v = verdict(wl, stop_dir=stop)
    assert "f1000001" in v["queue_start"], (
        "q1m: q1 does not depend on the concurrency skip: %s" % v["queue_start"]
    )


def test_q1s_queue_slot_names_the_held_item_on_a_held_back_line(wl):  # noqa: F811
    mutex_world(wl)
    wl.say("working\n\n## Remaining\n- the queue")
    got = wl.run()
    assert "QUEUED WORK AND A FREE WRITER SLOT" in got.out, got.out[:1500]
    assert "start #e1000002." in got.out, got.out[:1500]
    assert "held back: #f1000001 [P-] -- PLAN-e.md is exclusive" in got.out, got.out[:2000]


def conflict_world(fix, second: str) -> None:
    fix.brief_now()
    fix.hand_now()
    write_plan(fix, "e", conc="exclusive -- regenerates every golden file")
    write_plan(fix, "p", owns="src/a/**")
    write_plan(fix, "f", owns="src/f/**")
    write_plan(fix, "q", owns="src/a/b.py")
    first = "e" if second == "f" else "p"
    mk_sub(fix, W1, "general-purpose", 1, prompt="Plan: PLAN-%s.md" % first)
    mk_sub(fix, W2, "general-purpose", 1, prompt="Plan: PLAN-%s.md" % second)
    plant_lease(fix, "c1000001", W1, text=linked("PLAN-%s.md" % first, "one"))
    plant_lease(fix, "c1000002", W2, text=linked("PLAN-%s.md" % second, "two"))


def test_q3_two_live_writers_breaking_a_mutex_are_a_roster_concurrency_block(wl):  # noqa: F811
    conflict_world(wl, "f")
    v = verdict(wl)
    assert {aid for aid, _plans, _lines in v["plan_conflicts"]} == {W1, W2}, v["plan_conflicts"]
    assert v["state"] == "DISHONEST", v["state"]
    wl.say("working\n\n## Remaining\n- two writers")
    got = wl.run()
    assert "PLAN CONCURRENCY BROKEN: 2 live writer(s)" in got.out, got.out[:2000]
    assert "writer %s serving PLAN-e.md" % W1 in got.out, got.out[:2000]


def test_q3b_two_live_writers_whose_owns_overlap_are_a_block_too(wl):  # noqa: F811
    conflict_world(wl, "q")
    v = verdict(wl)
    assert v["plan_conflicts"], v
    assert any(
        "both claim `src/a/b.py`" in " ".join(lines) for _a, _p, lines in v["plan_conflicts"]
    )


def test_q3c_control_two_live_writers_on_disjoint_parallel_plans_are_not(wl):  # noqa: F811
    wl.brief_now()
    wl.hand_now()
    write_plan(wl, "p", owns="src/a/**")
    write_plan(wl, "r", owns="src/r/**")
    mk_sub(wl, W1, "general-purpose", 1, prompt="Plan: PLAN-p.md")
    mk_sub(wl, W2, "general-purpose", 1, prompt="Plan: PLAN-r.md")
    plant_lease(wl, "c1000001", W1, text=linked("PLAN-p.md", "one"))
    plant_lease(wl, "c1000002", W2, text=linked("PLAN-r.md", "two"))
    v = verdict(wl)
    assert v["plan_conflicts"] == [], v["plan_conflicts"]
    wl.say("working\n\n## Remaining\n- two writers")
    assert "PLAN CONCURRENCY BROKEN" not in wl.run().out


def test_q3d_a_peers_lease_is_never_a_roster_concurrency_conflict(wl):  # noqa: F811
    """A clash with ANOTHER session's lease is the spawn guard's and the queue's question; a stale peer lease must never make this session stop a writer."""
    wl.brief_now()
    wl.hand_now()
    write_plan(wl, "e", conc="exclusive -- regenerates every golden file")
    write_plan(wl, "f")
    mk_sub(wl, W1, "general-purpose", 1, prompt="Plan: PLAN-f.md")
    plant_lease(wl, "c1000001", W1, text=linked("PLAN-f.md", "one"))
    plant_lease(
        wl,
        "c1000009",
        "a5555555555555555",
        owner="cafe1234",
        text=linked("PLAN-e.md", "peer", "cafe1234"),
    )
    v = verdict(wl)
    assert v["plan_conflicts"] == [], v["plan_conflicts"]
    assert "PLAN-e.md" in (v["plan_holders"] or {}), v["plan_holders"]


def test_q3m_without_the_conflict_append_q3_goes_silent(wl):  # noqa: F811
    conflict_world(wl, "f")
    stop = private_stop(
        wl,
        "wl_planorder.py",
        "        if not got.allow and got.kind in HOLD_KINDS:\n            out.append((aid, got))\n",
        "        pass\n",
    )
    v = verdict(wl, stop_dir=stop)
    assert v["plan_conflicts"] == [], "q3m: q3 does not depend on the conflict rule: %s" % v
