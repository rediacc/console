"""wl_stuckshell: an agent that waits on a shell yet is finished or past a bound is STUCK, not live (agent/plans/PLAN-writers-now-cadence.md, box WN4).

THE SHAPE (2026-11-23). Writer a7f511c739e4aa739 (stripe-disable) launched its own `npm run ci -- --narrow` as background shell `bgjvtrdck`, ended its turn with a final TICK block, and the harness showed it as "waiting on 1 shell" for hours. `wl_roster.shell_waiters` counted any agent with an armed, running shell as a live writer with no bound short of WAIT_HORIZON_MIN, so its lease stayed covered and no dead-writer or silence check fired.

STUCK means the agent waits on a shell (the `wl_roster.armed_waiters` shape: not listed running, its transcript armed a shell the event still lists) AND either

  (a) its final report is captured: a `wl_report` index row for the agent, captured at or after the shell's launch, that names a box through a TICK line (`boxes`) or is a closing summary (not silent, not a relay, no interim shell, and at least `wl_report.RELAY_FLOOR` bytes, the calibrated gap between turn-end status lines and real reports); or
  (b) the shell has run longer than STUCK_SHELL_MIN minutes, measured from the timestamp of the transcript record that launched it.

A stuck agent is not live: `wl_roster.shell_waiters` drops it, so the roster, `wl_liveness.live_worker_ids` and the writer estimate stop counting it, and the `stuck-shell` check names the agent, the shell and the two moves.

LIVE WORK IS NEVER A TaskStop ORDER (2026-11-26), the wl_bgsweep rule (ca5331e3e4) applied here. Shell bxhnqm2th ran `cf_retire archive rediacc-www-media --to-bucket media`, a 3-hour sha256 verify of 8,422 objects, past the bound, and this check ordered `TaskStop bxhnqm2th` on every stop although the lead's item was leased to that very shell (`worker:bxhnqm2th`). Each stuck row now carries `live` (the command of the first descendant of the shell doing real work, per `wl_bgsweep.live_command`: not a sleep, a poll probe, a shell layer or the wake timer) and `leased` (the id of an in-flight item whose lease names `worker:<shell>`).
A row with either is OWNED work: `blocking` drops it, and `render_live` reports it once, age-free, under the `stuck-shell-live` advisory with no TaskStop. A shell that only waits blocks unless a FRESH lease names it: a lease past its `until:` (or with none, or one beyond the 120-minute cap) exempts nothing, so a lease a dead worker never released stops covering its shell once it expires. The roster's liveness is unchanged: a stuck agent stays not-live, since the work belongs to the shell, which the event lists running.

A launch record with no readable timestamp answers nothing for (a) or (b), since a report captured before the launch belongs to an earlier turn, and a report store that cannot be read answers nothing for (a); neither makes an agent stuck. Like wl_roster this module reads no environment variable: every threshold is a literal, so no knob can keep a stuck agent live.
"""

import json
import pathlib
import time

import wl_core as C

# Minutes a background shell may run while its agent waits before the agent counts as stuck (operator ruling #ac2de21f, 2026-11-23).
STUCK_SHELL_MIN = 45


def launched_at(jsonl, sid):
    """Epoch seconds of the newest transcript record carrying `"backgroundTaskId":"<sid>"`, or None when the transcript cannot be read or no such record carries a parseable `timestamp`."""
    import wl_roster as R

    needle = ('"backgroundTaskId":"%s"' % sid).encode()
    try:
        data = pathlib.Path(jsonl).read_bytes()
    except (OSError, TypeError):
        return None
    at = None
    for line in data.splitlines():
        if needle not in line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        when = R._epoch(rec.get("timestamp")) if isinstance(rec, dict) else None
        if when is not None:
            at = when
    return at


def is_final(entry):
    """True when a report index row is a final report: it names a box through a TICK line and is not `interim`, or it is a closing summary (see the module docstring). An `interim` row is never final, ticked boxes or not."""
    import wl_report as RPT

    if entry.get("boxes"):
        # A TICK block wins over an armed shell (the report closes the work), but not over `interim`: a mid-task report that ticks one box still waits on its next shell.
        return not entry.get("interim")
    return (
        not entry.get("silent")
        and not entry.get("relay")
        and not entry.get("interim")
        and not entry.get("armed")
        and int(entry.get("bytes") or 0) >= RPT.RELAY_FLOOR
    )


def final_report(entries, aid, since):
    """The newest report row captured for `aid` at or after epoch `since` when that row is final, else None.

    Only the NEWEST row decides: an older closing-looking row is superseded by a newer interim one (2026-11-23: the hostinger runner's report -2 predated the `armed` field and read as final while its newer report -4 said it was still waiting on its restart)."""
    import wl_report as RPT
    import wl_roster as R

    rid = RPT.short_id(aid)
    newest = None
    newest_at = None
    for e in entries or []:
        ident = str(e.get("id") or "")
        if ident != rid and not ident.startswith(rid + "-"):
            continue
        at = R._epoch(e.get("at"))
        if at is None or at < since:
            continue
        if newest_at is None or at >= newest_at:
            newest, newest_at = e, at
    return newest if newest is not None and is_final(newest) else None


def classify(waiters, metas, entries, now=None):
    """{agent id: row} for each stuck agent among `waiters` ({agent id: shell id}).

    Each row carries `shell`, `reason` ("report" or "runtime"), `report` (the report id, or ""), and `age_min` (the shell's runtime in minutes, or None when its launch time is unreadable). `entries` is the report index (`wl_report.read_index`), or None when it could not be read, which leaves only the runtime test."""
    now = time.time() if now is None else now
    out = {}
    for aid, sid in (waiters or {}).items():
        jsonl = (metas.get(aid) or {}).get("jsonl")
        start = launched_at(jsonl, sid) if jsonl is not None else None
        age = None if start is None else max(0.0, (now - start) / 60.0)
        rep = (
            final_report(entries, aid, start) if entries is not None and start is not None else None
        )
        if rep is not None:
            out[aid] = {"shell": sid, "reason": "report", "report": str(rep["id"]), "age_min": age}
        elif age is not None and age > STUCK_SHELL_MIN:
            out[aid] = {"shell": sid, "reason": "runtime", "report": "", "age_min": age}
    return out


def report_entries(start, problems=None):
    """The report index for project `start`, or None when `start` is None or the read raised (the error is appended to `problems`)."""
    if start is None:
        return None
    import wl_report as RPT

    try:
        return RPT.read_index(RPT.store_root(start))
    except Exception as exc:
        if problems is not None:
            problems.append("report index: %s: %s" % (type(exc).__name__, exc))
        return None


def stuck_waiters(running, metas, start=None, now=None, problems=None):
    """{agent id: row} (see `classify`) for every stuck agent among the shell waiters of `running`, the event's running background tasks."""
    import wl_roster as R

    waiters = R.armed_waiters(running, metas, now)
    if not waiters:
        return {}
    return classify(waiters, metas, report_entries(start, problems), now)


def shell_work(shell_ids, table_with_age=None, anchor_table=None, stdout_task=None):
    """{shell id: command} for each shell in `shell_ids` that a descendant process is doing real work for (`wl_bgsweep.live_command`), read from this session's own harness subtree.

    A shell is found as the topmost row writing its `tasks/<id>.output` (the wl_bgsweep.findings rule). An unreadable process table or an unresolved anchor answers {}: no shell is called live, so nothing that only waits is excused."""
    import wl_bgsweep as B

    wanted = {str(s) for s in shell_ids or () if s}
    if not wanted:
        return {}
    if table_with_age is None:
        table_with_age = B.proc_table_with_age()
    if not table_with_age:
        return {}
    anchor = B.resolve_anchor(
        anchor_table
        if anchor_table is not None
        else [(p, pp, c) for p, pp, c, _a in table_with_age]
    )
    if anchor is None:
        return {}
    task = stdout_task or B._stdout_task
    rows = B.descendants(anchor, table_with_age)
    task_of = {r[0]: task(r[0]) for r in rows}
    out = {}
    for pid, ppid, _cmd, _age in rows:
        sid = task_of.get(pid)
        if sid in wanted and sid not in out and task_of.get(ppid) != sid:
            work = B.live_command(rows, pid)
            if work:
                out[sid] = work
    return out


def leased_shells(items):
    """{worker id: item id} for each in-flight (`>`) item whose lease is fresh (`wl_core.lease_state`), from the `worker:<id>` it names.

    An expired, missing or over-cap `until:` names no shell: a lease is a time-boxed claim, and one its worker died holding must stop exempting a hung shell once the box closes (review f4b82bed.4)."""
    out: dict[str, str] = {}
    for rec in items or ():
        if rec.get("state") != ">":
            continue
        line = rec.get("line") or ""
        if "until:" not in line and rec.get("until"):
            line += " until:%s" % rec["until"]
        if C.lease_state(line) != "fresh":
            continue
        wm = C.WORKER.search(line)
        wid = rec.get("worker") or (wm.group(1) if wm else "")
        if wid:
            out.setdefault(str(wid), str(rec.get("id") or ""))
    return out


def stop_rows(event, session_id, now=None, problems=None, items=None, work=shell_work):
    """The `stuck-shell` check's rows for one stop: [(agent id, row)] sorted by agent id, from the event's running tasks and the session's subagent metas.

    Each row also carries `live` (the working descendant's command per `work({shell ids})`, or "") and `leased` (the id of the in-flight item in `items` leased to the shell, or ""); `blocking` keeps the rows with neither."""
    import wl_roster as R

    cwd = event.get("cwd") or ""
    metas = R.load_metas(R.session_subagents_dir(cwd, session_id))
    found = stuck_waiters(R._running(event), metas, C.project_start({"cwd": cwd}), now, problems)
    if found:
        try:
            busy = work({row["shell"] for row in found.values()}) or {}
        except Exception as exc:
            busy = {}
            if problems is not None:
                problems.append("shell descendants: %s: %s" % (type(exc).__name__, exc))
        leases = leased_shells(items)
        for row in found.values():
            row["live"] = busy.get(row["shell"], "")
            row["leased"] = leases.get(row["shell"], "")
    return sorted(found.items())


def is_owned(row):
    """True when the stuck row's shell does real work or an in-flight item is leased to it: reported, never a TaskStop order."""
    return bool(row.get("live") or row.get("leased"))


def blocking(rows):
    """The rows that still order a TaskStop: the shell only waits and no item is leased to it."""
    return [(aid, row) for aid, row in rows if not is_owned(row)]


def stop_check(rows, advise, block):
    """The `stuck-shell` check's two outputs for one stop's `rows` (`stop_rows`): `advise("stuck-shell-live", body)` once when any row is owned, and `block(rows)` with the rows that still order a TaskStop when any remain. Returns those blocking rows.

    wl_checks binds `advise` to its once-only advisory queue and `block` to its `vadd`, so the advisory path is driven by a test rather than only by the absence of the blocking text (review f4b82bed.3)."""
    live = render_live(rows)
    if live:
        advise("stuck-shell-live", live)
    stuck = blocking(rows)
    if stuck:
        block(stuck)
    return stuck


def render_live(rows):
    """The once-only advisory body for the owned rows in `rows` (`is_owned`), or "". Age-free on purpose, so an unchanged set renders the same text every stop."""
    keep = [(aid, row) for aid, row in rows if is_owned(row)]
    if not keep:
        return ""
    lines = ["%d STUCK SHELL-WAITER(S) WITH LIVE WORK (no TaskStop order):" % len(keep)]
    for aid, row in keep:
        what = []
        if row.get("live"):
            what.append("working: %s" % row["live"][:160])
        if row.get("leased"):
            what.append("item #%s is leased to it" % row["leased"])
        lines.append("    agent %s waiting on shell %s: %s" % (aid, row["shell"], "; ".join(what)))
    lines.append(
        "  Each shell does real work or holds a lease, so it is not stopped. Let it finish, "
        "read its output when the harness notifies, then land the agent's report."
    )
    return "\n".join(lines) + "\n"


def render(rows):
    """One block per stuck agent: what makes it stuck, then the two moves."""
    lines = []
    for aid, row in rows:
        if row["reason"] == "report":
            why = "its final report %s is captured" % row["report"]
            land = "land report %s" % row["report"]
        else:
            why = "shell %s has run %d minutes (bound %d)" % (
                row["shell"],
                int(row["age_min"] or 0),
                STUCK_SHELL_MIN,
            )
            land = "land its report"
        lines.append("    agent %s waiting on shell %s: %s" % (aid, row["shell"], why))
        lines.append(
            "      move: TaskStop %s, then %s; or SendMessage to %s to resume it"
            % (row["shell"], land, aid)
        )
    return "\n".join(lines)
