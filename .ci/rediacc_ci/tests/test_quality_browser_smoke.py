"""`rediacc_ci.quality.browser_smoke`, driven directly.

THE SUBJECT IS A LAUNCHER, so what is under test is the LAUNCH: which binary, with exactly which argv, from which working directory, after which stdout line. The real `scripts/gates/check-browser-smoke.ts` is never run here -- it drives six routes in a real Chromium inside a Playwright container and takes minutes -- and it does not need to be, because it is TypeScript and was
identical on both sides of the comparison this file used to carry.

THE SEAM IS PATH, populated with recording stubs for `npx`, `node`, `docker` and `id` (ruling 7's shape, as in `test_pr_sync_epic_block.py`). Each stub prints its own name, its argv and its cwd, so a divergence in ANY of the four things the launcher decides shows up as a text difference rather than as a silent pass. Docker absence is simulated by OMITTING the stub, never by an
environment flag, because `shutil.which("docker")` is the branch under test.

`id` GETS PER-ARGUMENT STUB OUTPUT (`STUB_ID_STDOUT_U` and `STUB_ID_STDOUT_G`, deliberately DIFFERENT numbers) so that a port which called `id -g` twice, or which assembled `gid:uid`, fails rather than passing on a coincidence. A single shared value would have made `-u 1000:1000` unfalsifiable.

K=5 LEDGER: `.ci/shadow/w7p6-browser-smoke.observations.jsonl` -- five distinct trees, `--assert --k 5` prints "equivalence holds over 5 distinct trees". Recorded in a disposable scratch repo outside this checkout (dirty tree; `--record` refuses one) with recording stubs of the same shape on PATH, varying the branch across trees: REDIACC_SMOKE_NO_DOCKER=1, docker absent, the
docker path at playwright 1.55.0, the docker path at 1.61.1 with different ids, and a failing node.

ON THE STRENGTH OF IT THE TWIN `.ci/scripts/quality/browser-smoke.sh` was retired in W7 P5, and every case that ran it went with it: the escape hatch, the docker-absent note, the derived image tag, the full docker argv token for token, `--ipc=host`, the `/work` mount target and the absent `-e CI=true` that both separate this launcher from its near-identical sibling
`page-density.sh`, the redirected HOME and npm cache, exit-code propagation from node, npx and the container, node's and `id`'s stderr reaching the caller, and the three 127-style paths where bash's own `line NN:` prefix made agreement a matter of exit code and substance rather than bytes.

THE REPRODUCED DEFECT WENT WITH THEM and is recorded here so its absence does not read as a repair. With `id` off PATH, bash's `set -euo pipefail` does NOT abort: a failed command substitution inside an argument list is not a failed command, so the twin printed `id: command not found` twice, substituted the empty string for both, and handed docker a literal `-u :`. The port
reproduces that rather than repairing it with `os.getuid()`, and the plant below is what stops the repair arriving unnoticed. That path was deliberately never recorded in the ledger either: shadow-gate compares normalized finding TEXT and the two sides legitimately differed there, so a row would have entered a MISMATCH that permanently disqualifies a tree.

BEYOND THE STUBS, THE REAL THING WAS DRIVEN ON BOTH BRANCHES, 2026-09-14. `REDIACC_SMOKE_NO_DOCKER=1` against the twin and against `python3 -m rediacc_ci.quality.browser_smoke` both ran the real `scripts/gates/check-browser-smoke.ts` against a real Chromium over all six routes and exited 0 with BYTE-IDENTICAL stdout and stderr. Then the same pair with no escape hatch, so both
went through the container: both pulled `mcr.microsoft.com/playwright:v1.61.1-noble` (the tag derived from the installed package, not typed), ran the gate inside it as the invoking user and exited 0, again byte-identical on both streams.
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
# QUIET exists for `node` and `id`: the gate captures the stdout of both into a
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

# `dirname` is on the stub PATH because the retired twin needed it to compute its own REPO_ROOT. Nothing else external is reached before the branch under test.
PATH_MINIMUM = ("dirname",)

# Every external binary the launcher can reach. Anything not explicitly stubbed for a case must be absent, or the case is testing the machine rather than the script.
EXTERNALS = ("docker", "npx", "node", "id")

# Deliberately different, and deliberately not this machine's real ids.
UID_STUB = "4242"
GID_STUB = "4343"


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
    """Run one subject. Returns its streams AND the stub call log.

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
    """`$(...)` removes trailing newlines and nothing else, so a leading space survives on both sides. `.strip()` would eat it."""
    assert browser_smoke.id_value("-u") == browser_smoke.id_value("-u")
    assert browser_smoke.id_value("-u").isdigit(), "the real id -u did not return a number"
    assert browser_smoke.id_value("-u") == str(os.getuid())


def test_planted_defect_ipc_host(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY. Drop `--ipc=host` from the docker argv -- the exact edit a
    reader who did not know why it was there would make, and one that turns a passing gate into a Chromium crash inside the container. Driven red against a mutated COPY, then the on-disk source is re-verified byte-identical."""
    _plant(
        tmp_path,
        '        "--ipc=host",\n',
        "",
        lambda calls: not any("--ipc=host" in c for c in calls),
        lambda calls: any("--ipc=host" in c for c in calls),
    )


def test_planted_defect_getuid_instead_of_id(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY for the reproduced defect. Replace the `id` shell-out with `os.getuid()`, which is what a reviewer would call an improvement. The port then stops calling `id` at all, so the call log loses two entries and the missing-`id` path silently repairs itself."""
    _plant(
        tmp_path,
        '    uid = id_value("-u")\n    gid = id_value("-g")\n',
        "    uid = str(os.getuid())\n    gid = str(os.getgid())\n",
        lambda calls: not any(c.startswith("id ") for c in calls),
        lambda calls: [c for c in calls if c.startswith("id ")] != [],
    )


def test_planted_defect_mounts_the_host_path(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY for the sibling pin. Mount the repo at its own path the way the sibling `rediacc_ci.quality.page_density` does. The gate still runs, still exits 0, and only the argv shows it."""
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
    """Run one plant: mutate a COPY, prove it behaves differently from the port on disk, and prove the port source is byte-identical afterwards.

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
    _good, good_calls = _run(PORT, _env(path, tmp_path / "plant-good.log", **common), tmp_path)
    _bad, bad_calls = _run(mutant, _env(path, tmp_path / "plant-bad.log", **common), tmp_path)

    assert port_ok(good_calls), f"the PORT does not exhibit what this plant removes: {good_calls}"
    assert mutant_ok(bad_calls), (
        f"the mutant still behaved correctly; plant did not fire: {bad_calls}"
    )
    assert bad_calls != good_calls, "the plant would not have gone red"
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
