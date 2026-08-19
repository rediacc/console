#!/usr/bin/env python3
"""PreCompact: the deterministic floor under the band trigger.

A PreCompact hook CANNOT make the model do anything. There is no model turn
between this hook and the compaction, the event does not accept
`additionalContext`, and it does not support `prompt` or `agent` hook types.
Verified against Claude Code 2.1.235, not inferred. So this hook does the two
things it actually can:

1. WRITES A FACTS SNAPSHOT, so something survives even when the band notice
   never fired or the session never acted on it.

   NOT into STATE.md, and that is a deliberate departure from the brief. The
   only supported writer is `worklist.py --state`, which REPLACES this
   session's section wholesale. A facts-only stub written at compaction time
   would therefore overwrite a good, model-authored document with a list of
   git facts -- destroying the exact artifact this hook exists to protect, at
   the exact moment it is needed. A floor that can demolish the building is
   not a floor. The snapshot goes in a sidecar and the stdout below names its
   path, so both documents reach the other side.

2. PRINTS SUMMARISER INSTRUCTIONS ON STDOUT. Undocumented but verified in the
   bundle: `executePreCompactHooks` collects the stdout of every successful
   hook into `newCustomInstructions` and merges it with any `/compact <text>`
   the user typed, and that string is what the summarising model is told to
   honour. It is the one channel a PreCompact hook has into what survives.

IT NEVER EXITS 2. Blocking a proactive compaction leaves the conversation
running uncompacted toward the hard limit; blocking a recovery compaction
surfaces the API's context-length error and fails the request. Neither is an
acceptable outcome for a bookkeeping hook, so every path here returns 0.

IT PRINTS NOTHING WHEN IT HAS NOTHING TO SAY. Non-empty output makes the
manual-compact precompute cache report `miss_hook` and recompute the summary
from scratch, so silence is the correct default rather than a missed
opportunity. Note that Claude Code folds STDERR into the same string, so this
hook must never write to stderr either; failures go to state/errors.log.
"""

import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ctx_budget as B  # noqa: E402

ITEM_RE = re.compile(r"^\s*- \[[ >?]\] #([0-9a-fA-F]{6,16})\b")

# How many worklist ids the summariser instruction may carry inline.
MAX_IDS = 25


def run(cmd, cwd, timeout=15):
    try:
        p = subprocess.run(
            cmd,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return p.stdout
    except Exception as exc:  # noqa: BLE001 -- a missing git or a slow store must not break compaction
        B.log_error("precompact-floor/run:%s" % cmd[0], exc)
        return ""


def open_items(project, slug):
    out = run(
        [
            sys.executable,
            str(Path(project) / ".claude" / "hooks" / "stop" / "worklist.py"),
            "--list",
            "--open",
            slug,
        ],
        project,
        timeout=30,
    )
    ids = []
    for line in out.splitlines():
        m = ITEM_RE.match(line)
        if m:
            ids.append(m.group(1))
    return ids, out


def facts(project, event, slug):
    git = lambda *a: run(["git"] + list(a), project).strip()  # noqa: E731
    branch = git("rev-parse", "--abbrev-ref", "HEAD") or "(detached or unknown)"
    head = git("log", "-1", "--format=%h %s")
    dirty = [l for l in git("status", "--porcelain").splitlines() if l.strip()]
    ids, listing = open_items(project, slug)
    state_md = B.state_md_path(project, event.get("session_id") or "")
    if state_md.is_file():
        stat = state_md.stat()
        state_line = "%s (%d bytes, mtime %s)" % (
            state_md.as_posix(),
            stat.st_size,
            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stat.st_mtime)),
        )
    else:
        state_line = "%s (ABSENT)" % state_md.as_posix()

    body = [
        "# PreCompact facts snapshot",
        "",
        "Written by .claude/hooks/context/precompact-floor.py at %s"
        % time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "",
        "- session: %s (slug %s)" % (event.get("session_id"), slug),
        "- compaction trigger: %s" % event.get("trigger"),
        "- cwd: %s" % project,
        "- branch: %s" % branch,
        "- HEAD: %s" % head,
        "- uncommitted paths: %d" % len(dirty),
        "- compact-recovery document: %s" % state_line,
        "- open worklist ids: %s" % (", ".join(ids) if ids else "(none)"),
        "",
        "## Uncommitted paths (first 40)",
        "",
    ]
    body += ["    " + l for l in dirty[:40]] or ["    (clean)"]
    body += ["", "## Open worklist items", "", listing.rstrip() or "(none)"]
    return "\n".join(body) + "\n", ids, state_md


def main():
    event = B.read_event()
    try:
        session_id = event.get("session_id") or ""
        slug = B.session_slug(session_id)
        project = B.project_dir(event)

        text, ids, state_md = facts(project, event, slug)
        snapshot = B.state_dir() / ("%s-precompact-facts.md" % slug)
        tmp = snapshot.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        import os

        os.replace(tmp, snapshot)

        # Silence unless there is something worth carrying across the summary.
        have_doc = state_md.is_file()
        if not have_doc and not ids:
            return

        parts = []
        if have_doc:
            parts.append(
                "The compact-recovery document for this session is %s; it is the "
                "authoritative record of in-flight work and survives this "
                "compaction on disk." % state_md.as_posix()
            )
        if ids:
            # Bounded on purpose. Hook output is capped at 10,000 characters,
            # and a live run produced 41 ids for a single session; an
            # instruction that is mostly a list stops reading as an
            # instruction. The full set is in the snapshot either way.
            shown = ids[:MAX_IDS]
            tail = (
                "" if len(ids) <= MAX_IDS else " (+%d more in the snapshot below)" % (len(ids) - MAX_IDS)
            )
            parts.append(
                "Open worklist ids that must appear in the summary verbatim: %s%s."
                % (", ".join(shown), tail)
            )
        parts.append(
            "A machine-written facts snapshot (branch, HEAD, uncommitted paths, "
            "open items) is at %s." % snapshot.as_posix()
        )
        parts.append(
            "Preserve these paths and ids exactly as written; they are how the "
            "session resumes."
        )
        sys.stdout.write(" ".join(parts) + "\n")
    except Exception as exc:  # noqa: BLE001 -- never break a compaction
        B.log_error("precompact-floor", exc)


if __name__ == "__main__":
    main()
    # Explicit, and the whole point: exit 2 blocks compaction, and this hook
    # must never do that.
    sys.exit(0)
