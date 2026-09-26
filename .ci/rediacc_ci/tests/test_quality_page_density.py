"""`rediacc_ci.quality.page_density`, driven directly.

THE SUBJECT IS A LAUNCHER, so what is under test is the LAUNCH: which binary, with exactly which argv, from which working directory, after which stdout line. The real `scripts/gates/check-page-density.ts` is never run here -- it drives three routes across four viewports in a Playwright container and takes minutes -- and it does not need to be, because it is TypeScript and was
identical on both sides of the comparison this file used to carry.

THE SEAM IS PATH, populated with recording stubs for `npx`, `node` and `docker` (ruling 7's shape, as in `test_pr_sync_epic_block.py`). Each stub prints its own name, its argv and its cwd, so a divergence in ANY of the three things the launcher decides shows up as a text difference rather than as a silent pass.

K=5 LEDGER: `.ci/shadow/w7p6-page-density.observations.jsonl` -- five distinct trees, `--assert --k 5` prints "equivalence holds over 5 distinct trees". Recorded in a disposable scratch repo outside this checkout (dirty tree; `--record` refuses one) with the same recording stubs on PATH, varying the branch across trees: REDIACC_SMOKE_NO_DOCKER=1, docker absent, two different
playwright versions, and a failing node.

ON THE STRENGTH OF IT THE TWIN `.ci/scripts/quality/page-density.sh` was retired in W7 P5, and the cases that ran it went with it: the escape hatch, the docker-absent note, the derived image tag, `--ipc=host`, exit-code propagation from node, npx and the container, node's stderr reaching the caller, and the two 127 paths where bash's own `line NN:` prefix made agreement a
matter of exit code and substance rather than bytes.

BEYOND THE STUBS, THE REAL THING WAS DRIVEN ONCE, 2026-09-10: `npm run check:ci-page-density` (then the bash twin) and `python3 -m rediacc_ci.quality.page_density` both pulled the real `mcr.microsoft.com/playwright:v1.61.1-noble` container, ran the real gate and exited 0 with BYTE-IDENTICAL stdout and stderr.

THE PLANT BELOW IS WHAT KEEPS THIS FILE HONEST WITHOUT A TWIN. It mutates a COPY of the port, proves the mutant's argv differs from the real port's, and proves the port source is byte-identical afterwards.
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
PORT = ROOT / ".ci" / "rediacc_ci" / "quality" / "page_density.py"
BASH = shutil.which("bash") or "/bin/bash"

# A recording stub: name, argv, cwd, then whatever the case asked it to do. `#!/usr/bin/python3` absolute, not `/usr/bin/env python3`: these run with a PATH that deliberately holds almost nothing, and `env` would fail to resolve the interpreter.
STUB = """#!/usr/bin/python3
import os
import sys

name = os.path.basename(sys.argv[0])
record = "%s argv=[%s] cwd=[%s]" % (name, " ".join(sys.argv[1:]), os.getcwd())
with open(os.environ["STUB_LOG"], "a") as fh:
    fh.write(record + "\\n")
# QUIET exists for `node` alone: the gate captures node's STDOUT into
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

# `dirname` is on the stub PATH because the retired twin needed it to compute its own REPO_ROOT. Nothing else external is reached before the branch under test.
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
    """Run one subject. Returns its streams AND the stub call log.

    The log is a separate artifact from stdout on purpose: `node`'s recording never reaches stdout (see STUB's QUIET note), so without it the image-derivation cases would assert nothing about how node was invoked.
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


def test_pure_helpers() -> None:
    """The two derivations, exercised directly rather than through a process."""
    assert page_density.image_for("1.55.0") == "mcr.microsoft.com/playwright:v1.55.0-noble"
    argv = page_density.docker_argv("/repo", "img:1")
    assert argv[:5] == ["docker", "run", "--rm", "--ipc=host", "-v"]
    assert argv[5] == "/repo:/repo"
    assert argv[-4:] == ["npx", "tsx", "scripts/gates/check-page-density.ts", "--selftest"]
    assert "CI=true" in argv


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY. Drop `--ipc=host` from the docker argv -- the exact edit a reader who did not know why it was there would make, and one that turns a passing gate into a Chromium crash inside the container. Driven red against a mutated COPY, then the on-disk source is re-verified byte-identical."""
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace('        "--ipc=host",\n', "")
    assert mutated != original, "the line this plant targets is no longer present verbatim"

    mutant = tmp_path / "mutant.py"
    mutant.write_text(mutated, encoding="utf-8")
    path = _stub_path(tmp_path, "npx", "node", "docker")
    good_env = _env(path, tmp_path / "plant-good.log", STUB_NODE_STDOUT="1.55.0")
    bad_env = _env(path, tmp_path / "plant-bad.log", STUB_NODE_STDOUT="1.55.0")

    _good, good_calls = _run(PORT, good_env, tmp_path)
    _bad, bad_calls = _run(mutant, bad_env, tmp_path)
    assert any("--ipc=host" in c for c in good_calls), (
        "the PORT did not pass --ipc=host; the plant is untested"
    )
    assert not any("--ipc=host" in c for c in bad_calls), (
        "the mutant still passed it; the plant did not fire"
    )
    assert bad_calls != good_calls

    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
