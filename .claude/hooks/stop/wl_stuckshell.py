"""wl_stuckshell: an agent that waits on a shell yet is finished or past a bound is STUCK, not live (agent/plans/PLAN-writers-now-cadence.md, box WN4).

THE SHAPE (2026-11-23). Writer a7f511c739e4aa739 (stripe-disable) launched its own `npm run ci -- --narrow` as background shell `bgjvtrdck`, ended its turn with a final TICK block, and the harness showed it as "waiting on 1 shell" for hours. `wl_roster.shell_waiters` counted any agent with an armed, running shell as a live writer with no bound short of WAIT_HORIZON_MIN, so its lease stayed covered and no dead-writer or silence check fired.

STUCK means the agent waits on a shell (the `wl_roster.armed_waiters` shape: not listed running, its transcript armed a shell the event still lists) AND either

  (a) its final report is captured: a `wl_report` index row for the agent, captured at or after the shell's launch, that names a box through a TICK line (`boxes`) or is a closing summary (not silent, not a relay, no interim shell, and at least `wl_report.RELAY_FLOOR` bytes, the calibrated gap between turn-end status lines and real reports); or
  (b) the shell has run longer than STUCK_SHELL_MIN minutes, measured from the timestamp of the transcript record that launched it.

A stuck agent is not live: `wl_roster.shell_waiters` drops it, so the roster, `wl_liveness.live_worker_ids` and the writer estimate stop counting it, and the `stuck-shell` check names the agent, the shell and the two moves.

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
    """True when a report index row is a final report: it names a box through a TICK line, or it is a closing summary (see the module docstring)."""
    import wl_report as RPT

    if entry.get("boxes"):
        return True
    return (
        not entry.get("silent")
        and not entry.get("relay")
        and not entry.get("interim")
        and not entry.get("armed")
        and int(entry.get("bytes") or 0) >= RPT.RELAY_FLOOR
    )


def final_report(entries, aid, since):
    """The newest final report row captured for `aid` at or after epoch `since`, or None."""
    import wl_report as RPT
    import wl_roster as R

    rid = RPT.short_id(aid)
    found = None
    for e in entries or []:
        ident = str(e.get("id") or "")
        if ident != rid and not ident.startswith(rid + "-"):
            continue
        at = R._epoch(e.get("at"))
        if at is None or at < since:
            continue
        if is_final(e):
            found = e
    return found


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


def stop_rows(event, session_id, now=None, problems=None):
    """The `stuck-shell` check's rows for one stop: [(agent id, row)] sorted by agent id, from the event's running tasks and the session's subagent metas."""
    import wl_roster as R

    cwd = event.get("cwd") or ""
    metas = R.load_metas(R.session_subagents_dir(cwd, session_id))
    found = stuck_waiters(R._running(event), metas, C.project_start({"cwd": cwd}), now, problems)
    return sorted(found.items())


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
