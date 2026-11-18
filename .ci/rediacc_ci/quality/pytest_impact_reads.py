"""What each pytest file reads that no import shows, and the union of the suite's reads from the same trace (PLAN-ciquick-cpu W4.3, B2 and B6).

THE UNION'S VERDICT (2026-11-18): the whole-suite trace read every tracked file, so check:ci-pytest declares no `paths` and hashes the whole tree (its trace-ledger.ts row), and the narrowing happens inside the run through the `reads` table. `derive_paths` stays as the evidence for that verdict: a later trace whose union stops reaching the whole tree is the signal to revisit it.

WHY A SEPARATE TRACE. path-trace.ts never traces check:ci-pytest as one gate (`NEVER_TRACED`): one strace log of 36k tests runs to tens of gigabytes, and a gate-level answer says nothing about WHICH test read a file. This module traces the suite once and keeps only what the impact map needs: per test file, the tracked files it opened, executed or listed.

HOW, IN THREE PARTS.

  1. A pytest plugin (`-p rediacc_ci.quality.pytest_impact_reads`), inert unless
     MARKER_OPTION names a directory (an option, so xdist hands it to every
     worker with the rest of the command line). When a module is collected and
     when an item starts, it opens (creating) a marker file whose name is the
     quoted test path. The marker is an ordinary `openat` in the trace, so the
     attribution travels IN the syscall stream: no clock, no second channel.
  2. `strace -f -qq -y --seccomp-bpf -e status=successful` writes to a pipe this
     module reads line by line (`Attributor.feed`), so nothing the size of the
     whole-suite log is ever stored. A process takes the attribution of the
     process that created it, at the moment it was created; a marker re-attributes
     its own thread group. Successful calls only: a failed lookup is an import
     probing sys.path, not a read.
  3. `derive_reads` turns the per-file trace into the policy's `reads` table
     (content reads only, minus the file's own static import closure), and
     `derive_paths` folds the union into the `paths` and `lists` shape input-hash.ts
     reads, which is printed, not written.

WHAT A TRACE CANNOT SEE, stated so a clean table is not read as more than it is:

  * a read the process MEMOIZED: an xdist worker that cached a JSON file for the
    first test file that loaded it does not open it again for the next one, so
    only the first is attributed. The union in `paths` is unaffected; the
    per-file table can miss an edge, and CI's full suite is the backstop
    (pytest_impact.py's FULL fallbacks catch every change no test is seen to
    read at all);
  * a read by a process that is not a descendant (a daemon over a socket);
  * a path the test reads only on another branch, or only under an opt-in such as
    REDIACC_PYTEST_REAL_DIST.

LISTINGS go to `paths`' sibling `lists`, never to the reads table. Python's import system lists every sys.path directory it searches, so a listing in the table would tie whichever test imported first to every file under `.ci` and `.claude`, and pytest_impact.py's literal and FULL rules already answer "a file was added where a test globs".

    pytest_impact_reads.py --trace [--jobs N] [--shards N] [--tests <path> ...]
                                  trace the suite (or the named test files) and
                                  write TRACE_RELPATH; a run that is red beyond a
                                  few named failures (red_run_problem), or that
                                  attributed too little (trace_problem), writes
                                  nothing and exits 1
    pytest_impact_reads.py --derive [--write]
                                  print the reads table and the paths from
                                  TRACE_RELPATH; --write puts `reads` into
                                  .ci/policy/pytest-impact.json
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rediacc_ci import gitx, paths
from rediacc_ci import pytest_impact as impact

if TYPE_CHECKING:
    from collections.abc import Iterable

MARKER_OPTION = "--impact-reads-markers"
UNATTRIBUTED = ""
# The marker name for "no test file": pytest's own start-up, conftest loading, session teardown.
_UNATTRIBUTED_MARK = "-"
TRACE_SCHEMA = 1
TRACE_RELPATH = ".ci/cache/pytest-impact/reads-trace.json"
STRACE_SYSCALLS = "openat,open,execve,getdents64,chdir,fchdir,clone,clone3,fork,vfork"
# A directory folds to `dir/**` when at least FOLD_MIN_FILES of its tracked files exist and more than FOLD_FRACTION of them were read: path-trace.ts's own two constants, so a reads entry and a traced gate fold alike.
FOLD_MIN_FILES = 4
FOLD_FRACTION = 0.5
# Files that already force a FULL run when they change (impact.FULL_BASENAMES / FULL_PATHS): listing them as a read would add nothing.
_FULL_BASENAMES = impact.FULL_BASENAMES
# A trace that attributed reads to fewer than this share of the collected test files did not see the suite; its table would be a selection of whichever files happened to be marked.
MIN_ATTRIBUTED_FRACTION = 0.9


# --------------------------------------------------------------------------- 1. the plugin


def marker_name(rel: str) -> str:
    return urllib.parse.quote(rel, safe="") if rel else _UNATTRIBUTED_MARK


def label_of_marker(name: str) -> str:
    return UNATTRIBUTED if name == _UNATTRIBUTED_MARK else urllib.parse.unquote(name)


# Set by pytest_configure from MARKER_OPTION, in the controller and in every xdist worker; empty leaves the plugin inert.
_MARKERS: list[str] = []


def _mark(rel: str) -> None:
    if not _MARKERS:
        return
    directory = _MARKERS[0]
    # A marker that cannot be written leaves the previous attribution standing; trace_problem's coverage floor is what notices a plugin that marks nothing.
    with contextlib.suppress(OSError):
        os.close(
            os.open(os.path.join(directory, marker_name(rel)), os.O_RDONLY | os.O_CREAT, 0o600)
        )


def _test_rel(nodeid: str) -> str:
    """The test file of a node id (`a/test_x.py::test_y[1]`), or "" for a node that is not one."""
    head = nodeid.split("::", 1)[0]
    return head if head.endswith(".py") else UNATTRIBUTED


def pytest_addoption(parser) -> None:
    parser.addoption(
        MARKER_OPTION,
        default=None,
        help="directory the impact-reads markers are opened in (pytest_impact_reads --trace)",
    )


def pytest_configure(config) -> None:
    _MARKERS.clear()
    directory = config.getoption(MARKER_OPTION)
    if directory:
        _MARKERS.append(directory)


def pytest_collectstart(collector) -> None:
    rel = _test_rel(getattr(collector, "nodeid", "") or "")
    if rel:
        _mark(rel)


def pytest_runtest_logstart(nodeid: str) -> None:
    # Called by the runner before an item's setup, in the process that runs it (the xdist worker), and not a firstresult hook, so it cannot be starved by the default protocol.
    _mark(_test_rel(nodeid))


def pytest_sessionfinish() -> None:
    _mark(UNATTRIBUTED)


# --------------------------------------------------------------------------- 2. the stream


_PID_LINE = re.compile(r"^(\d+)\s+(.*)$")
_FD_RET = re.compile(r"=\s+\d+<(.*)>$")
_FD_ARG = re.compile(r"^\w+\(\d+<(.*?)>")
_STR_ARG = re.compile(r'^\w+\((?:AT_FDCWD(?:<[^>]*>)?,\s*)?"((?:[^"\\]|\\.)*)"')
_RESUMED = re.compile(r"^<\.\.\. (\w+) resumed>(.*)$")
_UNFINISHED = " <unfinished ...>"


def _unescape(s: str) -> str:
    """strace's C-style escapes in a quoted path (`\\"`, `\\\\`, `\\x41`)."""
    if "\\" not in s:
        return s
    try:
        return (
            s.encode("latin-1", "backslashreplace")
            .decode("unicode_escape")
            .encode("latin-1")
            .decode("utf-8", "replace")
        )
    except (UnicodeDecodeError, UnicodeEncodeError):
        return s


@dataclass
class Attributor:
    """Folds strace -f lines into `{test file: (reads, lists)}`. Pure: no I/O, so a test feeds it synthetic lines."""

    root: str
    marker_dir: str
    owner: dict[int, str] = field(default_factory=dict)
    tgid: dict[int, int] = field(default_factory=dict)
    cwd: dict[int, str] = field(default_factory=dict)
    pending: dict[int, str] = field(default_factory=dict)
    unclaimed: dict[int, list[tuple[str, str]]] = field(default_factory=dict)
    reads: dict[str, set[str]] = field(default_factory=dict)
    lists: dict[str, set[str]] = field(default_factory=dict)
    markers: int = 0
    lines: int = 0

    def __post_init__(self) -> None:
        self.root = self.root.rstrip("/")
        self.marker_dir = self.marker_dir.rstrip("/")

    def _group(self, pid: int) -> int:
        return self.tgid.get(pid, pid)

    def _known(self, pid: int) -> bool:
        return self._group(pid) in self.owner

    def _record(self, pid: int, kind: str, path: str) -> None:
        if not self._known(pid):
            self.unclaimed.setdefault(pid, []).append((kind, path))
            return
        if not path.startswith(self.root + "/") and path != self.root:
            return
        rel = path[len(self.root) + 1 :] if path != self.root else ""
        label = self.owner[self._group(pid)]
        (self.reads if kind == "read" else self.lists).setdefault(label, set()).add(rel)

    def _abs(self, pid: int, p: str) -> str:
        if p.startswith("/"):
            return os.path.normpath(p)
        base = self.cwd.get(self._group(pid), self.root)
        return os.path.normpath(os.path.join(base, p))

    def feed(self, line: str) -> None:
        line = line.rstrip("\n")
        m = _PID_LINE.match(line)
        if not m:
            return
        self.lines += 1
        pid, rest = int(m.group(1)), m.group(2)
        if not self.owner and not self.tgid:
            # The first process seen is the one strace started: pytest itself, before any test.
            self.owner[pid] = UNATTRIBUTED
            self.cwd[pid] = self.root
        if rest.startswith(("---", "+++")):
            return
        if rest.endswith(_UNFINISHED):
            self.pending[pid] = rest[: -len(_UNFINISHED)]
            return
        r = _RESUMED.match(rest)
        if r:
            rest = self.pending.pop(pid, r.group(1) + "(") + r.group(2)
        name = rest.split("(", 1)[0]
        ret = rest.rsplit(" = ", 1)[-1] if " = " in rest else ""
        if not ret or ret.startswith(("-1", "?")):
            return
        if name in ("clone", "clone3", "fork", "vfork"):
            try:
                child = int(ret.split()[0])
            except ValueError:
                return
            if "CLONE_THREAD" in rest:
                self.tgid[child] = self._group(pid)
            else:
                self.owner[child] = self.owner.get(self._group(pid), UNATTRIBUTED)
                self.cwd[child] = self.cwd.get(self._group(pid), self.root)
            for kind, path in self.unclaimed.pop(child, []):
                self._apply(child, kind, path)
            return
        if not self._known(pid) and name not in (
            "openat",
            "open",
            "execve",
            "getdents64",
            "chdir",
            "fchdir",
        ):
            return
        if name in ("openat", "open"):
            fd = _FD_RET.search(rest)
            if fd:
                path = _unescape(fd.group(1))
            else:
                s = _STR_ARG.match(rest)
                if not s:
                    return
                path = self._abs(pid, _unescape(s.group(1)))
            if path.startswith(self.marker_dir + "/"):
                self._apply(pid, "mark", path)
                return
            self._apply(pid, "read", path)
        elif name == "execve":
            s = _STR_ARG.match(rest)
            if s:
                self._apply(pid, "read", self._abs(pid, _unescape(s.group(1))))
        elif name == "getdents64":
            fd = _FD_ARG.match(rest)
            if fd:
                self._apply(pid, "list", _unescape(fd.group(1)))
        elif name == "chdir":
            s = _STR_ARG.match(rest)
            if s:
                self._apply(pid, "cwd", self._abs(pid, _unescape(s.group(1))))
        elif name == "fchdir":
            fd = _FD_ARG.match(rest)
            if fd:
                self._apply(pid, "cwd", _unescape(fd.group(1)))

    def _apply(self, pid: int, kind: str, path: str) -> None:
        if not self._known(pid):
            self.unclaimed.setdefault(pid, []).append((kind, path))
            return
        group = self._group(pid)
        if kind == "mark":
            self.markers += 1
            self.owner[group] = label_of_marker(path[len(self.marker_dir) + 1 :])
        elif kind == "cwd":
            self.cwd[group] = path
        else:
            self._record(pid, kind, path)


# --------------------------------------------------------------------------- 3. the tracked tree, and the derivations


@dataclass
class Tree:
    files: frozenset[str]
    gitlinks: frozenset[str]
    dirs: frozenset[str]

    @classmethod
    def of(cls, entries: Iterable[tuple[str, str]]) -> Tree:
        """From `(mode, path)` pairs, as `git ls-files -s` gives them."""
        files: set[str] = set()
        links: set[str] = set()
        for mode, rel in entries:
            (links if mode == "160000" else files).add(rel)
        dirs = {""}
        for rel in files | links:
            parts = rel.split("/")[:-1]
            for i in range(1, len(parts) + 1):
                dirs.add("/".join(parts[:i]))
        return cls(frozenset(files), frozenset(links), frozenset(dirs))

    def tracked(self, rel: str) -> str | None:
        """The tracked entry a read reaches: the file, the gitlink above a submodule path, or None (untracked, a cache, git metadata)."""
        if rel == ".git" or rel.startswith(".git/") or "/.git/" in rel:
            return None
        if rel in self.files:
            return rel
        for link in self.gitlinks:
            if rel == link or rel.startswith(link + "/"):
                return link
        return None


def fold(rels: Iterable[str], tree: Tree) -> list[str]:
    """Exact paths, with a directory folded to `dir/**` when it holds at least FOLD_MIN_FILES tracked files and more than FOLD_FRACTION of them are in `rels`. Deepest directories first, so a parent can absorb folded children."""
    chosen = set(rels)
    under: dict[str, list[str]] = {}
    for rel in tree.files:
        parts = rel.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            under.setdefault("/".join(parts[:i]), []).append(rel)
    covered = set(chosen)
    folded: set[str] = set()
    for d in sorted(under, key=lambda x: -x.count("/")):
        members = under[d]
        if len(members) < FOLD_MIN_FILES:
            continue
        hit = sum(1 for f in members if f in covered)
        if hit / len(members) > FOLD_FRACTION:
            folded = {g for g in folded if not g.startswith(d + "/")}
            folded.add(d + "/**")
            covered.update(members)
    out = set(folded)
    for rel in chosen:
        if not any(rel.startswith(g[: -len("**")]) for g in folded):
            out.add(rel)
    return sorted(out)


def _content(reads: Iterable[str], tree: Tree) -> set[str]:
    out = set()
    for rel in reads:
        hit = tree.tracked(rel)
        if hit is not None:
            out.add(hit)
    return out


def derive_reads(trace: dict, impact_map: dict, tree: Tree) -> dict[str, list[str]]:
    """`{test file: [path globs]}`: what each test file was seen to read, minus its own static closure (pytest_impact sees those) and the files whose change already runs FULL. A test file with nothing left gets no key."""
    out: dict[str, list[str]] = {}
    for label, entry in trace["tests"].items():
        if label not in impact_map["tests"]:
            continue
        closure = set(impact_map["tests"][label]["closure"])
        extra = {
            rel
            for rel in _content(entry.get("reads", ()), tree)
            if rel not in closure
            and rel.rsplit("/", 1)[-1] not in _FULL_BASENAMES
            and rel not in impact.FULL_PATHS
        }
        if extra:
            out[label] = fold(extra, tree)
    return dict(sorted(out.items()))


def derive_paths(
    trace: dict, impact_map: dict, tree: Tree, test_roots: Iterable[str]
) -> dict[str, list[str]]:
    """The suite's traced inputs, the evidence behind check:ci-pytest's whole-tree verdict: `paths` (every tracked file any test read, every module in any test's closure, every file under a test root), folded, and `lists` (every tracked directory listed)."""
    content: set[str] = set()
    listed: set[str] = set()
    for entry in [*trace["tests"].values(), trace.get("unattributed", {})]:
        content |= _content(entry.get("reads", ()), tree)
        for rel in entry.get("lists", ()):
            if rel in tree.dirs:
                listed.add(rel)
    for entry in impact_map["tests"].values():
        content |= {c for c in entry["closure"] if c in tree.files}
    roots = [r.rstrip("/") for r in test_roots]
    content |= {f for f in tree.files if any(f.startswith(r + "/") for r in roots)}
    globs = {_clean_glob(g) for g in fold(content, tree)}
    return {
        "paths": _minimal({*globs, *(r + "/**" for r in roots)}),
        "lists": sorted({_clean_dir(d) for d in listed}),
    }


# input-hash.ts refuses these in a `paths` glob (FORBIDDEN_GLOB_CHARS, plus `*` outside a trailing `/**`) and in a `lists` directory; Astro's `[lang]` route directories are tracked names that hold them.
_GLOB_CHARS = frozenset("*?[{\\")


def _clean_dir(rel: str) -> str:
    """`rel`, or its nearest ancestor whose name holds no glob character ('' is the root)."""
    parts = rel.split("/") if rel else []
    for i, part in enumerate(parts):
        if any(c in _GLOB_CHARS for c in part):
            return "/".join(parts[:i])
    return rel


def _clean_glob(glob: str) -> str:
    """A `paths` entry the hasher accepts: an exact path or `dir/**` with no glob character in it, else `<nearest clean ancestor>/**` (path-trace.ts folds the same way). A fold that reaches the root is `**`, the whole tree."""
    body = glob.removesuffix("/**")
    if not any(c in _GLOB_CHARS for c in body):
        return glob
    clean = _clean_dir(body.rsplit("/", 1)[0] if "/" in body else "")
    return clean + "/**" if clean else "**"


def _minimal(globs: Iterable[str]) -> list[str]:
    """`globs` without any entry another `dir/**` entry already reaches, so a test root inside a folded parent is written once."""
    globs = set(globs)
    trees = [g[: -len("**")] for g in globs if g.endswith("/**")]
    return sorted(g for g in globs if not any(g != t + "**" and g.startswith(t) for t in trees))


def glob_matches(glob: str, rel: str) -> bool:
    """input-hash.ts `matchGlob` for the three shapes this module writes: an exact path, `dir/**`, and `**`."""
    if glob == "**":
        return True
    if glob.endswith("/**"):
        return rel.startswith(glob[: -len("**")])
    return glob == rel


# --------------------------------------------------------------------------- the real run


def read_tree(root: pathlib.Path) -> Tree | None:
    res = gitx.git(["ls-files", "-s", "-z"], root=root)
    if res.returncode != 0:
        return None
    entries = []
    for rec in res.stdout.split("\0"):
        if not rec:
            continue
        meta, rel = rec.split("\t", 1)
        entries.append((meta.split()[0], rel))
    return Tree.of(entries)


def strace_argv(log: str, inner: list[str]) -> list[str]:
    """strace writes the trace to its own stderr; the traced command's output goes to `log` and its exit code to `log`.rc, so the pipe this module reads carries strace lines and nothing else, and pytest's end is visible while strace is still running."""
    return [
        "strace",
        "-f",
        "-qq",
        "-y",
        "--seccomp-bpf",
        "-e",
        "status=successful",
        "-e",
        "trace=" + STRACE_SYSCALLS,
        # Through -o, so every line carries the `<pid> ` prefix `-f` gives a file; on bare stderr the prefix is `[pid N]` and the first process has none.
        "-o",
        "/dev/stderr",
        "--",
        "sh",
        "-c",
        '"$@" >"$0" 2>&1; echo $? >"$0.rc"',
        log,
        *inner,
    ]


# How long a process may outlive pytest under the trace before it is killed. `strace -f` exits only when EVERY tracee has, so an orphan a test leaked (wl_git.py's selftest leaves `tail -f /dev/null` as a git editor, seen 2026-11-18) would hold the trace open forever.
ORPHAN_GRACE_S = 10.0
LEAKED_PREFIX = "pytest-impact-reads: outlived pytest under the trace and was killed: "


def leaked_lines(output: str) -> list[str]:
    """The orphan lines run_trace appended to a shard's output, in order."""
    return [ln for ln in output.splitlines() if ln.startswith(LEAKED_PREFIX)]


# The strace sessions this process has running; run_trace adds and removes its own.
_LIVE: list[subprocess.Popen] = []


def session_members(sid: int, proc_root: str = "/proc") -> list[tuple[int, str]]:
    """`(pid, command line)` of every process in session `sid`, read from /proc. A process that vanishes mid-read is skipped."""
    out = []
    for name in os.listdir(proc_root):
        if not name.isdigit():
            continue
        try:
            with open(os.path.join(proc_root, name, "stat"), encoding="utf-8") as fh:
                fields = fh.read().rsplit(")", 1)[1].split()
            if int(fields[3]) != sid:
                continue
            with open(os.path.join(proc_root, name, "cmdline"), "rb") as fh:
                cmd = fh.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
        except (OSError, IndexError, ValueError):
            continue
        out.append((int(name), cmd))
    return sorted(out)


def _kill_session(sid: int, spare: int | None = None) -> list[str]:
    """SIGKILL every member of session `sid` but `spare`; the command lines killed."""
    killed = []
    for pid, cmd in session_members(sid):
        if pid in (spare, os.getpid()):
            continue
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)
            killed.append(cmd)
    return killed


def run_trace(root: pathlib.Path, pytest_argv: list[str]) -> tuple[int, Attributor, str]:
    """(pytest exit, the folded stream, pytest's output). A reader thread folds strace's stderr while pytest runs, so the log never touches disk; this thread watches for pytest's exit-code file. Once it appears, any process still running in the strace session after ORPHAN_GRACE_S was leaked by a test: it is killed, named in the output, and strace then exits. strace runs in its own session and the whole session is killed when this returns, normally or not."""
    if shutil.which("strace") is None:
        raise SystemExit(
            "pytest_impact_reads: strace is not installed; install it (apt-get install strace) and re-run"
        )
    scratch = tempfile.mkdtemp(prefix="pytest-reads-")
    child = None
    try:
        markers = os.path.join(scratch, "m")
        os.mkdir(markers)
        log = os.path.join(scratch, "pytest.log")
        rc_file = pathlib.Path(log + ".rc")
        att = Attributor(root=str(root), marker_dir=markers)
        # The environment is inherited unchanged: this module runs only as `python -m rediacc_ci...`, so whatever put `.ci` on its path puts it on pytest's, which `-p` needs before pyproject's `pythonpath` is applied.
        child = subprocess.Popen(
            # One token, `--opt=dir`: pytest decides whether any test path was given BEFORE this plugin registers its option, so a separate `dir` token reads as a test path, `testpaths` is skipped, and the marker directory is what gets collected (the 2026-11-18 full run: 18 of 927 files).
            strace_argv(log, [*pytest_argv, "%s=%s" % (MARKER_OPTION, markers)]),
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            start_new_session=True,
        )
        _LIVE.append(child)
        stream = child.stderr

        def fold() -> None:
            if stream is not None:
                for line in stream:
                    att.feed(line)

        reader = threading.Thread(target=fold, daemon=True)
        reader.start()
        leaked: list[str] = []
        ended_at = None
        while child.poll() is None:
            if ended_at is None and rc_file.exists():
                ended_at = time.monotonic()
            if ended_at is not None and time.monotonic() - ended_at > ORPHAN_GRACE_S:
                leaked = _kill_session(child.pid, spare=child.pid)
                break
            time.sleep(0.5)
        child.wait()
        reader.join()
        output = pathlib.Path(log).read_text(encoding="utf-8", errors="replace")
        try:
            rc = int(rc_file.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            rc = child.returncode or 2
        for cmd in leaked:
            output += "\n%s%s" % (LEAKED_PREFIX, cmd[:300])
    finally:
        if child is not None:
            if child.poll() is None:
                _kill_session(child.pid)
                child.wait()
            if child in _LIVE:
                _LIVE.remove(child)
        shutil.rmtree(scratch, ignore_errors=True)
    return rc, att, output


def _kill_live() -> None:
    """Kill every strace session still registered: the main thread's exit path, for shards whose own `finally` sits on a pool thread that a SystemExit in the main thread never reaches."""
    for child in _LIVE[:]:
        if child.poll() is None:
            _kill_session(child.pid)


def trace_record(att: Attributor, collected: int) -> dict:
    tests = {
        label: {
            "reads": sorted(att.reads.get(label, ())),
            "lists": sorted(att.lists.get(label, ())),
        }
        for label in sorted(set(att.reads) | set(att.lists))
        if label != UNATTRIBUTED
    }
    return {
        "schema": TRACE_SCHEMA,
        "collected": collected,
        "markers": att.markers,
        "lines": att.lines,
        "unclaimedPids": len(att.unclaimed),
        "tests": tests,
        "unattributed": {
            "reads": sorted(att.reads.get(UNATTRIBUTED, ())),
            "lists": sorted(att.lists.get(UNATTRIBUTED, ())),
        },
    }


# A traced run slows every syscall, so a test with a wall-clock bound can fail under the trace and pass without it. Such a test still read what it read before it failed, so its reads are a lower bound, as every read here is. More failures than this share of the passes is not timing: the run did not see the suite.
MAX_FAILED_FRACTION = 0.01
_FAILED_LINE = re.compile(r"^FAILED (\S+)", re.MULTILINE)


def failed_nodeids(output: str) -> list[str]:
    """The node ids pytest's `-ra` summary names as FAILED, sorted, without the ` - <message>` tail."""
    return sorted(set(_FAILED_LINE.findall(output)))


def red_run_problem(rc: int, passed: int, failed: list[str]) -> str | None:
    """Why a traced run's exit refuses its trace, or None. Exit 1 with a few named failures is accepted, and each failure is printed; any other non-zero exit (interrupted, internal error, usage, nothing collected) and a failure pytest did not name are refused."""
    if rc == 0:
        return None
    if rc != 1:
        return (
            "the traced run exited %d, which is not a test failure, so it may have stopped before reading everything"
            % rc
        )
    if not failed:
        return "the traced run exited 1 and named no FAILED test, so its failure is unexplained"
    if len(failed) > MAX_FAILED_FRACTION * max(passed, 1):
        return (
            "%d test(s) failed under the trace against %d passed, above %g%%; the run did not see the suite"
            % (
                len(failed),
                passed,
                MAX_FAILED_FRACTION * 100,
            )
        )
    return None


def trace_problem(record: dict, test_files: int) -> str | None:
    """Why a trace is not fit to derive from, or None. Zero is never a pass."""
    if record["markers"] == 0:
        return "the trace holds no marker, so the plugin never ran and no read is attributed"
    seen = len(record["tests"])
    if seen == 0:
        return "the trace attributed reads to no test file"
    if test_files and seen < MIN_ATTRIBUTED_FRACTION * test_files:
        return "the trace attributed reads to %d of %d test file(s), under %d%%" % (
            seen,
            test_files,
            MIN_ATTRIBUTED_FRACTION * 100,
        )
    return None


def _write_trace(root: pathlib.Path, record: dict) -> pathlib.Path:
    out = root / ".ci" / "cache" / "pytest-impact" / "reads-trace.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp%d" % os.getpid())
    tmp.write_text(json.dumps(record, separators=(",", ":")), encoding="utf-8")
    tmp.replace(out)
    return out


def _arg_values(argv: list[str], flag: str) -> list[str]:
    return [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == flag]


def _exit_on_term(signum: int, _frame) -> None:
    raise SystemExit(128 + signum)


def merge_attributors(parts: list[Attributor]) -> Attributor:
    """One Attributor holding every shard's reads and listings, with the counts summed. Shards partition the test FILES, so no label is split between two of them except UNATTRIBUTED, whose reads are unioned like any other."""
    out = Attributor(root=parts[0].root if parts else "", marker_dir="")
    for part in parts:
        for label, rels in part.reads.items():
            out.reads.setdefault(label, set()).update(rels)
        for label, rels in part.lists.items():
            out.lists.setdefault(label, set()).update(rels)
        out.markers += part.markers
        out.lines += part.lines
        # Pids are per shard and may repeat across shards, so each shard's unclaimed processes are re-keyed by arrival; only their count is reported.
        for events in part.unclaimed.values():
            out.unclaimed[len(out.unclaimed)] = list(events)
    return out


def merged_rc(codes: list[int]) -> int:
    """The worst exit across shards: any code that is not 0 or 1 wins (red_run_problem refuses it), then 1, then 0."""
    other = [c for c in codes if c not in (0, 1)]
    if other:
        return other[0]
    return 1 if 1 in codes else 0


def shard_files(files: list[str], shards: int) -> list[list[str]]:
    """Round-robin over the sorted files, so a directory of slow suites (the guards, the hooks) is spread over every strace instead of landing on one."""
    ordered = sorted(files)
    return [g for g in (ordered[i::shards] for i in range(shards)) if g]


def cmd_trace(root: pathlib.Path, argv: list[str]) -> int:
    # A plain SIGTERM would end this process without run_trace's `finally`, leaving strace and every tracee running in their own session (seen 2026-11-18); as an exception it unwinds through the group kill.
    signal.signal(signal.SIGTERM, _exit_on_term)
    tests = _arg_values(argv, "--tests")
    jobs = (_arg_values(argv, "--jobs") or [str(max(2, (os.cpu_count() or 2) // 2))])[-1]
    shards = int((_arg_values(argv, "--shards") or ["1"])[-1])
    pytest_bin = (_arg_values(argv, "--pytest") or [sys.executable])[-1]
    head = [
        pytest_bin,
        *(["-m", "pytest"] if pytest_bin == sys.executable else []),
        "-q",
        "-p",
        "rediacc_ci.quality.pytest_impact_reads",
        "-n",
        jobs,
    ]
    present = impact.present_files(root) or []
    test_roots = impact.testpath_roots(root)
    universe = [p for p in present if impact.is_test_file(p, test_roots)]
    if tests:
        universe = [
            p for p in universe if any(p == t or p.startswith(t.rstrip("/") + "/") for t in tests)
        ]
    # ONE strace serializes every ptrace stop in the suite: on 2026-11-18 it sat at 90% of one core with the machine at load 21 of 24. Shards are separate straces over disjoint test files.
    groups = shard_files(universe, shards) if shards > 1 else [tests]
    if shards > 1:
        print(
            "pytest-impact-reads: %d shard(s) of %s test file(s), -n %s each"
            % (len(groups), "/".join(str(len(g)) for g in groups), jobs)
        )
    # The pool is shut down only after the live sessions are killed: a SIGTERM raises in this thread while every shard thread is blocked on its strace, and `with ThreadPoolExecutor` would wait for them first (seen 2026-11-18: the CLI outlived its TERM with four straces running).
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=len(groups))
    try:
        futures = [pool.submit(run_trace, root, [*head, *g]) for g in groups]
        results = [f.result() for f in futures]
    except BaseException:
        _kill_live()
        raise
    finally:
        pool.shutdown(wait=True)
    rc = merged_rc([r[0] for r in results])
    att = merge_attributors([r[1] for r in results])
    output = "\n".join(r[2] for r in results)
    collected = sum(int(m[-1]) for m in (re.findall(r"(\d+) passed", r[2]) for r in results) if m)
    failed = failed_nodeids(output)
    record = trace_record(att, collected)
    record["failed"] = failed
    record["shards"] = len(groups)
    # Printed on every verdict and kept in the record: a test that leaks a process is a defect in that test, and the green path is where it would otherwise go unseen.
    record["leaked"] = leaked_lines(output)
    for line in record["leaked"]:
        print(line)
    print(
        "pytest-impact-reads: pytest rc %d, %d passed, %d strace line(s), %d marker(s), %d of %d test file(s) attributed, %d unclaimed pid(s)"
        % (
            rc,
            collected,
            att.lines,
            att.markers,
            len(record["tests"]),
            len(universe),
            len(att.unclaimed),
        )
    )
    red = red_run_problem(rc, collected, failed)
    if red:
        print(output[-3000:], file=sys.stderr)
        print("pytest-impact-reads: %s; nothing written" % red, file=sys.stderr)
        return 1
    for nodeid in failed:
        print("pytest-impact-reads: failed under the trace, its reads may be partial: %s" % nodeid)
    problem = trace_problem(record, len(universe))
    if problem:
        print("pytest-impact-reads: %s; nothing written" % problem, file=sys.stderr)
        return 1
    print("pytest-impact-reads: wrote %s" % _write_trace(root, record).relative_to(root))
    return 0


def cmd_derive(root: pathlib.Path, argv: list[str]) -> int:
    trace_path = root / ".ci" / "cache" / "pytest-impact" / "reads-trace.json"
    try:
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(
            "pytest-impact-reads: no usable trace at %s (%s); run --trace first"
            % (TRACE_RELPATH, exc),
            file=sys.stderr,
        )
        return 1
    tree = read_tree(root)
    present = impact.present_files(root)
    if tree is None or present is None:
        print("pytest-impact-reads: git ls-files failed", file=sys.stderr)
        return 1
    impact_map, _ = impact.load_or_build_map(root, present)
    test_roots = impact.testpath_roots(root)
    problem = trace_problem(trace, len(impact_map["tests"]))
    if problem:
        print("pytest-impact-reads: %s" % problem, file=sys.stderr)
        return 1
    reads = derive_reads(trace, impact_map, tree)
    gate = derive_paths(trace, impact_map, tree, test_roots)
    entries = sum(len(v) for v in reads.values())
    print(
        "pytest-impact-reads: reads for %d of %d test file(s), %d entr(y/ies); paths %d glob(s), lists %d dir(s)"
        % (len(reads), len(impact_map["tests"]), entries, len(gate["paths"]), len(gate["lists"]))
    )
    for nodeid in trace.get("failed", []):
        print("pytest-impact-reads: failed under the trace, its reads may be partial: %s" % nodeid)
    print(json.dumps(gate, indent=1))
    if "--write" in argv:
        policy_path = root / impact.POLICY_RELPATH
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["readsOrigin"] = (
            "PYTHONPATH=.ci python3 -m rediacc_ci.quality.pytest_impact_reads --trace, then --derive --write (strace per test file, PLAN-ciquick-cpu W4.3); a memoized read is attributed only to the first test file that made it"
        )
        policy["reads"] = reads
        policy_path.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
        print("pytest-impact-reads: wrote reads into %s" % impact.POLICY_RELPATH)
    return 0


def main(argv: list[str]) -> int:
    root = paths.repo_root()
    if "--trace" in argv:
        try:
            return cmd_trace(root, argv)
        finally:
            _kill_live()
    if "--derive" in argv:
        return cmd_derive(root, argv)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
