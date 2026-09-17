"""Differential: `rediacc_ci.infra.docker_prepull` against its twin `.ci/scripts/infra/docker-prepull.sh`.

A RECORDING FAKE `docker` ON A PREPENDED PATH, and it is not a convenience: the subject's entire job is `docker pull`, so a case that reached the real binary would pull whatever ref the argument named, over the network, into the developer's daemon -- and the retry cases would then take 90 seconds each while doing it. Three independent things keep the real one out of reach:

  1. the stub directory is FIRST on PATH and `shutil.which("docker", path=...)`
     is asserted to resolve to the fake, in `test_the_fake_docker_is_the_docker`
     -- a control that fires if the ordering ever stops working;
  2. every case names a ref that cannot exist
     (`registry.invalid/rediacc/base:fixture`), so a leaked real docker fails
     to resolve it rather than downloading anything;
  3. `DOCKER_HOST` points at a socket that does not exist, so a leaked real
     docker cannot reach any daemon either. It is a FIXED path rather than one
     under the case's temp directory, because docker's own refusal quotes the
     socket path and the two sides' temp directories legitimately differ --
     that difference would then show up as a divergence in the thing under
     test rather than in the fixture.

`sleep` IS FAKED THE SAME WAY, AND THAT IS WHAT MAKES THE RETRY CASES CHEAP. Both implementations resolve `sleep` through PATH -- the port execs it rather than calling `time.sleep`, for exactly this reason -- so one stub nulls the 30s+60s backoff on BOTH sides and the full three-attempt path costs milliseconds. The stub still RECORDS the durations it was asked for, into the same
log as the pulls, so the schedule and the interleaving are compared rather than merely skipped.

THE CALL LOG IS THE PRIMARY ARTIFACT. Which argv reached docker, in which order, with the sleeps interleaved, is invisible in stdout: a port that pulled
with the wrong `--platform`, or retried twice instead of three times, or slept
before the first attempt, prints the same lines as one that did not. Every case compares the log.

ONE NAMED DIVERGENCE, and it is the only one in this file: the no-arguments usage line interpolates `$0`, which is the path the caller typed, so the twin names the `.sh` and the port names the `.py`. `test_no_arguments_is_refused_with_the_usage_line` asserts everything else about that case byte for byte and asserts the two usage lines differ ONLY in that path, rather than papering
over it.

K=5 LEDGER: `.ci/shadow/w7p6-docker-prepull.observations.jsonl`, recorded in a
disposable scratch git repository outside this checkout.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.infra import docker_prepull as dp

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "infra" / "docker-prepull.sh"
# FROM THE MODULE, not spelled out. This port shares its BASENAME with `rediacc_ci.proxies.docker_prepull`, and `check:ci-dead-python`'s `mentioned` route matches by basename on purpose ("a bare basename admits every corpus file with that name"), so writing the literal here admits that OTHER file and its `MANUAL_ENTRY_POINTS` exemption is then reported as no longer true. Measured:
# the literal reddened that gate with one extra finding.
PORT = pathlib.Path(dp.__file__).resolve()
BASH = shutil.which("bash") or "/bin/bash"

# A ref no registry can serve, so a leaked real docker fails rather than pulls.
REF = "registry.invalid/rediacc/base:fixture"

# A socket that does not exist, identical on both sides. See the module docstring.
NOWHERE_DAEMON = "unix:///nonexistent/rediacc-docker-prepull-fixture.sock"

# What the twin needs on PATH before `require_cmd docker` can speak: `dirname`
# for its own SCRIPT_DIR, and `uname` because common.sh calls detect_os and
# detect_arch at SOURCE time (common.sh:64, :100). Measured by running the case without them and reading the two `uname: command not found` lines bash printed -- a curated PATH that is missing one of these makes the twin noisy in a way that has nothing to do with the subject.
CURATED = ("dirname", "uname")

FAKE_DOCKER = """#!/usr/bin/python3
import os
import sys

argv = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write("docker\\t" + "\\t".join(argv) + "\\n")
sys.stdout.write(os.environ.get("FAKE_DOCKER_STDOUT", ""))
needle = os.environ.get("FAKE_DOCKER_FAIL_ON", "")
if needle and needle in argv:
    sys.stderr.write("Error response from daemon: fixture refuses %s\\n" % needle)
    sys.exit(1)
sys.exit(int(os.environ.get("FAKE_DOCKER_RC", "0")))
"""

# Records what it was asked to wait for and returns immediately.
FAKE_SLEEP = """#!/usr/bin/python3
import os
import sys

with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write("sleep\\t" + "\\t".join(sys.argv[1:]) + "\\n")
sys.exit(0)
"""


def _stub_bin(base: pathlib.Path, *, with_docker: bool = True) -> str:
    """A directory holding the fakes, prepended to the real PATH.

    PREPENDED rather than curated down to a symlink farm: the twin sources `common.sh`, which reaches for `dirname` at source time, and `mktemp`, `tr` and `uname` live behind other helpers there. The safety property is therefore RESOLUTION ORDER, and it is asserted rather than assumed.

    `with_docker=False` IS THE ONE CASE THAT CANNOT PREPEND, because the real
    PATH holds a real docker on any host that can build anything here. That case gets a CURATED path instead: the stub directory plus a symlink to `dirname`, which is the only external the twin needs before `require_cmd` speaks.
    """
    stub = base / "bin"
    stub.mkdir(exist_ok=True)
    if with_docker:
        fake = stub / "docker"
        fake.write_text(FAKE_DOCKER, encoding="utf-8")
        fake.chmod(0o755)
    nap = stub / "sleep"
    nap.write_text(FAKE_SLEEP, encoding="utf-8")
    nap.chmod(0o755)
    if not with_docker:
        for name in CURATED:
            real = shutil.which(name)
            assert real is not None, "no %s on PATH; the twin cannot even source common.sh" % name
            (stub / name).symlink_to(real)
        return str(stub)
    return "%s:%s" % (stub, os.environ.get("PATH", "/usr/bin:/bin"))


def _run(subject: pathlib.Path, base: pathlib.Path, argv: list[str], extra: dict[str, str]):
    log = base / "calls.log"
    log.write_text("", encoding="utf-8")
    env = {
        "PATH": _stub_bin(base, with_docker=extra.pop("_no_docker", "") != "1"),
        "HOME": str(base),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_LOG": str(log),
        # A leaked real docker has no daemon to talk to. Fixed, not per-case: see the module docstring.
        "DOCKER_HOST": NOWHERE_DAEMON,
    }
    env.update(extra)
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject), *argv],
        capture_output=True,
        env=env,
        check=False,
        cwd=str(base),
        timeout=120,
    )
    calls = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
    return proc.returncode, proc.stdout, proc.stderr, calls


def _sides(name: str, argv: list[str], **extra: str):
    """Both subjects, one fixture shape, two private trees."""
    results = []
    with tempfile.TemporaryDirectory() as td:
        for subject in (TWIN, PORT):
            base = pathlib.Path(td) / subject.stem
            base.mkdir(parents=True)
            results.append(_run(subject, base, argv, dict(extra)))
    old, new = results
    for i, label in enumerate(("exit", "stdout", "stderr", "calls")):
        assert new[i] == old[i], "%s: %s diverged:\n twin: %r\n port: %r" % (
            name,
            label,
            old[i],
            new[i],
        )
    return old


# --------------------------------------------------------------------------- The controls, first: a fake that is not reached proves nothing. ---------------------------------------------------------------------------


def test_the_fake_docker_is_the_docker() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        path = _stub_bin(base)
        assert shutil.which("docker", path=path) == str(base / "bin" / "docker")
        assert shutil.which("sleep", path=path) == str(base / "bin" / "sleep")


def test_both_subjects_exist_where_this_file_says_they_do() -> None:
    assert TWIN.is_file(), TWIN
    assert PORT.is_file(), PORT


def test_the_twin_parses_under_bash() -> None:
    proc = subprocess.run([BASH, "-n", str(TWIN)], capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr


# --------------------------------------------------------------------------- The grammar, driven against bash's own parameter expansion. ---------------------------------------------------------------------------


def _bash_split(spec: str) -> tuple[str, str]:
    """`${spec%%=*}` and the guarded `${spec#*=}`, run by the real bash."""
    script = (
        'spec="$1"; image="${spec%%=*}"; platform=""; '
        '[[ "$spec" == *=* ]] && platform="${spec#*=}"; '
        'printf \'%s\\n%s\\n\' "$image" "$platform"'
    )
    out = subprocess.run(
        [BASH, "-c", script, "bash", spec],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split("\n")
    return out[0], out[1]


def test_split_spec_agrees_with_bash_on_every_shape() -> None:
    for spec in (
        "ubuntu:24.04",
        "ubuntu:24.04=linux/amd64",
        "ghcr.io/rediacc/base:1.2=linux/arm64",
        "a=b=c",
        "trailing=",
        "=linux/amd64",
        "",
        "no-tag",
        "weird==",
    ):
        assert dp.split_spec(spec) == _bash_split(spec), spec


def test_pull_argv_omits_the_platform_flag_when_there_is_none() -> None:
    assert dp.pull_argv("x", "") == ["docker", "pull", "x"]
    assert dp.pull_argv("x", "linux/amd64") == [
        "docker",
        "pull",
        "--platform",
        "linux/amd64",
        "x",
    ]


# --------------------------------------------------------------------------- The differential. ---------------------------------------------------------------------------


def test_no_arguments_is_refused_with_the_usage_line() -> None:
    """THE ONE NAMED DIVERGENCE. `$0` is the path the caller typed, so the two sides legitimately name different files; everything else must match."""
    results = []
    with tempfile.TemporaryDirectory() as td:
        for subject in (TWIN, PORT):
            base = pathlib.Path(td) / subject.stem
            base.mkdir(parents=True)
            results.append(_run(subject, base, [], {}))
    old, new = results
    assert old[0] == new[0] == 1
    assert old[1] == new[1] == b""
    assert old[3] == new[3] == [], "docker was called on the no-arguments path"

    old_lines = old[2].decode().splitlines()
    new_lines = new[2].decode().splitlines()
    assert old_lines[0] == new_lines[0] == "✗ No images given."
    assert old_lines[1].endswith(" <ref>[=<platform>] ...   e.g. ubuntu:24.04=linux/amd64")
    assert new_lines[1].endswith(" <ref>[=<platform>] ...   e.g. ubuntu:24.04=linux/amd64")
    assert str(TWIN) in old_lines[1] or "docker-prepull.sh" in old_lines[1]
    assert PORT.name in new_lines[1]
    # `✗ Usage: <path> <rest...>`: drop the three leading tokens and the remainder must be identical, so the path is the ONLY thing that differs.
    assert old_lines[1].split(" ", 3)[:2] == new_lines[1].split(" ", 3)[:2] == ["✗", "Usage:"]
    assert old_lines[1].split(" ", 3)[3] == new_lines[1].split(" ", 3)[3]
    assert len(old_lines) == len(new_lines) == 2


def test_a_missing_docker_is_refused_before_anything_is_pulled() -> None:
    """`require_cmd docker`, and its message is common.sh's, word for word."""
    exit_code, stdout, stderr, calls = _sides("no-docker", [REF], _no_docker="1")
    assert exit_code == 1
    assert stdout == b""
    assert calls == [], "a pull was attempted with no docker on PATH"
    assert stderr == b"\xe2\x9c\x97 Required command 'docker' is not available\n"


def test_a_bare_ref_pulls_once_with_no_platform_flag() -> None:
    exit_code, stdout, stderr, calls = _sides("bare", [REF])
    assert exit_code == 0
    assert calls == ["docker\tpull\t%s" % REF]
    assert b"Pre-pulled 1 base image(s)" in stderr
    assert stdout == b""


def test_the_ref_equals_platform_form_passes_platform_through() -> None:
    exit_code, _, stderr, calls = _sides("platform", ["%s=linux/amd64" % REF])
    assert exit_code == 0
    assert calls == ["docker\tpull\t--platform\tlinux/amd64\t%s" % REF]
    assert b"Pre-pulled 1 base image(s)" in stderr


def test_a_trailing_equals_is_a_bare_ref() -> None:
    """`*=*` matches, so platform is set to "" -- and `[[ -n ]]` then drops it."""
    exit_code, _, _, calls = _sides("trailing-equals", ["%s=" % REF])
    assert exit_code == 0
    assert calls == ["docker\tpull\t%s" % REF], "an empty --platform was passed"


def test_a_second_equals_belongs_to_the_platform() -> None:
    exit_code, _, _, calls = _sides("double-equals", ["%s=a=b" % REF])
    assert exit_code == 0
    assert calls == ["docker\tpull\t--platform\ta=b\t%s" % REF]


def test_docker_stdout_reaches_the_caller_unbuffered_and_unwrapped() -> None:
    """The pull's own output is INHERITED; neither side captures or re-emits."""
    exit_code, stdout, _, _ = _sides(
        "passthrough", [REF], FAKE_DOCKER_STDOUT="Status: Downloaded newer image\n"
    )
    assert exit_code == 0
    assert stdout == b"Status: Downloaded newer image\n"


def test_a_failing_pull_is_three_attempts_with_thirty_then_sixty_seconds() -> None:
    """The retry schedule, and the interleaving, both compared.

    Cheap only because `sleep` is a PATH stub on both sides; the twin would otherwise spend 90 seconds here and so would the port.
    """
    exit_code, _, stderr, calls = _sides("retry", [REF], FAKE_DOCKER_RC="1")
    assert exit_code == 1
    assert calls == [
        "docker\tpull\t%s" % REF,
        "sleep\t30",
        "docker\tpull\t%s" % REF,
        "sleep\t60",
        "docker\tpull\t%s" % REF,
    ], calls
    text = stderr.decode()
    assert text.count("retrying in") == 2
    assert "Pull failed for %s <default>, retrying in 30s..." % REF in text
    assert "Pull failed for %s <default>, retrying in 60s..." % REF in text
    assert "Failed to pull %s <default> after 3 attempts" % REF in text
    assert "One or more base images could not be pulled" in text
    assert "Pre-pulled" not in text


def test_the_retry_message_names_the_platform_when_there_is_one() -> None:
    _, _, stderr, _ = _sides("retry-platform", ["%s=linux/arm64" % REF], FAKE_DOCKER_RC="1")
    text = stderr.decode()
    assert "Pull failed for %s linux/arm64, retrying in 30s..." % REF in text
    assert "Failed to pull %s linux/arm64 after 3 attempts" % REF in text
    assert "<default>" not in text


def test_one_bad_spec_does_not_stop_the_others_from_being_attempted() -> None:
    """`|| failed=1` rather than `set -e`: every spec is tried, and the run
    still ends non-zero. A port that gave up on the first failure would leave the later bases unpulled and the build would fail where it always did."""
    good = "%s-ok" % REF
    exit_code, _, stderr, calls = _sides("one-bad", [REF, good], FAKE_DOCKER_FAIL_ON=REF)
    assert exit_code == 1
    assert calls == [
        "docker\tpull\t%s" % REF,
        "sleep\t30",
        "docker\tpull\t%s" % REF,
        "sleep\t60",
        "docker\tpull\t%s" % REF,
        "docker\tpull\t%s" % good,
    ], calls
    assert b"One or more base images could not be pulled" in stderr


def test_the_count_is_the_argument_count_not_the_image_count() -> None:
    """PRESERVED WART. `$#` counts arguments, so the same ref twice reads as 2. If this ever starts counting pulls, this test goes red first."""
    exit_code, _, stderr, calls = _sides("dupes", [REF, REF])
    assert exit_code == 0
    assert calls == ["docker\tpull\t%s" % REF] * 2
    assert b"Pre-pulled 2 base image(s)" in stderr


def test_an_empty_ref_reaches_docker_as_an_empty_argument() -> None:
    """PRESERVED SHAPE. `=linux/amd64` has no ref; the twin validates nothing
    beyond the split, so docker is handed "" and refuses it three times."""
    exit_code, _, _, calls = _sides("empty-ref", ["=linux/amd64"], FAKE_DOCKER_RC="1")
    assert exit_code == 1
    assert calls[0] == "docker\tpull\t--platform\tlinux/amd64\t"


def test_the_success_line_counts_a_mixed_batch() -> None:
    exit_code, _, stderr, calls = _sides("mixed", [REF, "%s=linux/amd64" % REF, "%s-b" % REF])
    assert exit_code == 0
    assert len(calls) == 3
    assert b"Pre-pulled 3 base image(s)" in stderr
