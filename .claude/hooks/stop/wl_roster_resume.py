"""wl_roster_resume: name the lead's sub-agents an API error killed, until the lead resumes them.

THE DEFECT (operator 2026-11-24): a background agent cut by a connection or API error is marked failed, the parent gets one task-notification, and nothing afterwards says the agent still holds unfinished work. A hook cannot resume it; only the parent's `SendMessage(to=<agent id>)` can. So the Stop hook names each such agent with the exact resume line, at every stop, until the parent's transcript shows that SendMessage.

MEASURED, NOT ASSUMED (2026-11-24, session d778be9d): agent a7795c6bbb38b95da died on `API Error: No response from API` at 2026-11-19T15:45:54Z. Its two siblings in the same wave each left a `src: hook` row in the report index (SubagentStop fired); it left none, by full or short id. So SubagentStop does not reliably fire on an API-error death, and this Stop-side reader is the load-bearing half; wl_report's SubagentStop resume is the bonus for the case where the event does fire.

TWO SOURCES, either is enough:
  1. the agent's own transcript: its last `assistant` record is an API error (`isApiErrorMessage: true`, or text wl_report.API_ERROR_RE matches);
  2. the parent's transcript: a `<task-notification>` for the agent with `<status>failed</status>` whose summary names an API error.
RESUMED once the parent's transcript holds a SendMessage tool call `to` that agent at or after the death, or the agent's transcript holds a non-error assistant record after it. Stateless on purpose: the transcripts are the authority, and a second death after a resume is a new death that fires again.

Only the lead's own agents (no `parentAgentId`): a nested agent is its parent agent's to resume. Bounded reads (a tail of each recent transcript), stdlib only.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import time

# Deaths older than this are history, not work in hand.
RESUME_LOOKBACK_H = float(os.environ.get("WORKLIST_RESUME_LOOKBACK_H", "24"))
# The API-error record is the LAST record of a dead agent's transcript, so a small tail sees it.
AGENT_TAIL_BYTES = int(os.environ.get("WORKLIST_RESUME_AGENT_TAIL", str(64 * 1024)))
PARENT_TAIL_BYTES = int(os.environ.get("WORKLIST_RESUME_PARENT_TAIL", str(8 * 1024 * 1024)))
RESUME_MESSAGE = (
    "Your run was cut by an API error; check your tree state, commit verified work, finish, "
    "and send the report."
)
_TASK_RE = re.compile(
    r"<task-notification>.*?<task-id>([^<]+)</task-id>.*?<status>([^<]+)</status>"
    r".*?<summary>(.*?)</summary>",
    re.DOTALL,
)
_NOTE_API_RE = re.compile(r"terminated early due to an API error|API Error", re.IGNORECASE)


def _tail_lines(path, tail_bytes):
    """The whole lines in the last `tail_bytes` of `path`, a partial first line dropped; [] when it cannot be read.

    Read through `wl_core.tail_bytes`, the Stop run's one memoized transcript reader: opening the file here made a stop read the parent transcript a second time (test_wl_stop_speed_reads.py).
    """
    import wl_core

    got = wl_core.tail_bytes(path, tail_bytes)
    if got is None:
        return []
    _size, start, blob = got
    if start > 0:
        cut = blob.find(b"\n")
        blob = b"" if cut < 0 else blob[cut + 1 :]
    return blob.decode("utf-8", errors="replace").splitlines()


def _epoch(stamp):
    """Epoch seconds of a transcript stamp (fractional seconds and `Z` included), or None."""
    import wl_roster

    return wl_roster._epoch(stamp)


def _text_of(rec):
    content = (rec.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    return "\n".join(
        str(c.get("text") or "")
        for c in content or []
        if isinstance(c, dict) and c.get("type") == "text"
    )


def _is_api_error(rec):
    import wl_report

    return rec.get("isApiErrorMessage") is True or wl_report.looks_api_error(_text_of(rec))


def agent_death(jsonl):
    """`(epoch, text)` when the agent's last assistant record is an API error, else None. A later non-error assistant record (a resume that already answered) clears it."""
    last = None
    for raw in _tail_lines(pathlib.Path(jsonl), AGENT_TAIL_BYTES) if jsonl else []:
        if '"assistant"' not in raw:
            continue
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("type") == "assistant":
            last = rec
    if last is None or not _is_api_error(last):
        return None
    return _epoch(last.get("timestamp")), _text_of(last)[:200]


def parent_facts(transcript):
    """`(failed, sends)` from the parent transcript's tail: `failed` is {agent id: (epoch, summary)} of API-error task-notifications, `sends` {agent id: [epoch]} of SendMessage calls."""
    failed: dict[str, tuple] = {}
    sends: dict[str, list] = {}
    for raw in _tail_lines(pathlib.Path(transcript), PARENT_TAIL_BYTES) if transcript else []:
        has_send = '"SendMessage"' in raw
        has_note = "task-notification" in raw
        if not (has_send or has_note):
            continue
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        when = _epoch(rec.get("timestamp"))
        if has_send and rec.get("type") == "assistant":
            for c in (rec.get("message") or {}).get("content") or []:
                if (
                    isinstance(c, dict)
                    and c.get("type") == "tool_use"
                    and c.get("name") == "SendMessage"
                ):
                    to = str((c.get("input") or {}).get("to") or "")
                    if to and when is not None:
                        sends.setdefault(to, []).append(when)
        if has_note and rec.get("type") in ("user", "queue-operation"):
            # A `user` record carries the notification as its content (a string, or text parts); a `queue-operation` record as its own `content`.
            body = _text_of(rec) if rec.get("type") == "user" else str(rec.get("content") or "")
            for m in _TASK_RE.finditer(body):
                aid, status, summary = m.group(1).strip(), m.group(2).strip(), m.group(3)
                if status == "failed" and _NOTE_API_RE.search(summary) and when is not None:
                    failed[aid] = (when, summary.strip()[:200])
                elif status != "failed":
                    failed.pop(aid, None)
    return failed, sends


def dead_agents(metas, parent_transcript, running_ids=(), now=None, lookback_h=None):
    """`[{"id", "at", "why", "desc"}]`, oldest death first: the lead's own agents an API error killed inside the lookback that nothing has resumed since."""
    now = time.time() if now is None else now
    horizon = now - 3600 * (RESUME_LOOKBACK_H if lookback_h is None else lookback_h)
    failed, sends = parent_facts(parent_transcript)
    found: dict[str, dict] = {}
    for aid, m in (metas or {}).items():
        if m.get("parent"):
            continue
        jsonl = m.get("jsonl")
        try:
            if jsonl is None or pathlib.Path(jsonl).stat().st_mtime < horizon:
                continue
        except OSError:
            continue
        death = agent_death(jsonl)
        if death and death[0] is not None:
            found[aid] = {"id": aid, "at": death[0], "why": death[1], "desc": m.get("desc") or ""}
    for aid, (when, summary) in failed.items():
        m = (metas or {}).get(aid) or {}
        if m.get("parent") or aid in found:
            continue
        jsonl = m.get("jsonl")
        if jsonl is not None and pathlib.Path(jsonl).exists() and agent_death(jsonl) is None:
            # The transcript answers for itself: its last assistant record is no API error, so a resume already ran.
            continue
        found[aid] = {"id": aid, "at": when, "why": summary, "desc": m.get("desc") or ""}
    out = []
    running = {str(r) for r in running_ids or ()}
    for aid, row in found.items():
        if row["at"] < horizon or aid in running:
            continue
        if any(t >= row["at"] - 1 for t in sends.get(aid, ())):
            continue
        out.append(row)
    return sorted(out, key=lambda r: r["at"])


def render(rows):
    """The RESUME block body: one SendMessage line per dead agent."""
    lines = []
    for r in rows:
        stamp = time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(r["at"]))
        lines.append(
            "    %s %s died %s: %s"
            % (r["id"], ("(%s)" % r["desc"][:40]) if r["desc"] else "", stamp, r["why"][:120])
        )
        lines.append("      RESUME: SendMessage to=%s '%s'" % (r["id"], RESUME_MESSAGE))
    return "\n".join(lines)


def stop_rows(event, session_id, now=None):
    """`dead_agents` for one Stop event: the session's subagent metas, its transcript, its running tasks."""
    import wl_roster

    cwd = event.get("cwd") or ""
    metas = wl_roster.load_metas(wl_roster.session_subagents_dir(cwd, session_id))
    running = [str(b.get("id") or "") for b in wl_roster._running(event)]
    return dead_agents(metas, event.get("transcript_path") or "", running, now=now)
