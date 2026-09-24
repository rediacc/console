#!/usr/bin/env python3
"""PostToolUse: after an edit to a Stop-hook module, say at once whether it still loads.

WHY THIS EXISTS (agent/plans/PLAN-stop-hook-continuity.md, box P2.6). The Stop hook runs straight from the working tree, so a writer's half-finished edit to `.claude/hooks/stop/*.py` is every session's Stop hook. A NameError inside `run_stop` is a RUNTIME failure: nothing notices it until the next stop, where it blocks with a traceback, and in a shared tree that stop
may belong to a different session than the one that made the edit. The writer is the one party that can fix it cheaply, and the writer is in the middle of its own turn right now.

WHAT IT CHECKS, on an Edit, Write or MultiEdit whose file is a `.py` directly inside a `.claude/hooks/stop/` directory:

  1. `ruff check --isolated --select F821,F811` on that file. F821 is the undefined name that
     is the whole motivating defect; F811 is a redefinition that shadows a live function. A
     syntax error is always reported by ruff, whatever is selected.
  2. An import smoke test of that stop directory in a subprocess: `worklist` is imported and
     its `_BROKEN` map must be empty, and the edited module is imported by name when it is
     one. `worklist.py` catches a sibling's import failure into `_BROKEN` rather than
     raising, so importing it alone would call a broken sibling healthy.

The directory checked is the EDITED FILE'S OWN, not this checkout's, so an edit in another worktree or in a copy is judged against its own siblings.

IT WARNS AND NEVER BLOCKS. Every path exits 0. A finding is returned as `hookSpecificOutput.additionalContext`, which reaches the writer in the same turn; a clean file produces no output at all, because a notice attached to every clean edit is noise within a minute. A check that cannot run (no ruff on PATH, a timeout) says so in the warning rather than passing silently.
"""

import json
import os
import pathlib
import shutil
import subprocess
import sys

EDIT_TOOLS = {"Edit", "Write", "MultiEdit"}
RUFF_SELECT = "F821,F811"
# Seconds per subprocess. The lifecycle member budget is the sum of both plus headroom.
STEP_TIMEOUT = 8

SMOKE = """
import importlib, sys
sys.path.insert(0, sys.argv[1])
import worklist
broken = dict(getattr(worklist, "_BROKEN", {}) or {})
for name, why in sorted(broken.items()):
    print("sibling %s did not import: %s" % (name, why))
target = sys.argv[2]
if target and target != "worklist" and target not in broken:
    importlib.import_module(target)
"""


def edited_stop_module(payload):
    """The edited file's path when it is a Stop-hook module, else None."""
    if payload.get("tool_name") not in EDIT_TOOLS:
        return None
    raw = (payload.get("tool_input") or {}).get("file_path")
    if not isinstance(raw, str) or not raw.endswith(".py"):
        return None
    path = pathlib.Path(raw)
    if not path.is_absolute():
        path = pathlib.Path(payload.get("cwd") or os.getcwd()) / path
    parts = path.parent.parts
    if parts[-3:] != (".claude", "hooks", "stop") or not path.is_file():
        return None
    return path


def ruff_binary():
    found = shutil.which("ruff")
    if found:
        return found
    local = pathlib.Path.home() / ".local" / "bin" / "ruff"
    return str(local) if local.is_file() else None


def ruff_findings(path):
    """Ruff's concise lines for the edited file, or one line saying ruff could not run."""
    ruff = ruff_binary()
    if ruff is None:
        return ["ruff is not installed, so the undefined-name check did NOT run"]
    try:
        proc = subprocess.run(
            [
                ruff,
                "check",
                "--isolated",
                "--no-cache",
                "--select",
                RUFF_SELECT,
                "--output-format",
                "concise",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=STEP_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ["ruff did not finish (%s), so the undefined-name check did NOT run" % exc]
    if proc.returncode == 0:
        return []
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith(str(path))]
    return lines or [(proc.stdout + proc.stderr).strip() or "ruff exited %d" % proc.returncode]


def smoke_findings(path):
    """What the import smoke test of the edited file's stop directory reported."""
    module = path.stem if path.stem.isidentifier() else ""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", SMOKE, str(path.parent), module],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(path.parent),
            timeout=STEP_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ["the import smoke test did not finish (%s)" % exc]
    out = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    if proc.returncode != 0:
        tail = [ln for ln in proc.stderr.splitlines() if ln.strip()][-3:]
        out.append("importing the stop directory raised: " + " | ".join(tail))
    return out


def report(path, lint, smoke):
    lines = [
        "STOP HOOK EDIT CHECK: %s no longer loads cleanly. The Stop hook runs from the working "
        "tree, so every session's next stop runs this file as it is now." % path
    ]
    if lint:
        lines.append("ruff --select %s:" % RUFF_SELECT)
        lines.extend("  " + ln for ln in lint[:20])
    if smoke:
        lines.append("import smoke test of %s:" % path.parent)
        lines.extend("  " + ln for ln in smoke[:20])
    return "\n".join(lines)


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    path = edited_stop_module(payload)
    if path is None:
        return 0
    lint = ruff_findings(path)
    smoke = smoke_findings(path)
    if not lint and not smoke:
        return 0
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": report(path, lint, smoke),
            }
        },
        sys.stdout,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 -- a PostToolUse warning must never break the tool call
        print("stop-hook-edit-check: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        sys.exit(0)
