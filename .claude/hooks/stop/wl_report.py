#!/usr/bin/env python3
"""wl_report: durable capture of sub-agent reports, and a pushed unread inbox.

THE DEFECT THIS CLOSES. A teammate's report arrives by SendMessage into the
lead's conversation and nowhere the lead can look afterwards. After a compaction
or a restart, a substantive report and an agent that went idle saying nothing are
INDISTINGUISHABLE -- there is no artifact to consult and no record that the agent
ever spoke. That is not a persistence problem in the abstract: it is capture at a
known moment, addressing that survives a restart, and unread-ness.

All three have an answer here:

  capture     `SubagentStop` hands over `last_assistant_message` verbatim, with
              `agent_id`, `agent_type` and `agent_transcript_path`, at the exact
              moment the agent finishes. PROBED LIVE, not inferred: it fires for
              plain `Task` sub-agents AND for `in_process_teammate` teammates,
              which was the single largest open question in the design.
  addressing  BRANCH, never session. `C.same_session` (wl_core.py:144) matches by
              PREFIX and a restarted session has a new id, so anything addressed
              session-to-session is unreachable after exactly the event this
              mechanism exists to survive.
  unread-ness a separate append-only `read.jsonl`, keyed PER READER. There is NO
              existing read marker anywhere in this system to copy (the
              `.requests` ack ledger is the ASKER's terminal close, not a
              recipient's read receipt), so the semantics are stated
              deliberately in `read_marks()` rather than inherited from a
              precedent that does not exist. Note the two keys are different on
              purpose: a REPORT is addressed by branch, a READ MARK is scoped by
              reader.

NO LOCK, ANYWHERE IN THIS MODULE, AND THAT IS LOAD-BEARING. One `os.write` of a
single line under 1024 bytes onto an `O_APPEND` handle is atomic on POSIX (below
PIPE_BUF) and serialised by the OS on Windows. Because it needs no lock it
imports no `fcntl`, so it does not inherit the Windows import death that kills
`wl_store.py` (line 46) and `worklist.py` (line 109) before they run a single
check. The 1024-byte cap enforced by `_fit` is what keeps that guarantee true, and
it is enforced by SHRINKING values, never by dropping fields -- a reader that
must tolerate missing keys cannot tell a capped line from a corrupt one.

Bodies never go in the index and never go in the worklist event log. Measured
over n=47 authored reports: min 3 938 B, median 17 575 B, max 115 720 B. The
MEDIAN is over 4x `AGENT_STATE_MAX_CHARS` (wl_store.py:82), so every existing
carrier is disqualified at the middle of the distribution, not at its tail; and
a 115 KB record inlined into the event log would be re-read IN FULL by `S.load`
on every future stop, making it a permanent tax rather than a one-time write.

Stdlib only, no sibling imports beyond `wl_core` (which is itself stdlib-only and
fcntl-free). Portable to linux, macOS and Windows on amd64 and arm64.
"""

import contextlib
import datetime
import json
import os
import pathlib
import re
import sys

import wl_core as C

# One index line must fit in a single atomic append. 4096 is PIPE_BUF on Linux;
# 1024 leaves headroom for every platform's weaker guarantee and is still ~5x a
# typical line.
INDEX_LINE_MAX = 1024
# Below this many characters, an agent's final message is an acknowledgement
# rather than a report. Calibrated against a measured capture: a real teammate's
# in-transcript final message runs 1.5-6 KB, so 200 separates "said nothing" from
# "said something terse" without mislabelling either.
SILENT_FLOOR = int(os.environ.get("WORKLIST_REPORT_SILENT_FLOOR", "200"))
TITLE_MAX = 120
# Surfacing is a context cost paid on every session start and every compaction.
SURFACE_MAX_LINES = int(os.environ.get("WORKLIST_REPORT_SURFACE_MAX", "25"))
# `--scan` only indexes an agent whose transcript has stopped growing, so a
# still-running agent is never captured mid-flight with a partial answer.
SCAN_IDLE_MIN = float(os.environ.get("WORKLIST_REPORT_SCAN_IDLE_MIN", "5"))
# `--scan` walks EVERY session's subagents dir under this project, and reads each
# candidate transcript whole (they run to 1.4 MB). Unbounded, the first run on a
# long-lived project would read gigabytes and resurrect months of finished agents
# as "unread". The window bounds both costs; anything older is history the index
# was never going to surface anyway.
SCAN_LOOKBACK_DAYS = float(os.environ.get("WORKLIST_REPORT_SCAN_LOOKBACK_DAYS", "7"))
# Transcripts here already reach 1.4 MB and nothing bounds them. Read at most
# this much (the tail, where the report is) so neither the stop hook nor a scan
# can be wedged by one pathological file.
TRANSCRIPT_MAX_BYTES = int(
    os.environ.get("WORKLIST_REPORT_TRANSCRIPT_MAX_BYTES", str(16 * 1024 * 1024))
)
# How much of the index the hook paths read. See read_index: the file is read on
# every stop and never pruned, so the read is bounded to its recent tail. 4 MB is
# roughly 20 000 reports, well past any window a session cares about.
INDEX_READ_MAX_BYTES = int(
    os.environ.get("WORKLIST_REPORT_INDEX_READ_MAX_BYTES", str(4 * 1024 * 1024))
)
# Bodies are pruned; index lines are kept forever. The index is the history and
# it is small (~200 B a line); the bodies are what actually costs disk.
RETENTION_DAYS = float(os.environ.get("WORKLIST_REPORT_RETENTION_DAYS", "30"))

# HEAD is detached often enough here (`private/renet` lives that way) that the
# empty branch needs a real directory name rather than an empty path segment.
NO_BRANCH = "_detached"

_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]")
_FS_RE = re.compile(r"[^A-Za-z0-9._-]+")


# ---- locations --------------------------------------------------------------


def store_root(start):
    """`$HOME/.claude/agent-reports/<repo-slug>/`, or `WORKLIST_REPORTS_DIR`.

    The slug is the one `C.worklist_for` (wl_core.py:161) already derives from
    the repo root, so two worktrees of one repo stay separate WITHOUT inventing a
    second naming scheme that could disagree with the first.

    Not `/tmp`: reboot deletes it.

    Not the repo's `agent/<session>/` tree either, and the migration of
    2026-08-14 STRENGTHENED that rather than weakening it. There used to be two
    objections to two different trees: a tracked `docs/agent/<branch>/` would put
    roughly 142 machine-written files per session into every PR diff, and a
    gitignored `.agent/<branch>/` would die with the worktree while a report is
    most wanted after the branch is gone. Those trees are now ONE tree, and it is
    tracked -- so the diff-noise objection applies to all of it, with nothing
    left to trade against. Reports stay outside the repo.
    """
    env = os.environ.get("WORKLIST_REPORTS_DIR")
    if env:
        return pathlib.Path(env)
    slug = _SLUG_RE.sub("_", str(C.project_root(start))).strip("_")
    return pathlib.Path.home() / ".claude" / "agent-reports" / slug


def index_path(store):
    return store / "index.jsonl"


def read_path(store):
    return store / "read.jsonl"


def short_id(agent_id):
    """The LAST 12 characters of the agent id, never the first.

    Both id shapes end in a random hex run (`a<17hex>` for a Task sub-agent,
    `a<name>-<16hex>` for a teammate), and only the tail is unique: two teammates
    named `design-statesplit` and `design-statefoo` share their first 12
    characters exactly, so a leading truncation would collide on precisely the
    long-lived named agents this mechanism is for.
    """
    a = str(agent_id or "")
    return a[-12:] if len(a) > 12 else a


def _fs_safe(text, fallback):
    s = _FS_RE.sub("-", str(text or "")).strip("-")
    return s[:60] or fallback


# ---- the index --------------------------------------------------------------


def _append_line(path, obj):
    """ONE `os.write` of ONE line on an O_APPEND handle. No lock (see module
    docstring). O_BINARY where it exists, so Windows does not rewrite the `\\n`
    into `\\r\\n` and push a line that was measured at 1024 bytes over the cap."""
    line = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    data = (line + "\n").encode("utf-8")
    if len(data) > INDEX_LINE_MAX:
        raise ValueError("index line %d bytes exceeds %d" % (len(data), INDEX_LINE_MAX))
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0)
    fd = os.open(str(path), flags, 0o644)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def _fit(obj):
    """Shrink VALUES until the line fits; never drop a KEY.

    A reader forced to tolerate absent keys cannot distinguish a deliberately
    capped line from a torn one, which would make the torn-tail rule below
    unenforceable. So `title` shrinks first (it is a convenience), then the
    transcript path (recoverable from `agent_transcript_path` conventions), and
    only a pathological id/agent pair could still overflow -- which raises, and
    the caller drops the whole capture rather than writing a malformed index.
    """
    for shrink in (TITLE_MAX, 80, 40, 20, 0):
        obj["title"] = obj["title"][:shrink]
        if (
            len(json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
            < INDEX_LINE_MAX
        ):
            return obj
    for shrink in (200, 80, 0):
        obj["transcript"] = obj["transcript"][-shrink:] if shrink else ""
        if (
            len(json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
            < INDEX_LINE_MAX
        ):
            return obj
    # LAST RESORT: the remaining fields are not "pathological id/agent" only --
    # `branch` is attacker-shaped in the ordinary sense that a git branch name
    # can be arbitrarily long, and `body` embeds it. So shrink those too rather
    # than returning a line that is still over the cap. Returning an oversized
    # object here is what let a single long-branch entry raise inside scan()'s
    # loop and abort the whole self-healing pass; the entry was never marked
    # known, so every later scan aborted at the same place, permanently and
    # silently. Found in review, not by a test.
    for field, keep in (("agent", 64), ("type", 64), ("body", 200), ("branch", 120)):
        val = obj.get(field)
        if isinstance(val, str) and len(val) > keep:
            obj[field] = val[:keep]
            if (
                len(json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
                < INDEX_LINE_MAX
            ):
                return obj
    return obj


def is_phantom(agent_type, transcript):
    """Is this SubagentStop something other than a finished sub-agent?

    THE LOOP THIS CLOSES, and it inverted the feature. `SubagentStop` also fires
    for the session's own main-loop turns, which the design never modelled. Each
    such turn was captured as a "report"; the waiter saw a new report and fired;
    the session spent a turn reading and re-arming; THAT turn was captured; the
    waiter fired again. Two consecutive firings served the lead its own session
    summary three minutes apart. It does not converge, and every cycle costs the
    exact turn the waiter exists to save.

    REJECTS ONLY WHEN BOTH SIGNALS FAIL, which is the safe direction and is the
    opposite of over-strict. A real agent whose transcript has not flushed yet
    still has a type; a hypothetical typeless agent kind still has a transcript.
    Only the phantom class fails both.

    Measured over the live store before choosing: 181 records partition exactly
    181 = 44 (no type, no transcript) + 137 (type, transcript). Not one mixed
    case. And across 1885 real `*.meta.json` sidecars, ZERO lack `agentType`, so
    type-emptiness does not exclude any real agent kind that exists today.
    """
    return not str(agent_type or "").strip() and not _resolves(transcript)


def read_index(store, max_bytes=INDEX_READ_MAX_BYTES):
    """Parseable index lines, oldest first. An UNPARSEABLE line is skipped, never
    fatal -- same rule every `.requests` reader follows, and the reason a crash
    mid-append cannot wedge the inbox.

    BOUNDED BY DEFAULT, because since v18 this file is read on EVERY stop and it
    grows forever by design (a line is the durable record that an agent ran and
    whether it said anything, so nothing prunes it; only bodies are pruned). At
    roughly 200 bytes a line and ~140 agents a session, an unbounded read would
    be a few megabytes per stop within months. The index is append-ordered, so
    the tail is the recent end -- exactly what every hook path wants. `--list
    --all` passes None to see the whole history.
    """
    p = index_path(store)
    out = []
    try:
        lines = (
            _bounded_lines(p, max_bytes)
            if max_bytes
            else p.read_text(encoding="utf-8", errors="replace").splitlines()
        )
    except OSError:
        return out
    retired = set()
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict) or not ev.get("id"):
            continue
        if ev.get("ev") == "retire":
            # APPENDED, never edited. Retirement keeps the log append-only, which
            # is what makes the lock-free single-write design sound; rewriting
            # lines to remove them would give that up for a tidier file.
            retired.add(str(ev["id"]))
        elif ev.get("ev") == "report":
            out.append(ev)
    return [e for e in out if str(e["id"]) not in retired]


def reader_id(explicit=None):
    """This reader's identity: an explicit prefix, else the session id.

    THE ENV LOOKUP MOVED to wl_core.resolve_session_id, which carries this
    function's hard-won note verbatim: the variable is CLAUDE_CODE_SESSION_ID
    and CLAUDE_SESSION_ID does not exist, checked against a live environment
    rather than assumed, because a wrong name resolves to the empty reader
    forever -- which reads as "has read nothing" and would surface every report
    on every stop while looking like it worked.

    It moved because this was the ONLY place in the CLI that ever asked the
    environment who it was, and the answer was never generalised past this one
    verb. Two definitions of "who am I" is how the drift starts; there is now
    one, and every `<me>` argument is checked against it."""
    if explicit:
        return str(explicit)
    return C.resolve_session_id()


def read_marks(store, reader):
    """Report ids marked read BY THIS READER. Empty when the reader is unknown.

    A READ MARK IS PER-READER, KEYED ON SESSION ID (operator decision, overriding
    this design's own earlier recommendation of a branch-level mark). `by` is a
    SCOPING KEY here, not provenance.

    WHY, because the rejected option is the tempting one. Branch-level means ONE
    ledger shared by every session in the worktree, so if session A reads a
    report, session B never learns it existed. Two concurrent sessions per
    worktree is this repo's normal state, so that is not a corner case -- and it
    is a quieter restatement of the exact failure this whole file exists to fix:
    a report that was written and that nobody sees.

    THE ACCEPTED COST, stated so nobody later mistakes it for a bug and
    "fixes" it: `C.same_session` matches by PREFIX (wl_core.py:20-26), so a
    restarted session is a different reader and re-sees every report on the
    branch. That resurfacing IS the compaction-recovery case working. A fresh
    session inheriting the branch's reports is the entire point of the feature.
    Do NOT add machinery to suppress it; if the list is long the correct lever is
    PRESENTATION (surface_block already collapses to a bounded count), never
    suppression. Surfacing less than exists is the thing being fixed.

    An UNKNOWN reader returns no marks, so everything reads as unread. That is
    the safe direction under the same rule: too much is recoverable, too little
    is the defect.
    """
    if not reader:
        return set()
    p = read_path(store)
    marks = set()
    try:
        # Bounded like read_index, and with the SAME byte budget on a strictly
        # smaller file -- so the marks always cover at least as much history as
        # the index does. The other way round, an old-but-still-indexed report
        # whose mark had scrolled out would resurrect as unread.
        lines = _bounded_lines(p, INDEX_READ_MAX_BYTES)
    except OSError:
        return marks
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict) or ev.get("ev") != "read" or not ev.get("id"):
            continue
        if C.same_session(str(ev.get("by") or ""), reader):
            marks.add(str(ev["id"]))
    return marks


def unread(store, branch=None, reader=None):
    """Reports this READER has not marked read, oldest first, on `branch`.

    Branch filtering is on the REPORT, not on the read mark: a report captured
    while the tree was on branch X is about work on X, and surfacing it to a
    session that has since moved to Y is noise, not memory."""
    marks = read_marks(store, reader)
    out = []
    for ev in read_index(store):
        if str(ev["id"]) in marks:
            continue
        if branch is not None and str(ev.get("branch", "")) != branch:
            continue
        out.append(ev)
    return out


def resolve(store, ident):
    """An index entry by exact id, else by unique prefix. An AMBIGUOUS prefix
    returns nothing rather than an arbitrary winner: showing the wrong report is
    worse than saying the id was not specific enough."""
    entries = read_index(store)
    exact = [e for e in entries if str(e["id"]) == ident]
    if exact:
        return exact[-1]
    pref = [e for e in entries if str(e["id"]).startswith(ident)]
    return pref[-1] if len(pref) == 1 else None


# ---- capture ----------------------------------------------------------------


def capture(
    store,
    branch,
    *,
    agent_id,
    agent_type,
    agent_name,
    session,
    body,
    transcript,
    source="hook",
    at=None,
    title=None,
    sends=0,
    tx="ok",
):
    """Write the body whole, then append one index line. Returns the entry, or
    None when the id is already indexed (so the hook and `--scan` can both run
    over the same agent without producing a duplicate)."""
    rid = short_id(agent_id)
    if not rid:
        return None
    if is_phantom(agent_type, transcript):
        return None  # a main-loop turn, not a sub-agent report; see is_phantom
    for ev in read_index(store):
        if str(ev["id"]) == rid:
            return None
    body = body or ""
    stamp = at or C.stamp_now()
    name = agent_name or agent_type or "agent"
    fname = "%s-%s-%s.md" % (
        _FS_RE.sub("", stamp) or "unknown",
        _fs_safe(name, "agent"),
        rid,
    )
    rel = "%s/%s" % (branch, fname)
    target = store / branch / fname
    front = (
        "---\n"
        "agent_id: %s\nagent_type: %s\nagent_name: %s\nsession: %s\nbranch: %s\n"
        "at: %s\nsource: %s\nsends: %d\ntranscript: %s%s\nbytes: %d\n"
        "---\n\n"
        % (
            agent_id,
            agent_type or "",
            name,
            session or "",
            branch,
            stamp,
            source,
            sends,
            transcript or "(none)",
            "" if tx == "ok" else "   <- DID NOT EXIST AT CAPTURE TIME",
            len(body.encode("utf-8")),
        )
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(front + body, encoding="utf-8")

    if title is None:
        title = ""
        for line in body.splitlines():
            if line.strip():
                title = line.strip()[:TITLE_MAX]
                break
    entry = _fit(
        {
            "ev": "report",
            "id": rid,
            "at": stamp,
            "branch": branch,
            "agent": str(name)[:48],
            "type": str(agent_type or "")[:48],
            "session": str(session or "")[:8],
            "body": rel,
            "bytes": len(body.encode("utf-8")),
            # THE WHOLE POINT OF (A) IS THIS FIELD. "Reported substantively" and
            # "went idle saying nothing" stop being indistinguishable the moment one
            # of them is recorded, at the moment it happens, from the harness's own
            # account of what the agent said.
            # A SendMessage payload is a report even when it is short, so any send at
            # all rules out `silent`. Without this an agent that delivered 8 KB by
            # SendMessage and signed off with "Done." would be indexed as having said
            # nothing -- inverting the exact distinction this field exists to draw.
            "silent": sends == 0 and len(body.strip()) < SILENT_FLOOR,
            "sends": sends,
            # WHETHER THE TRANSCRIPT PATH ACTUALLY RESOLVED, checked at capture. A
            # stored path that silently does not exist is worse than a null: every
            # reader treats it as readable and quietly gets nothing, which is the
            # vacuous-check class -- a lookup that cannot succeed and never says so.
            # Found live: a stop fired with a well-formed path to a file that was
            # never written, and the SendMessage harvest read nothing from it
            # without anybody being able to tell that from an agent that simply
            # sent nothing.
            "tx": tx,
            "title": title,
            "transcript": str(transcript or ""),
            "src": source,
        }
    )
    _append_line(index_path(store), entry)
    return entry


# ---- hook modes -------------------------------------------------------------


def _stdin_event():
    try:
        raw = sys.stdin.read()
    except (OSError, ValueError):
        return {}
    try:
        ev = json.loads(raw)
    except ValueError:
        return {}
    return ev if isinstance(ev, dict) else {}


def _branch_of(start):
    return C.git_branch(C.project_root(start)) or NO_BRANCH


def handle_subagent_stop(event):
    """A CAPTURE HOOK MUST NEVER WEDGE A SUB-AGENT'S STOP. Every failure path
    here exits 0 with no output: an unwritable store, a full disk or a malformed
    payload costs a lost report, while raising would cost the agent its exit."""
    agent_id = event.get("agent_id")
    if not agent_id:
        return  # main thread, not a subagent
    start = C.project_start(event)
    store = store_root(start)
    transcript = event.get("agent_transcript_path") or ""
    final = event.get("last_assistant_message") or ""
    # The event's own `last_assistant_message` is authoritative for the sign-off
    # (it needs no file to exist and cannot race the transcript's last flush);
    # the transcript is read ONLY for the SendMessage payloads, which the event
    # does not carry and which are usually the actual report.
    # RESOLVE THE PATH BEFORE TRUSTING IT. Proven necessary by a live capture:
    # `SubagentStop` fired for an agent id whose transcript was never written at
    # all -- no `.jsonl`, no `.meta.json`, and no record of it anywhere in the
    # parent session either. Not a race (still absent 30 minutes later) and not
    # an id-to-filename mismatch (the name matched the convention exactly); the
    # agent simply produced no turn, so nothing was ever flushed. The harvest
    # then read an absent file and reported `sends: 0`, which is indistinguishable
    # from an agent that genuinely sent nothing.
    sends = []
    tx = "ok" if transcript and _resolves(transcript) else "absent"
    if tx == "ok":
        sends, t_final, _rec = harvest_transcript(pathlib.Path(transcript))
        final = final or t_final
    body = assemble_body(sends, final)
    capture(
        store,
        _branch_of(start),
        agent_id=agent_id,
        agent_type=event.get("agent_type"),
        agent_name=event.get("agent_type"),
        session=str(event.get("session_id") or "")[:8],
        body=body,
        transcript=transcript,
        source="hook",
        title=_title_of(sends, final),
        sends=len(sends),
        tx=tx,
    )


def surface_block(store, branch, hook_path, reader):
    """The unread index, COLLAPSED. Bodies are never inlined: at a median of
    17.5 KB and a max of 115 KB, even a handful would be a context bomb on every
    single compaction, which is the moment context is scarcest.

    The collapse matters more under per-reader marks than it would have under
    branch-level ones: a restarted session legitimately re-sees every report on
    its branch, so this is the lever that keeps that honest rather than
    overwhelming. It bounds the LINES, never the SET -- the count always names
    the full total."""
    items = unread(store, branch, reader)
    if not items:
        return ""
    shown = items[-SURFACE_MAX_LINES:]
    lines = [
        "UNREAD SUB-AGENT REPORTS (%d) on branch %s -- captured at SubagentStop, "
        "durable across restart and compaction." % (len(items), branch)
    ]
    if len(items) > len(shown):
        lines.append(
            "  (%d older not shown; %s --list --unread for all)"
            % (len(items) - len(shown), hook_path)
        )
    for e in shown:
        age = C.stamp_age_min(e.get("at"))
        age_s = "%dm" % age if age is not None else "?"
        flag = "SILENT " if e.get("silent") else ""
        title = e.get("title") or (
            "(no body: this agent stopped without reporting)" if e.get("silent") else "(untitled)"
        )
        lines.append(
            "  %s%-12s %5s  %-22s %s" % (flag, e["id"], age_s, str(e.get("agent"))[:22], title)
        )
    lines.append("  read one:  %s --show <id>" % hook_path)
    # The prefix is BAKED IN rather than left as a placeholder: read marks are
    # per-reader now, so a command copied without it would record a mark under
    # the empty reader and clear nothing.
    lines.append("  mark read: %s --read %s <id> [<id>...]" % (hook_path, (reader or "<me>")[:8]))
    return "\n".join(lines)


def handle_surface(event, hook_event, hook_path):
    """SessionStart and PostCompact both emit; SessionStart declines the
    `compact` source. Claude Code fires SessionStart *and* PostCompact on every
    compaction, and emitting from both was a real, shipped defect in the sibling
    handler (`wl_checks.py:1232-1241`) -- the duplicate is not hypothetical."""
    if hook_event == "SessionStart" and str(event.get("source") or "") == "compact":
        return
    start = C.project_start(event)
    store = store_root(start)
    block = surface_block(store, _branch_of(start), hook_path, reader_id(event.get("session_id")))
    if not block:
        return
    print(
        json.dumps(
            {
                "systemMessage": block.splitlines()[0],
                "hookSpecificOutput": {"hookEventName": hook_event, "additionalContext": block},
            }
        )
    )


# ---- scan (self-healing capture) --------------------------------------------


def _projects_dir():
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    return (pathlib.Path(base) if base else pathlib.Path.home() / ".claude") / "projects"


def _munged(root):
    """Claude Code's own project-directory naming: every non-alphanumeric run in
    the absolute path becomes a `-`. Verified against this repo's live directory
    (`/home/muhammed/monorepo/console` -> `-home-muhammed-monorepo-console`)."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(root))


def _resolves(path):
    """Does this path name an existing file? False for ANY failure to find out.

    NOT `Path.is_file()`. That only swallows a WHITELIST of errnos (ENOENT,
    ENOTDIR, EBADF, ELOOP) and lets everything else propagate -- so a 3 KB path
    raises ENAMETOOLONG, which crashed the whole capture and LOST the report,
    strictly worse than the unresolved-path bug this check exists to catch.
    Caught by the suite's own long-path case, which is why that case exists.
    """
    try:
        return pathlib.Path(path).is_file()
    except (OSError, ValueError):
        return False


def _bounded_lines(path, max_bytes=TRANSCRIPT_MAX_BYTES):
    """Every line of a JSONL file, or the last `max_bytes` worth of them.

    A transcript here already reaches 1.4 MB and nothing bounds its growth, so an
    unconditional read_text() puts an unbounded file in memory inside a hook that
    must never wedge a sub-agent's stop. On overflow the first (necessarily
    partial) line is dropped, which the callers already tolerate: both of them
    skip unparseable lines by rule."""
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
                f.readline()  # discard the partial line the seek landed inside
            raw = f.read()
    except OSError:
        return []
    return raw.decode("utf-8", errors="replace").splitlines()


def harvest_transcript(jsonl):
    """(sends, final_text, last_record) from an agent's transcript.

    WHY THIS READS SendMessage AND NOT JUST THE FINAL MESSAGE -- this is the
    whole defect, one layer deeper than it first appears. A teammate delivers its
    report by CALLING SendMessage and then signs off in prose. The harness's
    `last_assistant_message` therefore hands over the SIGN-OFF, not the report.
    Measured on a real teammate (`rm-deployments`): `last_assistant_message` was
    "Released. Task complete." -- 24 characters -- while the two SendMessage
    payloads it had just sent ran 8 646 and 6 331 characters. Capturing only the
    final message would have indexed that agent as having said essentially
    nothing, and would have marked several genuinely substantive agents `silent`.

    That is not a corner case: "the report arrives by SendMessage and nowhere the
    lead can look afterwards" is the literal statement of the problem this file
    exists to solve, so the SendMessage payload is the PRIMARY artifact and the
    final message is the postscript.
    """
    sends, final, rec = [], "", {}
    for line in _bounded_lines(jsonl):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if not isinstance(r, dict) or r.get("type") != "assistant":
            continue
        rec = r
        content = (r.get("message") or {}).get("content")
        if isinstance(content, str):
            if content.strip():
                final = content
            continue
        if not isinstance(content, list):
            continue
        texts = []
        for c in content:
            if not isinstance(c, dict):
                continue
            if c.get("type") == "text" and str(c.get("text") or "").strip():
                texts.append(str(c["text"]))
            elif c.get("type") == "tool_use" and c.get("name") == "SendMessage":
                inp = c.get("input") or {}
                msg = inp.get("message")
                if not isinstance(msg, str):
                    msg = json.dumps(msg, ensure_ascii=False)
                if str(msg).strip():
                    sends.append(
                        {
                            "to": str(inp.get("to") or "?"),
                            "at": str(r.get("timestamp") or ""),
                            "summary": str(inp.get("summary") or ""),
                            "message": str(msg),
                        }
                    )
        if texts:
            final = "\n".join(texts)
    return sends, final, rec


def assemble_body(sends, final):
    """The durable artifact: every SendMessage payload in order, then the
    sign-off. Whole and uncapped -- that is the point of storing bodies in their
    own files rather than in any of the existing capped carriers."""
    parts = []
    for i, s in enumerate(sends, 1):
        head = "## SendMessage %d -> %s" % (i, s["to"])
        if s.get("at"):
            head += "  (%s)" % s["at"]
        if s.get("summary"):
            head += "\n_%s_" % s["summary"]
        parts.append("%s\n\n%s" % (head, s["message"]))
    if str(final or "").strip():
        parts.append("## Final message\n\n%s" % final)
    return "\n\n".join(parts)


def _title_of(sends, final):
    """The LAST SendMessage's opening line, else the final message's.

    Deliberately the last send and not the first: an agent that reports progress
    and then reports its conclusion should be indexed by the conclusion. Falling
    back to the final message keeps a plain `Task` sub-agent (which returns its
    report AS its final message and may never call SendMessage) titled properly.
    """
    for source in ([sends[-1]["message"]] if sends else []) + [final or ""]:
        for line in str(source).splitlines():
            if line.strip():
                return line.strip()[:TITLE_MAX]
    return ""


def scan(store, start, idle_min=None):
    """Index every finished agent the hook did not capture, and prune old bodies.

    THIS IS WHAT MAKES THE INDEX CORRECT RATHER THAN MERELY LIKELY. The hook is
    the fast path; this is the one that survives a crash, an interrupt, a
    settings.json that lost its wiring, and any task kind whose stop event turns
    out not to fire. It reads the same `subagents/` directory the hook's own
    `agent_transcript_path` points into, so the two agree on naming by
    construction rather than by convention.

    The meta sidecar's shape DIFFERS BY TASK KIND and every field but `agentType`
    is optional here. Measured over one live session: 74 sidecars, 44 teammates
    carrying `name`/`taskKind`/`teamName`, and 30 plain `Task` sub-agents
    carrying NONE of them. Keying on `name` or `taskKind` would therefore skip
    40% of the population in silence -- which is the "capture everything"
    requirement failing invisibly, the exact failure mode this file exists for.
    """
    idle_min = SCAN_IDLE_MIN if idle_min is None else idle_min
    root = C.project_root(start)
    proj = _projects_dir() / _munged(root)
    known = {str(e["id"]) for e in read_index(store)}
    now = C.utcnow()
    added = []
    if proj.is_dir():
        for meta in sorted(proj.glob("*/subagents/*.meta.json")):
            jsonl = meta.with_name(meta.name[: -len(".meta.json")] + ".jsonl")
            if not jsonl.exists():
                continue
            agent_id = jsonl.stem.removeprefix("agent-")
            if short_id(agent_id) in known:
                continue
            try:
                idle = (now.timestamp() - jsonl.stat().st_mtime) / 60.0
            except OSError:
                continue
            if idle < idle_min:
                continue  # still running: capturing now would record a half-answer
            if SCAN_LOOKBACK_DAYS > 0 and idle > SCAN_LOOKBACK_DAYS * 1440:
                continue  # older than the window; see SCAN_LOOKBACK_DAYS
            try:
                info = json.loads(meta.read_text(encoding="utf-8", errors="replace"))
            except (OSError, ValueError):
                info = {}
            if not isinstance(info, dict):
                info = {}
            # ONE BAD AGENT MUST NOT ABORT THE WHOLE PASS. Without this guard a
            # single entry that raises -- an oversized index line, an unreadable
            # transcript, a surprise in the meta shape -- kills the loop before
            # it reaches anything sorted after it. And because a failed entry is
            # never recorded as `known`, the NEXT scan hits the same wall at the
            # same place: the self-heal starves permanently, silently, and worst
            # of all invisibly, since wl_wait's periodic scan wraps this in a
            # blanket except of its own. Isolating per agent means a bad entry
            # costs exactly itself.
            try:
                sends, final, rec = harvest_transcript(jsonl)
                entry = capture(
                    store,
                    str(rec.get("gitBranch") or "") or _branch_of(start) or NO_BRANCH,
                    agent_id=agent_id,
                    agent_type=info.get("agentType") or rec.get("attributionAgent"),
                    agent_name=info.get("name") or info.get("agentType"),
                    session=str(rec.get("sessionId") or meta.parent.parent.name or "")[:8],
                    body=assemble_body(sends, final),
                    transcript=str(jsonl),
                    source="scan",
                    at=_iso_of(rec.get("timestamp")) or C.stamp_now(),
                    title=_title_of(sends, final),
                    sends=len(sends),
                    tx="ok",  # scan globbed this file, so it resolves by construction
                )
            except Exception:  # noqa: BLE001, S112 -- deliberate, see the comment above:
                # one bad agent must not abort the whole pass, and a narrower
                # tuple would let an unforeseen shape kill every entry sorted
                # after it.
                continue
            if entry:
                known.add(entry["id"])
                added.append(entry)
    return added, prune(store)


def _iso_of(stamp):
    """`2026-08-05T12:48:41.505Z` -> `2026-08-05T12:48:41Z`, the one format
    `C.parse_stamp` accepts. A transcript timestamp carries milliseconds and
    would otherwise parse as None and render every scanned report's age as `?`."""
    s = str(stamp or "")
    m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", s)
    return m.group(1) + "Z" if m else ""


def prune(store):
    """Delete BODIES past the retention window; keep index lines forever.

    The asymmetry is deliberate: a line is ~200 bytes and IS the history (it is
    what proves an agent ran and whether it said anything), while the bodies are
    the only part that costs real disk. A pruned body's index line still answers
    the question (A) is about."""
    if RETENTION_DAYS <= 0:
        return []
    cutoff = C.utcnow() - datetime.timedelta(days=RETENTION_DAYS)
    removed = []
    for e in read_index(store):
        when = C.parse_stamp(e.get("at"))
        if when is None or when >= cutoff:
            continue
        body = store / str(e.get("body") or "")
        try:
            if body.is_file():
                body.unlink()
                removed.append(str(e["id"]))
        except OSError:
            continue
    return removed


# ---- CLI --------------------------------------------------------------------

# The verbs main() dispatches on. Exported so worklist.py's `--reports` door can
# tell a MODE from a MODIFIER without duplicating the list.
MODES = (
    "--subagent-stop",
    "--session-start",
    "--post-compact",
    "--list",
    "--show",
    "--read",
    "--scan",
    "--retire-phantoms",
)


def _hook_path():
    return "python3 %s" % pathlib.Path(__file__).resolve()


def main(argv):
    if not argv:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print(
            "usage: wl_report.py --subagent-stop | --session-start | --post-compact"
            " | --list [--unread|--all] [--as <me>] | --show <id>"
            " | --read <me> <id>... | --scan | --retire-phantoms [--dry-run]",
            file=sys.stderr,
        )
        return 2
    mode = argv[0]

    if mode == "--subagent-stop":
        # Swallowed on purpose -- see handle_subagent_stop's docstring.
        with contextlib.suppress(Exception):
            handle_subagent_stop(_stdin_event())
        return 0
    if mode in ("--session-start", "--post-compact"):
        hook_event = "SessionStart" if mode == "--session-start" else "PostCompact"
        # Surfacing must never block a start, so every failure is swallowed.
        with contextlib.suppress(Exception):
            handle_surface(_stdin_event(), hook_event, _hook_path())
        return 0

    start = C.project_start()
    store = store_root(start)
    branch = _branch_of(start)

    if mode == "--list":
        rest = set(argv[1:])
        # --all reads the WHOLE index, unbounded: it is the history door, and a
        # tail-bounded history is not a history.
        entries = (
            read_index(store, None)
            if "--all" in rest
            else [e for e in read_index(store) if str(e.get("branch", "")) == branch]
        )
        explicit = argv[argv.index("--as") + 1] if "--as" in argv[1:-1] else None
        if explicit:
            # Only the EXPLICIT one is checked. The env default is correct by
            # construction -- it IS the resolved identity -- so checking it
            # would compare a value to itself.
            ok, why = C.check_me(explicit)
            if not ok:
                print(why, file=sys.stderr)
                return 2
        who = reader_id(explicit)
        marks = read_marks(store, who)
        if "--unread" in rest:
            entries = [e for e in entries if str(e["id"]) not in marks]
        if not entries:
            print("no reports indexed (%s)" % index_path(store))
            return 0
        for e in entries:
            age = C.stamp_age_min(e.get("at"))
            print(
                "%-12s %s (%s) %-18s %-10s %s%s%s"
                % (
                    e["id"],
                    e.get("at", "?"),
                    "?" if age is None else "%dm" % age,
                    str(e.get("agent"))[:18],
                    e.get("branch", "?"),
                    "[read] " if str(e["id"]) in marks else "",
                    "[SILENT] " if e.get("silent") else "",
                    e.get("title") or "",
                )
            )
        return 0

    if mode == "--show":
        if len(argv) < 2:
            print("usage: --show <id>", file=sys.stderr)
            return 2
        e = resolve(store, argv[1])
        if e is None:
            print("no report %r here (list them with --list --all)" % argv[1], file=sys.stderr)
            return 2
        body = store / str(e.get("body") or "")
        try:
            sys.stdout.write(body.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            print(
                "report %s is indexed but its body is gone (pruned after %d days); "
                "transcript: %s" % (e["id"], int(RETENTION_DAYS), e.get("transcript") or "unknown"),
                file=sys.stderr,
            )
            return 2
        return 0

    if mode == "--read":
        # `<me>` FIRST and REQUIRED, matching every other worklist verb
        # (--tick/--defer/--lease all take the owner first). Read marks are
        # per-reader, so a mark with no reader clears nothing for anybody; making
        # it positional means that cannot happen by omission.
        me = argv[1] if len(argv) > 1 else ""
        if not C.PREFIX_RE.match(me or ""):
            print("usage: --read <your-session-id-prefix> <id> [<id>...]", file=sys.stderr)
            return 2
        ok, why = C.check_me(me)
        if not ok:
            # A read mark under the wrong identity clears nothing for the reader
            # who filed it and hides the report from nobody -- the same
            # write-here-read-there split, in the report inbox.
            print(why, file=sys.stderr)
            return 2
        ids = argv[2:]
        if not ids:
            print("usage: --read <your-session-id-prefix> <id> [<id>...]", file=sys.stderr)
            return 2
        marked = 0
        for ident in ids:
            e = resolve(store, ident)
            if e is None:
                print("no report %r here; not marking it read" % ident, file=sys.stderr)
                continue
            _append_line(
                read_path(store),
                {
                    "ev": "read",
                    "id": e["id"],
                    "by": me[:32],  # a SCOPING key since the per-reader decision
                    "at": C.stamp_now(),
                    "branch": branch,
                },
            )
            marked += 1
        if not marked:
            return 2
        print("marked %d report(s) read" % marked)
        return 0

    if mode == "--retire-phantoms":
        # One-off (and re-runnable) cleanup for records captured before the
        # phantom filter existed. Appends a `retire` event per offender; the
        # report lines themselves are never touched.
        dry = "--dry-run" in argv[1:]
        entries = read_index(store, None)
        doomed = [e for e in entries if is_phantom(e.get("type"), e.get("transcript"))]
        if not doomed:
            print("nothing to retire (%d live record(s))" % len(entries))
            return 0
        for e in doomed:
            print(
                "%s %-10s %s%s"
                % (
                    e["id"],
                    e.get("agent") or "?",
                    "[would retire] " if dry else "[retired] ",
                    (e.get("title") or "")[:70],
                )
            )
            if not dry:
                _append_line(
                    index_path(store),
                    {
                        "ev": "retire",
                        "id": e["id"],
                        "at": C.stamp_now(),
                        "why": "phantom: main-loop turn, not a sub-agent report",
                    },
                )
                body = store / str(e.get("body") or "")
                try:
                    if body.is_file():
                        body.unlink()
                except OSError:
                    pass
        print(
            "%s %d of %d record(s); %d real report(s) untouched"
            % (
                "would retire" if dry else "retired",
                len(doomed),
                len(entries),
                len(entries) - len(doomed),
            )
        )
        return 0

    if mode == "--scan":
        added, pruned = scan(store, start)
        for e in added:
            print(
                "indexed %s %s %s%s"
                % (
                    e["id"],
                    e.get("agent"),
                    "[SILENT] " if e.get("silent") else "",
                    e.get("title") or "",
                )
            )
        if pruned:
            print("pruned %d body file(s) past %d days" % (len(pruned), int(RETENTION_DAYS)))
        if not added and not pruned:
            print("nothing to index (%s)" % index_path(store))
        return 0

    print("unknown mode %s" % mode, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
