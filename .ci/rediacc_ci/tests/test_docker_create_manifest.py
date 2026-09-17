"""Differential: `rediacc_ci.docker.create_manifest` against its twin
`.ci/scripts/docker/create-manifest.sh`.

A RECORDING FAKE `docker` ON A SCRATCH PATH, and the PATH is an explicit list of
symlinks so that a tool nobody named is genuinely absent. That is not a
formality here: an early probe for this port left `/usr/bin` on PATH and the
real docker binary contacted `ghcr.io/token` before the twin printed its first
line. Nothing in this file can reach a registry.

THE CALL LOG IS THE EVIDENCE, and the fake is built to keep it that way: its
`create` path prints NOTHING, so a port that pushed the wrong tag, dropped an
architecture or skipped the `:latest` manifest would produce identical stdout,
identical stderr and an identical exit code.
`test_planted_defect_is_caught_only_by_the_call_log` plants a dropped arch and
shows all three agreeing while the log does not.

grep AND head ARE COMPARED AGAINST THE REAL TOOLS. The port reimplements the
twin's `grep -E "(Platform:|Name:)" | head -10` in Python, so
`test_the_platform_filter_matches_grep_e_on_a_corpus` runs both over the same
awkward corpus (no trailing newline, an eleventh match, a line matching both
needles, an empty stream) rather than trusting that they agree.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.docker import create_manifest as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "docker" / "create-manifest.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
CONSTANTS = ROOT / ".ci" / "config" / "constants.sh"
TOOLCHAIN = ROOT / ".devcontainer" / "toolchain.env"
PORT_FILE = ROOT / ".ci" / "rediacc_ci" / "docker" / "create_manifest.py"
BASH = shutil.which("bash") or "/bin/bash"

# `create` PRINTS NOTHING on purpose; `inspect` answers with a fixed manifest
# listing. See the module docstring: a constant, argv-independent response is what makes the recorded call log the only witness to what was pushed.
FAKE_DOCKER = r"""#!/usr/bin/python3
import os
import sys

argv = sys.argv[1:]
with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("docker\t" + "\t".join(argv) + "\n")

rc = int(os.environ.get("FAKE_DOCKER_RC", "0"))
verb = argv[2] if len(argv) > 2 else ""

if verb == "create" and rc:
    sys.stderr.write("ERROR: failed to create manifest list: unauthorized\n")
    sys.exit(rc)
if verb == "inspect":
    if os.environ.get("FAKE_INSPECT_RC", "0") != "0":
        sys.stderr.write("ERROR: manifest unknown\n")
        sys.exit(int(os.environ["FAKE_INSPECT_RC"]))
    sys.stdout.write("Name:      <redacted>\n")
    sys.stdout.write("MediaType: application/vnd.oci.image.index.v1+json\n")
    sys.stdout.write("Digest:    sha256:redacted\n")
    sys.stdout.write("\n")
    sys.stdout.write("Manifests:\n")
    sys.stdout.write("Platform:  linux/amd64\n")
    sys.stdout.write("Platform:  linux/arm64\n")
sys.exit(0)
"""

# `dirname` for SCRIPT_DIR in the twin and in constants.sh, `uname`/`tr` for common.sh's detection helpers, `grep`/`head` for the twin's verify pipeline, `python3` because the fake is Python. Anything not listed is ABSENT.
PATH_MINIMUM = ("dirname", "uname", "tr", "grep", "head", "python3")


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
    """`$0`, the one thing that cannot agree. Masked by the two exact spellings,
    so any other absolute path leaking into the output is still compared.
    """
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


# --------------------------------------------------------------------------- Argument handling ---------------------------------------------------------------------------


def test_help_is_stdout_and_exit_zero(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--help"])
    _agree(old, new, "help", old_calls, new_calls)
    assert old.returncode == 0
    assert old.stderr == ""
    assert old_calls == ""


def test_image_and_image_path_are_mutually_exclusive(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--image", "api", "--image-path", "ghcr.io/acme/api", "--tag", "1"]
    )
    _agree(old, new, "both", old_calls, new_calls)
    assert old.returncode == 1
    assert old.stderr == "✗ --image and --image-path are mutually exclusive\n"


def test_the_exclusivity_check_runs_before_the_tag_check(tmp_path) -> None:
    """ORDER IS OBSERVABLE. With neither `--tag` nor a valid target, the twin
    reports the exclusivity error; a port that validated `--tag` first would
    print a different message with the same exit code.
    """
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--image", "api", "--image-path", "ghcr.io/acme/api"]
    )
    _agree(old, new, "order", old_calls, new_calls)
    assert old.stderr == "✗ --image and --image-path are mutually exclusive\n"


def test_neither_target_refuses(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--tag", "1"])
    _agree(old, new, "neither", old_calls, new_calls)
    assert old.returncode == 1
    assert old.stderr == "✗ --image or --image-path is required\n"


def test_no_arguments_at_all_reports_the_missing_target_not_the_missing_tag(tmp_path) -> None:
    """THE ARM THAT WAS MISSING, and its absence was measured rather than
    guessed: a plant that swapped the "neither target" and "--tag" checks left
    all 27 tests green, because every case either supplied a target or supplied
    a tag. A control that does not fire is a claim about the control first, so
    this is the case that distinguishes the two orders.
    """
    old, new, old_calls, new_calls = run_both(tmp_path, [])
    _agree(old, new, "no-args", old_calls, new_calls)
    assert old.returncode == 1
    assert old.stderr == "✗ --image or --image-path is required\n", old.stderr


def test_a_missing_tag_refuses(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--image", "api"])
    _agree(old, new, "no-tag", old_calls, new_calls)
    assert old.returncode == 1
    assert old.stderr == "✗ --tag is required\n"


def test_an_unknown_option_refuses(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, ["--bogus"])
    _agree(old, new, "bogus", old_calls, new_calls)
    assert old.returncode == 1
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


# --------------------------------------------------------------------------- Dry run, including the double space ---------------------------------------------------------------------------


def test_dry_run_prints_the_two_commands_and_calls_nothing(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--image", "api", "--tag", "1.2.3", "--dry-run", "--push-latest"]
    )
    _agree(old, new, "dry-run", old_calls, new_calls)
    assert old.returncode == 0
    assert old_calls == "", "a dry run reached docker"
    srcs = "ghcr.io/rediacc/api:1.2.3-amd64 ghcr.io/rediacc/api:1.2.3-arm64"
    # THE DOUBLE SPACE BEFORE `srcs` IS THE TWIN'S. See the module docstring.
    assert old.stdout.splitlines() == [
        "  docker buildx imagetools create -t ghcr.io/rediacc/api:1.2.3  " + srcs,
        "  docker buildx imagetools create -t ghcr.io/rediacc/api:latest  " + srcs,
    ], old.stdout


def test_the_leading_space_in_the_sources_field_is_the_twins(tmp_path) -> None:
    """THE DOUBLE SPACE IS OUTPUT, NOT A TYPO. It comes from
    `SOURCE_IMAGES="${SOURCE_IMAGES} ..."` starting empty. Asserted on the raw
    bytes so nobody tidies it into a divergence.
    """
    old, _new, _oc, _nc = run_both(tmp_path, ["--image", "api", "--tag", "9", "--dry-run"])
    assert "✓   Sources:  ghcr.io/rediacc/api:9-amd64 ghcr.io/rediacc/api:9-arm64\n" in old.stderr
    assert "Sources:   " not in old.stderr, "three spaces means the field grew another one"


def test_dry_run_without_push_latest_prints_one_command(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--image", "api", "--tag", "1", "--dry-run"]
    )
    _agree(old, new, "dry-one", old_calls, new_calls)
    assert len(old.stdout.splitlines()) == 1


# --------------------------------------------------------------------------- The real path ---------------------------------------------------------------------------


def test_the_happy_path_creates_verifies_and_prints_platforms(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--image", "api", "--tag", "1.2.3", "--push-latest"]
    )
    _agree(old, new, "happy", old_calls, new_calls)
    assert old.returncode == 0

    head = "docker\tbuildx\timagetools\t"
    src = "ghcr.io/rediacc/api:1.2.3-amd64\tghcr.io/rediacc/api:1.2.3-arm64"
    assert old_calls.splitlines() == [
        head + "create\t-t\tghcr.io/rediacc/api:1.2.3\t" + src,
        head + "create\t-t\tghcr.io/rediacc/api:latest\t" + src,
        # TWO inspects, not one: the twin decides the verdict with the first and shows platforms with the second.
        head + "inspect\tghcr.io/rediacc/api:1.2.3",
        head + "inspect\tghcr.io/rediacc/api:1.2.3",
    ], old_calls

    assert old.stdout.splitlines() == [
        "Name:      <redacted>",
        "Platform:  linux/amd64",
        "Platform:  linux/arm64",
        "",
    ], old.stdout
    assert old.stderr.splitlines()[-1] == "✓ Manifest creation complete"


def test_image_path_bypasses_the_registry(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--image-path", "ghcr.io/acme/server", "--tag", "0.5.0"]
    )
    _agree(old, new, "image-path", old_calls, new_calls)
    assert old.returncode == 0
    assert "ghcr.io/rediacc" not in old_calls, old_calls
    # And the step line uses the FULL PATH as the label, because IMAGE_NAME is
    # empty and the twin's `${IMAGE_NAME:-$IMAGE_PATH}` falls through.
    assert "→ Creating multi-arch manifest for ghcr.io/acme/server:0.5.0" in old.stderr


def test_the_registry_override_reaches_the_argv(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path,
        ["--image", "api", "--tag", "1"],
        PUBLISH_DOCKER_REGISTRY="ghcr.io/other",
    )
    _agree(old, new, "registry-override", old_calls, new_calls)
    assert "ghcr.io/other/api:1-amd64" in old_calls, old_calls


def test_a_failing_create_stops_before_the_latest_manifest(tmp_path) -> None:
    """`set -e` at the top level: no summary, no verification, exit 1."""
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--image", "api", "--tag", "1", "--push-latest"], FAKE_DOCKER_RC="9"
    )
    _agree(old, new, "create-fails", old_calls, new_calls)
    assert old.returncode == 1
    assert len(old_calls.splitlines()) == 1, old_calls
    assert old.stderr.splitlines()[-1] == "✗ Failed to create manifest: ghcr.io/rediacc/api:1"
    assert "Manifest creation complete" not in old.stderr


def test_a_missing_docker_is_bashs_own_command_not_found(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--image", "api", "--tag", "1"], drop="docker"
    )
    _agree(old, new, "no-docker", old_calls, new_calls)
    assert old.returncode == 1
    assert (
        _mask(old.stderr)
        .splitlines()[-2]
        .endswith("<SELF>: line %d: docker: command not found" % port.DOCKER_CREATE_LINE)
    ), old.stderr
    assert old_calls == ""


# --------------------------------------------------------------------------- Defects of the twin, pinned rather than fixed ---------------------------------------------------------------------------


def test_defect_a_manifest_that_cannot_be_verified_still_exits_zero(tmp_path) -> None:
    """The verification is ADVISORY. `inspect` failing produces a warning and
    exit 0, so a `create` that reported success but pushed nothing readable is
    reported as a complete run.
    """
    old, new, old_calls, new_calls = run_both(
        tmp_path, ["--image", "api", "--tag", "1"], FAKE_INSPECT_RC="1"
    )
    _agree(old, new, "unverifiable", old_calls, new_calls)
    assert old.returncode == 0, "the twin's behaviour changed; re-read this test"
    assert "⚠ Could not verify manifest (may still be pushing)" in old.stderr
    assert "✓ Manifest creation complete" in old.stderr
    # ONE inspect, not two: the second only runs on the success branch.
    assert len([c for c in old_calls.splitlines() if "\tinspect\t" in c]) == 1


def test_defect_the_latest_manifest_is_never_verified(tmp_path) -> None:
    """Only `$MANIFEST_TAG` is inspected. `:latest` is pushed and forgotten."""
    old, _new, old_calls, _nc = run_both(
        tmp_path, ["--image", "api", "--tag", "1", "--push-latest"]
    )
    assert old.returncode == 0
    inspects = [c for c in old_calls.splitlines() if "\tinspect\t" in c]
    assert len(inspects) == 2
    assert all(c.endswith("api:1") for c in inspects), inspects


def test_defect_a_single_arch_image_is_not_detected_before_the_push(tmp_path) -> None:
    """`ARCHS` is hard-coded, so the arm64 reference is always passed. Nothing
    probes whether it exists; the registry decides, and here it accepts.
    """
    assert port.ARCHS == ("amd64", "arm64")
    old, _new, old_calls, _nc = run_both(tmp_path, ["--image", "api", "--tag", "1"])
    assert "api:1-arm64" in old_calls
    assert old.returncode == 0


# --------------------------------------------------------------------------- The planted defect ---------------------------------------------------------------------------


def test_planted_defect_is_caught_only_by_the_call_log(tmp_path) -> None:
    """PROVE THE DIFFERENTIAL CAN FIRE. The plant drops arm64 from the ARGV
    handed to docker, at the call site, so the printed `Sources:` line still
    names both architectures. That is exactly the mistake that publishes a
    silently single-arch manifest under a name every consumer reads as
    multi-arch: every printed byte and the exit code are unchanged by it.

    Planting it one layer down, in `source_images()`, was tried first and is the
    WRONG plant -- it also rewrites the `Sources:` line, so stderr diverges and
    the test proves nothing about the call log.
    """
    root = fixture(tmp_path)
    target = root / ".ci" / "rediacc_ci" / "docker" / PORT_FILE.name
    source = target.read_text(encoding="utf-8")
    plant = source.replace(
        '        ["buildx", "imagetools", "create", "-t", manifest_tag, *sources],',
        '        ["buildx", "imagetools", "create", "-t", manifest_tag, *sources[:1]],',
    )
    assert plant != source, "the plant did not apply; the control is broken, not the gate"
    target.write_text(plant, encoding="utf-8")

    args = ["--image", "api", "--tag", "1.2.3"]
    old, old_calls = _run(root, "old", args)
    new, new_calls = _run(root, "new", args)

    assert new.returncode == old.returncode, "the plant changed the exit code; wrong plant"
    assert _mask(new.stdout) == _mask(old.stdout), "the plant changed stdout; wrong plant"
    assert _mask(new.stderr) == _mask(old.stderr), "the plant changed stderr; wrong plant"
    assert new_calls != old_calls, "THE CALL LOG DID NOT SEE IT: this gate cannot fail"
    assert "1.2.3-arm64" not in new_calls.splitlines()[0]


def _run_merged(root, side: str, args: list[str], **extra: str):
    """ONE PIPE FOR BOTH STREAMS, which is what a CI log actually is.

    The separate-stream comparison above cannot see a CROSS-stream ordering
    divergence, and there is a real one to see: Python block-buffers stdout
    against a pipe while bash's `echo` writes straight through, so without the
    port's `flush=True` its `echo ""` separators arrive several lines late with
    byte-identical content in each stream taken alone. Measured before the flush
    was added, not imagined.
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
    old = _run_merged(root, "old", ["--image", "api", "--tag", "1.2.3", "--push-latest"])
    new = _run_merged(root, "new", ["--image", "api", "--tag", "1.2.3", "--push-latest"])
    assert new.returncode == old.returncode
    assert _mask(new.stdout) == _mask(old.stdout), "merged order diverged:\nold:\n%s\nnew:\n%s" % (
        old.stdout,
        new.stdout,
    )
    # NON-TRIVIAL BY CONSTRUCTION: a run with nothing on stdout would pass this
    # for free, so the case is one that writes to BOTH streams.
    assert old.stdout.count("\n") >= 10, old.stdout


# --------------------------------------------------------------------------- Pure helpers ---------------------------------------------------------------------------


def test_source_images_and_the_field_are_two_different_things() -> None:
    assert port.source_images("r/i", "1") == ["r/i:1-amd64", "r/i:1-arm64"]
    # The field carries the LEADING SPACE. This is the assertion that keeps the human-readable line byte-identical to the twin's.
    assert port.source_images_field("r/i", "1") == " r/i:1-amd64 r/i:1-arm64"


def test_the_platform_filter_matches_grep_e_on_a_corpus() -> None:
    """The port reimplements `grep -E "(Platform:|Name:)" | head -10`, so the
    two are run over the same awkward inputs rather than assumed equal.
    """
    corpus = [
        "",
        "Name:      x\n",
        "Name:      x",  # no trailing newline
        "nothing here\nor here\n",
        "Platform:  a\nName: b\nPlatform:  c\n",
        "  indented Platform: yes\n",
        "".join("Platform: %d\n" % i for i in range(15)),  # more than head -10
        "Name: and Platform: on one line\n",
        "platform: lowercase does not match\n",
    ]
    grep = shutil.which("grep")
    assert grep is not None, "grep is missing from this machine"
    head = shutil.which("head")
    assert head is not None, "head is missing from this machine"
    # THE PIPELINE IS RUN THROUGH bash, not through `shell=True`, because the
    # pipeline IS the thing under comparison and `bash -c` is what the twin itself uses. It also keeps the argv a list, which is this repo's rule.
    pipeline = '%s -E "(Platform:|Name:)" | %s -10' % (grep, head)
    for text in corpus:
        proc = subprocess.run(
            [BASH, "-c", pipeline],
            input=text,
            capture_output=True,
            text=True,
            check=False,
        )
        expected = proc.stdout.splitlines()
        assert port.platform_lines(text) == expected, (text, expected)


def test_the_registry_default_is_taken_on_unset_and_on_empty(monkeypatch) -> None:
    monkeypatch.delenv("PUBLISH_DOCKER_REGISTRY", raising=False)
    assert port.registry() == "ghcr.io/rediacc"
    monkeypatch.setenv("PUBLISH_DOCKER_REGISTRY", "")
    assert port.registry() == "ghcr.io/rediacc"


def test_dry_run_is_the_string_true_and_nothing_else(monkeypatch) -> None:
    monkeypatch.setenv("DRY_RUN", "1")
    assert port.dry_run_default() == "1"
    monkeypatch.setenv("DRY_RUN", "true")
    assert port.dry_run_default() == "true"


def test_resolve_image_path_prefers_image_path_verbatim(monkeypatch) -> None:
    monkeypatch.delenv("PUBLISH_DOCKER_REGISTRY", raising=False)
    opts = port.Options()
    opts.image_path = "ghcr.io/acme/server"
    assert port.resolve_image_path(opts) == "ghcr.io/acme/server"
    bare = port.Options()
    bare.image_name = "api"
    assert port.resolve_image_path(bare) == "ghcr.io/rediacc/api"


# --------------------------------------------------------------------------- Staleness alarms ---------------------------------------------------------------------------


def test_the_registry_constant_is_still_constants_shs() -> None:
    text = CONSTANTS.read_text(encoding="utf-8")
    registry = re.search(
        r'^PUBLISH_DOCKER_REGISTRY="\$\{PUBLISH_DOCKER_REGISTRY:-([^}]*)\}"$', text, re.MULTILINE
    )
    assert registry is not None, "the registry default moved in constants.sh"
    assert registry.group(1) == port.REGISTRY_DEFAULT


def test_the_quoted_line_numbers_still_name_their_statements() -> None:
    """Every line number this port prints is checked against the twin, because a
    twin edit that moves one would otherwise drift silently into a CI log.
    """
    lines = TWIN.read_text(encoding="utf-8").splitlines()
    expected = {
        "--image": 'IMAGE_NAME="$2"',
        "--image-path": 'IMAGE_PATH="$2"',
        "--tag": 'TAG="$2"',
    }
    for flag, number in port.UNBOUND_LINES.items():
        assert lines[number - 1].strip() == expected[flag], (flag, number, lines[number - 1])
    assert (
        lines[port.DOCKER_CREATE_LINE - 1]
        .strip()
        .startswith("if ! docker buildx imagetools create -t")
    ), lines[port.DOCKER_CREATE_LINE - 1]


def test_the_arch_list_is_still_the_twins() -> None:
    text = TWIN.read_text(encoding="utf-8")
    archs = re.search(r"^ARCHS=\((.*)\)$", text, re.MULTILINE)
    assert archs is not None, "ARCHS is no longer a one-line array in the twin"
    assert tuple(archs.group(1).replace('"', "").split()) == port.ARCHS
