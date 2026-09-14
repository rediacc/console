"""Differential: `rediacc_ci.quality.page_density` against its twin
`.ci/scripts/quality/page-density.sh`.

THE SUBJECT IS A LAUNCHER, so what is under test is the LAUNCH: which binary,
with exactly which argv, from which working directory, after which stdout
line. The real `scripts/gates/check-page-density.ts` is never run here -- it
drives three routes across four viewports in a Playwright container and takes
minutes -- and it does not need to be, because it is TypeScript and is
identical on both sides of this comparison by construction.

THE SEAM IS PATH, populated with recording stubs for `npx`, `node` and
`docker` (ruling 7's shape, as in `test_pr_sync_epic_block.py`). Each stub
prints its own name, its argv and its cwd, so a divergence in ANY of the three
things the launcher decides shows up as a text difference rather than as a
silent pass. The cwd line is not decoration: the twin `cd`s to
`SCRIPT_DIR/../../..` and the port to `paths.repo_root()`, and those are two
independent derivations of the same directory that could drift apart without
any other assertion here noticing.

DOCKER ABSENCE IS SIMULATED BY OMITTING THE STUB, never by an environment
flag, because `command -v docker` / `shutil.which("docker")` is the branch
under test. The real docker on this machine is out of PATH for every case.

TWO CASES ASSERT AGREEMENT ON EXIT CODE AND SUBSTANCE RATHER THAN BYTES, and
they are the two the port's docstring names as divergences: a missing `node`
and a missing `npx` both produce bash's own `<script>: line NN: ...` text,
which carries a line number no port should reproduce. Everything else in this
file is byte-for-byte.

K=5 LEDGER: `.ci/shadow/w7p6-page-density.observations.jsonl` -- five
distinct trees, `--assert --k 5` prints "equivalence holds over 5 distinct
trees". Recorded in a disposable scratch repo outside this checkout (dirty
tree; `--record` refuses one) with the same recording stubs on PATH, varying
the branch across trees: REDIACC_SMOKE_NO_DOCKER=1, docker absent, two
different playwright versions, and a failing node.

BEYOND THE STUBS, THE REAL THING WAS DRIVEN ONCE, 2026-09-10: `npm run
check:ci-page-density` (the registered gate, the bash twin) and `python3 -m
rediacc_ci.quality.page_density` both pulled the real
`mcr.microsoft.com/playwright:v1.61.1-noble` container, ran the real gate and
exited 0 with BYTE-IDENTICAL stdout and stderr.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

from rediacc_ci import paths
from rediacc_ci.quality import page_density

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "quality" / "page-density.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "quality" / "page_density.py"
BASH = shutil.which("bash") or "/bin/bash"

# A recording stub: name, argv, cwd, then whatever the case asked it to do.
# `#!/usr/bin/python3` absolute, not `/usr/bin/env python3`: these run with a
# PATH that deliberately holds almost nothing, and `env` would fail to resolve
# the interpreter.
STUB = """#!/usr/bin/python3
import os
import sys

name = os.path.basename(sys.argv[0])
record = "%s argv=[%s] cwd=[%s]" % (name, " ".join(sys.argv[1:]), os.getcwd())
with open(os.environ["STUB_LOG"], "a") as fh:
    fh.write(record + "\\n")
# QUIET exists for `node` alone: the twin captures node's STDOUT into
# PW_VERSION, so a stub that chattered there would be feeding its own
# recording into the image tag. Every other stub echoes, because for those the
# recording IS the observable behaviour under test.
if os.environ.get("STUB_%s_QUIET" % name.upper()) != "1":
    print("STUB " + record)
rc = int(os.environ.get("STUB_%s_RC" % name.upper(), "0"))
out = os.environ.get("STUB_%s_STDOUT" % name.upper(), "")
err = os.environ.get("STUB_%s_STDERR" % name.upper(), "")
if out:
    print(out)
if err:
    sys.stderr.write(err)
sys.exit(rc)
"""

# The twin needs `dirname` to compute its own REPO_ROOT (line 24). Nothing
# else external is reached before the branch under test on either side.
PATH_MINIMUM = ("dirname",)


def _stub_path(tmp_path: pathlib.Path, *names: str) -> str:
    """A PATH holding `dirname` plus one recording stub per requested name."""
    stub = tmp_path / "bin"
    stub.mkdir(exist_ok=True)
    for real_name in PATH_MINIMUM:
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        link = stub / real_name
        if not link.exists():
            link.symlink_to(real)
    for name in names:
        target = stub / name
        target.write_text(STUB, encoding="utf-8")
        target.chmod(0o755)
    for absent in ("docker", "npx", "node"):
        if absent not in names:
            assert shutil.which(absent, path=str(stub)) is None, f"{absent} leaked into the stub"
    return str(stub)


def _run(
    subject: pathlib.Path, env: dict[str, str], cwd: pathlib.Path
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Run one side. Returns its streams AND the stub call log.

    The log is a separate artifact from stdout on purpose: `node`'s recording
    never reaches stdout (see STUB's QUIET note), so without it the
    image-derivation cases would assert nothing about how node was invoked.
    """
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    log = pathlib.Path(env["STUB_LOG"])
    log.write_text("", encoding="utf-8")
    proc = subprocess.run(
        [*runner, str(subject)],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )
    return proc, [line for line in log.read_text(encoding="utf-8").splitlines() if line]


def _env(path: str, log: pathlib.Path, **overrides: str) -> dict[str, str]:
    env = {
        "PATH": path,
        "STUB_LOG": str(log),
        "STUB_NODE_QUIET": "1",
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    env.update(overrides)
    return env


def run_both(tmp_path: pathlib.Path, stubs: tuple[str, ...], **overrides: str):
    """Both sides, each with its OWN stub log so the two can be compared."""
    path = _stub_path(tmp_path, *stubs)
    old_env = _env(path, tmp_path / "old-calls.log", **overrides)
    new_env = _env(path, tmp_path / "new-calls.log", **overrides)
    # cwd is deliberately NOT the repo: both subjects must cd to the root
    # themselves, and starting them there would hide a port that did not.
    old, old_calls = _run(TWIN, old_env, tmp_path)
    new, new_calls = _run(PORT, new_env, tmp_path)
    return old, new, old_calls, new_calls


def _assert_agree(old, new, label: str, old_calls=None, new_calls=None) -> None:
    assert new.returncode == old.returncode, (
        f"{label}: exit diverged: {old.returncode!r} vs {new.returncode!r}"
    )
    assert new.stdout == old.stdout, (
        f"{label}: stdout diverged:\nold: {old.stdout!r}\nnew: {new.stdout!r}"
    )
    assert new.stderr == old.stderr, (
        f"{label}: stderr diverged:\nold: {old.stderr!r}\nnew: {new.stderr!r}"
    )
    if old_calls is not None:
        assert new_calls == old_calls, (
            f"{label}: stub call log diverged:\nold: {old_calls}\nnew: {new_calls}"
        )


def test_no_docker_env_execs_npx_with_no_note(tmp_path: pathlib.Path) -> None:
    """`REDIACC_SMOKE_NO_DOCKER=1` is the escape hatch, and it must NOT print
    the "docker not found" note -- the operator asked for this path."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ("npx", "docker", "node"), REDIACC_SMOKE_NO_DOCKER="1"
    )
    assert old.returncode == 0
    assert old.stdout == (
        f"STUB npx argv=[tsx scripts/gates/check-page-density.ts --selftest] cwd=[{ROOT}]\n"
    )
    assert "note:" not in old.stdout
    assert old_calls == [
        f"npx argv=[tsx scripts/gates/check-page-density.ts --selftest] cwd=[{ROOT}]"
    ]
    _assert_agree(old, new, "no-docker-env", old_calls, new_calls)


def test_docker_absent_prints_the_note_then_execs_npx(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ("npx", "node"))
    assert old.returncode == 0
    assert old.stdout.splitlines()[0] == (
        "note: docker not found, running the gate directly (needs a local Chromium)"
    )
    assert old_calls == [
        f"npx argv=[tsx scripts/gates/check-page-density.ts --selftest] cwd=[{ROOT}]"
    ]
    _assert_agree(old, new, "docker-absent", old_calls, new_calls)


def test_docker_present_derives_the_image_and_execs_docker(tmp_path: pathlib.Path) -> None:
    """The whole point of the script: the tag comes from the installed
    playwright package, never from a hand-typed pin."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ("npx", "node", "docker"), STUB_NODE_STDOUT="1.55.0"
    )
    assert old.returncode == 0
    lines = old.stdout.splitlines()
    assert lines[0] == (
        "page density: mcr.microsoft.com/playwright:v1.55.0-noble "
        "(tag derived from the installed playwright package)"
    )
    assert old_calls == [
        f"node argv=[-p require('playwright/package.json').version] cwd=[{ROOT}]",
        (
            f"docker argv=[run --rm --ipc=host -v {ROOT}:{ROOT} -w {ROOT} -e CI=true "
            "mcr.microsoft.com/playwright:v1.55.0-noble npx tsx "
            f"scripts/gates/check-page-density.ts --selftest] cwd=[{ROOT}]"
        ),
    ]
    _assert_agree(old, new, "docker-present", old_calls, new_calls)


def test_ipc_host_is_present_in_the_docker_argv(tmp_path: pathlib.Path) -> None:
    """Named separately because it is the one flag whose absence produces a
    Chromium crash rather than a clean failure (the twin's own comment: the
    default 64MB /dev/shm)."""
    old, _new, old_calls, _new_calls = run_both(
        tmp_path, ("npx", "node", "docker"), STUB_NODE_STDOUT="1.55.0"
    )
    assert "--ipc=host" in old.stdout
    assert any("--ipc=host" in call for call in old_calls)


def test_node_failure_propagates_its_exit_code(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ("npx", "node", "docker"),
        STUB_NODE_RC="3",
        STUB_NODE_STDERR="Cannot find module 'playwright/package.json'\n",
    )
    assert old.returncode == 3
    assert not any(call.startswith("docker ") for call in old_calls), (
        "docker was reached after node failed; set -e did not stop the twin"
    )
    _assert_agree(old, new, "node-fails", old_calls, new_calls)


def test_node_stderr_is_not_swallowed(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY for the inherited-stderr requirement. `$(...)` captures
    stdout only, so node's diagnostic must reach the caller. A port that used
    `capture_output=True` would exit with the same code and print the same
    (empty) stdout, so every other assertion in this file would still pass."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ("npx", "node", "docker"),
        STUB_NODE_RC="1",
        STUB_NODE_STDERR="playwright is not installed\n",
    )
    assert "playwright is not installed" in old.stderr, "the TWIN swallowed it; case is untested"
    assert "playwright is not installed" in new.stderr, "the PORT swallowed node's stderr"
    _assert_agree(old, new, "node-stderr", old_calls, new_calls)


def test_missing_node_exits_127_on_both_sides(tmp_path: pathlib.Path) -> None:
    """DOCUMENTED DIVERGENCE: bash's own `line NN: node: command not found`
    carries a line number, so agreement is on the exit code, the stream and
    the named binary rather than on the bytes."""
    old, new, _old_calls, _new_calls = run_both(tmp_path, ("npx", "docker"))
    assert old.returncode == 127
    assert new.returncode == 127
    assert old.stdout == new.stdout == ""
    assert "node" in old.stderr
    assert "not found" in old.stderr
    assert "node" in new.stderr
    assert "not found" in new.stderr


def test_missing_npx_exits_127_on_both_sides(tmp_path: pathlib.Path) -> None:
    """The other documented divergence, on the `exec` rather than the
    substitution."""
    old, new, _old_calls, _new_calls = run_both(tmp_path, ("node",), REDIACC_SMOKE_NO_DOCKER="1")
    assert old.returncode == 127
    assert new.returncode == 127
    assert "npx" in old.stderr
    assert "not found" in old.stderr
    assert "npx" in new.stderr
    assert "not found" in new.stderr


def test_exec_replaces_the_process_so_the_child_exit_code_is_the_gate_s(
    tmp_path: pathlib.Path,
) -> None:
    """`exec` on both sides: a non-zero gate must not be softened into 0 by a
    wrapper that forgot to propagate."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ("npx", "docker", "node"), REDIACC_SMOKE_NO_DOCKER="1", STUB_NPX_RC="7"
    )
    assert old.returncode == 7
    _assert_agree(old, new, "exec-exit-code", old_calls, new_calls)


def test_pure_helpers() -> None:
    """The two derivations, exercised directly rather than through a process."""
    assert page_density.image_for("1.55.0") == "mcr.microsoft.com/playwright:v1.55.0-noble"
    argv = page_density.docker_argv("/repo", "img:1")
    assert argv[:5] == ["docker", "run", "--rm", "--ipc=host", "-v"]
    assert argv[5] == "/repo:/repo"
    assert argv[-4:] == ["npx", "tsx", "scripts/gates/check-page-density.ts", "--selftest"]
    assert "CI=true" in argv


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY. Drop `--ipc=host` from the docker argv -- the exact edit a
    reader who did not know why it was there would make, and one that turns a
    passing gate into a Chromium crash inside the container. Driven red, then
    the source is restored byte-identical and re-verified green."""
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace('        "--ipc=host",\n', "")
    assert mutated != original, "the line this plant targets is no longer present verbatim"

    mutant = tmp_path / "mutant.py"
    mutant.write_text(mutated, encoding="utf-8")
    path = _stub_path(tmp_path, "npx", "node", "docker")
    old_env = _env(path, tmp_path / "plant-old.log", STUB_NODE_STDOUT="1.55.0")
    bad_env = _env(path, tmp_path / "plant-bad.log", STUB_NODE_STDOUT="1.55.0")
    good_env = _env(path, tmp_path / "plant-good.log", STUB_NODE_STDOUT="1.55.0")

    old, old_calls = _run(TWIN, old_env, tmp_path)
    _bad, bad_calls = _run(mutant, bad_env, tmp_path)
    assert any("--ipc=host" in c for c in old_calls), (
        "the TWIN did not pass --ipc=host; the plant is untested"
    )
    assert not any("--ipc=host" in c for c in bad_calls), (
        "the mutant still passed it; the plant did not fire"
    )
    assert bad_calls != old_calls

    good, good_calls = _run(PORT, good_env, tmp_path)
    assert good_calls == old_calls, "restored port no longer agrees with the twin"
    assert good.stdout == old.stdout
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
