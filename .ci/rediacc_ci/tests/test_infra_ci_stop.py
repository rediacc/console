"""Differential: `.ci/rediacc_ci/infra/ci_stop.py` against its twin `ci-stop.sh`.

WHY A DIFFERENTIAL AND NOT A UNIT TEST. The claim a port makes is not "the new code is correct", it is "the new code says what the old code said". Only running BOTH, on the same fixture, in the same run, can support that -- and it is the same argument `.ci/rediacc_ci/tests/gates/test_twin_parity.py` makes for the gate ports, applied to a non-gate script that has no gate harness to
hang from.

HOW DOCKER IS FAKED, AND WHY IT IS A FAKE RATHER THAN A MOCK. The subject shells out to `docker`, so the seam that matters is PATH. Each case puts a recording `docker` on PATH ahead of any real one and compares the ARGV SEQUENCE both sides produced, not just their stdout. Two implementations can print identical text
while calling different commands, and for a teardown script the commands ARE the
behaviour: a port that printed "Force removing" and never ran `docker rm` would pass a stdout-only comparison and leave the container up.

ANTI-VACUITY. `test_the_fake_is_actually_reached` fails if the recording docker was never invoked at all. Without it every comparison below is "two programs that did nothing agree", which is the cleanest-looking green in this file.

THE ONE DELIBERATE DIVERGENCE IS TESTED, NOT HIDDEN.
`test_no_docker_diverges_and_that_is_the_point` asserts the twin's vacuous exit 0 and the port's exit 77 in the SAME case, so the difference is a recorded decision rather than a surprise the next reader has to rediscover. A port that quietly changed an exit code would otherwise look exactly like this one.
"""

import os
import pathlib
import shutil
import subprocess

import pytest

from rediacc_ci import paths

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "infra" / "ci-stop.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "infra" / "ci_stop.py"

# The recording `docker`. Written as Python, not bash: ruling 7 puts new instruments in Python, and an untracked fixture is not an excuse to write the one shape the ruling names.
#
# EVERY KNOB IS BAKED INTO ITS TEXT rather than passed through the environment. The first draft passed five (DOCKER_LOG, FIXTURE_ROOT, COMPOSE_RC, PS_NAMES, VERB_RC) and this comment used to justify the change by claiming they would red `check_env_manifest.py` once the file was tracked. THAT CLAIM WAS WRONG, and the check that refuted it is worth more than the change it was meant
# to justify: driven against `rediacc_ci.quality.env_manifest.names_from_py`, the old draft reads ZERO names, because those `os.environ` calls lived inside this very string literal and that reader PARSES rather than greps (env_manifest.py:34). Text inside a string is not a read, in either direction -- the same reason the plan's A6 triage found seventeen false findings that were all
# Python prose.
#
# So this is a simplification, not a fix: the fake is generated per case anyway, so its configuration belongs in its text, where a reader can see it without tracing an environment two processes deep. Recorded at length because the wrong reason is the kind a future author would re-derive and act on.
#
# ONE NEARBY FACT IS TRUE AND SEPARATE: `check_env_manifest.py`'s corpus is `git ls-files` with no `--others` (deliberately -- env_manifest.py:15), so a real `os.environ` read planted in THIS file fires nothing while the file is untracked. Verified by planting one. That is a property of the gate's corpus, not of this fixture, and it applies to every new file in the tree.
FAKE_DOCKER = """#!/usr/bin/env python3
import os, pathlib, sys
LOG = %(log)r
ROOT = %(root)r
COMPOSE_RC = %(compose_rc)d
PS_NAMES = %(ps_names)r
VERB_RC = %(verb_rc)d
with pathlib.Path(LOG).open("a", encoding="utf-8") as fh:
    fh.write("\\t".join([os.path.relpath(os.getcwd(), ROOT), *sys.argv[1:]]) + "\\n")
argv = sys.argv[1:]
if argv[:1] == ["compose"]:
    sys.exit(COMPOSE_RC)
if argv[:2] == ["ps", "-a"]:
    if PS_NAMES:
        sys.stdout.write("\\n".join(PS_NAMES) + "\\n")
    sys.exit(0)
sys.exit(VERB_RC)
"""


def _fixture(tmp_path: pathlib.Path, *, compose_dir: bool, backend_state: bool) -> pathlib.Path:
    """A tree shaped like the repository, holding COPIES of both subjects.

    Copies, because each subject derives the console root from its own location (`BASH_SOURCE`/`__file__` then three directories up). Driving the tracked files with a `cwd` would point them at the real repository and this test would delete the real `.backend-state`.
    """
    root = tmp_path / "tree"
    (root / ".ci" / "scripts" / "infra").mkdir(parents=True)
    shutil.copy2(TWIN, root / ".ci" / "scripts" / "infra" / TWIN.name)
    shutil.copy2(PORT, root / ".ci" / "scripts" / "infra" / PORT.name)
    if compose_dir:
        (root / ".ci" / "docker" / "ci").mkdir(parents=True)
        (root / ".ci" / "docker" / "ci" / "docker-compose.yml").write_text("{}\n", encoding="utf-8")
    if backend_state:
        (root / ".backend-state").write_text("running\n", encoding="utf-8")
    return root


def _bin_with_fake_docker(
    where: pathlib.Path,
    log: pathlib.Path,
    root: pathlib.Path,
    *,
    compose_rc: int,
    ps_names: list[str],
    verb_rc: int,
) -> pathlib.Path:
    """A directory holding one recording `docker`, configured by its own text."""
    binder = where
    binder.mkdir(parents=True, exist_ok=True)
    fake = binder / "docker"
    fake.write_text(
        FAKE_DOCKER
        % {
            "log": str(log),
            "root": str(root),
            "compose_rc": compose_rc,
            "ps_names": ps_names,
            "verb_rc": verb_rc,
        },
        encoding="utf-8",
    )
    fake.chmod(0o755)
    return binder


# The tools BOTH subjects need with docker taken away. Named rather than derived: a restricted PATH built by copying "everything except docker" is a PATH nobody can state, and the first tool it forgot would look like a divergence in the subject.
NEEDED = ("bash", "sh", "python3", "dirname", "grep", "rm", "cat", "env", "uname")


def _bin_without_docker(where: pathlib.Path) -> pathlib.Path:
    """A PATH that can run both subjects and CANNOT find docker.

    THE ASSERTION AT THE BOTTOM IS THE CONTROL. An earlier draft set PATH to an empty directory, which removed `bash` as well: the twin then failed to launch at all and the case "proved" a divergence that was really a missing shell.
    """
    binder = where / "nodocker-bin"
    binder.mkdir(exist_ok=True)
    for tool in NEEDED:
        target = shutil.which(tool)
        if target is None:
            continue
        link = binder / tool
        if not link.exists():
            link.symlink_to(target)
    assert shutil.which("docker", path=str(binder)) is None, (
        "the restricted bin still resolves docker; the divergence case would be vacuous"
    )
    assert shutil.which("bash", path=str(binder)), "the restricted bin cannot run the twin"
    assert shutil.which("python3", path=str(binder)), "the restricted bin cannot run the port"
    return binder


def _run(
    subject: pathlib.Path,
    root: pathlib.Path,
    *,
    docker: bool = True,
    compose_rc: int = 0,
    ps_names: tuple[str, ...] = (),
    verb_rc: int = 0,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Drive one subject against a freshly generated fake docker.

    THE BINDER IS PER-SUBJECT, not shared. Both sides of a differential run with the same knobs but must record into DIFFERENT logs, and the log path is baked into the fake, so one shared binder would have the two subjects appending to one file and the comparison would be of a list against itself.
    """
    log = root.parent / ("dockerlog-%s.txt" % subject.name)
    log.write_text("", encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # PATH is REPLACED, not prepended. On a host that has a real docker a prepend would still pass while occasionally talking to the machine's daemon.
    if docker:
        binder = _bin_with_fake_docker(
            root.parent / ("fxbin-%s" % subject.name),
            log,
            root,
            compose_rc=compose_rc,
            ps_names=list(ps_names),
            verb_rc=verb_rc,
        )
        env["PATH"] = "%s:%s" % (binder, env.get("PATH", ""))
    else:
        env["PATH"] = str(_bin_without_docker(root.parent))
    runner = ["bash"] if subject.suffix == ".sh" else ["python3"]
    proc = subprocess.run(
        [*runner, str(root / ".ci" / "scripts" / "infra" / subject.name)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
    )
    calls = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
    return proc, calls


SERVER = ("rediacc-account-server",)
CASES = [
    pytest.param(0, SERVER, 0, True, True, id="happy-container-present"),
    pytest.param(0, (), 0, True, True, id="container-absent"),
    pytest.param(1, SERVER, 0, True, True, id="compose-down-fails"),
    pytest.param(0, ("rediacc-account-server-2",), 0, True, True, id="near-miss-name-untouched"),
    pytest.param(0, SERVER, 1, True, False, id="stop-and-rm-fail"),
    pytest.param(0, SERVER, 0, False, True, id="no-compose-directory"),
]


@pytest.mark.parametrize(("compose_rc", "ps_names", "verb_rc", "compose_dir", "state"), CASES)
def test_port_and_twin_agree(tmp_path, compose_rc, ps_names, verb_rc, compose_dir, state):
    """Same fixture, both subjects: same exit, same stdout, same docker calls."""
    kw = {"compose_rc": compose_rc, "ps_names": ps_names, "verb_rc": verb_rc}

    root_a = _fixture(tmp_path / "a", compose_dir=compose_dir, backend_state=state)
    old, old_calls = _run(TWIN, root_a, **kw)
    old_state_gone = not (root_a / ".backend-state").exists()

    root_b = _fixture(tmp_path / "b", compose_dir=compose_dir, backend_state=state)
    new, new_calls = _run(PORT, root_b, **kw)
    new_state_gone = not (root_b / ".backend-state").exists()

    assert new.returncode == old.returncode, "exit code diverged: %r vs %r" % (
        old.returncode,
        new.returncode,
    )
    assert new.stdout == old.stdout, "stdout diverged:\n--- twin ---\n%s\n--- port ---\n%s" % (
        old.stdout,
        new.stdout,
    )
    assert new_calls == old_calls, "the docker CALLS diverged:\n twin: %s\n port: %s" % (
        old_calls,
        new_calls,
    )
    assert new_state_gone == old_state_gone, ".backend-state handling diverged"


def test_the_fake_is_actually_reached(tmp_path):
    """ANTI-VACUITY. Every comparison above is worthless if docker was never called."""
    root = _fixture(tmp_path / "v", compose_dir=True, backend_state=True)
    _, calls = _run(PORT, root, ps_names=("rediacc-account-server",))
    assert calls, "the recording docker was never invoked; this file proves nothing"
    verbs = [c.split("\t")[1] for c in calls]
    assert "compose" in verbs, "compose down was never attempted: %r" % verbs
    assert "rm" in verbs, "the container was never removed: %r" % verbs


def test_the_force_removal_is_conditional(tmp_path):
    """CONTROL for the case above: with no matching container, nothing is removed.

    A port that removed unconditionally would satisfy every positive assertion in
    this file and would `docker rm` a container that another job is using."""
    root = _fixture(tmp_path / "c", compose_dir=True, backend_state=True)
    _, calls = _run(PORT, root, ps_names=())
    verbs = [c.split("\t")[1] for c in calls]
    assert "rm" not in verbs, "removed a container that docker ps did not name: %r" % verbs


def test_compose_runs_in_the_compose_directory(tmp_path):
    """The twin wraps the call in `(cd "$CI_DOCKER_DIR" && ...)`. Losing that runs
    compose against whatever the caller's cwd happened to be, which in CI is the
    repository root and a completely different stack."""
    root = _fixture(tmp_path / "d", compose_dir=True, backend_state=False)
    _, calls = _run(PORT, root)
    compose = [c for c in calls if c.split("\t")[1] == "compose"]
    assert compose, "compose was never called"
    assert compose[0].split("\t")[0] == ".ci/docker/ci", (
        "compose ran in %r, not the compose directory" % compose[0].split("\t")[0]
    )


def test_no_docker_diverges_and_that_is_the_point(tmp_path):
    """THE ONE DELIBERATE DIVERGENCE, asserted in BOTH directions.

    With no `docker` on PATH the twin prints its whole transcript, removes nothing, and exits 0 -- a teardown that reports success having torn nothing down. The port answers 77 (CANNOT RUN) and names the fix. This test exists so that the difference is a decision on the record: if either half ever changes, it reds here rather than in a CI job that quietly stopped cleaning up.
    """
    root_a = _fixture(tmp_path / "e", compose_dir=True, backend_state=True)
    old, _ = _run(TWIN, root_a, docker=False)
    root_b = _fixture(tmp_path / "f", compose_dir=True, backend_state=True)
    new, _ = _run(PORT, root_b, docker=False)

    assert old.returncode == 0, "the twin's vacuous success is the premise; it exited %d" % (
        old.returncode
    )
    assert "All services stopped" in old.stdout, "the twin claims success: %r" % old.stdout
    assert new.returncode == 77, "the port must refuse, not agree; it exited %d" % new.returncode
    assert "CANNOT RUN" in new.stderr, "and it must say so on stderr: %r" % new.stderr
    assert "docker is not on PATH" in new.stderr, "naming the cause: %r" % new.stderr
