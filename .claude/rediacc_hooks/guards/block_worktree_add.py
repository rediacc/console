"""Block `git worktree add` from the assistant's own Bash tool, unconditionally.

WHY UNCONDITIONAL. A hook has no reliable, verified way to tell "a live operator just approved this" from "an autonomous/cron-fired continuation
with nobody watching" -- there is no session field this codebase's other
hooks rely on for that distinction, and inventing one on an unverified guess is worse than not trying. So the policy is enforced by WHO can get the command to run at all, not by the hook reading intent:
  - An operator who wants a worktree created can run the command
    themselves via the `!` prefix (CLAUDE.md's documented escape hatch),
    which never reaches this hook -- that IS "asked the operator, they
    said yes", made structural rather than inferred.
  - An autonomous/cron-fired session has no live operator to relay that
    to, so the practical effect is worktree creation never happens there,
    which is exactly the "non-interactive: not allowed" requirement.

Found live 2026-08-01: a session created a throwaway worktree+branch for a small doc edit mid-/pr-merge, then a second one for a NUL-byte gate fix, after the operator had already twice said to keep changes local instead. The operator then found six PRE-EXISTING worktrees holding real, unrelated work from other sessions sitting untouched in the same repo. Worktrees are cheap to
create and easy to forget, and each one is a place uncommitted work can silently strand outside the one tree everyone actually watches.
"""

import re

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
ORDER = 28

# THE WRAPPER SAILED STRAIGHT PAST THE FIRST CHECK, and removing the second one puts it back: `./run.sh worktree create` runs the banned command through a script whose text never contains it.
DEFECT = ("if hookio.grep_q(RUN_SH_CREATE, scan):", "if False:")

# Command position: line start (or wrapper-payload line start), or after ; & | ( $( or a backtick. `git -C <path> worktree add ...` still matches since -C is a flag between `git` and `worktree`, not a new command.
#
# PORT NOTE. The bash writes this pattern inside DOUBLE quotes, so `\\\$\\(` reaches grep as `\$\(` and the backtick is bare. Here the pattern is a raw Python string, so the same ERE is spelled once instead of twice.
GIT_AT_CMD = hookio.rx(r"(^|[;&|(]|\$\(|`)[{S}]*git([{S}]+-[A-Za-z-]+([{S}]+[^ ;&|]+)?)*[{S}]+")

WORKTREE_ADD = GIT_AT_CMD + hookio.rx(r"worktree[{S}]+add([{S}]|$)")

# THE WRAPPER SAILED STRAIGHT PAST THE CHECK ABOVE. `./run.sh worktree create` reaches `rediacc_ci.dev.worktree.cmd_create`, which runs `git worktree add -b ...` -- the exact command this hook exists to stop -- but the text the hook sees never contains "git worktree add", so it matched nothing. The block was literal, and the wrapper is not literal.
#
# This got more urgent, not less: `worktree create` now also brings a devbox up, so the bypass costs a multi-GB image pull and a held port block on top of the unwanted checkout.
#
# NO "is this an agent?" SNIFF, deliberately. The operator's `!`-prefixed command runs in the SAME session with the SAME environment, so any such test would block the sanctioned path too. The `!` prefix bypasses PreToolUse hooks entirely, which is the whole mechanism -- there is nothing here to detect. The `(bash|sh)[[:space:]]+` prefix is not decoration: `bash run.sh worktree create`
# puts the INTERPRETER in command position, not the script, so a command-position-anchored match misses it entirely. Caught by driving both forms through this hook rather than reading the regex.
#
# ANY PATH TO run.sh, not only `./`. Measured 2026-10-09 before this widening: `/home/developer/console/run.sh worktree create x` was ALLOWED (rc 0) while `./run.sh worktree create x` was refused, because the old pattern accepted `run.sh` only bare or after `./`. The directory part admits `$`, `{`, `}` and `~` so `$ROOT/run.sh` and `~/console/run.sh` are the same decision as `./run.sh`.
RUN_SH_CREATE = hookio.rx(
    r"(^|[;&|(]|\$\(|`)[{S}]*((bash|sh)[{S}]+)?([A-Za-z0-9_.${}~/-]*/)?run\.sh[{S}]+worktree[{S}]+create([{S}]|$)"
)

# THE PORT SAILED PAST THE WRAPPER ARM, the same way the wrapper once sailed past the literal one. scripts/dev/worktree.sh was ported to `.ci/rediacc_ci/dev/worktree.py` and deleted (PLAN-retire-bash-oracles B3), and `run.sh` only ever reached it through `python3 -m rediacc_ci worktree`, so every spelling that calls the Python package directly creates a worktree without naming `run.sh`. Measured 2026-10-09 through chain-head.sh, every one rc 0 before this arm existed:
#
#   PYTHONPATH=.ci python3 -m rediacc_ci worktree create x       the package entry run.sh itself execs
#   PYTHONPATH=.ci python3 -m rediacc_ci.dev.worktree create x   the port's own `__main__`
#   python3 .ci/rediacc_ci/dev/worktree.py create x              the port by path
#
# JUDGED BY RUN, NOT BY TEXT. The first cut of this arm was an unanchored regex over the token pair `<entry> create`, and it refused `echo the docs say never to run rediacc_ci.dev.worktree create`, which is a sentence about the command and exactly the mention-matching class check:ci-guard-mention-anchoring exists for (that gate passed it anyway: a `(^|[^A-Za-z0-9_])` buried in one alternative read to it as a command-position anchor). So the arm walks `shellscan._analyse(cmd).runs`, the commands bash would execute: the walk already unwraps `env`, `timeout`, `nohup`, `exec`, `sudo`, an assignment prefix, a quoted command word, `sh -c` payloads and `$(...)`, which is every interpreter prefix the regex had to tolerate, and leaves an `echo` argument as an argument.
PYTHON = re.compile(r"^python[0-9.]*$")
# Interpreter options that consume the next word as their value (`python3 -X dev -m ...`).
PYTHON_VALUE_OPTIONS = ("-W", "-X", "-Q")
# The package entry run.sh execs: `-m rediacc_ci`, `-m rediacc_ci.__main__`, or the package directory / its `__main__.py` by path. Its first argument is the verb.
PACKAGE_TARGETS = ("rediacc_ci", "rediacc_ci.__main__")
# The port itself: its first argument is the command.
PORT_TARGETS = ("rediacc_ci.dev.worktree",)


def _python_argv(run_):
    """The interpreter's own argument list when `run_` is a Python interpreter, else None. `uv run [opts] python ...` is the one launcher whose argv carries the interpreter."""
    name = run_.name.rsplit("/", 1)[-1]
    args = list(run_.argv)
    if PYTHON.match(name):
        return args
    if name == "uv" and args[:1] == ["run"]:
        for k, word in enumerate(args[1:], 1):
            if PYTHON.match(word.rsplit("/", 1)[-1]):
                return args[k + 1 :]
    return None


def _target(args):
    """(target, the target's own arguments) for a python command line, or (None, []) for `-c`, `-` or no target."""
    i = 0
    while i < len(args):
        word = args[i]
        if word == "-m":
            return (args[i + 1], args[i + 2 :]) if i + 1 < len(args) else (None, [])
        if word.startswith("-m"):
            return word[2:], args[i + 1 :]
        if word in ("-c", "-") or word.startswith("-c"):
            return None, []
        if word in PYTHON_VALUE_OPTIONS:
            i += 2
            continue
        if not word.startswith("-"):
            return word, args[i + 1 :]
        i += 1
    return None, []


def runs_port_create(cmd):
    """Does `cmd` run the worktree port's `create`, through any Python spelling?"""
    for run_ in shellscan._analyse(cmd).runs:
        args = _python_argv(run_)
        if args is None:
            continue
        target, rest = _target(args)
        if not target:
            continue
        path = target.rstrip("/")
        package = target in PACKAGE_TARGETS or path.endswith(
            ("/rediacc_ci", "rediacc_ci/__main__.py")
        )
        port = target in PORT_TARGETS or path.rsplit("/", 1)[-1] == "worktree.py"
        if (package and rest[:2] == ["worktree", "create"]) or (port and rest[:1] == ["create"]):
            return True
    return False


GIT_MESSAGE = (
    "❌ BLOCKED: git worktree add is not run from here. Worktree creation needs the "
    "operator to approve it explicitly THIS session, then run the command themselves via "
    "the `!` prefix (bypasses this hook) -- do not ask the operator through chat and then "
    "run it yourself, and never create one in an autonomous/cron-fired continuation with "
    "no live operator to ask. Prefer working directly in the current checkout, a plain "
    "`git clone`, or an existing worktree instead. If you believe you already have "
    "explicit sign-off, hand the exact command back to the operator to run with `!`."
)

RUN_SH_MESSAGE = (
    "❌ BLOCKED: `run.sh worktree create` creates a git worktree (and now a devbox "
    "container with it), so it is the same decision as `git worktree add` and carries the "
    "same rule: the operator approves it explicitly THIS session and runs it themselves "
    "via the `!` prefix, which bypasses this hook. Do not ask through chat and then run it "
    "yourself, and never in an autonomous/cron-fired continuation with no live operator to "
    "ask. Prefer the current checkout or an existing worktree. `worktree list`, `switch`, "
    "`remove` and `prune` are unaffected."
)

PORT_MESSAGE = (
    "❌ BLOCKED: this runs the Python worktree port's `create` (`rediacc_ci.dev.worktree`), "
    "which is `./run.sh worktree create` without the router: it runs `git worktree add` and "
    "brings a devbox up, so it carries the same rule. The operator approves it explicitly THIS "
    "session and runs it themselves via the `!` prefix, which bypasses this hook. Do not ask "
    "through chat and then run it yourself, and never in an autonomous/cron-fired continuation "
    "with no live operator to ask. Prefer the current checkout or an existing worktree. The "
    "port's `list`, `switch`, `remove` and `prune` are unaffected."
)

EDGE_CASES = [
    ("the plain shape", "git worktree add /tmp/wt main"),
    ("a -C flag between git and the verb", "git -C private/renet worktree add /tmp/wt"),
    ("after a separator", "true; git worktree add /tmp/wt"),
    # The wrapper the second arm exists for, in three spellings.
    ("the run.sh wrapper", "./run.sh worktree create 0901-1"),
    ("the run.sh wrapper through an interpreter", "bash run.sh worktree create x"),
    ("the run.sh wrapper by absolute path", "/home/x/console/run.sh worktree create x"),
    # The Python port the wrapper reaches, in every spelling that skips run.sh.
    ("the package entry", "PYTHONPATH=.ci python3 -m rediacc_ci worktree create x"),
    ("the port's module", "PYTHONPATH=.ci python3 -m rediacc_ci.dev.worktree create x"),
    ("the port by path", "python3 .ci/rediacc_ci/dev/worktree.py create x"),
    ("the port under a venv interpreter", "uv run python -m rediacc_ci.dev.worktree create"),
    ("control: the port's list is allowed", "python3 -m rediacc_ci.dev.worktree list"),
    ("control: the package's worktree list is allowed", "python3 -m rediacc_ci worktree list"),
    (
        "control: reading the port is not running it",
        "grep -n create .ci/rediacc_ci/dev/worktree.py",
    ),
    ("the port inside sh -c", "sh -c 'python3 -m rediacc_ci worktree create x'"),
    ("the port behind timeout", "timeout 60 python3 .ci/rediacc_ci/dev/worktree.py create"),
    ("the port with an interpreter option first", "python3 -X dev -m rediacc_ci worktree create"),
    (
        "control: a sentence naming the port is not running it",
        "echo the docs say never to run rediacc_ci.dev.worktree create here",
    ),
    # Reads are none of this hook's business.
    ("listing worktrees is allowed", "git worktree list"),
    ("removing a worktree is allowed", "git worktree remove /tmp/wt"),
    ("run.sh doing something else", "./run.sh setup --check"),
    ("prose is stripped before the scan", "echo 'git worktree add /tmp/wt'"),
    # RULE T (PLAN-retire-bash-oracles A4, A0 L9): GIT_AT_CMD's anchor is the copied `(^|[;&|(]|\$\(|`)`, which misses every reserved word, prefix builtin and leading redirect. These ran with rc 0 until `shellscan.lifted_commands`; the heredoc twin below them is data and stays allowed.
    ("L9 a brace group", "{ git worktree add /tmp/wt main; }"),
    ("L9 a leading redirect", "2>/dev/null git worktree add /tmp/wt main"),
    ("L7 a quoted command word", '"git" worktree add /tmp/wt main'),
    (
        "control: a quoted heredoc naming the command is data",
        "cat > n.md <<'EOF'\ngit worktree add /tmp/wt main\nEOF",
    ),
]


def run(ev):
    cmd = ev.field("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW

    scan = shellscan._command_substitution(shellscan.scan_target(cmd))

    if hookio.grep_q(WORKTREE_ADD, scan):
        ev.warn(GIT_MESSAGE)
        return hookio.DENY

    if hookio.grep_q(RUN_SH_CREATE, scan):
        ev.warn(RUN_SH_MESSAGE)
        return hookio.DENY

    if runs_port_create(cmd):
        ev.warn(PORT_MESSAGE)
        return hookio.DENY
    return hookio.ALLOW
