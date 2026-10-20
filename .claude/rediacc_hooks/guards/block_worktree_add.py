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

import ast
import io
import itertools
import os
import re
import shlex
import stat
import tokenize
import zipfile
from typing import Any

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
# `-c`/`-m` closing a bundle of argument-less flags, with the value attached or in the next word.
PYTHON_BUNDLE = re.compile(r"^-[bBdEhiIOPqRsSuvx]*([cm])(.*)$")
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


def _python_program(args):
    """What a Python command line names as its entry: `("c", code)`, `("stdin", None)`, or `("target", target, its own arguments)` for `-m <module>` or a script path. Read only by `_target`, which needs the module NAME and the arguments after it; the program TEXT a run executes is `shellscan.interpreter_program`'s reading (#78afdc0b, see `_program_of` and `_script_verdict`).

    `-c` and `-m` may close a bundle of argument-less flags (`-Ic code`, `-Im mod`) and may carry their value attached (`-cCODE`, `-mrediacc_ci`). No target at all, or `-`, is a program read from stdin.
    """
    i = 0
    while i < len(args):
        word = args[i]
        if word == "-":
            return ("stdin", None)
        if word == "--":
            return ("target", args[i + 1], args[i + 2 :]) if i + 1 < len(args) else ("stdin", None)
        m = PYTHON_BUNDLE.match(word)
        if m:
            value = m.group(2) or (args[i + 1] if i + 1 < len(args) else None)
            rest = args[i + 1 :] if m.group(2) else args[i + 2 :]
            if value is None:
                return ("stdin", None)
            return ("c", value) if m.group(1) == "c" else ("target", value, rest)
        if word in PYTHON_VALUE_OPTIONS:
            i += 2
            continue
        if not word.startswith("-"):
            return ("target", word, args[i + 1 :])
        i += 1
    return ("stdin", None)


def _target(args):
    """(target, the target's own arguments) for a python command line, or (None, []) for `-c`, `-` or no target."""
    program = _python_program(args)
    return (program[1], program[2]) if program[0] == "target" else (None, [])


def runs_port_create(cmd):
    """Does `cmd` run the worktree port's `create`, through any Python spelling? A Python that `npx` or `find -exec` starts runs it just the same (#503f0ba8), so the walk is `shellscan.every_run`."""
    for run_ in shellscan.every_run(cmd):
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


# THE INTERPRETER SAILED PAST ALL THREE ARMS, the way the wrapper sailed past the literal one and the port past the wrapper. Measured 2026-10-09 through chain-head.sh before this arm existed, every one rc 0:
#
#   python3 -c "import subprocess; subprocess.run(['git','worktree','add','/tmp/x'])"
#   python3 -c 'from rediacc_ci.dev import worktree; worktree.main(["create"])'
#   python3 - <<'EOF' (a body running `git worktree add`) EOF
#   python3 - <<< 'import os; os.system("git worktree add /tmp/x")'
#
# `bash -c` / `sh -c` / `bash <<EOF` were already refused (rc 2): shellscan unwraps a SHELL's payload, because a shell payload is shell. A Python, node, perl or ruby program is not, so the walk leaves it as one opaque argument and every arm above saw only an interpreter with a string.
#
# THE BOUNDARY. A program text is refused when it RUNS the banned thing, judged by what the program does with its strings rather than by whether it names them:
#   - a string literal that, read as a shell command, is refused by the arms above (`os.system("git worktree add x")`, `"cd x && git worktree add y"`, `"python3 -m rediacc_ci worktree create"`); a literal in which `git` is not at a command position, such as a sentence, is not;
#   - an argument list (a list or tuple literal, or a call's positional arguments) that, joined into a command, is refused, or that holds `"worktree", "add"` back to back, the shape the port itself hands its git helper;
#   - an in-process call of the port: a program that imports `rediacc_ci.dev.worktree` (or names it for runpy) AND calls `cmd_create` or passes a literal `"create"`, or that reaches the `rediacc_ci` package entry with `"worktree", "create"` back to back.
# Reading the port (`open(".../worktree.py")`, `print(worktree.__doc__)`), `worktree list`, and a `print` of a sentence naming the command stay allowed. A Python body is read with `ast`; a non-Python body, or Python that does not parse, gets the same three questions asked of its quoted literals by regex.
#
# THE EDGE, the same one shellscan draws: a string BUILT at run time (`"work" + "tree"`, base64, a file read and exec'd) is outside a static scanner's reach and is not claimed here.
INTERPRETERS = ("node", "perl", "ruby", "deno", "bun", "tsx")
# The flags that hand each non-Python interpreter its program text as the next word. deno takes its program as the operand of the `eval` subcommand (and `repl --eval`), and bun and tsx read node's spellings; `shellscan.program_parse` holds the deno, bun and tsx grammar.
EVAL_FLAGS = {
    "node": ("-e", "--eval", "-p", "--print"),
    "perl": ("-e", "-E"),
    "ruby": ("-e",),
    "deno": ("eval", "--eval"),
    "bun": ("-e", "--eval", "-p", "--print"),
    "tsx": ("-e", "--eval", "-p", "--print"),
}
# How deep a program may hand another program a shell command (`os.system("python3 -c ...")`) before the rest is left unread. Real payloads nest once or twice; the cap only bounds a pathological input.
MAX_PROGRAM_DEPTH = 4
# The literals a program read by regex is searched for (fa5d11be.4). The three plain shapes, `'...'`, `"..."` and a backtick span, are common to all four languages; a node template literal's `${...}` is read as its raw text, never interpolated.
LITERAL = re.compile(r"'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"|`((?:[^`\\]|\\.)*)`")
# Perl's `q`/`qq`/`qw` and ruby's `%q`/`%Q`/`%w`/`%W`/`%` with a BRACKET delimiter, unnested: `system qw(git worktree add x)` hands the same words as a list literal. A word list's words are joined with spaces, so it reads as the command it spells.
# OUT OF REACH, stated so a green is not read as more: these forms with any other delimiter (`q!...!`, `%w|...|`), nested brackets inside one, heredocs inside the program, and every string built at run time.
QUOTE_LIKE = re.compile(
    r"(?:\bq[qw]?|%[qQwWiI]?)\s*(?:\(([^()]*)\)|\[([^\[\]]*)\]|\{([^{}]*)\}|<([^<>]*)>)"
)
ARGV_WORKTREE_ADD = re.compile(r"""['"]worktree['"]\s*,\s*['"]add['"]""")
ARGV_WORKTREE_CREATE = re.compile(r"""['"]worktree['"]\s*,\s*['"]create['"]""")
TEXT_PORT = re.compile(
    r"rediacc_ci[./]dev[./]worktree|rediacc_ci\.dev\s+import\s+(\([^)]*)?\bworktree\b"
)
TEXT_PORT_CREATE = re.compile(r"""['"]create['"]|\bcmd_create\b""")


def _interpreter_name(name):
    """`python`, one of INTERPRETERS, or None, for a command word."""
    base = name.rsplit("/", 1)[-1]
    if PYTHON.match(base):
        return "python"
    return base if base in INTERPRETERS else None


# OPTION GRAMMAR (fa5d11be.1/.2). An option's VALUE is not the script: `perl -I lib -e '...'` runs the `-e` program, and stopping at `lib` hid it. Perl (measured, 5.40.1) and ruby (`ruby(1)`) bundle single letters (`-wle`); a letter in the first set takes a value, attached (`-Ilib`) or as the next word when it ends the bundle (`-I lib`); one in the second takes only an attached value; an eval letter takes the rest of the word as code (`-esystem(...)`) or the next word.
_NEXT_VALUE = {"perl": frozenset("IMm"), "ruby": frozenset("IrCE")}
_ATTACHED_VALUE = {"perl": frozenset("xidDFC0"), "ruby": frozenset("xFKTW0")}
_EVAL_LETTERS = {"perl": frozenset("eE"), "ruby": frozenset("e")}
# node options that take the next word as their value.
_NODE_VALUE = frozenset(
    (
        "-r",
        "--require",
        "--import",
        "-C",
        "--conditions",
        "--input-type",
        "--loader",
        "--experimental-loader",
        "--title",
    )
)


def _bundle(family, word, following):
    """`(codes, consumed_next)` for one perl/ruby option word: the program texts it carries and whether it took the next word as a value."""
    codes: list[str] = []
    letters = word[1:]
    k = 0
    while k < len(letters):
        letter = letters[k]
        rest = letters[k + 1 :]
        if letter in _EVAL_LETTERS[family]:
            if rest:
                return [*codes, rest], False
            return ([*codes, following] if following is not None else codes), following is not None
        if letter in _NEXT_VALUE[family]:
            return codes, not rest and following is not None
        if letter in _ATTACHED_VALUE[family]:
            return codes, False
        if letter == "l":
            k += 1
            while k < len(letters) and letters[k] in "01234567":
                k += 1
            continue
        k += 1
    return codes, False


# A SCRIPT OPERAND THAT IS THE PROCESS'S OWN STDIN IS A STDIN PROGRAM (review 0d227c80.2). `python3 /dev/stdin <<'EOF'` runs the heredoc exactly as `python3 - <<'EOF'` does, so it is judged by the program text the command line holds, not refused as a descriptor the hook cannot read. Only an absolute spelling counts: a relative word that resolves to /dev/stdin stays a descriptor `_unread_reason` refuses, so the two readers never disagree about which run reads stdin. /dev/fd/N for any other N is still a descriptor.
# The spelling is resolved as `shellscan._script_path` resolves a script (review c5f0fd12.3): a `..` after a directory symlink is the kernel's step, so `<link>/../../dev/stdin`, which `os.path.normpath` turned into /dev/stdin, names the file the kernel opens and is read as a script (rc 0 at bd4ead963 with `git worktree add` in it).
# The procfs spelling is a RECOGNISED path, never read (the pid-wait-anchor precedent in .ci/rediacc_ci/quality/hook_cross_os.py): the root is named once, from REDIACC_WORKTREE_STDIN_PROCFS, and STDIN_PATHS and both stdin-touch patterns below are built from it, so a machine whose procfs is not at /proc moves all three together.
PROCFS_ENV = "REDIACC_WORKTREE_STDIN_PROCFS"
PROCFS_ROOT = (os.environ.get(PROCFS_ENV) or "/proc").rstrip("/") or "/proc"
PROC_STDIN = PROCFS_ROOT + "/self/fd/0"
STDIN_PATHS = ("/dev/stdin", "/dev/fd/0", PROC_STDIN)


def _stdin_path(word):
    return word.startswith("/") and shellscan._script_path(word, None, None) in STDIN_PATHS


def _eval_program(family, args):
    """`("c", code)`, `("stdin", None)` or `("file", None)` for a node/perl/ruby argv. Perl and ruby bundle `-e` (`-ne`, `-le`, `-esystem(...)`) and take several, which run as one program. A script operand naming the process's own stdin (`_stdin_path`) is "stdin"."""
    codes: list[str] = []
    i = 0
    while i < len(args):
        word = args[i]
        following = args[i + 1] if i + 1 < len(args) else None
        if word == "--":
            if codes or following is None:
                break
            return ("stdin", None) if _stdin_path(following) else ("file", None)
        if word == "-":
            break
        if not word.startswith("-"):
            if codes:
                return ("c", "\n".join(codes))
            return ("stdin", None) if _stdin_path(word) else ("file", None)
        if family == "node":
            if word in EVAL_FLAGS["node"]:
                if following is not None:
                    codes.append(following)
                i += 2
                continue
            if word.split("=", 1)[0] in ("--eval", "--print") and "=" in word:
                codes.append(word.split("=", 1)[1])
            i += 2 if word in _NODE_VALUE else 1
            continue
        if word.startswith("--"):
            i += 1
            continue
        found, consumed = _bundle(family, word, following)
        codes.extend(found)
        i += 2 if consumed else 1
    if codes:
        return ("c", "\n".join(codes))
    return ("stdin", None)


def _program_of(name, args):
    """`(family, mode, code)` for an interpreter command, or None when `name` is no interpreter. `mode` is "c" (the code is in argv), "stdin" (the code arrives on stdin) or anything else (a file or module, which the arms above judge). `bun exec` hands a shell command line, which is family "shell" in mode "c"."""
    family = _interpreter_name(name)
    if family is None:
        if name.rsplit("/", 1)[-1] == "uv" and args[:1] == ["run"]:
            for k, word in enumerate(args[1:], 1):
                if PYTHON.match(word.rsplit("/", 1)[-1]):
                    return _program_of(word, args[k + 1 :])
        return None
    if family in shellscan.RUNTIMES:
        # The walk every guard shares (`shellscan.program_parse`, #a2599946).
        kind, value = shellscan.program_parse(family, args)
        if kind == "shell":
            return ("shell", "c", value)
        if kind == "file" and _stdin_path(value):
            kind = "stdin"
        mode = {"inline": "c", "stdin": "stdin"}.get(kind, kind)
        return (family, mode, value if mode == "c" else None)
    if family == "python":
        # The option parse `shellscan.interpreter_program` reads with (#78afdc0b): the private one this replaced stepped over `--check-hash-based-pycs` alone, read its value as the script and never saw the `-c` after it.
        kind, code = shellscan.program_parse(name.rsplit("/", 1)[-1], args)
        if kind == "file" and _stdin_path(code):
            kind = "stdin"
        mode = {"inline": "c", "stdin": "stdin"}.get(kind, kind)
        return (family, mode, code if mode == "c" else None)
    mode, code = _eval_program(family, args)
    return (family, mode, code)


# A FILE ON STDIN IS A SCRIPT ON DISK (0d227c80 sibling). Reading only the text the command line holds let `python3 - < p.py`, `cat p.py | python3 -`, `{ python3 -; } < p.py` and `bash < x.sh` run a file holding `git worktree add` with rc 0 (2026-10-15) while `python3 p.py` was refused. Each file a stdin program is read from is named, and `_redirect_verdict` reads it under the rules a script run by path is read by.
STDIN_REDIRECTS = ("<", "<>")

# A STDIN THE HOOK CANNOT READ IS REFUSED, NOT PASSED (#faca6bd7). Two spellings ran a program holding `git worktree add` with rc 0 at c5f0fd121: a duplicated descriptor (`python3 - <&3 3< p.py`, `exec 3<p.py; python3 - <&3`), and a pipe from a producer whose output the command line does not hold (`git show HEAD:p.py | python3 -`, `curl -s URL | python3 -`, `some_tool | bash`). A `<&N` is followed to whatever opens N in the same command line, and a stdin fed by anything but a heredoc, a here-string, a file, `echo`, `printf` or `cat` of one of those is an "unread" source naming its producer.
# A STDIN PROGRAM is judged this way, and so is the stdin of an inline program that can EVALUATE what it reads (13fdcda2.2): `git show HEAD:p.py | python3 -c 'import sys; exec(sys.stdin.read())'` ran the piped program with rc 0 at 13fdcda23. An inline program (`-c`, `-e`, `deno eval`, `bun -e`) whose text touches stdin (`_STDIN_TOUCH`) and names anything that could run text as code or as a command (`_EVALUATOR`) has its stdin read as a program: its text judged both in the program's language and as a command line, a file judged as a script, an unread producer refused.
# FAIL CLOSED BY BREADTH. No list of evaluators is complete (the reason a script naming the phrase is refused outright), so `_EVALUATOR` errs wide: dynamic reaches (`getattr`, `globals`, `Reflect`, `send`), process launchers and module loaders by a non-literal name all count. Perl and ruby read stdin implicitly (`-n`, `-p`, `gets`, `<>`), so for them any evaluator suffices. A program that reads stdin and evaluates nothing (`print(sys.stdin.read())`, `process.stdin.pipe(process.stdout)`, `perl -ne 'print'`) still takes the pipe as data, as `python3 script.py` and `-m` do.
# OUT OF REACH, stated: a child process that inherits the stdin and reads it as its program (`python3 -c 'import os; os.system("sh")'` behind a pipe), and an evaluator spelled from pieces this text does not hold.
STDIN_DEPTH = 16
DUP_TARGET = re.compile(r"^(\d+)-?$")
_PY_STRING_PARTS = tuple(
    getattr(tokenize, name)
    for name in ("FSTRING_MIDDLE", "TSTRING_MIDDLE")
    if hasattr(tokenize, name)
)
_JS_FAMILIES = ("node", "deno", "bun", "tsx")
# A DESCRIPTOR HELD IN A NAME IS STDIN UNTIL SHOWN OTHERWISE (review db1e9409.1). `const fd=0; eval(require("fs").readFileSync(fd,"utf8"))` read the pipe and ran it with rc 0 at bd4ead963: the touch list held `fd` bound to 0 for python alone, and no list of names is complete. So a read that takes a descriptor or a path, called with a first argument that is not a literal (a name, an expression, `null` with `{fd: 0}`), counts as touching stdin, in both languages.
# That over-reads on purpose: such a program is only judged when it also names an evaluator and is fed something, and then its stdin is read as a program, which refuses an unreadable producer. A read given a literal path (`readFileSync("x.json")`, `open('x')`) is not a touch.
_STDIN_TOUCH = {
    "python": re.compile(
        r"stdin|/dev/(?:stdin|fd/0)|"
        + re.escape(PROC_STDIN)
        + r"|fileinput|\binput\s*\(|\(\s*(?:\w+\s*=\s*)?0\s*[,)]|\bfd\s*=\s*0\b"
        r"""|\b(?:os\s*\.\s*read|fdopen|FileIO|open)\s*\(\s*(?![)\s'"]|[rRbBuUfF]{1,2}['"])"""
    ),
    "js": re.compile(
        r"stdin|/dev/(?:stdin|fd/0)|"
        + re.escape(PROC_STDIN)
        + r"|readline|\(\s*0\s*[,)]|\bfd\s*:\s*0\b"
        r"""|\b(?:readFileSync|readFile|readSync|read|createReadStream|readTextFileSync|readTextFile|readAll|readAllSync|file|open|openSync)\s*\(\s*(?![)\s'"`])"""
    ),
}
_EVALUATOR = {
    "python": re.compile(
        r"\b(?:exec|eval|compile|execfile|runpy|run_path|run_module|exec_module|__import__|importlib|getattr|globals|locals|vars|builtins|__builtins__|__dict__|system|popen|spawn\w*|exec[lv]p?e?|subprocess|Popen|pty|code|Interactive\w*|pickle|marshal|types|ctypes|cffi|breakpoint|pdb|timeit|doctest|zipimport|operator|methodcaller|partial)\b"
    ),
    "js": re.compile(
        r"\b(?:eval|Function|vm|runIn\w*|compileFunction|SourceTextModule|Script|child_process|exec\w*|spawn\w*|fork|Command|Worker|Transpiler|globalThis|Reflect|constructor|WebAssembly)\b|\b(?:Deno|Bun)\s*\.\s*run\b|\bBun\s*\.\s*\$|\$\s*`|\b(?:require|import)\s*\(\s*[^'\"`\s)]"
    ),
    "perl": re.compile(
        r"\b(?:eval|system|exec|qx|open|fork|syscall)\b|`|\bdo\s*[\$\"'(]|\brequire\s*[\$(]|[/}|!#][msixpodualngcr]*e[msixpodualngcr]*\b"
    ),
    "ruby": re.compile(
        r"\b(?:eval|instance_eval|class_eval|module_eval|instance_exec|binding|send|__send__|public_send|method|system|exec|spawn|fork|syscall|load|Open3|popen\w*|Kernel|ObjectSpace|const_get|define_method|RubyVM|ERB|open)\b|`|%x|\brequire(?:_relative)?\s*\(?\s*[^'\"\s(]"
    ),
}


# A string literal that spells a module or a lookup able to run a child on the inherited stdin stays visible to the evaluator list: `sys.modules["subprocess"].run(["sh"])` names no evaluator outside its strings. `sys.modules` itself counts, the over-reading direction.
_PY_MODULE_REACH = re.compile(
    r"""\bmodules\b|['"](?:subprocess|pty|ctypes|cffi|pickle|marshal|builtins|importlib|runpy|zipimport|pdb|doctest|timeit)['"]"""
)


def _python_code_view(code):
    """`code` with its comments and string literals blanked, so the evaluator list reads names and calls and not the words in a JSON key or a message. A program that does not tokenize is returned whole (fail closed: every word counts)."""
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(code).readline))
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return code
    out = []
    for tok in toks:
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING:
            # An f-string carries code in its {...} parts, and before Python 3.12 it is ONE STRING token, so blanking it would hide `f"{eval(...)}"` (review c032227c.1). Keep any string whose prefix has an f, so every word in it counts (fail closed).
            prefix = tok.string[: len(tok.string) - len(tok.string.lstrip("rRbBuUfF"))]
            out.append(tok.string if "f" in prefix.lower() else '""')
        elif tok.type in _PY_STRING_PARTS:
            continue
        else:
            out.append(tok.string)
    return " ".join(out)


def _evaluates_stdin(family, code):
    """Can the inline program `code` read its stdin and run what it reads, as code or as a command line? Errs towards yes (see `_EVALUATOR`)."""
    key = "js" if family in _JS_FAMILIES else family
    evaluator = _EVALUATOR.get(key)
    if evaluator is None:
        return False
    # A WORD IN A STRING OR A COMMENT RUNS NOTHING (#14aadab3): `curl URL | python3 -c 'import json,sys; print(json.load(sys.stdin).get("code"))'` was refused because the key `"code"` is an evaluator word. The python evaluator list is read over the program with its comments and string literals blanked (`_python_code_view`); a string that names a module able to run a child on the inherited stdin stays visible.
    if key == "python":
        if not (evaluator.search(_python_code_view(code)) or _PY_MODULE_REACH.search(code)):
            return False
    elif not evaluator.search(code):
        return False
    touch = _STDIN_TOUCH.get(key)
    return touch is None or bool(touch.search(code))


def _stdin_ctx(redirs=(), upstream=None, outer=()):
    """What a command's stdin is when its own redirects leave it alone: `redirs`, the redirects of every group around it; `upstream`, `(stage, ctx)` for the pipeline stage feeding it; `outer`, the sources a shell running this command line as `-c` handed it (`_stdin_sources`)."""
    return (tuple(redirs), upstream, tuple(outer))


def interpreter_programs(cmd, depth=0, files=None, stdin=()):
    """Every `(family, program text)` `cmd` hands an interpreter: `python3 -c`, `node -e`, `perl -e`, `ruby -e`, and each of them reading a heredoc, a here-string or a piped `cat`/`echo` as its program.

    It walks the same token structure `shellscan._analyse` walks (subshells, brace groups, pipelines, `$(...)`, the prefix commands `_strip_prefixes` drops), and descends into a shell's own payload (`sh -c`, `bash <<EOF`, `eval`), because `sh -c "python3 - <<EOF ..."` is the same program one level down. `_Run` records argv but not redirects, which is why this cannot read `_analyse(cmd).runs` alone: a heredoc is a redirect.

    A group's stdin (`{ ...; } < f`, `(...) <<EOF`, `cat f | { ...; }`) is the stdin of the first command of each pipeline inside it, and a shell's stdin (`git show | sh -c 'python3 -'`) is the stdin `stdin` hands the first commands of its payload. When `files` is a list, each `(family, kind, value)` a stdin program reads that is not text the command line holds is appended to it, `family` being "shell" for a shell reading its script on stdin: `("file", word)` for a file, read by `_redirect_verdict`, and `("unread", producer)` for a source the hook cannot read.
    """
    out: list[tuple[str, str]] = []
    if depth > MAX_PROGRAM_DEPTH or cmd == "":
        return out
    lexer = shellscan._Lexer(cmd)
    toks = lexer.tokens()
    tree = shellscan._parse(toks)

    def heredoc_text(hd):
        return lexer.src[hd.body_start : hd.body_end]

    # `exec 3< p.py` opens a descriptor for every later command of the same shell. The walk does not order commands, so every redirect-only `exec` in the command line counts, the over-reading direction.
    exec_redirs: list[Any] = []

    def collect_exec(items):
        for item in items:
            if item[0] == "sep":
                continue
            for stage in item[1]:
                if stage[0] in ("sub", "brace"):
                    collect_exec(stage[1])
                    continue
                raw = [t for t in stage[1] if isinstance(t, shellscan._Word)]
                words, _ = shellscan._strip_prefixes(raw)
                if not words and "exec" in (shellscan._word_value(w) for w in raw):
                    exec_redirs.extend(t for t in stage[1] if isinstance(t, shellscan._Redir))

    collect_exec(tree)

    def opened(redir, redirs, seen, level):
        """The sources a read of the descriptor `redir` opens carries."""
        hd = redir.heredoc
        if hd is not None:
            return [("text", heredoc_text(hd))] if hd.body_start is not None else []
        if redir.target is None:
            return [("unread", "descriptor %s, opened with no target" % redir.fd)]
        target = shellscan._word_value(redir.target)
        if redir.op == "<<<":
            return [("text", target)]
        if redir.op in STDIN_REDIRECTS:
            return [("inherit", None)] if _stdin_path(target) else [("file", target)]
        if redir.op == "<&":
            return duplicated(target, redirs, seen, level)
        return [("unread", "descriptor %s, opened for writing" % redir.fd)]

    def duplicated(target, redirs, seen, level):
        """The sources `<&target` reads: nothing for `<&-`, the command's own stdin ("inherit") for `<&0`, and otherwise what the command line opens on that descriptor. One it does not open is supplied by the shell, so it is "unread"."""
        if target == "-":
            return []
        found = DUP_TARGET.match(target)
        if not found:
            return [("unread", "a descriptor named by `%s`" % target)]
        fd = found.group(1)
        if fd == "0":
            return [("inherit", None)]
        if fd in seen or level > STDIN_DEPTH:
            return [("unread", "descriptor %s, duplicated in a cycle" % fd)]
        openers = [r for r in list(redirs) + exec_redirs if r.fd == fd]
        if not openers:
            return [("unread", "descriptor %s, which the command line does not open" % fd)]
        got: list[tuple[str, Any]] = []
        for redir in openers:
            got.extend(opened(redir, redirs, seen | {fd}, level + 1))
        return got

    def stdin_sources(own, ctx, level=0, piped=True):
        """`(kind, value)` for everything a command with redirects `own` reads on stdin under `ctx`: "text" the command line holds, a "file" word, or an "unread" producer. Every heredoc and here-string counts whatever its descriptor and every stdin redirect counts, the over-reading direction; the pipe or group stdin counts unless a redirect replaces it, so a pipe into `python3 - < f` is not read as the program."""
        if level > STDIN_DEPTH:
            return [("unread", "a pipeline nested deeper than the hook follows")]
        redirs = list(own) + list(ctx[0])
        got: list[tuple[str, Any]] = []
        replaced = False
        for redir in redirs:
            on_stdin = redir.fd in (None, "0")
            if redir.heredoc is not None or redir.op == "<<<":
                got.extend(opened(redir, redirs, frozenset(), level))
                replaced = replaced or on_stdin
            elif on_stdin and redir.op in STDIN_REDIRECTS and redir.target is not None:
                target = shellscan._word_value(redir.target)
                # `< /dev/stdin` reopens the stdin the command already has (13fdcda2.1): the pipe or group stdin still feeds it, so it is not replaced.
                if not _stdin_path(target):
                    got.append(("file", target))
                    replaced = True
            elif on_stdin and redir.op == "<&" and redir.target is not None:
                dup = duplicated(shellscan._word_value(redir.target), redirs, frozenset(), level)
                replaced = replaced or ("inherit", None) not in dup
                got.extend(s for s in dup if s[0] != "inherit")
        if piped and not replaced:
            got.extend(pipe_sources(ctx, level))
        return got

    def pipe_sources(ctx, level):
        """What the pipe, the group stdin or the shell's stdin hands a command whose own redirects leave stdin alone."""
        if ctx[1] is None:
            return list(ctx[2])
        stage, up = ctx[1]
        if stage[0] != "cmd":
            return [("unread", "a subshell or brace group")]
        own = [t for t in stage[1] if isinstance(t, shellscan._Redir)]
        words, _ = shellscan._strip_prefixes(
            [t for t in stage[1] if isinstance(t, shellscan._Word)]
        )
        if not words:
            return []
        argv = [shellscan._word_value(w) for w in words]
        feeder = argv[0].rsplit("/", 1)[-1]
        if feeder in ("echo", "printf"):
            args = argv[1:]
            while args and feeder == "echo" and re.match(r"^-[neE]+$", args[0]):
                args = args[1:]
            return [("text", " ".join(args))]
        if feeder == "cat":
            names: list[str] = []
            reads_stdin = False
            operands = False
            for word in argv[1:]:
                if word == "--" and not operands:
                    operands = True
                elif word == "-" or _stdin_path(word):
                    # `cat /dev/stdin` passes its own stdin through as `cat -` does (13fdcda2.1).
                    reads_stdin = True
                elif operands or not word.startswith("-"):
                    names.append(word)
            got = [("file", name) for name in names]
            return got + stdin_sources(own, up, level + 1, piped=reads_stdin or not names)
        return [("unread", "`%s`" % _shorten(" ".join(argv)))]

    def take(family, ctx_own, ctx, evaluated=False):
        """Read what a stdin program reads. `evaluated` is an inline program's stdin (`_evaluates_stdin`), whose text may be run as code or as a command line, so it is judged as both."""
        for kind, value in stdin_sources(ctx_own, ctx):
            if kind == "text":
                if family == "shell":
                    out.extend(interpreter_programs(value, depth + 1, files))
                else:
                    out.append((family, value))
                    if evaluated:
                        out.append(("shell", value))
            elif files is not None:
                files.append((family, kind, value))

    def words_subs(parts):
        for part in parts:
            if part.sub is not None:
                walk(shellscan._parse(part.sub), _stdin_ctx())
            if part.parts:
                words_subs(part.parts)

    def element(stage, ctx):
        if stage[0] in ("sub", "brace"):
            own = [
                t for t in (stage[2] if len(stage) > 2 else []) if isinstance(t, shellscan._Redir)
            ]
            walk(stage[1], _stdin_ctx(own + list(ctx[0]), ctx[1], ctx[2]))
            return
        words = [t for t in stage[1] if isinstance(t, shellscan._Word)]
        own = [t for t in stage[1] if isinstance(t, shellscan._Redir)]
        for word in words:
            words_subs(word.parts)
        words, _ = shellscan._strip_prefixes(words)
        if not words:
            return
        name = shellscan._word_value(words[0])
        argv = [shellscan._word_value(w) for w in words[1:]]
        base = name.rsplit("/", 1)[-1]
        program = _program_of(name, argv)
        if program is not None:
            family, mode, code = program
            if mode == "c" and code is not None:
                out.append((family, code))
                if family != "shell" and _evaluates_stdin(family, code):
                    take(family, own, ctx, evaluated=True)
            elif mode == "stdin":
                take(family, own, ctx)
        elif base in shellscan.SHELL_NAMES:
            mode, payload = shellscan._shell_payload(argv)
            if mode == "c" and payload is not None:
                out.extend(interpreter_programs(payload, depth + 1, files, stdin_sources(own, ctx)))
            elif mode == "stdin":
                take("shell", own, ctx)
        elif base == "eval":
            out.extend(
                interpreter_programs(" ".join(argv), depth + 1, files, stdin_sources(own, ctx))
            )
        else:
            # A LAUNCHER'S COMMAND (#503f0ba8): `find . -exec python3 -c '...' \;` and `npx -c '...'` hand an interpreter its program one level down, so the launched command is walked as a command line of its own, quoted back so its program text stays one word.
            for how, launched in shellscan._launched(base, argv):
                src = launched if how == "text" else shellscan._quote_argv(launched)
                out.extend(interpreter_programs(src, depth + 1, files))

    def walk(items, ctx):
        for item in items:
            if item[0] == "sep":
                continue
            stages = item[1]
            prev = ctx
            for pos, stage in enumerate(stages):
                here = ctx if pos == 0 else _stdin_ctx((), (stages[pos - 1], prev))
                element(stage, here)
                prev = here

    walk(tree, _stdin_ctx((), None, stdin))
    return out


def _shorten(text, limit=80):
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _const_str(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
        value = node.value
        return value.decode("utf-8", "replace") if isinstance(value, bytes) else value
    return None


def _sequences(tree):
    """Every argument list a Python program writes down: list, tuple and set literals, and each call's positional arguments. A non-literal element is `None`."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            yield [_const_str(e) for e in node.elts]
        elif isinstance(node, ast.Call) and node.args:
            yield [_const_str(a) for a in node.args]


def _adjacent(seq, first, second):
    return any(a == first and b == second for a, b in itertools.pairwise(seq))


def _joined(seq):
    """An argv list as the shell command it spells; a non-literal element stands in as one opaque word."""
    return " ".join(shlex.quote(e) if e is not None else "X" for e in seq)


# A SCRIPT RUN BY PATH THAT NAMES THE PHRASE IS REFUSED, WHATEVER IT DOES WITH IT. A program the command line itself holds (`-c`, a heredoc, a here-string) is judged by every string it carries, because the command line IS the program. A script read from disk (`python3 x.py`, `node x.js`, `./x.py` by its shebang, `bash x.sh`, `source x.sh`, `./x.sh`) is refused when its text names `worktree` together with `add` or `create` (`_names_phrase`), and otherwise judged as a `-c` program is.
#
# NO QUESTION OF WHETHER THE FILE CAN RUN ANYTHING. An earlier reading allowed a file that mentioned the phrase when a deny list of exec primitives, dynamic reaches and code-running modules found no way for it to run a command. Every round of review found a stdlib road the list missed (`operator.methodcaller("system", ...)(os)`, `timeit.timeit`, `doctest`, `zipimport`, `functools.partial`), so the list could not be completed and the guard failed open on whatever it lacked. A test that cannot be completed is not a guard.
#
# THE COST, stated: a script that only lists the phrase as data (a guard's own test table) is refused while it is untracked or differs from HEAD. A tracked script unchanged from HEAD is reviewed code and is not read at all (`shellscan._tracked_unchanged`), so the repository's own test files still run; an edited one is read again, and the operator's `!` prefix runs it. OUT OF REACH: a script that spells neither word, building `worktree`, `add` or `create` from pieces at run time.
PHRASE_VERB = re.compile(r"(?<![a-z])(?:add|create)(?![a-z])")
# Quotes and backslashes go before the search, so an adjacent-literal split (`'work''tree'`, `"a""dd"`, `work\tree`) reads as the word it spells.
PHRASE_NOISE = re.compile(r"[\"'`\\]")


def _names_phrase(text):
    """Does a script's text name `worktree` together with `add` or `create`, in any case, anywhere in the file?"""
    bare = PHRASE_NOISE.sub("", text).lower()
    return "worktree" in bare and bool(PHRASE_VERB.search(bare))


# The word after `bash`/`sh` options that is the script it runs: what `shellscan._shell_payload` calls a "file" operand.
SHELL_VALUE_LONG = ("--rcfile", "--init-file")
SOURCE_WORDS = (".", "source")


def _shell_operand(argv):
    k = 0
    while k < len(argv):
        arg = argv[k]
        if arg in ("--", "-"):
            k += 1
            break
        if arg.startswith("--"):
            k += 2 if arg in SHELL_VALUE_LONG else 1
            continue
        if len(arg) > 1 and arg[0] in "-+":
            k += 2 if ("o" in arg[1:] or "O" in arg[1:]) else 1
            continue
        break
    return argv[k] if k < len(argv) else None


def _noexec(argv):
    """Does a shell's option list turn on `noexec` (`bash -n x.sh`, `-xn`, `-o noexec`) before its operand? Such a shell parses its script and runs none of it, `set +n` inside included, so it is a syntax check, not a run (#bfe569ca). Options are walked as `_shell_operand` walks them, and the LAST setting wins: `bash -n +n x.sh` and `-o noexec +o noexec` run the script (measured, bash 5.3.9). `-i` does not undo it for a script operand: `bash -in x.sh`, `-i -n` and `-i -o noexec` ran nothing in the same measurement (review 02425af7.1)."""
    on = False
    k = 0
    while k < len(argv):
        arg = argv[k]
        if arg in ("--", "-"):
            break
        if arg.startswith("--"):
            k += 2 if arg in SHELL_VALUE_LONG else 1
            continue
        if len(arg) > 1 and arg[0] in "-+":
            flags = arg[1:]
            if "n" in flags:
                on = arg[0] == "-"
            takes = "o" in flags or "O" in flags
            if "o" in flags and k + 1 < len(argv) and argv[k + 1] == "noexec":
                on = arg[0] == "-"
            k += 2 if takes else 1
            continue
        break
    return on


def _shell_script_path(run_, cmd, cwd):
    """The script a shell run reads by path: `bash x.sh`, `source x.sh`, `. x.sh`, or `./x.sh` run directly whose shebang names no interpreter `shellscan.interpreter_program` reads (a shell, or none). None for anything else."""
    base = run_.name.rsplit("/", 1)[-1]
    argv = list(run_.argv)
    if base.startswith(shellscan.INTERPRETER_NAMES):
        return None
    if base in shellscan.SHELL_NAMES:
        if _noexec(argv):
            return None
        return _shell_operand(argv) if shellscan._shell_payload(argv)[0] == "file" else None
    if base in SOURCE_WORDS:
        return argv[0] if argv else None
    if "/" in run_.name and shellscan.shebang_interpreter(run_, cwd, cmd) is None:
        return run_.name
    return None


def _shell_script(run_, cmd, cwd):
    """`(text, kind)` for a shell script run by path, read under the rules `shellscan.interpreter_program` reads an interpreter's script by: what an earlier run of the same command wrote into it, else the file on disk, a tracked and unchanged one exempt. A file that does not exist, and a compiled binary, are `(None, None)`. The phrase is searched before git is asked whether the file is tracked, so a script that does not name it costs no `git status`."""
    path = _shell_script_path(run_, cmd, cwd)
    if not path:
        return None, None
    target = shellscan._script_path(path, run_.cwd, cwd)
    written = shellscan._written_scripts(cmd, run_, cwd)
    if target in written:
        return (written[target], "file") if written[target] is not None else (None, "unjudgeable")
    try:
        # A named pipe or device is not a script, and opening one could block the hook.
        if not os.path.isfile(target):
            return None, None
        with open(target, "rb") as handle:
            if handle.read(4) == b"\x7fELF":
                return None, None
            if os.path.getsize(target) > shellscan._SCRIPT_MAX:
                return (
                    (None, None) if shellscan._tracked_unchanged(target) else (None, "unjudgeable")
                )
            handle.seek(0)
            text = handle.read().decode("utf-8", "replace")
    except OSError:
        return None, None
    if not (_names_phrase(text) or _could_spell(text.lower())) or shellscan._tracked_unchanged(
        target
    ):
        return None, None
    return text, "file"


# A SCRIPT THE HOOK CANNOT READ IN FULL IS REFUSED, NOT PASSED. The readers above judge a script by its text and skip what they cannot open: a shell script or interpreter program larger than `shellscan._SCRIPT_MAX`, one the hook may not read, a directory an interpreter runs (`python3 pkg` runs `pkg/__main__.py`), a zip archive python runs, and a program the shell hands over as a descriptor (`python3 <(...)`, `bash /dev/fd/3 3<x`). Each was allowed (rc 0, 2026-10-15) with `git worktree add` inside. `_unread_reason` names why such a script cannot be read, and the run is refused unless the script is tracked and unchanged from HEAD. A path that does not exist still fails open (the interpreter fails on it), and a compiled program run directly or handed to a shell is not a script: bash refuses an ELF file and one whose first line holds a NUL, and a binary run directly is a program like any on PATH.
DESCRIPTOR_PATH = re.compile(r"^/dev/(?:stdin|fd/\d+)$|^/proc/[^/]+/fd/\d+$")


def _script_operand(run_, cmd, cwd):
    """The path `run_` reads its program from: an interpreter's script operand, a shell's script (`_shell_script_path`), or the command word of a run by path. None for anything else."""
    base = run_.name.rsplit("/", 1)[-1]
    if base.startswith(shellscan.INTERPRETER_NAMES):
        kind, value = shellscan.program_parse(base, run_.argv)
        return value if kind in ("file", "remote") else None
    if base in shellscan.SHELL_NAMES or base in SOURCE_WORDS:
        return _shell_script_path(run_, cmd, cwd)
    return run_.name if "/" in run_.name else None


def _binary(head):
    return head.startswith(b"\x7fELF") or b"\0" in head.split(b"\n", 1)[0]


def _unread_reason(run_, cmd, cwd):
    """Why the script `run_` runs by path cannot be read in full, or None when it can, is a compiled program, does not exist, is what an earlier run of `cmd` writes (judged by that write), or is tracked and unchanged from HEAD."""
    path = _script_operand(run_, cmd, cwd)
    if not path:
        return None
    # A NUL IN THE PATH FAILS CLOSED (review 0d227c80.1). `os.stat` raises ValueError for it, which escaped this function; the dispatcher counts a crash as no decision, so the run was allowed. Failing open is wrong too: bash cuts a word at its first NUL (`printf '%s|' $'ab\0cd'` prints `ab|`, measured on bash 5.2), so `python3 $'p.py\0x'` runs p.py while the hook would stat a path that names no file. The hook cannot know which file runs, so the run is refused; no script path a person types holds a NUL.
    if "\0" in path:
        return "a path holding a NUL byte"
    if path.startswith(("<(", ">(")):
        return "a process substitution"
    base = run_.name.rsplit("/", 1)[-1]
    if (
        base.startswith(shellscan.INTERPRETER_NAMES)
        and shellscan.program_parse(base, run_.argv)[0] == "remote"
    ):
        # `deno run https://...` fetches its program at run time, so no text of it is here to read.
        return "a remote module"
    if _reads_stdin_operand(run_):
        return None
    target = shellscan._script_path(path, run_.cwd, cwd)
    if target in shellscan._written_scripts(cmd, run_, cwd):
        return None
    interpreter = run_.name.rsplit("/", 1)[-1].startswith(shellscan.INTERPRETER_NAMES)
    reason = None
    try:
        if DESCRIPTOR_PATH.match(target):
            return "a descriptor the shell supplies"
        mode = os.stat(target).st_mode
        if stat.S_ISDIR(mode):
            # A DIRECTORY PERL IS HANDED RUNS NOTHING (#faca6bd7). Python runs `pkg/__main__.py` and node runs `dir/index.js` (measured, node v24.21.0), but perl stops with `Can't open perl script "/tmp": Is a directory` and rc 25 (measured, perl 5.40.1), so `perl -x /tmp -e 'print 1'`, the pinned hookcases control, is not a script the hook failed to read. Ruby was not measurable here and stays refused.
            perl = run_.name.rsplit("/", 1)[-1].startswith("perl")
            reason = "a directory" if interpreter and not perl else None
        elif not stat.S_ISREG(mode):
            reason = None if os.path.realpath(target) == os.devnull else "not a regular file"
        else:
            with open(target, "rb") as handle:
                head = handle.read(80)
            if interpreter and zipfile.is_zipfile(target):
                reason = "a zip archive"
            elif not interpreter and _binary(head):
                reason = None
            elif os.path.getsize(target) > shellscan._SCRIPT_MAX:
                reason = "larger than the %d bytes the hook reads" % shellscan._SCRIPT_MAX
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        reason = "unreadable (%s)" % (getattr(exc, "strerror", None) or type(exc).__name__)
    if reason is None or _tracked_unchanged(target):
        return None
    return reason


def _tracked_unchanged(target):
    """`shellscan._tracked_unchanged`, False when the file cannot be asked about."""
    try:
        return shellscan._tracked_unchanged(target)
    except (OSError, ValueError):
        return False


def _reads_stdin_operand(run_):
    """Is `run_` an interpreter whose script operand is its own stdin (`_stdin_path`)? Its program is the text `interpreter_programs` hands `_program_verdict`, so the by-path readers skip it."""
    if not run_.name.rsplit("/", 1)[-1].startswith(shellscan.INTERPRETER_NAMES):
        return False
    kind, value = shellscan.program_parse(run_.name.rsplit("/", 1)[-1], run_.argv)
    if kind != "file" or not _stdin_path(value):
        return False
    # Both readers must agree: the operand is skipped only when `interpreter_programs` reads this run's stdin as its program.
    program = _program_of(run_.name, list(run_.argv))
    return program is not None and program[1] == "stdin"


def _stdin_file(target):
    """`(reason, text)` for a file a stdin program is read from: `reason` names why it cannot be read in full (as `_unread_reason` does), `text` is its content, and both are None for a file that does not exist, a directory (nothing is read from it), and /dev/null."""
    if DESCRIPTOR_PATH.match(target):
        return "a descriptor the shell supplies", None
    try:
        mode = os.stat(target).st_mode
        if stat.S_ISDIR(mode):
            return None, None
        if not stat.S_ISREG(mode):
            if os.path.realpath(target) == os.devnull:
                return None, None
            return "not a regular file", None
        if os.path.getsize(target) > shellscan._SCRIPT_MAX:
            return "larger than the %d bytes the hook reads" % shellscan._SCRIPT_MAX, None
        with open(target, "rb") as handle:
            return None, handle.read().decode("utf-8", "replace")
    except FileNotFoundError:
        return None, None
    except (OSError, ValueError) as exc:
        return "unreadable (%s)" % (getattr(exc, "strerror", None) or type(exc).__name__), None


def _redirect_verdict(family, word, cmd, cwd, depth):
    """The arm a file fed to a stdin program trips (a "file" source `interpreter_programs` hands back), read under the rules a script run by path is read by: what an earlier run of `cmd` writes into it, and the file on disk, are both judged as `_file_verdict` judges a script; one that cannot be read in full is "unread"; a tracked file unchanged from HEAD is reviewed code and passes; one that does not exist fails open. A relative word is resolved in every directory a run of `cmd` executes in, the over-reading direction, because the walk that finds the redirect does not follow `cd`."""
    if "\0" in word or word.startswith(("<(", ">(")):
        return "unread"
    if _stdin_path(word):
        # The shell's own stdin: no file the hook can name, the same as no redirect at all.
        return None
    written = shellscan._written_scripts(cmd, None, cwd)
    dirs = {None} | {run_.cwd for run_ in shellscan.every_run(cmd)}
    for run_cwd in sorted(dirs, key=lambda d: d or ""):
        target = shellscan._script_path(word, run_cwd, cwd)
        if target in written:
            if written[target] is None:
                if _could_spell(cmd):
                    return "unjudgeable"
            else:
                verdict = _file_verdict(family, written[target], depth + 1)
                if verdict:
                    return verdict
        reason, text = _stdin_file(target)
        verdict = "unread" if reason else (_file_verdict(family, text, depth + 1) if text else None)
        if verdict and not _tracked_unchanged(target):
            return verdict
    return None


# A string handed to one of these is Python, judged as a program one level down.
EVALUATORS = ("eval", "exec", "compile")
# The words a string fills an unknown piece of a built string with: a concatenation, an f-string or a format whose known text names `worktree` is judged as if the unknown part completed the phrase.
FILLS = ("add", "worktree", "worktree add")
PLACEHOLDER = re.compile(r"%[-#0 +]*\d*(?:\.\d+)?[sdirfx]|\{[^{}]*\}|\$\{[^{}]*\}|#\{[^{}]*\}")
UNKNOWN = "\0"


def _callee(node):
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else ""


FOLDS = (ast.BinOp, ast.JoinedStr, ast.Call)


def _pieces(node):
    """A string expression as its pieces, a part the text does not hold read as None: a concatenation, an f-string, `%` and `.format` (whose placeholders `_filled` reads as unknown), and `sep.join([...])`."""
    value = _const_str(node)
    if value is not None:
        return [value]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _pieces(node.left) + _pieces(node.right)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
        return _pieces(node.left)
    if isinstance(node, ast.JoinedStr):
        out: list[str | None] = []
        for part in node.values:
            out.extend(_pieces(part.value if isinstance(part, ast.FormattedValue) else part))
        return out
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "format":
            return _pieces(node.func.value)
        sep = _const_str(node.func.value)
        if (
            node.func.attr == "join"
            and sep is not None
            and node.args
            and isinstance(node.args[0], (ast.List, ast.Tuple))
        ):
            out = []
            for pos, elt in enumerate(node.args[0].elts):
                if pos:
                    out.append(sep)
                out.extend(_pieces(elt))
            return out
    return [None]


def _filled(text, mentions):
    """The commands a built string can spell: its known text, and with each unknown piece or placeholder filled from FILLS when the file names `worktree` anywhere (`mentions`)."""
    text = PLACEHOLDER.sub(UNKNOWN, text)
    if UNKNOWN not in text:
        return [text]
    if not mentions:
        return [text.replace(UNKNOWN, " ")]
    return [text.replace(UNKNOWN, " %s " % fill) for fill in FILLS]


def _python_folds(tree, mentions):
    """Every outermost built string in the file, as the commands `_filled` reads it to spell. `mentions` is whether the file names `worktree` at all; a built string is filled only then."""
    inner: set[int] = set()
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, FOLDS) or id(node) in inner:
            continue
        pieces = _pieces(node)
        if pieces == [None]:
            continue
        for child in ast.walk(node):
            if child is not node and isinstance(child, FOLDS):
                inner.add(id(child))
        out.extend(_filled("".join(UNKNOWN if p is None else p for p in pieces), mentions))
    return out


def _filled_sequences(sequences, mentions):
    """An argv list with an element the text does not hold, filled from FILLS when the file names `worktree`: `["git", "worktree", verb]` with `verb` bound by a loop."""
    for seq in sequences:
        yield seq
        if mentions and None in seq:
            for fill in FILLS:
                yield [fill if e is None else e for e in seq]


def _python_verdict(code, depth):
    """The arm a Python program text trips, or None. Python that does not parse runs nothing, but this module's own reading of a shell word may differ from bash's, so it falls back to the regex reading rather than to an allow."""
    try:
        tree = ast.parse(code)
        mentions = "worktree" in code
        folds = _python_folds(tree, mentions)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        # fa5d11be.3: a program nested past the parser's recursion limit, or too large for it, is read like Python that does not parse: by the regex reading, which neither recurses nor allocates a tree. Not fail-open (its literals and argv shapes are still judged) and not a blanket refusal (a deep data structure is not a worktree add).
        return _text_verdict(code, depth)
    strings = []
    for node in ast.walk(tree):
        value = _const_str(node)
        if value is not None:
            strings.append(value)
    sequences = list(_sequences(tree))
    called = set()
    for value in dict.fromkeys(strings + folds):
        verdict = shell_verdict(value, depth)
        if verdict:
            return verdict
    # A string handed to eval, exec or compile is Python, not shell: judged as a program one level down.
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _callee(node) in EVALUATORS and node.args:
            program = _const_str(node.args[0])
            if program is not None and depth < MAX_PROGRAM_DEPTH:
                verdict = _python_verdict(program, depth + 1)
                if verdict:
                    return verdict
    for seq in _filled_sequences(sequences, mentions):
        if _adjacent(seq, "worktree", "add"):
            return "git"
        if any(e is not None for e in seq) and len(seq) > 1:
            verdict = shell_verdict(_joined(seq), depth)
            if verdict:
                return verdict
    modules = set(strings)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            modules.update("%s.%s" % (node.module, alias.name) for alias in node.names)
        elif isinstance(node, ast.Call):
            called.add(_callee(node))
    port = any(m == PORT_TARGETS[0] or m.startswith(PORT_TARGETS[0] + ".") for m in modules)
    if port and (
        "cmd_create" in called
        or "cmd_create" in strings
        or any("create" in seq for seq in sequences)
    ):
        return "port"
    package = any(m == "rediacc_ci" or m.startswith("rediacc_ci.") for m in modules)
    if package and any(_adjacent(seq, "worktree", "create") for seq in sequences):
        return "port"
    return None


# A literal that is one piece of a built string: a concatenation operator (`+`, perl `.`, `<<`, `.concat(`) beside it, or an interpolation inside it.
TEXT_JOIN_AFTER = re.compile(r"\s*(?:\+|\.(?![\w.])|<<|\.concat\b)")
TEXT_JOIN_BEFORE = re.compile(r"(?:\+|(?<![\w.])\.|<<)\s*$")
TEXT_INTERPOLATION = re.compile(r"\$\{[^{}]*\}|#\{[^{}]*\}|[$@]\w+")


def _text_literals(code):
    """Every literal the regex reading finds, a built one also as the commands `_filled` reads it to spell."""
    mentions = "worktree" in code
    for m in itertools.chain(LITERAL.finditer(code), QUOTE_LIKE.finditer(code)):
        literal = " ".join(next(g for g in m.groups() if g is not None).split())
        yield literal
        built = TEXT_INTERPOLATION.sub(UNKNOWN, literal)
        if UNKNOWN in built:
            yield from _filled(built, mentions)
        if mentions and TEXT_JOIN_AFTER.match(code, m.end()):
            yield from _filled(built + UNKNOWN, mentions)
        if mentions and TEXT_JOIN_BEFORE.search(code[max(0, m.start() - 16) : m.start()]):
            yield from _filled(UNKNOWN + built, mentions)


def _text_verdict(code, depth):
    """The arm a program text trips, read by regex: for a node/perl/ruby program, and for Python that `ast` cannot parse."""
    for literal in _text_literals(code):
        verdict = shell_verdict(literal, depth)
        if verdict:
            return verdict
    if ARGV_WORKTREE_ADD.search(code):
        return "git"
    if TEXT_PORT.search(code) and TEXT_PORT_CREATE.search(code):
        return "port"
    if "rediacc_ci" in code and ARGV_WORKTREE_CREATE.search(code):
        return "port"
    return None


def _direct_verdict(cmd):
    """The arm that refuses `cmd` as the shell reads it, before any program text is opened: "git", "run.sh", "port", or None."""
    scan = shellscan._command_substitution(shellscan.scan_target(cmd))
    if hookio.grep_q(WORKTREE_ADD, scan):
        return "git"
    if hookio.grep_q(RUN_SH_CREATE, scan):
        return "run.sh"
    if runs_port_create(cmd):
        return "port"
    return None


def _code_verdict(family, code, depth):
    if family == "python":
        return _python_verdict(code, depth)
    if family == "shell":
        # `bun exec "<command line>"` runs its operand through Bun's shell, and a program fed to an evaluator on stdin may be one too: either is read as a command line.
        return shell_verdict(code, depth)
    return _text_verdict(code, depth)


def _file_verdict(family, text, depth):
    """The arm a script run by path trips: "script" when its text names the phrase (`_names_phrase`), else what the same text trips as a `-c` program (a built string folded, an implicit concatenation `ast` joins, the port's `cmd_create`), or for a shell script as a command line."""
    if _names_phrase(text):
        return "script"
    if family == "shell":
        return shell_verdict(text, depth)
    return _code_verdict(family, text, depth)


def _program_verdict(cmd, depth, cwd=None):
    """The arm a program `cmd` hands an interpreter trips, to MAX_PROGRAM_DEPTH programs deep: the texts `interpreter_programs` finds in the command line, the files and unread producers a stdin program is read from, then every script it runs BY PATH (`_script_verdict`). An unread producer is the verdict "unread:<producer>", which `run` names in the refusal."""
    if depth >= MAX_PROGRAM_DEPTH:
        return None
    files: list[tuple[str, str, str]] = []
    for family, code in interpreter_programs(cmd, files=files):
        verdict = _code_verdict(family, code, depth + 1)
        if verdict:
            return verdict
    for family, kind, value in files:
        if kind == "unread":
            return "unread:" + value
        verdict = _redirect_verdict(family, value, cmd, cwd, depth)
        if verdict:
            return verdict
    return _script_verdict(cmd, depth, cwd)


# A SCRIPT RUN BY PATH IS A PROGRAM TOO (#78afdc0b). `interpreter_programs` reads only what the command line itself holds (`-c`, `-e`, a heredoc, a here-string, a pipe), so `python3 scratch/wt.py` whose file runs `git worktree add` was allowed (rc 0, 2026-10-14) while the same text as `python3 - <<EOF` was refused. `shellscan.interpreter_program` is the reading the shell-write guards share: what an earlier run of the same command wrote into the script, else the file on disk;
# a script tracked and unchanged from HEAD is reviewed code and is not read, and one that does not exist fails open. A shell script run by path (`bash x.sh`, `source x.sh`, `./x.sh`) is read by `_shell_script` under the same rules. A script on disk that cannot be read in full (`_unread_reason`: past its size cap, unreadable, a directory, a zip, a descriptor) is refused whatever the command line says, unless tracked and unchanged. An "unjudgeable" script written by the same command from a source the walk cannot read (`cp a.py b.py && python3 b.py`) is refused when the command itself could spell the banned verb, the pre-filter `shell_verdict` applies inside a program.
# `shellscan.PROGRAM_PREFILTER` admits an interpreter word or a path word; a shell reading a script named without a slash (`bash x.sh`, `source x.sh`) is neither.
SHELL_SCRIPT_PREFILTER = re.compile(r"\b(?:sh|bash|dash|zsh|ash|ksh|source)\b|(?:^|[\s;&|(`])\.\s")


def _script_verdict(cmd, depth, cwd):
    if not (shellscan.PROGRAM_PREFILTER.search(cmd) or SHELL_SCRIPT_PREFILTER.search(cmd)):
        return None
    for run_ in shellscan.every_run(cmd):
        if _unread_reason(run_, cmd, cwd):
            return "unread"
        if _reads_stdin_operand(run_):
            # Judged by its stdin program (`_program_verdict`); opening /dev/stdin here would read the hook's own input.
            continue
        text, kind = shellscan.interpreter_program(run_, cmd, cwd)
        family = _interpreter_name(run_.name) or _interpreter_name(
            shellscan.shebang_interpreter(run_, cwd) or ""
        )
        if kind not in ("file", "unjudgeable"):
            text, kind = _shell_script(run_, cmd, cwd)
            family = "shell"
        if kind == "file" and text:
            verdict = _file_verdict(family, text, depth + 1)
            if verdict:
                return verdict
        elif kind == "unjudgeable" and _could_spell(cmd):
            return "unjudgeable"
    return None


def _could_spell(text):
    bare = re.sub(r"[\"'\\]", "", text)
    return "worktree" in bare and ("add" in bare or "create" in bare)


def shell_verdict(cmd, depth=0):
    """Which arm refuses the shell command `cmd`: "git", "run.sh", "port", or None, counting what any program inside it runs.

    Inside a program (depth > 0) a string that cannot spell `worktree` and one of `add`/`create` once quotes and backslashes are gone is skipped without a walk: every arm needs that word and one of those verbs, and a Python heredoc holds thousands of strings that are not commands (3,000 list literals naming `worktree list` took 2.9 s before the verb joined the filter).
    """
    if cmd == "":
        return None
    if depth > 0 and not _could_spell(cmd):
        return None
    return _direct_verdict(cmd) or _program_verdict(cmd, depth)


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

PROGRAM_NOTE = (
    "It was found inside the program text this command hands an interpreter (`python3 -c`, "
    "a heredoc or here-string on stdin, `node -e`, `perl -e`, `ruby -e`, or a script run by "
    "path): code an interpreter runs is the same decision as the command typed at the shell."
)

SCRIPT_MESSAGE = (
    "❌ BLOCKED: this runs a script, by path or read on stdin from a file, whose text "
    "names `worktree` together with `add` "
    "or `create`, and the script is untracked or differs from HEAD. Such a script is refused "
    "whatever it does with the words, because no reading of what a file can execute is "
    "complete. A script whose file only QUOTES the words (a fixture table, a docstring, a "
    "selftest) has a safe path: commit it, then run it, because the hook does not read a tracked "
    "script unchanged from HEAD (`git status --porcelain -- <script>` must print nothing for "
    "it); a commit is not a review, so commit only a script whose text you have judged yourself. Otherwise hand the command to the operator to run with the `!` "
    "prefix, or drop the phrase from a script that does not need it."
)

UNJUDGEABLE_MESSAGE = (
    "❌ BLOCKED: this command names a worktree verb and runs a script this hook cannot read: "
    + shellscan.UNJUDGEABLE_REASON
    + "."
)

UNREAD_MESSAGE = (
    "❌ BLOCKED: this runs a script, by path or read on stdin from a file, that this "
    "hook could not read in full (larger than the hook reads, unreadable, a directory or zip an "
    "interpreter runs, a path holding a NUL byte, a remote module deno fetches, or a descriptor "
    "such as `<(...)` or /dev/fd/N), "
    "and the script is untracked or differs from HEAD, so whether it runs "
    "`git worktree add` cannot be judged. Hand the command to the operator to run with the `!` "
    "prefix, which bypasses this hook, or run a script the hook can read."
)

# The "unread:<producer>" verdict: a program an interpreter or shell reads on stdin from a source the hook cannot read (#faca6bd7).
UNREAD_STDIN_MESSAGE = (
    "❌ BLOCKED: this runs a program an interpreter or shell reads on stdin from %s, which "
    "this hook could not read in full, so whether it runs `git worktree add` cannot be judged. "
    "Hand the command to the operator to run with the `!` prefix, which bypasses this hook, or "
    "hand the interpreter its program as `-c`, a heredoc or a file the hook can read."
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
    # The interpreter arm: a program text handed to python, node, perl or ruby, through -c/-e, a heredoc, a here-string or a pipe.
    (
        "python -c with a git argv list",
        "python3 -c \"import subprocess; subprocess.run(['git','worktree','add','/tmp/x'])\"",
    ),
    (
        "python -c calling the port in-process",
        "python3 -c 'from rediacc_ci.dev import worktree; worktree.main([\"create\"])'",
    ),
    (
        "python reading a heredoc",
        "python3 - <<'EOF'\nimport os\nos.system('git worktree add /tmp/x')\nEOF",
    ),
    (
        "python reading a here-string",
        "python3 - <<< 'import os; os.system(\"git worktree add /tmp/x\")'",
    ),
    (
        "python fed by a piped cat heredoc",
        "cat <<'EOF' | python3\nimport os; os.system('git worktree add x')\nEOF",
    ),
    ("node -e", 'node -e \'require("child_process").execSync("git worktree add /tmp/x")\''),
    ("perl -e with an argv list", 'perl -e \'system("git", "worktree", "add", "/tmp/x")\''),
    (
        "control: python -c listing worktrees",
        "python3 -c \"import subprocess; subprocess.run(['git','worktree','list'])\"",
    ),
    (
        "control: python printing a sentence",
        "python3 -c 'print(\"never run git worktree add here\")'",
    ),
    (
        "control: python reading the port's source",
        "python3 - <<'EOF'\nprint(open('.ci/rediacc_ci/dev/worktree.py').read().count('create'))\nEOF",
    ),
    (
        "control: python reading the port's docstring",
        "python3 -c 'from rediacc_ci.dev import worktree; print(worktree.cmd_create.__doc__)'",
    ),
    # #503f0ba8: a command `npx` or `find -exec` LAUNCHES is judged as a run of its own.
    (
        "the port launched by find -exec",
        r"find . -maxdepth 0 -exec python3 -m rediacc_ci.dev.worktree create x \;",
    ),
    (
        "a python program launched by npx -c",
        'npx -c "python3 -c \\"import os; os.system(\'git worktree add /tmp/x\')\\""',
    ),
    (
        "control: prose naming a launched create",
        "echo find . -exec python3 -m rediacc_ci.dev.worktree create x",
    ),
    # fa5d11be.1-.4: option values, attached -e code, a program too deep for ast, quote-like literals.
    ("perl -I value then -e", 'perl -I lib -e \'system("git","worktree","add","x")\''),
    ("control: words after perl's script", "perl -I lib script.pl git worktree add x"),
    ("perl -e with attached code", "perl '-esystem(\"git worktree add x\")'"),
    (
        "a deep program read by regex",
        "python3 -c \"import os; os.system('git worktree add /tmp/x'); x = %s1\"" % ("-" * 10000),
    ),
    ("control: a deep program running nothing", 'python3 -c "x = %s1"' % ("-" * 10000)),
    ("a perl qw() word list", "perl -e 'system qw(git worktree add x)'"),
    ("control: a qw() sentence", "perl -e 'print qw(never run git worktree add here)'"),
]


def run(ev):
    cmd = ev.field("tool_input", "command")
    if cmd == "":
        return hookio.ALLOW
    messages = {
        "git": GIT_MESSAGE,
        "run.sh": RUN_SH_MESSAGE,
        "port": PORT_MESSAGE,
        "unjudgeable": UNJUDGEABLE_MESSAGE,
        "script": SCRIPT_MESSAGE,
        "unread": UNREAD_MESSAGE,
    }
    verdict = _direct_verdict(cmd)
    if verdict:
        ev.warn(messages[verdict])
        return hookio.DENY
    verdict = _program_verdict(cmd, 0, ev.field("cwd") or None)
    if verdict:
        key, _, producer = verdict.partition(":")
        if key == "unread" and producer:
            ev.warn(UNREAD_STDIN_MESSAGE % producer)
            return hookio.DENY
        # An unjudgeable or unread script found nothing, and a script naming the phrase was refused for its text: the note says where a worktree verb was found, so it is for the other verdicts only.
        ev.warn(
            messages[key]
            + ("" if key in ("unjudgeable", "unread", "script") else " " + PROGRAM_NOTE)
        )
        return hookio.DENY
    return hookio.ALLOW
