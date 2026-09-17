"""Differential: `rediacc_ci.quality.browser_smoke` against its twin
`.ci/scripts/quality/browser-smoke.sh`.

THE SUBJECT IS A LAUNCHER, so what is under test is the LAUNCH: which binary,
with exactly which argv, from which working directory, after which stdout
line. The real `scripts/gates/check-browser-smoke.ts` is never run here -- it drives six routes in a real Chromium inside a Playwright container and takes minutes -- and it does not need to be, because it is TypeScript and is identical on both sides of this comparison by construction.

THE SEAM IS PATH, populated with recording stubs for `npx`, `node`, `docker` and `id` (ruling 7's shape, as in `test_pr_sync_epic_block.py`). Each stub prints its own name, its argv and its cwd, so a divergence in ANY of the four things the launcher decides shows up as a text difference rather than as a silent pass. The cwd line is not decoration: the twin `cd`s to
`SCRIPT_DIR/../../..` and the port to `paths.repo_root()`, and those are two independent derivations of the same directory that could drift apart without any other assertion here noticing.

DOCKER ABSENCE IS SIMULATED BY OMITTING THE STUB, never by an environment flag, because `command -v docker` / `shutil.which("docker")` is the branch under test. The real docker on this machine is out of PATH for every case. `id` absence is simulated the same way, and that case is the reproduced defect below.

`id` GETS PER-ARGUMENT STUB OUTPUT (`STUB_ID_STDOUT_U` and `STUB_ID_STDOUT_G`, deliberately DIFFERENT numbers) so that a port which called `id -g` twice, or which assembled `gid:uid`, fails rather than passing on a coincidence. A single shared value would have made `-u 1000:1000` unfalsifiable.

THE REPRODUCED DEFECT HAS ITS OWN CASE.
`test_missing_id_yields_a_bare_colon_on_both_sides` drives the TWIN with `id` off PATH and asserts the twin itself hands docker `-u :` while exiting 0. That assertion is on the BASH side first: if bash ever started aborting there, the
case would fail loudly rather than quietly testing a port behaviour nothing
mirrors any more.

THREE CASES ASSERT AGREEMENT ON EXIT CODE AND SUBSTANCE RATHER THAN BYTES, and they are the three the port's docstring names as divergences: a missing `node`, a missing `npx` and a missing `id` all produce bash's own `<script>: line NN: ...` text, which carries a line number no port should reproduce. Everything else in this file is byte-for-byte.

TWO CASES PIN THE DIFFERENCES FROM THE NEAR-IDENTICAL SIBLING
`page-density.sh`: the mount target is `/work` and NOT the host path, and there
is no `-e CI=true`. Both are the exact edits a reader who had just read the
sibling would make, and neither would break any other assertion here.

K=5 LEDGER: `.ci/shadow/w7p6-browser-smoke.observations.jsonl` -- five
distinct trees, `--assert --k 5` prints "equivalence holds over 5 distinct trees". Recorded in a disposable scratch repo outside this checkout (dirty
tree; `--record` refuses one) with recording stubs of the same shape on PATH,
varying the branch across trees: REDIACC_SMOKE_NO_DOCKER=1, docker absent, the
docker path at playwright 1.55.0, the docker path at 1.61.1 with different ids, and a failing node.

THE MISSING-`id` CASE IS DELIBERATELY NOT IN THE LEDGER, and the reason is worth stating so its absence does not read as an oversight. shadow-gate compares normalized finding TEXT, and on that path the two sides legitimately differ in text: bash emits `<script>: line 50: id: command not found` and the port emits `browser-smoke.py: id: command not found`. Recording it would enter a
MISMATCH row, which DISQUALIFIES that tree permanently -- the tree id is the content of both implementations, so it can never be cleared by re-running. The substance of that path (exit code, both stderr lines, the resulting `-u :`, the docker argv) is asserted instead by `test_missing_id_yields_a_bare_colon_on_both_sides`, which compares the two sides directly and does not have to
go through a text fingerprint.

BEYOND THE STUBS, THE REAL THING WAS DRIVEN ON BOTH BRANCHES, 2026-09-14, and
this is the part the stubs cannot vouch for. `REDIACC_SMOKE_NO_DOCKER=1 bash
.ci/scripts/quality/browser-smoke.sh` and `REDIACC_SMOKE_NO_DOCKER=1
PYTHONPATH=.ci python3 -m rediacc_ci.quality.browser_smoke` both ran the real
`scripts/gates/check-browser-smoke.ts` against a real Chromium over all six routes and exited 0 with BYTE-IDENTICAL stdout and stderr. Then the same pair
with no escape hatch, so both went through the container: both pulled
`mcr.microsoft.com/playwright:v1.61.1-noble` (the tag derived from the installed package, not typed), ran the gate inside it as the invoking user and exited 0, again byte-identical on both streams.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

from rediacc_ci import paths
from rediacc_ci.quality import browser_smoke

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "quality" / "browser-smoke.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "quality" / "browser_smoke.py"
BASH = shutil.which("bash") or "/bin/bash"

# A recording stub: name, argv, cwd, then whatever the case asked it to do. `#!/usr/bin/python3` absolute, not `/usr/bin/env python3`: these run with a PATH that deliberately holds almost nothing, and `env` would fail to resolve the interpreter.
STUB = """#!/usr/bin/python3
import os
import sys

name = os.path.basename(sys.argv[0])
record = "%s argv=[%s] cwd=[%s]" % (name, " ".join(sys.argv[1:]), os.getcwd())
with open(os.environ["STUB_LOG"], "a") as fh:
    fh.write(record + "\\n")
# QUIET exists for `node` and `id`: the twin captures the stdout of both into a
# substitution, so a stub that chattered there would be feeding its own
# recording into the image tag or into `-u`. Every other stub echoes, because
# for those the recording IS the observable behaviour under test.
if os.environ.get("STUB_%s_QUIET" % name.upper()) != "1":
    print("STUB " + record)
# Per-argument output, so `id -u` and `id -g` can be told apart. The key is the
# alphanumerics of the argv, uppercased: `-u` -> U, `-g` -> G.
key = "".join(c for c in "_".join(sys.argv[1:]) if c.isalnum() or c == "_").upper()
rc = int(os.environ.get("STUB_%s_RC" % name.upper(), "0"))
specific = os.environ.get("STUB_%s_STDOUT_%s" % (name.upper(), key))
out = specific if specific is not None else os.environ.get("STUB_%s_STDOUT" % name.upper(), "")
err = os.environ.get("STUB_%s_STDERR" % name.upper(), "")
if out:
    print(out)
if err:
    sys.stderr.write(err)
sys.exit(rc)
"""

# The twin needs `dirname` to compute its own REPO_ROOT (line 32). Nothing
# else external is reached before the branch under test on either side.
PATH_MINIMUM = ("dirname",)

# Every external binary either subject can reach. Anything not explicitly stubbed for a case must be absent, or the case is testing the machine rather than the script.
EXTERNALS = ("docker", "npx", "node", "id")

# Deliberately different, and deliberately not this machine's real ids.
UID_STUB = "4242"
GID_STUB = "4343"

GATE = "scripts/gates/check-browser-smoke.ts --selftest"


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
    for absent in EXTERNALS:
        if absent not in names:
            assert shutil.which(absent, path=str(stub)) is None, f"{absent} leaked into the stub"
    return str(stub)


def _run(
    subject: pathlib.Path, env: dict[str, str], cwd: pathlib.Path
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Run one side. Returns its streams AND the stub call log.

    The log is a separate artifact from stdout on purpose: neither `node`'s nor `id`'s recording reaches stdout (see STUB's QUIET note), so without it the image-derivation and the `-u` cases would assert nothing about how those two were invoked.
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
        "STUB_ID_QUIET": "1",
        "STUB_ID_STDOUT_U": UID_STUB,
        "STUB_ID_STDOUT_G": GID_STUB,
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
    # cwd is deliberately NOT the repo: both subjects must cd to the root themselves, and starting them there would hide a port that did not.
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


def _docker_call(image: str, uid_gid: str) -> str:
    """The one docker invocation the twin makes, as the stub records it."""
    return (
        f"docker argv=[run --rm --ipc=host -u {uid_gid} -e HOME=/tmp "
        f"-e npm_config_cache=/tmp/.npm -v {ROOT}:/work -w /work "
        f"{image} npx tsx {GATE}] cwd=[{ROOT}]"
    )


def test_no_docker_env_execs_npx_with_no_note(tmp_path: pathlib.Path) -> None:
    """`REDIACC_SMOKE_NO_DOCKER=1` is the escape hatch, and it must NOT print
    the "docker not found" note -- the operator asked for this path."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ("npx", "docker", "node", "id"), REDIACC_SMOKE_NO_DOCKER="1"
    )
    assert old.returncode == 0
    assert old.stdout == f"STUB npx argv=[tsx {GATE}] cwd=[{ROOT}]\n"
    assert "note:" not in old.stdout
    assert old_calls == [f"npx argv=[tsx {GATE}] cwd=[{ROOT}]"]
    _assert_agree(old, new, "no-docker-env", old_calls, new_calls)


def test_docker_absent_prints_the_note_then_execs_npx(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ("npx", "node", "id"))
    assert old.returncode == 0
    assert old.stdout.splitlines()[0] == (
        "note: docker not found, running the gate directly (needs a local Chromium)"
    )
    assert old_calls == [f"npx argv=[tsx {GATE}] cwd=[{ROOT}]"]
    _assert_agree(old, new, "docker-absent", old_calls, new_calls)


def test_docker_present_derives_the_image_and_execs_docker(tmp_path: pathlib.Path) -> None:
    """The whole point of the script: the tag comes from the installed
    playwright package, never from a hand-typed pin. The full docker argv is asserted token for token, because every token in it was put there for a
    reason the twin states."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ("npx", "node", "docker", "id"), STUB_NODE_STDOUT="1.55.0"
    )
    assert old.returncode == 0
    lines = old.stdout.splitlines()
    assert lines[0] == (
        "browser smoke: mcr.microsoft.com/playwright:v1.55.0-noble "
        "(tag derived from the installed playwright package)"
    )
    assert old_calls == [
        f"node argv=[-p require('playwright/package.json').version] cwd=[{ROOT}]",
        f"id argv=[-u] cwd=[{ROOT}]",
        f"id argv=[-g] cwd=[{ROOT}]",
        _docker_call("mcr.microsoft.com/playwright:v1.55.0-noble", f"{UID_STUB}:{GID_STUB}"),
    ]
    _assert_agree(old, new, "docker-present", old_calls, new_calls)


def test_uid_and_gid_are_read_separately_and_in_that_order(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY for `-u`. The two stub values differ, so a port that read
    the gid twice, or swapped the pair, produces `4343:4343` or `4343:4242`
    here rather than passing on two identical numbers."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ("npx", "node", "docker", "id"), STUB_NODE_STDOUT="1.55.0"
    )
    assert UID_STUB != GID_STUB, "the two stub ids must differ or this case proves nothing"
    assert any(f"-u {UID_STUB}:{GID_STUB}" in call for call in old_calls), (
        f"the TWIN did not pass -u {UID_STUB}:{GID_STUB}; the case is untested"
    )
    id_calls = [c for c in old_calls if c.startswith("id ")]
    assert id_calls == [f"id argv=[-u] cwd=[{ROOT}]", f"id argv=[-g] cwd=[{ROOT}]"]
    _assert_agree(old, new, "uid-gid", old_calls, new_calls)


def test_ipc_host_is_present_in_the_docker_argv(tmp_path: pathlib.Path) -> None:
    """Named separately because it is the one flag whose absence produces a
    Chromium crash rather than a clean failure (the twin's own comment: the
    default 64MB /dev/shm)."""
    old, _new, old_calls, _new_calls = run_both(
        tmp_path, ("npx", "node", "docker", "id"), STUB_NODE_STDOUT="1.55.0"
    )
    assert "--ipc=host" in old.stdout
    assert any("--ipc=host" in call for call in old_calls)


def test_mount_target_is_work_and_not_the_host_path(tmp_path: pathlib.Path) -> None:
    """PINS A DIFFERENCE FROM THE SIBLING `page-density.sh`, which mounts the
    repo at its own absolute path. Copying that line across would still run the
    gate and still pass every other case in this file."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ("npx", "node", "docker", "id"), STUB_NODE_STDOUT="1.55.0"
    )
    assert any(f"-v {ROOT}:/work -w /work" in call for call in old_calls), (
        "the TWIN no longer mounts at /work; this pin is stale"
    )
    assert not any(f"-v {ROOT}:{ROOT}" in call for call in old_calls)
    _assert_agree(old, new, "mount-target", old_calls, new_calls)


def test_no_ci_true_is_passed(tmp_path: pathlib.Path) -> None:
    """The other sibling difference: `page-density.sh` passes `-e CI=true` and
    this one does not. Pinned so the port cannot acquire it by osmosis."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ("npx", "node", "docker", "id"), STUB_NODE_STDOUT="1.55.0"
    )
    assert not any("CI=true" in call for call in old_calls), (
        "the TWIN now passes CI=true; this pin is stale"
    )
    assert not any("CI=true" in call for call in new_calls)
    _assert_agree(old, new, "no-ci-true", old_calls, new_calls)


def test_home_and_npm_cache_are_redirected_for_the_non_root_user(tmp_path: pathlib.Path) -> None:
    """`-u` drops to a user with no writable home in the image, so these two
    are what keep `npx` from failing on an unwritable cache. They travel with
    `-u` and are meaningless without it."""
    _old, _new, old_calls, _new_calls = run_both(
        tmp_path, ("npx", "node", "docker", "id"), STUB_NODE_STDOUT="1.55.0"
    )
    docker_calls = [c for c in old_calls if c.startswith("docker ")]
    assert len(docker_calls) == 1
    assert "-e HOME=/tmp" in docker_calls[0]
    assert "-e npm_config_cache=/tmp/.npm" in docker_calls[0]


def test_node_failure_propagates_its_exit_code(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ("npx", "node", "docker", "id"),
        STUB_NODE_RC="3",
        STUB_NODE_STDERR="Cannot find module 'playwright/package.json'\n",
    )
    assert old.returncode == 3
    assert not any(call.startswith("docker ") for call in old_calls), (
        "docker was reached after node failed; set -e did not stop the twin"
    )
    assert not any(call.startswith("id ") for call in old_calls), (
        "id was reached after node failed; set -e did not stop the twin"
    )
    _assert_agree(old, new, "node-fails", old_calls, new_calls)


def test_node_stderr_is_not_swallowed(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY for the inherited-stderr requirement. `$(...)` captures
    stdout only, so node's diagnostic must reach the caller. A port that used
    `capture_output=True` would exit with the same code and print the same
    (empty) stdout, so every other assertion in this file would still pass."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ("npx", "node", "docker", "id"),
        STUB_NODE_RC="1",
        STUB_NODE_STDERR="playwright is not installed\n",
    )
    assert "playwright is not installed" in old.stderr, "the TWIN swallowed it; case is untested"
    assert "playwright is not installed" in new.stderr, "the PORT swallowed node's stderr"
    _assert_agree(old, new, "node-stderr", old_calls, new_calls)


def test_id_stderr_is_not_swallowed_and_its_exit_code_is_ignored(
    tmp_path: pathlib.Path,
) -> None:
    """The asymmetry the port's docstring names: `$(id -u)` sits inside an
    argument list, so `set -e` cannot see its status. `id` printing a value and THEN failing must still yield that value, and its stderr must still reach
    the caller."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ("npx", "node", "docker", "id"),
        STUB_NODE_STDOUT="1.55.0",
        STUB_ID_RC="5",
        STUB_ID_STDERR="id: cannot find name for user ID\n",
    )
    assert old.returncode == 0, (
        f"the TWIN aborted on a failing id (exit {old.returncode}); the asymmetry is gone"
    )
    assert "id: cannot find name for user ID" in old.stderr
    assert any(f"-u {UID_STUB}:{GID_STUB}" in c for c in old_calls), (
        "the TWIN dropped the value id printed before failing"
    )
    _assert_agree(old, new, "id-fails-nonzero", old_calls, new_calls)


def test_missing_id_yields_a_bare_colon_on_both_sides(tmp_path: pathlib.Path) -> None:
    """REPRODUCED DEFECT (`browser-smoke.sh:51`). With `id` off PATH, bash's
    `set -euo pipefail` does NOT abort: a failed command substitution inside an argument list is not a failed command. The twin prints `id: command not found` twice, substitutes the empty string for both, and hands docker a literal `-u :`.

    The twin's behaviour is asserted FIRST. If bash ever started aborting here this case fails on the old side, rather than quietly testing a port behaviour that no longer mirrors anything.

    Text diverges (bash's prefix carries a line number), so agreement is on the
    exit code, the docker argv and the stderr shape."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ("npx", "node", "docker"), STUB_NODE_STDOUT="1.55.0"
    )
    # The TWIN, first.
    assert old.returncode == 0, "the twin aborted; the defect this reproduces is gone"
    assert old.stderr.count("id: command not found") == 2, (
        f"expected two bash not-found lines, got: {old.stderr!r}"
    )
    assert old_calls == [
        f"node argv=[-p require('playwright/package.json').version] cwd=[{ROOT}]",
        _docker_call("mcr.microsoft.com/playwright:v1.55.0-noble", ":"),
    ]
    # The PORT reproduces it rather than repairing it with os.getuid().
    assert new.returncode == old.returncode
    assert new.stdout == old.stdout
    assert new_calls == old_calls, (
        f"the port did not reproduce the bare colon:\nold: {old_calls}\nnew: {new_calls}"
    )
    assert new.stderr.count("id: command not found") == 2, (
        f"the port did not report the missing id twice: {new.stderr!r}"
    )


def test_missing_node_exits_127_on_both_sides(tmp_path: pathlib.Path) -> None:
    """DOCUMENTED DIVERGENCE: bash's own `line NN: node: command not found`
    carries a line number, so agreement is on the exit code, the stream and
    the named binary rather than on the bytes."""
    old, new, _old_calls, _new_calls = run_both(tmp_path, ("npx", "docker", "id"))
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
    old, new, _old_calls, _new_calls = run_both(
        tmp_path, ("node", "id"), REDIACC_SMOKE_NO_DOCKER="1"
    )
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
        tmp_path,
        ("npx", "docker", "node", "id"),
        REDIACC_SMOKE_NO_DOCKER="1",
        STUB_NPX_RC="7",
    )
    assert old.returncode == 7
    _assert_agree(old, new, "exec-exit-code", old_calls, new_calls)


def test_docker_exit_code_is_the_gate_s(tmp_path: pathlib.Path) -> None:
    """The same propagation on the container branch, which is the one CI uses."""
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ("npx", "docker", "node", "id"),
        STUB_NODE_STDOUT="1.55.0",
        STUB_DOCKER_RC="4",
    )
    assert old.returncode == 4
    _assert_agree(old, new, "docker-exit-code", old_calls, new_calls)


def test_pure_helpers() -> None:
    """The derivations, exercised directly rather than through a process."""
    assert browser_smoke.image_for("1.55.0") == "mcr.microsoft.com/playwright:v1.55.0-noble"
    argv = browser_smoke.docker_argv("/repo", "img:1", "10", "20")
    assert argv[:4] == ["docker", "run", "--rm", "--ipc=host"]
    assert argv[4:6] == ["-u", "10:20"]
    assert "-v" in argv
    assert argv[argv.index("-v") + 1] == "/repo:/work"
    assert argv[argv.index("-w") + 1] == "/work"
    assert argv[-4:] == ["npx", "tsx", "scripts/gates/check-browser-smoke.ts", "--selftest"]
    assert "CI=true" not in argv, "this is the sibling page-density's flag, not this one's"


def test_id_value_strips_only_trailing_newlines() -> None:
    """`$(...)` removes trailing newlines and nothing else, so a leading space
    survives on both sides. `.strip()` would eat it."""
    assert browser_smoke.id_value("-u") == browser_smoke.id_value("-u")
    assert browser_smoke.id_value("-u").isdigit(), "the real id -u did not return a number"
    assert browser_smoke.id_value("-u") == str(os.getuid())


def test_planted_defect_ipc_host(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY. Drop `--ipc=host` from the docker argv -- the exact edit a
    reader who did not know why it was there would make, and one that turns a passing gate into a Chromium crash inside the container. Driven red, then
    the source is restored byte-identical and re-verified green."""
    _plant(
        tmp_path,
        '        "--ipc=host",\n',
        "",
        lambda calls: not any("--ipc=host" in c for c in calls),
        lambda calls: any("--ipc=host" in c for c in calls),
    )


def test_planted_defect_getuid_instead_of_id(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY for the reproduced defect. Replace the `id` shell-out with
    `os.getuid()`, which is what a reviewer would call an improvement. The port then stops calling `id` at all, so the call log loses two entries and the
    missing-`id` path silently repairs itself."""
    _plant(
        tmp_path,
        '    uid = id_value("-u")\n    gid = id_value("-g")\n',
        "    uid = str(os.getuid())\n    gid = str(os.getgid())\n",
        lambda calls: not any(c.startswith("id ") for c in calls),
        lambda calls: [c for c in calls if c.startswith("id ")] != [],
    )


def test_planted_defect_mounts_the_host_path(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY for the sibling pin. Mount the repo at its own path the way
    `page-density.sh` does. The gate still runs, still exits 0, and only the
    argv shows it."""
    _plant(
        tmp_path,
        'WORKDIR = "/work"',
        "WORKDIR = None  # replaced below",
        lambda calls: not any("-w /work" in c for c in calls),
        lambda calls: any("-w /work" in c for c in calls),
        extra=('        "%s:%s" % (root, WORKDIR),', '        "%s:%s" % (root, root),'),
    )


def _plant(
    tmp_path: pathlib.Path,
    old_text: str,
    new_text: str,
    mutant_ok,
    port_ok,
    extra: tuple[str, str] | None = None,
) -> None:
    """Run one plant: mutate a COPY, prove the differential goes red, prove the
    on-disk port is byte-identical afterwards and still agrees with the twin.

    The mutation is never written to `PORT`. A plant that edited the real file and restored it would leave the tree wrong if the assertion in between raised, and this tree has no safety net.
    """
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace(old_text, new_text)
    assert mutated != original, f"the text this plant targets is gone: {old_text!r}"
    if extra is not None:
        before = mutated
        mutated = mutated.replace(extra[0], extra[1])
        assert mutated != before, f"the second edit of this plant found nothing: {extra[0]!r}"

    mutant = tmp_path / "mutant.py"
    mutant.write_text(mutated, encoding="utf-8")
    path = _stub_path(tmp_path, "npx", "node", "docker", "id")
    common = {"STUB_NODE_STDOUT": "1.55.0"}
    old, old_calls = _run(TWIN, _env(path, tmp_path / "plant-old.log", **common), tmp_path)
    _bad, bad_calls = _run(mutant, _env(path, tmp_path / "plant-bad.log", **common), tmp_path)

    assert port_ok(old_calls), f"the TWIN does not exhibit what this plant removes: {old_calls}"
    assert mutant_ok(bad_calls), (
        f"the mutant still behaved correctly; plant did not fire: {bad_calls}"
    )
    assert bad_calls != old_calls, "the differential would not have gone red"

    good, good_calls = _run(PORT, _env(path, tmp_path / "plant-good.log", **common), tmp_path)
    assert good_calls == old_calls, "restored port no longer agrees with the twin"
    assert good.stdout == old.stdout
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
