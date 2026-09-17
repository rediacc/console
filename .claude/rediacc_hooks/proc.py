#!/usr/bin/env python3
"""Reading the process table, for the two guards that refuse to corrupt a
running script.

WHO NEEDS THIS. `block-bash-write-to-running-script.sh` and
`block-edit-of-running-script.sh` cover the two doors -- Bash and Edit -- onto
the same failure: bash reads a script LAZILY, by byte offset, so rewriting it
mid-run makes the interpreter resume at its old offset inside the new bytes
and die parsing mid-token, naming an INNOCENT line while `bash -n` on that same
file stays clean. Documented at docs/agent-reference/TRAPS.md, hit three times
on 2026-08-26/27 and again on 2026-08-09.

Both guards answer the same question three ways, and this module is those three
reads with nothing else attached:

    pgrep -f -- "$PAT"                 which processes match at all
    ps -o comm= -p "$rpid"             is it an interpreter, or something that
                                       merely MENTIONS the name
    tr '\\0' ' ' < /proc/$rpid/cmdline  the argv, to check the name sits in the
                                       first few slots where a script argument
                                       lives rather than buried in a prose
                                       payload

THE SECOND AND THIRD READS ARE NOT DECORATION. `pgrep -af` matches any process
whose ARGUMENTS mention the name, which is the very trap the guards exist to
prevent wearing a different hat: on 2026-08-27 an edit to the hook suite was
refused because a PEER session's `claude -p` carried a long prompt containing
that filename, and no interpreter was executing the script at all. So a match
is only a match when the process IS a shell and the name sits in the first few
argv slots.

WHY A BACKEND SEAM. `/proc` does not exist on macOS, and a hook that silently
finds nothing is worse than one that refuses: it reports "no process is running
this script" for every script, forever, and the guard becomes a no-op that
still looks green. `REDIACC_PROC_BACKEND` selects `proc` or `ps` explicitly and
`auto` (the default) probes for `/proc/self/cmdline`, so a test on Linux can
force the macOS path and prove it agrees rather than trusting that it would.

WHAT THE TWO BACKENDS CANNOT AGREE ON, stated rather than smoothed over:

  * `comm` is truncated to 15 characters by the kernel on Linux, in both
    `/proc/<pid>/comm` and `ps -o comm=` (`init-systemd(Ub` is a real row from
    this machine). macOS `ps -o comm=` prints a full PATH instead, so the ps
    backend takes its basename -- otherwise `/bin/bash` would fail the guards'
    `case ... in bash|sh|dash)` test on macOS while passing on Linux.
  * `ps -o args=` shows argv joined by single spaces and cannot say where the
    NUL separators were, so an argument CONTAINING a space is indistinguishable
    from two arguments. `/proc` has the same limitation the moment `tr` runs
    over it, which is what the guards do, so the two agree on the string the
    guards actually match against.
  * A process whose cmdline is empty (a kernel thread) is invisible to
    `pgrep -f`: measured on this machine, `pgrep -f '^$'` matches nothing.
    Both backends reproduce that by skipping empty cmdlines.

A NAME COLLISION, REPORTED RATHER THAN RESOLVED HERE. `.ci/rediacc_ci/proc.py`
landed in the same window and is a DIFFERENT thing: running a command, bounding
it in time and retrying it (the `run`/`timeout`/`retry` family). This module
READS the process table and starts nothing. Both are `proc`, and a guard that
later imports both will read `from rediacc_ci import proc` and
`from rediacc_hooks import proc` in one file. The filename here is the one the
workstream brief specifies, so it is kept and the clash is handed to the root
driver; `proctable` would be the unambiguous name for this one.
"""

import os
import pathlib
import re
import subprocess

BACKEND_ENV = "REDIACC_PROC_BACKEND"

# The interpreters the two guards accept as "actually running the script".
# Kept here beside the reads so the guard port does not grow a second copy;
# the guards themselves spell it `case "$(ps -o comm= -p "$rpid")" in
# bash | sh | dash | zsh | ksh)`.
SHELL_COMMS = ("bash", "sh", "dash", "zsh", "ksh")


class ProcError(RuntimeError):
    """The process table could not be read at all.

    Distinct from "nothing matched" on purpose. A guard that cannot see the
    process table must say so; treating the two as the same is how a guard
    becomes a permanent no-op that still exits 0.
    """


def backend_name():
    """`proc`, `ps`, or whatever `auto` resolves to on this host.

    Read at CALL time and not at import: the seam exists so a test can flip it
    between two calls in one process, and a module-level constant would freeze
    whichever value happened to be set when pytest imported the module.
    """
    choice = os.environ.get(BACKEND_ENV, "auto").strip().lower() or "auto"
    if choice == "auto":
        # The probe is a FILE READ, not `sys.platform`. A container, a WSL image or a future platform is judged by whether /proc answers, which is the thing the backend actually needs.
        return "proc" if pathlib.Path("/proc/self/cmdline").exists() else "ps"
    if choice in ("proc", "ps"):
        return choice
    msg = "%s=%r is not one of auto, proc, ps" % (BACKEND_ENV, choice)
    raise ProcError(msg)


class _ProcBackend:
    """/proc, read directly. One open() per question, like the bash."""

    name = "proc"

    def pids(self):
        try:
            entries = os.listdir("/proc")
        except OSError as exc:
            raise ProcError("cannot list /proc: %s" % exc) from exc
        return sorted(int(e) for e in entries if e.isdigit())

    def comm(self, pid):
        # /proc/<pid>/comm is the same 15-character-truncated name `ps -o comm=`
        # prints on Linux, without the fork.
        try:
            return (
                pathlib.Path("/proc/%d/comm" % pid)
                .read_text(encoding="utf-8", errors="surrogateescape")
                .rstrip("\n")
            )
        except OSError:
            # The process exited between the listing and the read. That is the normal case, not an error: a dead process is not running your script.
            return None

    def argv(self, pid):
        try:
            raw = pathlib.Path("/proc/%d/cmdline" % pid).read_bytes()
        except OSError:
            return None
        if raw == b"":
            return []
        # The kernel terminates the last argument with a NUL too, so a plain split yields a trailing empty field that is not an argument.
        parts = raw.split(b"\0")
        if parts and parts[-1] == b"":
            parts.pop()
        return [p.decode("utf-8", "surrogateescape") for p in parts]


class _PsBackend:
    """`ps`, for hosts with no /proc. One invocation answers everything.

    The whole table is fetched in a single call rather than one `ps -p <pid>`
    per question: on a machine with a few hundred processes the per-pid form is
    a few hundred forks, and the guards run on EVERY Bash and Edit call.
    """

    name = "ps"

    def __init__(self):
        self._table = None

    def _read(self):
        if self._table is not None:
            return self._table
        # `-A` every process, `ww` unlimited width (macOS truncates to the terminal width otherwise, which would silently cut the argv slots the
        # guards inspect), `-o pid=,comm=` and `-o pid=,args=` with the trailing
        # `=` suppressing the header.
        comms = self._run(["ps", "-Awwo", "pid=,comm="])
        args = self._run(["ps", "-Awwo", "pid=,args="])
        table = {}
        for line in comms.splitlines():
            pid, _, name = line.strip().partition(" ")
            if pid.isdigit():
                # macOS prints a full path here; Linux prints a truncated bare
                # name. Basename makes both mean the same thing, which is what the guards' shell-name test compares against.
                table[int(pid)] = [name.strip().rsplit("/", 1)[-1], []]
        for line in args.splitlines():
            pid, _, rest = line.strip().partition(" ")
            if pid.isdigit() and int(pid) in table:
                # Split on runs of space, which is the only thing `ps` gives back: an argument that CONTAINED a space is already indistinguishable from two, in ps and in `tr '\0' ' '` alike.
                table[int(pid)][1] = rest.strip().split(" ") if rest.strip() else []
        self._table = table
        return table

    @staticmethod
    def _run(argv):
        try:
            proc = subprocess.run(argv, capture_output=True, check=False)
        except OSError as exc:
            raise ProcError("cannot run %s: %s" % (argv[0], exc)) from exc
        if proc.returncode != 0:
            raise ProcError("%s exited %d" % (" ".join(argv), proc.returncode))
        return proc.stdout.decode("utf-8", "surrogateescape")

    def pids(self):
        return sorted(self._read())

    def comm(self, pid):
        row = self._read().get(pid)
        return None if row is None else row[0]

    def argv(self, pid):
        row = self._read().get(pid)
        return None if row is None else list(row[1])


def _backend():
    """A FRESH backend per call.

    The ps backend caches its table, which is right within one question and
    wrong across two: a guard that asked twice would be answered from a
    snapshot taken before the process it is looking for started.
    """
    return _ProcBackend() if backend_name() == "proc" else _PsBackend()


def pids():
    """Every process id visible to this user, ascending."""
    return _backend().pids()


def comm(pid):
    """`ps -o comm= -p <pid>`, or None when the process is gone."""
    return _backend().comm(pid)


def argv(pid):
    """The process's arguments as a list, or None when the process is gone."""
    return _backend().argv(pid)


def cmdline(pid):
    """The argv joined by single spaces, with NO trailing space.

    This is the string `pgrep -f` matches against: measured on this machine, a
    process running `sleep 19` matches `sleep 19$` and does NOT match
    `sleep 19 $`, so pgrep drops the final NUL rather than mapping it to a
    space.
    """
    parts = argv(pid)
    return None if parts is None else " ".join(parts)


def cmdline_tr(pid):
    """The `tr '\\0' ' ' < /proc/<pid>/cmdline` form, trailing space included.

    A SECOND spelling of the same data, and it earns its place: the two guards
    pipe this exact string through `cut -d' ' -f1-4` and a `grep -E`, so a port
    of them must be able to reproduce it byte for byte. The trailing space is
    invisible to both of those, which is precisely why it would be dropped by
    accident and never noticed until something else depended on it.
    """
    parts = argv(pid)
    if parts is None:
        return None
    if not parts:
        return ""
    return " ".join(parts) + " "


def is_shell(pid):
    """Whether the process IS an interpreter, rather than merely naming one.

    The guards' `case "$(ps -o comm= -p "$rpid")" in bash | sh | dash | zsh |
    ksh)` test, in one place, because both of them run it and a sibling drift
    between two copies of a guard is a documented cost in this tree (the path
    anchor reached the Edit-side guard three days after the Bash-side one).
    """
    return comm(pid) in SHELL_COMMS


def pgrep_full(pattern):
    """`pgrep -f -- <pattern>`: pids whose full command line matches.

    THE PATTERN IS AN ERE, and it is the CALLER's, unescaped. Both guards build
    it deliberately -- a bracket class on the first character so the pattern
    cannot match the shell running the hook itself, a path-boundary anchor, and
    every regex metacharacter in the rest of the basename escaped after a
    one-letter name plus `.sh` produced `[b].sh`, which matches **/bin/bash**,
    i.e. every bash process on the machine (measured 2026-09-01). Escaping it
    here would break all three.

    NOTHING IS EXCLUDED. Real pgrep hides only the pgrep process itself, never
    its parent, which is why the guards need the bracket trick at all; here
    there is no separate process to hide, and the caller is as visible as the
    hook's shell was. The trap and its defence are unchanged.
    """
    compiled = re.compile(pattern)
    backend = _backend()
    found = []
    for pid in backend.pids():
        line = backend.argv(pid)
        if not line:
            # An empty cmdline is a kernel thread, and `pgrep -f` does not match those: `pgrep -f '^$'` returns nothing on this machine.
            continue
        if compiled.search(" ".join(line)):
            found.append(pid)
    return found
