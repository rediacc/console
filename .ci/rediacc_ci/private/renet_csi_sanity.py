#!/usr/bin/env python3
"""Port of `.ci/scripts/private/renet-csi-sanity.sh`.

Builds a scratch loop-BTRFS datastore, runs the CSI driver conformance suite
(csi-sanity, spec 09 section 12) against it, and refuses to report success
unless the transcript proves specs actually EXECUTED.

THE BASH TWIN REMAINS THE LIVE CALL SITE. `.github/workflows/ct-tests.yml:1758`
spells `run: sudo .ci/scripts/private/renet-csi-sanity.sh`, and nothing else in
the tree invokes either subject. THIS MODULE CARRIES NO `---- gate ----` HEADER,
and neither does the twin: this is a workflow step, not a registered gate.
Cutover is a separate, later, driver-only step.

-----------------------------------------------------------------------------
THE LOUD-SKIP GUARD IS THE POINT OF THE SCRIPT
-----------------------------------------------------------------------------
`go test` exits 0 for a run in which every spec skipped, and the ginkgo suite
behind `TestCSISanity` skips itself entirely off-root or off-BTRFS. So a bare
exit-code check would report conformance on any machine that could not host the
test at all. The twin therefore asserts TWO things about its own captured
transcript, in order, and each failure is its own `::error::` annotation:

    Ran [1-9][0-9]* of [0-9]+ Specs   -> a NON-ZERO executed count
    --- PASS: TestCSISanity           -> and the Go test itself passed

Both are reproduced exactly, including the order, and including the fact that
the first one to fail wins and the second is never evaluated.

THE MATCHING IS DONE ON BYTES, not on a decoded string, which is what `grep`
does. A transcript that is not valid UTF-8 therefore cannot change the verdict
or raise. The first pattern is a real ERE and is spelled as one; the second is a
literal (`grep -q --` with no `-E`), so it is a byte containment test and the
leading `---` cannot be read as an option.

-----------------------------------------------------------------------------
TWO SPECS ARE SKIPPED BY DESIGN, AND THE STRING IS CONTRACT
-----------------------------------------------------------------------------
`SKIP_SPECS` names the two RULED deviations of spec 09 section 16
(CSI-DEVIATION-1 max-length name, CSI-DEVIATION-2 snapshot same-name-different-
source), each already covered by a dedicated Go unit test. It reaches ginkgo as
ONE argument after `-args`, alternation pipe and spaces intact, and the
differential compares the recorded argv character for character: a port that
word-split it would silently run 50 of 50 and go red for a reason that has
nothing to do with the driver.

-----------------------------------------------------------------------------
WHAT IS SHELLED OUT TO, AND WHY ALL OF IT IS
-----------------------------------------------------------------------------
`apt-get`, `umount`, `truncate`, `mkfs.btrfs`, `mkdir`, `mount` and `go`, each
with the twin's argv verbatim. `mkdir -p` could have been `os.makedirs` and
`truncate` could have been `os.truncate`; neither is done, because the recorded
call log is the only place the datastore setup is observable at all and a port
that performed the same effect by another route would pass a stdout-only
comparison while diverging on anything a fake, a strace or an audit log sees.

`command -v mkfs.btrfs` / `command -v cryptsetup` become `shutil.which`, which
asks the same question of the same PATH with the same X_OK test. The twin checks
BOTH names with two separate `command -v` calls rather than handing two names to
one helper, so it does NOT have the `require_cmd`-only-validates-its-first-
argument defect that runs through much of this tree.

-----------------------------------------------------------------------------
COMMAND SUBSTITUTION IS AN OUTPUT FORMAT, NOT JUST A CAPTURE
-----------------------------------------------------------------------------
`out="$(... 2>&1)"` then `echo "$out"` has three consequences, all visible:

  * go's stderr is folded into go's STDOUT, so the script's own stderr carries
    only the three log lines and nothing the toolchain wrote.
  * `$()` strips ALL trailing newlines and `echo` adds exactly one back, so a
    run ending in three blank lines and one ending in none produce identical
    bytes. `_echo` reproduces that; a run with no output at all still emits one
    newline.
  * NOTHING IS PRINTED UNTIL GO HAS FINISHED, on both sides. A 600-second run is
    silent for 600 seconds. Streaming would be friendlier and would also be a
    divergence.

BOTH `::error::` LINES GO TO STDOUT, deliberately: that is the twin's behaviour
and it is what the GitHub Actions annotation form requires.

THE FAILING GO RUN LOSES ITS EXIT CODE. `|| { echo "$out"; exit 1; }` turns any
non-zero go status into 1. Driven with a fake exiting 2: the script exits 1.
Reproduced, and reported as a (minor) finding against the twin rather than
fixed here.

-----------------------------------------------------------------------------
A FAILING `apt-get update` IS SWALLOWED, AND THAT IS THE ONE TO READ TWICE
-----------------------------------------------------------------------------
`apt-get update -qq && apt-get install -y -qq btrfs-progs cryptsetup-bin` looks
like one guarded install under `set -e`. It is not. `set -e` is IGNORED for any
member of an AND-OR list other than the LAST, and bash does not fire on the
list's own status in this position either, so a failed `update` short-circuits
the `install` and THE SCRIPT CARRIES ON. Reproduced 2026-09-14 with a fake
`apt-get` failing only its `update` subcommand and only `cryptsetup` absent: the
script printed "Installing btrfs-progs + cryptsetup...", installed nothing, ran
the suite and exited 0 with "csi-sanity conformance passed".

The `install` arm does NOT have this property, because it IS the last member.
Both halves are pinned by the differential.

This is a REAL DEFECT in the twin, reported rather than repaired: a port whose
verdict differed from its twin's would not be a port, and the repair belongs to
a cutover box.

-----------------------------------------------------------------------------
ENVIRONMENT
-----------------------------------------------------------------------------
Two variables are read, each with `os.environ.get` at the call site rather than
through any `env = dict(os.environ)` alias, so the env-registry AST scanner can
see the names:

    CSI_SANITY_IMG   default /tmp/csi-btrfs.img
    CSI_SANITY_BASE  default /mnt/csi-sanity

`${VAR:-default}` means UNSET OR EMPTY both take the default, so
`CSI_SANITY_BASE=""` selects `/mnt/csi-sanity` rather than the empty string.

`REDIACC_CSI_SANITY_BASE=... go test ...` is a PER-COMMAND assignment, not an
`export`: it reaches `go` and nothing else, and this process's own environment
is left alone. `_go_env` is the whole of that, and it is the one place a
materialised copy of the environment is correct.
"""

from __future__ import annotations

import inspect
import os
import pathlib
import re
import shutil
import subprocess
import sys

from rediacc_ci import log

# `CSI_IMG="${CSI_SANITY_IMG:-/tmp/csi-btrfs.img}"` and its neighbour.
DEFAULT_IMG = "/tmp/csi-btrfs.img"
DEFAULT_BASE = "/mnt/csi-sanity"

# The variable `go test` reads to find the datastore. Set for that child only.
BASE_ENV = "REDIACC_CSI_SANITY_BASE"

# The two ruled-deviation specs (spec 09 section 16) that stay red by design.
# ONE string, one argument, pipe and spaces intact. Do NOT reflow it.
SKIP_SPECS = (
    "should not fail when creating volume with maximum-length name"
    "|should fail when requesting to create a snapshot with already existing "
    "name and different source volume ID"
)

# `grep -qE 'Ran [1-9][0-9]* of [0-9]+ Specs'`, as bytes. A LEADING DIGIT OF
# ZERO IS EXCLUDED ON PURPOSE: "Ran 0 of 50 Specs" is the whole failure this
# guard exists for, and `[0-9]+` in its place would accept it.
RAN_SPECS = re.compile(rb"Ran [1-9][0-9]* of [0-9]+ Specs")

# `grep -q -- '--- PASS: TestCSISanity'`. A literal, not a pattern.
PASSED = b"--- PASS: TestCSISanity"

# U+2014 SPELLED AS AN ESCAPE, NOT AS THE CHARACTER. The twin's annotation
# carries a literal em dash; this tree's `check:ci-em-dash-surfaces` scans
# `.ci/rediacc_ci/**/*.py` against a shrink-only baseline, so a literal here
# would be a NEW finding in a gate that is right to object. The escape emits the
# identical byte sequence, which is what the differential compares.
ZERO_SPECS_ERROR = "::error::csi-sanity ran zero specs \u2014 root/BTRFS prerequisites not met"
NOT_PASSED_ERROR = "::error::csi-sanity did not PASS"


def console_root() -> pathlib.Path:
    """The repository root, derived the way the twin derives it: from the
    subject file's own path, never from cwd and never from an env override."""
    # This file: <root>/.ci/rediacc_ci/private/renet_csi_sanity.py
    return pathlib.Path(__file__).resolve().parents[3]


def _shell_diagnostic(message: str) -> str:
    """`<$0>: line <n>: <message>`, the shape bash puts on a script's stderr.

    The line number is the CALLER's, taken from the live frame rather than
    hard-coded, so it cannot go stale when this file is reflowed.
    """
    frame = inspect.currentframe()
    back = frame.f_back if frame is not None else None
    lineno = back.f_lineno if back is not None else 0
    return "%s: line %d: %s" % (sys.argv[0], lineno, message)


def _echo(payload: bytes) -> None:
    """`echo "$out"`: all trailing newlines stripped, exactly one added back."""
    sys.stdout.flush()
    sys.stdout.buffer.write(payload.rstrip(b"\n") + b"\n")
    sys.stdout.buffer.flush()


class _MissingToolError(Exception):
    """The tool was not on PATH. Bash's `command not found`, as control flow."""


def _run(argv: list[str]) -> int:
    """One foreground command, its status returned. ENOENT raises, and does not exit.

    Separated from the `set -e` wrapper below so the umount arm, which swallows
    both the status AND the missing-command case, can reuse it.
    """
    try:
        return subprocess.run(argv, check=False).returncode
    except FileNotFoundError as exc:
        raise _MissingToolError(argv[0]) from exc


def _strict(argv: list[str]) -> int:
    """`set -e` around one command: 0 to continue, non-zero to exit with.

    A missing binary becomes bash's own diagnostic on STDERR and status 127,
    which is what bash does and what a caller greps for. Anything else is the
    command's own status, propagated unchanged.
    """
    try:
        return _run(argv)
    except _MissingToolError as exc:
        print(_shell_diagnostic("%s: command not found" % exc.args[0]), file=sys.stderr, flush=True)
        return 127


def _go_env(base: str) -> dict[str, str]:
    """The environment `go test` gets: this process's, plus the one assignment.

    A materialised copy is CORRECT here and nowhere else in the file. The twin
    writes `REDIACC_CSI_SANITY_BASE="$CSI_MNT" go test ...`, a per-command
    assignment: the child sees it, this process does not, and no later child
    does either. Building it as an explicit `env=` is exactly that, whereas
    mutating `os.environ` would reproduce an `export` the twin did not write.
    """
    env = dict(os.environ)
    env[BASE_ENV] = base
    return env


def go_command() -> list[str]:
    """The `go test` argv, verbatim from the twin. Exported so the differential
    can assert against it without reading this module's private state."""
    return [
        "go",
        "test",
        "-tags",
        "root",
        "-run",
        "TestCSISanity",
        "./pkg/kubecsi/",
        "-v",
        "-count=1",
        "-timeout",
        "600s",
        "-args",
        "-ginkgo.skip=%s" % SKIP_SPECS,
    ]


def main(argv: list[str]) -> int:
    """The twin ignores its arguments entirely; so does this, and `argv` is
    accepted only so the signature matches every other module in the package."""
    del argv

    # `${VAR:-default}`: unset OR EMPTY takes the default. Read at the call
    # site, one `os.environ.get` per name, never through an alias.
    csi_img = os.environ.get("CSI_SANITY_IMG", "") or DEFAULT_IMG
    csi_mnt = os.environ.get("CSI_SANITY_BASE", "") or DEFAULT_BASE

    if shutil.which("mkfs.btrfs") is None or shutil.which("cryptsetup") is None:
        log.step("Installing btrfs-progs + cryptsetup...")
        # `apt-get update -qq && apt-get install -y -qq ...`, AND THE ASYMMETRY
        # IS REAL RATHER THAN A TRANSCRIPTION SLIP. `set -e` is IGNORED for any
        # member of an AND-OR list other than the last, and bash does not fire
        # on the list's own status in this position either, so:
        #
        #   update fails  -> the list short-circuits, the install never runs,
        #                    AND THE SCRIPT CARRIES ON as though it had.
        #   install fails -> it IS the last member, so `set -e` exits with it.
        #
        # Driven both ways 2026-09-14 before this branch was written; the
        # differential pins both. The first arm is a REAL DEFECT in the twin --
        # with only `cryptsetup` missing the run then reaches the end and prints
        # "conformance passed" having installed nothing -- and it is reproduced,
        # not repaired, because repairing a twin is a cutover-box decision.
        if _strict(["apt-get", "update", "-qq"]) == 0:
            rc = _strict(["apt-get", "install", "-y", "-qq", "btrfs-progs", "cryptsetup-bin"])
            if rc != 0:
                return rc

    log.step("Creating scratch loop-BTRFS datastore at %s..." % csi_mnt)

    # `umount "$CSI_MNT" 2>/dev/null || true`. THREE things are swallowed here
    # and the third is easy to miss: the status, the stderr, AND the
    # command-not-found case, because bash's own diagnostic goes to the stderr
    # that `2>/dev/null` discards and `|| true` eats the 127. Driven.
    try:
        with open(os.devnull, "wb") as devnull:
            subprocess.run(["umount", csi_mnt], stderr=devnull, check=False)
    except FileNotFoundError:
        pass

    for step in (
        ["truncate", "-s", "4G", csi_img],
        ["mkfs.btrfs", "-q", "-f", csi_img],
        ["mkdir", "-p", csi_mnt],
        ["mount", "-o", "loop", csi_img, csi_mnt],
    ):
        rc = _strict(step)
        if rc != 0:
            return rc

    log.step("Running csi-sanity conformance suite...")

    renet_dir = console_root() / "private" / "renet"
    try:
        os.chdir(renet_dir)
    except OSError as exc:
        # `set -e` on a failed `cd`: bash's own diagnostic, then status 1.
        print(
            _shell_diagnostic("cd: %s: %s" % (renet_dir, exc.strerror)),
            file=sys.stderr,
            flush=True,
        )
        return 1

    try:
        completed = subprocess.run(
            go_command(),
            env=_go_env(csi_mnt),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except FileNotFoundError:
        # `2>&1` is applied BEFORE the lookup fails, so bash's `command not
        # found` lands INSIDE the capture and is echoed to stdout by the `||`
        # arm, with status 1. Verified directly, not assumed.
        _echo(_shell_diagnostic("go: command not found").encode("utf-8", "surrogateescape"))
        return 1

    out = completed.stdout or b""
    _echo(out)
    if completed.returncode != 0:
        # THE STATUS IS FLATTENED TO 1, which is the twin's `exit 1` and loses
        # go's own code. Reproduced; reported as a finding, not fixed here.
        return 1

    if not RAN_SPECS.search(out):
        print(ZERO_SPECS_ERROR, flush=True)
        return 1
    if PASSED not in out:
        print(NOT_PASSED_ERROR, flush=True)
        return 1

    log.info("csi-sanity conformance passed (48/50; 2 ruled deviations skipped per spec 09 §16)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
