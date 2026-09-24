#!/usr/bin/env python3
"""PostToolUse: after an edit to a hook module the lifecycle table runs, say at once whether it still loads.

WHY THIS EXISTS (agent/plans/PLAN-stop-hook-continuity.md, box P2.6). The Stop hook runs straight from the working tree, so a writer's half-finished edit to `.claude/hooks/stop/*.py` is every session's Stop hook. A NameError inside `run_stop` is a RUNTIME failure: nothing notices it until the next stop, where it blocks with a traceback, and in a shared tree that stop
may belong to a different session than the one that made the edit. The writer is the one party that can fix it cheaply, and the writer is in the middle of its own turn right now.

WHICH FILES. Every hook directory `.claude/rediacc_hooks/lifecycle.py` runs, DERIVED from its `PATTERNS` table rather than listed here, so a new hook directory wired there is covered with no edit to this file (worklist #95918e15; before it only `.claude/hooks/stop/` was, while lifecycle also ran hook code from `hooks/context`, `hooks/post-bash`, `hooks/trapguard`, `hooks/` itself and `rediacc_hooks`). A directory holding a lifecycle script is covered flat, the `.py` files directly inside it; a script inside a Python package (`rediacc_hooks`) covers that whole package, `guards/` included, since the dispatcher imports those modules by name. A `tests` directory is never a hook.

WHAT IT CHECKS, on an Edit, Write or MultiEdit of such a file:

  1. `ruff check --isolated --select F821,F811` on that file. F821 is the undefined name that
     is the whole motivating defect; F811 is a redefinition that shadows a live function. A
     syntax error is always reported by ruff, whatever is selected.
  2. An import smoke test in a subprocess: every lifecycle script of that directory (or
     package) is imported, then the edited module. An entry carrying a `_BROKEN` map is read,
     because `worklist.py` catches a sibling's import failure into `_BROKEN` rather than
     raising, so importing it alone would call a broken sibling healthy. Every entry script
     keeps its `main()` behind a `__name__` guard, so importing one runs no hook.

The directory checked is the EDITED FILE'S OWN, not this checkout's, and so is the lifecycle table when that checkout has one, so an edit in another worktree or in a copy is judged against its own siblings.

IT WARNS AND NEVER BLOCKS. Every path exits 0. A finding is returned as `hookSpecificOutput.additionalContext`, which reaches the writer in the same turn; a clean file produces no output at all, because a notice attached to every clean edit is noise within a minute. A check that cannot run (no ruff on PATH, a timeout) says so in the warning rather than passing silently.
"""

import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

EDIT_TOOLS = {"Edit", "Write", "MultiEdit"}
RUFF_SELECT = "F821,F811"
# Seconds per subprocess. The lifecycle member budget is the sum of both plus headroom.
STEP_TIMEOUT = 8

# This checkout's `.claude`, whose lifecycle table is the fallback when the edited checkout has none.
OWN_CLAUDE = pathlib.Path(__file__).resolve().parents[2]
LIFECYCLE_REL = pathlib.PurePosixPath("rediacc_hooks/lifecycle.py")
# A hook script as a lifecycle member names it: `"$CLAUDE_PROJECT_DIR/.claude/<rel>.py"`.
SCRIPT_RE = re.compile(r"\$CLAUDE_PROJECT_DIR/\.claude/([^\"'\s]+\.py)")

# argv: kind ("flat" or "package"), the sys.path base, the edited module, then the entries. A flat entry is a file name inside base; a package entry is a dotted name.
SMOKE = r"""
import importlib, importlib.util, sys
kind, base, target = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, base)
broken = set()

def load(entry):
    if kind == "package":
        return importlib.import_module(entry)
    stem = entry[:-3]
    name = stem if stem.isidentifier() else "_edit_check_" + "".join(c if c.isalnum() else "_" for c in stem)
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, base + "/" + entry)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        del sys.modules[name]
        raise
    return mod

for entry in list(dict.fromkeys(sys.argv[4:] + [target])):
    if (entry[:-3] if kind == "flat" else entry.rsplit(".", 1)[-1]) in broken:
        continue
    try:
        mod = load(entry)
    except BaseException as exc:
        print("importing %s raised %s: %s" % (entry, type(exc).__name__, exc))
        continue
    found = getattr(mod, "_BROKEN", None)
    for name, why in sorted(found.items() if isinstance(found, dict) else ()):
        broken.add(name)
        print("sibling %s did not import: %s" % (name, why))
"""


def claude_root(path):
    """The nearest `.claude` ancestor of the edited file, or None."""
    for parent in path.parents:
        if parent.name == ".claude":
            return parent
    return None


def lifecycle_scripts(root):
    """Every `.py` the lifecycle table runs, relative to `.claude`, read from the edited checkout's own table when it has one."""
    src = root / LIFECYCLE_REL
    if not src.is_file():
        src = OWN_CLAUDE / LIFECYCLE_REL
    spec = importlib.util.spec_from_file_location("_edit_check_lifecycle", src)
    if spec is None or spec.loader is None:
        return []
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    found = []
    for key in mod.PATTERNS:
        for member in mod.flat_commands(key):
            for rel in SCRIPT_RE.findall(member["command"]):
                if rel not in found:
                    found.append(rel)
    return [pathlib.PurePosixPath(rel) for rel in found]


def package_top(root, rel_dir):
    """The outermost package directory `rel_dir` sits in, relative to `.claude`, or None when it is no package."""
    top = None
    while rel_dir != pathlib.PurePosixPath(".") and (root / rel_dir / "__init__.py").is_file():
        top = rel_dir
        rel_dir = rel_dir.parent
    return top


def _dotted(rel):
    return ".".join(rel.with_suffix("").parts)


def hook_target(path):
    """(kind, base, target, entries) when the edited file is hook code the lifecycle table runs, else None."""
    root = claude_root(path)
    if root is None:
        return None
    rel = pathlib.PurePosixPath(path.relative_to(root).as_posix())
    if "tests" in rel.parts:
        return None
    scripts = lifecycle_scripts(root)
    for script in scripts:
        top = package_top(root, script.parent)
        if top is None or (rel.parent != top and top not in rel.parent.parents):
            continue
        under = [_dotted(s.relative_to(top.parent)) for s in scripts if top in s.parents]
        return "package", root / top.parent, _dotted(rel.relative_to(top.parent)), under
    flat = [s.name for s in scripts if s.parent == rel.parent]
    if flat:
        return "flat", root / rel.parent, rel.name, flat
    return None


def edited_hook_module(payload):
    """(path, smoke target) when the edited file is hook code the lifecycle table runs, else None."""
    if payload.get("tool_name") not in EDIT_TOOLS:
        return None
    raw = (payload.get("tool_input") or {}).get("file_path")
    if not isinstance(raw, str) or not raw.endswith(".py"):
        return None
    path = pathlib.Path(raw)
    if not path.is_absolute():
        path = pathlib.Path(payload.get("cwd") or os.getcwd()) / path
    if not path.is_file():
        return None
    target = hook_target(path.resolve())
    return (path, target) if target else None


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


def smoke_findings(target):
    """What the import smoke test of the edited file's hook directory reported."""
    kind, base, module, entries = target
    try:
        proc = subprocess.run(
            [sys.executable, "-c", SMOKE, kind, str(base), module, *entries],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(base),
            stdin=subprocess.DEVNULL,
            timeout=STEP_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return ["the import smoke test did not finish (%s)" % exc]
    out = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    if proc.returncode != 0:
        tail = [ln for ln in proc.stderr.splitlines() if ln.strip()][-3:]
        out.append("importing the hook directory raised: " + " | ".join(tail))
    return out


def report(path, lint, smoke):
    lines = [
        "HOOK EDIT CHECK: %s no longer loads cleanly. Hooks run from the working tree, so "
        "every session's next hook event runs this file as it is now." % path
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
    found = edited_hook_module(payload)
    if found is None:
        return 0
    path, target = found
    lint = ruff_findings(path)
    smoke = smoke_findings(target)
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
