#!/usr/bin/env python3
"""Both sides of the `setup` port differential, in one file.

WHAT THIS IS FOR. `scripts/lib/shadow-gate.ts` compares two commands and rules on whether a port kept the verdict. It needs each side to PRINT what it observed, because the thing being compared is a finding multiset and not a
return value. This module is the printer, and it can print either side:

    python3 .ci/rediacc_ci/setup/shadow_driver.py --side old
        drives the BASH: `source .ci/lib/setup.sh` and the `setup()` body in
        `.ci/legacy/run-legacy.sh`, through `bash -c`.

    python3 .ci/rediacc_ci/setup/shadow_driver.py --side new
        drives the PYTHON: `rediacc_ci.setup.machine` and `.host`.

ONE FILE AND NOT TWO, and the reason is a gate rather than tidiness. `.ci/rediacc_ci/quality/dead_python.py:280` admits a pre-cutover port as alive
only when it is "named as the NEW side of a `.ci/shadow/*.jsonl` record"; the OLD
side's command is scanned for a live `.sh` TWIN, never for a Python file. A separate `shadow_old.py` would therefore be reported dead the day it landed. One module, named on the new side, imports everything else in this package, and the `imported` route carries the rest.

WHY IT IS DRIVEN AGAINST THE FUNCTION BODIES AND NEVER THROUGH `./run.sh setup`. `.ci/scripts/test/gates/test-run-sh.sh:279-290` emits `overlap <verb>` when a verb sits in both `PORTED_VERBS` and the legacy dispatcher, so the flip has to be
atomic: `PORTED_VERBS=(setup)` lands in the SAME change that deletes the legacy
arm and both function bodies. After that change there is no bash side left to drive. So this ledger is recorded BEFORE the flip, and it reaches the bash by sourcing it, which keeps working right up to the moment the bash is deleted and stops working loudly the moment after.

-----------------------------------------------------------------------------
THE SIX OBSERVATION GROUPS, AND WHAT EACH ONE WOULD CATCH
-----------------------------------------------------------------------------
  phase     The ORDERED phase sequence, obtained by TRACING a real run with
            every phase stubbed out. Not by reading a table on either side: a
            table compared against a table proves the two tables agree.
            Each line carries its ORDINAL, so a swap changes two lines and the
            multiset comparison sees it. `.ci/rediacc_ci/setup/tools.py:196-200`
            is why that matters: "ORDER IS THE DEPENDENCY ORDER", so an unordered
            comparison passes a port that installs go before jq.
  check     Every line `setup --check` prints, on both streams, plus its exit
            code. This is the whole report-only contract.
  idem      Each drivable function run TWICE, with both runs printed. Catches a
            port that works once and a port that is not idempotent, and it
            catches them separately: `stable=no` names the second run.
  pure      `node_pick_lts` and `go_pick_sha` over a fixed corpus. The two parts
            of `.ci/lib/setup.sh` that are already Python inside a `python3 -c`
            heredoc, so a disagreement here means the interpolation changed
            meaning.
  args      The flag grammar: `--help`'s text, an unknown flag's exit code.
  plan      The phase keys the tree's own conditionals select, which is the
            half `phase` cannot show without a fixture per condition.

-----------------------------------------------------------------------------
WHY THE CLOSED-STDIN BRANCH IS THE ONE DRIVEN, AND WHY THAT IS NOT A CHEAT
-----------------------------------------------------------------------------
Every install path in `.ci/lib/setup.sh` is behind `[[ -t 0 ]]` and a `prompt_continue`. A differential cannot answer a prompt, cannot be given root, and must not download a Go tarball. So both sides run with stdin closed, which takes the branch that PRINTS the command instead of running it. That branch is not a fallback: `.ci/lib/setup.sh:21-23` describes it as the contract, and
it is the branch every agent session, CI checkout and piped run actually meets. The install halves are covered by reading, are marked as such in `host.py`, and this file does not pretend otherwise.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from rediacc_ci import log, paths
from rediacc_ci.setup import bridge, host, machine
from rediacc_ci.setup.ctx import Ctx, Result

# The prefix `shadow-gate --finding-re` is pointed at. Deliberately not `✗` or `FAIL:`: those already mean "a finding" to the comparator's own marker table, and an observation that AGREES is not a failure. A neutral token keeps the ledger readable by a person who did not write this file.
OBS = "obs"

# The seven functions of `.ci/lib/setup.sh` that can be driven without a tty, without root and without the network. `setup_docker_probe` is here even though `setup()` never calls it: it is real code, it is drivable, and driving it is the cheapest way to keep the port honest while the bash still exists. See `host.py`'s header for the measurement that it is uncalled.
DRIVABLE: tuple[str, ...] = (
    "setup_node_toolchain",
    "setup_system_tools",
    "setup_go_toolchain",
    "setup_gh_cli",
    "setup_docker_probe",
    "setup_git_identity",
    "setup_git_credentials",
)

# bash name -> the `host.py` callable. Written out rather than derived by stripping `setup_`, so a renamed port cannot silently pair with the wrong twin.
PY_FOR: dict[str, str] = {
    "setup_node_toolchain": "node_toolchain",
    "setup_system_tools": "system_tools",
    "setup_go_toolchain": "go_toolchain",
    "setup_gh_cli": "gh_cli",
    "setup_docker_probe": "docker_probe",
    "setup_git_identity": "git_identity",
    "setup_git_credentials": "git_credentials",
}

# A FIXED corpus for the two pure pickers, so this group's findings do not depend on what nodejs.org and go.dev are serving today. A live index would make the ledger's fingerprints move for reasons that have nothing to do with either implementation, which is noise dressed as evidence.
NODE_INDEX = json.dumps(
    [
        {"version": "v23.1.0", "lts": False},
        {"version": "v22.20.0", "lts": False},
        {"version": "v22.13.0", "lts": "Jod"},
        {"version": "v22.9.0", "lts": "Jod"},
        {"version": "v20.18.0", "lts": "Iron"},
        {"version": "v19.9.0", "lts": False},
    ]
)
NODE_MAJORS = ("22", "20", "23", "19", "18")

GO_INDEX = json.dumps(
    [
        {
            "version": "go1.26.6",
            "files": [
                {"filename": "go1.26.6.linux-amd64.tar.gz", "sha256": "a" * 64},
                {"filename": "go1.26.6.darwin-arm64.tar.gz", "sha256": "b" * 64},
                {"filename": "go1.26.6.src.tar.gz", "sha256": ""},
            ],
        },
        {
            "version": "go1.25.0",
            "files": [{"filename": "go1.25.0.linux-arm64.tar.gz", "sha256": "c" * 64}],
        },
    ]
)
GO_FILES = (
    "go1.26.6.linux-amd64.tar.gz",
    "go1.26.6.darwin-arm64.tar.gz",
    "go1.25.0.linux-arm64.tar.gz",
    "go1.26.6.src.tar.gz",
    "go9.9.9.linux-amd64.tar.gz",
)

# The bash prelude every `--side old` call runs. `REDIACC_DOCKER_GROUP_REEXEC=1`
# makes `reexec_with_docker_group` a no-op, which is required rather than convenient: without it a traced `setup` would `exec sg docker -c ...` and replace this process with a real, unstubbed run.
OLD_PRELUDE = """
set -euo pipefail
export REDIACC_DOCKER_GROUP_REEXEC=1
source "$ROOT_DIR/.ci/legacy/run-legacy.sh"
source "$ROOT_DIR/.ci/lib/devbox.sh"
"""

# The stubs that turn `setup()` into a phase trace.
#
# `source` IS OVERRIDDEN, and that one line is what makes the trace possible. `.ci/legacy/run-legacy.sh:583` re-sources `.ci/lib/devbox.sh` from INSIDE `setup()`, which would redefine `devbox_up`, `devbox_ensure_image`, `devbox_url` and `devbox_status` and silently discard the stubs below. The first version of this trace lost exactly those four phases and looked correct. A bash
# function shadows a builtin, so `source` becomes a filter and every other `source` still works.
#
# `bash` and `npm` ARE STUBBED AS COMMANDS, because those two phases are spelled inline in `setup()` rather than as a function call: `bash "$ROOT_DIR/.devcontainer/init-submodules.sh" --quiet` and `npm run --silent check:env-credential-drift`. Nothing else in the traced body invokes either.
TRACE_STUBS = """
_p() { printf 'PHASE %s\\n' "$1"; }
source() { case "${1:-}" in *devbox.sh) return 0 ;; esac; builtin source "$@"; }
setup_node_toolchain()    { _p setup_node_toolchain; }
check_node_version()      { _p check_node_version; }
setup_system_tools()      { _p setup_system_tools; }
setup_go_toolchain()      { _p setup_go_toolchain; }
setup_gh_cli()            { _p setup_gh_cli; }
ensure_host_tools()       { _p ensure_host_tools; }
ensure_bashcov_sup()      { _p ensure_bashcov_sup; }
setup_git_identity()      { _p setup_git_identity; }
setup_git_credentials()   { _p setup_git_credentials; }
ensure_deps()             { _p ensure_deps; }
ensure_docker_installed() { _p ensure_docker_installed; }
devbox_ensure_image()     { _p devbox_ensure_image; }
devbox_up()               { _p devbox_up; }
devbox_url()              { echo "http://devbox.invalid"; }
devbox_status()           { :; }
bash()                    { _p init-submodules.sh; }
npm()                     { _p check:env-credential-drift; }
"""


# --------------------------------------------------------------------------- emitting ---------------------------------------------------------------------------


class _Counting(io.StringIO):
    """A stdout that can be counted before it is released.

    THE FLOOR HAS TO BE CHECKED BEFORE ANYTHING IS PRINTED, or the comparator has already read a short run by the time this process notices. Buffering the whole thing costs a few kilobytes and makes the refusal reachable.
    """


def emit(group: str, text: str) -> None:
    """One observation line. STDOUT, one per line, nothing else on the stream."""
    print("%s %s %s" % (OBS, group, text))


def emit_block(group: str, text: str) -> None:
    """A multi-line blob as numbered observations, blank lines included.

    NUMBERED, and every line kept including the empty ones. `setup --check` prints two deliberate blank lines and the bash's own `printf` column widths
    are part of what a person reads; a comparison that dropped blanks would
    pass a port that lost them.
    """
    lines = text.split("\n")
    # A trailing newline yields one empty final element that no side "printed".
    if lines and lines[-1] == "":
        lines.pop()
    if not lines:
        emit(group, "00 <no output>")
        return
    for index, line in enumerate(lines, start=1):
        emit(group, "%02d %s" % (index, line if line != "" else "<blank>"))


# --------------------------------------------------------------------------- the old side ---------------------------------------------------------------------------


def bash_run(root: pathlib.Path, body: str, env: dict[str, str]) -> tuple[int, str, str]:
    """One `bash -c` with the prelude, both streams captured SEPARATELY."""
    script = "ROOT_DIR=%s\n%s\n%s" % (_quote(str(root)), OLD_PRELUDE, body)
    proc = subprocess.run(
        ["bash", "-c", script],
        cwd=str(root),
        env=env,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def old_side(root: pathlib.Path, env: dict[str, str]) -> None:
    """Every observation, driven against the bash."""
    # -- phase, traced -----------------------------------------------------
    for label, args in (("default", ""), ("no-start", "--no-start")):
        rc, out, _ = bash_run(root, "%s\nsetup %s" % (TRACE_STUBS, args), env)
        keys = [line[len("PHASE ") :] for line in out.split("\n") if line.startswith("PHASE ")]
        emit("phase/%s" % label, "rc=%d count=%d" % (rc, len(keys)))
        for index, key in enumerate(keys, start=1):
            emit("phase/%s" % label, "%02d %s" % (index, key))

    # -- check -------------------------------------------------------------
    rc, out, err = bash_run(root, "setup_check", env)
    emit("check", "rc=%d" % rc)
    emit_block("check/out", out)
    emit_block("check/err", err)

    # -- idempotence -------------------------------------------------------
    for name in DRIVABLE:
        first = bash_run(root, name, env)
        second = bash_run(root, name, env)
        _emit_idem(name, first, second)

    # -- the two pure pickers ---------------------------------------------
    for major in NODE_MAJORS:
        rc, out, _ = bash_run(
            root, "printf '%%s' %s | node_pick_lts %s" % (_quote(NODE_INDEX), major), env
        )
        emit("pure/node-lts", "%s rc=%d -> %s" % (major, rc, out.strip() or "<none>"))
    for filename in GO_FILES:
        rc, out, _ = bash_run(
            root, "printf '%%s' %s | go_pick_sha %s" % (_quote(GO_INDEX), filename), env
        )
        emit("pure/go-sha", "%s rc=%d -> %s" % (filename, rc, out.strip() or "<none>"))

    # -- the flag grammar --------------------------------------------------
    rc, out, err = bash_run(root, "setup --help", env)
    emit("args/help", "rc=%d" % rc)
    emit_block("args/help/out", out)
    rc, out, err = bash_run(root, "setup --frobnicate", env)
    emit("args/unknown", "rc=%d" % rc)
    emit_block("args/unknown/err", err)

    # -- plan --------------------------------------------------------------
    _emit_plan(root, env)


def _emit_idem(name: str, first: tuple[int, str, str], second: tuple[int, str, str]) -> None:
    """Both runs of one function, plus the stability verdict.

    BOTH RUNS ARE PRINTED, not just the verdict. A single `stable=yes` line would
    be one bit, and one bit is exactly what a broken port can accidentally get
    right; printing both runs means the comparison is over the CONTENT of each
    run as well as over whether they matched.
    """
    for label, (rc, out, err) in (("run1", first), ("run2", second)):
        emit("idem/%s" % name, "%s rc=%d" % (label, rc))
        emit_block("idem/%s/%s/out" % (name, label), out)
        emit_block("idem/%s/%s/err" % (name, label), err)
    emit("idem/%s" % name, "stable=%s" % ("yes" if first == second else "no"))


def _emit_plan(root: pathlib.Path, env: dict[str, str]) -> None:
    """The conditional selection, stated for the tree the fixture really is.

    READ FROM THE TREE ON BOTH SIDES, not from either implementation: the two conditions are `[[ -f "$ROOT_DIR/.gitmodules" ]]` and
    `SKIP_ENV_DRIFT_CHECK != 1 && [[ -f "$ROOT_DIR/private/account/.env" ]]`,
    and the point of this group is that the fixture's answer to them is part of the ledger row. A fixture with no `.gitmodules` produces a genuinely different phase trace above, and this group says why.
    """
    emit("plan", "gitmodules=%s" % ("yes" if (root / ".gitmodules").is_file() else "no"))
    emit(
        "plan",
        "account-env=%s" % ("yes" if (root / "private" / "account" / ".env").is_file() else "no"),
    )
    emit("plan", "skip-drift=%s" % (env.get("SKIP_ENV_DRIFT_CHECK", "") or "<unset>"))


# --------------------------------------------------------------------------- the new side ---------------------------------------------------------------------------


def _capture(call) -> tuple[int, str, str]:
    """Run `call()` with stdout and stderr captured SEPARATELY.

    `ctx.say` writes to stdout and every `log_*` writes to stderr, so the split has to survive into the observation or the comparison stops being able to see a stream swap. `.ci/rediacc_ci/log.py`'s header records the day one happened.
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        logger = log.Logger(stream=err, colour=False)
        rc = call(logger)
    return rc, out.getvalue(), err.getvalue()


def _trace_ctx(root: pathlib.Path, env: dict[str, str], sink: list[str]) -> Ctx:
    """A `Ctx` whose `run` records the two inline phases instead of running them."""

    class TracingCtx(Ctx):
        def run(self, argv, *, timeout=None, stdin_text=None):  # type: ignore[override]
            joined = " ".join(argv)
            if "init-submodules.sh" in joined:
                sink.append("init-submodules.sh")
                return Result(0, "", "")
            if "check:env-credential-drift" in joined:
                sink.append("check:env-credential-drift")
                return Result(0, "", "")
            return super().run(argv, timeout=timeout, stdin_text=stdin_text)

    return TracingCtx(root=root, env=env, stdin_tty=False)


def new_phase_trace(
    root: pathlib.Path, env: dict[str, str], *, start: bool
) -> tuple[int, list[str]]:
    """The Python `run_setup` with every phase stubbed. Mirrors `TRACE_STUBS`.

    THE REAL `run_setup` RUNS. Nothing here reads `phases.PHASES` and prints it: the whole value of this group is that the ORDER comes out of the code path that will actually execute, on both sides. Substituting the table here would make the comparison "does the Python table match the bash", which is a weaker claim and, worse, one a broken `run_setup` would still satisfy.
    """
    sink: list[str] = []
    saved_host = {name: getattr(host, name) for name in PY_FOR.values()}
    saved_call, saved_capture = bridge.call, bridge.capture

    def stub(key: str):
        def inner(_ctx):
            sink.append(key)
            return 0

        return inner

    def stub_call(body, _root, _env=None):
        for key in (
            "check_node_version",
            "ensure_host_tools",
            "ensure_bashcov_sup",
            "ensure_deps",
            "ensure_docker_installed",
            "devbox_ensure_image",
            "devbox_up",
        ):
            if body.startswith(key):
                sink.append(key)
                return 0
        # `devbox_status` is reached only from `check()`, never from a traced `run_setup`. Recorded rather than silently allowed, so a phase this stub does not know about cannot pass as a no-op.
        sink.append("UNSTUBBED:%s" % body.split("\n")[0])
        return 0

    def stub_capture(_body, _root, _env=None):
        return 0, "http://devbox.invalid\n"

    try:
        for bash_name, py_name in PY_FOR.items():
            if bash_name == "setup_docker_probe":
                continue
            setattr(host, py_name, stub(bash_name))
        bridge.call = stub_call  # type: ignore[assignment]
        bridge.capture = stub_capture  # type: ignore[assignment]
        options = machine.Options(start=start)
        ctx = _trace_ctx(root, env, sink)
        rc, _, _ = _capture(lambda logger: machine.run_setup(_relog(ctx, logger), options, {}))
    finally:
        for name, value in saved_host.items():
            setattr(host, name, value)
        bridge.call = saved_call  # type: ignore[assignment]
        bridge.capture = saved_capture  # type: ignore[assignment]
    return rc, sink


def _relog(ctx: Ctx, logger: log.Logger) -> Ctx:
    """Point an existing ctx at a captured logger. Returns the same object."""
    ctx.logger = logger
    return ctx


def new_side(root: pathlib.Path, env: dict[str, str]) -> None:
    """Every observation, driven against the Python."""
    constants = bridge.constants(root, env)
    env = dict(env)
    env.update(constants)

    # -- phase, traced -----------------------------------------------------
    for label, start in (("default", True), ("no-start", False)):
        rc, keys = new_phase_trace(root, env, start=start)
        emit("phase/%s" % label, "rc=%d count=%d" % (rc, len(keys)))
        for index, key in enumerate(keys, start=1):
            emit("phase/%s" % label, "%02d %s" % (index, key))

    # -- check -------------------------------------------------------------
    ctx = Ctx(root=root, env=env, stdin_tty=False)
    rc, out, err = _capture(lambda logger: machine.check(_relog(ctx, logger), constants))
    emit("check", "rc=%d" % rc)
    emit_block("check/out", out)
    emit_block("check/err", err)

    # -- idempotence -------------------------------------------------------
    for name in DRIVABLE:
        function = getattr(host, PY_FOR[name])

        def once(function=function):
            local = Ctx(root=root, env=dict(env), stdin_tty=False)
            return _capture(lambda logger: function(_relog(local, logger)))

        _emit_idem(name, once(), once())

    # -- the two pure pickers ---------------------------------------------
    for major in NODE_MAJORS:
        answer = host.node_pick_lts(NODE_INDEX, major)
        # `rc` MIRRORS THE BASH's: `node_pick_lts` exits 1 when it finds nothing (`sys.exit(1)` inside its heredoc) and the caller reads that, so a
        # port returning None must be reported as rc=1 rather than as rc=0 with
        # an empty answer.
        emit("pure/node-lts", "%s rc=%d -> %s" % (major, 0 if answer else 1, answer or "<none>"))
    for filename in GO_FILES:
        answer = host.go_pick_sha(GO_INDEX, filename)
        emit("pure/go-sha", "%s rc=%d -> %s" % (filename, 0 if answer else 1, answer or "<none>"))

    # -- the flag grammar --------------------------------------------------
    emit("args/help", "rc=0")
    emit_block("args/help/out", machine.HELP + "\n")
    parsed = machine.parse_args(["--frobnicate"])
    rc, out, err = _capture(lambda logger: _unknown(logger, parsed.error))
    emit("args/unknown", "rc=%d" % rc)
    emit_block("args/unknown/err", err)

    # -- plan --------------------------------------------------------------
    _emit_plan(root, env)


def _unknown(printer: log.Logger, name: str) -> int:
    """`main`'s unknown-option arm, without going through `main`.

    NOT A REIMPLEMENTATION: `main` would run the docker-group re-exec and read the constants first, neither of which belongs in this observation, and both of which can `exec` this process away. The two lines here are the arm itself, and `test_setup_machine.py` asserts `main` still takes it.
    """
    printer.emit("error", "Unknown option for setup: %s" % name)
    return machine.EXIT_USAGE


# --------------------------------------------------------------------------- entry ---------------------------------------------------------------------------


# The bash this differential is ABOUT. Named on the command line rather than only here for a second reason beyond readability: `.ci/rediacc_ci/quality/dead_python.py:317` scans the OLD side's command string for a `.sh` token and treats the port as ADMITTED only while that file is still on disk. A ledger row whose old command names no `.sh` at all admits nothing, so the port would
# read as dead the day it landed.
TWIN_DEFAULT = ".ci/lib/setup.sh"

# The body file the phase trace needs. Separate from the twin because they are different files and either can move on its own.
BODY_DEFAULT = ".ci/legacy/run-legacy.sh"

# Exit 77 is CANNOT RUN and is never a verdict, the convention `scripts/ci-runner/pool.ts:80-89` defines and `rediacc_ci.check_pytest:124` names. Used here for exactly one condition: the subject is not on disk.
EXIT_CANNOT_RUN = 77

# The floor no honest run of this driver can fall below. NOT a round number picked to look safe: the six groups emit at least 2 phase headers + 13 + 12 phase lines + 1 check rc + 2 check blocks + 7 functions * 8 lines + 5 + 5 pure + 2 args + 3 plan, and the smallest fixture measured (fx3, no `.gitmodules`) produced 114. A run under 80 means a group silently produced nothing, which
# is the shape a green comparison of two empty sides has.
OBSERVATION_FLOOR = 80


def _refuse(message: str) -> int:
    """Say the subject is missing, loudly, and never emit a partial ledger row."""
    print("shadow_driver: CANNOT RUN. %s" % message, file=sys.stderr)
    print(
        "shadow_driver: this is a missing subject, not a finding about it. A row "
        "recorded now would compare nothing against nothing.",
        file=sys.stderr,
    )
    return EXIT_CANNOT_RUN


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--side", choices=("old", "new"), required=True)
    parser.add_argument("--root", default=None)
    parser.add_argument("--twin", default=TWIN_DEFAULT)
    parser.add_argument("--body", default=BODY_DEFAULT)
    args = parser.parse_args(argv)

    root = pathlib.Path(args.root).resolve() if args.root else paths.repo_root()
    env = dict(os.environ)
    # DETERMINISM PINS, applied to BOTH sides. `shadow-gate.ts:buildEnv` already
    # sets LC_ALL and TZ for the processes it spawns; these are the two this
    # comparison needs on top and they are set here so the driver behaves the same when a person runs it by hand.
    env["NO_COLOR"] = "1"
    env["REDIACC_DOCKER_GROUP_REEXEC"] = "1"

    # BOTH SIDES CHECK THE TWIN, not just the old one. After the flip the bash is gone and BOTH sides must refuse: a new side that kept answering would
    # let a comparison record `NEW_SIDE_NOISY` against a deleted twin, which
    # reads as a port defect and is really an expired ledger.
    twin = root / args.twin
    body = root / args.body
    if not twin.is_file() or twin.stat().st_size == 0:
        return _refuse(
            "the bash twin %s is absent or empty. The `setup` port has been "
            "flipped, so this ledger is history and must not be extended." % args.twin
        )
    if not body.is_file():
        return _refuse("the setup() body file %s is absent." % args.body)

    counter = _Counting()
    with contextlib.redirect_stdout(counter):
        if args.side == "old":
            old_side(root, env)
        else:
            new_side(root, env)
    text = counter.getvalue()
    lines = [line for line in text.split("\n") if line.startswith(OBS + " ")]
    if len(lines) < OBSERVATION_FLOOR:
        return _refuse(
            "only %d observation(s) were emitted and the floor is %d. A group "
            "produced nothing, and two silent sides compare as equal."
            % (len(lines), OBSERVATION_FLOOR)
        )
    sys.stdout.write(text)

    # NO SUMMARY LINE AND NO VERDICT. This is an OBSERVER: it reports what each implementation did and the comparator rules. A driver that also ruled would be a second opinion nobody asked for, and its exit code would enter the ledger as if it were the gate's.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
