"""`rediacc_ci.docker.create_manifest`, driven against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/docker/create-manifest.sh` and the port over the same throwaway tree and compared exit code, stdout, stderr and the `docker` call log. The K=5 ledger `.ci/shadow/w7p6-create-manifest.observations.jsonl` recorded that comparison over five distinct trees. The twin has now been deleted and every case that executed it
compares against `goldens/create-manifest/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree. Each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

A RECORDING FAKE `docker` ON A SCRATCH PATH, and the PATH is an explicit list of symlinks so that a tool nobody named is genuinely absent. That is not a formality here: an early probe for this port left `/usr/bin` on PATH and the real docker binary contacted `ghcr.io/token` before the twin printed its first line. Nothing in this file can reach a registry.

THE CALL LOG IS THE EVIDENCE, and the fake is built to keep it that way: its `create` path prints NOTHING, so a port that pushed the wrong tag, dropped an architecture or skipped the `:latest` manifest would produce identical stdout, identical stderr and an identical exit code. `test_a_planted_dropped_arch_is_caught_only_by_the_call_log` plants a dropped arch and shows all
three agreeing while the log does not.

grep AND head ARE COMPARED AGAINST THE REAL TOOLS. The port reimplements the twin's `grep -E "(Platform:|Name:)" | head -10` in Python, so `test_the_platform_filter_matches_grep_e_on_a_corpus` runs both over the same awkward corpus (no trailing newline, an eleventh match, a line matching both needles, an empty stream) rather than trusting that they agree.

ONE GOLDEN IS A MERGED STREAM, and it is not a duplicate of the separate-stream one. A per-stream comparison cannot see a CROSS-stream ordering divergence, and there was a real one to see: Python block-buffers stdout against a pipe while bash's `echo` wrote straight through, so without the port's `flush=True` its `echo ""` separators arrived several lines late with
byte-identical content in each stream taken alone. `the-merged-stream` records `2>&1` as a CI log really sees it, under the stdout marker with an empty stderr.

THE TWO STALENESS ALARMS THAT READ THE TWIN'S SOURCE ARE GONE, and the goldens replace them. They existed so a line number quoted by the port could not drift away from the statement it named while the twin was still being edited; a deleted file does not drift, and the port's copy of those numbers is pinned to the byte by the three `an-unbound-*` recordings and the
`command not found` one. `ARCHS` is likewise pinned by the recorded call log, which names both architectures.
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
from rediacc_ci.docker import create_manifest as port
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
CONSTANTS = ROOT / ".ci" / "config" / "constants.sh"
TOOLCHAIN = ROOT / ".devcontainer" / "toolchain.env"
PORT_FILE = ROOT / ".ci" / "rediacc_ci" / "docker" / "create_manifest.py"
BASH = shutil.which("bash") or "/bin/bash"

SLUG = "create-manifest"
TWIN_REL = ".ci/scripts/docker/create-manifest.sh"
PORT_REL = ".ci/rediacc_ci/docker/create_manifest.py"

CALLS_MARKER = "--- calls ---\n"

# `create` PRINTS NOTHING on purpose; `inspect` answers with a fixed manifest listing. See the module docstring: a constant, argv-independent response is what makes the recorded call log the only witness to what was pushed.
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


CASE_KW: dict[str, tuple[list[str], dict[str, object]]] = {
    "help": (["--help"], {}),
    "image-and-image-path-together": (
        ["--image", "api", "--image-path", "ghcr.io/acme/api", "--tag", "1"],
        {},
    ),
    "the-exclusivity-check-beats-the-tag-check": (
        ["--image", "api", "--image-path", "ghcr.io/acme/api"],
        {},
    ),
    "neither-target": (["--tag", "1"], {}),
    "no-arguments-at-all": ([], {}),
    "a-missing-tag": (["--image", "api"], {}),
    "an-unknown-option": (["--bogus"], {}),
    "an-unbound-image": (["--image"], {}),
    "an-unbound-image-path": (["--image-path"], {}),
    "an-unbound-tag": (["--tag"], {}),
    "a-dry-run-with-push-latest": (
        ["--image", "api", "--tag", "1.2.3", "--dry-run", "--push-latest"],
        {},
    ),
    "a-dry-run-at-tag-nine": (["--image", "api", "--tag", "9", "--dry-run"], {}),
    "a-dry-run-without-push-latest": (["--image", "api", "--tag", "1", "--dry-run"], {}),
    "the-happy-path": (["--image", "api", "--tag", "1.2.3", "--push-latest"], {}),
    "an-image-path": (["--image-path", "ghcr.io/acme/server", "--tag", "0.5.0"], {}),
    "a-registry-override": (
        ["--image", "api", "--tag", "1"],
        {"PUBLISH_DOCKER_REGISTRY": "ghcr.io/other"},
    ),
    "a-failing-create": (
        ["--image", "api", "--tag", "1", "--push-latest"],
        {"FAKE_DOCKER_RC": "9"},
    ),
    "a-missing-docker": (["--image", "api", "--tag", "1"], {"drop": "docker"}),
    "an-unverifiable-manifest": (["--image", "api", "--tag", "1"], {"FAKE_INSPECT_RC": "1"}),
    "a-single-image-at-tag-one": (["--image", "api", "--tag", "1"], {}),
    "a-single-image-at-tag-one-two-three": (["--image", "api", "--tag", "1.2.3"], {}),
    "the-merged-stream": (
        ["--image", "api", "--tag", "1.2.3", "--push-latest"],
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


# --------------------------------------------------------------------------- Argument handling ---------------------------------------------------------------------------


def test_help_is_stdout_and_exit_zero() -> None:
    returncode, _, stderr, calls = recorded("help")
    assert returncode == 0
    assert stderr == ""
    assert calls == ""


def test_image_and_image_path_are_mutually_exclusive() -> None:
    returncode, _, stderr, _ = recorded("image-and-image-path-together")
    assert returncode == 1
    assert stderr == "✗ --image and --image-path are mutually exclusive\n"


def test_the_exclusivity_check_runs_before_the_tag_check() -> None:
    """ORDER IS OBSERVABLE. With neither `--tag` nor a valid target, the twin reported the exclusivity error; a port that validated `--tag` first would print a different message with the same exit code."""
    assert recorded("the-exclusivity-check-beats-the-tag-check")[2] == (
        "✗ --image and --image-path are mutually exclusive\n"
    )


def test_neither_target_refuses() -> None:
    returncode, _, stderr, _ = recorded("neither-target")
    assert returncode == 1
    assert stderr == "✗ --image or --image-path is required\n"


def test_no_arguments_at_all_reports_the_missing_target_not_the_missing_tag() -> None:
    """THE ARM THAT WAS MISSING, and its absence was measured rather than guessed: a plant that swapped the "neither target" and "--tag" checks left all 27 tests green, because every case either supplied a target or supplied a tag. A control that does not fire is a claim about the control first, so this is the case that distinguishes the two orders."""
    returncode, _, stderr, _ = recorded("no-arguments-at-all")
    assert returncode == 1
    assert stderr == "✗ --image or --image-path is required\n", stderr


def test_a_missing_tag_refuses() -> None:
    returncode, _, stderr, _ = recorded("a-missing-tag")
    assert returncode == 1
    assert stderr == "✗ --tag is required\n"


def test_an_unknown_option_refuses() -> None:
    returncode, _, stderr, _ = recorded("an-unknown-option")
    assert returncode == 1
    assert stderr == "✗ Unknown option: --bogus\n"


UNBOUND_CASES = {
    "--image": "an-unbound-image",
    "--image-path": "an-unbound-image-path",
    "--tag": "an-unbound-tag",
}


def test_each_value_flag_dies_the_way_set_u_dies() -> None:
    """THE LINE NUMBERS, PINNED BY RECORDING. `set -u` made bash name the twin's own file and line, and the port reproduces both from `UNBOUND_LINES`. These three recordings are what stops that table drifting now that the file they describe is gone."""
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


# --------------------------------------------------------------------------- Dry run, including the double space ---------------------------------------------------------------------------


def test_dry_run_prints_the_two_commands_and_calls_nothing() -> None:
    returncode, stdout, _, calls = recorded("a-dry-run-with-push-latest")
    assert returncode == 0
    assert calls == "", "a dry run reached docker"
    srcs = "ghcr.io/rediacc/api:1.2.3-amd64 ghcr.io/rediacc/api:1.2.3-arm64"
    # THE DOUBLE SPACE BEFORE `srcs` IS THE TWIN'S. See the module docstring.
    assert stdout.splitlines() == [
        "  docker buildx imagetools create -t ghcr.io/rediacc/api:1.2.3  " + srcs,
        "  docker buildx imagetools create -t ghcr.io/rediacc/api:latest  " + srcs,
    ], stdout


def test_the_leading_space_in_the_sources_field_is_the_twins() -> None:
    """THE DOUBLE SPACE IS OUTPUT, NOT A TYPO. It came from
    `SOURCE_IMAGES="${SOURCE_IMAGES} ..."` starting empty. Asserted on the raw
    bytes so nobody tidies it into a divergence.
    """
    stderr = recorded("a-dry-run-at-tag-nine")[2]
    assert "✓   Sources:  ghcr.io/rediacc/api:9-amd64 ghcr.io/rediacc/api:9-arm64\n" in stderr
    assert "Sources:   " not in stderr, "three spaces means the field grew another one"


def test_dry_run_without_push_latest_prints_one_command() -> None:
    assert len(recorded("a-dry-run-without-push-latest")[1].splitlines()) == 1


# --------------------------------------------------------------------------- The real path ---------------------------------------------------------------------------


def test_the_happy_path_creates_verifies_and_prints_platforms() -> None:
    returncode, stdout, stderr, calls = recorded("the-happy-path")
    assert returncode == 0

    head = "docker\tbuildx\timagetools\t"
    src = "ghcr.io/rediacc/api:1.2.3-amd64\tghcr.io/rediacc/api:1.2.3-arm64"
    assert calls.splitlines() == [
        head + "create\t-t\tghcr.io/rediacc/api:1.2.3\t" + src,
        head + "create\t-t\tghcr.io/rediacc/api:latest\t" + src,
        # TWO inspects, not one: the twin decided the verdict with the first and showed platforms with the second.
        head + "inspect\tghcr.io/rediacc/api:1.2.3",
        head + "inspect\tghcr.io/rediacc/api:1.2.3",
    ], calls

    assert stdout.splitlines() == [
        "Name:      <redacted>",
        "Platform:  linux/amd64",
        "Platform:  linux/arm64",
        "",
    ], stdout
    assert stderr.splitlines()[-1] == "✓ Manifest creation complete"


def test_image_path_bypasses_the_registry() -> None:
    returncode, _, stderr, calls = recorded("an-image-path")
    assert returncode == 0
    assert "ghcr.io/rediacc" not in calls, calls
    # And the step line uses the FULL PATH as the label, because IMAGE_NAME was
    # empty and the twin's `${IMAGE_NAME:-$IMAGE_PATH}` fell through.
    assert "→ Creating multi-arch manifest for ghcr.io/acme/server:0.5.0" in stderr


def test_the_registry_override_reaches_the_argv() -> None:
    assert "ghcr.io/other/api:1-amd64" in recorded("a-registry-override")[3]


def test_a_failing_create_stops_before_the_latest_manifest() -> None:
    """`set -e` at the top level: no summary, no verification, exit 1."""
    returncode, _, stderr, calls = recorded("a-failing-create")
    assert returncode == 1
    assert len(calls.splitlines()) == 1, calls
    assert stderr.splitlines()[-1] == "✗ Failed to create manifest: ghcr.io/rediacc/api:1"
    assert "Manifest creation complete" not in stderr


def test_a_missing_docker_is_bashs_own_command_not_found() -> None:
    returncode, _, stderr, calls = recorded("a-missing-docker")
    assert returncode == 1
    assert stderr.splitlines()[-2].endswith(
        "<SELF>: line %d: docker: command not found" % port.DOCKER_CREATE_LINE
    ), stderr
    assert calls == ""


# --------------------------------------------------------------------------- Defects of the twin, pinned rather than fixed ---------------------------------------------------------------------------


def test_defect_a_manifest_that_cannot_be_verified_still_exits_zero() -> None:
    """The verification was ADVISORY. `inspect` failing produced a warning and exit 0, so a `create` that reported success but pushed nothing readable is reported as a complete run."""
    returncode, _, stderr, calls = recorded("an-unverifiable-manifest")
    assert returncode == 0, "the twin's behaviour changed; re-read this test"
    assert "⚠ Could not verify manifest (may still be pushing)" in stderr
    assert "✓ Manifest creation complete" in stderr
    # ONE inspect, not two: the second only ran on the success branch.
    assert len([c for c in calls.splitlines() if "\tinspect\t" in c]) == 1


def test_defect_the_latest_manifest_is_never_verified() -> None:
    """Only `$MANIFEST_TAG` was inspected. `:latest` is pushed and forgotten."""
    returncode, _, _, calls = recorded("the-happy-path")
    assert returncode == 0
    inspects = [c for c in calls.splitlines() if "\tinspect\t" in c]
    assert len(inspects) == 2
    assert all(c.endswith("api:1.2.3") for c in inspects), inspects


def test_defect_a_single_arch_image_is_not_detected_before_the_push() -> None:
    """`ARCHS` was hard-coded, so the arm64 reference is always passed. Nothing probes whether it exists; the registry decides, and here it accepts. The recorded call log is also what now pins the arch list, which used to be read out of the twin."""
    assert port.ARCHS == ("amd64", "arm64")
    returncode, _, _, calls = recorded("a-single-image-at-tag-one")
    assert "api:1-arm64" in calls
    assert "api:1-amd64" in calls
    assert returncode == 0


def test_the_merged_stream_keeps_the_twins_line_order() -> None:
    """THE CROSS-STREAM ORDERING, which no per-stream comparison can see. See the module docstring for the buffering divergence this exists to catch."""
    returncode, merged, stderr, _ = recorded(MERGED_CASE)
    assert returncode == 0
    assert stderr == "", "the merged recording put bytes under the stderr marker"
    # NON-TRIVIAL BY CONSTRUCTION: a run with nothing on stdout would pass this
    # for free, so the case is one that writes to BOTH streams.
    assert merged.count("\n") >= 10, merged


# --------------------------------------------------------------------------- Pure helpers ---------------------------------------------------------------------------


def test_source_images_and_the_field_are_two_different_things() -> None:
    assert port.source_images("r/i", "1") == ["r/i:1-amd64", "r/i:1-arm64"]
    # The field carries the LEADING SPACE. This is the assertion that keeps the human-readable line byte-identical to the twin's.
    assert port.source_images_field("r/i", "1") == " r/i:1-amd64 r/i:1-arm64"


def test_the_platform_filter_matches_grep_e_on_a_corpus() -> None:
    """The port reimplements `grep -E "(Platform:|Name:)" | head -10`, so the two are run over the same awkward inputs rather than assumed equal."""
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
    # pipeline IS the thing under comparison and `bash -c` is what the twin itself used. It also keeps the argv a list, which is this repo's rule.
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


def test_the_registry_constant_is_still_constants_shs() -> None:
    """`constants.sh` is NOT a twin and is not going anywhere: it is the shared source of the registry default, so drift between it and the port's copy is still a live risk."""
    text = CONSTANTS.read_text(encoding="utf-8")
    registry = re.search(
        r'^PUBLISH_DOCKER_REGISTRY="\$\{PUBLISH_DOCKER_REGISTRY:-([^}]*)\}"$', text, re.MULTILINE
    )
    assert registry is not None, "the registry default moved in constants.sh"
    assert registry.group(1) == port.REGISTRY_DEFAULT


# --------------------------------------------------------------------------- The controls: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_dropped_arch_is_caught_only_by_the_call_log(tmp_path: pathlib.Path) -> None:
    """PROVE THE GOLDENS CAN FIRE. The plant drops arm64 from the ARGV handed to docker, at the call site, so the printed `Sources:` line still names both architectures. That is exactly the mistake that publishes a silently single-arch manifest under a name every consumer reads as multi-arch: every printed byte and the exit code are unchanged by it.

    Planting it one layer down, in `source_images()`, was tried first and is the WRONG plant -- it also rewrites the `Sources:` line, so stderr diverges and the test proves nothing about the call log.
    """
    source = PORT_FILE.read_text(encoding="utf-8")
    plant = source.replace(
        '        ["buildx", "imagetools", "create", "-t", manifest_tag, *sources],',
        '        ["buildx", "imagetools", "create", "-t", manifest_tag, *sources[:1]],',
    )
    assert plant != source, "the plant did not apply; the control is broken, not the gate"

    name = "a-single-image-at-tag-one-two-three"
    want = recorded(name)
    got = drive(tmp_path / "bad", name, port_source=plant)
    assert got[0] == want[0], "the plant changed the exit code; wrong plant"
    assert got[1] == want[1], "the plant changed stdout; wrong plant"
    assert got[2] == want[2], "the plant changed stderr; wrong plant"
    assert got[3] != want[3], "THE CALL LOG DID NOT SEE IT: this gate cannot fail"
    assert "1.2.3-arm64" not in got[3].splitlines()[0]

    compare(tmp_path / "good", name)
    assert PORT_FILE.read_text(encoding="utf-8") == source


def test_a_planted_skip_of_the_latest_manifest_is_caught(tmp_path: pathlib.Path) -> None:
    """THE NEW CONTROL ON THE GOLDENS. Push the version manifest and forget `:latest`.

    Nothing verifies `:latest` -- that is the defect two tests above -- so dropping its `create` changes no message, no exit code and no verification. `docker pull <image>` then serves whatever the previous release left behind. The recorded call log for the happy path is the only witness, and it holds two creates. The mutation is written to a throwaway copy; the tracked port
    is never touched.
    """
    source = PORT_FILE.read_text(encoding="utf-8")
    anchor = '    if opts.push_latest and not create_manifest("%s:latest" % image_path, sources):\n'
    assert source.count(anchor) == 1, "the plant's anchor moved"
    plant = source.replace(anchor, "    if False:\n")

    with pytest.raises(AssertionError):
        compare(tmp_path / "bad", "the-happy-path", port_source=plant)
    compare(tmp_path / "good", "the-happy-path")
    assert PORT_FILE.read_text(encoding="utf-8") == source
