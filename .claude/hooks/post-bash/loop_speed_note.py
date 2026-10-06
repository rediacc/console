#!/usr/bin/env python3
"""PostToolUse(Bash): two loop-speed notes (agent/plans/PLAN-fast-loop.md, Parts 3 and 4). Informational: the tool call already ran, nothing is refused, the exit status is 0 whatever happens.

PART 3, ONE PRE-PUSH PER PUSH. When the command RUNS `npm run ci:quick`, `run.ts --quick` or a prepush script (command position, read off `shellscan.scan_target`, so a command that merely mentions one is silent), the note says a receipt is worth building only when a push is due: an epic milestone, a fix for a red, or a stop with unpushed commits.

PART 4, DON'T PUSH INTO A RUNNING RUN. When the command RUNS `git push` and the cached PR CI state (the file the Stop hook's `wl_ci.ci_trouble` keeps; no GitHub call is made here) shows the run on the pushed head in progress and not red, the note advises holding further commits until it settles. A red with a fix in hand pushes at once, and a push is never refused.
"""

import importlib.util
import json
import os
import pathlib
import re
import sys

HOOKS = pathlib.Path(__file__).resolve().parents[1]

_POS = r"(?:^|[;&|(]|\$\(|`)\s*"
# `npm run ci:quick`, `npm run -s ci:quick`, `[npx] tsx scripts/ci-runner/run.ts ... --quick`, and any prepush script by name.
RECEIPT_COMMAND = re.compile(
    _POS
    + r"(?:"
    + r"npm\s+run\s+(?:-\S+\s+)*ci:quick\b"
    + r"|(?:npx\s+)?tsx\s+\S*ci-runner/run\.ts\b[^;&|]*--quick\b"
    + r"|(?:npm\s+run\s+(?:-\S+\s+)*|(?:python3?\s+|bash\s+)?\S*/)\S*prepush\S*"
    + r")",
    re.MULTILINE,
)
PUSH_COMMAND = re.compile(_POS + r"git(?:\s+-[Cc]\s+\S+)*\s+push\b", re.MULTILINE)


def _load_syspath():
    """The canonical `.claude` hop, loaded BY PATH: this hook runs as a script, so `rediacc_hooks` is not importable by name until the hop has run."""
    hop_file = HOOKS.parent / "rediacc_hooks" / "syspath.py"
    spec = importlib.util.spec_from_file_location("rediacc_hooks_syspath", hop_file)
    if spec is None or spec.loader is None:
        raise ImportError("no loadable %s" % hop_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def classify(cmd):
    """ "receipt", "push" or "": which note a Bash command line earns, by invocation in command position."""
    if not cmd or not any(w in cmd for w in ("ci:quick", "prepush", "--quick", "push")):
        return ""
    syspath = _load_syspath()
    syspath.on_sys_path(syspath.CLAUDE_DIR)
    from rediacc_hooks import shellscan  # noqa: PLC0415 -- only a candidate command needs the lexer

    scanned = shellscan.scan_target(cmd)
    if RECEIPT_COMMAND.search(scanned):
        return "receipt"
    if PUSH_COMMAND.search(scanned):
        return "push"
    return ""


def push_note(doc):
    """The hold note for a `git push` payload, or "" when the cached run is not in progress-and-not-red."""
    syspath = _load_syspath()
    syspath.on_sys_path(syspath.STOP_DIR)
    import wl_core as C  # noqa: PLC0415 -- only a push needs the Stop modules
    import wl_loopspeed as L  # noqa: PLC0415
    import worklist_messages as M  # noqa: PLC0415

    root = C.project_root(C.project_start(doc))
    worklist = C.worklist_for(C.project_start(doc))
    head = L.pending_run(worklist, str(doc.get("session_id") or ""))
    if head is None:
        return ""
    ahead = L.unpushed(root)
    return M.N_CI_HOLD % (head, ahead) if ahead else M.N_CI_HOLD_PUSHED % head


def note_for(doc):
    """The additionalContext text for this payload, or ""."""
    tool_input = doc.get("tool_input")
    cmd = str(tool_input.get("command") or "") if isinstance(tool_input, dict) else ""
    kind = classify(cmd)
    if kind == "receipt":
        syspath = _load_syspath()
        syspath.on_sys_path(syspath.STOP_DIR)
        import worklist_messages as M  # noqa: PLC0415

        return M.N_RECEIPT_EARLY
    if kind == "push":
        return push_note(doc)
    return ""


def render(text):
    return (
        json.dumps(
            {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}
        )
        + "\n"
    )


def main(stdin=None, stdout=None):
    if os.environ.get("COMMIT_REVIEW_CHILD") or os.environ.get("STOPHOOK_CHILD"):
        return 0
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    try:
        doc = json.loads(stdin.read() or "{}")
        text = note_for(doc) if isinstance(doc, dict) else ""
        if text:
            stdout.write(render(text))
    except Exception:  # noqa: BLE001 -- advisory: never fail the chain
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
