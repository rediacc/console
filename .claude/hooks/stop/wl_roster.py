"""wl_roster: the parallel-writer roster the Stop hook and the lead session supervise together.

THE ASK (operator, 2026-09-24, quoted in full in agent/plans/PLAN-parallel-writer-roster.md): the Stop hook may skip pushing the lead when the lead is honest about its parallel writers; there must be a limit of 4 writers; a status report older than 20 minutes gets a ping; "there should be no escape hatches."

ONE VERDICT FROM THREE SOURCES THE LEAD CANNOT EDIT. The Stop event (the harness's own running list), the subagent metas and transcripts under the session's `subagents/` directory, and the append-only store. The lead has no way to DECLARE the roster; it can only make the roster true. `roster()` returns the rows and the five defect lists, and a `state`:

  HONEST     no plain open item owned by the session, no defect, and every `[>]` it owns is a
             subagent lease some live agent in its lineage covers, or a live shell lease the OS
             did not flag `suspect`. At least one covered subagent lease is required: an empty
             roster is not a supervised one, and calling it honest would stand the stuck detector
             down for a session that has nothing running at all.
  DISHONEST  at least one defect.
  UNKNOWN    anything the roster cannot judge (a teammate leased by name, a suspect shell, an
             open item, a store it cannot see). UNKNOWN changes nothing: the battery runs as before.

THE CAP AND THE PING ARE COMPUTED IN EVERY STATE. Honesty only decides whether some pushes are dropped; it never turns enforcement off.

NO ESCAPE HATCHES, and this module is where that is enforced. It reads NO environment variable, and every threshold is a module-level literal. `.ci/policy/worklist-env-registry.json` lists this file under `sealed_modules`, so an environment read added here is CI red that registering the variable cannot clear. Thresholds borrowed from `wl_liveness` would inherit its `WORKLIST_*` overrides, so
the few this module needs are restated here as literals rather than imported: `FINISHED_QUIET_S` stands in for `IDLE_EDGE_EPSILON_S`, and every tail read passes an explicit byte bound instead of `TEAMMATE_TAIL_BYTES`. An override that made no transcript ever "proven finished" would turn every dead lease into a covered one, which is an escape hatch by another name.

WHAT IS AND IS NOT A WRITER. Plan and Explore agents never wrote across 131 transcripts (plan F6), so their type is enough. Every other type is a writer, and so is ANY agent whose transcript shows an edit tool call, whatever its type claims. A reader promoted by evidence is never demoted again, which is the conservative direction for a cap.
"""

import datetime
import json
import os
import pathlib
import re
import tempfile
import time
from typing import Any

import wl_common
import wl_core as C
import wl_leasehelp as LH

# ---- the sealed constants ---------------------------------------------------

# The operator's number. A writer beyond it is refused at spawn (guards/block_agent_cap.py) and blocked at Stop (`roster-cap`).
WRITER_CAP = 4
# The operator's number. A leased worker whose newest evidence (a transcript write, a tool call in flight, a lease, a --status, its own SendMessage or SubagentStop) is this old is `roster-silent`. Evidence counts as status since 2026-09-24 (operator ruling "Evidence counts as status"), so the separate `roster-status` ping is merged into it.
STATUS_PING_MIN = 20
# A lease on `worker:queue` holds writer work the cap forbids starting. It is covered ONLY while every writer slot is taken; the moment one frees it is a defect naming the item to start, so it can never park work behind a cap that is not full.
QUEUE_WORKER = LH.QUEUE_WORKER
# The tool calls that prove an agent writes, whatever its declared type says.
EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
# The harness types that never write (plan F6: 0 edit calls in 66 Plan and 65 Explore transcripts). Custom read-only types are ADDED from `.claude/agents/*.md` by `read_only_types`, never subtracted.
READ_ONLY_AGENT_TYPES = frozenset({"Plan", "Explore"})
# The pushes an HONEST roster answers. The ladder keys are deliberately ABSENT, and that is a narrowing of the plan's list rather than an omission: `wl_liveness.ladder` skips every subject whose worker is a known subagent, so a ladder key that reaches the filter is BY CONSTRUCTION about a shell lease, a teammate or a harness task, which the plan says must keep firing. `agent-state`
# is dropped only for its `stale` verdict; the caller enforces that.
ROSTER_SUPPRESSES = frozenset({"bg-report", "stuck", "idle-stall", "solo-grind", "agent-state"})
# The defect keys. `roster-status` was merged into `roster-silent` on 2026-09-24 ("Evidence counts as status"). `roster-concurrency` is the Stop-side backstop of the plan-concurrency spawn guard (agent/plans/PLAN-plan-priority-concurrency.md section 5c): two live writers whose plans already break a mutex or share files.
ROSTER_KEYS = (
    "roster-cap",
    "roster-silent",
    "roster-unleased",
    "roster-dead",
    "queue-slot",
    "roster-concurrency",
)

# THE CAP-SATURATED WAIT (operator 2026-09-24; agent/plans/PLAN-stop-hook-cap-saturated-wait.md). Its keep-list lives in wl_standdown.CAP_WAIT beside the focus profile that generalises it; the predicate stays here because it needs WRITER_CAP.


def cap_saturated_wait(verdict, open_items, actionable_tasks):
    """True when every writer slot is verified live, or every queued item is held by a live plan, and this session has nothing it could start.

    `verdict` is this stop's `roster()` result; `open_items` is `classify_items`' open list (a plain `[ ]`, an expired lease, a `worker:lead` lease with nothing live); `actionable_tasks` is the harness tasks the session could do now. Every other disallowed item state surfaces as a KEPT key instead (see wl_standdown.CAP_WAIT), so an exception arrives as one focused block rather than the whole battery.
    """
    if not verdict or verdict.get("blind") or open_items or actionable_tasks:
        return False
    return len(verdict.get("writers") or ()) >= WRITER_CAP or concurrency_saturated(verdict)


def concurrency_saturated(verdict):
    """True when a slot is free but EVERY queued item is held by a live plan's mutex or Owns (agent/plans/PLAN-plan-priority-concurrency.md section 5c): the concurrency-saturated wait. A queued item that is waiting on a blocker, or reserved by HOLD_FOR, is not held, so one of those keeps the ordinary battery."""
    held = verdict.get("queue_conc_held") or ()
    return (
        bool(held)
        and not verdict.get("queue_start")
        and len(held) == int(verdict.get("queued") or 0)
    )


# How long an agent that ended its turn with a background shell still armed counts as WAITING rather than finished, when no fresh Stop event can confirm the shell. The lease cap: a wait longer than any lease is not supervision the estimate should vouch for.
WAIT_HORIZON_MIN = 120

# A transcript whose last record ended the turn must also have been quiet this long to count as finished; the harness appends the final record and then stops.
FINISHED_QUIET_S = 2
# How far back the last-record probe reads. One record can be large (a pasted file), so generous.
TAIL_BYTES = 262144
# The incremental edit and SendMessage scan reads at most this much of one transcript per stop and resumes from its byte offset on the next, so a 30 MB transcript costs one pass in total rather than one pass per stop.
SCAN_STEP_BYTES = 8 * 1024 * 1024
# `--status` prints at most this much of the worker's last text.
STATUS_TEXT_MAX = 600
# Rows printed in the HONEST summary before a counted remainder line.
SUMMARY_ROWS_MAX = 8


# A `worker:queue` lease whose note carries `HOLD_FOR:#<id>` holds ONE free writer slot for that item (agent/plans/PLAN-stop-hook-retro-20260924.md R.5, operator default 2026-09-24): at most one per session, it must name an open or in-flight item the session owns, and it lasts exactly as long as its own lease (at most 120 minutes).
HOLD_FOR = re.compile(r"\bHOLD_FOR:#?([0-9a-f]{6,})\b")
HOLD_MAX = 1


def hold_target(rec):
    """The item id a queue lease reserves a slot for, or ""."""
    m = HOLD_FOR.search(str((rec or {}).get("lease_note") or ""))
    return m.group(1) if m else ""


def hold_valid(target, by_id, session_id):
    """True when `target` is an open or in-flight item this session owns: the only thing a slot may be held for."""
    rec = by_id.get(target)
    if not isinstance(rec, dict):
        return False
    return rec.get("state") in (" ", ">") and C.owned_by_me(rec.get("owner"), session_id)


def queue_order(rec):
    """The queue's AGE term: oldest queue lease first, then id. `roster` ranks by `wl_planorder.item_key` with this as its age (agent/plans/PLAN-plan-priority-concurrency.md section 2: dependencies, operator priority, AI priority, then this), and falls back to it alone when the plans cannot be read."""
    return (_epoch(rec.get("lease_at")) or 0, rec["id"])


def queue_waiting(rec, by_id, _session_id):
    """The skip reason for a queued item still waiting on an open BLOCKED_BY blocker, or "". Only the explicit token counts, never prose (agent/plans/PLAN-stop-hook-retro-20260925.md, Decision 4)."""
    blockers = LH.waiting_on(rec, by_id)
    return "waiting on %s" % ", ".join("#" + b for b in blockers) if blockers else ""


# The reasons a queued item is NOT startable although a slot is free, tried in order; the first non-empty reason wins. Each is `(rec, by_id, session_id) -> reason or ""`. A concurrency hold (agent/plans/PLAN-plan-priority-concurrency.md section 5c) is one more entry, not a new code path: `roster` appends `queue_held_skip(...)`, which needs this stop's live plans.
QUEUE_SKIPS = (queue_waiting,)


def queue_holder_plans(verdict):
    """The plans holding this stop's queue, in first-seen order, parsed from the recorded hold reasons (for the concurrency-saturated wait's allow line)."""
    out: list[str] = []
    for _rid, why in verdict.get("queue_conc_held") or ():
        for plan in re.findall(r"(PLAN-[A-Za-z0-9._-]+\.md) is (?:exclusive|parallel)\b", why):
            if plan not in out:
                out.append(plan)
    return out


def queue_held_skip(live, xinfo, held):
    """The concurrency skip for one stop: a queued item whose writer the plan-concurrency spawn guard would refuse right now (a live exclusive plan, or a live plan owning the same files). Each hold is recorded in `held` ({id: reason}) for queue-slot's "held back" lines and the concurrency-saturated wait. `live` None (the plans could not be read) holds nothing."""
    import wl_planorder as PO  # noqa: PLC0415 -- read only when a queue exists

    def skip(rec, _by_id, _session_id):
        got = PO.hold(rec, live, xinfo) if live is not None else None
        if got is None:
            return ""
        held[rec["id"]] = PO.reason(got)
        return "held: " + held[rec["id"]]

    return skip


def queue_pick(queued, free, by_id, session_id, order_key=None, skips=QUEUE_SKIPS):
    """Which queued items to start now. THE QUEUE IS NOT A FINISHED WORKER.

    agent/plans/PLAN-stop-hook-retro-20260924.md R.5: every queued item used to read as `leased_dead` the moment one slot was free, so 15 "start it" lines were printed for 1 free slot. Only the first K startable items are named, K being the free slots less at most one HOLD_FOR reservation; the rest stay covered behind the cap.

    R20260925.5 (agent/plans/PLAN-stop-hook-retro-20260925.md): an item a `skips` predicate refuses is never named, and the NEXT startable one takes its slot. On 2026-09-24 queue-slot twice named an item the lead could not start because another writer held what it needed (#bea10927 waiting on A3), and each naming was overridden by hand.

    Returns {"start": [id], "free": K, "hold": rec or None, "covered": [id], "skipped": [(id, reason)]}. A skipped item stays covered: it is waiting, not dead and not open.
    """
    order_key = order_key or queue_order
    ordered = sorted(queued, key=order_key)
    hold = next((r for r in ordered if hold_valid(hold_target(r), by_id, session_id)), None)
    slots = max(0, max(0, free) - (HOLD_MAX if hold is not None else 0))
    start: list[str] = []
    covered: list[str] = []
    skipped: list[tuple[str, str]] = []
    for r in ordered:
        if r is hold:
            continue
        reason = next((why for why in (fn(r, by_id, session_id) for fn in skips) if why), "")
        if reason:
            skipped.append((r["id"], reason))
            covered.append(r["id"])
        elif len(start) < slots:
            start.append(r["id"])
        else:
            covered.append(r["id"])
    if hold is not None:
        covered.append(hold["id"])
    return {"start": start, "free": slots, "hold": hold, "covered": covered, "skipped": skipped}


# ---- locating the session's agents -------------------------------------------


def session_subagents_dir(cwd, session_id):
    """`<projects>/<munged root>/<session>/subagents`, or None when it cannot be located.

    A PREFIX resolves only when exactly one session directory carries it; an ambiguous prefix is "cannot tell", never a guess. A full session id whose directory does not exist yet is a session that has spawned nothing, which is an honest zero and is returned as the (absent) path.
    """
    import wl_report as RPT  # noqa: PLC0415 -- stdlib-only sibling, no cycle

    if not session_id:
        return None
    try:
        proj = RPT._projects_dir() / RPT._munged(C.project_root(C.project_start({"cwd": cwd})))
    except (OSError, ValueError, TypeError, RuntimeError):
        return None
    if not proj.is_dir():
        return None
    direct = proj / session_id
    if direct.is_dir() or len(session_id) >= 36:
        return direct / "subagents"
    hits = [p for p in proj.glob(session_id + "*") if p.is_dir()]
    if len(hits) != 1:
        return None
    return hits[0] / "subagents"


def load_metas(sub_dir):
    """{agent_id: meta} for every `agent-<id>.meta.json` in the directory, read once per stop.

    Each meta carries `type`, `parent` (the `parentAgentId`, or ""), `depth`, `desc`, `name`, the `jsonl` path and `spawned`: the meta file's mtime, which is the agent's last (re)START rather than its first spawn. Measured 2026-09-24: an agent listed in a 07:16Z Stop event carried a meta mtime of 08:05Z, because the harness rewrites the meta when an agent is resumed. That is the right clock for both
    consumers -- the newest (re)started writer is the excess the cap names, and an agent (re)started after the last Stop event is exactly one that event cannot list.
    """
    out: dict[Any, Any] = {}
    if sub_dir is None:
        return out
    try:
        # WORKFLOW AGENTS TOO (agent/plans/PLAN-stop-hook-continuity.md P1.9): a workflow's agents write under `subagents/workflows/<runId>/`, and a workflow agent that edits is a writer the cap must count.
        paths = list(sub_dir.glob("agent-*.meta.json")) + list(
            sub_dir.glob("workflows/*/agent-*.meta.json")
        )
    except OSError:
        return out
    for meta in paths:
        try:
            info = json.loads(meta.read_text(encoding="utf-8", errors="replace"))
            spawned = meta.stat().st_mtime
        except (OSError, ValueError):
            continue
        if not isinstance(info, dict):
            continue
        aid = meta.name[len("agent-") : -len(".meta.json")]
        out[aid] = {
            "type": str(info.get("agentType") or ""),
            "parent": str(info.get("parentAgentId") or ""),
            "depth": info.get("spawnDepth") if isinstance(info.get("spawnDepth"), int) else 1,
            "desc": str(info.get("description") or ""),
            "name": str(info.get("name") or ""),
            "jsonl": meta.with_name("agent-%s.jsonl" % aid),
            "spawned": spawned,
        }
    return out


def children_map(metas):
    kids: dict[Any, Any] = {}
    for aid, m in metas.items():
        if m["parent"]:
            kids.setdefault(m["parent"], []).append(aid)
    return kids


def ancestors(aid, metas):
    """The `parentAgentId` chain upward, nearest first. Bounded, so a cycle cannot hang a stop."""
    out, cur = [], aid
    for _ in range(len(metas) + 1):
        parent = (metas.get(cur) or {}).get("parent") or ""
        if not parent or parent in out or parent == aid:
            break
        out.append(parent)
        cur = parent
    return out


def descendants(aid, kids):
    out, stack = [], list(kids.get(aid, ()))
    while stack:
        nxt = stack.pop()
        if nxt in out or nxt == aid:
            continue
        out.append(nxt)
        stack.extend(kids.get(nxt, ()))
    return out


def read_only_types(root):
    """READ_ONLY_AGENT_TYPES plus every `.claude/agents/*.md` whose `tools:` line names no edit tool.

    An agent definition with NO `tools:` line inherits every tool, so it is a writer. Only ever adds to the literal set.
    """
    out = set(READ_ONLY_AGENT_TYPES)
    try:
        defs = sorted((pathlib.Path(root) / ".claude" / "agents").glob("*.md"))
    except (OSError, TypeError):
        return frozenset(out)
    for path in defs:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not text.startswith("---"):
            continue
        head = text.split("\n---", 1)[0]
        name = re.search(r"(?m)^name:\s*(\S+)", head)
        tools = re.search(r"(?m)^tools:\s*(.*)$", head)
        if not name or not tools:
            continue
        listed = {t for t in re.split(r"[\s,]+", tools.group(1)) if t}
        if listed and not (listed & EDIT_TOOLS):
            out.add(name.group(1))
    return frozenset(out)


# ---- reading a transcript -----------------------------------------------------


def _mtime(path):
    try:
        return path.stat().st_mtime
    except (OSError, AttributeError):
        return None


def _epoch(stamp):
    """Epoch seconds from an ISO8601 stamp (`Z`, fractional seconds, or the store's form), or None."""
    if not stamp:
        return None
    when = C.parse_stamp(str(stamp))
    if when is not None:
        return when.timestamp()
    try:
        return datetime.datetime.fromisoformat(str(stamp)).timestamp()
    except ValueError:
        return None


def last_record(jsonl):
    import wl_liveness as L  # noqa: PLC0415 -- wl_liveness imports this module lazily too

    if jsonl is None:
        return None
    return L._last_record(jsonl, tail_bytes=TAIL_BYTES)


def inflight_tool(rec):
    """The tool name when the record is an assistant turn ending in a tool call, else "".

    A worker sitting in a 25-minute gate run writes nothing while it waits, and that is not silence.
    """
    if not isinstance(rec, dict) or rec.get("type") != "assistant":
        return ""
    content = (rec.get("message") or {}).get("content")
    name = ""
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                name = str(block.get("name") or "tool")
    return name


def proven_finished(jsonl, now, name="", cwd="", session_id=""):
    """True only when the transcript's last record ENDED THE TURN and nothing was written after.

    The same one-directional test `wl_liveness._record_is_idle` makes: every ambiguous shape reads as working, because a false "finished" would hide a live writer from the cap.
    """
    import wl_liveness as L  # noqa: PLC0415

    mtime = _mtime(jsonl)
    if mtime is None:
        return False
    rec = last_record(jsonl)
    if L._record_is_idle(rec):
        return now - mtime >= FINISHED_QUIET_S
    if name:
        edge = L.idle_edge(cwd, session_id, name)
        if edge is not None and mtime <= edge + FINISHED_QUIET_S:
            return True
    return False


def scan_transcript(jsonl, ent):
    """Advance the incremental scan of one transcript. Returns the updated cache entry.

    Cached per agent as {"off", "ino", "edits", "send"}: the byte offset already read, the inode it was read from (a replaced file restarts at 0), the count of edit tool calls, and the newest SendMessage timestamp. Only complete lines are consumed, so a half-flushed final line is read on the next stop.
    """
    ent = dict(ent or {})
    try:
        st = jsonl.stat()
    except (OSError, AttributeError):
        return ent
    off = int(ent.get("off") or 0)
    if ent.get("ino") != st.st_ino or off > st.st_size:
        ent = {"ino": st.st_ino, "off": 0, "edits": 0, "send": ""}
        off = 0
    if off >= st.st_size:
        return ent
    try:
        with jsonl.open("rb") as fh:
            fh.seek(off)
            blob = fh.read(SCAN_STEP_BYTES)
    except OSError:
        return ent
    cut = blob.rfind(b"\n")
    if cut < 0:
        if len(blob) >= SCAN_STEP_BYTES:
            ent["off"] = off + len(blob)  # one record larger than a step: skip it rather than stall
        return ent
    edits = int(ent.get("edits") or 0)
    send = str(ent.get("send") or "")
    for rec in wl_common.records(blob[: cut + 1].splitlines(), need=b'"tool_use"'):
        if rec.get("type") != "assistant":
            continue
        content = (rec.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name")
            if name in EDIT_TOOLS:
                edits += 1
            elif name == "SendMessage":
                at = str(rec.get("timestamp") or "")
                if at and (not send or (_epoch(at) or 0) >= (_epoch(send) or 0)):
                    send = at
    ent.update({"ino": st.st_ino, "off": off + cut + 1, "edits": edits, "send": send})
    return ent


def subagent_stop_at(start, aid):
    """Epoch of the newest SubagentStop capture for this agent in the report store, or None."""
    import wl_report as RPT  # noqa: PLC0415

    rid = RPT.short_id(aid)
    newest = None
    try:
        entries = RPT.read_index(RPT.store_root(start))
    except Exception:  # noqa: BLE001 -- a report store is evidence, never a crash
        return None
    for e in entries:
        ident = str(e.get("id") or "")
        if ident != rid and not ident.startswith(rid + "-"):
            continue
        at = _epoch(e.get("at"))
        if at is not None and (newest is None or at > newest):
            newest = at
    return newest


# ---- the verdict ---------------------------------------------------------------


def _worker_of(rec):
    wm = C.WORKER.search(rec.get("line") or "")
    return rec.get("worker") or (wm.group(1) if wm else "")


def _running(event):
    return [
        b
        for b in (event.get("background_tasks") or [])
        if isinstance(b, dict) and b.get("status") == "running"
    ]


def shell_waiters(running, metas, now=None):
    """{agent id: shell id} for every agent the event does NOT list as running whose own transcript launched a shell that still runs.

    An agent that armed a background command and ended its turn is WAITING, not finished: the harness resumes it when that shell exits, yet the event reports the agent itself as completed. Its launch leaves `"backgroundTaskId":"<id>"` in the agent's transcript, and that is the only link between the two, since the event's shell rows carry no owner.
    """
    listed = {str(b.get("id") or "") for b in running if b.get("type") == "subagent"}
    shell_ids = [
        str(b.get("id") or "") for b in running if b.get("type") == "shell" and b.get("id")
    ]
    out: dict[Any, Any] = {}
    if not shell_ids:
        return out
    now = time.time() if now is None else now
    for aid, m in metas.items():
        if aid in listed or m.get("jsonl") is None:
            continue
        # BOUNDED LIKE transcript_waiting: an agent that armed a daemon (`./run.sh account dev`) and ended its turn is "waiting" on a shell that never exits. Past WAIT_HORIZON_MIN of transcript silence it is finished, not waiting; without the bound a completed writer held a slot and raised UNLEASED WRITER 1010 minutes later (2026-09-25, a5469082799b4a5af on bi06trcl0).
        mt = _mtime(m["jsonl"])
        if mt is None or now - mt > WAIT_HORIZON_MIN * 60:
            continue
        # ARMED, not merely launched (agent/plans/PLAN-stop-hook-retro-20260924.md R.6): a shell whose `<task-id>` notification already reached the agent's own transcript is one it is no longer waiting on, even while the event still lists that shell as running. Without this a finished writer held a slot (2026-09-24 15:08, a9130421).
        armed = armed_shells(m["jsonl"])
        for sid in shell_ids:
            if sid in armed:
                out[aid] = sid
                break
    return out


_ARMED = re.compile(rb'"backgroundTaskId":"([A-Za-z0-9_-]+)"')


def armed_shells(jsonl):
    """Background shells this transcript launched that no later task notification IN IT has reported back, in launch order.

    The harness resumes a waiting agent by appending `<task-notification>` carrying `<task-id>X</task-id>` to that agent's own transcript (measured 2026-09-24 on real subagent transcripts: both the queued_command attachment and the SYSTEM NOTIFICATION user record carry it). A launch with no such record after it is a shell the agent is still waiting on."""
    try:
        data = jsonl.read_bytes()
    except (OSError, AttributeError):
        return []
    out: list[bytes] = []
    for m in _ARMED.finditer(data):
        sid = m.group(1)
        if sid in out:
            out.remove(sid)
        if b"<task-id>%s</task-id>" % sid not in data[m.end() :]:
            out.append(sid)
    return [x.decode() for x in out if not shell_ended(jsonl, x.decode())]


# The harness's last line in a finished shell's `tasks/<id>.output`: `[killed]`, or `[exited with code N]`.
_SHELL_END = re.compile(rb"\[(?:killed|exited with code -?\d+)\]\s*$")


def shell_ended(jsonl, sid):
    """True when shell `sid`'s own output stream ends with the harness's terminal marker.

    THE STREAM IS THE AUTHORITY, not the agent's transcript. A shell that ends after its agent already finished never gets its `<task-id>` notification into that transcript, so `armed_shells` read it as armed forever and the agent held a writer slot: on 2026-09-25 the finished harness writer a9fb71e0 (quiet 67 minutes) blocked a spawn at 4 of 4 on `br7n2v42t`, whose stream read `[killed]`. The stream sits at `<tmp>/claude-<uid>/<project>/<session>/tasks/<id>.output`, and the agent transcript at `<projects>/<project>/<session>/subagents/agent-<id>.jsonl` names both segments. A stream that cannot be found or read proves nothing, so the shell stays armed (the safe side for a cap).
    """
    try:
        path = pathlib.Path(jsonl)
        session, project = path.parents[1].name, path.parents[2].name
    except (IndexError, TypeError):
        return False
    # No environment override, on purpose: this module is sealed against env reads (test_r6b), so no knob can free a writer slot.
    bases = [
        os.path.join(tempfile.gettempdir(), "claude-%d" % os.getuid(), project, session, "tasks"),
        os.path.join(tempfile.gettempdir(), project, session, "tasks"),
    ]
    for b in bases:
        try:
            with open(os.path.join(b, sid + ".output"), "rb") as fh:
                fh.seek(0, os.SEEK_END)
                fh.seek(max(0, fh.tell() - 256))
                return bool(_SHELL_END.search(fh.read()))
        except OSError:
            continue
    return False


def transcript_waiting(jsonl, now):
    """The shell id an agent is WAITING on, read from its transcript alone, or "".

    For the callers with no fresh Stop event (the spawn guard, `--lease worker:queue`, `--status`): an agent whose last record ended the turn, written inside WAIT_HORIZON_MIN, with a background shell still armed. 2026-09-24: without this the estimate counted such an agent as finished until the next stop refreshed the event, so `--lease worker:queue` refused ("3 of 4 busy") in the same minute the spawn guard blocked at 4 of 4."""
    import wl_liveness as L  # noqa: PLC0415

    mt = _mtime(jsonl)
    if mt is None or now - mt > WAIT_HORIZON_MIN * 60:
        return ""
    if not L._record_is_idle(last_record(jsonl)):
        return ""
    armed = armed_shells(jsonl)
    return armed[-1] if armed else ""


def roster(event, fold, session_id, state_doc=None, cwd=None, verdicts=None, now=None):
    """The roster verdict for one stop. Never raises for a missing input; it degrades to UNKNOWN."""
    now = time.time() if now is None else now
    cwd = cwd or event.get("cwd") or ""
    start = C.project_start({"cwd": cwd})
    root = C.project_root(start)
    sub_dir = session_subagents_dir(cwd, session_id)
    blind = sub_dir is None
    metas = load_metas(sub_dir)
    kids = children_map(metas)
    ro_types = read_only_types(root)
    running = _running(event)
    shells = {str(b.get("id") or ""): b for b in running if b.get("type") == "shell"}
    workflows = {str(b.get("id") or ""): b for b in running if b.get("type") == "workflow"}
    waiters = shell_waiters(running, metas)
    running = running + [{"id": aid, "type": "subagent", "status": "running"} for aid in waiters]

    # LIVE: the harness lists it AND its transcript is not proven finished. The `--reap` list is not consulted: a reaped id whose transcript is not proven finished is still a live writer, and one that is proven finished is excluded here anyway.
    live, finished = {}, set()
    for b in running:
        if b.get("type") != "subagent":
            continue
        aid = str(b.get("id") or "")
        if not aid:
            continue
        m = metas.get(aid) or {}
        jsonl = m.get("jsonl")
        if (
            aid not in waiters
            and jsonl is not None
            and proven_finished(jsonl, now, m.get("name", ""), cwd, session_id)
        ):
            finished.add(aid)
            continue
        live[aid] = {
            "id": aid,
            "type": str(b.get("agent_type") or m.get("type") or "?"),
            "desc": str(b.get("description") or m.get("desc") or "")[:60],
            "parent": m.get("parent", ""),
            "depth": m.get("depth", 1),
            "spawned": m.get("spawned"),
            "jsonl": jsonl,
            "known": bool(m),
        }

    # Writer classification, with the incremental evidence scan cached in the state doc.
    cache = {}
    if isinstance(state_doc, dict):
        cache = state_doc.setdefault("roster", {}).setdefault("scan", {})
        for stale in [k for k in cache if k not in live]:
            del cache[stale]
    row: Any
    for aid, row in live.items():
        ent = cache.get(aid) or {}
        if row["jsonl"] is not None:
            ent = scan_transcript(row["jsonl"], ent)
            cache[aid] = ent
        row["edits"] = int(ent.get("edits") or 0)
        row["send"] = str(ent.get("send") or "")
        row["writer"] = row["type"] not in ro_types or row["edits"] > 0
        mt = _mtime(row["jsonl"])
        row["quiet_min"] = None if mt is None else max(0.0, (now - mt) / 60.0)
        rec = last_record(row["jsonl"])
        row["inflight"] = inflight_tool(rec)
        row["size"] = row["jsonl"].stat().st_size if mt is not None else 0

    writers = sorted(
        (a for a, r in live.items() if r["writer"]),
        key=lambda a: (live[a]["spawned"] or 0, a),
    )
    readers = sorted(a for a, r in live.items() if not r["writer"])

    # The session's own items: plain open, and the leases grouped by worker.
    mine = [
        r for r in getattr(fold, "items", []) or [] if C.owned_by_me(r.get("owner"), session_id)
    ]
    live_ids = {str(b.get("id") or "") for b in running}
    by_id = {r["id"]: r for r in getattr(fold, "items", []) or []}
    # A `waiting` item (BLOCKED_BY, P2.4) is not open work in hand; its chain's root is, and it is counted.
    open_ids = [r["id"] for r in mine if r.get("state") == " " and not LH.waiting_on(r, by_id)]
    leases: dict[Any, Any] = {}
    for r in mine:
        if r.get("state") != ">":
            continue
        ls = C.lease_state(r.get("line") or "")
        w = _worker_of(r)
        if w == LH.LEAD_WORKER:
            # worker:lead (P2.1) is no agent and fills no writer slot; it is covered exactly while a task of this session is live, the same fact classify_items reads.
            if verdicts is None:
                import wl_liveness as L  # noqa: PLC0415

                verdicts = L.verify_background(list(shells.values()))
            if ls in ("fresh", "expired") and LH.lead_covered(running, verdicts):
                leases.setdefault(w, []).append(r)
            else:
                open_ids.append(r["id"])
            continue
        if ls != "fresh" and not (ls == "expired" and w and w in live_ids):
            if ls == "expired" and w == QUEUE_WORKER and LH.waiting_on(r, by_id):
                # R20260925.5: an expired queue lease on an item still waiting on its BLOCKED_BY blocker reads as `waiting`, exactly as classify_items; queue_pick below skips it.
                leases.setdefault(w, []).append(r)
                continue
            open_ids.append(r["id"])  # fails closed into an open item, exactly as classify_items
            continue
        leases.setdefault(w, []).append(r)

    def covered_by(w):
        if w in live:
            return w
        for d in descendants(w, kids):
            if d in live:
                return d
        return ""

    # PLAN ORDER AND PLAN CONCURRENCY (agent/plans/PLAN-plan-priority-concurrency.md sections 2 and 5c), judged against the writers the harness's own event proves live plus every session's fresh leases. A plan read that fails leaves the queue in age order with nothing held, and says why in `plan_error`: never a crashed roster.
    plan_holders: dict[str, list[str]] | None = None
    plan_serving: dict[str, set[str]] = {}
    plan_error = ""
    xinfo = None
    order_key = queue_order
    try:
        import wl_planconc as X  # noqa: PLC0415
        import wl_planorder as PO  # noqa: PLC0415

        order_ctx, plan_error = PO.context(root)
        order_key = PO.item_key(order_ctx, age=queue_order)
        texts = []
        for aid in writers:
            row = live[aid]
            prompt = LH.first_prompt(row["jsonl"]) if row["jsonl"] is not None else ""
            texts.append((aid, row["type"], "%s\n%s" % (row["desc"], prompt)))
        plan_holders = PO.holders(texts, fold, session_id)
        xinfo = PO.xinfo_for(root)
        for aid, _kind, text in texts:
            served = set(X.spawn_plans(text, by_id))
            for w in [aid, *ancestors(aid, metas)]:
                served.update(p for p in (X.item_plan(r) for r in leases.get(w, ())) if p)
            plan_serving[aid] = served
    except Exception as exc:  # noqa: BLE001 -- the roster must never crash on a plan read
        plan_holders = None
        plan_error = "%s: %s" % (type(exc).__name__, str(exc)[:160])
    conc_held: dict[str, str] = {}
    plan_conflicts: list[tuple[str, list[str], list[str]]] = []
    if plan_holders is not None:
        plan_conflicts = [
            (aid, sorted(plan_serving[aid]), list(v.lines))
            for aid, v in PO.conflicts(plan_serving, plan_holders, xinfo)
        ]

    covered: list[Any] = []
    leased_dead: list[Any] = []
    unknown: list[Any] = []
    queued = list(leases.get(QUEUE_WORKER, ()))
    pick = queue_pick(
        queued,
        WRITER_CAP - len(writers),
        by_id,
        session_id,
        order_key=order_key,
        skips=(*QUEUE_SKIPS, queue_held_skip(plan_holders, xinfo, conc_held)),
    )
    queue_start = pick["start"]
    slots = pick["free"]
    hold = pick["hold"]
    covered.extend((i, QUEUE_WORKER, QUEUE_WORKER) for i in pick["covered"])
    for w, recs in leases.items():
        if w == LH.LEAD_WORKER:
            covered.extend((r["id"], w, w) for r in recs)
            continue
        if w == QUEUE_WORKER:
            continue
        if w and (w in metas or w in live):
            coverer = covered_by(w)
            for r in recs:
                (covered if coverer else leased_dead).append((r["id"], w, coverer))
        elif w and w in workflows:
            # A WORKFLOW LEASE is covered by its agents' stream (agent/plans/PLAN-stop-hook-continuity.md P1.9). It is in the event, so "no meta and not in the event" was simply false and dropped the roster to UNKNOWN.
            import wl_liveness as L  # noqa: PLC0415

            wf = L.workflow_stream(cwd, session_id, workflows[w].get("name"))
            if wf is not None and wf[0] < STATUS_PING_MIN:
                covered.extend((r["id"], w, w) for r in recs)
            else:
                unknown.extend((r["id"], w, "workflow with no fresh agent stream") for r in recs)
        elif w and w in shells:
            if verdicts is None:
                import wl_liveness as L  # noqa: PLC0415

                verdicts = L.verify_background(list(shells.values()))
            if (verdicts or {}).get(w) == "suspect":
                unknown.extend((r["id"], w, "suspect shell") for r in recs)
        else:
            unknown.extend((r["id"], w, "no meta and not in the event") for r in recs)

    # A writer is leased when it, or any ancestor, holds one of the session's leases.
    unleased = [a for a in writers if not any(x in leases for x in [a, *ancestors(a, metas)])]
    over_cap = writers[WRITER_CAP:] if len(writers) > WRITER_CAP else []

    # Status time, per leased worker, over its whole lineage.
    statuses = getattr(fold, "statuses", None) or {}
    stop_cache = {}

    def status_at(w):
        family = [w, *ancestors(w, metas), *descendants(w, kids)]
        best, src = None, "none"
        lease_family = {w, *ancestors(w, metas)}
        for lw in lease_family:
            for r in leases.get(lw, ()):
                at = _epoch(r.get("lease_at") or r.get("upd"))
                if at is not None and (best is None or at > best):
                    best, src = at, "lease of #%s" % r["id"]
        for f in family:
            st = statuses.get(f) or {}
            at = _epoch(st.get("reset_at"))
            if at is not None and (best is None or at > best):
                best, src = at, "--status on %s" % f
            send = (live.get(f) or {}).get("send") or (cache.get(f) or {}).get("send")
            at = _epoch(send)
            if at is not None and (best is None or at > best):
                best, src = at, "SendMessage from %s" % f
            if f not in stop_cache:
                stop_cache[f] = subagent_stop_at(start, f)
            at = stop_cache[f]
            if at is not None and (best is None or at > best):
                best, src = at, "SubagentStop of %s" % f
            # EVIDENCE COUNTS AS STATUS (operator ruling 2026-09-24). A transcript write is the growth a `--status` would have recorded, and a tool call in flight is the other half of the same test; asking the lead to restate either was churn the hook could answer itself. A shell waiter is live by its running shell.
            row_f = live.get(f)
            if row_f is not None:
                if row_f.get("inflight") or f in waiters:
                    best, src = (
                        now,
                        (
                            "tool call in flight in %s" % f
                            if row_f.get("inflight")
                            else "%s waiting on shell %s" % (f, waiters[f])
                        ),
                    )
                elif row_f.get("quiet_min") is not None:
                    at = now - row_f["quiet_min"] * 60
                    if best is None or at > best:
                        best, src = at, "transcript growth of %s" % f
        return best, src

    status_due, status_rows = [], {}
    # `worker:queue` is a placeholder, not an agent: nothing can report for it, and it is covered only while the cap is full, so its own lease expiry bounds it.
    # A workflow lease is covered only while its agents' stream is fresh, which is its evidence already.
    for w in sorted({w for _i, w, _c in covered} - {QUEUE_WORKER, LH.LEAD_WORKER} - set(workflows)):
        at, src = status_at(w)
        age = None if at is None else max(0.0, (now - at) / 60.0)
        status_rows[w] = (age, src)
        if age is None or age >= STATUS_PING_MIN:
            status_due.append(w)

    # Silence: a supervised live agent whose transcript stopped growing with nothing in flight, or whose last --status found no growth.
    supervised = set(writers) | {c for _i, _w, c in covered if c}
    silent = []
    for aid in sorted(supervised):
        row = live.get(aid)
        if row is None or aid in waiters:
            # A SHELL WAITER is not silent (agent/plans/PLAN-stop-hook-continuity.md P1.7): it ended its turn by definition, so its transcript cannot grow, and the harness resumes it when the shell it is waiting on exits.
            continue
        quiet = row["quiet_min"]
        last = (statuses.get(aid) or {}).get("last") or {}
        said_silent = bool(last.get("silent")) and int(last.get("size") or -1) == row["size"]
        if said_silent or (quiet is not None and quiet >= STATUS_PING_MIN and not row["inflight"]):
            silent.append(aid)

    # VERIFIED: a live agent the roster itself is supervising -- leased directly or through an ancestor, or the live descendant covering a lease -- that is neither silent nor owing a status. This, and not "live", is what may stand the 15-minute check-in down: an unleased reader is pinged by nothing here, so a stale one must keep the check-in (1.3's control 13h caught
    # the looser version).
    owing = set(silent) | set(status_due) | {c for _i, w, c in covered if w in status_due}
    leased_live = {a for a in live if any(x in leases for x in [a, *ancestors(a, metas)])}
    # An UNSUPERVISED reader is answered by its own transcript alone, the same evidence 1.3's stream check accepts: verified while it moved inside the ping window, and not once it has been quiet that long. An unleased WRITER is never verified; it is a defect of its own.
    fresh_readers = {
        a
        for a in readers
        if a not in leased_live
        and live[a]["quiet_min"] is not None
        and live[a]["quiet_min"] < STATUS_PING_MIN
    }
    verified = sorted((({c for _i, _w, c in covered if c} | leased_live) - owing) | fresh_readers)

    defects = bool(
        unleased or leased_dead or over_cap or status_due or silent or queue_start or plan_conflicts
    )
    if defects:
        state = "DISHONEST"
    elif blind or open_ids or unknown or not covered:
        state = "UNKNOWN"
    else:
        state = "HONEST"

    lease_of: dict[Any, Any] = {}
    for w, recs in leases.items():
        for r in recs:
            lease_of.setdefault(w, []).append(r["id"])
    for aid, row in live.items():
        row["leased"] = [i for x in [aid, *ancestors(aid, metas)] for i in lease_of.get(x, [])]
        age, src = status_rows.get(aid, (None, ""))
        if age is None and row["leased"]:
            for x in ancestors(aid, metas):
                if x in status_rows:
                    age, src = status_rows[x]
                    break
        row["status_age"], row["status_src"] = age, src
        row["age_min"] = None if not row["spawned"] else max(0.0, (now - row["spawned"]) / 60.0)
        row.pop("jsonl", None)

    return {
        "state": state,
        "blind": blind,
        "rows": live,
        "writers": writers,
        "readers": readers,
        "finished": sorted(finished),
        "unleased": unleased,
        "leased_dead": leased_dead,
        "queue_start": queue_start,
        "queue_free": slots,
        "queue_held": hold["id"] if hold is not None else "",
        "queue_skipped": pick["skipped"],
        "queue_conc_held": [(i, conc_held[i]) for i, _why in pick["skipped"] if i in conc_held],
        "plan_holders": plan_holders,
        "plan_conflicts": plan_conflicts,
        "plan_error": plan_error,
        "queued": len(queued),
        "over_cap": over_cap,
        "status_due": status_due,
        "status_rows": status_rows,
        "silent": silent,
        "verified": verified,
        "covered": covered,
        "unknown": unknown,
        "open": open_ids,
        "known_ids": set(metas),
    }


# ---- what a writer changed on disk -------------------------------------------------

# The commands whose PATH OPERANDS a Bash call writes, deletes or moves (agent/plans/PLAN-stop-hook-retro-20260925.md R20260925.1). A3 made 330 Bash calls against 78 Edits on 2026-09-24, and every edit the judge then asked the lead to sweep went through Bash: `sed -i` over the guards, two Python rewrites of baseline files, `git rm -r --cached` plus `rm -rf` of a directory.
BASH_WRITE_VERBS = frozenset({"rm", "mv", "cp", "sed", "tee", "truncate", "install"})
# `git <sub>` spellings whose operands are written.
GIT_WRITE_SUBS = frozenset({"rm", "mv"})
# A cheap prefilter: a command with none of these cannot write a file by any route read below, so the lexer never sees it.
_BASH_MAYBE_WRITES = re.compile(r">|\b(?:rm|mv|cp|sed|tee|truncate|install|python3?|git)\b")
# A Python body that writes, deletes or moves a file. Its presence makes every repo-path literal in the body count as written, which errs toward subtracting (Decision 2): a missed subtraction costs the lead a blocked turn, an extra one only defers the question to the writer's own tick.
_PY_WRITES = re.compile(
    r"open\((?:[^()]|\([^()]*\))*?,\s*(?:mode\s*=\s*)?['\"][rbt]*[wax+][rbtwax+]*['\"]"
    r"|\.write_(?:text|bytes)\(|\.unlink\(|\.rename\(|\.touch\("
    r"|\bos\.(?:remove|unlink|rename|replace|rmdir)\(|\bshutil\.(?:rmtree|move|copy\w*)\("
)
# A string literal that reads as a repo path: path characters only, with a `/` or a file extension. `HEAD:x` and `utf-8` are not.
_PY_PATH_LIT = re.compile(r"""['"]([A-Za-z0-9_.@+-][A-Za-z0-9_./@+-]*)['"]""")
# Shell characters that make an operand's value unknowable before it runs (`"$f"`, `*.py`): the literal directory in front of the first one is what the operand can touch.
_UNEXPANDABLE = re.compile(r"[$*?\[`{~]")


def _operands(argv, takes_value=()):
    """The non-option arguments of `argv`, with each option in `takes_value` consuming the next word. `--` ends the options."""
    out, skip, ended = [], False, False
    for arg in argv:
        if skip:
            skip = False
            continue
        if ended or not arg.startswith("-") or arg == "-":
            out.append(arg)
        elif arg == "--":
            ended = True
        elif arg in takes_value:
            skip = True
    return out


def _target_dir(argv):
    """The `-t DIR` / `--target-directory=DIR` of cp, mv and install, or ""."""
    for k, arg in enumerate(argv):
        if arg == "-t" and k + 1 < len(argv):
            return argv[k + 1]
        if arg.startswith("--target-directory="):
            return arg.split("=", 1)[1]
    return ""


def _sed_files(argv):
    """The files an IN-PLACE sed rewrites, or [] when it is not in place."""
    in_place = any(
        a.startswith("--in-place") or (a.startswith("-") and not a.startswith("--") and "i" in a)
        for a in argv
    )
    if not in_place:
        return []
    scripted = any(a in ("-e", "-f") or a.startswith(("--expression", "--file")) for a in argv)
    ops = _operands(argv, takes_value=("-e", "-f", "-l"))
    return ops if scripted else ops[1:]


def _run_operands(run):
    """The path operands one simple command writes, deletes or moves, as the lexer quote-removed them."""
    import posixpath  # noqa: PLC0415 -- stdlib, only on the Bash arm

    name = posixpath.basename(str(run.name or ""))
    argv = [str(a) for a in run.argv or []]
    if name == "git" and run.git_sub in GIT_WRITE_SUBS:
        at = argv.index(run.git_sub) if run.git_sub in argv else 0
        return _operands(argv[at + 1 :])
    if name not in BASH_WRITE_VERBS:
        return []
    if name == "sed":
        return _sed_files(argv)
    if name == "truncate":
        return _operands(argv, takes_value=("-s", "-r"))
    if name in ("cp", "install"):
        target = _target_dir(argv)
        if target:
            return [target]
        if name == "install" and any(a in {"-d", "--directory"} for a in argv):
            return _operands(argv, takes_value=("-m", "-o", "-g"))
        ops = _operands(argv, takes_value=("-m", "-o", "-g", "-S"))
        return ops[-1:] if len(ops) > 1 else []
    # rm, mv (sources vanish, the destination appears), tee.
    return _operands(argv, takes_value=("-t",)) + ([_target_dir(argv)] if _target_dir(argv) else [])


def _norm_under(path, base, root):
    """`path` joined to the absolute directory `base`, normalised, and made relative to `root`; None for a path that cannot name a repo file (the root itself, or an unknowable operand whose literal part is the root)."""
    import posixpath  # noqa: PLC0415

    m = _UNEXPANDABLE.search(path)
    if m:
        # The directory in front of the first unknowable character covers whatever the operand expands to (`"$f"` from a `cd` into the guards directory covers the guards directory).
        path = posixpath.dirname(path[: m.start()])
    full = posixpath.normpath(path if path.startswith("/") else posixpath.join(base, path))
    root = str(root).rstrip("/")
    if full == root:
        return None  # never the whole tree: that would subtract every lead edit with it
    if full.startswith(root + "/"):
        return full[len(root) + 1 :]
    return full  # outside the repo: kept absolute, which matches no `git status` line


def bash_write_paths(cmd, cwd, root):
    """Every repo-relative path a Bash command writes, deletes or moves, read from what bash would RUN (agent/plans/PLAN-stop-hook-retro-20260925.md R20260925.1).

    Three routes: an output redirect (the lexer's per-run writes, the same answer `shellscan.write_targets` gives, with the run's own directory), the path operands of `BASH_WRITE_VERBS` and `git rm|mv`, and the repo-path string literals of a Python heredoc or `-c` body that writes, unlinks or moves a file. Every path is joined to the `cd` in force for its clause and then to `cwd`, the directory the call ran in. A directory operand is returned as the directory and covers its subtree (`wl_reggate._covers`). An unknowable operand (`"$f"`, `*.json`) is cut back to its literal directory. Never raises: an unlexable command writes nothing it can prove.
    """
    import posixpath  # noqa: PLC0415

    if not cmd or not _BASH_MAYBE_WRITES.search(cmd):
        return set()
    try:
        shellscan = _shellscan()
        analysis = shellscan._analyse(
            cmd
        )  # the lexer's own walk, the same entry commit_policy.git_runs reads
        runs = list(analysis.runs)
        loose = shellscan.write_targets(cmd)
    except Exception:  # noqa: BLE001 -- a command the lexer cannot read proves no write
        return set()
    base_cwd = str(cwd or root)
    out, seen_writes = set(), []

    def add(raw, run_cwd):
        base = base_cwd if run_cwd is None else posixpath.join(base_cwd, str(run_cwd))
        rel = _norm_under(str(raw), base, root)
        if rel:
            out.add(rel)

    py_bodies = []
    for run in runs:
        for target in run.writes or []:
            seen_writes.append(target)
            add(target, run.cwd)
        for operand in _run_operands(run):
            add(operand, run.cwd)
        if posixpath.basename(str(run.name or "")).startswith("python"):
            argv = [str(a) for a in run.argv or []]
            body = argv[argv.index("-c") + 1] if "-c" in argv[:-1] else ""
            py_bodies.append((body, run.cwd))
    for target in loose:
        # A redirect on a brace group or a subshell belongs to no simple command, so only write_targets sees it.
        if target not in seen_writes:
            add(target, None)
    if py_bodies:
        heredocs = _heredoc_bodies(shellscan, cmd)
        for body, run_cwd in py_bodies:
            for text in [body, *heredocs]:
                if text and _PY_WRITES.search(text):
                    for lit in _PY_PATH_LIT.findall(text):
                        if "/" in lit or re.search(r"\.[A-Za-z0-9]{1,8}$", lit):
                            add(lit, run_cwd)
    return {p for p in out if p not in ("/dev/null", "/dev/stdout", "/dev/stderr")}


def _heredoc_bodies(shellscan, cmd):
    lexer = shellscan._Lexer(cmd)
    try:
        lexer.tokens()
    except Exception:  # noqa: BLE001 -- an unlexable command has no readable heredoc
        return []
    return [
        lexer.src[h.body_start : h.body_end]
        for h in lexer.heredocs
        if h.body_start is not None and h.body_end is not None
    ]


def _shellscan():
    """`rediacc_hooks.shellscan`, the guards' lexer, reached with `.claude` on sys.path the way that package expects."""
    import importlib.util  # noqa: PLC0415

    # The ONE canonical hop for .claude code (.claude/rediacc_hooks/syspath.py), loaded by file path because
    # this module lives outside the rediacc_hooks package (test_canonical_sys_path_hop).
    helper = pathlib.Path(__file__).resolve().parents[2] / "rediacc_hooks" / "syspath.py"
    spec = importlib.util.spec_from_file_location("_rediacc_syspath", helper)
    syspath = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(syspath)  # type: ignore[union-attr]
    syspath.on_sys_path(syspath.CLAUDE_DIR)
    from rediacc_hooks import shellscan  # noqa: PLC0415

    return shellscan


def edit_paths(jsonl, root):
    """Every repo-relative path one transcript's tool calls changed: the `file_path` (or `notebook_path`) of every edit tool call, and since R20260925.1 every path a Bash call wrote, deleted or moved (`bash_write_paths`, joined to the record's own `cwd`). Paths outside `root` are kept absolute, which never matches a `git status` line and so subtracts nothing."""
    try:
        data = jsonl.read_bytes()
    except (OSError, AttributeError):
        return set()
    base = str(root).rstrip("/") + "/"
    out = set()
    for rec in wl_common.records(data.splitlines(), need=b'"tool_use"'):
        if rec.get("type") != "assistant":
            continue
        content = (rec.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            raw = block.get("input")
            inp = raw if isinstance(raw, dict) else {}
            if block.get("name") == "Bash":
                out |= bash_write_paths(str(inp.get("command") or ""), rec.get("cwd"), root)
                continue
            if block.get("name") not in EDIT_TOOLS:
                continue
            path = str(inp.get("file_path") or inp.get("notebook_path") or "")
            if path:
                out.add(path.removeprefix(base))
    return out


class WriterPaths(set):
    """The paths the judge's tick-based fix-set subtracts, plus `by_tick`: {tick id: the paths of that ticked item's own lease workers}. A plain set to every caller that only subtracts; `wl_reggate.fixset_files` reads `by_tick` to answer a tick with its own writers' files (R20260925.2)."""

    by_tick: dict

    def __init__(self, paths=(), by_tick=None):
        super().__init__(paths)
        self.by_tick = dict(by_tick or {})


def _agent_workers(rec, metas):
    """The agents this item was ever leased to, oldest first: the fold's lease history, or the current worker for a record folded before that history existed. `queue` and `lead` are no agents."""
    hist = list(rec.get("lease_workers") or ())
    if not hist and rec.get("worker"):
        hist = [str(rec["worker"])]
    return [w for w in hist if w in metas]


def live_writer_paths(cwd, session_id, event, now=None, fold=None):
    """Every path the lead's tick-based fix-set must NOT carry, repo-relative, as a `WriterPaths`.

    agent/plans/PLAN-stop-hook-retro-20260924.md R.1: the judge's tick-based fix-set is the whole dirty tree, which carries every in-flight writer's uncommitted edits; on 2026-09-24 six of ten judge blocks demanded a sweep or a proof for work a writer still had in flight. Live is the roster's own predicate: listed running by the event (or a shell waiter) and not proven finished.

    agent/plans/PLAN-stop-hook-retro-20260925.md R20260925.2 (Decision 1): a FINISHED writer's edits stay subtracted while any item ever leased to it (or to an agent above it) is not ticked. Uncommitted edits the lead has not verified have not landed: at 19:50:04 on 2026-09-24 A3 had finished 41 seconds earlier and its baseline rewrites drew a sweep the lead could not own. Once every such item is ticked the writer's paths are the lead's again. A finished writer that never held a lease is the lead's at once, as before.

    `by_tick` maps each ticked item of this session that had agent lease workers to those workers' paths (their descendants included), keyed by `wl_reggate._tick_id` of its line. `fold` is the stop's own fold when the caller has one; it is loaded without syncing otherwise. Never raises: an unreadable roster subtracts nothing, which keeps the demand.
    """
    now = time.time() if now is None else now
    try:
        metas = load_metas(session_subagents_dir(cwd, session_id))
        if not metas:
            return WriterPaths()
        kids = children_map(metas)
        running = _running(event or {})
        waiters = shell_waiters(running, metas)
        listed = {str(b.get("id") or "") for b in running if b.get("type") == "subagent"} | set(
            waiters
        )
        start = C.project_start({"cwd": cwd})
        root = C.project_root(start)
        cache: dict[str, set] = {}

        def paths_of(aids):
            out = set()
            for aid in aids:
                m = metas.get(aid)
                if not m or m.get("jsonl") is None:
                    continue
                if aid not in cache:
                    cache[aid] = edit_paths(m["jsonl"], root)
                out |= cache[aid]
            return out

        def lineage(aids):
            return {d for a in aids for d in [a, *descendants(a, kids)]}

        live = set()
        for aid in listed:
            m = metas.get(aid)
            if not m or m.get("jsonl") is None:
                continue
            if aid not in waiters and proven_finished(
                m["jsonl"], now, m.get("name", ""), cwd, session_id
            ):
                continue
            live.add(aid)
        if fold is None:
            import wl_store as S  # noqa: PLC0415

            fold = S.load(C.worklist_for(start), sync=False)
        import wl_reggate as RG  # noqa: PLC0415 -- wl_reggate imports nothing of the roster

        pending, by_tick = set(), {}
        for rec in getattr(fold, "items", None) or []:
            if not C.owned_by_me(rec.get("owner"), session_id):
                continue
            workers = _agent_workers(rec, metas)
            if not workers:
                continue
            if rec.get("state") == "x":
                by_tick[RG._tick_id(rec.get("line") or "")] = frozenset(paths_of(lineage(workers)))
            elif rec.get("state") not in LH.CLOSED_STATES:
                pending |= set(workers)
        return WriterPaths(paths_of(lineage(live | pending)), by_tick)
    except Exception:  # noqa: BLE001 -- subtracting nothing keeps the demand, the safe side
        return WriterPaths()


def known_subagent_ids(cwd, session_id):
    """Every agent id with a meta in this session. The liveness ladder skips their leases."""
    return set(load_metas(session_subagents_dir(cwd, session_id)))


def roster_covers_all(live_bg, verdict):
    """True when every live background task is a roster-verified subagent.

    Roster-verified means SUPERVISED by the roster (leased directly, through an ancestor, or covering a lease as a live descendant), not silent and not owing a status. A shell keeps its 15-minute check-in, and so does a teammate: the roster cannot read either one's clock. An OS-confirmed shell is still covered, by `wl_liveness.all_waits_live`, the other term of the same predicate in run_stop.
    """
    bg = [b for b in live_bg or [] if isinstance(b, dict)]
    if not bg or not verdict or verdict.get("blind"):
        return False
    verified = set(verdict.get("verified") or ())
    return all(b.get("type") == "subagent" and str(b.get("id") or "") in verified for b in bg)


def lastevent_path(cwd, session_id):
    wl = C.worklist_for(C.project_start({"cwd": cwd}))
    return wl.with_suffix(".lastevent-%s.json" % (session_id or "unknown")[:8])


def live_estimate(cwd, session_id, now=None):
    """(rows, metas) for every agent the session is running right now, readers included; rows is None when it cannot tell.

    A PreToolUse payload or a CLI call carries no background-task list, so this ESTIMATES: the last Stop event's running subagents, plus every agent whose meta was written after that event (started this turn, which the event cannot know yet), minus any whose transcript is proven finished. With no event on disk at all, an agent counts when its transcript moved in the last STATUS_PING_MIN minutes.
    Each row carries `id`, `type`, `desc` and `writer`, by type only: there is no state doc here to cache an evidence scan in. The Stop hook recomputes from the authoritative event on the next stop either way.
    """
    now = time.time() if now is None else now
    sub_dir = session_subagents_dir(cwd, session_id)
    if sub_dir is None:
        return None, {}
    metas = load_metas(sub_dir)
    ro_types = read_only_types(C.project_root(C.project_start({"cwd": cwd})))
    types, since, waiters = {}, None, {}
    try:
        p = lastevent_path(cwd, session_id)
        doc = json.loads(p.read_text(encoding="utf-8"))
        since = p.stat().st_mtime
        for b in _running(doc):
            if b.get("type") == "subagent" and b.get("id"):
                types[str(b["id"])] = str(b.get("agent_type") or "")
        waiters = shell_waiters(_running(doc), metas)
        for aid in waiters:
            types.setdefault(aid, metas[aid]["type"])
    except (OSError, ValueError, AttributeError, TypeError):
        types, since, waiters = {}, None, {}
    for aid, m in metas.items():
        if since is not None:
            fresh = m["spawned"] > since
        else:
            mt = _mtime(m["jsonl"])
            fresh = mt is not None and now - mt <= STATUS_PING_MIN * 60
        if fresh and aid not in types:
            types[aid] = m["type"]
        elif aid not in types and aid not in waiters:
            # WAITING SINCE THE EVENT: the last Stop event may already call it completed while the shell it armed after that event still runs. Its own transcript says so.
            wshell = transcript_waiting(m["jsonl"], now)
            # "After that event" is checked, not assumed: a transcript that has not moved since the event was written armed its shell BEFORE it, and the event (which lists every running shell) did not list the agent's. A TaskStop-ped agent is exactly that shape -- its transcript still ends waiting on a shell that died with it -- and this branch kept it live for WAIT_HORIZON_MIN, holding a writer slot the Stop hook already saw free (2026-09-24, pr-babysitter a149262d8b6a1601f, #b9d4dcb2).
            mt_agent = _mtime(m["jsonl"])
            if wshell and since is not None and (mt_agent is None or mt_agent <= since):
                wshell = ""
            if wshell:
                waiters[aid] = wshell
                types[aid] = m["type"]
    done = _completed_since(sub_dir, since)
    rows = []
    for aid, typ in sorted(types.items()):
        m = metas.get(aid) or {}
        kind = typ or m.get("type") or "?"
        if (
            m
            and aid not in waiters
            and (
                proven_finished(m["jsonl"], now, m.get("name", ""), cwd, session_id)
                or _done_after(done.get(_short(aid)), m)
            )
        ):
            # ONE NUMBER FOR BOTH CALLERS: an agent listed as running by the last event that has since ended its turn to wait on a shell is a live writer, not a finished one. The spawn guard and `--lease worker:queue` both read this function, so they now agree.
            wshell = transcript_waiting(m["jsonl"], now)
            if not wshell:
                continue
            waiters[aid] = wshell
        rows.append(
            {
                "id": aid,
                "type": kind,
                "desc": (m.get("desc") or "")[:60],
                "writer": kind not in ro_types,
                "waiting": waiters.get(aid, ""),
            }
        )
    return rows, metas


def _short(aid):
    import wl_report as RPT  # noqa: PLC0415

    return RPT.short_id(aid)


def _completed_since(sub_dir, since):
    """{short agent id: epoch} of every COMPLETED task notification that reached the LEAD's transcript after `since` (the last Stop event's mtime), result or not. {} when there is no event or no transcript.

    The lead transcript sits beside the session's `subagents/` directory as `<session>.jsonl`. Reuses `wl_report.delivered_ids` without its non-empty `<result>` filter (agent/plans/PLAN-stop-hook-retro-20260924.md R.6).
    """
    if since is None or sub_dir is None:
        return {}
    import wl_report as RPT  # noqa: PLC0415

    try:
        ids, _cur = RPT.delivered_ids(sub_dir.parent.with_suffix(".jsonl"), require_result=False)
    except Exception:  # noqa: BLE001 -- an unreadable transcript drops nobody, the safe side for a cap
        return {}
    return {k: v for k, v in ids.items() if v > since}


def _done_after(done_at, meta):
    """True when the harness reported this agent completed AFTER its last (re)start. A resumed agent rewrites its meta, so a later `spawned` means the completion is history."""
    return done_at is not None and (meta.get("spawned") or 0) <= done_at


def live_writers_estimate(cwd, session_id, now=None):
    """The live WRITER rows the PreToolUse guard counts, or None when it cannot count. See `live_estimate`."""
    rows, _metas = live_estimate(cwd, session_id, now=now)
    if rows is None:
        return None
    return [r for r in rows if r["writer"]]


def _tail_facts(jsonl):
    """(last assistant text, last tool call with its target) from a bounded tail of the transcript."""
    import wl_report as RPT  # noqa: PLC0415

    text, tool = "", ""
    for raw in reversed(RPT._bounded_lines(jsonl, TAIL_BYTES)):
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(rec, dict) or rec.get("type") != "assistant":
            continue
        content = (rec.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in reversed(content):
            if not isinstance(block, dict):
                continue
            if not tool and block.get("type") == "tool_use":
                raw_inp = block.get("input")
                inp = raw_inp if isinstance(raw_inp, dict) else {}
                target = next(
                    (
                        str(inp[k])
                        for k in ("file_path", "command", "description", "pattern", "to")
                        if inp.get(k)
                    ),
                    "",
                )
                tool = "%s %s" % (block.get("name") or "?", " ".join(target.split())[:160])
            if not text and block.get("type") == "text" and str(block.get("text") or "").strip():
                text = " ".join(str(block["text"]).split())
        if text and tool:
            break
    return text[:STATUS_TEXT_MAX] or "(none in the tail)", tool or "(none in the tail)"


def full_edit_count(jsonl):
    """Edit tool calls across the WHOLE transcript, read in SCAN_STEP_BYTES steps."""
    ent: dict[Any, Any] = {}
    for _ in range(100000):
        before = int(ent.get("off") or 0)
        ent = scan_transcript(jsonl, ent)
        if int(ent.get("off") or 0) == before:
            break
    return int(ent.get("edits") or 0)


def status_verb(worklist, me, target, session_id=None, cwd=None, now=None):
    """`worklist.py --status <me> [<id>|all]`: read each worker's transcript and record what it showed.

    Returns (text, rc). A status RESETS the 20-minute clock only when the transcript grew since the previous status (or, with no previous one, moved inside the ping window) or a tool call is in flight; otherwise it is recorded `silent` and the next stop raises `roster-silent`. The lead reads; the hook decides what the read proves.
    """
    import wl_store as S  # noqa: PLC0415
    import worklist_messages as M  # noqa: PLC0415

    now = time.time() if now is None else now
    session_id = session_id or me
    cwd = cwd or str(C.project_start())
    rows, metas = live_estimate(cwd, session_id, now=now)
    if rows is None:
        return M.CLI_STATUS_BLIND % session_id, 1
    if target in ("all", "", None):
        picked = [r["id"] for r in rows]
    elif target in metas:
        picked = [target]
    else:
        picked = []
    if not picked:
        return M.CLI_STATUS_NONE % target, 1
    fold = S.load(worklist, sync=False)
    kids = children_map(metas)
    out = []
    for aid in picked:
        m = metas.get(aid) or {}
        jsonl: Any = m.get("jsonl")
        try:
            st = jsonl.stat()
        except (OSError, AttributeError):
            out.append("%s: no transcript on disk, nothing recorded" % aid)
            continue
        prev = ((fold.statuses or {}).get(aid) or {}).get("last") or {}
        if prev:
            grew = st.st_size != int(prev.get("size") or -1)
        else:
            grew = now - st.st_mtime < STATUS_PING_MIN * 60
        inflight = inflight_tool(last_record(jsonl))
        waiting = next((r.get("waiting") for r in rows if r["id"] == aid), "") or ""
        # A SHELL WAITER is not silent (P1.7): its turn ended by definition and the harness resumes it when the shell exits.
        silent = not grew and not inflight and not waiting
        S.status_event(worklist, me, aid, st.st_size, st.st_mtime, inflight, silent)
        text, tool = _tail_facts(jsonl)
        lineage = "depth %s" % m.get("depth", 1)
        if m.get("parent"):
            lineage += ", child of %s" % m["parent"]
        live_kids = [k for k in descendants(aid, kids) if k in {r["id"] for r in rows}]
        out.append(
            M.CLI_STATUS_ROW
            % {
                "id": aid,
                "type": m.get("type") or "?",
                "desc": m.get("desc", "")[:60],
                "lineage": lineage,
                "children": ", ".join(live_kids) or "none",
                "size": st.st_size,
                "quiet": _mins(max(0.0, (now - st.st_mtime) / 60.0)),
                "edits": full_edit_count(jsonl),
                "tool": tool + ("  (IN FLIGHT)" if inflight else ""),
                "text": text,
                "verdict": (
                    "SILENT: the transcript has not grown and nothing is in flight; the clock was "
                    "NOT reset and the next stop raises roster-silent"
                    if silent
                    else "WAITING on shell %s: the harness resumes it when that shell exits"
                    % waiting
                    if waiting and not grew and not inflight
                    else "status recorded; the 20-minute clock restarts"
                ),
            }
        )
    return "\n\n".join(out), 0


# ---- rendering -----------------------------------------------------------------


def _mins(v):
    return "?" if v is None else "%dm" % v


def row_line(row):
    """One worker, the way every roster message prints it."""
    lineage = "depth %s" % row.get("depth", 1)
    if row.get("parent"):
        lineage += ", child of %s" % row["parent"]
    return "%s %s (%s) %r, %s, started %s ago, quiet %s%s, items: %s, status %s ago via %s" % (
        "WRITER" if row.get("writer") else "reader",
        row["id"],
        row.get("type") or "?",
        row.get("desc") or "",
        lineage,
        _mins(row.get("age_min")),
        _mins(row.get("quiet_min")),
        ", in tool %s" % row["inflight"] if row.get("inflight") else "",
        ",".join("#" + i for i in row.get("leased") or []) or "none",
        _mins(row.get("status_age")),
        row.get("status_src") or "none",
    )


def defect_rows(verdict):
    """{"cap", "silent", "unleased", "dead"}: the rendered rows each roster block quotes. Never truncated: a defect list is short by nature, and a capped one would hide the id the remedy needs."""
    rows = verdict.get("rows") or {}

    def lines(ids):
        return "\n".join("    " + row_line(rows[a]) for a in ids if a in rows) or "    (none)"

    status = []
    for w in verdict.get("status_due") or []:
        age, src = (verdict.get("status_rows") or {}).get(w, (None, "none"))
        coverer = next((c for _i, lw, c in verdict.get("covered") or [] if lw == w), w)
        status.append(
            "    %s: last status %s ago via %s%s"
            % (w, _mins(age), src, "" if coverer == w else "; its live descendant is %s" % coverer)
        )
    dead = [
        "    #%s leased to worker:%s, which is not live and has no live descendant" % (i, w)
        for i, w, _c in verdict.get("leased_dead") or []
    ]
    # MERGED (operator ruling 2026-09-24, "Evidence counts as status"): a worker whose newest evidence is STATUS_PING_MIN old is the same fact as a silent one, so its status row rides the silent block rather than a second key.
    silent_ids = list(verdict.get("silent") or [])
    silent_rows = ["    " + row_line(rows[a]) for a in silent_ids if a in rows] + [
        ln
        for ln, w in zip(status, verdict.get("status_due") or [], strict=True)
        if w not in silent_ids
    ]
    return {
        "cap": lines(verdict.get("writers") or []),
        "silent": "\n".join(silent_rows) or "    (none)",
        "unleased": lines(verdict.get("unleased") or []),
        "dead": "\n".join(dead) or "    (none)",
    }


def summary_lines(verdict, limit=SUMMARY_ROWS_MAX):
    rows = verdict.get("rows") or {}
    order = list(verdict.get("writers") or []) + list(verdict.get("readers") or [])
    out = ["  " + row_line(rows[a]) for a in order[:limit] if a in rows]
    if len(order) > limit:
        out.append("  + %d more worker(s), all counted above" % (len(order) - limit))
    return out


def next_status_due(verdict, now=None):
    """HH:MMZ when the earliest leased worker next owes a status, or "now"."""
    now = time.time() if now is None else now
    ages = [a for a, _s in (verdict.get("status_rows") or {}).values() if a is not None]
    if not ages:
        return "now"
    left = STATUS_PING_MIN - max(ages)
    if left <= 0:
        return "now"
    return time.strftime("%H:%MZ", time.gmtime(now + left * 60))


def explain_lastevent(prefix):
    """The roster verdict for the last FULL Stop event of `prefix`, rendered. Read-only.

    The in-tree way to rerun an incident: it reads the `.lastevent-<prefix>.json` sidecar the Stop hook wrote, folds the store without syncing, loads the state doc without saving it, and prints what `roster()` concludes.
    """
    import wl_store as S  # noqa: PLC0415

    start = C.project_start()
    worklist = C.worklist_for(start)
    side = worklist.with_suffix(".lastevent-%s.json" % prefix[:8])
    try:
        event = json.loads(side.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return "ROSTER: cannot read %s (%s); no verdict" % (side, exc)
    sid = str(event.get("session_id") or prefix)
    fold = S.load(worklist, sync=False)
    state_doc = S.load_state(worklist, sid)
    v = roster(event, fold, sid, state_doc=state_doc, cwd=event.get("cwd") or str(start))
    lines = [
        "ROSTER %s: %d writer(s)/%d, %d reader(s), %d finished-but-listed, %d open item(s), from %s"
        % (
            v["state"],
            len(v["writers"]),
            WRITER_CAP,
            len(v["readers"]),
            len(v["finished"]),
            len(v["open"]),
            side,
        )
    ]
    lines.extend(summary_lines(v, limit=len(v["rows"]) or 1))
    for label, items in (
        ("over cap", v["over_cap"]),
        ("unleased writers", v["unleased"]),
        ("silent or no evidence", sorted(set(v["silent"]) | set(v["status_due"]))),
    ):
        if items:
            lines.append("  %s: %s" % (label, ", ".join(items)))
    lines.extend(
        "  leased dead: #%s on worker:%s (no live agent in its lineage)" % (i, w)
        for i, w, _c in v["leased_dead"]
    )
    lines.extend("  unknown: #%s on worker:%s (%s)" % (i, w, why) for i, w, why in v["unknown"])
    # THE REPLAY IS OLDER THAN THE TREE IT READS. The sidecar is the last stop's event, while the metas and transcripts are read as they are now, so an agent spawned after that stop is absent from the event and its lease reads as dead here. Said out loud rather than left to be mistaken for a verdict about the agent.
    try:
        since = side.stat().st_mtime
        later = sorted(
            aid
            for aid, m in load_metas(session_subagents_dir(event.get("cwd") or "", sid)).items()
            if m["spawned"] > since
        )
    except OSError:
        later = []
    if later:
        lines.append(
            "  NOTE: %d agent(s) were spawned or resumed after this event was written (%s), so "
            "the event may not list them and a lease on one can read as dead in this replay: %s"
            % (len(later), time.strftime("%H:%MZ", time.gmtime(since)), ", ".join(later))
        )
    return "\n".join(lines)


if __name__ == "__main__":
    # `python3 .claude/hooks/stop/wl_roster.py <session-prefix>`: the read-only incident replay.
    import sys

    if len(sys.argv) != 2:
        sys.exit("usage: wl_roster.py <session-prefix>   (replays the last full Stop event)")
    print(explain_lastevent(sys.argv[1]))
