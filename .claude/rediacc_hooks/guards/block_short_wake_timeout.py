"""Refuse a wake-timer arm (`wl_wake.py <me>`) that cannot wake the session.

WHY (PLAN-lessons-registry-followups L11, operator ruling 2026-11-10: "Build L11 (+ the & check)"). The harness re-invokes a session only when a BACKGROUND TASK EXITS, and `.claude/hooks/stop/wl_wake.py` exists to be one that is guaranteed to exit. Four spellings of the arm look armed and are not:

1. Behind a shell `&`. `python3 .claude/hooks/stop/wl_wake.py d778be9d --minutes 30 >/dev/null 2>&1 & true`, appended to an unrelated command, ran on 2026-11-10. The Bash call returns at once and the timer sleeps on as an orphan the harness never tracked, so its exit wakes nothing; the Stop hook's `wake-timer` invariant does not see it either, since that reads the harness's own background tasks.
2. Chained with another command (`;`, `&&`, `||`, a pipe, a substitution, a nested shell). The task's exit is then tied to the other work, and `wl_wake.split_wakers` reads the whole task as a timer, so the work it waits on drops out of the wait.
3. In the foreground. The call blocks the turn for the whole sleep, which is the opposite of what a timer is for. `wl_wake.py`'s own usage line says "always with run_in_background", and nothing in it admits a foreground arm.
4. With a Bash `timeout` not above the sleep. The harness kills a background task at its `timeout`, 30 minutes when none is passed, which is exactly the default sleep, so the timer died just before firing (2026-10-04, task bsbrweq7v). The required value is `wl_wake.harness_timeout_ms(N)`, read from that module rather than copied, so a change to the margin or the ceiling moves this guard with it.

This is trap `wake-timer-timeout-above-sleep` in docs/agent-reference/TRAPS.md, whose Residue ("nothing reads the Bash call's timeout") this guard retires.

WHAT COUNTS AS AN ARM. Only a command bash would RUN, as `shellscan.every_run` finds it: `python3 [opts] <path>/wl_wake.py ...` or the file run by path, at any depth (a `bash -c` payload, a heredoc fed to a shell, a substitution). A heredoc read by `cat`, an `echo`, a `grep wl_wake.py`, or a commit message naming the file runs nothing and is not judged. An arm is a run whose first operand is a session prefix (`wl_wake.SESSION_RE`) or a word holding an expansion this walk cannot know; `wl_wake.py --help` and any other first word make the script print its usage and exit 2 without sleeping, so they pass.

UNKNOWN MINUTES REQUIRE THE CEILING. `--minutes $N` cannot be read here, so the arm must carry `wl_wake.HARNESS_MAX_MS`, the one timeout that covers every legal sleep. Guessing the default would admit the exact failure this guard exists for.
"""

import math
import re

from rediacc_hooks import hookio, shellscan, syspath

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 69

# The incident's own check: with it forced off, the 2026-11-10 `... & true` arm passes again whenever no other command shares the line.
DEFECT = ('backgrounded = "&" in ops', "backgrounded = False")

WAKE_FILE = "wl_wake.py"
_PYTHON = re.compile(r"^python(?:3(?:\.[0-9]+)?)?$")
# Python's options that consume the next word, so that word is not read as the script.
_PY_VALUE_OPTS = frozenset(("-W", "-X", "-Q"))
_UNKNOWN = re.compile(r"[$`]")

EDGE_CASES = [
    (
        "the 2026-11-10 incident: backgrounded with & after nothing else",
        {
            "tool_input": {
                "command": "python3 .claude/hooks/stop/wl_wake.py d778be9d --minutes 30 >/dev/null 2>&1 & true",
                "run_in_background": False,
            }
        },
    ),
    (
        "chained after another command in a background task",
        {
            "tool_input": {
                "command": "npm test; python3 .claude/hooks/stop/wl_wake.py d778be9d",
                "run_in_background": True,
                "timeout": 2400000,
            }
        },
    ),
    (
        "the right shape with the harness default timeout",
        {
            "tool_input": {
                "command": "python3 .claude/hooks/stop/wl_wake.py d778be9d",
                "run_in_background": True,
            }
        },
    ),
    (
        "the right shape in the foreground",
        {
            "tool_input": {
                "command": "python3 .claude/hooks/stop/wl_wake.py d778be9d",
                "timeout": 2400000,
            }
        },
    ),
    (
        "the correct arm",
        {
            "tool_input": {
                "command": "python3 .claude/hooks/stop/wl_wake.py d778be9d",
                "run_in_background": True,
                "timeout": 2400000,
            }
        },
    ),
    (
        "a heredoc read by cat that names the timer",
        "cat <<'E'\npython3 .claude/hooks/stop/wl_wake.py d778be9d &\nE",
    ),
    ("a grep naming the timer", "grep -n wl_wake.py .claude/hooks/stop/wl_checks.py"),
    ("the usage line", "python3 .claude/hooks/stop/wl_wake.py --help"),
]


def _wl_wake():
    """The timer module itself, so every number in a refusal is the one the timer uses."""
    syspath.on_sys_path(syspath.STOP_DIR)
    import wl_wake

    return wl_wake


def _operands_start(run_):
    """Index into `run_.argv` where wl_wake.py's own arguments begin, or None when this run is not wl_wake.py."""
    base = run_.name.rsplit("/", 1)[-1]
    if base == WAKE_FILE:
        return 0
    if not _PYTHON.match(base):
        return None
    argv = run_.argv
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "-" or (
            arg[:1] == "-"
            and arg[1:].isalpha()
            and arg[1:2] not in ("W", "X")
            and ("c" in arg[1:] or "m" in arg[1:])
        ):
            # An inline program, a module or stdin: no script path is run, and a program's text is not this guard's question.
            return None
        if arg in _PY_VALUE_OPTS:
            i += 2
            continue
        if arg.startswith("-"):
            i += 1
            continue
        return i + 1 if arg.rsplit("/", 1)[-1] == WAKE_FILE else None
    return None


def _arms(operands, session_re):
    """Whether these wl_wake.py arguments start a timer: a session prefix, or a first word this walk cannot know."""
    if not operands:
        return False
    first = operands[0]
    return bool(session_re.match(first) or _UNKNOWN.search(first))


def _minutes(operands, wl_wake):
    """The sleep in minutes, or None when `--minutes` carries a value that cannot be read here."""
    if "--minutes" not in operands:
        return wl_wake.WAKE_DEFAULT_MIN
    at = operands.index("--minutes")
    try:
        return float(operands[at + 1])
    except (IndexError, ValueError):
        return None


def _timeout(ev):
    """The Bash call's `timeout` as (raw, ms, present): present is False only when the key is missing from tool_input (an explicit null is present, with raw None), and ms is None unless raw is a finite number."""
    doc = ev.doc
    if not isinstance(doc, dict):
        return None, None, False
    tool_input = doc.get("tool_input") or {}
    present = "timeout" in tool_input
    raw = tool_input.get("timeout")
    if raw is None or isinstance(raw, bool):
        return raw, None, present
    try:
        ms = float(raw)
    except (TypeError, ValueError):
        return raw, None, present
    return raw, (ms if math.isfinite(ms) else None), present


def _label(run_):
    return " ".join([run_.name, *run_.argv])[:80]


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if WAKE_FILE not in cmd:
        return hookio.ALLOW
    wl_wake = _wl_wake()
    runs = shellscan.every_run(cmd)
    arm = None
    operands = []
    for run_ in runs:
        start = _operands_start(run_)
        if start is None:
            continue
        if _arms(run_.argv[start:], wl_wake.SESSION_RE):
            arm = run_
            operands = run_.argv[start:]
            break
    if arm is None:
        return hookio.ALLOW

    problems = []
    ops = [t.text for t in shellscan._Lexer(cmd).tokens() if isinstance(t, shellscan._Op)]
    backgrounded = "&" in ops
    if backgrounded:
        problems.append(
            "it is backgrounded with a shell `&`, so the call returns at once and the timer is an "
            "orphan the harness never tracks: its exit wakes nothing"
        )
    others = [r for r in runs if r is not arm]
    if others:
        problems.append(
            "it shares the call with %s, so the task's exit is tied to that work and the Stop hook "
            "reads the whole task as a timer" % ", ".join("`%s`" % _label(r) for r in others[:3])
        )
    if ev.flag("tool_input", "run_in_background") != "true":
        problems.append(
            "run_in_background is not true, so the timer is not a harness background task "
            "(in the foreground the call would block the turn for the whole sleep)"
        )
    minutes = _minutes(operands, wl_wake)
    if minutes is None:
        need = wl_wake.HARNESS_MAX_MS
        why_need = "--minutes cannot be read here, so only the ceiling covers it"
    else:
        need = math.ceil(wl_wake.harness_timeout_ms(minutes))
        why_need = "harness_timeout_ms(%g)" % minutes
    raw, got, present = _timeout(ev)
    if got is None and present:
        problems.append(
            "its timeout is %r, which is not a valid number of milliseconds (the harness kills "
            "the task before the timer fires unless it is at least %d, %s)" % (raw, need, why_need)
        )
    elif got is None or got < need:
        problems.append(
            "its timeout is %s, below %d (%s): the harness kills the task before the timer fires"
            % (
                "absent (the harness default, 1800000)" if got is None else "%d" % got,
                need,
                why_need,
            )
        )
    if not problems:
        return hookio.ALLOW

    me = operands[0] if wl_wake.SESSION_RE.match(operands[0]) else "<me>"
    form = "python3 .claude/hooks/stop/wl_wake.py %s" % me
    if minutes is not None and minutes != wl_wake.WAKE_DEFAULT_MIN:
        form += " --minutes %g" % minutes
    ev.warn_raw(
        "BLOCKED: this wake-timer arm cannot wake the session:\n"
        + "".join("  - %s\n" % p for p in problems)
        + "\n"
        "Arm the timer as its OWN Bash call, nothing else in the command:\n"
        "    command:            %s\n"
        "    run_in_background:  true\n"
        "    timeout:            %d\n"
        "\n"
        "The default sleep is %d minutes and needs timeout %d; with --minutes N the timeout is\n"
        "(N + %d) * 60000 ms, at most %d (wl_wake.harness_timeout_ms). One timer per session:\n"
        "a second start prints ALREADY ARMED and exits.\n"
        % (
            form,
            need,
            wl_wake.WAKE_DEFAULT_MIN,
            wl_wake.harness_timeout_ms(wl_wake.WAKE_DEFAULT_MIN),
            wl_wake.TIMEOUT_MARGIN_MIN,
            wl_wake.HARNESS_MAX_MS,
        )
    )
    return hookio.DENY
