"""`rediacc_ci.infra.docker_prepull`, driven against the bytes its bash twin printed.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/infra/docker-prepull.sh` and the port over one stubbed PATH and compared exit code, stdout, stderr and the docker CALL LOG. The ledger `.ci/shadow/w7p6-docker-prepull.observations.jsonl` holds 5 rows of that comparison, recorded in a disposable scratch git repository outside this checkout.

Every case now compares against `goldens/docker-prepull/`, which holds the twin's OWN recorded bytes, captured on its last day in the tree, and each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

ONE MORE PIECE OF EVIDENCE EXISTS FOR THIS PORT THAN FOR MOST, and it was taken before the twin went: `.ci/scripts/test/proxies/proxy-docker-prepull.sh` drives the subject against a REAL docker daemon and a real registry, and its own differential compares the bash proxy with the ported proxy byte for byte. Flipping only the ported proxy to this port, while the bash proxy still ran
the bash subject, left that comparison byte-identical over four live pulls. That is a live-daemon check no fixture here can make, and it says the port and the twin agreed where it actually counts.

A RECORDING FAKE `docker` ON A PREPENDED PATH, and it is not a convenience: the subject's entire job is `docker pull`, so a case that reached the real binary would pull whatever ref the argument named, over the network, into the developer's daemon, and the retry cases would then take 90 seconds each while doing it. Three independent things keep the real one out of reach:

  1. the stub directory is FIRST on PATH and `shutil.which("docker", path=...)`
     is asserted to resolve to the fake, in `test_the_fake_docker_is_the_docker`,
     a control that fires if the ordering ever stops working;
  2. every case names a ref that cannot exist
     (`registry.invalid/rediacc/base:fixture`), so a leaked real docker fails to
     resolve it rather than downloading anything;
  3. `DOCKER_HOST` points at a socket that does not exist, so a leaked real
     docker cannot reach any daemon either. It is a FIXED path rather than one
     under the case's temporary directory, because docker's own refusal quotes
     the socket path and a per-case path would then appear in a recording.

`sleep` IS FAKED THE SAME WAY, AND THAT IS WHAT MAKES THE RETRY CASES CHEAP. The port execs `sleep` rather than calling `time.sleep`, for exactly this reason, so one stub nulls the 30s and 60s backoff and the full three-attempt path costs milliseconds. The stub still RECORDS the durations it was asked for, into the same log as the pulls, so the schedule and the interleaving are
compared rather than skipped.

THE CALL LOG IS THE PRIMARY ARTIFACT, and it is carried in the recorded shape as its own `--- docker calls ---` section. Which argv reached docker, in which order, with the sleeps interleaved, is invisible in stdout: a port that pulled with the wrong `--platform`, or retried twice instead of three times, or slept before the first attempt, prints the same lines as one that did not.
The control at the foot of this file plants exactly the first of those.

ONE CASE IS COMPARED BY SHAPE, and it is the only one: the no-arguments usage line interpolates `$0`, which is the path the caller typed, so the twin named the `.sh` and the port names the `.py`. Everything else about that case is compared byte for byte, and the two usage lines are asserted to differ ONLY in that path rather than papered over.

WHAT IS MASKED, and it is two paths. The case's own directory is its `HOME` and its working directory and is rebuilt under a different name every run, so it becomes `<case>`; the checkout root becomes `<repo>`, because the divergent usage line names the subject's own absolute path. Nothing else is touched.

THE CONTROL IS A WRAPPER PLANT that imports the tracked module and replaces one exported function in its own process. A copy of the file would also run here, since this module resolves no sibling from its own location, but replacing `pull_argv` mutates exactly the argv the recording is about and leaves the file on disk untouched.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.infra import docker_prepull as dp
from rediacc_ci.tests import frozen

ROOT = paths.repo_root()
# FROM THE MODULE, not spelled out. This port shares its BASENAME with `rediacc_ci.proxies.docker_prepull`, and `check:ci-dead-python`'s `mentioned` route matches by basename on purpose ("a bare basename admits every corpus file with that name"), so writing the literal here admits that OTHER file and its `MANUAL_ENTRY_POINTS` exemption is then reported as no longer true. Measured:
# the literal reddened that gate with one extra finding.
PORT = pathlib.Path(dp.__file__).resolve()
BASH = shutil.which("bash") or "/bin/bash"
PYTHON = sys.executable

SLUG = "docker-prepull"
CALLS_MARKER = "--- docker calls ---\n"

# A ref no registry can serve, so a leaked real docker fails rather than pulls.
REF = "registry.invalid/rediacc/base:fixture"

# A socket that does not exist, identical in every case. See the module docstring.
NOWHERE_DAEMON = "unix:///nonexistent/rediacc-docker-prepull-fixture.sock"

# What the twin needed on PATH before `require_cmd docker` could speak: `dirname` for its own SCRIPT_DIR, and `uname` because common.sh calls detect_os and detect_arch at SOURCE time (common.sh:64, :100). Measured by running the case without them and reading the two `uname: command not found` lines bash printed.
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

# name -> argv and the environment the fakes read their behaviour from. `_no_docker` is not an environment variable but the marker for the one case that cannot prepend.
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "no-arguments": {"argv": []},
    "a-missing-docker": {"argv": [REF], "env": {"_no_docker": "1"}},
    "a-bare-ref": {"argv": [REF]},
    "a-ref-with-a-platform": {"argv": ["%s=linux/amd64" % REF]},
    "a-trailing-equals": {"argv": ["%s=" % REF]},
    "a-second-equals": {"argv": ["%s=a=b" % REF]},
    "dockers-own-stdout": {
        "argv": [REF],
        "env": {"FAKE_DOCKER_STDOUT": "Status: Downloaded newer image\n"},
    },
    "a-failing-pull": {"argv": [REF], "env": {"FAKE_DOCKER_RC": "1"}},
    "a-failing-pull-with-a-platform": {
        "argv": ["%s=linux/arm64" % REF],
        "env": {"FAKE_DOCKER_RC": "1"},
    },
    "one-bad-spec-among-two": {
        "argv": [REF, "%s-ok" % REF],
        "env": {"FAKE_DOCKER_FAIL_ON": REF},
    },
    "the-same-ref-twice": {"argv": [REF, REF]},
    "an-empty-ref": {"argv": ["=linux/amd64"], "env": {"FAKE_DOCKER_RC": "1"}},
    "a-mixed-batch": {"argv": [REF, "%s=linux/amd64" % REF, "%s-b" % REF]},
}

CASES = tuple(CASE_KW)

# The one case whose usage line names the implementation's own file. Compared by shape, in its own test.
DIVERGENT = ("no-arguments",)


def stub_bin(base: pathlib.Path, *, with_docker: bool = True) -> str:
    """A directory holding the fakes, prepended to the real PATH.

    PREPENDED rather than curated down to a symlink farm: the twin sourced `common.sh`, which reaches for `dirname` at source time, and `mktemp`, `tr` and `uname` live behind other helpers there. The safety property is therefore RESOLUTION ORDER, and it is asserted rather than assumed.

    `with_docker=False` IS THE ONE CASE THAT CANNOT PREPEND, because the real PATH holds a real docker on any host that can build anything here. That case gets a CURATED path instead: the stub directory plus symlinks to the two externals the subject needs before `require_cmd` speaks.
    """
    stub = base / "bin"
    stub.mkdir(parents=True, exist_ok=True)
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
            assert real is not None, "no %s on PATH; the subject cannot even start" % name
            link = stub / name
            if not link.exists():
                link.symlink_to(real)
        return str(stub)
    return "%s:%s" % (stub, os.environ.get("PATH", "/usr/bin:/bin"))


def run(subject: pathlib.Path, base: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    """One subject, once, over this case's own stub PATH."""
    kw = CASE_KW[name]
    base.mkdir(parents=True, exist_ok=True)
    log = base / "calls.log"
    log.write_text("", encoding="utf-8")
    extra = dict(kw.get("env") or {})
    env = {
        "PATH": stub_bin(base, with_docker=extra.pop("_no_docker", "") != "1"),
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
    runner = [BASH] if subject.suffix == ".sh" else [PYTHON]
    proc = subprocess.run(
        [*runner, str(subject), *kw["argv"]],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        cwd=str(base),
        timeout=120,
    )

    def mask(text: str) -> str:
        return text.replace(str(base), "<case>").replace(str(ROOT), "<repo>")

    return (
        proc.returncode,
        mask(proc.stdout),
        mask(proc.stderr),
        mask(log.read_text(encoding="utf-8")),
    )


def render(code: int, stdout: str, stderr: str, calls: str) -> str:
    return "%s%s%s" % (frozen.render(code, stdout, stderr), CALLS_MARKER, calls)


def recorded(name: str) -> tuple[int, str, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, calls = rest.split(CALLS_MARKER, 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, calls


def port(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    return run(PORT, tmp_path / name, name)


def lines(calls: str) -> list[str]:
    return [line for line in calls.splitlines() if line]


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    want = recorded(name)
    got = port(tmp_path, name)
    labels = ("exit code", "stdout", "stderr", "the docker CALL LOG")
    # `strict=True`: the tuple and the labels must stay the same length, and a silently truncated zip is how a comparison stops checking its last field.
    for label, a, b in zip(labels, want, got, strict=True):
        assert a == b, "%s: %s diverged:\n--- recorded ---\n%s\n--- port ---\n%s" % (
            name,
            label,
            a,
            b,
        )
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c not in DIVERGENT])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- The controls, first: a fake that is not reached proves nothing. ---------------------------------------------------------------------------


def test_the_fake_docker_is_the_docker(tmp_path: pathlib.Path) -> None:
    path = stub_bin(tmp_path)
    assert shutil.which("docker", path=path) == str(tmp_path / "bin" / "docker")
    assert shutil.which("sleep", path=path) == str(tmp_path / "bin" / "sleep")


def test_the_port_exists_where_this_file_says_it_does() -> None:
    assert PORT.is_file(), PORT


# --------------------------------------------------------------------------- The grammar, driven against bash's own parameter expansion. ---------------------------------------------------------------------------


def bash_split(spec: str) -> tuple[str, str]:
    """`${spec%%=*}` and the guarded `${spec#*=}`, run by the real bash.

    STILL DRIVEN AGAINST BASH ITSELF, even though the twin is gone: the claim `split_spec` makes is about bash's parameter expansion, and the only honest oracle for that is bash. It costs one subprocess per shape and it is what stops the port's own reading of the rule becoming its own proof.
    """
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
        assert dp.split_spec(spec) == bash_split(spec), spec


def test_pull_argv_omits_the_platform_flag_when_there_is_none() -> None:
    assert dp.pull_argv("x", "") == ["docker", "pull", "x"]
    assert dp.pull_argv("x", "linux/amd64") == [
        "docker",
        "pull",
        "--platform",
        "linux/amd64",
        "x",
    ]


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_a_missing_docker_is_refused_before_anything_is_pulled() -> None:
    """`require_cmd docker`, and its message is common.sh's, word for word."""
    code, stdout, stderr, calls = recorded("a-missing-docker")
    assert code == 1
    assert stdout == ""
    assert calls == "", "a pull was attempted with no docker on PATH"
    assert stderr == "✗ Required command 'docker' is not available\n"


def test_a_bare_ref_pulls_once_with_no_platform_flag() -> None:
    code, stdout, stderr, calls = recorded("a-bare-ref")
    assert code == 0
    assert lines(calls) == ["docker\tpull\t%s" % REF]
    assert "Pre-pulled 1 base image(s)" in stderr
    assert stdout == ""


def test_the_ref_equals_platform_form_passes_platform_through() -> None:
    code, _, stderr, calls = recorded("a-ref-with-a-platform")
    assert code == 0
    assert lines(calls) == ["docker\tpull\t--platform\tlinux/amd64\t%s" % REF]
    assert "Pre-pulled 1 base image(s)" in stderr


def test_a_trailing_equals_is_a_bare_ref() -> None:
    """`*=*` matches, so platform is set to "", and `[[ -n ]]` then drops it."""
    code, _, _, calls = recorded("a-trailing-equals")
    assert code == 0
    assert lines(calls) == ["docker\tpull\t%s" % REF], "an empty --platform was passed"


def test_a_second_equals_belongs_to_the_platform() -> None:
    code, _, _, calls = recorded("a-second-equals")
    assert code == 0
    assert lines(calls) == ["docker\tpull\t--platform\ta=b\t%s" % REF]


def test_docker_stdout_reaches_the_caller_unwrapped() -> None:
    """The pull's own output is INHERITED; the subject captures none of it."""
    code, stdout, _, _ = recorded("dockers-own-stdout")
    assert code == 0
    assert stdout == "Status: Downloaded newer image\n"


def test_a_failing_pull_is_three_attempts_with_thirty_then_sixty_seconds() -> None:
    """The retry schedule, and the interleaving, both recorded.

    Cheap only because `sleep` is a PATH stub: the subject would otherwise spend 90 seconds here.
    """
    code, _, stderr, calls = recorded("a-failing-pull")
    assert code == 1
    assert lines(calls) == [
        "docker\tpull\t%s" % REF,
        "sleep\t30",
        "docker\tpull\t%s" % REF,
        "sleep\t60",
        "docker\tpull\t%s" % REF,
    ], calls
    assert stderr.count("retrying in") == 2
    assert "Pull failed for %s <default>, retrying in 30s..." % REF in stderr
    assert "Pull failed for %s <default>, retrying in 60s..." % REF in stderr
    assert "Failed to pull %s <default> after 3 attempts" % REF in stderr
    assert "One or more base images could not be pulled" in stderr
    assert "Pre-pulled" not in stderr


def test_the_retry_message_names_the_platform_when_there_is_one() -> None:
    stderr = recorded("a-failing-pull-with-a-platform")[2]
    assert "Pull failed for %s linux/arm64, retrying in 30s..." % REF in stderr
    assert "Failed to pull %s linux/arm64 after 3 attempts" % REF in stderr
    assert "<default>" not in stderr


def test_one_bad_spec_does_not_stop_the_others_from_being_attempted() -> None:
    """`|| failed=1` rather than `set -e`: every spec is tried, and the run still ends non-zero. A port that gave up on the first failure would leave the later bases unpulled and the build would fail where it always did."""
    code, _, stderr, calls = recorded("one-bad-spec-among-two")
    assert code == 1
    assert lines(calls) == [
        "docker\tpull\t%s" % REF,
        "sleep\t30",
        "docker\tpull\t%s" % REF,
        "sleep\t60",
        "docker\tpull\t%s" % REF,
        "docker\tpull\t%s-ok" % REF,
    ], calls
    assert "One or more base images could not be pulled" in stderr


def test_the_count_is_the_argument_count_not_the_image_count() -> None:
    """PRESERVED WART. `$#` counts arguments, so the same ref twice reads as 2. If this ever starts counting pulls, this test goes red first."""
    code, _, stderr, calls = recorded("the-same-ref-twice")
    assert code == 0
    assert lines(calls) == ["docker\tpull\t%s" % REF] * 2
    assert "Pre-pulled 2 base image(s)" in stderr


def test_an_empty_ref_reaches_docker_as_an_empty_argument() -> None:
    """PRESERVED SHAPE. `=linux/amd64` has no ref; the subject validates nothing beyond the split, so docker is handed "" and refuses it three times."""
    code, _, _, calls = recorded("an-empty-ref")
    assert code == 1
    assert lines(calls)[0] == "docker\tpull\t--platform\tlinux/amd64\t"


def test_the_success_line_counts_a_mixed_batch() -> None:
    code, _, stderr, calls = recorded("a-mixed-batch")
    assert code == 0
    assert len(lines(calls)) == 3
    assert "Pre-pulled 3 base image(s)" in stderr


# --------------------------------------------------------------------------- The one divergence, pinned rather than papered over ---------------------------------------------------------------------------


def test_no_arguments_is_refused_with_the_usage_line(tmp_path: pathlib.Path) -> None:
    """THE ONE NAMED DIVERGENCE. `$0` is the path the caller typed, so the twin and the port legitimately name different files; everything else must match."""
    name = "no-arguments"
    want = recorded(name)
    got = port(tmp_path, name)
    assert want[0] == got[0] == 1
    assert want[1] == got[1] == ""
    assert want[3] == got[3] == "", "docker was called on the no-arguments path"

    want_lines = want[2].splitlines()
    got_lines = got[2].splitlines()
    assert want_lines[0] == got_lines[0] == "✗ No images given."
    assert want_lines[1].endswith(" <ref>[=<platform>] ...   e.g. ubuntu:24.04=linux/amd64")
    assert got_lines[1].endswith(" <ref>[=<platform>] ...   e.g. ubuntu:24.04=linux/amd64")
    assert "docker-prepull.sh" in want_lines[1], "the recorded line no longer names the twin"
    assert PORT.name in got_lines[1]
    # `✗ Usage: <path> <rest...>`: drop the three leading tokens and the remainder must be identical, so the path is the ONLY thing that differs.
    assert want_lines[1].split(" ", 3)[:2] == got_lines[1].split(" ", 3)[:2] == ["✗", "Usage:"]
    assert want_lines[1].split(" ", 3)[3] == got_lines[1].split(" ", 3)[3]
    assert len(want_lines) == len(got_lines) == 2


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


# A throwaway entry point that loads the real module, drops the `--platform` flag from every pull argv, and runs `main`. See the control below.
PLANT = """import sys

from rediacc_ci.infra import docker_prepull as subject


def _without_the_platform(image, platform):
    return ["docker", "pull", image]


subject.pull_argv = _without_the_platform
raise SystemExit(subject.main(sys.argv[1:]))
"""


def test_a_planted_drop_of_the_platform_flag_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS, aimed at the section that would otherwise be decoration.

    `--platform` is how a build asks for the architecture it is actually going to build for, and a pull that omits it fetches whatever the daemon's own architecture is. On the success path the subject says nothing about the platform: it prints `Pre-pulled 1 base image(s)` either way, exits 0 either way, and writes nothing to stdout either way. Only the recorded argv sees the
    difference, which is why the call log is a section rather than a footnote.

    THE PLANT IS A WRAPPER, NOT A COPY OF THE FILE. A copy would also run here, since this module resolves no sibling from its own location, but replacing `pull_argv` mutates exactly the argv the recording is about and leaves the file on disk untouched.
    """
    original = PORT.read_text(encoding="utf-8")
    assert '"--platform"' in original, "the plant's target moved"

    mutant = tmp_path / "plant" / "mutant.py"
    mutant.parent.mkdir(parents=True)
    mutant.write_text(PLANT, encoding="utf-8")

    name = "a-ref-with-a-platform"
    want = recorded(name)
    assert "--platform" in want[3], "the recorded corpus moved"
    planted = run(mutant, tmp_path / "planted", name)
    assert "--platform" not in planted[3], "the plant did not change the argv"
    assert lines(planted[3]) == ["docker\tpull\t%s" % REF]
    for index in (0, 1, 2):
        assert planted[index] == want[index], "the plant was supposed to be invisible here"

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original
