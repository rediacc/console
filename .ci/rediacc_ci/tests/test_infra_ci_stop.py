"""`rediacc_ci.infra.ci_stop`, driven against the bytes and the docker calls its bash twin produced.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/infra/ci-stop.sh` and the port over the same throwaway tree and compared four things: the exit code, stdout, the recording docker's ARGV SEQUENCE and whether `.backend-state` survived. The K=5 ledger `.ci/shadow/w7p6-ci-stop.observations.jsonl` recorded that comparison over five distinct trees. The twin has now been
deleted and every case that executed it compares against `goldens/ci-stop/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree. Each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

THE CALL LOG IS THE EVIDENCE, and it is recorded beside the streams rather than instead of them. Two implementations can print identical text while calling different commands, and for a teardown script the commands ARE the behaviour: a port that printed "Force removing" and never ran `docker rm` would pass a stdout-only comparison and leave the container up. Each recorded
line is the fake's working directory relative to the fixture root, then argv, so the `(cd "$CI_DOCKER_DIR" && ...)` wrapper is visible in the recording too.

HOW DOCKER IS FAKED, AND WHY IT IS A FAKE RATHER THAN A MOCK. The subject shells out to `docker`, so the seam that matters is PATH. Each case puts a recording `docker` on PATH, and PATH is REPLACED rather than prepended, so a host with a real docker cannot occasionally talk to its own daemon.

THE ONE DELIBERATE DIVERGENCE IS RECORDED, NOT HIDDEN. With no `docker` on PATH the twin printed its whole transcript, removed nothing, and exited 0: a teardown that reported success having torn nothing down. The port answers 77 (CANNOT RUN) and names the fix. `no-docker` is recorded from the twin exactly as it behaved, and `test_no_docker_diverges_and_that_is_the_point`
asserts both halves so the difference stays a decision on the record.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
PORT = ROOT / ".ci" / "rediacc_ci" / "infra" / "ci_stop.py"

SLUG = "ci-stop"

CALLS_MARKER = "--- calls ---\n"
STATE_MARKER = "--- backend-state ---\n"

# The recording `docker`. Written as Python, not bash: ruling 7 puts new instruments in Python, and an untracked fixture is not an excuse to write the one shape the ruling names.
#
# EVERY KNOB IS BAKED INTO ITS TEXT rather than passed through the environment. The first draft passed five (DOCKER_LOG, FIXTURE_ROOT, COMPOSE_RC, PS_NAMES, VERB_RC) and this comment used to justify the change by claiming they would red `check_env_manifest.py` once the file was tracked. THAT CLAIM WAS WRONG, and the check that refuted it is worth more than the change it was meant
# to justify: driven against `rediacc_ci.quality.env_manifest.names_from_py`, the old draft reads ZERO names, because those `os.environ` calls lived inside this very string literal and that reader PARSES rather than greps (env_manifest.py:34). Text inside a string is not a read, in either direction -- the same reason the plan's A6 triage found seventeen false findings that were all
# Python prose.
#
# So this is a simplification, not a fix: the fake is generated per case anyway, so its configuration belongs in its text, where a reader can see it without tracing an environment two processes deep. Recorded at length because the wrong reason is the kind a future author would re-derive and act on.
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

SERVER = ("rediacc-account-server",)

# name -> the knobs the recording was taken under.
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "happy-container-present": {"ps_names": SERVER},
    "container-absent": {"ps_names": ()},
    "compose-down-fails": {"ps_names": SERVER, "compose_rc": 1},
    "near-miss-name-untouched": {"ps_names": ("rediacc-account-server-2",)},
    "stop-and-rm-fail": {"ps_names": SERVER, "verb_rc": 1, "backend_state": False},
    "no-compose-directory": {"ps_names": SERVER, "compose_dir": False},
    "no-docker": {"docker": False},
}

CASES = tuple(CASE_KW)

# The one case the port does not reproduce, on purpose. Compared by shape, in its own test.
DIVERGENT = "no-docker"

# The tools the port needs with docker taken away. Named rather than derived: a restricted PATH built by copying "everything except docker" is a PATH nobody can state, and the first tool it forgot would look like a divergence in the subject.
NEEDED = ("bash", "sh", "python3", "dirname", "grep", "rm", "cat", "env", "uname")


def fixture(
    where: pathlib.Path, *, compose_dir: bool = True, backend_state: bool = True
) -> pathlib.Path:
    """A tree shaped like the repository, holding a COPY of the subject.

    A copy, because the subject derives the console root from its own location (`__file__` then three directories up). Driving the tracked file with a `cwd` would point it at the real repository and this test would delete the real `.backend-state`.
    """
    root = where / "tree"
    (root / ".ci" / "scripts" / "infra").mkdir(parents=True)
    shutil.copy2(PORT, root / ".ci" / "scripts" / "infra" / PORT.name)
    if compose_dir:
        (root / ".ci" / "docker" / "ci").mkdir(parents=True)
        (root / ".ci" / "docker" / "ci" / "docker-compose.yml").write_text("{}\n", encoding="utf-8")
    if backend_state:
        (root / ".backend-state").write_text("running\n", encoding="utf-8")
    return root


def bin_with_fake_docker(
    binder: pathlib.Path,
    log: pathlib.Path,
    root: pathlib.Path,
    *,
    compose_rc: int,
    ps_names: tuple[str, ...],
    verb_rc: int,
) -> pathlib.Path:
    """A directory holding one recording `docker`, configured by its own text."""
    binder.mkdir(parents=True, exist_ok=True)
    fake = binder / "docker"
    fake.write_text(
        FAKE_DOCKER
        % {
            "log": str(log),
            "root": str(root),
            "compose_rc": compose_rc,
            "ps_names": list(ps_names),
            "verb_rc": verb_rc,
        },
        encoding="utf-8",
    )
    fake.chmod(0o755)
    return binder


def bin_without_docker(where: pathlib.Path) -> pathlib.Path:
    """A PATH that can run the subject and CANNOT find docker.

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
    assert shutil.which("bash", path=str(binder)), "the restricted bin cannot run a shell"
    assert shutil.which("python3", path=str(binder)), "the restricted bin cannot run the port"
    return binder


def run(
    where: pathlib.Path,
    subject: pathlib.Path,
    *,
    docker: bool = True,
    compose_rc: int = 0,
    ps_names: tuple[str, ...] = (),
    verb_rc: int = 0,
    compose_dir: bool = True,
    backend_state: bool = True,
) -> tuple[int, str, str, str, str]:
    """Drive one subject against a freshly generated fake docker.

    THE BINDER IS PER-RUN, not shared: the log path is baked into the fake, so one shared binder would have two subjects appending to one file and the comparison would be of a list against itself.
    """
    where.mkdir(parents=True, exist_ok=True)
    root = fixture(where, compose_dir=compose_dir, backend_state=backend_state)
    target = root / ".ci" / "scripts" / "infra" / subject.name
    if subject != PORT:
        shutil.copy2(subject, target)
    log = where / "dockerlog.txt"
    log.write_text("", encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if docker:
        binder = bin_with_fake_docker(
            where / "fxbin",
            log,
            root,
            compose_rc=compose_rc,
            ps_names=ps_names,
            verb_rc=verb_rc,
        )
        env["PATH"] = str(binder)
        for tool in NEEDED:
            found = shutil.which(tool)
            if found and not (binder / tool).exists():
                (binder / tool).symlink_to(found)
    else:
        env["PATH"] = str(bin_without_docker(where))
    runner = "bash" if subject.suffix == ".sh" else "python3"
    # `cwd` IS PINNED TO THE FIXTURE ROOT, and it is the one thing freezing had to add. Neither subject reads its cwd -- both derive the console root from their own location -- but the recording `docker` logs its working directory RELATIVE to that root, so a run started from a deeper temporary directory writes `../../..` where a shallower one writes `../..`. While both
    # implementations ran in the same second from the same cwd that cancelled out; a recording compared against a tree built months later under a different tempdir does not.
    proc = subprocess.run(
        [runner, str(target)],
        cwd=str(root),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
    )
    calls = log.read_text(encoding="utf-8")
    state = "present" if (root / ".backend-state").exists() else "removed"
    return proc.returncode, proc.stdout, proc.stderr, calls, state


def render(returncode: int, stdout: str, stderr: str, calls: str, state: str) -> str:
    body = frozen.render(returncode, stdout, stderr)
    return body + CALLS_MARKER + calls + STATE_MARKER + state + "\n"


def recorded(name: str) -> tuple[int, str, str, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    streams, tail = rest.split(CALLS_MARKER, 1)
    stdout, stderr = streams.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    calls, state = tail.split(STATE_MARKER, 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, calls, state.rstrip("\n")


def drive(tmp_path: pathlib.Path, name: str, *, subject: pathlib.Path = PORT):
    return run(tmp_path / name, subject, **CASE_KW[name])


def compare(tmp_path: pathlib.Path, name: str) -> None:
    want = recorded(name)
    got = drive(tmp_path, name)
    assert got[0] == want[0], "%s: the twin exited %d, the port %d" % (name, want[0], got[0])
    assert got[1] == want[1], "%s: stdout diverged from the recorded bytes" % name
    assert got[2] == want[2], "%s: stderr diverged from the recorded bytes" % name
    assert got[3] == want[3], "%s: the docker calls diverged from the recording" % name
    assert got[4] == want[4], "%s: .backend-state handling diverged" % name


@pytest.mark.parametrize("name", [c for c in CASES if c != DIVERGENT])
def test_port_matches_the_twins_recorded_behaviour(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_the_fake_was_actually_reached() -> None:
    """ANTI-VACUITY on the recordings. Every comparison above is worthless if docker was never called.

    Read out of the RECORDING rather than re-run, because it is the twin's call sequence that the comparisons are against.
    """
    calls = recorded("happy-container-present")[3]
    assert calls, "the recording docker was never invoked; this file proves nothing"
    verbs = [line.split("\t")[1] for line in calls.splitlines() if line]
    assert "compose" in verbs, "compose down was never attempted: %r" % verbs
    assert "rm" in verbs, "the container was never removed: %r" % verbs


def test_the_force_removal_is_conditional() -> None:
    """CONTROL for the case above: with no matching container, nothing is removed.

    A port that removed unconditionally would satisfy every positive assertion in this file and would `docker rm` a container another job is using.
    """
    calls = recorded("container-absent")[3]
    verbs = [line.split("\t")[1] for line in calls.splitlines() if line]
    assert "rm" not in verbs, "removed a container that docker ps did not name: %r" % verbs


def test_a_near_miss_name_is_left_alone() -> None:
    """`^<name>$` against `--format '{{.Names}}'`, so `rediacc-account-server-2` is a different container."""
    calls = recorded("near-miss-name-untouched")[3]
    verbs = [line.split("\t")[1] for line in calls.splitlines() if line]
    assert "rm" not in verbs, "a near-miss name was removed: %r" % verbs


def test_compose_ran_in_the_compose_directory() -> None:
    """The twin wrapped the call in `(cd "$CI_DOCKER_DIR" && ...)`. Losing that runs compose against whatever the caller's cwd happened to be, which in CI is the repository root and a completely different stack."""
    calls = recorded("happy-container-present")[3]
    compose = [line for line in calls.splitlines() if line.split("\t")[1:2] == ["compose"]]
    assert compose, "compose was never called"
    assert compose[0].split("\t")[0] == ".ci/docker/ci", (
        "compose ran in %r, not the compose directory" % compose[0].split("\t")[0]
    )


def test_a_failing_compose_down_is_not_fatal() -> None:
    """`|| { echo ...; }` in the twin, and then the force-removal loop runs anyway."""
    returncode, _, _, calls, _ = recorded("compose-down-fails")
    assert returncode == 0
    verbs = [line.split("\t")[1] for line in calls.splitlines() if line]
    assert "rm" in verbs, "a failed compose down skipped the force removal: %r" % verbs


def test_stop_and_rm_both_run_even_when_the_first_fails() -> None:
    """`2>/dev/null || true` on each, so a failing `docker stop` must not skip `docker rm`."""
    returncode, _, _, calls, _ = recorded("stop-and-rm-fail")
    assert returncode == 0
    verbs = [line.split("\t")[1] for line in calls.splitlines() if line]
    assert verbs.count("stop") == 1
    assert verbs.count("rm") == 1


def test_no_docker_diverges_and_that_is_the_point(tmp_path: pathlib.Path) -> None:
    """THE ONE DELIBERATE DIVERGENCE, asserted in BOTH directions.

    With no `docker` on PATH the twin printed its whole transcript, removed nothing, and exited 0 -- a teardown that reported success having torn nothing down. The port answers 77 (CANNOT RUN) and names the fix. This test exists so that the difference is a decision on the record: if either half ever changes, it reds here rather than in a CI job that quietly stopped cleaning up.
    """
    want_exit, want_out, _, want_calls, _ = recorded(DIVERGENT)
    assert want_exit == 0, "the twin's vacuous success is the premise; it exited %d" % want_exit
    assert "All services stopped" in want_out, "the twin claimed success: %r" % want_out
    assert want_calls == "", "the twin called docker after all: %r" % want_calls

    returncode, _, stderr, _, _ = drive(tmp_path, DIVERGENT)
    assert returncode == 77, "the port must refuse, not agree; it exited %d" % returncode
    assert "CANNOT RUN" in stderr, "and it must say so on stderr: %r" % stderr
    assert "docker is not on PATH" in stderr, "naming the cause: %r" % stderr


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_unconditional_removal_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Remove the container whether or not `docker ps -a` named it.

    The recorded `container-absent` call log holds no `rm`, and a mutant that removes unconditionally reaches a container another job may be using. Every stdout line it prints is one the twin also printed in the container-PRESENT case, so the call log is the only witness. The mutation runs from a throwaway copy of the module file; the tracked port is never touched.
    """
    with open(PORT, encoding="utf-8") as fh:
        original = fh.read()
    anchor = "        if container in known:\n"
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(anchor, "        if True:\n")

    mutant_dir = tmp_path / "mutant"
    mutant_dir.mkdir(parents=True, exist_ok=True)
    mutant = mutant_dir / "ci_stop.py"
    mutant.write_text(mutated, encoding="utf-8")

    name = "container-absent"
    _, _, _, calls, _ = run(tmp_path / "planted", mutant, **CASE_KW[name])
    verbs = [line.split("\t")[1] for line in calls.splitlines() if line]
    assert "rm" in verbs, "the plant did not change the calls"
    assert recorded(name)[3].count("\trm\t") == 0, "the recorded corpus moved"

    compare(tmp_path / "good", name)
    with open(PORT, encoding="utf-8") as fh:
        assert fh.read() == original
