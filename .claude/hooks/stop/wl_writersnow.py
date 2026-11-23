"""wl_writersnow: the /writers-now round record (agent/plans/PLAN-writers-now-cadence.md WN1, operator ruling #ac2de21f).

THE ROUND RECORD (WN1). `worklist.py --writers-now-start <me> <survey>` appends one JSON line to `agent/ledgers/writers-now-rounds.jsonl` at the start of every round: the round id, the session, the UTC start and the survey path. Nothing else writes the ledger, and nothing rewrites a line.
"""

from __future__ import annotations

import json
import os
import pathlib
import secrets

import wl_core as C

LEDGER_REL = "agent/ledgers/writers-now-rounds.jsonl"


# ---- the round ledger -------------------------------------------------------------


def ledger_path(root) -> pathlib.Path:
    return pathlib.Path(root) / LEDGER_REL


def read_rounds(root) -> list[dict]:
    """Every parseable round row, oldest first. An absent ledger is no round yet ([]); an unparseable line is skipped, as every event-log reader here does; any other read failure raises."""
    path = ledger_path(root)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    rows = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and row.get("session") and C.parse_stamp(row.get("at")):
            rows.append(row)
    return rows


def last_round(rows, session) -> dict | None:
    """The newest row of `session` (prefix-matched either way, wl_core.same_session), or None."""
    mine = [r for r in rows if C.same_session(str(r.get("session")), str(session))]
    return max(mine, key=lambda r: C.parse_stamp(r["at"])) if mine else None


def new_round_id() -> str:
    return secrets.token_hex(4)


def append_round(root, session, survey, now, round_id=None, **extra) -> dict:
    """Append one round row and return it. One `os.write` of one line onto an O_APPEND handle, so two sessions starting rounds at once each keep their own line."""
    row = {
        "round": round_id or new_round_id(),
        "session": str(session),
        "at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "survey": str(survey),
        **extra,
    }
    path = ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, (json.dumps(row, separators=(",", ":")) + "\n").encode("utf-8"))
    finally:
        os.close(fd)
    return row
