"""Differential: `rediacc_ci.infra.ci_pull_images` against its twin
`.ci/scripts/infra/ci-pull-images.sh`.

A RECORDING FAKE `docker` ON A PREPENDED PATH, the seam `rediacc_ci.tests.test_infra_docker_prepull` established. It is not a convenience here, it is the only safe way to run this subject at all: the twin's second line is `docker login ghcr.io --password-stdin`, and a case that reached the real binary would WRITE A CREDENTIAL into the developer's `~/.docker/config.json`, then pull
two multi-hundred-megabyte images, then LOG THE MACHINE OUT of ghcr.io. Four independent things keep the real one out of reach:

  1. the stub directory is FIRST on PATH and `shutil.which("docker", path=...)`
     is asserted to resolve to the fake, in `test_the_fake_docker_is_the_docker`
     -- a control that fires if the ordering ever stops working;
  2. `HOME` is redirected into the case's own temporary directory, so even a
     leaked real `docker login` could not touch the developer's config;
  3. `DOCKER_HOST` points at a socket that does not exist, so a leaked real
     docker cannot reach a daemon. It is a FIXED path rather than one under the
     case's temp directory, because docker's refusal quotes the socket path and
     the two sides' temp directories legitimately differ -- that difference
     would then show up as a divergence in the subject rather than the fixture;
  4. every case uses a fixture token and the actor `fixture-actor`, so nothing
     that could authenticate anywhere is ever on a command line.

THE CALL LOG IS THE PRIMARY ARTIFACT, and for this script more than most. The observable effect is a SEQUENCE of five docker invocations plus a rewrite of `~/.docker/config.json`, and two implementations can print byte-identical text
while making different calls: a port that pulled `renet` from the hard-coded
`ghcr.io/rediacc` instead of `$DOCKER_REGISTRY`, or that logged out before the config scrub, prints exactly what a correct one prints. Every case compares the log, and the login case compares the BYTES ON DOCKER'S STDIN as well, because `--password-stdin` is where the token goes and `echo` appends a newline.

THE CREDENTIAL-CLEANUP HAZARD IS PINNED, NOT FIXED.
`test_a_failing_pull_skips_the_credential_cleanup_on_both_sides` asserts that BOTH sides walk away from a failed pull with no `docker logout` and no config
scrub. That is the twin's behaviour and the port reproduces it; the test exists
so that the day someone adds the missing `trap ... EXIT` they have to change this file and read the reason.

ONE NAMED DIVERGENCE, and it is the missing-docker case. The twin has no `require_cmd docker`, so bash itself prints `<script>: line 49: docker: command not found` -- a message naming a line number the port does not have. `test_a_missing_docker_is_127_on_both_sides_with_a_named_text_divergence` asserts the exit STATUS is 127 on both, that both say `command not found`, and that the
texts differ only in that prefix.

K=5 LEDGER: `.ci/shadow/w7p6-ci-pull-images.observations.jsonl`, recorded in a
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
from rediacc_ci.infra import ci_pull_images as cpi

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "infra" / "ci-pull-images.sh"
PORT = pathlib.Path(cpi.__file__).resolve()
BASH = shutil.which("bash") or "/bin/bash"

# A socket that does not exist, identical on both sides. See the module docstring.
NOWHERE_DAEMON = "unix:///nonexistent/rediacc-ci-pull-images-fixture.sock"

TOKEN = "fixture-token"  # noqa: S105 -- a throwaway fixture value that authenticates nowhere
ACTOR = "fixture-actor"

FAKE_DOCKER = """#!/usr/bin/python3
import os
import sys

argv = sys.argv[1:]
record = "docker\\t" + "\\t".join(argv)
# `--password-stdin` is the whole point of the login call, so the bytes that
# reach it are recorded rather than merely the argv.
if argv[:1] == ["login"]:
    record += "\\tstdin=%r" % sys.stdin.read()
with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write(record + "\\n")

if argv[:1] == ["images"]:
    sys.stdout.write(os.environ.get("FAKE_DOCKER_IMAGES", ""))

sys.stdout.write(os.environ.get("FAKE_DOCKER_STDOUT", ""))

verb = os.environ.get("FAKE_DOCKER_FAIL_ON", "")
if verb and argv[:1] == [verb]:
    sys.stderr.write("fixture: docker %s refused\\n" % verb)
    sys.exit(int(os.environ.get("FAKE_DOCKER_FAIL_RC", "1")))
sys.exit(0)
"""

# What the twin needs on PATH before it can even source common.sh: `dirname` for its own SCRIPT_DIR, and `uname` because common.sh calls detect_os and detect_arch at SOURCE time (common.sh:64, :100). Only the no-docker case curates, so only that case needs the list.
CURATED = ("dirname", "uname")


def _stub_bin(base: pathlib.Path, *, with_docker: bool = True) -> str:
    """A directory holding the fake, prepended to the real PATH.

    PREPENDED rather than curated down to a symlink farm, because both sides genuinely need the real `jq` and the real `grep`: this script scrubs `~/.docker/config.json` with jq and filters `docker images` with grep, and the port RUNS both binaries rather than reimplementing them. The safety property is therefore RESOLUTION ORDER, and it is asserted rather than assumed.

    `with_docker=False` IS THE ONE CASE THAT CANNOT PREPEND, because the real
    PATH holds a real docker on any host that can build anything here.
    """
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


def _run(subject: pathlib.Path, base: pathlib.Path, extra: dict[str, str]):
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
        # An empty value means UNSET, which is how `${VAR:-default}` is driven.
        if value == "":
            env.pop(key, None)
            extra.pop(key)
    env.update(extra)
    runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject)],
        capture_output=True,
        env=env,
        check=False,
        cwd=str(base),
        timeout=120,
    )
    calls = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
    return proc.returncode, proc.stdout, proc.stderr, calls


def _sides(name: str, *, seed=None, **extra: str):
    """Both subjects, one fixture shape, two private trees.

    `seed` is called with the case's base directory before the subject runs, so a case can plant a `~/.docker/config.json` for BOTH sides identically.
    """
    results = []
    bases = []
    with tempfile.TemporaryDirectory() as td:
        for subject in (TWIN, PORT):
            base = pathlib.Path(td) / subject.stem
            base.mkdir(parents=True)
            if seed is not None:
                seed(base)
            bases.append(base)
            results.append(_run(subject, base, dict(extra)))
        old, new = results
        for i, label in enumerate(("exit", "stdout", "stderr", "calls")):
            assert new[i] == old[i], "%s: %s diverged:\n twin: %r\n port: %r" % (
                name,
                label,
                old[i],
                new[i],
            )
        # Read the config back INSIDE the context manager; the directory is gone
        # after it.
        configs = [(b / ".docker" / "config.json") for b in bases]
        blobs = [c.read_text(encoding="utf-8") if c.is_file() else None for c in configs]
        assert blobs[0] == blobs[1], "%s: ~/.docker/config.json diverged:\n twin: %r\n port: %r" % (
            name,
            blobs[0],
            blobs[1],
        )
    return (*old, blobs[0])


# --------------------------------------------------------------------------- The controls, first: a fake that is not reached proves nothing. ---------------------------------------------------------------------------


def test_the_fake_docker_is_the_docker() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = pathlib.Path(td)
        path = _stub_bin(base)
        assert shutil.which("docker", path=path) == str(base / "bin" / "docker")
        # The two the port EXECUTES rather than reimplements must be the real ones, and must still resolve behind the stub directory.
        for real in ("jq", "grep"):
            found = shutil.which(real, path=path)
            assert found is not None, real
            assert not found.startswith(str(base)), real


def test_both_subjects_exist_where_this_file_says_they_do() -> None:
    assert TWIN.is_file(), TWIN
    assert PORT.is_file(), PORT


def test_the_twin_parses_under_bash() -> None:
    proc = subprocess.run([BASH, "-n", str(TWIN)], capture_output=True, check=False)
    assert proc.returncode == 0, proc.stderr


# ---------------------------------------------------------------------------
# The defaulting ladder, driven against bash's own `${VAR:-default}`.
# ---------------------------------------------------------------------------


def _bash_resolve(env: dict[str, str]) -> tuple[str, str, str]:
    """Lines 40-43, run by the real bash under the case's environment."""
    script = (
        'DOCKER_REGISTRY="${DOCKER_REGISTRY:-ghcr.io/rediacc}"; '
        'TAG="${TAG:-latest}"; RENET_TAG="${RENET_TAG:-$TAG}"; WEB_TAG="${WEB_TAG:-$TAG}"; '
        'printf \'%s\\n%s\\n%s\\n\' "$DOCKER_REGISTRY" "$RENET_TAG" "$WEB_TAG"'
    )
    out = subprocess.run(
        [BASH, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": os.environ.get("PATH", ""), **env},
    ).stdout.split("\n")
    return out[0], out[1], out[2]


def test_resolve_tags_agrees_with_bash_on_every_shape() -> None:
    for env in (
        {},
        {"TAG": "ci-7"},
        {"TAG": "ci-7", "RENET_TAG": "r-1"},
        {"TAG": "ci-7", "WEB_TAG": "w-1"},
        {"RENET_TAG": "r-1"},
        {"DOCKER_REGISTRY": "ghcr.io/example"},
        # THE COLON FORM: an exported EMPTY value falls back to the default rather than producing `renet:`.
        {"TAG": ""},
        {"DOCKER_REGISTRY": ""},
    ):
        assert cpi.resolve_tags(env) == _bash_resolve(env), env


# --------------------------------------------------------------------------- The differential. ---------------------------------------------------------------------------


def test_a_missing_token_is_refused_after_the_banner_and_before_docker() -> None:
    exit_code, stdout, stderr, calls, _ = _sides("no-token", GITHUB_TOKEN="")
    assert exit_code == 1
    assert calls == [], "docker was reached with no token"
    assert stderr == "✗ GITHUB_TOKEN environment variable is required\n".encode()
    # The banner is a bare `echo`, so it is on STDOUT and it prints even on the refusal path. A port that logged it would move it to stderr.
    assert stdout.decode().splitlines() == ["", "=" * 70, cpi.BANNER, "=" * 70]


def test_a_missing_actor_is_refused_the_same_way() -> None:
    exit_code, _, stderr, calls, _ = _sides("no-actor", GITHUB_ACTOR="")
    assert exit_code == 1
    assert calls == []
    assert stderr == "✗ GITHUB_ACTOR environment variable is required\n".encode()


def test_the_token_check_comes_first_when_both_are_missing() -> None:
    _, _, stderr, _, _ = _sides("neither", GITHUB_TOKEN="", GITHUB_ACTOR="")
    assert b"GITHUB_TOKEN" in stderr
    assert b"GITHUB_ACTOR" not in stderr


def test_the_happy_path_is_five_docker_calls_in_this_order() -> None:
    exit_code, stdout, stderr, calls, _ = _sides(
        "happy", FAKE_DOCKER_IMAGES="REPOSITORY:TAG\tSIZE\nghcr.io/rediacc/renet:latest\t10MB\n"
    )
    assert exit_code == 0
    assert calls == [
        "docker\tlogin\tghcr.io\t-u\t%s\t--password-stdin\tstdin='%s\\n'" % (ACTOR, TOKEN),
        "docker\tpull\t--quiet\tghcr.io/rediacc/server:latest",
        "docker\tpull\t--quiet\tghcr.io/rediacc/renet:latest",
        "docker\tlogout\tghcr.io",
        # `\\t` -- TWO CHARACTERS. bash does not interpret `\t` inside double quotes, so docker receives a backslash and a `t` and expands it itself. A real tab here is the reflex mistake, and it is what the port shipped until this case fired.
        "docker\timages\t--format\ttable {{.Repository}}:{{.Tag}}\\t{{.Size}}",
    ], calls
    text = stderr.decode()
    assert "✓ All images pulled successfully" in text
    assert "✓ Credentials cleaned - environment is now safe for debug access" in text
    # grep keeps both lines here: one matches REPOSITORY, one matches rediacc.
    out = stdout.decode().splitlines()
    assert out[-3:] == [
        "Pulled images:",
        "REPOSITORY:TAG\tSIZE",
        "ghcr.io/rediacc/renet:latest\t10MB",
    ], out


def test_the_final_grep_drops_rows_that_are_neither_rediacc_nor_the_header() -> None:
    """`grep -E "(rediacc|REPOSITORY)"` is what decides these bytes, and both
    sides run the SAME grep binary rather than one of them re-implementing it."""
    _, stdout, _, _, _ = _sides(
        "grep",
        FAKE_DOCKER_IMAGES="REPOSITORY:TAG\tSIZE\nubuntu:24.04\t80MB\nghcr.io/rediacc/renet:1\t9MB\n",
    )
    out = stdout.decode().splitlines()
    assert "ubuntu:24.04\t80MB" not in out
    assert "REPOSITORY:TAG\tSIZE" in out
    assert "ghcr.io/rediacc/renet:1\t9MB" in out


def test_no_matching_images_still_exits_zero() -> None:
    """`|| true` on the last pipeline: grep's exit 1 must not become the
    script's. A port that let it through would fail every clean runner."""
    exit_code, stdout, _, _, _ = _sides("grep-empty", FAKE_DOCKER_IMAGES="ubuntu:24.04\t80MB\n")
    assert exit_code == 0
    assert stdout.decode().splitlines()[-1] == "Pulled images:"


def test_tag_feeds_both_images_and_either_can_override_it() -> None:
    _, _, _, calls, _ = _sides("tag", TAG="ci-42")
    assert "docker\tpull\t--quiet\tghcr.io/rediacc/server:ci-42" in calls
    assert "docker\tpull\t--quiet\tghcr.io/rediacc/renet:ci-42" in calls

    _, _, _, calls, _ = _sides("tag-split", TAG="ci-42", WEB_TAG="w-9")
    assert "docker\tpull\t--quiet\tghcr.io/rediacc/server:w-9" in calls
    assert "docker\tpull\t--quiet\tghcr.io/rediacc/renet:ci-42" in calls


def test_docker_registry_moves_renet_and_not_server() -> None:
    """PRESERVED SHAPE. The header documents DOCKER_REGISTRY as "Registry URL",
    but line 54 hard-codes `ghcr.io/rediacc/server`, so this variable moves ONE
    of the two images. If that ever changes, this test goes red first."""
    _, _, _, calls, _ = _sides("registry", DOCKER_REGISTRY="ghcr.io/example")
    assert "docker\tpull\t--quiet\tghcr.io/rediacc/server:latest" in calls
    assert "docker\tpull\t--quiet\tghcr.io/example/renet:latest" in calls


def test_a_failing_login_stops_before_any_pull() -> None:
    exit_code, _, _, calls, _ = _sides("login-fails", FAKE_DOCKER_FAIL_ON="login")
    assert exit_code == 1
    assert len(calls) == 1, calls
    assert calls[0].startswith("docker\tlogin")


def test_the_subshells_exit_status_is_dockers_own() -> None:
    """`set -e` propagates the STATUS, not a canned 1. A port returning 1 for
    every failure would lose the distinction between docker's exit codes."""
    exit_code, _, _, _, _ = _sides(
        "login-rc", FAKE_DOCKER_FAIL_ON="login", FAKE_DOCKER_FAIL_RC="42"
    )
    assert exit_code == 42


def test_a_failing_pull_skips_the_credential_cleanup_on_both_sides() -> None:
    """THE HAZARD, PINNED. No `trap`, so a failed pull leaves the GHCR
    credential in `~/.docker/config.json` and the job continues into whatever
    comes next. Both sides do it; neither is allowed to quietly start being
    better than the other. Fixing it is a change to the TWIN, out of scope for a
    one-for-one port, and reported to the driver instead."""
    exit_code, stdout, stderr, calls, _ = _sides("pull-fails", FAKE_DOCKER_FAIL_ON="pull")
    assert exit_code == 1
    assert [c.split("\t")[1] for c in calls] == ["login", "pull"]
    assert b"logout" not in b"\n".join(c.encode() for c in calls)
    assert b"Credentials cleaned" not in stderr
    assert b"Pulled images:" not in stdout


def test_a_failing_logout_is_swallowed_and_the_run_still_succeeds() -> None:
    """`docker logout ghcr.io 2>/dev/null || true`, and the `2>/dev/null` half
    matters as much as the `|| true`: the complaint must not reach stderr."""
    exit_code, _, stderr, calls, _ = _sides("logout-fails", FAKE_DOCKER_FAIL_ON="logout")
    assert exit_code == 0
    assert b"fixture: docker logout refused" not in stderr
    assert [c.split("\t")[1] for c in calls] == ["login", "pull", "pull", "logout", "images"]


def test_the_ghcr_entry_is_scrubbed_out_of_the_docker_config_and_others_survive() -> None:
    """The `jq 'del(.auths["ghcr.io"])'` rewrite, compared as FILE BYTES.

    Both sides run the same jq, so this asserts the port drives it with the same filter and the same move -- and, more importantly, that it does not reach
    for `json.dumps`, which would reformat a file a human later reads.
    """

    def seed(base: pathlib.Path) -> None:
        cfg = base / ".docker"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "config.json").write_text(
            '{\n  "auths": {\n    "ghcr.io": {"auth": "fixture"},\n'
            '    "docker.io": {"auth": "keepme"}\n  }\n}\n',
            encoding="utf-8",
        )

    exit_code, _, _, _, blob = _sides("scrub", seed=seed)
    assert exit_code == 0
    assert blob is not None
    assert "ghcr.io" not in blob
    assert "keepme" in blob


def test_a_config_without_a_ghcr_entry_is_left_valid() -> None:
    def seed(base: pathlib.Path) -> None:
        cfg = base / ".docker"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "config.json").write_text('{"auths": {"docker.io": {"auth": "keepme"}}}\n', "utf-8")

    _, _, _, _, blob = _sides("scrub-noop", seed=seed)
    assert blob is not None
    assert "keepme" in blob


def test_an_unparseable_config_is_left_exactly_as_it_was() -> None:
    """`jq ... >tmp && mv tmp cfg || rm -f tmp`: a jq that fails must NOT leave
    the truncated temporary in place of the user's file. The `>` truncates the temporary BEFORE jq runs, so a port that moved unconditionally would replace
    a broken config with an empty one."""

    def seed(base: pathlib.Path) -> None:
        cfg = base / ".docker"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "config.json").write_text("this is not json at all\n", encoding="utf-8")

    exit_code, _, _, _, blob = _sides("scrub-broken", seed=seed)
    assert exit_code == 0
    assert blob == "this is not json at all\n"


def test_no_docker_config_at_all_is_not_an_error() -> None:
    exit_code, _, _, _, blob = _sides("no-config")
    assert exit_code == 0
    assert blob is None


def test_a_missing_docker_is_127_on_both_sides_with_a_named_text_divergence() -> None:
    """THE ONE NAMED DIVERGENCE. There is no `require_cmd docker` in this twin
    (unlike `docker-pull-ghcr.sh`), so bash's own `command not found` is the message, and it carries `<script>: line 49: `. Everything that a caller can act on -- the status, the words, the absence of any further work -- is
    asserted equal; only the prefix differs."""
    results = []
    with tempfile.TemporaryDirectory() as td:
        for subject in (TWIN, PORT):
            base = pathlib.Path(td) / subject.stem
            base.mkdir(parents=True)
            results.append(_run(subject, base, {"_no_docker": "1"}))
    old, new = results
    assert old[0] == new[0] == 127
    assert old[3] == new[3] == []
    old_lines = old[2].decode().splitlines()
    new_lines = new[2].decode().splitlines()
    # Both get as far as the same log_step, and both stop at the same place.
    assert old_lines[0] == new_lines[0] == "→ Authenticating with ghcr.io..."
    assert len(old_lines) == len(new_lines) == 2
    assert old_lines[1].endswith("docker: command not found")
    assert new_lines[1] == "docker: command not found"
    # The twin names a file and a line number; the port has neither to name.
    assert "line 49" in old_lines[1]
    assert old_lines[1] != new_lines[1], "the divergence this test exists for vanished"
