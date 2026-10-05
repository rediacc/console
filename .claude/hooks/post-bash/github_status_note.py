#!/usr/bin/env python3
"""PostToolUse(Bash): after a CI-related command, put GitHub's own service status into the agent's context when GitHub is degraded.

WHY HERE. A session reading "no runs yet" or "still queued" cannot tell a slow GitHub runner pool from a broken workflow, and on 2026-10-05 ("Incident with Actions", runner assignment delays) sessions burned turns on exactly that. PostToolUse is the primary channel (operator ruling 2026-10-05) because its `additionalContext` lands in the agent's context right after the command whose output it qualifies; the Stop hook only reaches the agent when it blocks.

ONLY CI-RELATED COMMANDS, AND ONLY AS INVOCATIONS (`CI_COMMAND`): `git push`, `ci-trace.py`, `gh run|pr|workflow`, `gh api .../actions...`, `wl_prreview.py`, each in command position. A command that only mentions one (`ls .../ci-trace.py`) is silent, and so is everything else.

NEVER THE NETWORK. `rediacc_ci.ci.github_status.read_cached` reads the machine-wide cache and, when it is older than 15 minutes, starts one detached refresher and returns at once; this hook therefore costs a file read and never waits on githubstatus.com (operator ruling 2026-10-05, "it should not block us much"). Silent when GitHub is ok or the status is simply unknown; after a degraded -> ok flip it says `GITHUB RECOVERED: ...` once per session (`github_status.surface`).

`--session-start` is the same note for the SessionStart pattern (`.claude/rediacc_hooks/lifecycle.py`), unconditional on the command: a session starting while GitHub is degraded should know before its first CI read.

Advisory: always exits 0 and never blocks the tool call that already ran.
"""

import importlib
import importlib.util
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODULE = "rediacc_ci.ci.github_status"
MODULE_FILE = ROOT / ".ci" / "rediacc_ci" / "ci" / "github_status.py"

# A CI command IN COMMAND POSITION (start of a line, or after `;`, `&`, `|`, `(`, `$(` or a backtick), read off `shellscan.scan_target`, which has already dropped heredoc bodies, quoted spans and `VAR=x` prefixes. A command that merely MENTIONS one (`ls .ci/scripts/ci/ci-trace.py`, `grep ci-trace.py x`) is not one: on 2026-10-05 the substring form fired on exactly that `ls`.
_POS = r"(?:^|[;&|(]|\$\(|`)\s*"
_PY = r"(?:python3?\s+)?"
CI_COMMAND = re.compile(
    _POS
    + r"(?:"
    + r"git(?:\s+-[Cc]\s+\S+)*\s+push\b"
    + r"|"
    + _PY
    + r"\S*ci-trace\.py\b"
    + r"|gh\s+(?:run|pr|workflow)\b"
    + r"|gh\s+api\s+\S*actions"
    + r"|"
    + _PY
    + r"\S*wl_prreview\.py\b"
    + r")",
    re.MULTILINE,
)


def _load_syspath():
    """The canonical `.claude` hop, rediacc_hooks/syspath.py, loaded BY PATH: this hook runs as a script, so `rediacc_hooks` is not importable by name until the hop has run."""
    hop_file = ROOT / ".claude" / "rediacc_hooks" / "syspath.py"
    spec = importlib.util.spec_from_file_location("rediacc_hooks_syspath", hop_file)
    if spec is None or spec.loader is None:
        raise ImportError("no loadable %s" % hop_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_github_status():
    """The status module by name when `.ci` is importable (the tests, which patch that object), else by file: a hook process has no `.ci` on sys.path."""
    if MODULE in sys.modules:
        return sys.modules[MODULE]
    try:
        return importlib.import_module(MODULE)
    except ImportError:
        spec = importlib.util.spec_from_file_location("github_status", MODULE_FILE)
        if spec is None or spec.loader is None:
            raise
        mod = importlib.util.module_from_spec(spec)
        # Registered BEFORE it runs: a dataclass resolves its module through sys.modules while the class is built.
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod


def is_ci_command(cmd):
    """True when `cmd` RUNS a command that reads or moves CI (`CI_COMMAND`), as opposed to naming one in an argument, a quoted string or a heredoc body."""
    # The cheap prefilter first: most Bash calls name none of these, and they skip the lexer's import entirely.
    if not cmd or not any(w in cmd for w in ("push", "ci-trace", "gh", "wl_prreview")):
        return False
    _load_syspath().on_sys_path(ROOT / ".claude")
    from rediacc_hooks import shellscan  # noqa: PLC0415 -- only a Bash payload needs the lexer

    return bool(CI_COMMAND.search(shellscan.scan_target(cmd)))


def note_line(session, gs=None):
    """The degraded line, the one-time recovery note for this session, or "" (ok, unknown, already told, or any failure)."""
    try:
        gs = gs or load_github_status()
        return gs.surface(session=session or None)
    except Exception:  # noqa: BLE001 -- advisory: a broken status read is silence, never a failed hook
        return ""


def render(event_name, text):
    return (
        json.dumps({"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": text}})
        + "\n"
    )


def main(argv=None, stdin=None, stdout=None):
    argv = sys.argv[1:] if argv is None else argv
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    try:
        try:
            doc = json.loads(stdin.read() or "{}")
        except ValueError:
            doc = {}
        doc = doc if isinstance(doc, dict) else {}
        session = str(doc.get("session_id") or "")
        if argv[:1] == ["--session-start"]:
            text = note_line(session)
            if text:
                stdout.write(render("SessionStart", text))
            return 0
        tool_input = doc.get("tool_input") if isinstance(doc.get("tool_input"), dict) else {}
        if not is_ci_command(str(tool_input.get("command") or "")):
            return 0
        text = note_line(session)
        if text:
            stdout.write(render("PostToolUse", text))
    except Exception:  # noqa: BLE001 -- advisory: never fail the chain
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
