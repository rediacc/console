"""Differential: `rediacc_ci.docker.retag_image` against its twin `.ci/scripts/docker/retag-image.sh`.

A RECORDING FAKE `docker` ON A SCRATCH PATH built from an explicit symlink list, so a tool nobody named is genuinely absent. Not a formality: an early probe for this port left `/usr/bin` on PATH and the real docker binary contacted `ghcr.io/token` before the twin printed a line. Nothing here can reach a registry.

THE CALL LOG IS THE EVIDENCE, and the fake's `create` prints nothing, so a port that swapped `-t <dst>` and `<src>` -- the mistake that retags the OLD image onto the new version -- would produce identical stdout, identical stderr and an identical exit code. `test_planted_defect_is_caught_only_by_the_call_log` plants exactly that.

`--skip-if-exists` GETS FOUR CASES, NOT ONE, because it is the only branch in this directory that can silently do nothing: destination absent, digests equal, digests different, and source unreadable. The twin's own comment says an inverted version of this check "silently locks the new image out of promotion"
with the symptom appearing only in post-publish pull tests, so all four
directions are driven.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.docker import retag_image as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "docker" / "retag-image.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
CONSTANTS = ROOT / ".ci" / "config" / "constants.sh"
TOOLCHAIN = ROOT / ".devcontainer" / "toolchain.env"
PORT_FILE = ROOT / ".ci" / "rediacc_ci" / "docker" / "retag_image.py"
BASH = shutil.which("bash") or "/bin/bash"

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

# `dirname` for SCRIPT_DIR in the twin and in constants.sh, `uname`/`tr` for common.sh's detection helpers, `basename` because the twin calls it for the label, `python3` for the fake. Anything not listed is ABSENT.
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


def fixture(tmp_path: pathlib.Path) -> pathlib.Path:
    """A throwaway tree holding both implementations and the twin's libraries."""
    root = tmp_path / "repo"
    for rel in (
        ".ci/scripts/docker",
        ".ci/scripts/lib",
        ".ci/config",
        ".devcontainer",
        ".ci/rediacc_ci/docker",
    ):
        (root / rel).mkdir(parents=True, exist_ok=True)
    shutil.copy2(TWIN, root / ".ci" / "scripts" / "docker" / TWIN.name)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / COMMON.name)
    shutil.copy2(CONSTANTS, root / ".ci" / "config" / CONSTANTS.name)
    shutil.copy2(TOOLCHAIN, root / ".devcontainer" / TOOLCHAIN.name)
    shutil.copy2(PORT_FILE, root / ".ci" / "rediacc_ci" / "docker" / PORT_FILE.name)
    return root


def _run(
    root: pathlib.Path,
    side: str,
    args: list[str],
    *,
    drop: str = "",
    docker_body: str = FAKE_DOCKER,
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
    if side == "old":
        argv = [BASH, str(root / ".ci" / "scripts" / "docker" / TWIN.name)]
    else:
        argv = [sys.executable, str(root / ".ci" / "rediacc_ci" / "docker" / PORT_FILE.name)]
    proc = subprocess.run(
        [*argv, *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )
    return proc, call_log.read_text(encoding="utf-8")


def run_both(tmp_path: pathlib.Path, args: list[str] | None = None, **kw):
    root = fixture(tmp_path)
    old, old_calls = _run(root, "old", args or [], **kw)
    new, new_calls = _run(root, "new", args or [], **kw)
    return old, new, old_calls, new_calls


def _mask(text: str) -> str:
    """`$0`, the one thing that cannot agree between the two sides."""
    masked = text.replace(".ci/scripts/docker/" + TWIN.name, "<SELF>")
    return masked.replace(".ci/rediacc_ci/docker/" + PORT_FILE.name, "<SELF>")


def _agree(old, new, label: str, old_calls: str = "", new_calls: str = "") -> None:
    """The three streams SEPARATELY, plus the call log. Never `2>&1`."""
    assert new.returncode == old.returncode, (
        "%s: exit diverged: %r vs %r\nold stderr: %r\nnew stderr: %r"
        % (label, old.returncode, new.returncode, old.stderr, new.stderr)
    )
    assert _mask(new.stdout) == _mask(old.stdout), "%s: stdout diverged:\n%r\n%r" % (
        label,
        old.stdout,
        new.stdout,
    )
    assert _mask(new.stderr) == _mask(old.stderr), "%s: stderr diverged:\n%r\n%r" % (
        label,
        old.stderr,
        new.stderr,
    )
    assert new_calls == old_calls, "%s: call log diverged:\n%s\n---\n%s" % (
        label,
        old_calls,
        new_calls,
    )


# --------------------------------------------------------------------------- Argument handling, in the twin's validation ORDER ---------------------------------------------------------------------------


def test_help_is_stdout_and_names_the_images(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--help"])
    _agree(old, new, "help", old_calls, new_calls)
    assert old.returncode == 0
    assert old.stderr == ""
    assert "Available images: renet rdc" in old.stdout
    assert old_calls == ""


def test_from_is_demanded_first(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--image", "api"])
    _agree(old, new, "no-from", old_calls, new_calls)
    assert old.returncode == 1
    assert old.stderr == "✗ --from is required\n"


def test_from_is_demanded_before_the_exclusivity_checks(tmp_path) -> None:
    """ORDER IS OBSERVABLE. `--all --image api` with no tags reports the missing `--from`, not the mutual exclusion, and a port that validated targets first would print a different message with the same exit code."""
    old, new, old_calls, new_calls = run_both(tmp_path, ["--all", "--image", "api"])
    _agree(old, new, "order", old_calls, new_calls)
    assert old.stderr == "✗ --from is required\n"


def test_the_missing_from_beats_the_image_exclusivity_too(tmp_path) -> None:
    """THE CASE THE PREVIOUS TEST DOES NOT COVER, and its absence was measured rather than guessed: a plant that moved the `--image`/`--image-path` exclusivity check ABOVE the `--from` check left all 36 tests green, because every existing case either supplied `--from` or paired `--all` with `--image` rather than the two target flags with each other. A control that does not fire is
    a claim about the control, so this is the missing arm.
    """
    old, new, old_calls, new_calls = run_both(tmp_path, ["--image", "a", "--image-path", "x/b"])
    _agree(old, new, "order-2", old_calls, new_calls)
    assert old.returncode == 1
    assert old.stderr == "✗ --from is required\n", old.stderr


def test_the_missing_to_also_beats_the_all_exclusivity(tmp_path) -> None:
    """The same gap one rung down: `--to` is checked before `--all` versus a named target, so this pairing reports the missing `--to`."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--all", "--image", "api", "--from", "ci-1"]
    )
    _agree(old, new, "order-3", old_calls, new_calls)
    assert old.stderr == "✗ --to is required\n", old.stderr


def test_to_is_demanded_second(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--image", "api", "--from", "a"])
    _agree(old, new, "no-to", old_calls, new_calls)
    assert old.stderr == "✗ --to is required\n"


def test_image_and_image_path_are_mutually_exclusive(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--image", "a", "--image-path", "x/b", "--from", "1", "--to", "2"]
    )
    _agree(old, new, "both", old_calls, new_calls)
    assert old.stderr == "✗ --image and --image-path are mutually exclusive\n"


def test_all_is_mutually_exclusive_with_a_named_target(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--all", "--image", "a", "--from", "1", "--to", "2"]
    )
    _agree(old, new, "all+image", old_calls, new_calls)
    assert old.stderr == "✗ --all is mutually exclusive with --image / --image-path\n"


def test_no_target_at_all_refuses(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--from", "1", "--to", "2"])
    _agree(old, new, "no-target", old_calls, new_calls)
    assert old.stderr == "✗ --image, --image-path, or --all required\n"


def test_an_unknown_option_refuses(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--bogus"])
    _agree(old, new, "bogus", old_calls, new_calls)
    assert old.stderr == "✗ Unknown option: --bogus\n"


def test_each_value_flag_dies_the_way_set_u_dies(tmp_path) -> None:
    for flag, line in port.UNBOUND_LINES.items():
        old, new, old_calls, new_calls = run_both(tmp_path, [flag])
        _agree(old, new, "unbound " + flag, old_calls, new_calls)
        assert old.returncode == 1
        assert _mask(old.stderr).endswith("<SELF>: line %d: $2: unbound variable\n" % line), (
            flag,
            old.stderr,
        )


# --------------------------------------------------------------------------- The real retag paths ---------------------------------------------------------------------------


def test_all_retags_both_images_and_pushes_latest(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--all", "--from", "ci-1", "--to", "0.5.0", "--push-latest"]
    )
    _agree(old, new, "all", old_calls, new_calls)
    assert old.returncode == 0

    head = "docker\tbuildx\timagetools\tcreate\t-t\t"
    assert old_calls.splitlines() == [
        head + "ghcr.io/rediacc/renet:0.5.0\tghcr.io/rediacc/renet:ci-1",
        head + "ghcr.io/rediacc/renet:latest\tghcr.io/rediacc/renet:ci-1",
        head + "ghcr.io/rediacc/rdc:0.5.0\tghcr.io/rediacc/rdc:ci-1",
        head + "ghcr.io/rediacc/rdc:latest\tghcr.io/rediacc/rdc:ci-1",
    ], old_calls
    # THE NEGATIVE HALF: the source is the CI tag, never the destination.
    assert ":0.5.0\tghcr.io/rediacc/renet:0.5.0" not in old_calls
    assert "✓ Re-tag summary: 2 succeeded, 0 failed" in old.stderr


def test_a_single_image_takes_the_registry_prefix(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--image", "api", "--from", "a", "--to", "b"]
    )
    _agree(old, new, "one", old_calls, new_calls)
    assert old_calls.splitlines() == [
        "docker\tbuildx\timagetools\tcreate\t-t\tghcr.io/rediacc/api:b\tghcr.io/rediacc/api:a"
    ]
    assert "→ Re-tagging api: a -> b" in old.stderr


def test_an_image_path_bypasses_the_registry_and_shortens_the_label(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--image-path", "ghcr.io/acme/server", "--from", "a", "--to", "b"]
    )
    _agree(old, new, "image-path", old_calls, new_calls)
    assert "ghcr.io/rediacc" not in old_calls, old_calls
    # `basename` for the LABEL, full path for the reference.
    assert "→ Re-tagging server: a -> b" in old.stderr
    assert "✓ Re-tagged server successfully" in old.stderr


def test_an_image_with_a_slash_is_treated_as_a_full_path(tmp_path) -> None:
    """THE UNDOCUMENTED HALF: `--image` does not always mean "relative". The twin decides by looking for a `/` inside `retag_image`, so this reaches the same code path as `--image-path`."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--image", "ghcr.io/acme/server", "--from", "a", "--to", "b"]
    )
    _agree(old, new, "slashy-image", old_calls, new_calls)
    assert "ghcr.io/rediacc" not in old_calls, old_calls


def test_an_image_path_without_a_slash_is_treated_as_relative(tmp_path) -> None:
    """And the OTHER half: `--image-path` does not always bypass the registry."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--image-path", "server", "--from", "a", "--to", "b"]
    )
    _agree(old, new, "bare-image-path", old_calls, new_calls)
    assert "ghcr.io/rediacc/server:b" in old_calls, old_calls


def test_the_registry_override_reaches_the_argv(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--image", "api", "--from", "a", "--to", "b"],
        PUBLISH_DOCKER_REGISTRY="ghcr.io/other",
    )
    _agree(old, new, "registry-override", old_calls, new_calls)
    assert "ghcr.io/other/api:b" in old_calls, old_calls


def test_a_failing_create_counts_as_failed_and_keeps_going(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--all", "--from", "a", "--to", "b"], FAKE_DOCKER_RC="7"
    )
    _agree(old, new, "create-fails", old_calls, new_calls)
    assert old.returncode == 1
    # BOTH images are attempted; the loop does not stop at the first failure.
    assert len(old_calls.splitlines()) == 2, old_calls
    assert "✓ Re-tag summary: 0 succeeded, 2 failed" in old.stderr


def test_a_failing_latest_push_aborts_that_image(tmp_path) -> None:
    """`--push-latest` failing returns 1 BEFORE the `Re-tagged ... successfully` line, so the version tag is live and `:latest` is stale with nothing saying so beyond the summary count."""
    body = FAKE_DOCKER.replace(
        "if rc:",
        'if rc and (":latest" in " ".join(argv) or os.environ.get("FAKE_ALL_FAIL")):',
    )
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--image", "api", "--from", "a", "--to", "b", "--push-latest"],
        docker_body=body,
        FAKE_DOCKER_RC="7",
    )
    _agree(old, new, "latest-fails", old_calls, new_calls)
    assert old.returncode == 1
    assert len(old_calls.splitlines()) == 2, old_calls
    assert "✗ Failed to re-tag ghcr.io/rediacc/api:a -> ghcr.io/rediacc/api:latest" in old.stderr
    assert "Re-tagged api successfully" not in old.stderr


def test_a_missing_docker_is_bashs_own_command_not_found(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--image", "api", "--from", "a", "--to", "b"], drop="docker"
    )
    _agree(old, new, "no-docker", old_calls, new_calls)
    assert old.returncode == 1
    assert any(
        line.endswith("<SELF>: line %d: docker: command not found" % port.RETAG_CREATE_LINE)
        for line in _mask(old.stderr).splitlines()
    ), old.stderr


# --------------------------------------------------------------------------- Dry run ---------------------------------------------------------------------------


def test_dry_run_inspects_the_source_and_pushes_nothing(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--image", "api", "--from", "a", "--to", "b", "--dry-run", "--push-latest"]
    )
    _agree(old, new, "dry-run", old_calls, new_calls)
    assert old.returncode == 0
    assert old_calls.splitlines() == [
        "docker\tbuildx\timagetools\tinspect\tghcr.io/rediacc/api:a"
    ], old_calls
    assert "✓ [DRY-RUN] Would also tag: ghcr.io/rediacc/api:latest" in old.stderr
    # The probe's own stdout is DISCARDED by `>/dev/null`, so nothing leaks.
    assert old.stdout == "\n", repr(old.stdout)


def test_dry_run_fails_when_the_source_cannot_be_inspected(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--image", "api", "--from", "a", "--to", "b", "--dry-run"],
        FAKE_DOCKER_RC="4",
    )
    _agree(old, new, "dry-run-fails", old_calls, new_calls)
    assert old.returncode == 1
    assert "✗ [DRY-RUN] Failed to inspect source image: ghcr.io/rediacc/api:a" in old.stderr


def test_dry_run_with_a_missing_docker_names_the_probe_line(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--image", "api", "--from", "a", "--to", "b", "--dry-run"], drop="docker"
    )
    _agree(old, new, "dry-no-docker", old_calls, new_calls)
    assert any(
        line.endswith("<SELF>: line %d: docker: command not found" % port.DRY_RUN_INSPECT_LINE)
        for line in _mask(old.stderr).splitlines()
    ), old.stderr


# --------------------------------------------------------------------------- --skip-if-exists: all four directions ---------------------------------------------------------------------------


def _skip(tmp_path, **digests):
    return run_both(
        tmp_path,
        ["--image", "api", "--from", "a", "--to", "b", "--skip-if-exists"],
        FAKE_TO="b",
        **digests,
    )


def test_skip_if_exists_with_no_destination_falls_through_to_the_retag(tmp_path) -> None:
    old, new, old_calls, new_calls = _skip(tmp_path)
    _agree(old, new, "skip-absent", old_calls, new_calls)
    assert old.returncode == 0
    # ONE probe (the destination), then the retag. The source is never probed, because the twin short-circuits on an empty destination digest.
    assert len(old_calls.splitlines()) == 2, old_calls
    assert "\tcreate\t-t\tghcr.io/rediacc/api:b\t" in old_calls


def test_skip_if_exists_skips_when_the_digests_match(tmp_path) -> None:
    old, new, old_calls, new_calls = _skip(
        tmp_path, FAKE_DIGEST_DST="sha256:same", FAKE_DIGEST_SRC="sha256:same"
    )
    _agree(old, new, "skip-same", old_calls, new_calls)
    assert old.returncode == 0
    assert "\tcreate\t" not in old_calls, "an idempotent retry still pushed"
    assert (
        "✓ Destination matches source digest, skipping: ghcr.io/rediacc/api:b (sha256:same)"
        in old.stderr
    )


def test_skip_if_exists_retags_when_the_digests_differ(tmp_path) -> None:
    """THE CASE THE TWIN'S COMMENT IS ABOUT: a stale destination tag from a previous failed release at the same version must NOT lock the new image out."""
    old, new, old_calls, new_calls = _skip(
        tmp_path, FAKE_DIGEST_DST="sha256:stale", FAKE_DIGEST_SRC="sha256:fresh"
    )
    _agree(old, new, "skip-differs", old_calls, new_calls)
    assert old.returncode == 0
    assert "\tcreate\t" in old_calls, "a stale destination was left in place"
    assert (
        "✓ Destination exists but digest differs (dst=sha256:stale src=sha256:fresh), "
        "retagging: ghcr.io/rediacc/api:b" in old.stderr
    )


def test_skip_if_exists_retags_when_the_source_cannot_be_read(tmp_path) -> None:
    """`${src_digest:-unknown}`: an unreadable source falls THROUGH rather than
    skipping, and says `unknown` rather than inventing a digest.
    """
    old, new, old_calls, new_calls = _skip(tmp_path, FAKE_DIGEST_DST="sha256:stale")
    _agree(old, new, "skip-src-unknown", old_calls, new_calls)
    assert "src=unknown" in old.stderr, old.stderr
    assert "\tcreate\t" in old_calls


# --------------------------------------------------------------------------- Defects of the twin, pinned rather than fixed ---------------------------------------------------------------------------


def test_defect_the_failing_summary_is_still_a_green_tick(tmp_path) -> None:
    """`log_info` on a summary that says `0 succeeded, 2 failed`, so the last line of a totally failed run carries a ✓. `cleanup-staging.sh`, one directory over, uses `log_error` for the same situation."""
    old, _new, _oc, _nc = run_both(
        tmp_path, ["--all", "--from", "a", "--to", "b"], FAKE_DOCKER_RC="7"
    )
    assert old.returncode == 1
    assert old.stderr.splitlines()[-1] == "✓ Re-tag summary: 0 succeeded, 2 failed"


def test_defect_nothing_verifies_the_destination_after_the_push(tmp_path) -> None:
    """A docker that records nothing and exits 0 produces a clean promotion report. That is the twin's behaviour and the port reproduces it."""
    silent = "#!/usr/bin/python3\nimport sys\nsys.exit(0)\n"
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--all", "--from", "a", "--to", "b"], docker_body=silent
    )
    _agree(old, new, "silent-docker", old_calls, new_calls)
    assert old.returncode == 0
    assert "✓ Re-tag summary: 2 succeeded, 0 failed" in old.stderr
    assert old_calls == "", "the silent fake recorded a call; the case is not what it says"


# --------------------------------------------------------------------------- The planted defect ---------------------------------------------------------------------------


def test_planted_defect_is_caught_only_by_the_call_log(tmp_path) -> None:
    """PROVE THE DIFFERENTIAL CAN FIRE, AND WHICH ASSERTION FIRES.

    The plant swaps `-t <dst>` and `<src>`, which retags the release version BACKWARDS onto the CI tag. Every printed byte and the exit code are unchanged by it, so this also shows that a streams-only comparison would have blessed the defective port.
    """
    root = fixture(tmp_path)
    target = root / ".ci" / "rediacc_ci" / "docker" / PORT_FILE.name
    source = target.read_text(encoding="utf-8")
    plant = source.replace(
        'if _docker(["buildx", "imagetools", "create", "-t", dst, src], '
        "line=RETAG_CREATE_LINE) != 0:",
        'if _docker(["buildx", "imagetools", "create", "-t", src, dst], '
        "line=RETAG_CREATE_LINE) != 0:",
    )
    assert plant != source, "the plant did not apply; the control is broken, not the gate"
    target.write_text(plant, encoding="utf-8")

    args = ["--image", "api", "--from", "a", "--to", "b"]
    old, old_calls = _run(root, "old", args)
    new, new_calls = _run(root, "new", args)

    assert new.returncode == old.returncode, "the plant changed the exit code; wrong plant"
    assert _mask(new.stdout) == _mask(old.stdout), "the plant changed stdout; wrong plant"
    assert _mask(new.stderr) == _mask(old.stderr), "the plant changed stderr; wrong plant"
    assert new_calls != old_calls, "THE CALL LOG DID NOT SEE THE SWAP: this gate cannot fail"
    assert "-t\tghcr.io/rediacc/api:a\tghcr.io/rediacc/api:b" in new_calls


def _run_merged(root, side: str, args: list[str], **extra: str):
    """ONE PIPE FOR BOTH STREAMS, which is what a CI log actually is.

    The separate-stream comparison above cannot see a CROSS-stream ordering divergence, and there is a real one to see: Python block-buffers stdout against a pipe while bash's `echo` writes straight through, so without the
    port's `flush=True` its `echo ""` separators arrive several lines late with
    byte-identical content in each stream taken alone. Measured before the flush was added, not imagined.
    """
    call_log = root / ("%s-merged-calls.log" % side)
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(root),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
    }
    env.update(extra)
    if side == "old":
        argv = [BASH, str(root / ".ci" / "scripts" / "docker" / TWIN.name)]
    else:
        argv = [sys.executable, str(root / ".ci" / "rediacc_ci" / "docker" / PORT_FILE.name)]
    return subprocess.run(
        [*argv, *args],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )


def test_the_merged_stream_keeps_the_twins_line_order(tmp_path) -> None:
    root = fixture(tmp_path)
    old = _run_merged(root, "old", ["--all", "--from", "ci-1", "--to", "0.5.0", "--push-latest"])
    new = _run_merged(root, "new", ["--all", "--from", "ci-1", "--to", "0.5.0", "--push-latest"])
    assert new.returncode == old.returncode
    assert _mask(new.stdout) == _mask(old.stdout), "merged order diverged:\nold:\n%s\nnew:\n%s" % (
        old.stdout,
        new.stdout,
    )
    # NON-TRIVIAL BY CONSTRUCTION: a run with nothing on stdout would pass this
    # for free, so the case is one that writes to BOTH streams.
    assert old.stdout.count("\n") >= 8, old.stdout


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


# --------------------------------------------------------------------------- Staleness alarms ---------------------------------------------------------------------------


def test_the_constants_are_still_constants_shs() -> None:
    text = CONSTANTS.read_text(encoding="utf-8")
    images = re.search(r"^readonly PUBLISH_IMAGES=\((.*)\)$", text, re.MULTILINE)
    assert images is not None, "PUBLISH_IMAGES is no longer a one-line array in constants.sh"
    assert tuple(images.group(1).replace('"', "").split()) == port.PUBLISH_IMAGES
    registry = re.search(
        r'^PUBLISH_DOCKER_REGISTRY="\$\{PUBLISH_DOCKER_REGISTRY:-([^}]*)\}"$', text, re.MULTILINE
    )
    assert registry is not None, "the registry default moved in constants.sh"
    assert registry.group(1) == port.REGISTRY_DEFAULT


def test_the_quoted_line_numbers_still_name_their_statements() -> None:
    lines = TWIN.read_text(encoding="utf-8").splitlines()
    expected = {
        "--image": 'IMAGE_NAME="$2"',
        "--image-path": 'IMAGE_PATH="$2"',
        "--from": 'FROM_TAG="$2"',
        "--to": 'TO_TAG="$2"',
    }
    for flag, number in port.UNBOUND_LINES.items():
        assert lines[number - 1].strip() == expected[flag], (flag, number, lines[number - 1])
    assert lines[port.DRY_RUN_INSPECT_LINE - 1].strip() == (
        'if ! docker buildx imagetools inspect "$src" >/dev/null; then'
    )
    assert lines[port.RETAG_CREATE_LINE - 1].strip() == (
        'if ! docker buildx imagetools create -t "$dst" "$src"; then'
    )
    assert lines[port.LATEST_CREATE_LINE - 1].strip() == (
        'if ! docker buildx imagetools create -t "$dst_latest" "$src"; then'
    )


def test_the_digest_format_is_still_the_twins() -> None:
    text = TWIN.read_text(encoding="utf-8")
    assert "--format '%s'" % port.DIGEST_FORMAT in text, port.DIGEST_FORMAT
