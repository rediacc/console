"""Differential: `rediacc_ci.deploy.promote_docker_to_stable_hotfix` against its
twin `.ci/scripts/deploy/promote-docker-to-stable-hotfix.sh`.

A RECORDING FAKE `docker` ON A SCRATCH PATH. Nothing here reaches GHCR: the fake logs its exact argv and answers from the environment, and no case names a real credential. `.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one real run" clause and says in as many words that the mocked parity ledger is a separate, achievable piece of work. This is that piece.

THE CALL LOG IS THE EVIDENCE HERE, MORE THAN THE STREAMS, and the fake is built to make that true rather than to hide it: its stdout line is CONSTANT, not derived from the reference it was handed. So a port that promoted stable BACKWARDS onto edge, or that tagged `:latest`, would produce identical stdout, identical stderr and an identical exit code, and only the recorded argv
catches it. `test_planted_defect_is_caught_only_by_the_call_log` plants exactly that and shows all three agreeing while the log does not.

BOTH DIRECTIONS ARE DRIVEN. A partial failure is compared as carefully as the happy path, because the interesting property of this script is WHICH images are already promoted when it stops.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.deploy import promote_docker_to_stable_hotfix as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "deploy" / "promote-docker-to-stable-hotfix.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT_FILE = ROOT / ".ci" / "rediacc_ci" / "deploy" / "promote_docker_to_stable_hotfix.py"
BASH = shutil.which("bash") or "/bin/bash"

# THE STDOUT LINE IS DELIBERATELY CONSTANT. See the module docstring: it is what makes the call log the only witness to WHICH reference was promoted.
FAKE_DOCKER = """#!/usr/bin/python3
import os
import sys

argv = sys.argv[1:]
log = os.environ["FAKE_CALL_LOG"]
with open(log, "a") as fh:
    fh.write("docker\\t" + "\\t".join(argv) + "\\n")
with open(log) as fh:
    call_index = len([line for line in fh if line.startswith("docker\\t")])

fail_on = os.environ.get("FAKE_FAIL_ON_CALL", "")
rc = int(os.environ.get("FAKE_DOCKER_RC", "0"))
if rc or (fail_on and str(call_index) == fail_on):
    sys.stderr.write("ERROR: failed to create manifest list: unauthorized\\n")
    sys.exit(rc or 6)

sys.stdout.write("Created: <redacted>\\n")
"""

# common.sh needs `dirname` at source time (SCRIPT_DIR) and `uname`/`tr` in its detection helpers. Nothing else is on the scratch PATH, so a tool leaking in would be visible as a behaviour change rather than as a silent convenience.
PATH_MINIMUM = ("dirname", "uname", "tr")


def _bin(root: pathlib.Path, *, drop: str = "", docker_body: str = FAKE_DOCKER) -> str:
    stub = root / "fixture-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
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
    """A throwaway repository holding both implementations.

    BOTH SIDES ARE COPIED IN rather than invoked from this checkout, because each resolves its own neighbours from its own location. A test that ran the real files would drive them against the real tree.
    """
    root = tmp_path / "repo"
    (root / ".ci" / "scripts" / "deploy").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "rediacc_ci" / "deploy").mkdir(parents=True, exist_ok=True)
    shutil.copy2(TWIN, root / ".ci" / "scripts" / "deploy" / TWIN.name)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / COMMON.name)
    shutil.copy2(PORT_FILE, root / ".ci" / "rediacc_ci" / "deploy" / PORT_FILE.name)
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
    call_log = root / f"{side}-calls.log"
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
        argv = [BASH, str(root / ".ci" / "scripts" / "deploy" / TWIN.name)]
    else:
        argv = [sys.executable, str(root / ".ci" / "rediacc_ci" / "deploy" / PORT_FILE.name)]
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


def _agree(old, new, label: str, old_calls: str = "", new_calls: str = "") -> None:
    """THE THREE STREAMS ARE COMPARED SEPARATELY, plus the call log.

    `2>&1` is the reflex and it destroys the defect class these tests exist for: a message moving between stdout and stderr is invisible once the two are merged.
    """
    assert new.returncode == old.returncode, (
        f"{label}: exit diverged: {old.returncode!r} vs {new.returncode!r}\n"
        f"old stderr: {old.stderr!r}\nnew stderr: {new.stderr!r}"
    )
    assert new.stdout == old.stdout, f"{label}: stdout diverged:\n{old.stdout!r}\n{new.stdout!r}"
    assert new.stderr == old.stderr, f"{label}: stderr diverged:\n{old.stderr!r}\n{new.stderr!r}"
    assert new_calls == old_calls, f"{label}: call log diverged:\n{old_calls}\n---\n{new_calls}"


# --------------------------------------------------------------------------- The three code paths, driven end to end ---------------------------------------------------------------------------


def test_happy_path_promotes_three_images_identically(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path)
    _agree(old, new, "happy", old_calls, new_calls)

    assert old.returncode == 0, old.stderr
    assert old.stdout.splitlines() == [
        "Promoting renet: edge -> stable",
        "Created: <redacted>",
        "Promoting rdc: edge -> stable",
        "Created: <redacted>",
        "Promoting server: edge -> stable",
        "Created: <redacted>",
        "Docker promoted to stable",
    ], old.stdout
    assert old.stderr == ""

    # THE SHAPE, not just the verdict: three calls, in this order, each copying edge onto stable and never the reverse.
    head = "docker\tbuildx\timagetools\tcreate\t-t\t"
    assert old_calls.splitlines() == [
        head + "ghcr.io/rediacc/renet:stable\tghcr.io/rediacc/renet:edge",
        head + "ghcr.io/rediacc/rdc:stable\tghcr.io/rediacc/rdc:edge",
        head + "ghcr.io/rediacc/server:stable\tghcr.io/rediacc/server:edge",
    ], old_calls


def test_a_failure_on_the_first_call_stops_before_the_other_two(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, FAKE_FAIL_ON_CALL="1")
    _agree(old, new, "fail-first", old_calls, new_calls)

    assert old.returncode == 6, old.returncode
    assert old.stdout == "Promoting renet: edge -> stable\n"
    assert old.stderr == "ERROR: failed to create manifest list: unauthorized\n"
    assert len(old_calls.splitlines()) == 1, old_calls


def test_a_failure_on_the_last_call_leaves_two_images_already_promoted(tmp_path) -> None:
    """THE HALF-PROMOTION IS THE POINT. renet and rdc are at the new version and
    server is not, and the run says nothing about it beyond docker's own error.
    """
    old, new, old_calls, new_calls = run_both(tmp_path, FAKE_FAIL_ON_CALL="3")
    _agree(old, new, "fail-last", old_calls, new_calls)

    assert old.returncode == 6
    assert "Promoting server: edge -> stable" in old.stdout
    assert "Docker promoted to stable" not in old.stdout
    assert len(old_calls.splitlines()) == 3, old_calls


def test_a_missing_docker_refuses_before_any_call(tmp_path) -> None:
    old, new, old_calls, new_calls = run_both(tmp_path, drop="docker")
    _agree(old, new, "no-docker", old_calls, new_calls)

    assert old.returncode == 1
    assert old.stdout == ""
    assert old.stderr == "✗ Required command 'docker' is not available\n", repr(old.stderr)
    assert old_calls == "", "a refused run still called docker"


def test_extra_arguments_are_ignored_by_both(tmp_path) -> None:
    """NOT AN ACADEMIC CASE. `--dry-run` looks like it would be honoured and is
    not: the twin parses no argv at all, so a caller reaching for a safety flag gets a real promotion. Recorded as agreement rather than as a wish.
    """
    old, new, old_calls, new_calls = run_both(tmp_path, ["--dry-run", "extra"])
    _agree(old, new, "argv", old_calls, new_calls)
    assert old.returncode == 0
    assert len(old_calls.splitlines()) == 3


# --------------------------------------------------------------------------- The stream-ordering control, which is what `_flush` exists for ---------------------------------------------------------------------------


def test_the_ports_own_lines_interleave_with_dockers_in_the_twins_order(tmp_path) -> None:
    """A PIPE, NOT A TERMINAL, because that is where the divergence lives.

    Python block-buffers stdout against a pipe and flushes at exit, while the docker child writes straight to the inherited descriptor. Without `port._flush` the three `Promoting ...` lines all arrive AFTER the three `Created:` lines, with byte-identical content in the wrong order. Both exits are 0 and the call log is identical, so this comparison is the only witness.
    """
    root = fixture(tmp_path)
    env = {
        "PATH": _bin(root),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(root / "pipe-calls.log"),
    }
    (root / "pipe-calls.log").write_text("", encoding="utf-8")
    # NO SHELL AND NO `| cat`. `capture_output=True` already hands the child a
    # PIPE for stdout, which is the whole condition under test: block buffering is chosen by the descriptor's type, not by there being a downstream process. Spelling it with a pipeline would add a shell for nothing.
    piped = subprocess.run(
        [sys.executable, str(root / ".ci" / "rediacc_ci" / "deploy" / PORT_FILE.name)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(root),
        check=False,
        timeout=120,
        input="",
    )
    assert piped.returncode == 0, piped.stderr
    assert piped.stdout.splitlines()[:2] == [
        "Promoting renet: edge -> stable",
        "Created: <redacted>",
    ], piped.stdout


# --------------------------------------------------------------------------- The planted defect: three streams agree and the call log does not ---------------------------------------------------------------------------


def test_planted_defect_is_caught_only_by_the_call_log(tmp_path) -> None:
    """PROVE THE DIFFERENTIAL CAN FIRE, and prove WHICH assertion fires.

    The plant swaps `-t <dst>` and `<src>`, which is the mistake that promotes stable backwards onto edge. Every printed byte and the exit code are unchanged by it, so this test also demonstrates that a streams-only comparison would have called the defective port equivalent.
    """
    root = fixture(tmp_path)
    target = root / ".ci" / "rediacc_ci" / "deploy" / PORT_FILE.name
    source = target.read_text(encoding="utf-8")
    swapped = source.replace(
        "        image_ref(image, TARGET_TAG),\n        image_ref(image, SOURCE_TAG),\n",
        "        image_ref(image, SOURCE_TAG),\n        image_ref(image, TARGET_TAG),\n",
    )
    assert swapped != source, "the plant did not apply; the control is broken, not the gate"
    target.write_text(swapped, encoding="utf-8")

    old, old_calls = _run(root, "old", [])
    new, new_calls = _run(root, "new", [])

    assert new.returncode == old.returncode, "the plant changed the exit code; wrong plant"
    assert new.stdout == old.stdout, "the plant changed stdout; wrong plant"
    assert new.stderr == old.stderr, "the plant changed stderr; wrong plant"
    assert new_calls != old_calls, "THE CALL LOG DID NOT SEE THE SWAP: this gate cannot fail"
    assert "ghcr.io/rediacc/renet:edge\tghcr.io/rediacc/renet:stable" in new_calls


# --------------------------------------------------------------------------- The named vacuity fact ---------------------------------------------------------------------------


def test_defect_no_post_promotion_verification(tmp_path) -> None:
    """A docker THAT DOES NOTHING AND EXITS 0 produces a clean promotion report.

    The fake is replaced by one that records nothing and touches nothing. Both implementations print the same seven-line success and exit 0. That is the
    twin's behaviour and the port reproduces it; repairing it is a cutover-box
    decision, not this one's.
    """
    assert port.NO_POST_PROMOTION_VERIFICATION is True

    silent = "#!/usr/bin/python3\nimport sys\nsys.exit(0)\n"
    old, new, old_calls, new_calls = run_both(tmp_path, docker_body=silent)
    _agree(old, new, "silent-docker", old_calls, new_calls)
    assert old.returncode == 0
    assert old.stdout.rstrip("\n").endswith("Docker promoted to stable")
    assert old_calls == "", "the silent fake recorded a call; the case is not what it says"


# --------------------------------------------------------------------------- Pure helpers, exercised directly ---------------------------------------------------------------------------


def test_the_image_sequence_is_the_twins_and_the_server_image_is_last() -> None:
    assert port.images() == ("renet", "rdc", "server")
    assert port.LOOP_IMAGES == ("renet", "rdc")
    assert port.STANDALONE_IMAGE == "server"


def test_promote_argv_puts_the_target_behind_t_and_the_source_last() -> None:
    argv = port.promote_argv("renet")
    assert argv == [
        "docker",
        "buildx",
        "imagetools",
        "create",
        "-t",
        "ghcr.io/rediacc/renet:stable",
        "ghcr.io/rediacc/renet:edge",
    ]
    # The NEGATIVE half: the source must not be the stable tag, which is the exact shape the planted defect above produces.
    assert argv[-1].endswith(":edge")


def test_image_ref_and_announce_carry_the_twins_bytes() -> None:
    assert port.image_ref("server", "stable") == "ghcr.io/rediacc/server:stable"
    assert port.announce("rdc") == "Promoting rdc: edge -> stable"
