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
import pathlib
import re
import time

import wl_core as C

# ---- the sealed constants ---------------------------------------------------

# The operator's number. A writer beyond it is refused at spawn (guards/block_agent_cap.py) and blocked at Stop (`roster-cap`).
WRITER_CAP = 4
# The operator's number. A leased worker whose newest status is this old owes one (`roster-status`); a transcript this quiet with no tool call in flight is `roster-silent`.
STATUS_PING_MIN = 20
# A lease on `worker:queue` holds writer work the cap forbids starting. It is covered ONLY while every writer slot is taken; the moment one frees it is a defect naming the item to start, so it can never park work behind a cap that is not full.
QUEUE_WORKER = "queue"
# The tool calls that prove an agent writes, whatever its declared type says.
EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
# The harness types that never write (plan F6: 0 edit calls in 66 Plan and 65 Explore transcripts). Custom read-only types are ADDED from `.claude/agents/*.md` by `read_only_types`, never subtracted.
READ_ONLY_AGENT_TYPES = frozenset({"Plan", "Explore"})
# The pushes an HONEST roster answers. The ladder keys are deliberately ABSENT, and that is a narrowing of the plan's list rather than an omission: `wl_liveness.ladder` skips every subject whose worker is a known subagent, so a ladder key that reaches the filter is BY CONSTRUCTION about a shell lease, a teammate or a harness task, which the plan says must keep firing. `agent-state`
# is dropped only for its `stale` verdict; the caller enforces that.
ROSTER_SUPPRESSES = frozenset({"bg-report", "stuck", "idle-stall", "solo-grind", "agent-state"})
# The five defect keys, in the order the plan names them.
ROSTER_KEYS = ("roster-cap", "roster-status", "roster-silent", "roster-unleased", "roster-dead")

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
    out = {}
    if sub_dir is None:
        return out
    try:
        paths = list(sub_dir.glob("agent-*.meta.json"))
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
    kids = {}
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
    for raw in blob[: cut + 1].splitlines():
        if b'"tool_use"' not in raw:
            continue
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(rec, dict) or rec.get("type") != "assistant":
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


def shell_waiters(running, metas):
    """{agent id: shell id} for every agent the event does NOT list as running whose own transcript launched a shell that still runs.

    An agent that armed a background command and ended its turn is WAITING, not finished: the harness resumes it when that shell exits, yet the event reports the agent itself as completed. Its launch leaves `"backgroundTaskId":"<id>"` in the agent's transcript, and that is the only link between the two, since the event's shell rows carry no owner.
    """
    listed = {str(b.get("id") or "") for b in running if b.get("type") == "subagent"}
    shell_ids = [
        str(b.get("id") or "") for b in running if b.get("type") == "shell" and b.get("id")
    ]
    out = {}
    if not shell_ids:
        return out
    for aid, m in metas.items():
        if aid in listed or m.get("jsonl") is None:
            continue
        try:
            data = m["jsonl"].read_bytes()
        except OSError:
            continue
        for sid in shell_ids:
            if b'"backgroundTaskId":"%s"' % sid.encode() in data:
                out[aid] = sid
                break
    return out


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
    open_ids = [r["id"] for r in mine if r.get("state") == " "]
    leases = {}
    for r in mine:
        if r.get("state") != ">":
            continue
        ls = C.lease_state(r.get("line") or "")
        w = _worker_of(r)
        if ls != "fresh" and not (ls == "expired" and w and w in live_ids):
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

    covered, leased_dead, unknown = [], [], []
    for w, recs in leases.items():
        if w == QUEUE_WORKER:
            full = len(writers) >= WRITER_CAP
            for r in recs:
                (covered if full else leased_dead).append(
                    (r["id"], w, QUEUE_WORKER if full else "")
                )
            continue
        if w and (w in metas or w in live):
            coverer = covered_by(w)
            for r in recs:
                (covered if coverer else leased_dead).append((r["id"], w, coverer))
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
        return best, src

    status_due, status_rows = [], {}
    # `worker:queue` is a placeholder, not an agent: nothing can report for it, and it is covered only while the cap is full, so its own lease expiry bounds it.
    for w in sorted({w for _i, w, _c in covered} - {QUEUE_WORKER}):
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
        if row is None:
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

    defects = bool(unleased or leased_dead or over_cap or status_due or silent)
    if defects:
        state = "DISHONEST"
    elif blind or open_ids or unknown or not covered:
        state = "UNKNOWN"
    else:
        state = "HONEST"

    lease_of = {}
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


def known_subagent_ids(cwd, session_id):
    """Every agent id with a meta in this session. The ladder and the poll path skip their leases."""
    return set(load_metas(session_subagents_dir(cwd, session_id)))


def roster_covers_all(live_bg, verdict, bg_verdicts=None):
    """True when every live background task is a roster-verified subagent or an OS-confirmed waiter.

    Roster-verified means SUPERVISED by the roster (leased directly, through an ancestor, or covering a lease as a live descendant), not silent and not owing a status. A shell that is not a confirmed waiter keeps its 15-minute check-in, and so does a teammate: the roster cannot read either one's clock.
    """
    import wl_liveness as L  # noqa: PLC0415

    bg = [b for b in live_bg or [] if isinstance(b, dict)]
    if not bg or not verdict or verdict.get("blind"):
        return False
    waiters = {str(b.get("id") or "") for b in L.confirmed_waiters(bg, bg_verdicts or {})}
    verified = set(verdict.get("verified") or ())
    for b in bg:
        tid = str(b.get("id") or "")
        if b.get("type") == "subagent":
            if tid not in verified:
                return False
        elif tid not in waiters:
            return False
    return True


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
    rows = []
    for aid, typ in sorted(types.items()):
        m = metas.get(aid) or {}
        kind = typ or m.get("type") or "?"
        if (
            m
            and aid not in waiters
            and proven_finished(m["jsonl"], now, m.get("name", ""), cwd, session_id)
        ):
            continue
        rows.append(
            {
                "id": aid,
                "type": kind,
                "desc": (m.get("desc") or "")[:60],
                "writer": kind not in ro_types,
            }
        )
    return rows, metas


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
                inp = block.get("input") if isinstance(block.get("input"), dict) else {}
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
    ent = {}
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
        jsonl = m.get("jsonl")
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
        silent = not grew and not inflight
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
    """{"cap", "status", "silent", "unleased", "dead"}: the rendered rows each roster block quotes. Never truncated: a defect list is short by nature, and a capped one would hide the id the remedy needs."""
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
        (
            "    #%s is queued behind the writer cap, and a slot is free now: start it" % i
            if w == QUEUE_WORKER
            else "    #%s leased to worker:%s, which is not live and has no live descendant"
            % (i, w)
        )
        for i, w, _c in verdict.get("leased_dead") or []
    ]
    return {
        "cap": lines(verdict.get("writers") or []),
        "status": "\n".join(status) or "    (none)",
        "silent": lines(verdict.get("silent") or []),
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
        ("status due", v["status_due"]),
        ("silent", v["silent"]),
    ):
        if items:
            lines.append("  %s: %s" % (label, ", ".join(items)))
    lines.extend(
        "  leased dead: #%s on worker:%s (no live agent in its lineage)" % (i, w)
        for i, w, _c in v["leased_dead"]
    )
    lines.extend("  unknown: #%s on worker:%s (%s)" % (i, w, why) for i, w, why in v["unknown"])
    # THE REPLAY IS OLDER THAN THE TREE IT READS. The sidecar is the last FULL stop's event (a silent poll stop does not rewrite it), while the metas and transcripts are read as they are now, so an agent spawned after that stop is absent from the event and its lease reads as dead here. Said out loud rather than left to be mistaken for a verdict about the agent.
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
