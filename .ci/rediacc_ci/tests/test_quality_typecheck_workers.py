"""Differential: `rediacc_ci.quality.typecheck_workers` against its twin `.ci/scripts/quality/typecheck-workers.sh`.

RECORDING FAKES FOR `npm` AND `npx` ON A SCRATCH PATH, INSIDE A FIXTURE REPO. Nothing here reaches the npm registry and nothing runs a real TypeScript compiler: the two programs that would are the two the fakes model, and every other tool the twin reaches for (`find`, `sort`, `dirname`) is the real binary symlinked into the same scratch directory, because both sides call the same
one.

THE CALL LOG IS EVIDENCE ON EQUAL FOOTING WITH THE STREAMS. This script's observable behaviour is half what it prints and half WHICH projects it installs and typechecks, in what order, with which flags. A port that printed the same five lines while calling `npm install` where the twin calls `npm ci` would pass a stdout comparison and be wrong in the way that matters.

THE FIXTURE HAS TWO WORKERS, NOT ONE, and they differ: `alpha` has a `package-lock.json` (so `npm ci`) and `beta` does not (so `npm install`). One worker would let a port that hard-coded either verb through.

`REDIACC_CI_ROOT` STEERS THE PORT, THE COPY STEERS THE TWIN. The twin derives
its root from `${BASH_SOURCE[0]}/../../..`, so the copy inside the fixture makes
it land on the fixture root; the port asks `rediacc_ci.paths`, which honours the variable. Both then `cd` there, which is why `cwd` for the subprocess is deliberately the fixture's PARENT: a side that did not chdir would find no `workers/` at all.
"""

from __future__ import annotations

import inspect
import os
import re
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.quality import typecheck_workers as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "quality" / "typecheck-workers.sh"
PORT_FILE = ROOT / ".ci" / "rediacc_ci" / "quality" / "typecheck_workers.py"
BASH = shutil.which("bash") or "/bin/bash"

# The tail every `npm ci`/`npm install` call carries, spelled once. Built from the port's own tuple rather than retyped, so a port that reordered or dropped a flag would still be caught by `test_npm_argv_...` below (which compares that tuple against the literal list) instead of silently agreeing with itself here.
NPM_NET_TAIL = " ".join(port.NPM_NET)

# The real binaries both sides reach through PATH. `find` and `sort` are the discovery pipeline, `dirname` is the twin's per-iteration call.
PATH_MINIMUM = ("find", "sort", "dirname", "cat", "env")

# A recording fake shared by `npm` and `npx`: it appends its own argv to the call log under a distinct `call: ` prefix and then either succeeds quietly or fails with the status the fixture asked for.
#
# THE PREFIX IS LOAD-BEARING FOR THE LEDGER, not decoration. `shadow-gate.ts` classifies a line starting with `→ ` or `✓ ` as CHATTER before any `--finding-re` is consulted, so a script that reports through log-step lines can never produce a finding by message text alone. `call: ` is a shape no logger emits, and the ledger scopes its `--finding-re` to it.
FAKE_TOOL = r'''#!/usr/bin/python3
"""Recording fake for `npm`/`npx`. See the test module docstring."""
import os
import sys

name = os.path.basename(sys.argv[0])
argv = sys.argv[1:]

with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("call: %s %s\n" % (name, " ".join(argv)))

fail_spec = os.environ.get("FAKE_FAIL", "")
for clause in [c for c in fail_spec.split(",") if c]:
    needle, _, code = clause.partition("=")
    if needle in " ".join([name, *argv]):
        sys.stderr.write("%s: a fixture failure was injected (%s)\n" % (name, needle))
        sys.exit(int(code))

if name == "npx":
    sys.stdout.write("tsc: 0 errors\n")
sys.exit(0)
'''


def _bin(root: pathlib.Path) -> str:
    stub = root / "fixture-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        link = stub / real_name
        if link.is_symlink() or link.exists():
            link.unlink()
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        link.symlink_to(real)
    for tool in ("npm", "npx"):
        path = stub / tool
        path.write_text(FAKE_TOOL, encoding="utf-8")
        path.chmod(0o755)
    return str(stub)


def fixture(
    tmp_path: pathlib.Path,
    *,
    workers: tuple[tuple[str, bool, bool], ...] = (("alpha", True, False), ("beta", False, False)),
    make_workers_dir: bool = True,
) -> pathlib.Path:
    """A throwaway repository holding the twin and a `workers/` tree.

    Each worker is `(name, has_lockfile, has_node_modules)`.
    `make_workers_dir=False` removes `workers/` entirely, which is the input for
    the zero-discovery refusal.
    """
    root = tmp_path / "repo"
    (root / ".ci" / "scripts" / "quality").mkdir(parents=True, exist_ok=True)
    shutil.copy2(TWIN, root / ".ci" / "scripts" / "quality" / TWIN.name)

    if make_workers_dir:
        (root / "workers").mkdir(parents=True, exist_ok=True)
    for name, has_lock, has_modules in workers:
        directory = root / "workers" / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "tsconfig.json").write_text('{"compilerOptions": {}}\n', encoding="utf-8")
        if has_lock:
            (directory / "package-lock.json").write_text(
                '{"lockfileVersion": 3}\n', encoding="utf-8"
            )
        if has_modules:
            (directory / "node_modules").mkdir(exist_ok=True)
    return root


def _run(
    root: pathlib.Path,
    side: str,
    *,
    args: tuple[str, ...] = (),
    **extra: str,
):
    call_log = root / f"{side}-calls.log"
    call_log.write_text("", encoding="utf-8")

    env = {
        "PATH": _bin(root),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "REDIACC_CI_ROOT": str(root),
        "FAKE_CALL_LOG": str(call_log),
    }
    env.update(extra)

    if side == "old":
        argv = [BASH, str(root / ".ci" / "scripts" / "quality" / TWIN.name), *args]
    else:
        argv = [sys.executable, str(PORT_FILE), *args]
    proc = subprocess.run(
        argv,
        # DELIBERATELY NOT THE FIXTURE ROOT: both sides must chdir there themselves, and a side that did not would discover nothing.
        cwd=str(root.parent),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )
    return proc, call_log.read_text(encoding="utf-8")


def run_both(tmp_path: pathlib.Path, *, fixture_kw: dict | None = None, **kw):
    root = fixture(tmp_path, **(fixture_kw or {}))
    old = _run(root, "old", **kw)
    new = _run(root, "new", **kw)
    return root, old, new


def _agree(old, new, label: str) -> None:
    """THE THREE STREAMS SEPARATELY, plus the call log.

    Nothing is masked. Neither side writes a temporary path, a timestamp or a duration, so a mask here would only be able to hide a real difference.
    """
    old_proc, old_calls = old
    new_proc, new_calls = new
    assert new_proc.returncode == old_proc.returncode, (
        f"{label}: exit diverged: {old_proc.returncode!r} vs {new_proc.returncode!r}\n"
        f"old stderr: {old_proc.stderr!r}\nnew stderr: {new_proc.stderr!r}"
    )
    assert new_proc.stdout == old_proc.stdout, (
        f"{label}: stdout diverged:\n{old_proc.stdout!r}\n{new_proc.stdout!r}"
    )
    assert new_proc.stderr == old_proc.stderr, (
        f"{label}: stderr diverged:\n{old_proc.stderr!r}\n{new_proc.stderr!r}"
    )
    assert new_calls == old_calls, f"{label}: call log diverged:\n{old_calls}\n---\n{new_calls}"


def _calls(log: str) -> list[str]:
    return [line[len("call: ") :] for line in log.splitlines() if line.startswith("call: ")]


# --------------------------------------------------------------------------- The three documented modes ---------------------------------------------------------------------------


def test_default_run_installs_then_typechecks_every_worker_in_order(tmp_path) -> None:
    _root, old, new = run_both(tmp_path)
    _agree(old, new, "default")

    proc, calls = old
    assert proc.returncode == 0, proc.stderr
    # PRINT THE SHAPE. Two workers, each contributing one install and one tsc, interleaved per worker rather than batched, and `alpha` before `beta` because `sort` says so.
    assert _calls(calls) == [
        f"npm ci --prefix workers/alpha --ignore-scripts {NPM_NET_TAIL}",
        "npx tsc --noEmit -p workers/alpha/tsconfig.json",
        f"npm install --prefix workers/beta --ignore-scripts {NPM_NET_TAIL}",
        "npx tsc --noEmit -p workers/beta/tsconfig.json",
    ], _calls(calls)
    assert proc.stdout.splitlines() == [
        "typecheck-workers: installing workers/alpha (npm ci)",
        "typecheck-workers: workers/alpha/tsconfig.json",
        "tsc: 0 errors",
        "typecheck-workers: installing workers/beta (npm install, no lockfile)",
        "typecheck-workers: workers/beta/tsconfig.json",
        "tsc: 0 errors",
        "typecheck-workers: 2 worker project(s) typechecked clean",
    ], proc.stdout


def test_list_prints_the_real_set_and_calls_nothing(tmp_path) -> None:
    """`check-typecheck-scope-coverage.ts` reads this output as the authority on which projects are covered, so `--list` must not install anything and must print one path per line and nothing else."""
    _root, old, new = run_both(tmp_path, args=("--list",))
    _agree(old, new, "list")

    proc, calls = old
    assert proc.returncode == 0
    assert proc.stdout == "workers/alpha/tsconfig.json\nworkers/beta/tsconfig.json\n"
    assert _calls(calls) == []


def test_install_stops_before_typechecking_and_says_so(tmp_path) -> None:
    """`lint:unused` runs BEFORE the TypeScript step, so it asks for the trees itself. The distinguishing evidence is the ABSENCE of any `npx tsc` call."""
    _root, old, new = run_both(tmp_path, args=("--install",))
    _agree(old, new, "install")

    proc, calls = old
    assert proc.returncode == 0
    assert [c.split()[0] for c in _calls(calls)] == ["npm", "npm"]
    assert proc.stdout.splitlines()[-1] == "typecheck-workers: 2 worker project(s) have their deps"


# --------------------------------------------------------------------------- The anti-vacuity floor, which is the only refusal this script has ---------------------------------------------------------------------------


def test_zero_discovery_is_a_two_line_refusal_on_stderr_and_exit_1(tmp_path) -> None:
    _root, old, new = run_both(tmp_path, fixture_kw={"workers": (), "make_workers_dir": False})
    _agree(old, new, "zero-discovery")

    proc, calls = old
    assert proc.returncode == 1
    assert proc.stdout == ""
    # find's own complaint first, then the script's two lines, verbatim.
    assert proc.stderr.splitlines()[-2:] == list(port.NO_WORKERS_LINES)
    assert "No such file or directory" in proc.stderr
    assert _calls(calls) == []


def test_an_empty_workers_directory_also_refuses(tmp_path) -> None:
    """A `workers/` that exists and holds nothing is the same refusal WITHOUT find's complaint, which proves the refusal is the guard's and not find's."""
    _root, old, new = run_both(tmp_path, fixture_kw={"workers": ()})
    _agree(old, new, "empty-workers")

    proc, _log = old
    assert proc.returncode == 1
    assert proc.stderr.splitlines() == list(port.NO_WORKERS_LINES)


def test_the_refusal_precedes_list_so_list_can_never_print_an_empty_set(tmp_path) -> None:
    """ORDER MATTERS HERE. The guard is above the `--list` arm in the twin, so a coverage gate asking for the set gets a REFUSAL rather than zero lines and a green exit. A port that put the arm first would satisfy every other test in this file."""
    _root, old, new = run_both(tmp_path, fixture_kw={"workers": ()}, args=("--list",))
    _agree(old, new, "list-refusal")

    proc, _log = old
    assert proc.returncode == 1
    assert proc.stdout == ""


# --------------------------------------------------------------------------- Failure propagation: both unguarded commands, and the work NOT done after ---------------------------------------------------------------------------


def test_a_failing_npm_ci_ends_the_run_with_npms_own_status(tmp_path) -> None:
    _root, old, new = run_both(tmp_path, FAKE_FAIL="npm ci=7")
    _agree(old, new, "npm-fails")

    proc, calls = old
    assert proc.returncode == 7
    # AND NOTHING AFTER IT RAN: no tsc for alpha, and beta is never reached.
    assert _calls(calls) == [f"npm ci --prefix workers/alpha --ignore-scripts {NPM_NET_TAIL}"]
    assert "typecheck-workers: 2 worker project(s)" not in proc.stdout


def test_a_failing_tsc_ends_the_run_with_tscs_own_status(tmp_path) -> None:
    _root, old, new = run_both(tmp_path, FAKE_FAIL="tsc --noEmit -p workers/beta=2")
    _agree(old, new, "tsc-fails")

    proc, calls = old
    assert proc.returncode == 2
    # alpha completed, beta's tsc is the last call, and the summary never prints.
    assert _calls(calls)[-1] == "npx tsc --noEmit -p workers/beta/tsconfig.json"
    assert "typechecked clean" not in proc.stdout


def test_a_failing_npm_under_install_only_still_stops_the_run(tmp_path) -> None:
    """`--install` is the `lint:unused` entry point, so a registry outage there must be a red step rather than a quiet skip into knip."""
    _root, old, new = run_both(tmp_path, args=("--install",), FAKE_FAIL="npm install=99")
    _agree(old, new, "install-fails")

    proc, _log = old
    assert proc.returncode == 99
    assert "have their deps" not in proc.stdout


# --------------------------------------------------------------------------- The three named defects ---------------------------------------------------------------------------


def test_defect_a_an_unknown_argument_is_silently_a_full_run(tmp_path) -> None:
    """`--isntall` is one letter from `--install` and does the OPPOSITE of what the caller asked: a full typecheck instead of an install-only pass. The twin has no `*)` arm, so there is nothing to report it."""
    assert port.AN_UNKNOWN_ARGUMENT_IS_A_FULL_RUN
    _root, old, new = run_both(tmp_path, args=("--isntall",))
    _agree(old, new, "unknown-arg")

    proc, calls = old
    assert proc.returncode == 0
    assert "npx tsc --noEmit -p workers/alpha/tsconfig.json" in _calls(calls)
    assert (
        proc.stdout.splitlines()[-1] == "typecheck-workers: 2 worker project(s) typechecked clean"
    )


def test_defect_a_holds_for_help_too(tmp_path) -> None:
    """`--help` is the one an operator is most likely to type, and it installs and typechecks the whole estate instead of printing usage."""
    _root, old, new = run_both(tmp_path, args=("--help",))
    _agree(old, new, "help")

    proc, _log = old
    assert proc.returncode == 0
    assert "typechecked clean" in proc.stdout


def test_defect_b_a_partial_find_failure_is_a_smaller_green_run(tmp_path) -> None:
    """A REAL UNREADABLE DIRECTORY, not a fake `find`. `workers/beta` is chmod 000, so the real `find` prints its complaint, lists `alpha` anyway and exits
    1. Both sides discard that status, report ONE project and exit 0, so the
    count in the success line is the only trace and nothing compares it to anything.

    The mode is restored in a `finally` because pytest's own tmp-dir reaper cannot delete a directory it may not enter, and a fixture that breaks the NEXT session's collection is a worse bug than the one being demonstrated.
    """
    assert port.A_PARTIAL_FIND_FAILURE_IS_A_SMALLER_GREEN_RUN
    root = fixture(tmp_path)
    blocked = root / "workers" / "beta"
    blocked.chmod(0o000)
    try:
        # THE CONTROL FIRST: prove the mode really does block THIS uid before reading anything into the run's output. Running as root would make the whole case vacuous, and a chmod that did nothing would look exactly like a gate that correctly found one worker.
        probe = subprocess.run(
            ["find", "workers", "-maxdepth", "2", "-name", "tsconfig.json", "-type", "f"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        assert probe.returncode == 1, "the chmod did not block this uid; the case is vacuous"
        assert "Permission denied" in probe.stderr

        old = _run(root, "old")
        new = _run(root, "new")
    finally:
        blocked.chmod(0o755)
    _agree(old, new, "partial-find")

    proc, calls = old
    assert proc.returncode == 0, "the twin does not see find's status at all"
    assert "Permission denied" in proc.stderr
    assert (
        proc.stdout.splitlines()[-1] == "typecheck-workers: 1 worker project(s) typechecked clean"
    )
    assert not [c for c in _calls(calls) if "beta" in c]


def test_defect_c_a_present_but_empty_node_modules_is_never_refreshed(tmp_path) -> None:
    """The guard is `[ ! -d "$dir/node_modules" ]`, an EXISTENCE test. An empty directory is indistinguishable from a complete install, which is exactly the state the twin's own comment says breaks knip."""
    assert port.A_PRESENT_BUT_STALE_NODE_MODULES_IS_NEVER_REFRESHED
    _root, old, new = run_both(
        tmp_path,
        fixture_kw={"workers": (("alpha", True, True), ("beta", False, False))},
    )
    _agree(old, new, "stale-node-modules")

    proc, calls = old
    assert proc.returncode == 0
    assert not [c for c in _calls(calls) if c.startswith("npm ") and "alpha" in c], (
        "alpha's empty node_modules suppressed its install"
    )
    assert "installing workers/alpha" not in proc.stdout
    assert "installing workers/beta" in proc.stdout


# --------------------------------------------------------------------------- Pure helpers, exercised directly ---------------------------------------------------------------------------


def test_read_configs_follows_bash_rather_than_python() -> None:
    assert port.read_configs("a\nb\n") == ["a", "b"]
    assert port.read_configs("a\nb") == ["a"], "a final line without a newline is dropped"
    assert port.read_configs("") == []
    assert port.read_configs("a\n\nb\n") == ["a", "", "b"], (
        "there is no -n guard in this loop, so a blank line becomes an element"
    )


def test_dirname_answers_dot_where_os_path_answers_empty() -> None:
    assert port.dirname("workers/alpha/tsconfig.json") == "workers/alpha"
    assert port.dirname("tsconfig.json") == "."
    assert port.dirname("") == "."
    assert os.path.dirname("tsconfig.json") == "", "the difference this helper exists for"


def test_npm_argv_picks_the_verb_from_the_lockfile_and_keeps_the_flag_order() -> None:
    ci = port.npm_argv("workers/alpha", has_lockfile=True)
    install = port.npm_argv("workers/beta", has_lockfile=False)
    assert ci[:5] == ["npm", "ci", "--prefix", "workers/alpha", "--ignore-scripts"]
    assert install[:2] == ["npm", "install"]
    assert ci[5:] == list(port.NPM_NET)
    assert port.NPM_NET == (
        "--fetch-timeout=120000",
        "--fetch-retries=5",
        "--fetch-retry-mintimeout=2000",
        "--fetch-retry-maxtimeout=30000",
    )


def test_tsc_argv_is_the_twins_words() -> None:
    assert port.tsc_argv("workers/x/tsconfig.json") == [
        "npx",
        "tsc",
        "--noEmit",
        "-p",
        "workers/x/tsconfig.json",
    ]


def test_the_port_does_not_carry_a_second_copy_of_the_gate_header() -> None:
    """The twin is the REGISTERED gate. `scripts/ci-runner` derives the estate
    from `---- gate ----` blocks, so a copy of the block in the port would
    register `lint:unused` twice from two files. The twin's own block is asserted present in the same breath, because "neither file has one" would satisfy a one-sided check.

    THE MATCHER IS `scripts/lib/gate-header.ts`'s OWN, transcribed: an opening marker is a WHOLE LINE, optionally commented. A substring test reads as stricter and is in fact wrong -- it fails on this file's own prose, which names the marker in a sentence and declares nothing.
    """
    open_marker = re.compile(r"^\s*(?:#|//|\*)?\s*-{2,}\s*gate\s*-{2,}\s*$")
    twin_lines = TWIN.read_text(encoding="utf-8").split("\n")
    port_lines = PORT_FILE.read_text(encoding="utf-8").split("\n")
    assert [ln for ln in twin_lines if open_marker.match(ln)], "the twin's registration moved"
    assert [ln for ln in port_lines if open_marker.match(ln)] == []
    assert "---- gate ----" in PORT_FILE.read_text(encoding="utf-8"), (
        "the port explains the omission in prose, which is not a declaration"
    )


def test_the_port_reads_no_environment_variable_of_its_own() -> None:
    """Every input is a positional argument or the filesystem. The only environment this module is sensitive to is `$REDIACC_CI_ROOT`, and that is read inside `rediacc_ci.paths`, which already declares it. A future edit that reaches for `os.environ` here owes an env-registry entry, and this is the line that will say so."""
    source = PORT_FILE.read_text(encoding="utf-8")
    body = source.split('"""', 2)[2]
    assert "os.environ" not in body


def test_the_twin_still_says_what_this_port_says_it_says() -> None:
    """A STALENESS GUARD, quoting the twin. Each of these is a line the port reproduces; if one moves, the port's claim to be a port needs re-checking rather than the assertion needs relaxing."""
    text = TWIN.read_text(encoding="utf-8")
    assert "find workers -maxdepth 2 -name tsconfig.json -type f | sort" in text
    assert 'if [ ! -d "$dir/node_modules" ]; then' in text
    assert 'if [ "${1:-}" = "--list" ]; then' in text
    assert '[ "${1:-}" = "--install" ] && INSTALL_ONLY=1' in text
    assert 'npx tsc --noEmit -p "$config"' in text
    for line in port.NO_WORKERS_LINES:
        assert line in text


def test_the_helpers_the_selftest_leans_on_are_exported() -> None:
    """The pure helpers are module-level functions, not closures, so this file can drive them without shelling out. Asserted rather than assumed, because a refactor that hid one inside `main` would silently reduce this suite to subprocess tests only."""
    for name in ("read_configs", "dirname", "npm_argv", "tsc_argv", "discover"):
        assert inspect.isfunction(getattr(port, name)), name
