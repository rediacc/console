"""`rediacc_ci.docker.retag_image`, driven against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/docker/retag-image.sh` and the port over the same throwaway tree and compared exit code, stdout, stderr and the `docker` call log. The K=5 ledger `.ci/shadow/w7p6-retag-image.observations.jsonl` recorded that comparison over five distinct trees. The twin has now been deleted and every case that executed it compares
against `goldens/retag-image/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree. Each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

A RECORDING FAKE `docker` ON A SCRATCH PATH built from an explicit symlink list, so a tool nobody named is genuinely absent. Not a formality: an early probe for this port left `/usr/bin` on PATH and the real docker binary contacted `ghcr.io/token` before the twin printed a line. Nothing here can reach a registry.

THE CALL LOG IS THE EVIDENCE, and the fake's `create` prints nothing, so a port that swapped `-t <dst>` and `<src>` -- the mistake that retags the OLD image onto the new version -- would produce identical stdout, identical stderr and an identical exit code. `test_a_planted_argument_swap_is_caught_only_by_the_call_log` plants exactly that.

`--skip-if-exists` GETS FOUR CASES, NOT ONE, because it is the only branch in this directory that can silently do nothing: destination absent, digests equal, digests different, and source unreadable. The twin's own comment said an inverted version of this check "silently locks the new image out of promotion"
with the symptom appearing only in post-publish pull tests, so all four
directions are recorded.

ONE GOLDEN IS A MERGED STREAM, and it is not a duplicate of the separate-stream one. A per-stream comparison cannot see a CROSS-stream ordering divergence, and there was a real one to see: Python block-buffers stdout against a pipe while bash's `echo` wrote straight through, so without the port's `flush=True` its `echo ""` separators arrived several lines late with byte-identical
content in each stream taken alone. `the-merged-stream` records `2>&1` as a CI log really sees it, and stores the whole thing under the stdout marker with an empty stderr.

THE TWO STALENESS ALARMS THAT READ THE TWIN'S SOURCE ARE GONE, and the goldens replace them. They existed so a line number quoted by the port (`<SELF>: line 41: $2: unbound variable`) could not drift away from the statement it named while the twin was still being edited. A deleted file does not drift; what could still drift is the port's copy of those numbers, and the four
`an-unbound-*` recordings plus the two `command not found` ones pin every one of them to the byte.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.docker import retag_image as port
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
CONSTANTS = ROOT / ".ci" / "config" / "constants.sh"
TOOLCHAIN = ROOT / ".devcontainer" / "toolchain.env"
PORT_FILE = ROOT / ".ci" / "rediacc_ci" / "docker" / "retag_image.py"
BASH = shutil.which("bash") or "/bin/bash"

SLUG = "retag-image"
TWIN_REL = ".ci/scripts/docker/retag-image.sh"
PORT_REL = ".ci/rediacc_ci/docker/retag_image.py"

CALLS_MARKER = "--- calls ---\n"

# The digest answers are keyed by the TAG SUFFIX of the reference, so a case can make the destination match, differ, or be unreadable. Everything else the fake prints is constant, which is what keeps the call log the only witness to which reference was pushed where.
FAKE_DOCKER = r"""#!/usr/bin/python3
import os
import sys

argv = sys.argv[1:]
with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("docker\t" + "\t".join(argv) + "\n")

rc = int(os.environ.get("FAKE_DOCKER_RC", "0"))
verb = argv[2] if len(argv) > 2 else ""
ref = argv[3] if len(argv) > 3 else ""
is_digest_probe = "--format" in argv

if is_digest_probe:
    # `2>/dev/null || true` on the twin's side: an empty answer means "cannot
    # read", which is a DIFFERENT branch from an answer that disagrees.
    key = "FAKE_DIGEST_DST" if ref.endswith(":" + os.environ.get("FAKE_TO", "0.5.0")) \
        else "FAKE_DIGEST_SRC"
    value = os.environ.get(key, "")
    if value:
        sys.stdout.write(value + "\n")
    sys.exit(0)

if rc:
    sys.stderr.write("ERROR: failed to create manifest list: unauthorized\n")
    sys.exit(rc)
if verb == "inspect":
    sys.stdout.write("Name:      <redacted>\n")
sys.exit(0)
"""

# The variant `a-failing-latest-push` recorded: only the `:latest` create fails, so the version tag lands and `:latest` stays stale.
LATEST_ONLY_FAILS = FAKE_DOCKER.replace(
    "if rc:",
    'if rc and (":latest" in " ".join(argv) or os.environ.get("FAKE_ALL_FAIL")):',
)

# A docker that records nothing and exits 0, for the "nothing verifies the destination" recording.
SILENT_DOCKER = "#!/usr/bin/python3\nimport sys\nsys.exit(0)\n"

# `dirname` for SCRIPT_DIR in the twin and in constants.sh, `uname`/`tr` for common.sh's detection helpers, `basename` because the twin called it for the label, `python3` for the fake. Anything not listed is ABSENT.
PATH_MINIMUM = ("dirname", "basename", "uname", "tr", "python3")


def _bin(root: pathlib.Path, *, drop: str = "", docker_body: str = FAKE_DOCKER) -> str:
    stub = root / "fixture-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        if real_name == drop:
            continue
        real = shutil.which(real_name)
        assert real is not None, "%s is missing from this machine" % real_name
        link = stub / real_name
        if not link.exists():
            link.symlink_to(real)
    docker = stub / "docker"
    if drop == "docker":
        if docker.exists():
            docker.unlink()
        assert shutil.which("docker", path=str(stub)) is None, "docker leaked into the stub PATH"
    else:
        docker.write_text(docker_body, encoding="utf-8")
        docker.chmod(0o755)
    return str(stub)


def fixture(tmp_path: pathlib.Path, *, port_source: str | None = None) -> pathlib.Path:
    """A throwaway tree holding the port and the libraries the twin also read."""
    root = tmp_path / "repo"
    for rel in (
        ".ci/scripts/docker",
        ".ci/scripts/lib",
        ".ci/config",
        ".devcontainer",
        ".ci/rediacc_ci/docker",
    ):
        (root / rel).mkdir(parents=True, exist_ok=True)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / COMMON.name)
    shutil.copy2(CONSTANTS, root / ".ci" / "config" / CONSTANTS.name)
    shutil.copy2(TOOLCHAIN, root / ".devcontainer" / TOOLCHAIN.name)
    target = root / PORT_REL
    if port_source is None:
        shutil.copy2(PORT_FILE, target)
    else:
        target.write_text(port_source, encoding="utf-8")
    return root


def _run(
    root: pathlib.Path,
    side: str,
    args: list[str],
    *,
    drop: str = "",
    docker_body: str = FAKE_DOCKER,
    subject: pathlib.Path | None = None,
    merged: bool = False,
    **extra: str,
):
    call_log = root / ("%s-calls.log" % side)
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(root, drop=drop, docker_body=docker_body),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
    }
    env.update(extra)
    if subject is None:
        subject = root / PORT_REL
    argv = [BASH if subject.suffix == ".sh" else sys.executable, str(subject)]
    proc = subprocess.run(
        [*argv, *args],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if merged else subprocess.PIPE,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )
    return proc, call_log.read_text(encoding="utf-8")


def mask(text: str, root: pathlib.Path) -> str:
    """`$0` -- the one thing a bash child and a python one never agreed on -- and the fixture root."""
    masked = text.replace(TWIN_REL, "<SELF>").replace(PORT_REL, "<SELF>")
    return frozen.mask_root(masked, root)


ONE = ["--image", "api", "--from", "a", "--to", "b"]
SKIP = [*ONE, "--skip-if-exists"]

CASE_KW: dict[str, tuple[list[str], dict[str, object]]] = {
    "help": (["--help"], {}),
    "no-from": (["--image", "api"], {}),
    "from-beats-the-all-exclusivity": (["--all", "--image", "api"], {}),
    "from-beats-the-image-exclusivity": (["--image", "a", "--image-path", "x/b"], {}),
    "to-beats-the-all-exclusivity": (["--all", "--image", "api", "--from", "ci-1"], {}),
    "no-to": (["--image", "api", "--from", "a"], {}),
    "image-and-image-path-together": (
        ["--image", "a", "--image-path", "x/b", "--from", "1", "--to", "2"],
        {},
    ),
    "all-with-a-named-target": (["--all", "--image", "a", "--from", "1", "--to", "2"], {}),
    "no-target-at-all": (["--from", "1", "--to", "2"], {}),
    "an-unknown-option": (["--bogus"], {}),
    "an-unbound-image": (["--image"], {}),
    "an-unbound-image-path": (["--image-path"], {}),
    "an-unbound-from": (["--from"], {}),
    "an-unbound-to": (["--to"], {}),
    "all-with-push-latest": (["--all", "--from", "ci-1", "--to", "0.5.0", "--push-latest"], {}),
    "a-single-image": (ONE, {}),
    "an-image-path": (["--image-path", "ghcr.io/acme/server", "--from", "a", "--to", "b"], {}),
    "an-image-with-a-slash": (["--image", "ghcr.io/acme/server", "--from", "a", "--to", "b"], {}),
    "an-image-path-without-a-slash": (["--image-path", "server", "--from", "a", "--to", "b"], {}),
    "a-registry-override": (ONE, {"PUBLISH_DOCKER_REGISTRY": "ghcr.io/other"}),
    "a-failing-create": (["--all", "--from", "a", "--to", "b"], {"FAKE_DOCKER_RC": "7"}),
    "a-failing-latest-push": (
        [*ONE, "--push-latest"],
        {"docker_body": LATEST_ONLY_FAILS, "FAKE_DOCKER_RC": "7"},
    ),
    "a-missing-docker": (ONE, {"drop": "docker"}),
    "a-dry-run": ([*ONE, "--dry-run", "--push-latest"], {}),
    "a-dry-run-that-cannot-inspect": ([*ONE, "--dry-run"], {"FAKE_DOCKER_RC": "4"}),
    "a-dry-run-with-a-missing-docker": ([*ONE, "--dry-run"], {"drop": "docker"}),
    "skip-if-exists-with-no-destination": (SKIP, {"FAKE_TO": "b"}),
    "skip-if-exists-with-equal-digests": (
        SKIP,
        {"FAKE_TO": "b", "FAKE_DIGEST_DST": "sha256:same", "FAKE_DIGEST_SRC": "sha256:same"},
    ),
    "skip-if-exists-with-different-digests": (
        SKIP,
        {"FAKE_TO": "b", "FAKE_DIGEST_DST": "sha256:stale", "FAKE_DIGEST_SRC": "sha256:fresh"},
    ),
    "skip-if-exists-with-an-unreadable-source": (
        SKIP,
        {"FAKE_TO": "b", "FAKE_DIGEST_DST": "sha256:stale"},
    ),
    "a-silent-docker": (["--all", "--from", "a", "--to", "b"], {"docker_body": SILENT_DOCKER}),
    "the-merged-stream": (
        ["--all", "--from", "ci-1", "--to", "0.5.0", "--push-latest"],
        {"merged": True},
    ),
}

CASES = tuple(CASE_KW)

MERGED_CASE = "the-merged-stream"


def render(proc, calls: str, root: pathlib.Path, *, merged: bool = False) -> str:
    body = frozen.render(
        proc.returncode,
        mask(proc.stdout, root),
        "" if merged else mask(proc.stderr, root),
    )
    return body + CALLS_MARKER + mask(calls, root)


def recorded(name: str) -> tuple[int, str, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    streams, calls = rest.split(CALLS_MARKER, 1)
    stdout, stderr = streams.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, calls


def drive(
    tmp_path: pathlib.Path, name: str, *, port_source: str | None = None
) -> tuple[int, str, str, str]:
    args, kw = CASE_KW[name]
    root = fixture(tmp_path, port_source=port_source)
    proc, calls = _run(root, "new", args, **kw)  # type: ignore[arg-type]
    merged = bool(kw.get("merged"))
    return (
        proc.returncode,
        mask(proc.stdout, root),
        "" if merged else mask(proc.stderr, root),
        mask(calls, root),
    )


def compare(
    tmp_path: pathlib.Path, name: str, *, port_source: str | None = None
) -> tuple[int, str, str, str]:
    want = recorded(name)
    got = drive(tmp_path, name, port_source=port_source)
    assert got[0] == want[0], "%s: the twin exited %d, the port %d" % (name, want[0], got[0])
    assert got[1] == want[1], "%s: stdout diverged from the recorded bytes" % name
    assert got[2] == want[2], "%s: stderr diverged from the recorded bytes" % name
    assert got[3] == want[3], "%s: the docker call log diverged:\n%s---\n%s" % (
        name,
        want[3],
        got[3],
    )
    return got


@pytest.mark.parametrize("name", CASES)
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- Argument handling, in the twin's validation ORDER ---------------------------------------------------------------------------


def test_help_is_stdout_and_names_the_images() -> None:
    returncode, stdout, stderr, calls = recorded("help")
    assert returncode == 0
    assert stderr == ""
    assert "Available images: renet rdc" in stdout
    assert calls == ""


def test_from_is_demanded_first() -> None:
    returncode, _, stderr, _ = recorded("no-from")
    assert returncode == 1
    assert stderr == "✗ --from is required\n"


def test_from_is_demanded_before_the_exclusivity_checks() -> None:
    """ORDER IS OBSERVABLE. `--all --image api` with no tags reported the missing `--from`, not the mutual exclusion, and a port that validated targets first would print a different message with the same exit code."""
    assert recorded("from-beats-the-all-exclusivity")[2] == "✗ --from is required\n"


def test_the_missing_from_beats_the_image_exclusivity_too() -> None:
    """THE CASE THE PREVIOUS TEST DOES NOT COVER, and its absence was measured rather than guessed: a plant that moved the `--image`/`--image-path` exclusivity check ABOVE the `--from` check left all 36 tests green, because every existing case either supplied `--from` or paired `--all` with `--image` rather than the two target flags with each other. A control that does not fire is
    a claim about the control, so this is the missing arm.
    """
    returncode, _, stderr, _ = recorded("from-beats-the-image-exclusivity")
    assert returncode == 1
    assert stderr == "✗ --from is required\n", stderr


def test_the_missing_to_also_beats_the_all_exclusivity() -> None:
    """The same gap one rung down: `--to` was checked before `--all` versus a named target, so this pairing reports the missing `--to`."""
    assert recorded("to-beats-the-all-exclusivity")[2] == "✗ --to is required\n"


def test_to_is_demanded_second() -> None:
    assert recorded("no-to")[2] == "✗ --to is required\n"


def test_image_and_image_path_are_mutually_exclusive() -> None:
    assert recorded("image-and-image-path-together")[2] == (
        "✗ --image and --image-path are mutually exclusive\n"
    )


def test_all_is_mutually_exclusive_with_a_named_target() -> None:
    assert recorded("all-with-a-named-target")[2] == (
        "✗ --all is mutually exclusive with --image / --image-path\n"
    )


def test_no_target_at_all_refuses() -> None:
    assert recorded("no-target-at-all")[2] == "✗ --image, --image-path, or --all required\n"


def test_an_unknown_option_refuses() -> None:
    assert recorded("an-unknown-option")[2] == "✗ Unknown option: --bogus\n"


UNBOUND_CASES = {
    "--image": "an-unbound-image",
    "--image-path": "an-unbound-image-path",
    "--from": "an-unbound-from",
    "--to": "an-unbound-to",
}


def test_each_value_flag_dies_the_way_set_u_dies() -> None:
    """THE LINE NUMBERS, PINNED BY RECORDING. `set -u` made bash name the twin's own file and line, and the port reproduces both from `UNBOUND_LINES`. The four recordings are what stops that table drifting now that the file they describe is gone."""
    assert set(UNBOUND_CASES) == set(port.UNBOUND_LINES), "the flag table moved"
    for flag, name in UNBOUND_CASES.items():
        returncode, _, stderr, _ = recorded(name)
        assert returncode == 1
        assert stderr.endswith(
            "<SELF>: line %d: $2: unbound variable\n" % port.UNBOUND_LINES[flag]
        ), (
            flag,
            stderr,
        )


# --------------------------------------------------------------------------- The real retag paths ---------------------------------------------------------------------------


def test_all_retags_both_images_and_pushes_latest() -> None:
    returncode, _, stderr, calls = recorded("all-with-push-latest")
    assert returncode == 0

    head = "docker\tbuildx\timagetools\tcreate\t-t\t"
    assert calls.splitlines() == [
        head + "ghcr.io/rediacc/renet:0.5.0\tghcr.io/rediacc/renet:ci-1",
        head + "ghcr.io/rediacc/renet:latest\tghcr.io/rediacc/renet:ci-1",
        head + "ghcr.io/rediacc/rdc:0.5.0\tghcr.io/rediacc/rdc:ci-1",
        head + "ghcr.io/rediacc/rdc:latest\tghcr.io/rediacc/rdc:ci-1",
    ], calls
    # THE NEGATIVE HALF: the source is the CI tag, never the destination.
    assert ":0.5.0\tghcr.io/rediacc/renet:0.5.0" not in calls
    assert "✓ Re-tag summary: 2 succeeded, 0 failed" in stderr


def test_a_single_image_takes_the_registry_prefix() -> None:
    _, _, stderr, calls = recorded("a-single-image")
    assert calls.splitlines() == [
        "docker\tbuildx\timagetools\tcreate\t-t\tghcr.io/rediacc/api:b\tghcr.io/rediacc/api:a"
    ]
    assert "→ Re-tagging api: a -> b" in stderr


def test_an_image_path_bypasses_the_registry_and_shortens_the_label() -> None:
    _, _, stderr, calls = recorded("an-image-path")
    assert "ghcr.io/rediacc" not in calls, calls
    # `basename` for the LABEL, full path for the reference.
    assert "→ Re-tagging server: a -> b" in stderr
    assert "✓ Re-tagged server successfully" in stderr


def test_an_image_with_a_slash_is_treated_as_a_full_path() -> None:
    """THE UNDOCUMENTED HALF: `--image` did not always mean "relative". The twin decided by looking for a `/` inside `retag_image`, so this reaches the same code path as `--image-path`."""
    assert "ghcr.io/rediacc" not in recorded("an-image-with-a-slash")[3]


def test_an_image_path_without_a_slash_is_treated_as_relative() -> None:
    """And the OTHER half: `--image-path` did not always bypass the registry."""
    assert "ghcr.io/rediacc/server:b" in recorded("an-image-path-without-a-slash")[3]


def test_the_registry_override_reaches_the_argv() -> None:
    assert "ghcr.io/other/api:b" in recorded("a-registry-override")[3]


def test_a_failing_create_counts_as_failed_and_keeps_going() -> None:
    returncode, _, stderr, calls = recorded("a-failing-create")
    assert returncode == 1
    # BOTH images are attempted; the loop did not stop at the first failure.
    assert len(calls.splitlines()) == 2, calls
    assert "✓ Re-tag summary: 0 succeeded, 2 failed" in stderr


def test_a_failing_latest_push_aborts_that_image() -> None:
    """`--push-latest` failing returned 1 BEFORE the `Re-tagged ... successfully` line, so the version tag is live and `:latest` is stale with nothing saying so beyond the summary count."""
    returncode, _, stderr, calls = recorded("a-failing-latest-push")
    assert returncode == 1
    assert len(calls.splitlines()) == 2, calls
    assert "✗ Failed to re-tag ghcr.io/rediacc/api:a -> ghcr.io/rediacc/api:latest" in stderr
    assert "Re-tagged api successfully" not in stderr


def test_a_missing_docker_is_bashs_own_command_not_found() -> None:
    returncode, _, stderr, _ = recorded("a-missing-docker")
    assert returncode == 1
    assert any(
        line.endswith("<SELF>: line %d: docker: command not found" % port.RETAG_CREATE_LINE)
        for line in stderr.splitlines()
    ), stderr


# --------------------------------------------------------------------------- Dry run ---------------------------------------------------------------------------


def test_dry_run_inspects_the_source_and_pushes_nothing() -> None:
    returncode, stdout, stderr, calls = recorded("a-dry-run")
    assert returncode == 0
    assert calls.splitlines() == ["docker\tbuildx\timagetools\tinspect\tghcr.io/rediacc/api:a"], (
        calls
    )
    assert "✓ [DRY-RUN] Would also tag: ghcr.io/rediacc/api:latest" in stderr
    # The probe's own stdout is DISCARDED by `>/dev/null`, so nothing leaks.
    assert stdout == "\n", repr(stdout)


def test_dry_run_fails_when_the_source_cannot_be_inspected() -> None:
    returncode, _, stderr, _ = recorded("a-dry-run-that-cannot-inspect")
    assert returncode == 1
    assert "✗ [DRY-RUN] Failed to inspect source image: ghcr.io/rediacc/api:a" in stderr


def test_dry_run_with_a_missing_docker_names_the_probe_line() -> None:
    stderr = recorded("a-dry-run-with-a-missing-docker")[2]
    assert any(
        line.endswith("<SELF>: line %d: docker: command not found" % port.DRY_RUN_INSPECT_LINE)
        for line in stderr.splitlines()
    ), stderr


# --------------------------------------------------------------------------- --skip-if-exists: all four directions ---------------------------------------------------------------------------


def test_skip_if_exists_with_no_destination_falls_through_to_the_retag() -> None:
    returncode, _, _, calls = recorded("skip-if-exists-with-no-destination")
    assert returncode == 0
    # ONE probe (the destination), then the retag. The source was never probed, because the twin short-circuited on an empty destination digest.
    assert len(calls.splitlines()) == 2, calls
    assert "\tcreate\t-t\tghcr.io/rediacc/api:b\t" in calls


def test_skip_if_exists_skips_when_the_digests_match() -> None:
    returncode, _, stderr, calls = recorded("skip-if-exists-with-equal-digests")
    assert returncode == 0
    assert "\tcreate\t" not in calls, "an idempotent retry still pushed"
    assert (
        "✓ Destination matches source digest, skipping: ghcr.io/rediacc/api:b (sha256:same)"
        in stderr
    )


def test_skip_if_exists_retags_when_the_digests_differ() -> None:
    """THE CASE THE TWIN'S COMMENT WAS ABOUT: a stale destination tag from a previous failed release at the same version must NOT lock the new image out."""
    returncode, _, stderr, calls = recorded("skip-if-exists-with-different-digests")
    assert returncode == 0
    assert "\tcreate\t" in calls, "a stale destination was left in place"
    assert (
        "✓ Destination exists but digest differs (dst=sha256:stale src=sha256:fresh), "
        "retagging: ghcr.io/rediacc/api:b" in stderr
    )


def test_skip_if_exists_retags_when_the_source_cannot_be_read() -> None:
    """`${src_digest:-unknown}`: an unreadable source fell THROUGH rather than
    skipping, and said `unknown` rather than inventing a digest.
    """
    _, _, stderr, calls = recorded("skip-if-exists-with-an-unreadable-source")
    assert "src=unknown" in stderr, stderr
    assert "\tcreate\t" in calls


def test_the_digest_probe_still_asks_for_the_twins_format() -> None:
    """The `--format` template, recorded rather than read out of a deleted file."""
    calls = recorded("skip-if-exists-with-equal-digests")[3]
    assert port.DIGEST_FORMAT in calls, port.DIGEST_FORMAT


# --------------------------------------------------------------------------- Defects of the twin, pinned rather than fixed ---------------------------------------------------------------------------


def test_defect_the_failing_summary_is_still_a_green_tick() -> None:
    """`log_info` on a summary that said `0 succeeded, 2 failed`, so the last line of a totally failed run carries a ✓. `cleanup_staging`, one directory over, uses `log_error` for the same situation."""
    returncode, _, stderr, _ = recorded("a-failing-create")
    assert returncode == 1
    assert stderr.splitlines()[-1] == "✓ Re-tag summary: 0 succeeded, 2 failed"


def test_defect_nothing_verifies_the_destination_after_the_push() -> None:
    """A docker that records nothing and exits 0 produced a clean promotion report. That is the twin's behaviour and the port reproduces it."""
    returncode, _, stderr, calls = recorded("a-silent-docker")
    assert returncode == 0
    assert "✓ Re-tag summary: 2 succeeded, 0 failed" in stderr
    assert calls == "", "the silent fake recorded a call; the case is not what it says"


def test_the_merged_stream_keeps_the_twins_line_order() -> None:
    """THE CROSS-STREAM ORDERING, which no per-stream comparison can see. See the module docstring for the buffering divergence this exists to catch."""
    returncode, merged, stderr, _ = recorded(MERGED_CASE)
    assert returncode == 0
    assert stderr == "", "the merged recording put bytes under the stderr marker"
    # NON-TRIVIAL BY CONSTRUCTION: a run with nothing on stdout would pass this
    # for free, so the case is one that writes to BOTH streams.
    assert merged.count("\n") >= 8, merged


# --------------------------------------------------------------------------- Pure helpers ---------------------------------------------------------------------------


def test_basename_matches_bash_on_trailing_slashes() -> None:
    """`os.path.basename` is NOT bash's basename, and the difference would print an empty label. Checked against the real tool rather than assumed."""
    real = shutil.which("basename")
    assert real is not None, "basename is missing from this machine"
    for candidate in ("a/b", "a/b/", "a/b//", "/", "//", "ghcr.io/acme/server", "x"):
        proc = subprocess.run([real, candidate], capture_output=True, text=True, check=False)
        assert port._basename(candidate) == proc.stdout.rstrip("\n"), candidate


def test_resolve_splits_on_the_slash(monkeypatch) -> None:
    monkeypatch.delenv("PUBLISH_DOCKER_REGISTRY", raising=False)
    assert port.resolve("renet") == ("ghcr.io/rediacc/renet", "renet")
    assert port.resolve("ghcr.io/acme/server") == ("ghcr.io/acme/server", "server")


def test_validate_raises_in_the_twins_order() -> None:
    opts = port.Options()
    opts.retag_all = True
    opts.image_name = "api"
    with pytest.raises(port.Refusal, match=r"^--from is required$"):
        port.validate(opts)


def test_the_registry_default_is_taken_on_unset_and_on_empty(monkeypatch) -> None:
    monkeypatch.delenv("PUBLISH_DOCKER_REGISTRY", raising=False)
    assert port.registry() == "ghcr.io/rediacc"
    monkeypatch.setenv("PUBLISH_DOCKER_REGISTRY", "")
    assert port.registry() == "ghcr.io/rediacc"


def test_dry_run_is_the_string_true_and_nothing_else(monkeypatch) -> None:
    monkeypatch.setenv("DRY_RUN", "yes")
    assert port.dry_run_default() == "yes"


def test_the_constants_are_still_constants_shs() -> None:
    """`constants.sh` is NOT a twin and is not going anywhere: it is the shared source of the image list and the registry default, so drift between it and the port's copy is still a live risk."""
    import re  # noqa: PLC0415 -- one alarm, scoped to this case

    text = CONSTANTS.read_text(encoding="utf-8")
    images = re.search(r"^readonly PUBLISH_IMAGES=\((.*)\)$", text, re.MULTILINE)
    assert images is not None, "PUBLISH_IMAGES is no longer a one-line array in constants.sh"
    assert tuple(images.group(1).replace('"', "").split()) == port.PUBLISH_IMAGES
    registry = re.search(
        r'^PUBLISH_DOCKER_REGISTRY="\$\{PUBLISH_DOCKER_REGISTRY:-([^}]*)\}"$', text, re.MULTILINE
    )
    assert registry is not None, "the registry default moved in constants.sh"
    assert registry.group(1) == port.REGISTRY_DEFAULT


# --------------------------------------------------------------------------- The controls: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_argument_swap_is_caught_only_by_the_call_log(tmp_path: pathlib.Path) -> None:
    """PROVE THE GOLDENS CAN FIRE, AND WHICH SECTION FIRES.

    The plant swaps `-t <dst>` and `<src>`, which retags the release version BACKWARDS onto the CI tag. Every printed byte and the exit code are unchanged by it, so this also shows that a streams-only recording would have blessed the defective port.
    """
    source = PORT_FILE.read_text(encoding="utf-8")
    plant = source.replace(
        'if _docker(["buildx", "imagetools", "create", "-t", dst, src], '
        "line=RETAG_CREATE_LINE) != 0:",
        'if _docker(["buildx", "imagetools", "create", "-t", src, dst], '
        "line=RETAG_CREATE_LINE) != 0:",
    )
    assert plant != source, "the plant did not apply; the control is broken, not the gate"

    want = recorded("a-single-image")
    got = drive(tmp_path / "bad", "a-single-image", port_source=plant)
    assert got[0] == want[0], "the plant changed the exit code; wrong plant"
    assert got[1] == want[1], "the plant changed stdout; wrong plant"
    assert got[2] == want[2], "the plant changed stderr; wrong plant"
    assert got[3] != want[3], "THE CALL LOG DID NOT SEE THE SWAP: this gate cannot fail"
    assert "-t\tghcr.io/rediacc/api:a\tghcr.io/rediacc/api:b" in got[3]

    compare(tmp_path / "good", "a-single-image")
    assert PORT_FILE.read_text(encoding="utf-8") == source


def test_a_planted_inversion_of_the_skip_check_is_caught(tmp_path: pathlib.Path) -> None:
    """THE NEW CONTROL ON THE GOLDENS, planted on the comparison the twin's own comment warned about.

    Skipping when the digests DIFFER, rather than when they match, is the inversion that "silently locks the new image out of promotion": a stale destination left over from a failed release at the same version survives, and the run still exits 0. Two recordings see it at once -- the different-digest case, whose recorded call log holds a `create` the mutant never makes, and the
    equal-digest case, which the mutant pushes instead of skipping. The mutation is written to a throwaway copy; the tracked port is never touched.
    """
    source = PORT_FILE.read_text(encoding="utf-8")
    anchor = "            if src_digest and dst_digest == src_digest:\n"
    assert source.count(anchor) == 1, "the plant's anchor moved"
    plant = source.replace(anchor, "            if src_digest and dst_digest != src_digest:\n")

    for name in (
        "skip-if-exists-with-different-digests",
        "skip-if-exists-with-equal-digests",
    ):
        with pytest.raises(AssertionError):
            compare(tmp_path / ("bad-" + name[-6:]), name, port_source=plant)
        compare(tmp_path / ("good-" + name[-6:]), name)
    assert PORT_FILE.read_text(encoding="utf-8") == source
