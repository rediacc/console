"""wl_uncommitted: the commit reminder's engine (agent/plans/PLAN-fast-loop.md, Part 2).

WHAT IT ANSWERS. "Does this session hold edited files that are still uncommitted, and has the branch gone `commit_remind_min` minutes without a commit?" The answer feeds two advisories that share this one engine and one piece of state: the Stop hook's `commit-remind` line and the PostToolUse member `.claude/hooks/post-tool/commit_remind.py`. Neither blocks (operator ruling 2026-10-06: a reminder, never a wall).

WHY THE TRANSCRIPT. The worktree is shared, so `git status` alone cannot say whose a dirty file is: a peer session's edit looks the same. The session's own transcript names every file its own Edit, Write, MultiEdit and NotebookEdit calls touched, so the dirty set is intersected with that list and a peer's path never counts.

THE CURSOR. The transcript only grows. `state_doc["uc_cursor"]` is the byte offset already read, so each call reads the new tail and nothing more. A cursor past the end (a rewritten file) restarts at zero; a first read of a transcript larger than `CATCHUP_MAX_BYTES` begins at the last `CATCHUP_MAX_BYTES` bytes, so the catch-up is bounded. Only complete lines are consumed: a half-written last line stays unread until it is whole.

THE STATE, all in the session's state doc: `uc_cursor` (int), `uc_files` ({repo-relative path: first_seen_epoch}, the write-once first sight of each path), and `uc_git` ({"at", "ct", "dirty"}: the throttled `git status` read).

THE THROTTLE. `git status --porcelain` runs at most once per `STATUS_FLOOR_S` (ten minutes), except that a changed last-commit time proves a commit just happened and re-reads at once, so a commit never leaves a stale reminder behind. `git log -1 --format=%ct HEAD` is cheap and runs on every evaluation.

READ-ONLY, BY CONSTRUCTION. This module runs `git status` and `git log` and nothing else: no add, commit, stash, restore, checkout, clean or reset. `test_wl_commit_remind.py` scans the source for any other git verb.

Every function here swallows nothing silently on its own; callers wrap the whole evaluation in the same try/except every Stop detector uses, and the PostToolUse member exits 0 whatever happens.
"""

import datetime
import json
import os
import pathlib
import subprocess
import time

EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
PATH_KEYS = ("file_path", "notebook_path")
#: The first read of a transcript larger than this starts at its tail.
CATCHUP_MAX_BYTES = 8 * 1024 * 1024
#: `git status` runs at most this often per session (a commit re-reads at once).
STATUS_FLOOR_S = 600
#: Files named in the reminder before the remainder is counted.
LIST_CAP = 8
GIT_TIMEOUT_S = 20


def _git(root, *args):
    """stdout of one read-only git command in `root`, or "" on any failure."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout if proc.returncode == 0 else ""


def _epoch(stamp, default):
    """An ISO-8601 transcript timestamp as epoch seconds, or `default` when it does not parse."""
    try:
        text = str(stamp).replace("Z", "+00:00")
        parsed = datetime.datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.UTC)
        return parsed.timestamp()
    except (TypeError, ValueError):
        return default


def _rel(root, path):
    """`path` as a repo-relative POSIX string, or "" when it lies outside `root`."""
    try:
        resolved = pathlib.Path(path)
        if not resolved.is_absolute():
            resolved = pathlib.Path(root) / resolved
        return resolved.resolve().relative_to(pathlib.Path(root).resolve()).as_posix()
    except (OSError, ValueError, RuntimeError):
        return ""


def edited_paths(line):
    """[(path, timestamp)] for each Edit/Write/MultiEdit/NotebookEdit tool_use block in one transcript JSONL line."""
    try:
        row = json.loads(line)
    except ValueError:
        return []
    message = row.get("message") if isinstance(row, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    found = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        if block.get("name") not in EDIT_TOOLS:
            continue
        tool_input = block.get("input")
        if not isinstance(tool_input, dict):
            continue
        for key in PATH_KEYS:
            value = tool_input.get(key)
            if isinstance(value, str) and value:
                found.append((value, row.get("timestamp")))
    return found


def scan_transcript(root, transcript_path, state_doc, now=None):
    """Advance `uc_cursor` over the new tail of the transcript and union the edited paths into `uc_files`. Returns True when the state doc changed."""
    if not transcript_path:
        return False
    now = time.time() if now is None else now
    try:
        size = os.path.getsize(transcript_path)
    except OSError:
        return False
    cursor = state_doc.get("uc_cursor")
    first = not (isinstance(cursor, int) and 0 <= cursor <= size)
    start = max(0, size - CATCHUP_MAX_BYTES) if first else cursor
    if start >= size:
        state_doc["uc_cursor"] = start
        return first
    try:
        with open(transcript_path, "rb") as handle:
            handle.seek(start)
            data = handle.read(size - start)
    except OSError:
        return False
    if first and start > 0:
        # A bounded catch-up lands mid-line: the partial first line is skipped.
        cut = data.find(b"\n") + 1
        data, start = (data[cut:], start + cut) if cut else (b"", size)
    end = data.rfind(b"\n") + 1
    complete = data[:end]
    files = state_doc.get("uc_files")
    files = files if isinstance(files, dict) else {}
    changed = False
    for raw in complete.splitlines():
        for path, stamp in edited_paths(raw.decode("utf-8", "replace")):
            rel = _rel(root, path)
            if rel and rel not in files:
                files[rel] = _epoch(stamp, now)
                changed = True
    new_cursor = start + end
    if state_doc.get("uc_cursor") != new_cursor:
        changed = True
    state_doc["uc_cursor"] = new_cursor
    state_doc["uc_files"] = files
    return changed


def parse_porcelain(text):
    """Paths named by `git status --porcelain -z` output (renames list the new path first)."""
    paths = []
    parts = text.split("\0")
    i = 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if entry[0] in "RC":
            i += 1  # the original path follows a rename or copy entry
    return paths


def _dirty_match(own, dirty):
    """The members of `own` that `dirty` names: the same path, or inside an untracked directory entry (`dir/`)."""
    dirs = tuple(d for d in dirty if d.endswith("/"))
    names = set(dirty)
    return sorted(p for p in own if p in names or p.startswith(dirs))


def own_dirty(root, state_doc, now=None):
    """(own still-dirty paths, last commit epoch or None), refreshing the throttled status read when it is due.

    Paths that read clean on a fresh status are dropped from `uc_files`, so a file edited again after its commit gets a new first-seen time.
    """
    now = time.time() if now is None else now
    out = _git(root, "log", "-1", "--format=%ct", "HEAD").strip()
    ct = int(out) if out.isdigit() else None
    cached = state_doc.get("uc_git")
    cached = cached if isinstance(cached, dict) else {}
    due = (
        cached.get("ct") != ct
        or not isinstance(cached.get("at"), (int, float))
        or now - cached["at"] >= STATUS_FLOOR_S
        or cached["at"] > now
    )
    if due:
        status = _git(root, "status", "--porcelain", "-z", "--untracked-files=normal")
        dirty = parse_porcelain(status)
        files = state_doc.get("uc_files") or {}
        for gone in [p for p in files if p not in _dirty_match(files, dirty)]:
            del files[gone]
        state_doc["uc_files"] = files
        cached = {"at": now, "ct": ct, "dirty": dirty}
        state_doc["uc_git"] = cached
    return _dirty_match(state_doc.get("uc_files") or {}, cached.get("dirty") or []), ct


def remind_min(root):
    """`commit_remind_min` of the root's QUEUE.md `## Settings` (default 15)."""
    import wl_planqueue  # noqa: PLC0415 -- only a reminder evaluation needs the settings

    return int(wl_planqueue.settings_for(root)[0].commit_remind_min)


def evaluate(root, transcript_path, state_doc, now=None, minutes=None):
    """The reminder facts, or None when nothing is owed.

    {"files": [paths, oldest first], "count": n, "oldest_min": n, "last_commit_min": n, "threshold": n}. Owed when the session has own dirty files AND the last commit is at least `minutes` old. Mutates `state_doc` (cursor, files, git read); the caller persists it.
    """
    now = time.time() if now is None else now
    scan_transcript(root, transcript_path, state_doc, now)
    own, ct = own_dirty(root, state_doc, now)
    if not own or ct is None:
        return None
    threshold = remind_min(root) if minutes is None else minutes
    last_min = int((now - ct) // 60)
    if last_min < threshold:
        return None
    seen = state_doc.get("uc_files") or {}
    ordered = sorted(own, key=lambda p: (seen.get(p, now), p))
    oldest = max(0, int((now - min(seen.get(p, now) for p in ordered)) // 60))
    return {
        "files": ordered,
        "count": len(ordered),
        "oldest_min": oldest,
        "last_commit_min": last_min,
        "threshold": threshold,
    }


def render(facts):
    """The reminder text for `evaluate`'s facts (the template is `worklist_messages.N_COMMIT_REMIND`)."""
    import worklist_messages as M  # noqa: PLC0415 -- the catalogue is the one home of wording

    shown = facts["files"][:LIST_CAP]
    rest = facts["count"] - len(shown)
    listing = "\n".join("  - %s" % p for p in shown)
    if rest > 0:
        listing += "\n  ... and %d more" % rest
    return M.N_COMMIT_REMIND % (
        facts["count"],
        facts["oldest_min"],
        facts["last_commit_min"],
        facts["threshold"],
        listing,
    )
