#!/usr/bin/env python3
"""One hook command per (event, matcher) pattern, and the table that says what it runs.

WHAT CHANGED AND WHY. `.claude/settings.json` used to register 30 command entries over 11 distinct (event, matcher) patterns: a jq check and a python3 check were copied into all three PreToolUse chains and into PostToolUse/Bash, and seven lifecycle hooks sat in groups of one under a null matcher. The harness forks a process per entry, so the cost was paid on every tool call.
`PATTERNS` below is that wiring, moved out of the settings file: the file now names ONE command per pattern and this module runs the rest, in the order the file declared them.

THE TABLE IS THE RECORD, so nothing about the old shape is lost. `flat_commands()` returns the exact command sequence a pattern ran before the collapse, which is what `.ci/scripts/quality/check_hooks_resolvable.py` resolves, what `tests/test_dispatch.py` derives guard positions from, and what `tests/test_settings_collapse.py` compares against the settings file. A member dropped
from the table is therefore a failure in four places rather than a guard that quietly stopped running.

WHY A BASH HEAD SITS IN FRONT OF FOUR OF THEM. One of the two checks is the check that python3 exists, so it may never be Python; `.claude/hooks/chain-head.sh` says so in its own header. A pattern that begins with it therefore cannot begin with this module, and that head is the minimum that can: the two checks inlined, then this runner. The seven patterns that never ran those two
checks are not given them here, because adding a refusal a pattern did not have is a behaviour change and this collapse is not one.

WHAT IT REPRODUCES, MEMBER FOR MEMBER. The harness runs the commands of a block in order, each with the event payload on stdin; exit 2 is a blocking refusal and stops the block, any other non-zero is a non-blocking error whose stderr is surfaced while the block continues. That is what `run_pattern` does. A member that raises, or that never returns inside its own timeout, is named
loudly and the rest still run, which is the argument `dispatch.run_chain` makes for guards applied with more force, because one process now carries a whole pattern.

STDOUT IS MERGED, NOT CONCATENATED. Several lifecycle hooks answer with a JSON document carrying `hookSpecificOutput.additionalContext`, and two such documents written back to back parse as neither. `merge_stdout` folds them into one document and joins the contexts; plain text passes through verbatim when no member spoke JSON, which is every guard pattern.
"""

import json
import os
import pathlib
import shlex
import subprocess
import sys

# The harness's own per-command default, in seconds. A collapsed entry's timeout in settings.json is the SUM of its members' budgets, so no member is cut shorter than it was when it had an entry of its own.
DEFAULT_TIMEOUT = 60

# `$CLAUDE_PROJECT_DIR` is spelled by the settings file, so the members keep spelling it: the table has to read back as the commands that file used to carry, and `argv_of` is what expands it.
_P = '"$CLAUDE_PROJECT_DIR/.claude/%s"'

# What `.claude/hooks/chain-head.sh` decides before this module runs, so the flattened view is complete. The two checks were scripts of their own until 2026-09-21; they are inlined in the head now, and `--check <tool>` keeps each addressable as one command. Two members rather than one is what keeps every guard's ORDER the position it always was.
HEAD = (
    {"command": "bash " + _P % "hooks/chain-head.sh" + " --check jq"},
    {"command": "bash " + _P % "hooks/chain-head.sh" + " --check python3"},
)


def head_checks():
    """The tools the head checks for, in order, as the members name them.

    ONE RECORD, read by both the gate and the collapse test. The head is bash and this table is Python, so nothing but a reader of both can say they still agree; a head that quietly stopped checking one tool would leave every reader of the flattened view wrong in the same direction.
    """
    return tuple(member["command"].rsplit(" ", 1)[-1] for member in HEAD)


HEAD_SCRIPT = ".claude/hooks/chain-head.sh"
RUNNER_SCRIPT = ".claude/rediacc_hooks/lifecycle.py"

# The seam every reader of the wiring shares, in the shape `TRAP_SETTINGS` and `HOOK_EXEC_COUNTER_DIR` already use. A wiring change cannot be checked by editing the live file first: a wrong second of `.claude/settings.json` is a wrong second for every concurrent session in a shared worktree, so the proposed file is driven through this and applied afterwards. Nothing on the hook
# path reads it.
SETTINGS_ENV = "REDIACC_HOOK_SETTINGS"


def _members(*commands):
    return [c if isinstance(c, dict) else {"command": c} for c in commands]


# Anything that makes a command line a SHELL PROGRAM rather than a program with arguments. A member carrying one of these is run through bash, because reproducing redirection, chaining or globbing by hand is how a runner starts to differ from the harness it replaces.
_SHELL_CHARS = ";&|<>()`*?[]{}!#~\n"


def argv_of(command, env):
    """A member's argv, or None when it needs a shell.

    WHY NOT ALWAYS A SHELL. The harness runs every hook command through one, and reproducing that literally costs an extra process per member: `bash -c 'python3 x.py'` forks a shell that immediately execs. Nine of the eleven patterns hold nothing but `<interpreter> "<path>" <flags>`, where the shell's only contribution is expanding `$CLAUDE_PROJECT_DIR` and removing the quotes, and
    both of those are done here instead. The fallback keeps the faithful path available for anything else, and the collapse differential compares the two.
    """
    if any(c in command for c in _SHELL_CHARS):
        return None
    expanded = command.replace("$CLAUDE_PROJECT_DIR", env.get("CLAUDE_PROJECT_DIR", ""))
    if "$" in expanded:
        return None  # another variable to expand, so the shell does it
    try:
        argv = shlex.split(expanded)
    except ValueError:
        return None
    return argv or None


# Every (event, matcher) pattern the settings file wires, in the order the file lists them.
#
# `head` is True where the pattern began with the two toolchain checks before the collapse, and only there. `collapsed` is False for the four patterns that already carried a single command: wrapping one command in a runner adds a process instead of removing one, so those keep their entry verbatim and appear here only so this table is the whole picture.
PATTERNS = {
    "pre-bash": {
        "event": "PreToolUse",
        "matcher": "Bash",
        "head": True,
        "collapsed": True,
        # THE DISPATCHER CARRIES TWO BUDGETS, and that is what keeps the entry's timeout unchanged across the W7 P6 port. `block-pathspecless-git-commit.sh` was the last bash member of this pattern and ran after the dispatcher; it is `guards/block_pathspecless_git_commit.py` now, so it runs INSIDE the dispatcher at the same position it always held. `entry_timeout` sums the
        # members, so folding a member in without folding in its 60 seconds would silently cut the pattern's budget from 240 to 180 for every session sharing this checkout.
        "members": _members(
            {
                "command": "python3 " + _P % "rediacc_hooks/dispatch.py" + " --chain pre-bash",
                "timeout": 2 * DEFAULT_TIMEOUT,
            },
        ),
    },
    "pre-edit": {
        "event": "PreToolUse",
        "matcher": "^(Edit|MultiEdit|Write|NotebookEdit)$",
        "head": True,
        "collapsed": True,
        "members": _members(
            "python3 " + _P % "hooks/why-on-edit.py",
            "python3 " + _P % "rediacc_hooks/dispatch.py" + " --chain pre-edit",
        ),
    },
    "pre-ask": {
        "event": "PreToolUse",
        "matcher": "AskUserQuestion",
        "head": True,
        "collapsed": True,
        "members": _members(
            "python3 " + _P % "rediacc_hooks/dispatch.py" + " --chain pre-ask",
        ),
    },
    # THE PARALLEL-WRITER CAP (agent/plans/PLAN-parallel-writer-roster.md). A writer-class spawn is refused while `wl_roster.WRITER_CAP` writers are already live; Plan and Explore spawns never are. The Stop hook's `roster-cap` recounts from the authoritative event on every stop, so this guard is the primary and that block is the backstop. A head pattern like the other guard
    # chains, because a missing python3 would otherwise disarm it silently.
    "pre-agent": {
        "event": "PreToolUse",
        "matcher": "^(Agent|Task)$",
        "head": True,
        "collapsed": True,
        "members": _members(
            "python3 " + _P % "rediacc_hooks/dispatch.py" + " --chain pre-agent",
        ),
    },
    "post-bash": {
        "event": "PostToolUse",
        "matcher": "Bash",
        "head": True,
        "collapsed": True,
        # PYTHON SINCE W7 P6, same order, same budgets, same stop-at-refusal semantics. Both were bash until the port; their originals were kept as `.claude/oracles/post-bash/*.sh` until PLAN-retire-bash-oracles A3 deleted them, and `tests/test_post_bash_differential.py` now runs each port against a golden frozen from that same shared set of `git` and `gh` stubs. Neither ever exits 2, so nothing behind them was ever stopped and nothing is now.
        "members": _members(
            "python3 " + _P % "hooks/post-bash/cancel_old_ci.py",
            "python3 " + _P % "hooks/post-bash/refresh_pr_body.py",
            "python3 " + _P % "hooks/trapguard/dispatch.py" + " --posttool",
        ),
    },
    "post-tool": {
        "event": "PostToolUse",
        "matcher": None,
        "head": False,
        "collapsed": True,
        "members": _members(
            {"command": "python3 " + _P % "hooks/context/band-notice.py", "timeout": 15},
            "python3 " + _P % "hooks/context/onboard.py",
            # PLAN-stop-hook-continuity P2.6: an edit to a Stop-hook module is linted and import-smoked in the writer's own turn. It warns and never exits 2, so nothing behind it is stopped. Two 8-second steps plus interpreter start fit in 20.
            {"command": "python3 " + _P % "hooks/context/stop-hook-edit-check.py", "timeout": 20},
        ),
    },
    "pre-compact": {
        "event": "PreCompact",
        "matcher": None,
        "head": False,
        "collapsed": False,
        "members": _members(
            {"command": "python3 " + _P % "hooks/context/precompact-floor.py", "timeout": 45},
        ),
    },
    "teammate-idle": {
        "event": "TeammateIdle",
        "matcher": None,
        "head": False,
        "collapsed": False,
        "members": _members("$CLAUDE_PROJECT_DIR/.claude/hooks/stop/worklist.py --teammate-idle"),
    },
    "subagent-stop": {
        "event": "SubagentStop",
        "matcher": None,
        "head": False,
        "collapsed": False,
        "members": _members(
            "python3 " + _P % "hooks/stop/wl_report.py" + " --subagent-stop",
        ),
    },
    "stop": {
        "event": "Stop",
        "matcher": None,
        "head": False,
        "collapsed": False,
        "members": _members(
            {"command": "python3 " + _P % "hooks/stop/worklist.py", "timeout": 900},
        ),
    },
    "post-compact": {
        "event": "PostCompact",
        "matcher": None,
        "head": False,
        "collapsed": True,
        "members": _members(
            "python3 " + _P % "hooks/stop/worklist.py" + " --post-compact",
            "python3 " + _P % "hooks/stop/wl_report.py" + " --post-compact",
            {"command": "python3 " + _P % "hooks/context/epoch-reset.py", "timeout": 15},
            "python3 " + _P % "hooks/context/onboard.py" + " --arm",
        ),
    },
    "session-start": {
        "event": "SessionStart",
        "matcher": None,
        "head": False,
        "collapsed": True,
        "members": _members(
            "python3 " + _P % "hooks/stop/worklist.py" + " --session-start",
            "python3 " + _P % "hooks/stop/wl_report.py" + " --session-start",
            "python3 " + _P % "hooks/context/onboard.py" + " --arm",
        ),
    },
}


def flat_commands(key):
    """The command sequence this pattern ran before the collapse, head included."""
    pattern = PATTERNS[key]
    head = [dict(h) for h in HEAD] if pattern["head"] else []
    return head + [dict(m) for m in pattern["members"]]


def entry_command(key):
    """The single command string `.claude/settings.json` carries for this pattern."""
    pattern = PATTERNS[key]
    if not pattern["collapsed"]:
        return pattern["members"][0]["command"]
    if pattern["head"]:
        return "bash " + _P % "hooks/chain-head.sh" + " " + key
    return "python3 " + _P % "rediacc_hooks/lifecycle.py" + " " + key


def entry_timeout(key):
    """The collapsed entry's budget: every member's, so none is cut shorter than before."""
    budgets = [m.get("timeout", DEFAULT_TIMEOUT) for m in flat_commands(key)]
    if not PATTERNS[key]["collapsed"]:
        return budgets[0] if budgets[0] != DEFAULT_TIMEOUT else None
    return sum(budgets)


def hooks_block():
    """The whole `hooks` object of the collapsed settings file, derived from the table."""
    out = {}
    for key, pattern in PATTERNS.items():
        entry = {"type": "command", "command": entry_command(key)}
        timeout = entry_timeout(key)
        if timeout is not None:
            entry["timeout"] = timeout
        block = {"hooks": [entry]}
        if pattern["matcher"] is not None:
            block = {"matcher": pattern["matcher"], "hooks": [entry]}
        out.setdefault(pattern["event"], []).append(block)
    return out


def routed_key(command):
    """The pattern key a settings command delegates to, or None if it runs a hook itself."""
    for script in (HEAD_SCRIPT, RUNNER_SCRIPT):
        marker = script.rsplit("/", 1)[-1]
        if marker not in command:
            continue
        tail = command.rsplit(marker, 1)[1].strip().strip('"').split()
        if tail and tail[0] in PATTERNS:
            return tail[0]
    return None


def expand(command):
    """A settings command as the list of commands it really runs.

    A command that delegates to the head or to this runner expands to the pattern's flattened sequence; anything else is itself. This is what keeps every reader of the settings file (the resolvable gate, the wiring test, the guard-position test) looking at the same 30 commands after the collapse as before it.
    """
    key = routed_key(command)
    if key is None:
        return [{"command": command}]
    return flat_commands(key)


# A pattern key this module does not know is the failure the whole collapse risks: one command now carries a whole pattern, so an unrecognised key is every hook of that pattern silently not running while the tool call still looks clean. Refusing is the same fail-closed answer `dispatch.EMPTY_CHAIN` and the head's jq check give.
UNKNOWN_KEY = (
    "BLOCKED: %r is not a hook pattern this repo wires.\n"
    "\n"
    "One command in .claude/settings.json runs a whole (event, matcher) pattern now, so an\n"
    "unrecognised key is not a typo with a cosmetic cost: every hook that pattern carries is\n"
    "not running at all, and nothing else would say so.\n"
    "\n"
    "Known keys: %s\n"
)

EMPTY_PATTERN = (
    "BLOCKED: the %s hook pattern has ZERO members, so the command that replaced its entries\n"
    "runs nothing. Look at PATTERNS in .claude/rediacc_hooks/lifecycle.py.\n"
)


def merge_stdout(chunks):
    """One stdout for the whole pattern, out of one per member.

    Plain text passes through verbatim when no member answered with JSON, which is every guard pattern and is what keeps the collapse byte-faithful where the bytes are compared. Where members do answer with JSON objects they are merged into one document, because two documents written back to back parse as neither.
    """
    docs = []
    plain = []
    for chunk in chunks:
        if not chunk.strip():
            continue
        try:
            parsed = json.loads(chunk)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            docs.append(parsed)
        else:
            plain.append(chunk)
    if not docs:
        return "".join(chunks)
    merged = {}
    contexts = []
    messages = []
    event_name = None
    for doc in docs:
        specific = doc.get("hookSpecificOutput")
        if isinstance(specific, dict):
            event_name = event_name or specific.get("hookEventName")
            text = specific.get("additionalContext")
            if text:
                contexts.append(text)
            for key, value in specific.items():
                if key not in ("hookEventName", "additionalContext"):
                    merged.setdefault("hookSpecificOutput", {})[key] = value
        message = doc.get("systemMessage")
        if message:
            messages.append(message)
        merged.update(
            {k: v for k, v in doc.items() if k not in ("hookSpecificOutput", "systemMessage")}
        )
    # Plain text can only reach here beside a JSON answer, where there is no second stdout to put it on. Folding it into the context keeps it visible rather than dropping it, and the collapse test asserts that no live pattern mixes the two.
    contexts.extend(plain)
    if contexts or event_name:
        specific = merged.setdefault("hookSpecificOutput", {})
        if event_name:
            specific["hookEventName"] = event_name
        if contexts:
            specific["additionalContext"] = "\n\n".join(contexts)
    if messages:
        merged["systemMessage"] = "\n".join(messages)
    return json.dumps(merged) + "\n"


def run_pattern(key, payload, env=None, cwd=None, members=None):
    """Every member of one pattern, in order. Returns (rc, stdout, stderr).

    STOPPING IS THE HARNESS'S RULE, NOT A SHORTCUT. Exit 2 is a blocking refusal: the harness stops the block there and the entries behind it never speak, so this stops there too. Any other non-zero is a non-blocking error, which the harness surfaces WITHOUT stopping the block, so the rest still run and the pattern ends non-zero to keep the failure visible.

    A MEMBER THAT DIES DOES NOT TAKE THE PATTERN WITH IT. Before the collapse a member that crashed, or hung past its timeout, cost exactly itself; the entries behind it were separate commands and still ran. In one process an uncaught exception would end the interpreter and silently disarm every member behind it, which is a strictly larger blast radius than the arrangement this
    replaces.

    `members` is for the differential's controls, which drop one member and require the comparison to go red. Nothing in the live path passes it.
    """
    if key not in PATTERNS:
        return 2, "", UNKNOWN_KEY % (key, ", ".join(sorted(PATTERNS)))
    if members is None:
        members = flat_commands(key) if not PATTERNS[key]["head"] else PATTERNS[key]["members"]
    members = [dict(m) for m in members]
    if not members:
        return 2, "", EMPTY_PATTERN % key
    environ = os.environ if env is None else env
    out = []
    err = []
    failed = False
    for member in members:
        command = member["command"]
        budget = member.get("timeout", DEFAULT_TIMEOUT)
        argv = argv_of(command, environ)
        try:
            proc = subprocess.run(
                argv or ["bash", "-c", command],
                input=payload,
                capture_output=True,
                text=True,
                check=False,
                env=environ,
                cwd=cwd,
                timeout=budget,
            )
        except subprocess.TimeoutExpired:
            failed = True
            err.append(
                "HOOK MEMBER TIMED OUT after %ss, so it decided nothing: %s\n"
                "The rest of the %s pattern still ran.\n" % (budget, command, key)
            )
            continue
        except OSError as exc:
            failed = True
            err.append(
                "HOOK MEMBER COULD NOT START, so it decided nothing: %s (%s)\n"
                "The rest of the %s pattern still ran.\n" % (command, exc, key)
            )
            continue
        out.append(proc.stdout)
        err.append(proc.stderr)
        if proc.returncode == 2:
            return 2, merge_stdout(out), "".join(err)
        if proc.returncode != 0:
            failed = True
    return (1 if failed else 0), merge_stdout(out), "".join(err)


def settings_path():
    """The settings file a reader of the wiring should read: the live one, or the proposed one."""
    return pathlib.Path(os.environ.get(SETTINGS_ENV) or (repo_root() / ".claude/settings.json"))


def repo_root():
    """The tree holding both `.claude` and `.ci`, found by looking rather than by counting."""
    for candidate in pathlib.Path(__file__).resolve().parents:
        if (candidate / ".claude").is_dir() and (candidate / ".ci").is_dir():
            return candidate
    msg = "no repository root above %s (looked for a directory holding .claude and .ci)" % __file__
    raise RuntimeError(msg)


def main(argv):
    if not argv:
        print(__doc__.strip(), file=sys.stderr)
        return 64
    if argv[0] == "--flatten":
        print(json.dumps({key: flat_commands(key) for key in PATTERNS}, indent=2))
        return 0
    if argv[0] == "--hooks":
        print(json.dumps(hooks_block(), indent=2))
        return 0
    env = dict(os.environ)
    env.setdefault("CLAUDE_PROJECT_DIR", str(repo_root()))
    rc, out, err = run_pattern(argv[0], sys.stdin.read(), env=env)
    sys.stdout.write(out)
    sys.stderr.write(err)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
