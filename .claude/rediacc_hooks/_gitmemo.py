"""One answer per read-only git question for the life of ONE guard chain run.

WHY (PR-TASK 79b7e92e, operator 2026-11-24: "This is a throttle!", load 134 on 24 cores with about ten lease writers). Measured on the 5775bcdaf2 tree, one pre-bash chain over an `echo hi` payload started 68 subprocesses, every one of them a `git rev-parse` or `git symbolic-ref` asked of the same directory: `--git-common-dir` 31 times, `--show-toplevel` 24 times, the rest a handful each. Eight distinct questions, asked by guards that each locate the repository for themselves through `commit_policy.git`, `hookio.run_out` and `shellscan._git_stdout`. Every Bash tool call of every session and writer paid those forks, and on a loaded machine a fork is the expensive part.

WHY THE ANSWER CANNOT CHANGE INSIDE THE RUN. A PreToolUse chain runs BEFORE the tool: the command it judges has not started, and no guard writes to git (they ask, they never commit, check out or move a ref). So the repository a directory sits in, its common directory, its superproject and the branch HEAD names are fixed for the chain's whole life, which is a few hundred milliseconds. The memo lives exactly that long: `chain_memo()` installs it, and leaving the `with` drops every answer, so the next tool call asks git again.

WHAT IS MEMOIZED, AND WHAT IS NOT. Only `subprocess.run` calls whose argv is git's and whose subcommand (the first word after git's global options, `-C <dir>` and `-c <k=v>` included) is in `READ_ONLY` (or is `symbolic-ref` in its reading form: at most one operand and only `-q`, `--quiet`, `--short`, `--recurse`, `--no-recurse`), with captured stdout, no stdin data and no `check=True`. The key is the argv, the directory it runs in (the process's own when `cwd` is unset), every `GIT_*` variable of the environment it runs under, and the keyword arguments that shape the returned object (`text`, `encoding`, `errors`, `universal_newlines`, `stderr`, `timeout` is deliberately NOT in it, since it changes no answer). An exception (git missing, a timeout) is never stored, so the next caller asks again. Anything else passes straight through to the real `subprocess.run`.

PLANTED DEFECT. `tests/test_gitmemo.py` replaces `DEFECT[0]` with `DEFECT[1]`, which keys on the argv alone: two directories in different repositories then share one `--show-toplevel`, and the test that asks both must go red.
"""

from __future__ import annotations

import contextlib
import os
import subprocess

# git subcommands that only read. `rev-parse` answers where a repository is and what a name points at; `symbolic-ref` with no new value and only reading options only reads HEAD.
READ_ONLY = frozenset({"rev-parse"})
# `symbolic-ref` reads with one or two words after its options (`-q --short HEAD`) and WRITES with a second operand (`symbolic-ref HEAD refs/heads/x`), so it is memoized only in its reading form.
SYMBOLIC_REF = "symbolic-ref"
# The only options a READING `symbolic-ref` carries. Any other (`-d`/`--delete` removes the symref with ONE operand, `-m` sets a reflog message for a write) makes it a write, which passes through every time.
_SYMBOLIC_REF_READ_FLAGS = frozenset({"-q", "--quiet", "--short", "--recurse", "--no-recurse"})

# git's global options that take the next word as their value.
_VALUE_OPTS = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"})

# Keyword arguments that change the returned CompletedProcess, and so belong in the key.
_SHAPE_KW = ("text", "encoding", "errors", "universal_newlines", "stderr")

DEFECT = (
    "    return (tuple(argv), where, git_env, shape)\n",
    "    return (tuple(argv),)\n",
)


def _subcommand(argv):
    """`(index, word)` of git's subcommand in argv, or (None, None)."""
    i = 1
    while i < len(argv):
        word = argv[i]
        if word in _VALUE_OPTS:
            i += 2
            continue
        if word.startswith("-"):
            i += 1
            continue
        return i, word
    return None, None


def _reads_only(argv):
    if not argv or os.path.basename(str(argv[0])) != "git":
        return False
    at, sub = _subcommand(argv)
    if sub in READ_ONLY:
        return True
    if sub == SYMBOLIC_REF:
        rest = [str(w) for w in argv[at + 1 :]]
        flags = [w for w in rest if w.startswith("-")]
        operands = [w for w in rest if not w.startswith("-")]
        return len(operands) <= 1 and all(f in _SYMBOLIC_REF_READ_FLAGS for f in flags)
    return False


def _key(argv, kwargs):
    """The memo key, or None when the directory git would run in cannot be named (the process's own was deleted): that question is not memoized, so the real call answers it and raises or fails exactly as it would unmemoized."""
    cwd = kwargs.get("cwd")
    try:
        where = os.path.abspath(os.fspath(cwd)) if cwd else os.getcwd()
    except FileNotFoundError:
        return None
    env = kwargs.get("env")
    env = os.environ if env is None else env
    git_env = tuple(sorted((k, v) for k, v in env.items() if k.startswith("GIT_")))
    shape = tuple((k, repr(kwargs.get(k))) for k in _SHAPE_KW)
    return (tuple(argv), where, git_env, shape)


def _cacheable(args, kwargs):
    argv = args[0] if args else kwargs.get("args")
    if not isinstance(argv, (list, tuple)) or kwargs.get("shell"):
        return None
    argv = [os.fspath(a) if isinstance(a, os.PathLike) else a for a in argv]
    if not all(isinstance(a, str) for a in argv) or not _reads_only(argv):
        return None
    if kwargs.get("input") is not None or kwargs.get("check"):
        return None
    if kwargs.get("stdin") not in (None, subprocess.DEVNULL):
        return None
    if not (kwargs.get("capture_output") or kwargs.get("stdout") == subprocess.PIPE):
        return None
    return argv


class Memo:
    """The table one chain run fills, plus its counters for tests and measurement."""

    def __init__(self, real):
        self.real = real
        self.table = {}
        self.hits = 0
        self.misses = 0

    def run(self, *args, **kwargs):
        argv = _cacheable(args, kwargs)
        if argv is None:
            return self.real(*args, **kwargs)
        key = _key(argv, kwargs)
        if key is None:
            return self.real(*args, **kwargs)
        got = self.table.get(key)
        if got is not None:
            self.hits += 1
            return subprocess.CompletedProcess(got.args, got.returncode, got.stdout, got.stderr)
        self.misses += 1
        got = self.real(*args, **kwargs)
        self.table[key] = got
        return subprocess.CompletedProcess(got.args, got.returncode, got.stdout, got.stderr)


@contextlib.contextmanager
def chain_memo():
    """Memoize read-only git questions until the `with` ends. Nested use shares the outer memo."""
    current = subprocess.run
    outer = getattr(current, "__self__", None)
    if isinstance(outer, Memo):
        yield outer
        return
    memo = Memo(current)
    subprocess.run = memo.run
    try:
        yield memo
    finally:
        subprocess.run = current
