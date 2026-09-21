"""`rediacc_ci.infra.docker_pull_ghcr`, driven against the bytes its bash twin printed.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/infra/docker-pull-ghcr.sh` and the port over the same fixture and compared exit code, stdout, stderr and the docker CALL LOG; the K=5 ledger `.ci/shadow/w7p6-docker-pull-ghcr.observations.jsonl` recorded that comparison over five distinct trees.
Every case now compares against `goldens/docker-pull-ghcr/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree, and each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

A RECORDING FAKE `docker` ON A PREPENDED PATH is the seam, the same one `rediacc_ci.tests.test_infra_docker_prepull` established and `rediacc_ci.tests.test_infra_ci_pull_images` reuses. The reason is stronger here than for a plain pull: the subject's second action is `docker login ghcr.io --password-stdin`, which WRITES a credential into `~/.docker/config.json`, and its last action
is `docker logout ghcr.io`, which would log the developer's machine OUT of a registry it may be using. Four guards keep the real binary unreachable:

  1. the stub directory is FIRST on PATH and `test_the_fake_docker_is_the_docker`
     asserts the resolution rather than assuming it;
  2. `HOME` points into the case's own temporary directory;
  3. `DOCKER_HOST` names a socket that does not exist, fixed rather than per-case
     so a leaked docker's refusal text cannot differ between a recording and a
     replay;
  4. every image is `registry.invalid/...`, which no registry can serve.

THE CALL LOG IS THE PRIMARY ARTIFACT, so it is carried in the recorded shape as its own `--- docker calls ---` section. This script's whole observable effect is three docker invocations in a fixed order with a token on stdin, and the interesting failures are invisible in the text: a port that dropped `--quiet`, or that logged out before pulling, or that sent the token without its
trailing newline, prints exactly what a correct one prints. The login line's recorded argv carries the STDIN BYTES for that reason, and the control at the foot of this file plants a mutation that moves nothing but that section.

WHAT IS MASKED, and it is two paths, neither of which the differential ever had to compare. The case's temporary directory is its own `HOME` and its own working directory, and it is rebuilt under a different name every run, so it becomes `<root>` and its parent `<base>`. The checkout root becomes `<repo>`, because the twin's one bash-level failure carried `common.sh`'s absolute
path into the diagnostic and a golden naming this worktree would be unreadable from any other. Nothing else is touched: the glyphs, the exact wording, docker's own passed-through stdout and every recorded argv are compared as recorded.

THE `:latest` LADDER IS DRIVEN ON ALL THREE ARMS, and the third one is the one a reader misses: `USE_CI_IMAGES` unset and `USE_CI_IMAGES=TRUE` take the SAME branch, because the twin compares against the exact literal `true`. Both are cases here.

ONE CASE IS COMPARED BY SHAPE, and it has to be. `--foo.bar=x` reaches common.sh's `printf -v` on a key that is not a shell identifier, and the twin's message carried common.sh's own path and line number while `core.common` raises a refusal carrying the text alone. Exit status, stdout and the absence of any docker call are asserted equal; only the prefix is allowed to differ.

`require_cmd docker` IS THE DIFFERENCE FROM `ci-pull-images.sh`, and it means there is no second divergence in this file: the twin refused through common.sh with a message `rediacc_ci.core.common` reproduces byte for byte, so the missing-docker case compares equal on all four channels rather than being excused.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.infra import docker_pull_ghcr as dpg
from rediacc_ci.tests import frozen

ROOT = paths.repo_root()
PORT = pathlib.Path(dpg.__file__).resolve()
BASH = shutil.which("bash") or "/bin/bash"

SLUG = "docker-pull-ghcr"
CALLS_MARKER = "--- docker calls ---\n"
REPO = "<repo>"

NOWHERE_DAEMON = "unix:///nonexistent/rediacc-docker-pull-ghcr-fixture.sock"

# A ref no registry can serve, so a leaked real docker fails rather than pulls.
IMAGE = "registry.invalid/rediacc/renet:fixture"
LATEST = "registry.invalid/rediacc/renet:latest"

TOKEN = "fixture-token"  # noqa: S105 -- a throwaway fixture value that authenticates nowhere
ACTOR = "fixture-actor"

FAKE_DOCKER = """#!/usr/bin/python3
import os
import sys

argv = sys.argv[1:]
record = "docker\\t" + "\\t".join(argv)
if argv[:1] == ["login"]:
    record += "\\tstdin=%r" % sys.stdin.read()
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write(record + "\\n")

sys.stdout.write(os.environ.get("FAKE_DOCKER_STDOUT", ""))

verb = os.environ.get("FAKE_DOCKER_FAIL_ON", "")
if verb and argv[:1] == [verb]:
    sys.stderr.write("fixture: docker %s refused\\n" % verb)
    sys.exit(int(os.environ.get("FAKE_DOCKER_FAIL_RC", "1")))
sys.exit(0)
"""

# What the twin needed on PATH before `require_cmd docker` could even speak.
#
# `tr` IS ON THIS LIST BECAUSE THE CONTROL DID NOT FIRE WITHOUT IT, and the reason had nothing to do with the subject. `parse_args` -> `to_upper` is `echo "$1" | tr '[:lower:]' '[:upper:]'` (common.sh:302), a FORK PER FLAG, so a curated PATH without `tr` made the twin die at `common.sh: line 302: tr: command not found` with status 127, before a single validation ran. Measured: the
# missing-docker case reported `twin: 127 / port: 1` and looked like a port that had lost `require_cmd`. It is also a real latent property of common.sh worth knowing: any of the 53 `parse_args` callers dies at 127 on a host with no `tr`.
CURATED = ("dirname", "uname", "tr")

# name -> (argv, environment overrides). An override whose value is the empty string UNSETS the variable, which is the only way to drive `${GITHUB_TOKEN:-}` and `${CI:-}` down their absent arms; `_no_docker` is not an environment variable but the marker that builds a PATH with no docker on it at all.
CASE_KW: dict[str, tuple[list[str], dict[str, str]]] = {
    "no-image": ([], {}),
    "the-happy-path": (["--image", IMAGE], {}),
    "the-quiet-flag": (["--image", IMAGE, "--quiet"], {}),
    "quiet-with-a-following-word": (["--image", IMAGE, "--quiet", "false"], {}),
    "the-token-and-actor-flags": (
        ["--image", IMAGE, "--token", "flag-tok", "--actor", "flag-actor"],
        {},
    ),
    "a-missing-token": (["--image", IMAGE], {"GITHUB_TOKEN": ""}),
    "a-missing-actor": (["--image", IMAGE], {"GITHUB_ACTOR": ""}),
    "a-missing-docker": (["--image", IMAGE], {"_no_docker": "1"}),
    "latest-with-use-ci-images-true": (
        ["--image", LATEST],
        {"CI": "true", "USE_CI_IMAGES": "true"},
    ),
    "latest-with-use-ci-images-false": (
        ["--image", LATEST],
        {"CI": "true", "USE_CI_IMAGES": "false"},
    ),
    "latest-with-no-flag": (["--image", LATEST], {"CI": "true"}),
    "latest-with-ci-zero": (["--image", LATEST], {"CI": "0"}),
    "latest-with-ci-one": (["--image", LATEST], {"CI": "1"}),
    "latest-with-ci-false": (["--image", LATEST], {"CI": "false"}),
    "latest-outside-ci": (["--image", LATEST], {"CI": ""}),
    "a-failing-login": (
        ["--image", IMAGE],
        {"FAKE_DOCKER_FAIL_ON": "login", "FAKE_DOCKER_FAIL_RC": "42"},
    ),
    "a-failing-pull": (["--image", IMAGE], {"FAKE_DOCKER_FAIL_ON": "pull"}),
    "a-failing-logout": (["--image", IMAGE], {"FAKE_DOCKER_FAIL_ON": "logout"}),
    "dockers-own-stdout": (
        ["--image", IMAGE],
        {"FAKE_DOCKER_STDOUT": "Status: Downloaded newer image\n"},
    ),
    "a-flag-that-is-not-an-identifier": (["--foo.bar=x", "--image", IMAGE], {}),
}

CASES = tuple(CASE_KW)

# The one case the port does not reproduce byte for byte. Compared by shape, in its own test.
DIVERGENT = ("a-flag-that-is-not-an-identifier",)


def _stub_bin(base: pathlib.Path, *, with_docker: bool = True) -> str:
    stub = base / "bin"
    stub.mkdir(exist_ok=True)
    if with_docker:
        fake = stub / "docker"
        fake.write_text(FAKE_DOCKER, encoding="utf-8")
        fake.chmod(0o755)
        return "%s:%s" % (stub, os.environ.get("PATH", "/usr/bin:/bin"))
    for name in CURATED:
        real = shutil.which(name)
        assert real is not None, "no %s on PATH; the twin cannot even source common.sh" % name
        (stub / name).symlink_to(real)
    return str(stub)


def _spawn(subject: pathlib.Path, base: pathlib.Path, argv: list[str], extra: dict[str, str]):
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
        "DOCKER_HOST": NOWHERE_DAEMON,
        "GITHUB_TOKEN": TOKEN,
        "GITHUB_ACTOR": ACTOR,
    }
    for key, value in list(extra.items()):
        if value == "":
            env.pop(key, None)
            extra.pop(key)
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


def mask(text: str, base: pathlib.Path) -> str:
    return frozen.mask_root(text, base).replace(str(ROOT), REPO)


def run(where: pathlib.Path, subject: pathlib.Path, name: str) -> tuple[int, str, str, list[str]]:
    """One subject, once, over this case's own fixture directory.

    A FRESH DIRECTORY PER RUN, because it is the stub PATH, the call log and `HOME` all at once: giving the next run the previous one's leftovers would let a call log accumulate across cases and a recorded credential survive into a case that never logged in.
    """
    argv, extra = CASE_KW[name]
    where.mkdir(parents=True, exist_ok=True)
    code, stdout, stderr, calls = _spawn(subject, where, list(argv), dict(extra))
    return (
        code,
        mask(stdout.decode("utf-8"), where),
        mask(stderr.decode("utf-8"), where),
        [mask(line, where) for line in calls],
    )


def render(code: int, stdout: str, stderr: str, calls: list[str]) -> str:
    return "%s%s%s\n" % (frozen.render(code, stdout, stderr), CALLS_MARKER, "\n".join(calls))


def recorded(name: str) -> tuple[int, str, str, list[str]]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, calls = rest.split(CALLS_MARKER, 1)
    return (
        int(exit_line.removeprefix("exit: ")),
        stdout,
        stderr,
        [line for line in calls.splitlines() if line],
    )


def port(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, list[str]]:
    return run(tmp_path / name, PORT, name)


def verbs(calls: list[str]) -> list[str]:
    return [line.split("\t")[1] for line in calls]


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, list[str]]:
    want = recorded(name)
    got = port(tmp_path, name)
    assert got[0] == want[0], "%s: the twin exited %d, the port %d" % (name, want[0], got[0])
    assert got[1] == want[1], "%s: stdout diverged: %r vs %r" % (name, want[1], got[1])
    assert got[2] == want[2], "%s: stderr diverged: %r vs %r" % (name, want[2], got[2])
    assert got[3] == want[3], "%s: the docker calls diverged: %r vs %r" % (name, want[3], got[3])
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c not in DIVERGENT])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- The seam, first: a fake that is not reached proves nothing. ---------------------------------------------------------------------------


def test_the_fake_docker_is_the_docker(tmp_path: pathlib.Path) -> None:
    path = _stub_bin(tmp_path)
    assert shutil.which("docker", path=path) == str(tmp_path / "bin" / "docker")


def test_the_port_exists_where_this_file_says_it_does() -> None:
    assert PORT.is_file(), PORT


def test_no_ghcr_helper_exists_to_share_because_common_sh_has_none() -> None:
    """THE DUPLICATION CLAIM IN THE PORT'S DOCSTRING, MEASURED RATHER THAN ASSERTED.

    The port says the GHCR-auth dance is duplicated and deliberately not factored, on the grounds that `common.sh` offers nothing to call. If a helper ever lands there, this goes red and that docstring becomes wrong in the same run. The surviving sibling twin is checked too: it still open-codes the same three lines.
    """
    common_sh = (ROOT / ".ci" / "scripts" / "lib" / "common.sh").read_text(encoding="utf-8")
    assert "ghcr" not in common_sh.lower()
    assert "docker login" not in common_sh
    sibling = ROOT / ".ci" / "scripts" / "infra" / "ci-pull-images.sh"
    assert "docker login ghcr.io" in sibling.read_text(encoding="utf-8"), sibling


# --------------------------------------------------------------------------- The pure halves, driven directly. ---------------------------------------------------------------------------


def test_resolve_prefers_the_flag_then_the_environment() -> None:
    env = {"GITHUB_TOKEN": "env-tok", "GITHUB_ACTOR": "env-actor"}
    assert dpg.resolve({"ARG_IMAGE": "i"}, env) == ("i", "env-tok", "env-actor", "false")
    assert dpg.resolve({"ARG_IMAGE": "i", "ARG_TOKEN": "flag"}, env)[1] == "flag"
    # `${ARG_TOKEN:-${GITHUB_TOKEN:-}}` is the COLON form, so an empty flag
    # value falls THROUGH to the environment rather than winning.
    assert dpg.resolve({"ARG_IMAGE": "i", "ARG_TOKEN": ""}, env)[1] == "env-tok"
    assert dpg.resolve({}, {}) == ("", "", "", "false")


def test_pull_argv_adds_quiet_only_for_the_exact_literal() -> None:
    assert dpg.pull_argv("x", "true") == ["docker", "pull", "--quiet", "x"]
    for spelling in ("false", "TRUE", "1", "yes", ""):
        assert dpg.pull_argv("x", spelling) == ["docker", "pull", "x"], spelling


def test_latest_verdict_has_three_arms_and_only_one_of_them_warns() -> None:
    errs, warns = dpg.latest_verdict(LATEST, {"CI": "1", "USE_CI_IMAGES": "true"})
    assert len(errs) == 3
    assert warns == []
    errs, warns = dpg.latest_verdict(LATEST, {"CI": "1", "USE_CI_IMAGES": "false"})
    assert errs == []
    assert len(warns) == 1
    errs, warns = dpg.latest_verdict(LATEST, {"CI": "1"})
    assert len(errs) == 3
    assert warns == []
    # `TRUE` is NOT `true`: it takes the legacy arm, not the first one.
    errs, _ = dpg.latest_verdict(LATEST, {"CI": "1", "USE_CI_IMAGES": "TRUE"})
    assert errs[0] == dpg.LATEST_HEAD_LEGACY
    # Outside CI, and for any tag that is not `:latest`, the ladder is skipped.
    assert dpg.latest_verdict(LATEST, {}) == ([], [])
    assert dpg.latest_verdict(IMAGE, {"CI": "1"}) == ([], [])
    # A SUFFIX, not a tag parse: `notlatest` does not match.
    assert dpg.latest_verdict("registry.invalid/x:notlatest", {"CI": "1"}) == ([], [])


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_no_image_is_the_usage_refusal_and_nothing_is_pulled() -> None:
    code, stdout, stderr, calls = recorded("no-image")
    assert code == 1
    assert stdout == ""
    assert calls == []
    assert stderr == "✗ %s\n" % dpg.USAGE


def test_the_happy_path_is_login_pull_logout_with_the_token_on_stdin() -> None:
    code, stdout, stderr, calls = recorded("the-happy-path")
    assert code == 0
    assert calls == [
        "docker\tlogin\tghcr.io\t-u\t%s\t--password-stdin\tstdin='%s\\n'" % (ACTOR, TOKEN),
        "docker\tpull\t%s" % IMAGE,
        "docker\tlogout\tghcr.io",
    ], calls
    assert stdout == ""
    assert stderr.splitlines() == [
        "→ Authenticating with ghcr.io...",
        "→ Pulling %s..." % IMAGE,
        "→ Cleaning up GHCR credentials...",
        "✓ Successfully pulled %s" % IMAGE,
    ]


def test_quiet_only_reaches_docker_and_not_the_log_lines() -> None:
    """`--quiet` is docker's flag, not this script's. The three `log_step` lines print either way; a port that treated it as a verbosity switch would be silently quieter than the twin in CI logs."""
    code, _, stderr, calls = recorded("the-quiet-flag")
    assert code == 0
    assert calls[1] == "docker\tpull\t--quiet\t%s" % IMAGE
    assert stderr.count("→ ") == 3


def test_quiet_with_a_following_word_takes_that_word_as_its_value() -> None:
    """common.sh `parse_args` QUIRK: `--quiet` consumes the next token unless it starts with `--`. So `--quiet --image X` is the boolean and `--image X --quiet false` is NOT, and the flag never reaches docker. Reproduced through `core.common`."""
    assert recorded("quiet-with-a-following-word")[3][1] == "docker\tpull\t%s" % IMAGE


def test_the_token_and_actor_flags_beat_the_environment() -> None:
    """Both flags win over `GITHUB_TOKEN` and `GITHUB_ACTOR`, and the recorded login argv is where that is visible: the actor is an argument and the token is the bytes on stdin."""
    assert recorded("the-token-and-actor-flags")[3][0] == (
        "docker\tlogin\tghcr.io\t-u\tflag-actor\t--password-stdin\tstdin='flag-tok\\n'"
    )


def test_a_missing_token_is_refused_before_docker_is_reached() -> None:
    code, _, stderr, calls = recorded("a-missing-token")
    assert code == 1
    assert calls == []
    assert stderr == "✗ %s\n" % dpg.MISSING_TOKEN


def test_a_missing_actor_is_refused_before_docker_is_reached() -> None:
    code, _, stderr, calls = recorded("a-missing-actor")
    assert code == 1
    assert calls == []
    assert stderr == "✗ %s\n" % dpg.MISSING_ACTOR


def test_a_missing_docker_is_common_shs_refusal_word_for_word() -> None:
    """UNLIKE `ci-pull-images.sh`: this subject calls `require_cmd docker`, so there is no bash `command not found` at 127 and no divergence to excuse."""
    code, _, stderr, calls = recorded("a-missing-docker")
    assert code == 1
    assert calls == []
    assert stderr == "✗ Required command 'docker' is not available\n"


def test_latest_in_ci_with_use_ci_images_true_is_three_errors_and_no_pull() -> None:
    code, _, stderr, calls = recorded("latest-with-use-ci-images-true")
    assert code == 1
    assert calls == []
    assert stderr.splitlines() == [
        "✗ %s" % dpg.LATEST_HEAD_CI,
        "✗ %s" % dpg.LATEST_MID_CI,
        "✗ %s" % (dpg.LATEST_TAIL % LATEST),
    ]


def test_latest_in_ci_with_use_ci_images_false_warns_and_pulls_anyway() -> None:
    code, _, stderr, calls = recorded("latest-with-use-ci-images-false")
    assert code == 0
    assert verbs(calls) == ["login", "pull", "logout"]
    assert "⚠ %s" % dpg.LATEST_ALLOWED_WARNING in stderr


def test_latest_in_ci_with_no_flag_is_the_legacy_refusal() -> None:
    code, _, stderr, calls = recorded("latest-with-no-flag")
    assert code == 1
    assert calls == []
    assert "✗ %s" % dpg.LATEST_HEAD_LEGACY in stderr


def test_any_non_empty_ci_arms_the_latest_check_including_zero() -> None:
    """`[[ -n "${CI:-}" ]]`, NOT `is_ci`. `CI=0` and `CI=1` are both "in CI" here, while `is_ci` in common.sh would say no to both. Two tests in one tree disagreeing about what CI means is the twin's disagreement, and it is preserved."""
    for name in ("latest-with-ci-zero", "latest-with-ci-one", "latest-with-ci-false"):
        code, _, _, calls = recorded(name)
        assert code == 1, name
        assert calls == [], name


def test_outside_ci_a_latest_tag_is_pulled_without_comment() -> None:
    code, _, stderr, calls = recorded("latest-outside-ci")
    assert code == 0
    assert verbs(calls) == ["login", "pull", "logout"]
    assert "latest" not in stderr.replace(LATEST, "")


def test_a_failing_login_stops_before_the_pull_and_keeps_dockers_status() -> None:
    """Under `pipefail` the pipeline's status is docker's own, so 42 in means 42 out, and nothing is pulled from a registry the run never authenticated to."""
    code, _, _, calls = recorded("a-failing-login")
    assert code == 42
    assert verbs(calls) == ["login"]


def test_a_failing_pull_never_reaches_the_logout() -> None:
    """SAME HAZARD AS `ci-pull-images.sh`, in a smaller script and with no subshell to blame: `set -e` walks out past `docker logout`, so a failed pull leaves the GHCR credential in `~/.docker/config.json`. Both sides did it. Reported to the driver rather than repaired, because repairing it would have meant changing the live twin."""
    code, _, stderr, calls = recorded("a-failing-pull")
    assert code == 1
    assert verbs(calls) == ["login", "pull"]
    assert "Cleaning up GHCR credentials" not in stderr
    assert "Successfully pulled" not in stderr


def test_a_failing_logout_loses_the_success_line() -> None:
    """UNGUARDED LOGOUT, unlike `ci-pull-images.sh`'s `2>/dev/null || true`. The image IS pulled and the script still exits non-zero with no success line, so a caller reading the exit status concludes the pull failed."""
    code, _, stderr, calls = recorded("a-failing-logout")
    assert code == 1
    assert verbs(calls) == ["login", "pull", "logout"]
    assert "Successfully pulled" not in stderr
    # And docker's complaint is NOT suppressed here, which is the other half of the difference from the sibling script.
    assert "fixture: docker logout refused" in stderr


def test_dockers_own_stdout_reaches_the_caller_unwrapped() -> None:
    """Three docker calls, so the fixture line appears three times. The point is that the script captures none of it and re-emits none of it, and that the passthrough lands on stdout while every line the script writes itself lands on stderr."""
    code, stdout, stderr, _ = recorded("dockers-own-stdout")
    assert code == 0
    assert stdout == "Status: Downloaded newer image\n" * 3
    assert "Status: Downloaded" not in stderr


# --------------------------------------------------------------------------- The one divergence, pinned rather than papered over ---------------------------------------------------------------------------


def test_divergence_a_flag_that_is_not_a_shell_identifier(tmp_path: pathlib.Path) -> None:
    """common.sh QUIRK 3, reached through `parse_args "$@"`: `printf -v 'ARG_FOO.BAR'` fails, `set -e` is on, and the run dies at exit 2 with a message naming common.sh rather than the caller. `core.common` reproduces the text; only bash's `common.sh: line 334: ` prefix differs, so the exit status, the empty stdout and the absence of any docker call are what is compared."""
    name = "a-flag-that-is-not-an-identifier"
    want = recorded(name)
    got = port(tmp_path, name)
    assert want[0] == got[0] == 2
    assert want[1] == got[1] == ""
    assert want[3] == got[3] == []
    for text in (want[2], got[2]):
        assert "not a valid identifier" in text, text
    assert "common.sh" in want[2], "the twin's message named common.sh"
    assert REPO in want[2], "the recorded path was not masked"


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_truthy_quiet_is_caught_by_the_call_log(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS. Read `QUIET` as a boolean instead of comparing it against the literal `true`.

    `[[ "$QUIET" == "true" ]]` is an exact-literal comparison, and `QUIET` defaults to the STRING `false`, which is truthy in Python. A port that wrote `if quiet:` therefore adds `--quiet` to every pull, including the happy path where the twin recorded a bare `docker pull`. That mutation moves NOTHING on stdout or stderr, because the three `log_step` lines print either way, so a
    comparison of the two streams alone would stay green and the `--- docker calls ---` section is the only thing that sees it. The mutant is a throwaway copy resolving `rediacc_ci` through PYTHONPATH exactly as the tracked file does; the tracked port is never touched.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = "    if quiet == USE_CI_TRUE:\n"
    assert original.count(anchor) == 1, "the plant's anchor moved"
    mutated = original.replace(anchor, "    if quiet:\n")

    mutant = tmp_path / "plant" / "docker_pull_ghcr.py"
    mutant.parent.mkdir(parents=True)
    mutant.write_text(mutated, encoding="utf-8")

    name = "the-happy-path"
    want = recorded(name)
    assert want[3][1] == "docker\tpull\t%s" % IMAGE, "the recorded corpus moved"
    code, stdout, stderr, calls = run(tmp_path / "planted", mutant, name)
    assert calls[1] == "docker\tpull\t--quiet\t%s" % IMAGE, "the plant did not change the argv"
    assert (code, stdout, stderr) == (want[0], want[1], want[2]), "the plant was visible elsewhere"

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original
