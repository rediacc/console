"""Differential: `rediacc_ci.infra.ci_stop_elite` against its twin `.ci/scripts/infra/ci-stop-elite.sh`.

Same technique as `test_infra_ci_stop.py` and for the same reason: the subject shells out to `docker`, so the seam is PATH, and a recording fake `docker` lets the comparison assert on the ARGV SEQUENCE both sides produced rather than only on stdout. A port that printed "Force removing" and never called `docker rm` would pass a stdout-only comparison and leave the container running.

FIXTURE ROOT, NOT THE REAL REPOSITORY. Both subjects derive the console root
from their own file location (`BASH_SOURCE[0]` / `__file__`, three directories
up from where each actually lives -- `.ci/scripts/infra/` for the twin, `.ci/rediacc_ci/infra/` for the port). Driving the TRACKED files directly would point both at this real checkout's `private/elite`, so each case COPIES both subjects into a fresh tree at the right relative depth and runs the copies.

K=5 LEDGER: `.ci/shadow/w7p6-ci-stop-elite.observations.jsonl`, recorded
against a disposable scratch git repo built outside this checkout (this checkout's own working tree is not clean; `shadow-gate.ts --record` refuses a dirty tree). See that file's own header for the exact recording commands.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import tempfile

from rediacc_ci import paths

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "infra" / "ci-stop-elite.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "infra" / "ci_stop_elite.py"

# A recording `docker`, written as Python per ruling 7 (new instruments are Python, not bash) and generated per case so its configuration lives in its own text rather than in an environment two processes deep.
FAKE_DOCKER = """#!/usr/bin/env python3
import sys
LOG = %(log)r
COMPOSE_RC = %(compose_rc)d
PS_NAMES = %(ps_names)r
VERB_RC = %(verb_rc)d
with open(LOG, "a", encoding="utf-8") as fh:
    fh.write("\\t".join(sys.argv[1:]) + "\\n")
argv = sys.argv[1:]
if argv[:1] == ["compose"]:
    sys.exit(COMPOSE_RC)
if argv[:2] == ["ps", "-a"]:
    if PS_NAMES:
        sys.stdout.write("\\n".join(PS_NAMES) + "\\n")
    sys.exit(0)
# REAL docker echoes the container name back on both `stop` and `rm`. Neither
# call is stdout-redirected in the twin, so this must be reproduced here or a
# port that silently swallows that stdout (capture_output=True with nothing
# read back) would agree with the twin on every assertion in this file.
if argv[:1] in (["stop"], ["rm"]) and VERB_RC == 0:
    sys.stdout.write(argv[1] + "\\n")
sys.exit(VERB_RC)
"""


def _fixture(tmp_path: pathlib.Path, *, elite_dir: bool) -> pathlib.Path:
    """A tree shaped like the repository, holding COPIES of both subjects."""
    root = tmp_path / "tree"
    (root / ".ci" / "scripts" / "infra").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "infra").mkdir(parents=True)
    shutil.copy2(TWIN, root / ".ci" / "scripts" / "infra" / TWIN.name)
    shutil.copy2(PORT, root / ".ci" / "rediacc_ci" / "infra" / PORT.name)
    if elite_dir:
        (root / "private" / "elite").mkdir(parents=True)
    return root


def _bin_with_fake_docker(
    where: pathlib.Path,
    log: pathlib.Path,
    *,
    compose_rc: int,
    ps_names: tuple[str, ...],
    verb_rc: int,
) -> pathlib.Path:
    where.mkdir(parents=True, exist_ok=True)
    fake = where / "docker"
    fake.write_text(
        FAKE_DOCKER
        % {
            "log": str(log),
            "compose_rc": compose_rc,
            "ps_names": list(ps_names),
            "verb_rc": verb_rc,
        },
        encoding="utf-8",
    )
    fake.chmod(0o755)
    return where


def _run(
    subject: pathlib.Path,
    root: pathlib.Path,
    *,
    compose_rc: int = 0,
    ps_names: tuple[str, ...] = (),
    verb_rc: int = 0,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    log = root.parent / ("dockerlog-%s.txt" % subject.name)
    log.write_text("", encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    binder = _bin_with_fake_docker(
        root.parent / ("fxbin-%s" % subject.name),
        log,
        compose_rc=compose_rc,
        ps_names=ps_names,
        verb_rc=verb_rc,
    )
    # REPLACED, not prepended: a prepend on a host with a real docker would still pass and occasionally talk to the machine's daemon.
    env["PATH"] = "%s:%s" % (binder, env.get("PATH", ""))
    if subject.suffix == ".sh":
        subject_dir = root / ".ci" / "scripts" / "infra"
        runner = ["bash"]
    else:
        subject_dir = root / ".ci" / "rediacc_ci" / "infra"
        runner = ["python3"]
    proc = subprocess.run(
        [*runner, str(subject_dir / subject.name)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )
    calls = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
    return proc, calls


CASES = [
    ("no-elite-dir-no-container", False, 0, (), 0),
    ("happy-container-present", True, 0, ("rediacc-web",), 0),
    ("container-absent", True, 0, (), 0),
    ("compose-down-fails-container-still-removed", True, 1, ("rediacc-web",), 0),
    ("near-miss-name-untouched", True, 0, ("rediacc-web-2",), 0),
    ("stop-and-rm-fail-still-exits-0", True, 0, ("rediacc-web",), 1),
]


def test_port_and_twin_agree() -> None:
    """Same fixture, both subjects: same exit, same stdout, same docker calls."""
    for name, elite, compose_rc, ps_names, verb_rc in CASES:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = pathlib.Path(td)
            kw = {"compose_rc": compose_rc, "ps_names": ps_names, "verb_rc": verb_rc}

            root_a = _fixture(tmp_path / "a", elite_dir=elite)
            old, old_calls = _run(TWIN, root_a, **kw)

            root_b = _fixture(tmp_path / "b", elite_dir=elite)
            new, new_calls = _run(PORT, root_b, **kw)

            assert new.returncode == old.returncode, "%s: exit code diverged: %r vs %r" % (
                name,
                old.returncode,
                new.returncode,
            )
            assert new.stdout == old.stdout, (
                "%s: stdout diverged:\n--- twin ---\n%s\n--- port ---\n%s"
                % (
                    name,
                    old.stdout,
                    new.stdout,
                )
            )
            assert new_calls == old_calls, (
                "%s: the docker CALLS diverged:\n twin: %s\n port: %s"
                % (
                    name,
                    old_calls,
                    new_calls,
                )
            )


def test_the_fake_is_actually_reached() -> None:
    """ANTI-VACUITY. Without this, every comparison above proves nothing: two programs that never touched docker agree trivially."""
    with tempfile.TemporaryDirectory() as td:
        root = _fixture(pathlib.Path(td) / "v", elite_dir=True)
        _, calls = _run(PORT, root, ps_names=("rediacc-web",))
        assert calls, "the recording docker was never invoked; this file proves nothing"
        verbs = [c.split("\t")[0] for c in calls]
        assert "compose" in verbs, "compose down was never attempted: %r" % verbs
        assert "rm" in verbs, "the container was never removed: %r" % verbs


def test_the_force_removal_is_conditional() -> None:
    """CONTROL for the case above: with no matching container, nothing is removed. A port that removed unconditionally would satisfy every positive assertion here and would `docker rm` a container another job is using."""
    with tempfile.TemporaryDirectory() as td:
        root = _fixture(pathlib.Path(td) / "c", elite_dir=True)
        _, calls = _run(PORT, root, ps_names=())
        verbs = [c.split("\t")[0] for c in calls]
        assert "rm" not in verbs, "removed a container that docker ps did not name: %r" % verbs


def test_compose_down_failure_does_not_skip_force_removal() -> None:
    """The twin falls through to the removal loop even when `docker compose ... down` fails; an early return here would leave `rediacc-web` running whenever compose already failed -- exactly the case force removal exists for."""
    with tempfile.TemporaryDirectory() as td:
        root = _fixture(pathlib.Path(td) / "d", elite_dir=True)
        _, calls = _run(PORT, root, compose_rc=1, ps_names=("rediacc-web",))
        verbs = [c.split("\t")[0] for c in calls]
        assert "rm" in verbs, "compose failing must not skip force removal: %r" % verbs
