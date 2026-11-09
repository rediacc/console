#!/usr/bin/env python3
"""The away flag behind `/awk`: while the operator is away from the keyboard, no question is put to them.

WHY (operator 2026-11-08T19:27Z): "make a new custom command called /awk (away from keyboard). So, it should avoid asking questions until the operator writes a messages." and "For some questions, of course [?] is still usable." The command is reusable, night after night. An AskUserQuestion put to an absent operator blocks the turn until morning, so the pre-ask guard `block_away_questions` refuses it while the flag stands, and the session parks a genuine decision as a `[?]` with its DEFAULT instead.

ONE FLAG PER CHECKOUT, NOT PER SESSION. A long night crosses compactions, and a compaction can hand the conversation a new session id; a flag keyed on the id would drop silently at the first one. The operator is away from the keyboard, not from one session, so every session in this tree honours it. It lives in `.claude/hooks/context/state/`, which is gitignored.

IT CLEARS ITSELF ON THE OPERATOR'S NEXT MESSAGE. `operator_since` walks the asking session's transcript for a record after the flag's `since` that is the operator: a typed turn or an interrupt (`wl_admit._is_operator_turn`, which leaves out tool results, hook feedback, task notifications and the compaction summary), or a message typed while a turn runs, which the harness records as an `attachment` of type `queued_command`. The `/awk` invocation itself is written after the flag and is skipped. The first such record clears the flag, and the guard lets the question through.

CLI: `wl_away.py set [note...]`, `wl_away.py clear`, `wl_away.py status [--transcript <path>]`.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import sys

DEFAULT_STATE = pathlib.Path(__file__).resolve().parents[1] / "context" / "state" / "away.json"


def state_path() -> pathlib.Path:
    """The flag file. `WL_AWAY_STATE` moves it (a file, or a directory holding `away.json`), so a test never touches the live flag."""
    path = pathlib.Path(os.environ.get("WL_AWAY_STATE") or DEFAULT_STATE)
    return path / "away.json" if path.is_dir() else path


# A night of work writes far more than the 3 MB other readers keep, and a sibling session may write a lot after the operator answered it; records before the flag's `since` are skipped. Every transcript, the asking one and each sibling, is read with the same 64 MB tail: the read runs only when a question is asked, which away mode makes rare.
TAIL_BYTES = 64 * 1024 * 1024
AWK_COMMAND = "<command-name>/awk</command-name>"


def _now() -> str:
    """Millisecond precision, the transcript's own form: a record stamped in the flag's millisecond compares equal and is skipped, never later."""
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def read(state: pathlib.Path | None = None) -> dict | None:
    """The flag, or None when the operator is not marked away. A file that does not parse is no flag: failing open lets a question through, which is this feature's safe side."""
    state = state or state_path()
    try:
        doc = json.loads(state.read_text())
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) and isinstance(doc.get("since"), str) else None


def set_away(note: str = "", state: pathlib.Path | None = None) -> dict:
    state = state or state_path()
    doc = {"since": _now(), "note": note}
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps(doc) + "\n")
    return doc


def clear(state: pathlib.Path | None = None) -> bool:
    state = state or state_path()
    try:
        state.unlink()
    except FileNotFoundError:
        return False
    return True


def _is_awk(text: str) -> bool:
    stripped = text.lstrip()
    return AWK_COMMAND in text or stripped == "/awk" or stripped.startswith("/awk ")


def _text(rec: dict) -> str:
    message = rec.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            str(b.get("text") or "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def operator_message(rec: dict) -> str | None:
    """The operator's text when `rec` is the operator speaking (a turn, an interrupt, or a message queued mid-turn), else None."""
    import wl_admit

    if rec.get("type") == "attachment":
        att = rec.get("attachment")
        if not isinstance(att, dict) or att.get("type") != "queued_command":
            return None
        prompt = str(att.get("prompt") or "")
        if (
            not prompt.strip()
            or prompt.lstrip().startswith(wl_admit.HARNESS_PREFIXES)
            or _is_awk(prompt)
        ):
            return None
        return prompt
    if not isinstance(rec.get("message", {}), dict) or not wl_admit._is_operator_turn(rec):
        return None
    text = _text(rec)
    return None if _is_awk(text) else (text or "(operator turn)")


def operator_since(transcript_path: str, since: str, tail: int = TAIL_BYTES) -> str | None:
    """The first operator message in the transcript stamped after `since`, or None. ISO-8601 UTC stamps compare as strings."""
    if not transcript_path:
        return None
    try:
        with open(transcript_path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - tail))
            chunk = fh.read()
    except OSError:
        return None
    for raw in chunk.split(b"\n"):
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        # Both sides cut to the millisecond (`YYYY-MM-DDTHH:MM:SS.mmm`): a flag written with microseconds and a record from its millisecond compare equal and the record is skipped.
        if not isinstance(rec, dict) or str(rec.get("timestamp") or "")[:23] <= since[:23]:
            continue
        text = operator_message(rec)
        if text is not None:
            return text
    return None


def _since_epoch(since: str) -> float:
    try:
        return (
            datetime.datetime.strptime(since, "%Y-%m-%dT%H:%M:%S.%fZ")
            .replace(tzinfo=datetime.UTC)
            .timestamp()
        )
    except ValueError:
        return 0.0


def _transcripts(transcript_path: str, since: str) -> list[str]:
    """The asking session's transcript first, then every other transcript of this project written after the flag. The operator may answer a different session than the one that asks, and the flag is per checkout, so a word to any of them ends it."""
    if not transcript_path:
        return []
    paths = [transcript_path]
    here = pathlib.Path(transcript_path)
    floor = _since_epoch(since)
    try:
        siblings = sorted(here.parent.glob("*.jsonl"))
    except OSError:
        return paths
    for sib in siblings:
        try:
            if sib != here and sib.stat().st_mtime >= floor:
                paths.append(str(sib))
        except OSError:
            continue
    return paths


def away(transcript_path: str, state: pathlib.Path | None = None) -> dict | None:
    """The live flag when the operator is still away, else None. A flag the operator has spoken after, in this session or any sibling session of this project, is cleared here."""
    state = state or state_path()
    doc = read(state)
    if doc is None:
        return None
    for path in _transcripts(transcript_path, doc["since"]):
        if operator_since(path, doc["since"], TAIL_BYTES) is not None:
            clear(state)
            return None
    return doc


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("set", "clear", "status"):
        print(
            "usage: wl_away.py set [note...] | clear | status [--transcript <path>]",
            file=sys.stderr,
        )
        return 2
    if argv[0] == "set":
        doc = set_away(" ".join(argv[1:]))
        print(
            "AWAY since %s: AskUserQuestion is refused until the operator's next message; "
            "park decisions as [?] with a DEFAULT." % doc["since"]
        )
        return 0
    if argv[0] == "clear":
        print("cleared" if clear() else "not away")
        return 0
    transcript = argv[argv.index("--transcript") + 1] if "--transcript" in argv[:-1] else ""
    shown: dict | None = away(transcript) if transcript else read()
    print("AWAY since %s" % shown["since"] if shown else "not away")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    sys.exit(main(sys.argv[1:]))
