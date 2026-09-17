"""Differential: `rediacc_ci.infra.docker_pull_ghcr` against its twin
`.ci/scripts/infra/docker-pull-ghcr.sh`.

A RECORDING FAKE `docker` ON A PREPENDED PATH, the same seam `rediacc_ci.tests.test_infra_docker_prepull` established and `rediacc_ci.tests.test_infra_ci_pull_images` reuses. The reason is stronger here than for a plain pull: the subject's second action is `docker login ghcr.io --password-stdin`, which WRITES a credential into `~/.docker/config.json`, and its last action is `docker
logout ghcr.io`, which would log the developer's machine OUT of a registry it may be using. Four guards keep the real binary unreachable:

  1. the stub directory is FIRST on PATH and
     `test_the_fake_docker_is_the_docker` asserts the resolution rather than
     assuming it;
  2. `HOME` points into the case's own temporary directory;
  3. `DOCKER_HOST` names a socket that does not exist, fixed rather than
     per-case so a leaked docker's refusal text cannot differ between sides;
  4. every image is `registry.invalid/...`, which no registry can serve.

THE CALL LOG IS THE PRIMARY ARTIFACT. This script's whole observable effect is three docker invocations in a fixed order with a token on stdin, and the interesting failures are invisible in the text: a port that dropped `--quiet`, or that logged out before pulling, or that sent the token without its trailing newline, prints exactly what a correct one prints. The login line's
recorded argv carries the STDIN BYTES for that reason.

THE `:latest` LADDER IS DRIVEN ON ALL THREE ARMS, and the third one is the one a
reader misses: `USE_CI_IMAGES` unset and `USE_CI_IMAGES=TRUE` take the SAME
branch, because the twin compares against the exact literal `true`. Both are cases here.

`require_cmd docker` IS THE DIFFERENCE FROM `ci-pull-images.sh`, and it means there is NO named divergence in this file: the twin refuses through common.sh
with a message `rediacc_ci.core.common` reproduces byte for byte, so the
missing-docker case compares equal on all four channels rather than being excused.

K=5 LEDGER: `.ci/shadow/w7p6-docker-pull-ghcr.observations.jsonl`, recorded in a
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
from rediacc_ci.infra import docker_pull_ghcr as dpg

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "infra" / "docker-pull-ghcr.sh"
PORT = pathlib.Path(dpg.__file__).resolve()
BASH = shutil.which("bash") or "/bin/bash"

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

# What the twin needs on PATH before `require_cmd docker` can even speak.
#
# `tr` IS ON THIS LIST BECAUSE THE CONTROL DID NOT FIRE WITHOUT IT, and the reason had nothing to do with the subject. `parse_args` -> `to_upper` is `echo "$1" | tr '[:lower:]' '[:upper:]'` (common.sh:302), a FORK PER FLAG, so a curated PATH without `tr` makes the twin die at `common.sh: line 302: tr: command not found` with status 127 -- before a single validation runs. Measured:
# the missing-docker case reported `twin: 127 / port: 1` and looked like a port that had lost `require_cmd`. It is also a real latent property of common.sh worth knowing: any of the 53 `parse_args` callers dies at 127 on a host with no `tr`.
CURATED = ("dirname", "uname", "tr")


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
        "DOCKER_HOST": NOWHERE_DAEMON,
        "GITHUB_TOKEN": TOKEN,
        "GITHUB_ACTOR": ACTOR,
    }
    for key, value in list(extra.items()):
        # An empty value means UNSET, which is the only way to drive
        # `${GITHUB_TOKEN:-}` and `${CI:-}` down their absent arms.
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


def _sides(name: str, argv: list[str], **extra: str):
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


def test_both_subjects_exist_where_this_file_says_they_do() -> None:
    assert TWIN.is_file(), TWIN
    assert PORT.is_file(), PORT


def test_the_twin_parses_under_bash() -> None:
    proc = subprocess.run([BASH, "-n", str(TWIN)], capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr


def test_neither_twin_shares_a_ghcr_helper_because_common_sh_has_none() -> None:
    """THE DUPLICATION CLAIM IN BOTH DOCSTRINGS, MEASURED RATHER THAN ASSERTED.

    Both ports say the GHCR-auth dance is duplicated in bash and deliberately not factored, on the grounds that `common.sh` offers nothing to call. If a helper ever lands there, this goes red and the two docstrings become wrong in the same run.
    """
    common_sh = (ROOT / ".ci" / "scripts" / "lib" / "common.sh").read_text(encoding="utf-8")
    assert "ghcr" not in common_sh.lower()
    assert "docker login" not in common_sh
    # And both twins really do open-code it.
    for twin in (TWIN, ROOT / ".ci" / "scripts" / "infra" / "ci-pull-images.sh"):
        assert "docker login ghcr.io" in twin.read_text(encoding="utf-8"), twin


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


# --------------------------------------------------------------------------- The differential. ---------------------------------------------------------------------------


def test_no_image_is_the_usage_refusal_and_nothing_is_pulled() -> None:
    exit_code, stdout, stderr, calls = _sides("no-image", [])
    assert exit_code == 1
    assert stdout == b""
    assert calls == []
    assert stderr.decode() == "✗ %s\n" % dpg.USAGE


def test_the_happy_path_is_login_pull_logout_with_the_token_on_stdin() -> None:
    exit_code, stdout, stderr, calls = _sides("happy", ["--image", IMAGE])
    assert exit_code == 0
    assert calls == [
        "docker\tlogin\tghcr.io\t-u\t%s\t--password-stdin\tstdin='%s\\n'" % (ACTOR, TOKEN),
        "docker\tpull\t%s" % IMAGE,
        "docker\tlogout\tghcr.io",
    ], calls
    assert stdout == b""
    assert stderr.decode().splitlines() == [
        "→ Authenticating with ghcr.io...",
        "→ Pulling %s..." % IMAGE,
        "→ Cleaning up GHCR credentials...",
        "✓ Successfully pulled %s" % IMAGE,
    ]


def test_quiet_only_reaches_docker_and_not_the_log_lines() -> None:
    """`--quiet` is docker's flag, not this script's. The three `log_step` lines
    print either way; a port that treated it as a verbosity switch would be
    silently quieter than the twin in CI logs."""
    exit_code, _, stderr, calls = _sides("quiet", ["--image", IMAGE, "--quiet"])
    assert exit_code == 0
    assert calls[1] == "docker\tpull\t--quiet\t%s" % IMAGE
    assert stderr.decode().count("→ ") == 3


def test_quiet_with_a_following_word_takes_that_word_as_its_value() -> None:
    """common.sh `parse_args` QUIRK: `--quiet` consumes the next token unless it
    starts with `--`. So `--quiet --image X` is the boolean and
    `--image X --quiet false` is NOT. Reproduced through `core.common`."""
    _, _, _, calls = _sides("quiet-false", ["--image", IMAGE, "--quiet", "false"])
    assert calls[1] == "docker\tpull\t%s" % IMAGE


def test_the_token_and_actor_flags_beat_the_environment() -> None:
    _, _, _, calls = _sides(
        "flags", ["--image", IMAGE, "--token", "flag-tok", "--actor", "flag-actor"]
    )
    assert calls[0] == (
        "docker\tlogin\tghcr.io\t-u\tflag-actor\t--password-stdin\tstdin='flag-tok\\n'"
    )


def test_a_missing_token_is_refused_before_docker_is_reached() -> None:
    exit_code, _, stderr, calls = _sides("no-token", ["--image", IMAGE], GITHUB_TOKEN="")
    assert exit_code == 1
    assert calls == []
    assert stderr.decode() == "✗ %s\n" % dpg.MISSING_TOKEN


def test_a_missing_actor_is_refused_before_docker_is_reached() -> None:
    exit_code, _, stderr, calls = _sides("no-actor", ["--image", IMAGE], GITHUB_ACTOR="")
    assert exit_code == 1
    assert calls == []
    assert stderr.decode() == "✗ %s\n" % dpg.MISSING_ACTOR


def test_a_missing_docker_is_common_shs_refusal_word_for_word() -> None:
    """UNLIKE `ci-pull-images.sh`: this twin calls `require_cmd docker`, so
    there is no bash `command not found` and no named divergence."""
    exit_code, _, stderr, calls = _sides("no-docker", ["--image", IMAGE], _no_docker="1")
    assert exit_code == 1
    assert calls == []
    assert stderr == b"\xe2\x9c\x97 Required command 'docker' is not available\n"


def test_latest_in_ci_with_use_ci_images_true_is_three_errors_and_no_pull() -> None:
    exit_code, _, stderr, calls = _sides(
        "latest-strict", ["--image", LATEST], CI="true", USE_CI_IMAGES="true"
    )
    assert exit_code == 1
    assert calls == []
    assert stderr.decode().splitlines() == [
        "✗ %s" % dpg.LATEST_HEAD_CI,
        "✗ %s" % dpg.LATEST_MID_CI,
        "✗ %s" % (dpg.LATEST_TAIL % LATEST),
    ]


def test_latest_in_ci_with_use_ci_images_false_warns_and_pulls_anyway() -> None:
    exit_code, _, stderr, calls = _sides(
        "latest-allowed", ["--image", LATEST], CI="true", USE_CI_IMAGES="false"
    )
    assert exit_code == 0
    assert [c.split("\t")[1] for c in calls] == ["login", "pull", "logout"]
    assert "⚠ %s" % dpg.LATEST_ALLOWED_WARNING in stderr.decode()


def test_latest_in_ci_with_no_flag_is_the_legacy_refusal() -> None:
    exit_code, _, stderr, calls = _sides("latest-legacy", ["--image", LATEST], CI="true")
    assert exit_code == 1
    assert calls == []
    assert "✗ %s" % dpg.LATEST_HEAD_LEGACY in stderr.decode()


def test_any_non_empty_ci_arms_the_latest_check_including_zero() -> None:
    """`[[ -n "${CI:-}" ]]`, NOT `is_ci`. `CI=0` and `CI=1` are both "in CI"
    here, while `is_ci` in common.sh would say no to both. The two tests in one
    tree disagreeing about what CI means is the twin's, and it is preserved."""
    for value in ("0", "1", "false"):
        exit_code, _, _, calls = _sides("ci-%s" % value, ["--image", LATEST], CI=value)
        assert exit_code == 1, value
        assert calls == [], value


def test_outside_ci_a_latest_tag_is_pulled_without_comment() -> None:
    exit_code, _, stderr, calls = _sides("latest-local", ["--image", LATEST], CI="")
    assert exit_code == 0
    assert [c.split("\t")[1] for c in calls] == ["login", "pull", "logout"]
    assert "latest" not in stderr.decode().replace(LATEST, "")


def test_a_failing_login_stops_before_the_pull_and_keeps_dockers_status() -> None:
    exit_code, _, _, calls = _sides(
        "login-fails",
        ["--image", IMAGE],
        FAKE_DOCKER_FAIL_ON="login",
        FAKE_DOCKER_FAIL_RC="42",
    )
    assert exit_code == 42
    assert [c.split("\t")[1] for c in calls] == ["login"]


def test_a_failing_pull_never_reaches_the_logout() -> None:
    """SAME HAZARD AS `ci-pull-images.sh`, in a smaller script and with no
    subshell to blame: `set -e` walks out past `docker logout`, so a failed pull leaves the GHCR credential in `~/.docker/config.json`. Both sides do it. Reported to the driver rather than repaired, because repairing it means
    changing the live twin."""
    exit_code, _, stderr, calls = _sides(
        "pull-fails", ["--image", IMAGE], FAKE_DOCKER_FAIL_ON="pull"
    )
    assert exit_code == 1
    assert [c.split("\t")[1] for c in calls] == ["login", "pull"]
    assert b"Cleaning up GHCR credentials" not in stderr
    assert b"Successfully pulled" not in stderr


def test_a_failing_logout_loses_the_success_line() -> None:
    """UNGUARDED LOGOUT, unlike `ci-pull-images.sh`'s `2>/dev/null || true`. The
    image IS pulled and the script still exits non-zero with no success line, so
    a caller reading the exit status concludes the pull failed."""
    exit_code, _, stderr, calls = _sides(
        "logout-fails", ["--image", IMAGE], FAKE_DOCKER_FAIL_ON="logout"
    )
    assert exit_code == 1
    assert [c.split("\t")[1] for c in calls] == ["login", "pull", "logout"]
    assert b"Successfully pulled" not in stderr
    # And its complaint is NOT suppressed here, which is the other half of the difference from the sibling script.
    assert b"fixture: docker logout refused" in stderr


def test_dockers_own_stdout_reaches_the_caller_unwrapped() -> None:
    exit_code, stdout, _, _ = _sides(
        "passthrough",
        ["--image", IMAGE],
        FAKE_DOCKER_STDOUT="Status: Downloaded newer image\n",
    )
    assert exit_code == 0
    # Three docker calls, so the fixture line appears three times. The point is that neither side captures or re-emits it.
    assert stdout == b"Status: Downloaded newer image\n" * 3


def test_a_flag_that_is_not_a_shell_identifier_kills_the_run_on_both_sides() -> None:
    """common.sh QUIRK 3, reached through this script's `parse_args "$@"`:
    `printf -v 'ARG_FOO.BAR'` fails, `set -e` is on, and the script dies at exit 2 with a message naming common.sh rather than the caller. `core.common`
    reproduces the text; only bash's `common.sh: line 333: ` prefix differs, so
    the exit status and the absence of any docker call are what is compared."""
    results = []
    with tempfile.TemporaryDirectory() as td:
        for subject in (TWIN, PORT):
            base = pathlib.Path(td) / subject.stem
            base.mkdir(parents=True)
            results.append(_run(subject, base, ["--foo.bar=x", "--image", IMAGE], {}))
    old, new = results
    assert old[0] == new[0] == 2
    assert old[3] == new[3] == []
    assert "not a valid identifier" in old[2].decode()
    assert "not a valid identifier" in new[2].decode()
