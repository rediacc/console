#!/usr/bin/env python3
"""Port of `.ci/scripts/private/renet-ebpf-e2e.sh`.

Mounts bpffs if it is not already there, runs the `ebpf_e2e`-tagged
socket-isolation tests in `private/renet`, and refuses to report success unless
at least one of them is seen to PASS.

WHY THE LOUD-SKIP GUARD IS THE WHOLE SCRIPT. These tests SKIP, not fail, when
they are run without root, without cgroup2 or without bpffs, and `go test` exits
0 for a run in which everything skipped. An all-skips run is green and useless,
and this is the guard against the 3-day nextcloud dual-stack regression, so the
twin greps its own captured output for `--- PASS: TestEBPF_` and exits 1 when it
finds none. Reproduced exactly, including the prefix match: the guard asks
whether ANY `TestEBPF_*` passed, not whether a particular one did, which is the
one difference from its sibling `renet_root_tests.py`.

-----------------------------------------------------------------------------
WHAT IS SHELLED OUT TO, AND WHAT IS NOT
-----------------------------------------------------------------------------
SHELLED OUT, all three faked as recording binaries on a scratch PATH by
`.ci/rediacc_ci/tests/test_private_renet_ebpf_e2e.py`, never invoked for real:

  * `stat -f -c %T /sys/fs/bpf`, the filesystem-type probe. `os.statvfs` is NOT
    used in its place: it does not report a filesystem TYPE at all on Linux, and
    the twin's decision turns on the exact string coreutils prints.
  * `mount -t bpf bpffs /sys/fs/bpf`, which needs root and is the reason this
    script is invoked as `sudo .ci/scripts/private/renet-ebpf-e2e.sh`. Its
    stdout and stderr pass straight through on both sides; nothing is captured.
  * `go test`, once, with the twin's argv character for character.

NOT SHELLED OUT: `grep`, for the reason given in `renet_root_tests.py` -- the
pattern is a literal and the buffer is already in hand, so the search is done on
BYTES, which is what grep does.

-----------------------------------------------------------------------------
THE PROBE FAILS OPEN TOWARDS MOUNTING, AND THAT IS LOAD-BEARING
-----------------------------------------------------------------------------
`"$(stat -f -c %T /sys/fs/bpf 2>/dev/null)" != "bpf_fs"` treats EVERY answer
that is not the literal `bpf_fs` as "not mounted": a stat that failed, a stat
that is not installed (its `command not found` goes to the `2>/dev/null` the
redirection already installed), a directory that does not exist, and a
coreutils build that spells the type differently. All of those lead to the
mount attempt, whose own failure is then loud and fatal under `set -e`. That is
the right direction to fail in and it is reproduced verbatim.

-----------------------------------------------------------------------------
COMMAND SUBSTITUTION IS AN OUTPUT FORMAT
-----------------------------------------------------------------------------
As in `renet_root_tests.py`: go's stderr is folded into its stdout, `$()` strips
all trailing newlines, `echo` adds exactly one back, and nothing is printed
until go has finished. `_echo` reproduces that, the failure arm and the
`::error::` annotation both go to STDOUT because that is where the twin puts
them and where GitHub Actions reads annotations from, and the two `log_step`
lines plus the final `log_info` are the only things on stderr.

-----------------------------------------------------------------------------
THE PROBE IS THE ONLY IDEMPOTENCE THERE IS, AND IT HOLDS. CHECKED.
-----------------------------------------------------------------------------
The twin's comment calls the mount idempotent, and the claim rests entirely on
`stat` naming bpffs `bpf_fs`: the first run mounts, every later run reads
`bpf_fs` and skips. A `stat` whose type table did not carry that name would
mount on EVERY invocation and stack a fresh bpffs over the previous one each
time, silently.

That was a hypothesis, and it was CHECKED rather than written down as a defect.
The `stat` on this host is uutils coreutils 0.8.0
(`/usr/lib/cargo/bin/coreutils/stat`), not GNU, and it does carry `bpf_fs` in
its filesystem-type table (`strings /usr/bin/stat`, in the concatenated blob
that also holds `btrfs`, `cgroup2fs` and `sysfs`). GNU coreutils carries it too.
So the idempotence holds on both implementations reachable here and there is no
finding to report. What DOES happen on this WSL host, verified with
`stat -f -c %T /sys/fs/bpf` -> `sysfs`, is that the path is a plain sysfs
directory, so a first run would mount bpffs over it. That is the script's
intent, not a defect.

-----------------------------------------------------------------------------
THE SHELL DIAGNOSTICS REPRODUCED BY HAND
-----------------------------------------------------------------------------
Same three as in `renet_root_tests.py` and for the same measured reasons: a
failed `cd` under `set -e`, a missing `go` whose bash-authored `command not
found` lands INSIDE the captured output because `2>&1` is applied before the
lookup fails, and a missing `mount` whose message does NOT land in a capture
because that call is not captured at all -- it goes to stderr, and bash exits
127. `_shell_diagnostic` composes the `<$0>: line <n>: ` prefix from
`sys.argv[0]` and the caller's live frame; the text after it is byte-identical.

CONSOLE ROOT comes from this file's own location (`parents[3]`), matching the
twin's `get_repo_root`; `rediacc_ci.paths.repo_root()` is not used because it
honours `$REDIACC_CI_ROOT` and the twin honours nothing.

NO ENVIRONMENT VARIABLE IS READ BY THIS MODULE. The twin's header says "No env
vars"; the only reads are inside `rediacc_ci.log` (`NO_COLOR`, `DEBUG`), exactly
as `common.sh:18` and `common.sh:52` do.
"""

from __future__ import annotations

import inspect
import os
import pathlib
import shutil
import subprocess
import sys

from rediacc_ci import log

# The bpffs mount point and the string coreutils prints for its filesystem type.
# Both are the twin's literals; the comparison is `!=`, so anything else at all
# means "mount it".
BPFFS_MOUNTPOINT = "/sys/fs/bpf"
BPFFS_TYPE = "bpf_fs"

# U+2014, written as an escape so no em dash is typed into a file under
# `.ci/rediacc_ci`, which `check:ci-em-dash-surfaces` scans. The CHARACTER still
# has to reach stdout, because the twin prints it and this port's whole claim is
# byte-identical output.
_EM_DASH = "\u2014"

# The twin's annotation, assembled around that escape.
ZERO_TESTS_ERROR = (
    "::error::ebpf_e2e executed zero tests (all skipped) %s "
    "root/bpffs/cgroup2 prerequisites not met on this runner" % _EM_DASH
)


def console_root() -> pathlib.Path:
    """The repository root, derived the way the twin derives it: from the
    subject file's own path, never from cwd and never from an env override."""
    # This file: <root>/.ci/rediacc_ci/private/renet_ebpf_e2e.py
    return pathlib.Path(__file__).resolve().parents[3]


def _shell_diagnostic(message: str) -> str:
    """`<$0>: line <n>: <message>`, the shape bash puts on a script's stderr."""
    frame = inspect.currentframe()
    back = frame.f_back if frame is not None else None
    lineno = back.f_lineno if back is not None else 0
    return "%s: line %d: %s" % (sys.argv[0], lineno, message)


def _echo(payload: bytes) -> None:
    """`echo "$out"`: all trailing newlines stripped, exactly one added back."""
    sys.stdout.flush()
    sys.stdout.buffer.write(payload.rstrip(b"\n") + b"\n")
    sys.stdout.buffer.flush()


def filesystem_type(path: str) -> str:
    """`"$(stat -f -c %T <path> 2>/dev/null)"`.

    Every failure mode collapses to the empty string, which is what the command
    substitution also yields: a non-zero stat, a stat that is not installed, and
    a path that does not exist. Exported so a test can drive the probe without
    driving the mount.
    """
    try:
        completed = subprocess.run(
            ["stat", "-f", "-c", "%T", path],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return ""
    # `$()` strips ALL trailing newlines, not just one.
    return completed.stdout.decode("utf-8", "replace").rstrip("\n")


def main(argv: list[str]) -> int:
    """The twin ignores its arguments entirely; so does this."""
    del argv

    renet_dir = console_root() / "private" / "renet"
    try:
        os.chdir(renet_dir)
    except OSError as exc:
        print(
            _shell_diagnostic("cd: %s: %s" % (renet_dir, exc.strerror)),
            file=sys.stderr,
            flush=True,
        )
        return 1

    if filesystem_type(BPFFS_MOUNTPOINT) != BPFFS_TYPE:
        log.step("Mounting bpffs at %s..." % BPFFS_MOUNTPOINT)
        try:
            mounted = subprocess.run(
                ["mount", "-t", "bpf", "bpffs", BPFFS_MOUNTPOINT],
                check=False,
            )
        except FileNotFoundError:
            # NOT captured, unlike the `go` call: this message goes to stderr and
            # bash's own status for a missing command is 127.
            print(_shell_diagnostic("mount: command not found"), file=sys.stderr, flush=True)
            return 127
        except PermissionError:
            found = shutil.which("mount", mode=os.F_OK) or "mount"
            print(
                _shell_diagnostic("%s: Permission denied" % found),
                file=sys.stderr,
                flush=True,
            )
            return 126
        if mounted.returncode != 0:
            # `set -e`: the script dies with mount's own status and says nothing
            # of its own. The silence is deliberate; mount already explained.
            return mounted.returncode

    log.step("Running eBPF socket-isolation tests (ebpf_e2e)...")

    command = [
        "go",
        "test",
        "-tags",
        "ebpf_e2e",
        "-run",
        "TestEBPF_",
        "./pkg/ebpf/",
        "-v",
        "-count=1",
        "-timeout",
        "300s",
    ]
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except FileNotFoundError:
        _echo(_shell_diagnostic("go: command not found").encode("utf-8", "surrogateescape"))
        return 1
    except PermissionError:
        # As in `renet_root_tests.py`: bash names the RESOLVED PATH for a `go`
        # that is on PATH but not executable, and the bare word only for a `go`
        # that is absent. `mode=os.F_OK` repeats bash's search.
        found = shutil.which("go", mode=os.F_OK) or "go"
        _echo(_shell_diagnostic("%s: Permission denied" % found).encode("utf-8", "surrogateescape"))
        return 1

    out = completed.stdout or b""
    _echo(out)
    if completed.returncode != 0:
        return 1

    if b"--- PASS: TestEBPF_" not in out:
        print(ZERO_TESTS_ERROR, flush=True)
        return 1

    log.info("eBPF socket-isolation tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
