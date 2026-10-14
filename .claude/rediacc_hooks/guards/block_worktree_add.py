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
import itertools
import os
import re
import shlex
import stat
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
INTERPRETERS = ("node", "perl", "ruby")
# The flags that hand each non-Python interpreter its program text as the next word.
EVAL_FLAGS = {
    "node": ("-e", "--eval", "-p", "--print"),
    "perl": ("-e", "-E"),
    "ruby": ("-e",),
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
STDIN_PATHS = ("/dev/stdin", "/dev/fd/0", "/proc/self/fd/0")


def _stdin_path(word):
    return word.startswith("/") and os.path.normpath(word) in STDIN_PATHS


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
    """`(family, mode, code)` for an interpreter command, or None when `name` is no interpreter. `mode` is "c" (the code is in argv), "stdin" (the code arrives on stdin) or anything else (a file or module, which the arms above judge)."""
    family = _interpreter_name(name)
    if family is None:
        if name.rsplit("/", 1)[-1] == "uv" and args[:1] == ["run"]:
            for k, word in enumerate(args[1:], 1):
                if PYTHON.match(word.rsplit("/", 1)[-1]):
                    return _program_of(word, args[k + 1 :])
        return None
    if family == "python":
        # The option parse `shellscan.interpreter_program` reads with (#78afdc0b): the private one this replaced stepped over `--check-hash-based-pycs` alone, read its value as the script and never saw the `-c` after it.
        kind, code = shellscan._program_parse(name.rsplit("/", 1)[-1], args)
        if kind == "file" and _stdin_path(code):
            kind = "stdin"
        mode = {"inline": "c", "stdin": "stdin"}.get(kind, kind)
        return (family, mode, code if mode == "c" else None)
    mode, code = _eval_program(family, args)
    return (family, mode, code)


def _stdin_texts(redirs, upstream):
    """What a command reads on stdin, as far as the command line itself supplies it: a heredoc body, a here-string, or the output of a `cat <<EOF` / `cat <<<` / `echo` / `printf` feeding it through a pipe. The same sources shellscan's walker hands a shell reading stdin."""
    out: list[tuple[Any, str | None]] = []
    for redir in redirs:
        hd = redir.heredoc
        if hd is not None and hd.body_start is not None:
            out.append((hd, None))
        elif redir.op == "<<<" and redir.target is not None:
            out.append((None, shellscan._word_value(redir.target)))
    if upstream is None or upstream[0] != "cmd":
        return out
    words, _ = shellscan._strip_prefixes([t for t in upstream[1] if isinstance(t, shellscan._Word)])
    if not words:
        return out
    feeder = shellscan._word_value(words[0]).rsplit("/", 1)[-1]
    if feeder == "cat":
        out.extend(_stdin_texts([t for t in upstream[1] if isinstance(t, shellscan._Redir)], None))
    elif feeder in ("echo", "printf"):
        argv = [shellscan._word_value(w) for w in words[1:]]
        while argv and feeder == "echo" and re.match(r"^-[neE]+$", argv[0]):
            argv = argv[1:]
        out.append((None, " ".join(argv)))
    return out


# A FILE ON STDIN IS A SCRIPT ON DISK (0d227c80 sibling). `_stdin_texts` reads only text the command line holds, so `python3 - < p.py`, `cat p.py | python3 -`, `{ python3 -; } < p.py` and `bash < x.sh` ran a file holding `git worktree add` with rc 0 (2026-10-15) while `python3 p.py` was refused. `_stdin_files` names every file a stdin program is read from: a `<` or `<>` redirect on descriptor 0, and the file operands and stdin redirect of a `cat` feeding the pipe. `_redirect_verdict` reads each under the rules a script run by path is read by.
STDIN_REDIRECTS = ("<", "<>")


def _stdin_files(redirs, upstream):
    """The words naming each file a command reads on stdin, as far as the command line names them: its own `<`/`<>` redirect on descriptor 0, and what a `cat` in front of it reads (its file operands, or its own stdin redirect)."""
    out = [
        shellscan._word_value(redir.target)
        for redir in redirs
        if redir.op in STDIN_REDIRECTS
        and redir.fd in (None, "0")
        and redir.heredoc is None
        and redir.target is not None
    ]
    if upstream is None or upstream[0] != "cmd":
        return out
    words, _ = shellscan._strip_prefixes([t for t in upstream[1] if isinstance(t, shellscan._Word)])
    if not words or shellscan._word_value(words[0]).rsplit("/", 1)[-1] != "cat":
        return out
    out.extend(_stdin_files([t for t in upstream[1] if isinstance(t, shellscan._Redir)], None))
    operands = False
    for word in (shellscan._word_value(w) for w in words[1:]):
        if word == "--" and not operands:
            operands = True
        elif word != "-" and (operands or not word.startswith("-")):
            out.append(word)
    return out


def interpreter_programs(cmd, depth=0, files=None):
    """Every `(family, program text)` `cmd` hands an interpreter: `python3 -c`, `node -e`, `perl -e`, `ruby -e`, and each of them reading a heredoc, a here-string or a piped `cat`/`echo` as its program.

    It walks the same token structure `shellscan._analyse` walks (subshells, brace groups, pipelines, `$(...)`, the prefix commands `_strip_prefixes` drops), and descends into a shell's own payload (`sh -c`, `bash <<EOF`, `eval`), because `sh -c "python3 - <<EOF ..."` is the same program one level down. `_Run` records argv but not redirects, which is why this cannot read `_analyse(cmd).runs` alone: a heredoc is a redirect.

    A group's stdin (`{ ...; } < f`, `(...) <<EOF`, `cat f | { ...; }`) is the stdin of the first command of each pipeline inside it. When `files` is a list, each `(family, word)` naming a FILE a stdin program is read from (`_stdin_files`) is appended to it, `family` being "shell" for a shell reading its script on stdin; `_redirect_verdict` reads those, since a file's text is not the command line's.
    """
    out: list[tuple[str, str]] = []
    if depth > MAX_PROGRAM_DEPTH or cmd == "":
        return out
    lexer = shellscan._Lexer(cmd)
    toks = lexer.tokens()

    def text_of(item):
        hd, text = item
        return lexer.src[hd.body_start : hd.body_end] if hd is not None else text

    def words_subs(parts):
        for part in parts:
            if part.sub is not None:
                walk(shellscan._parse(part.sub))
            if part.parts:
                words_subs(part.parts)

    def element(stage, upstream, inherited):
        group_redirs, group_upstream = inherited
        if upstream is None:
            upstream = group_upstream
        if stage[0] in ("sub", "brace"):
            own = [
                t for t in (stage[2] if len(stage) > 2 else []) if isinstance(t, shellscan._Redir)
            ]
            walk(stage[1], (own + group_redirs, upstream))
            return
        words = [t for t in stage[1] if isinstance(t, shellscan._Word)]
        redirs = [t for t in stage[1] if isinstance(t, shellscan._Redir)] + group_redirs
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
            elif mode == "stdin":
                out.extend((family, text_of(item)) for item in _stdin_texts(redirs, upstream))
                if files is not None:
                    files.extend((family, word) for word in _stdin_files(redirs, upstream))
        elif base in shellscan.SHELL_NAMES:
            mode, payload = shellscan._shell_payload(argv)
            if mode == "c" and payload is not None:
                out.extend(interpreter_programs(payload, depth + 1, files))
            elif mode == "stdin":
                for item in _stdin_texts(redirs, upstream):
                    out.extend(interpreter_programs(text_of(item), depth + 1, files))
                if files is not None:
                    files.extend(("shell", word) for word in _stdin_files(redirs, upstream))
        elif base == "eval":
            out.extend(interpreter_programs(" ".join(argv), depth + 1, files))
        else:
            # A LAUNCHER'S COMMAND (#503f0ba8): `find . -exec python3 -c '...' \;` and `npx -c '...'` hand an interpreter its program one level down, so the launched command is walked as a command line of its own, quoted back so its program text stays one word.
            for how, launched in shellscan._launched(base, argv):
                src = launched if how == "text" else shellscan._quote_argv(launched)
                out.extend(interpreter_programs(src, depth + 1, files))

    def walk(items, inherited=((), None)):
        for item in items:
            if item[0] == "sep":
                continue
            stages = item[1]
            for pos, stage in enumerate(stages):
                if pos:
                    element(stage, stages[pos - 1], ([], None))
                else:
                    element(stage, None, (list(inherited[0]), inherited[1]))

    walk(shellscan._parse(toks))
    return out


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


def _shell_script_path(run_, cmd, cwd):
    """The script a shell run reads by path: `bash x.sh`, `source x.sh`, `. x.sh`, or `./x.sh` run directly whose shebang names no interpreter `shellscan.interpreter_program` reads (a shell, or none). None for anything else."""
    base = run_.name.rsplit("/", 1)[-1]
    argv = list(run_.argv)
    if base.startswith(shellscan.INTERPRETER_NAMES):
        return None
    if base in shellscan.SHELL_NAMES:
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
        kind, value = shellscan._program_parse(base, list(run_.argv))
        return value if kind == "file" else None
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
            reason = "a directory" if interpreter else None
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
    kind, value = shellscan._program_parse(run_.name.rsplit("/", 1)[-1], list(run_.argv))
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
    """The arm a file fed to a stdin program trips (`_stdin_files`), read under the rules a script run by path is read by: what an earlier run of `cmd` writes into it, and the file on disk, are both judged as `_file_verdict` judges a script; one that cannot be read in full is "unread"; a tracked file unchanged from HEAD is reviewed code and passes; one that does not exist fails open. A relative word is resolved in every directory a run of `cmd` executes in, the over-reading direction, because the walk that finds the redirect does not follow `cd`."""
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
    return _text_verdict(code, depth)


def _file_verdict(family, text, depth):
    """The arm a script run by path trips: "script" when its text names the phrase (`_names_phrase`), else what the same text trips as a `-c` program (a built string folded, an implicit concatenation `ast` joins, the port's `cmd_create`), or for a shell script as a command line."""
    if _names_phrase(text):
        return "script"
    if family == "shell":
        return shell_verdict(text, depth)
    return _code_verdict(family, text, depth)


def _program_verdict(cmd, depth, cwd=None):
    """The arm a program `cmd` hands an interpreter trips, to MAX_PROGRAM_DEPTH programs deep: the texts `interpreter_programs` finds in the command line, then every script it runs BY PATH (`_script_verdict`)."""
    if depth >= MAX_PROGRAM_DEPTH:
        return None
    files: list[tuple[str, str]] = []
    for family, code in interpreter_programs(cmd, files=files):
        verdict = _code_verdict(family, code, depth + 1)
        if verdict:
            return verdict
    for family, word in files:
        verdict = _redirect_verdict(family, word, cmd, cwd, depth)
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
    "complete. Hand the command to the operator to run with the `!` prefix, or drop the "
    "phrase from a script that does not need it."
)

UNJUDGEABLE_MESSAGE = (
    "❌ BLOCKED: this command names a worktree verb and runs a script this hook cannot read: "
    + shellscan.UNJUDGEABLE_REASON
    + "."
)

UNREAD_MESSAGE = (
    "❌ BLOCKED: this runs a script, by path or read on stdin from a file, that this "
    "hook could not read in full (larger than the hook reads, unreadable, a directory or zip an "
    "interpreter runs, a path holding a NUL byte, or a descriptor such as `<(...)` or /dev/fd/N), "
    "and the script is untracked or differs from HEAD, so whether it runs "
    "`git worktree add` cannot be judged. Hand the command to the operator to run with the `!` "
    "prefix, which bypasses this hook, or run a script the hook can read."
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
        # An unjudgeable or unread script found nothing, and a script naming the phrase was refused for its text: the note says where a worktree verb was found, so it is for the other verdicts only.
        ev.warn(
            messages[verdict]
            + ("" if verdict in ("unjudgeable", "unread", "script") else " " + PROGRAM_NOTE)
        )
        return hookio.DENY
    return hookio.ALLOW
