#!/usr/bin/env python3
"""Both sides of the `dev` port differential, in one file.

WHAT THIS IS FOR. `scripts/lib/shadow-gate.ts` compares two commands and rules on whether a port kept the verdict. It needs each side to PRINT what it observed, because the thing being compared is a finding multiset and not a return value. This module is the printer, and it can print either side:

    python3 .ci/rediacc_ci/dev/shadow_driver.py --side old
        drives the BASH: `source .ci/legacy/run-legacy.sh` and call `dev`.

    python3 .ci/rediacc_ci/dev/shadow_driver.py --side new
        drives the PYTHON: `rediacc_ci.dev.www.main`.

ONE FILE AND NOT TWO, on the `rediacc_ci/setup/shadow_driver.py` precedent and for the reason that file records: `.ci/rediacc_ci/quality/dead_python.py:280` admits a pre-cutover port as alive only when it is named as the NEW side of a `.ci/shadow/*.jsonl` record, and the OLD side's command is scanned for a live `.sh` twin rather than for a Python file. A separate old-side module
would be reported dead the day it landed.

WHY IT IS DRIVEN AGAINST THE FUNCTION AND NEVER THROUGH `./run.sh dev`. `.ci/scripts/test/gates/test-run-sh.sh` section 6 emits `overlap <verb>` when a verb sits in both `PORTED_VERBS` and the legacy dispatcher, so the flip is atomic: the router table gains `dev` in the same change that deletes the arm and the body. After that change there is no bash side left to drive, so this
ledger is recorded BEFORE the flip and it reaches the bash by sourcing the file, which keeps working right up to the moment the body is deleted and stops working loudly the moment after.

-----------------------------------------------------------------------------
THE SANDBOX, AND WHY BOTH SIDES NEED THE SAME ONE
-----------------------------------------------------------------------------
`dev()` calls two functions this port deliberately does not own, `check_node_version` and `ensure_deps`. Running them for real would make the differential a test of npm: `ensure_deps` installs, compiles native modules and WRITES a stamp, so the first side to run would leave the tree in the state that makes the second side take a different branch. The comparison would then be
between two different programs.

So both sides run against a SANDBOX: a copy of `.devcontainer` and of `.ci/legacy`, `.ci/config`, `.ci/scripts/lib` and `.ci/lib` in a temporary directory, with ONE file replaced. `.ci/lib/devbox.sh` is the last file both preludes source (`rediacc_ci/setup/bridge.py:PRELUDE`, and the old side below uses the same two lines), so a stub there redefines the two functions for BOTH sides
through the same seam and in the same order. Nothing else is touched, the real `log_step`, the real `set -euo pipefail` and the real dispatch order are all still the tracked file's.

The bash side finds the sandbox because `run-legacy.sh` derives `ROOT_DIR` from its own location; the Python side finds it through `$REDIACC_CI_ROOT`, which `rediacc_ci/paths.py` names as the single override for the whole package. `rediacc_ci` itself is still imported from the tree under test, so the port being compared is the tracked one.

-----------------------------------------------------------------------------
THE FOUR OBSERVATION GROUPS, AND WHAT EACH ONE WOULD CATCH
-----------------------------------------------------------------------------
  trace     The ORDERED sequence of externals: each stubbed precondition as it
            is called, then `npm` with its argv and its working directory. Not
            read off either implementation's source, and each line carries its
            ORDINAL so a swap changes two lines and the multiset comparison
            sees it. This is the group that catches a step hoisted above a
            precondition, and the one that catches `npm` still being reached
            after a precondition failed.
  out/err   Every line each side printed, on the two streams SEPARATELY. The
            step line is the only thing either implementation writes itself,
            and which stream it lands on is exactly the defect a merged
            comparison cannot see.
  rc        The exit code per scenario. `set -e` in the twin and `return rc` in
            the port are the same contract written twice; three of the
            scenarios exist only to drive it.
  cwd       `npm` inherits the INVOCATION directory rather than the repository
            root, because the twin never `cd`s. A port that helpfully moved to
            the root would work for everyone who runs it from the root, which
            is almost everyone, and silently change what npm resolves for the
            rest.

-----------------------------------------------------------------------------
THE ONE SCENARIO WHOSE TEXT IS NORMALIZED, AND WHY ONLY ITS TEXT
-----------------------------------------------------------------------------
`no-npm` removes npm from PATH. Bash reports a missing command as `<file>: line <n>: npm: command not found`, and a line number inside `run-legacy.sh` is neither reproducible by a port nor worth reproducing. The EXIT CODE is what callers and CI act on, so 127 is compared verbatim on both sides, and the text is reduced to whether the message names `npm` at all. Reducing it to
nothing would let a port fail silently; the twin's own wording is the only part given up.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from rediacc_ci import paths

# The prefix `shadow-gate --finding-re` is pointed at. Deliberately not a cross or a FAIL: those already mean "a finding" to the comparator's marker table, and an observation that AGREES is not a failure.
OBS = "obs"

EXIT_CANNOT_RUN = 77

# What the sandbox is built from. `.devcontainer` carries the toolchain pins `constants.sh` refuses to load without; `.ci/config` and `.ci/scripts/lib` are here because `run-legacy.sh` sources `constants.sh`, `toolchain.sh` and, through `local-common.sh`, `common.sh`; `.ci/lib` carries the two functions being stubbed and `service.sh`, which the twin also sources.
SANDBOX_DIRS = (
    (".devcontainer",),
    (".ci", "legacy"),
    (".ci", "config"),
    (".ci", "scripts", "lib"),
    (".ci", "lib"),
)

# The file the sandbox replaces, and the only one. Chosen because it is the LAST file both preludes source, so these definitions win over the real ones without either implementation knowing a stub exists.
STUB_TARGET = (".ci", "lib", "devbox.sh")

STUB_DEVBOX = """#!/bin/bash
# SANDBOX STUB, written by .ci/rediacc_ci/dev/shadow_driver.py. Not a library.
#
# Sourced last by both sides' prelude, so these two definitions replace the
# real ones from local-common.sh for the bash side and for every bridged call
# the Python side makes. The trace file is how their ORDER reaches the driver:
# the two sides run them in different processes, and a shared append-only file
# is the one record both shapes produce identically.
#
# DEV_STUB=0 LEAVES THE REAL ONES IN PLACE, which is how the two `real-*`
# scenarios reach `check_node_version` and `ensure_deps` as local-common.sh
# defines them. The stubbed scenarios decide ORDER and SHORT-CIRCUIT; the real
# ones decide whether the seam reaches the same function and leaves the same
# side effect behind.
if [[ "${DEV_STUB:-1}" == "1" ]]; then
    check_node_version() {
        printf 'check_node_version\\n' >>"$DEV_TRACE"
        return "${DEV_CNV_RC:-0}"
    }

    ensure_deps() {
        printf 'ensure_deps\\n' >>"$DEV_TRACE"
        return "${DEV_ED_RC:-0}"
    }
fi
"""

# A node that reports one fixed version, so `check_node_version` compares a constant against the constant floor in constants.sh instead of whatever this machine has installed.
FAKE_NODE = """#!/usr/bin/env python3
import sys

sys.stdout.write("v22.0.0\\n")
"""

# A recording npm. Its working directory is part of the record: the twin never cd's, so npm must inherit whatever directory the verb was invoked from.
FAKE_NPM = """#!/usr/bin/env python3
import os
import sys

with open(os.environ["DEV_TRACE"], "a", encoding="utf-8") as fh:
    fh.write("npm cwd=%s argv=%s\\n" % (os.getcwd(), " ".join(sys.argv[1:])))
sys.stdout.write("[fake npm] %s\\n" % " ".join(sys.argv[1:]))
sys.stderr.write("[fake npm] starting\\n")
sys.exit(int(os.environ.get("DEV_NPM_RC", "0")))
"""

# The prelude the OLD side runs, which is `rediacc_ci/setup/bridge.py:PRELUDE` line for line. Identical on purpose: a differential whose two sides source different files is comparing environments rather than implementations.
OLD_PROGRAM = """set -euo pipefail
ROOT_DIR="$REDIACC_CI_ROOT"
source "$ROOT_DIR/.ci/legacy/run-legacy.sh"
source "$ROOT_DIR/.ci/lib/devbox.sh"
dev "$@"
"""

# The NEW side, as one expression. `main` either returns an exit code or is replaced by npm, so this has to be a process of its own rather than an import into the driver.
NEW_PROGRAM = "import sys; from rediacc_ci.dev import www; sys.exit(www.main(sys.argv[1:]))"


class Scenario:
    """One comparable run: what the preconditions answer, and how it is invoked."""

    def __init__(
        self,
        name: str,
        *,
        cnv_rc: int = 0,
        ed_rc: int = 0,
        npm_rc: int = 0,
        args: tuple[str, ...] = (),
        with_npm: bool = True,
        subdir: str = "",
        stub: bool = True,
    ) -> None:
        self.name = name
        self.cnv_rc = cnv_rc
        self.ed_rc = ed_rc
        self.npm_rc = npm_rc
        self.args = args
        self.with_npm = with_npm
        self.subdir = subdir
        self.stub = stub


# NINE SCENARIOS, one per claim in the group table above. `deps-fail` and `node-fails` are the two that prove `npm` is NOT reached, which is the half of the contract a healthy machine never exercises.
#
# THE TWO `real-*` ONES RUN THE PRECONDITIONS UNSTUBBED, in this order and only in this order: `real-install` meets a sandbox with no stamp and drives the whole install path, and `real-cached` then meets the stamp the FIRST one wrote and must take the early return. Ordering them the other way would test the fast path against a tree that was never installed. They are what makes the
# ledger's finding set TREE-DERIVED: the stamp is a hash of the tree's own package.json, package-lock.json and .npmrc, so five specimens produce five fingerprints rather than one observation re-shaded five times.
SCENARIOS = (
    Scenario("happy"),
    Scenario("npm-fails", npm_rc=7),
    Scenario("node-fails", cnv_rc=1),
    Scenario("deps-fail", ed_rc=4),
    Scenario("extra-args", args=("anything", "--flag")),
    Scenario("from-subdir", subdir="packages"),
    Scenario("no-npm", with_npm=False),
    Scenario("real-install", stub=False),
    Scenario("real-cached", stub=False),
)

# Where `ensure_deps` keeps its hash stamp, relative to the root it is given (`.ci/lib/local-common.sh:205`). Read as an observation because it is the side effect the install path leaves behind, and the only tree-derived value either implementation produces.
STAMP_PATH = (".ci", "cache", "npm-install.stamp")

# The root files `ensure_deps` hashes, copied into the sandbox so the real function has something to hash. Absent from a specimen the scenario still runs and both sides still agree, but the stamp then hashes a shorter input, which is a weaker observation rather than a wrong one.
ROOT_FIXTURES = ("package.json", "package-lock.json", ".npmrc")


# Refuse rather than emit a partial row: a group that produced nothing compares equal against another group that produced nothing. DERIVED FROM THE CORPUS rather than typed, because a typed floor is lowered by whoever removes a scenario and then guards nothing. Four is the minimum any scenario emits, one per group.
OBSERVATION_FLOOR = len(SCENARIOS) * 4


def build_sandbox(root: pathlib.Path, base: pathlib.Path) -> pathlib.Path:
    """Copy what the twin sources, plant the stub, and lay out a fresh-clone tree.

    `node_modules/.bin/tsx` and the `@rediacc/cli` link are two of the four conditions `ensure_deps` tests for, and they are the two a fixture cannot get from a stamp. Creating them here leaves the STAMP as the only condition the `real-*` pair moves, which is what makes that pair a test of the stamp round trip rather than of four things at once.
    """
    sandbox = base / "sandbox"
    for parts in SANDBOX_DIRS:
        shutil.copytree(root.joinpath(*parts), sandbox.joinpath(*parts), symlinks=False)
    sandbox.joinpath(*STUB_TARGET).write_text(STUB_DEVBOX, encoding="utf-8")
    (sandbox / "packages").mkdir(parents=True, exist_ok=True)
    for name in ROOT_FIXTURES:
        source = root / name
        if source.is_file():
            shutil.copyfile(source, sandbox / name)
    binary = sandbox / "node_modules" / ".bin" / "tsx"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)
    linked = sandbox / "node_modules" / "@rediacc" / "cli"
    linked.parent.mkdir(parents=True, exist_ok=True)
    linked.symlink_to(sandbox / "packages")
    return sandbox


def build_stubs(base: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    """Two PATH directories: one carrying the fakes, one deliberately bare."""
    withnpm = base / "bin-npm"
    without = base / "bin-bare"
    withnpm.mkdir(parents=True, exist_ok=True)
    without.mkdir(parents=True, exist_ok=True)
    for name, body in (("npm", FAKE_NPM), ("node", FAKE_NODE)):
        target = withnpm / name
        target.write_text(body, encoding="utf-8")
        target.chmod(0o755)
    return withnpm, without


def scenario_env(
    scenario: Scenario, sandbox: pathlib.Path, trace: pathlib.Path, bins: tuple
) -> dict[str, str]:
    """The environment BOTH sides get. Replaced, never extended.

    A differential that inherits the caller's environment passes or fails depending on whether whoever ran it happens to export CI or NO_COLOR, which is how a test becomes green on one machine and red on another for reasons nobody can see.
    """
    withnpm, without = bins
    stub = withnpm if scenario.with_npm else without
    return {
        "PATH": "%s:/usr/bin:/bin" % stub,
        "HOME": str(sandbox),
        "LC_ALL": "C",
        "LANG": "C",
        "DEV_TRACE": str(trace),
        "DEV_CNV_RC": str(scenario.cnv_rc),
        "DEV_ED_RC": str(scenario.ed_rc),
        "DEV_NPM_RC": str(scenario.npm_rc),
        "DEV_STUB": "1" if scenario.stub else "0",
        "REDIACC_CI_ROOT": str(sandbox),
        "PYTHONPATH": str(paths.repo_root() / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def run_side(
    side: str, scenario: Scenario, sandbox: pathlib.Path, trace: pathlib.Path, bins: tuple
) -> tuple[int, str, str, list[str]]:
    """Run one scenario on one side. Returns rc, stdout, stderr and the trace."""
    trace.write_text("", encoding="utf-8")
    env = scenario_env(scenario, sandbox, trace, bins)
    cwd = sandbox / scenario.subdir if scenario.subdir else sandbox
    if side == "old":
        argv = ["bash", "-c", OLD_PROGRAM, "dev", *scenario.args]
    else:
        argv = [sys.executable, "-c", NEW_PROGRAM, *scenario.args]
    proc = subprocess.run(
        argv,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    lines = [line for line in trace.read_text(encoding="utf-8").split("\n") if line]
    return proc.returncode, proc.stdout, proc.stderr, lines


def mask(text: str, sandbox: pathlib.Path) -> str:
    """Replace the throwaway sandbox path with a stable token.

    THE ONE NORMALIZATION THAT APPLIES TO EVERY GROUP. A tempdir name differs between the two sides' runs and between one recording and the next, so it is the single token that cannot be compared. Everything else is verbatim.
    """
    for spelling in (str(sandbox), str(sandbox.resolve())):
        text = text.replace(spelling, "<sandbox>")
    return text


def emit(label: str, value: str) -> None:
    print("%s %s %s" % (OBS, label, value))


def emit_lines(label: str, text: str, sandbox: pathlib.Path) -> None:
    """One observation per line, ORDINAL first, with an empty stream said out loud."""
    lines = mask(text, sandbox).split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    if not lines:
        emit(label, "<empty>")
        return
    for index, line in enumerate(lines, start=1):
        emit("%s %02d" % (label, index), line or "<blank>")


def sandbox_base(root: pathlib.Path) -> pathlib.Path:
    """A scratch directory whose NAME is the same on both sides of the comparison.

    NOT `mkdtemp`, and this cost a real mismatch before it was found. `_sha256sum` prints `<hash> <path>`, so the stamp `ensure_deps` writes hashes the ABSOLUTE PATH of the files it read as well as their bytes. Under two randomly named temporary directories the two sides computed two different stamps from identical inputs, and the difference described the harness.

    The name is derived from the root, so two roots never collide; two concurrent runs against the SAME root would, which is why the pytest differential drives the sides in sequence exactly as `shadow-gate.ts` does. A collision is loud rather than silent: it lands in the group that exists to compare stamps.
    """
    digest = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]
    return pathlib.Path(tempfile.gettempdir()) / ("dev-shadow-%s" % digest)


def observe(side: str, root: pathlib.Path) -> None:
    """Drive every scenario on one side and print what it did."""
    base = sandbox_base(root)
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True)
    try:
        sandbox = build_sandbox(root, base)
        bins = build_stubs(base)
        trace = base / "trace.txt"
        for scenario in SCENARIOS:
            rc, out, err, lines = run_side(side, scenario, sandbox, trace, bins)
            emit("%s/rc" % scenario.name, str(rc))
            if not scenario.stub:
                stamp = sandbox.joinpath(*STAMP_PATH)
                emit(
                    "%s/stamp" % scenario.name,
                    stamp.read_text(encoding="utf-8").strip() if stamp.is_file() else "<none>",
                )
            if lines:
                for index, line in enumerate(lines, start=1):
                    emit("%s/trace %02d" % (scenario.name, index), mask(line, sandbox))
            else:
                emit("%s/trace" % scenario.name, "<none>")
            emit_lines("%s/out" % scenario.name, out, sandbox)
            if scenario.name == "no-npm":
                # See the module header: the twin's wording carries a bash line number, so only the fact that the message names the program survives.
                emit("%s/err-names-npm" % scenario.name, "yes" if "npm" in err else "no")
            else:
                emit_lines("%s/err" % scenario.name, err, sandbox)
    finally:
        shutil.rmtree(base, ignore_errors=True)


def refuse(message: str) -> int:
    """Say the subject is missing, loudly, and never emit a partial ledger row."""
    print("shadow_driver: CANNOT RUN. %s" % message, file=sys.stderr)
    print(
        "shadow_driver: this is a missing subject, not a finding about it. A row "
        "recorded now would compare nothing against nothing.",
        file=sys.stderr,
    )
    return EXIT_CANNOT_RUN


def twin_body(root: pathlib.Path) -> str:
    """The twin's `dev()` body, or an empty string once it is gone."""
    legacy = root / ".ci" / "legacy" / "run-legacy.sh"
    if not legacy.is_file():
        return ""
    text = legacy.read_text(encoding="utf-8")
    start = text.find("\ndev() {\n")
    if start < 0:
        return ""
    end = text.find("\n}\n", start)
    return text[start : end + 3] if end > start else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--side", choices=("old", "new"), required=True)
    parser.add_argument("--root", default=None)
    args = parser.parse_args(argv)

    root = pathlib.Path(args.root).resolve() if args.root else paths.repo_root()

    # BOTH SIDES CHECK THE TWIN, not just the old one. After the flip the bash is gone and both must refuse: a new side that kept answering would let a comparison record a one-sided verdict against a deleted twin, which reads as a port defect and is really an expired ledger.
    if not twin_body(root):
        return refuse(
            "the bash `dev()` body is absent from %s. The `dev` port has been "
            "flipped, so this ledger is history and must not be extended."
            % (root / ".ci" / "legacy" / "run-legacy.sh")
        )

    buffer: list[str] = []
    real_stdout = sys.stdout
    try:
        sys.stdout = _Collecting(buffer)
        observe(args.side, root)
    finally:
        sys.stdout = real_stdout

    text = "".join(buffer)
    emitted = [line for line in text.split("\n") if line.startswith(OBS + " ")]
    if len(emitted) < OBSERVATION_FLOOR:
        return refuse(
            "only %d observation(s) were emitted and the floor is %d. A group "
            "produced nothing, and two silent sides compare as equal."
            % (len(emitted), OBSERVATION_FLOOR)
        )
    sys.stdout.write(text)

    # NO SUMMARY LINE AND NO VERDICT. This is an OBSERVER: it reports what each implementation did and the comparator rules. A driver that also ruled would be a second opinion nobody asked for, and its exit code would enter the ledger as if it were the verb's.
    return 0


class _Collecting:
    """A stdout that keeps the text so the floor can be checked before anything is printed."""

    def __init__(self, sink: list[str]) -> None:
        self.sink = sink

    def write(self, text: str) -> int:
        self.sink.append(text)
        return len(text)

    def flush(self) -> None:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
