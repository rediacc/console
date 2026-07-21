#!/usr/bin/env python3
"""Stop hook: refuse to end a turn while the session worklist has open items.

WHY: the failure this prevents is stopping to REPORT a discovery instead of
acting on it.

WHY v2: v1's oracle was `- [ ]`, and I close items by editing that file. The
thing being gated wrote the gate's input, so I closed the last item by ticking
it "cannot be done" on a claim I never probed (docker was right there). A gate
whose subject controls its oracle is not a gate.

v2 does not try to detect a dishonest tick, which is not decidable. It makes the
escape a SEPARATE state the harness reports, so a deferral reaches the operator
through the tool layer instead of through a paragraph in my summary:

    - [ ] open        blocks the stop
    - [x] done        silent
    - [?] deferred    allowed, but printed back to the operator every time

A `- [?]` is a QUESTION, not a footnote. Raise it with AskUserQuestion.

STATE: one worklist per PROJECT, at $TMPDIR/claude-worklist/<repo-slug>.md.

    WORKLIST=$(.claude/hooks/stop/worklist.py --path)

Two rejected alternatives, both tried:
  - per USER (v1): every project shared one list. Plainly wrong.
  - per SESSION: isolates concurrent sessions, but the list dies with the
    session. Unfinished work vanishing the moment you restart is the exact
    failure this hook exists to prevent, so session isolation buys the wrong
    thing. Two sessions in one worktree are working on one repo; seeing each
    other's open items is a feature.

Keyed on the git root, so `--path` works from any subdirectory and needs no
argument.

SAFETY, because a Stop hook you cannot escape is worse than no hook:
  1. MAX_BLOCKS consecutive blocks, then it gives up and says so.
  2. Deleting or emptying the worklist allows stopping immediately.
  3. Removing the hook from .claude/settings.json disables it.
The counter resets whenever open items reach zero, so later work gets a fresh
budget.
"""

import json
import os
import pathlib
import re
import sys

MAX_BLOCKS = 25
# `- [ ] (5546d4bb) do the thing`  ->  state " ", owner "5546d4bb"
ITEM = re.compile(r"^\s*-\s*\[(?P<state>[ x?])\]\s*(?:\((?P<owner>[0-9a-fA-F][0-9a-fA-F-]*)\)\s*)?")


def owned_by_me(owner, session_id):
    """An UNTAGGED item is mine: that is the safe default, since the cost of
    wrongly claiming one is doing a little extra work, while the cost of wrongly
    disowning one is silently dropping it. A tag is a PREFIX of the session id
    (CLAUDE.md asks for a short prefix, not the whole uuid)."""
    if owner is None:
        return True
    return bool(session_id) and session_id.startswith(owner)


def project_root(start):
    """Nearest ancestor holding .git. This repo uses worktrees, where .git is a
    FILE, not a directory, so test existence rather than is_dir()."""
    p = pathlib.Path(start).resolve()
    for candidate in [p, *p.parents]:
        if (candidate / ".git").exists():
            return candidate
    return p


def worklist_for(start):
    d = pathlib.Path(os.environ.get("TMPDIR", "/tmp")) / "claude-worklist"
    d.mkdir(parents=True, exist_ok=True)
    root = project_root(start)
    slug = re.sub(r"[^A-Za-z0-9._-]", "_", str(root)).strip("_")
    return d / (slug + ".md")


def emit(obj):
    print(json.dumps(obj))
    sys.exit(0)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--path":
        print(worklist_for(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()))
        return

    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        event = {}
    worklist = worklist_for(
        os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd()
    )
    counter = worklist.with_suffix(".blocks")

    session_id = event.get("session_id", "")
    lines = worklist.read_text().splitlines() if worklist.exists() else []

    open_items, others, deferred = [], {}, []
    for line in lines:
        m = ITEM.match(line)
        if not m:
            continue
        state, owner = m.group("state"), m.group("owner")
        mine = owned_by_me(owner, session_id)
        if state == " ":
            if mine:
                open_items.append(line.strip())
            else:
                others.setdefault(owner, []).append(line.strip())
        elif state == "?" and mine:
            deferred.append(line.strip())

    def other_sessions_note():
        if not others:
            return ""
        return "\n".join(
            "  %d open item(s) owned by session %s" % (len(v), k) for k, v in sorted(others.items())
        )

    if not open_items:
        counter.unlink(missing_ok=True)
        parts = []
        if deferred:
            # The operator sees these even if my summary buries them.
            parts.append(
                "Worklist: %d item(s) deferred rather than done:\n%s"
                % (len(deferred), "\n".join("  " + d for d in deferred))
            )
        if others:
            # Reported, never blocked on. Blocking one session on another's
            # items deadlocks it: it cannot do them without racing live work in
            # the same tree, and it must not tick or delete someone else's
            # tracking. Surfacing beats blocking.
            parts.append("Worklist: nothing open for this session.\n" + other_sessions_note())
        if parts:
            emit({"systemMessage": "\n\n".join(parts)})
        return

    count = int(counter.read_text()) if counter.exists() else 0
    if count >= MAX_BLOCKS:
        counter.unlink(missing_ok=True)
        emit(
            {
                "systemMessage": "Stop hook: hit the %d-block cap with %d item(s) still open in %s. "
                "Letting the turn end so you are not stuck in a loop."
                % (MAX_BLOCKS, len(open_items), worklist)
            }
        )

    counter.write_text(str(count + 1))
    emit(
        {
            # `reason` is fed to the model; only `systemMessage` reaches the
            # operator. v1 set reason alone, so every block was INVISIBLE from
            # the outside: the operator saw a long turn and no explanation of
            # why it kept going. A supervisor nobody can see supervising is
            # indistinguishable from one that is not running.
            "systemMessage": "Stop hook: %d item(s) still open, continuing (block %d/%d). %s%s"
            % (
                len(open_items),
                count + 1,
                MAX_BLOCKS,
                open_items[0][:70],
                ("  [+%d owned by other sessions]" % sum(len(v) for v in others.values()))
                if others
                else "",
            ),
            "decision": "block",
            "reason": "Do not stop yet: %d open item(s) on the session worklist (%s).\n\n%s\n\n"
            "Pick the next open item and do it. Tick with '- [x]' as they land and append what you discover.\n"
            "If an item needs an OPERATOR DECISION, mark it '- [?]' and ask via AskUserQuestion. "
            "Do not tick '- [x]' on a claim you have not probed: run the command that proves it first.\n"
            "Block %d of %d."
            % (
                len(open_items),
                worklist,
                "\n".join("  " + i for i in open_items),
                count + 1,
                MAX_BLOCKS,
            )
        }
    )


main()
