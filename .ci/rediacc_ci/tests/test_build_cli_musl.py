"""Differential: `rediacc_ci.build.build_cli_musl` against its twin
`.ci/scripts/build/build-cli-musl.sh`.

ONE REAL INVOCATION PULLS `node:22-alpine`, RUNS `npm ci` INSIDE IT AND WRITES
INTO `dist/cli/` OF WHATEVER TREE IT IS POINTED AT. It also runs
`sudo chown -R` over that directory. Nothing here goes near a real one: every
case runs with a PATH that REPLACES the caller's rather than prepending to it,
and `test_the_scratch_path_cannot_reach_a_real_docker_or_sudo` asserts the real
binaries are unreachable from it before anything is driven. A prepended PATH
would still resolve whatever the developer has installed, which is how a
previous wave nearly let a stub reach into the live checkout.

THE CALL LOG IS THE EVIDENCE. Both sides produce the same three log lines on a
successful run no matter what argv they hand `docker`, so a port that swapped
`--platform`, dropped the `-v` mount, forgot an `-e`, or shipped a different
container script would pass on stdout, stderr and exit code alone.
`test_a_planted_defect_is_caught_only_by_the_call_log` plants exactly that.

RECORDING FAKES LOG TO STDERR, NEVER STDOUT. This script's stdout is empty on
every path except `--help`, and a fake writing to stdout would invent a
difference that is the fake's, not the port's. They write to `$FAKE_CALL_LOG`
instead, and the `FAKEBIN ` prefix is also what the K=5 ledger scopes
`--finding-re` to: `shadow-gate.ts` classifies any line opening `-> ` or `ok `
as CHATTER before any message regex is consulted, and every one of this
script's own lines is exactly that, so a ledger keyed on message text alone
would record `VACUOUS_BOTH_EMPTY` on every row.

`rediacc_ci` IS VENDORED INTO THE FIXTURE rather than reached through an
absolute `PYTHONPATH`: it proves the port's dependency set, and
`scripts/lib/shadow-gate.ts --record` refuses a command string naming an
absolute path outside the recorded tree.

`$0` IS MASKED TO `<SELF>`. bash names the script in its `set -u` death and in
its `--help` usage; `sys.argv[0]` ends `.py`. Nothing else is masked, and stdout
and stderr are compared SEPARATELY.

K=5 LEDGER: `.ci/shadow/w7p6-build-cli-musl.observations.jsonl`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.build import build_cli_musl as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()

TWIN_REL = ".ci/scripts/build/build-cli-musl.sh"
PORT_REL = ".ci/rediacc_ci/build/build_cli_musl.py"
COMMON_REL = ".ci/scripts/lib/common.sh"
INJECT_REL = ".ci/scripts/version/inject-env.sh"

VENDORED = (
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/log.py",
    ".ci/rediacc_ci/paths.py",
    ".ci/rediacc_ci/core/__init__.py",
    ".ci/rediacc_ci/core/common.py",
    ".ci/rediacc_ci/build/__init__.py",
)

BASH = shutil.which("bash") or "/bin/bash"

# `dirname`/`uname` because sourcing common.sh runs `detect_os`/`detect_arch`;
# `mkdir`/`mv`/`rm`/`id`/`wc`/`cat`/`sed`/`sha256sum` because the twin genuinely
# calls them and their behaviour is deterministic, so they are REAL rather than
# faked. Anything not listed is ABSENT, including `docker`, `sudo` and `shasum`.
#
# `id` is on the list for a reason worth writing down. Leaving it off made the
# twin's `$(id -u)` expand to the empty string, so it ran `sudo chown -R :` while
# the port -- which cannot lose `os.getuid()` -- ran `sudo chown -R 1000:1000`.
# That is the exact divergence the port's docstring names, and it showed up here
# as a MISMATCH that had nothing to do with the port's logic. The fixture
# supplies `id` so the comparison is about the script.
PATH_MINIMUM = (
    "dirname",
    "uname",
    "sed",
    "sha256sum",
    "cat",
    "mkdir",
    "mv",
    "rm",
    "id",
    "wc",
)

# The two recording fakes. `docker` optionally WRITES the artifact the twin then
# checks for, so the success path can be driven end to end; `sudo` records and
# does nothing, exactly as a `chown` that is allowed to fail.
FAKE_DOCKER = """#!/bin/bash
{
    printf 'FAKEBIN docker'
    for a in "$@"; do printf '\\t%s' "${a//$'\\n'/\\\\n}"; done
    printf '\\n'
} >>"$FAKE_CALL_LOG"
if [[ -n "${FAKE_DOCKER_PRODUCES:-}" ]]; then
    mkdir -p "$(dirname "$FAKE_DOCKER_PRODUCES")"
    printf 'MUSL-SEA-BINARY\\n' >"$FAKE_DOCKER_PRODUCES"
fi
if [[ -n "${FAKE_DOCKER_CHECKSUM:-}" ]]; then
    printf '%s  %s\\n' "0000deadbeef" "rdc-linux-x64" >"$FAKE_DOCKER_CHECKSUM"
fi
if [[ "${FAKE_DOCKER_RC:-0}" != 0 ]]; then
    echo 'docker: Error response from daemon: pull access denied' >&2
    exit "$FAKE_DOCKER_RC"
fi
exit 0
"""

FAKE_SUDO = """#!/bin/bash
{
    printf 'FAKEBIN sudo'
    for a in "$@"; do printf '\\t%s' "${a//$'\\n'/\\\\n}"; done
    printf '\\n'
} >>"$FAKE_CALL_LOG"
exit 0
"""

# The version seam at `:82`. `--strict` refuses `0.0.0-dev`-shaped values; the
# fake reproduces the decision by exit code alone, which is all the twin reads.
FAKE_INJECT_ENV = """#!/bin/bash
{
    printf 'FAKEBIN inject-env'
    for a in "$@"; do printf '\\t%s' "${a//$'\\n'/\\\\n}"; done
    printf '\\n'
} >>"$FAKE_CALL_LOG"
echo 'CLI_VERSION resolved'
if [[ "${FAKE_INJECT_RC:-0}" != 0 ]]; then exit "$FAKE_INJECT_RC"; fi
exit 0
"""

SELF_RE = re.compile(r"\S*(?:%s|%s)" % (re.escape(TWIN_REL), re.escape(PORT_REL)))


def fixture(
    tmp_path: pathlib.Path,
    *,
    port_source: str | None = None,
    stale_output: bool = False,
) -> pathlib.Path:
    root = tmp_path / "repo"
    for rel in (TWIN_REL, PORT_REL, COMMON_REL, INJECT_REL, *VENDORED):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
    for rel in (TWIN_REL, COMMON_REL, *VENDORED):
        shutil.copy2(ROOT / rel, root / rel)
    if port_source is None:
        shutil.copy2(ROOT / PORT_REL, root / PORT_REL)
    else:
        (root / PORT_REL).write_text(port_source, encoding="utf-8")
    (root / INJECT_REL).write_text(FAKE_INJECT_ENV, encoding="utf-8")
    (root / INJECT_REL).chmod(0o755)
    (root / "dist" / "cli").mkdir(parents=True, exist_ok=True)
    if stale_output:
        # DEFECT 2's input: an artifact a PREVIOUS build left behind.
        (root / "dist" / "cli" / "rdc-linux-x64").write_text(
            "STALE-GLIBC-BINARY\n", encoding="utf-8"
        )
    return root


def scratch_bin(
    root: pathlib.Path,
    *,
    drop_docker: bool = False,
    drop_checksum_tools: bool = False,
) -> str:
    """The ONLY directory on PATH for either side."""
    stub = root / "fixture-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for name in PATH_MINIMUM:
        if drop_checksum_tools and name == "sha256sum":
            link = stub / name
            if link.exists() or link.is_symlink():
                link.unlink()
            continue
        real = shutil.which(name)
        assert real is not None, "%s is missing from this machine" % name
        link = stub / name
        if not link.exists():
            link.symlink_to(real)
    docker = stub / "docker"
    if drop_docker:
        if docker.exists():
            docker.unlink()
    else:
        docker.write_text(FAKE_DOCKER, encoding="utf-8")
        docker.chmod(0o755)
    sudo = stub / "sudo"
    sudo.write_text(FAKE_SUDO, encoding="utf-8")
    sudo.chmod(0o755)
    return str(stub)


def _run(
    root: pathlib.Path,
    side: str,
    *,
    args: tuple[str, ...] = (),
    drop_docker: bool = False,
    drop_checksum_tools: bool = False,
    produces: bool = False,
    checksum: bool = False,
    env_overrides: dict[str, str | None] | None = None,
):
    call_log = root / ("%s-calls.log" % side)
    call_log.write_text("", encoding="utf-8")
    env = {
        # REPLACED, never prepended.
        "PATH": scratch_bin(root, drop_docker=drop_docker, drop_checksum_tools=drop_checksum_tools),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "NO_COLOR": "1",
        "PYTHONPATH": str(root / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
    }
    if produces:
        env["FAKE_DOCKER_PRODUCES"] = str(root / "dist" / "cli" / "rdc-linux-x64")
    if checksum:
        env["FAKE_DOCKER_CHECKSUM"] = str(root / "dist" / "cli" / "rdc-linux-x64.sha256")
    for key, value in (env_overrides or {}).items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    argv = [BASH, str(root / TWIN_REL)] if side == "old" else [sys.executable, str(root / PORT_REL)]
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


def _artifacts(root: pathlib.Path) -> dict[str, str]:
    """Every file under `dist/`, so a port that wrote the right log lines and the
    wrong bytes cannot pass. Keyed by path relative to the fixture root."""
    out: dict[str, str] = {}
    dist = root / "dist"
    if not dist.is_dir():
        return out
    for path in sorted(dist.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(root))] = path.read_text(encoding="utf-8", errors="replace")
    return out


def _reset(root: pathlib.Path, *, stale_output: bool = False) -> None:
    """Between the two sides: the tree as it was before either ran."""
    shutil.rmtree(root / "dist", ignore_errors=True)
    (root / "dist" / "cli").mkdir(parents=True, exist_ok=True)
    if stale_output:
        (root / "dist" / "cli" / "rdc-linux-x64").write_text(
            "STALE-GLIBC-BINARY\n", encoding="utf-8"
        )


def run_both(root: pathlib.Path, *, stale_output: bool = False, **kw):
    _reset(root, stale_output=stale_output)
    old, old_calls = _run(root, "old", **kw)
    old_files = _artifacts(root)
    _reset(root, stale_output=stale_output)
    new, new_calls = _run(root, "new", **kw)
    new_files = _artifacts(root)
    return (old, old_calls, old_files), (new, new_calls, new_files)


def _mask(text: str) -> str:
    return SELF_RE.sub("<SELF>", text)


def _agree(old_t, new_t, label: str) -> None:
    old, old_calls, old_files = old_t
    new, new_calls, new_files = new_t
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
    assert new_calls == old_calls, "%s: call log diverged:\n%s---\n%s" % (
        label,
        old_calls,
        new_calls,
    )
    assert new_files == old_files, "%s: artifacts diverged:\n%r\n%r" % (
        label,
        sorted(old_files),
        sorted(new_files),
    )


def _docker_argv(calls: str) -> list[str]:
    lines = [ln for ln in calls.splitlines() if ln.startswith("FAKEBIN docker")]
    assert len(lines) == 1, "expected exactly one docker call, got %r" % calls
    return lines[0].split("\t")


# ---------------------------------------------------------------------------
# The control on the control
# ---------------------------------------------------------------------------


def test_the_scratch_path_cannot_reach_a_real_docker_or_sudo(tmp_path) -> None:
    """A real run pulls an image, runs `npm ci` in it and `sudo chown -R`s a
    directory, so the seal on the PATH is load-bearing rather than tidy.
    Asserted in both directions."""
    root = fixture(tmp_path)
    sealed = scratch_bin(root)
    assert shutil.which("docker", path=sealed) == str(root / "fixture-bin" / "docker")
    assert shutil.which("sudo", path=sealed) == str(root / "fixture-bin" / "sudo")
    dropped = scratch_bin(root, drop_docker=True)
    assert shutil.which("docker", path=dropped) is None, "a real docker is reachable"
    assert shutil.which("podman", path=dropped) is None
    assert shutil.which("npm", path=dropped) is None
    assert shutil.which("shasum", path=dropped) is None


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def test_no_arguments_refuses_naming_the_missing_flag(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root)
    assert old_t[0].returncode == 1
    assert old_t[0].stderr == "\u2717 Missing required argument: --arch\n"
    assert old_t[1] == "", "nothing should have been executed"
    _agree(old_t, new_t, "no-args")


def test_help_prints_usage_on_stdout_and_exits_zero(tmp_path) -> None:
    root = fixture(tmp_path)
    for flag in ("-h", "--help"):
        old_t, new_t = run_both(root, args=(flag,))
        assert old_t[0].returncode == 0
        assert old_t[0].stderr == ""
        assert old_t[0].stdout.startswith("Usage: ")
        assert old_t[0].stdout.endswith(" --arch ARCH [--output DIR] [--dry-run]\n")
        _agree(old_t, new_t, flag)


def test_an_unknown_option_refuses_and_names_it(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--nope",))
    assert old_t[0].returncode == 1
    assert old_t[0].stderr == "\u2717 Unknown option: --nope\n"
    _agree(old_t, new_t, "unknown-option")


def test_a_flag_with_no_value_dies_the_way_set_u_does(tmp_path) -> None:
    """`--arch` as the final argument makes bash expand `"$2"` with nothing
    behind it. The sentence names the script and the LINE, so the port forges it
    with the twin's line numbers and `$0` is masked on both sides."""
    root = fixture(tmp_path)
    for flag, line in (("--arch", 28), ("--output", 32)):
        old_t, new_t = run_both(root, args=(flag,))
        assert old_t[0].returncode == 1
        assert old_t[0].stderr == "%s: line %d: $2: unbound variable\n" % (
            str(root / TWIN_REL),
            line,
        )
        assert old_t[0].stdout == ""
        _agree(old_t, new_t, flag)


# ---------------------------------------------------------------------------
# --dry-run, including DEFECT 1
# ---------------------------------------------------------------------------


def test_dry_run_previews_and_executes_nothing(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--arch", "x64", "--dry-run"))
    assert old_t[0].returncode == 0
    assert old_t[1] == "", "a dry run must not shell out to anything"
    assert "[DRY-RUN] Would build rdc-linux-musl-x64" in old_t[0].stderr
    _agree(old_t, new_t, "dry-run")


def test_defect_dry_run_previews_an_architecture_the_real_run_rejects(tmp_path) -> None:
    """DEFECT 1. The `case` that rejects a bad `--arch` is at `:90-97`, AFTER the
    dry-run `exit 0` at `:68`, so the preview reports a binary that can never be
    built and exits 0. Both halves are asserted: the lie under `--dry-run`, and
    the refusal without it, from the SAME argument."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--arch", "banana", "--dry-run"))
    assert old_t[0].returncode == 0, "the defect is that this is a PASS"
    assert "[DRY-RUN] Would build rdc-linux-musl-banana" in old_t[0].stderr
    assert "Invalid architecture" not in old_t[0].stderr
    _agree(old_t, new_t, "dry-run-bad-arch")

    real_t, real_new_t = run_both(root, args=("--arch", "banana"))
    assert real_t[0].returncode == 1
    assert "\u2717 Invalid architecture 'banana'. Must be x64 or arm64\n" in real_t[0].stderr, (
        real_t[0].stderr
    )
    _agree(real_t, real_new_t, "real-bad-arch")


def test_a_missing_docker_refuses_through_require_cmd(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--arch", "x64"), drop_docker=True)
    assert old_t[0].returncode == 1
    assert old_t[0].stderr.endswith("\u2717 Required command 'docker' is not available\n")
    _agree(old_t, new_t, "no-docker")


# ---------------------------------------------------------------------------
# The release seam
# ---------------------------------------------------------------------------


def test_release_build_without_a_version_refuses_before_docker(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=("--arch", "x64"),
        env_overrides={"RELEASE_BUILD": "true", "CLI_VERSION": ""},
    )
    assert old_t[0].returncode == 1
    assert "RELEASE_BUILD=true but CLI_VERSION is empty" in old_t[0].stderr
    assert "FAKEBIN docker" not in old_t[1]
    _agree(old_t, new_t, "release-no-version")


def test_release_build_consults_inject_env_and_discards_only_its_stdout(tmp_path) -> None:
    """`:82` redirects the helper's STDOUT to /dev/null and reads its status.
    The fake prints on stdout, so a port that let it through would show up here."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=("--arch", "x64"),
        produces=True,
        env_overrides={"RELEASE_BUILD": "true", "CLI_VERSION": "1.2.3"},
    )
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert "CLI_VERSION resolved" not in old_t[0].stdout
    assert "FAKEBIN inject-env\t--version\t1.2.3\t--strict\t--print" in old_t[1]
    _agree(old_t, new_t, "release-ok")


def test_a_rejected_version_stops_the_build(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=("--arch", "x64"),
        env_overrides={
            "RELEASE_BUILD": "true",
            "CLI_VERSION": "0.0.0-dev",
            "FAKE_INJECT_RC": "3",
        },
    )
    assert old_t[0].returncode == 1, "the twin flattens inject-env's 3 to its own 1"
    assert "Release build refused: CLI_VERSION='0.0.0-dev'" in old_t[0].stderr
    assert "FAKEBIN docker" not in old_t[1]
    _agree(old_t, new_t, "release-refused")


# ---------------------------------------------------------------------------
# The build itself
# ---------------------------------------------------------------------------


def test_the_success_path_builds_renames_and_checksums(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--arch", "x64"), produces=True)
    old = old_t[0]
    assert old.returncode == 0, old.stderr
    assert old.stdout == ""
    assert "\u2713 Musl binary: " in old.stderr
    assert "(0MB)" in old.stderr, "DEFECT 3: two floor divisions"
    assert "\u2713 CLI musl build complete: " in old.stderr
    assert set(old_t[2]) == {"dist/cli/rdc-linux-musl-x64", "dist/cli/rdc-linux-musl-x64.sha256"}
    assert old_t[2]["dist/cli/rdc-linux-musl-x64"] == "MUSL-SEA-BINARY\n"
    assert old_t[2]["dist/cli/rdc-linux-musl-x64.sha256"].endswith("  rdc-linux-musl-x64\n")
    _agree(old_t, new_t, "success")


def test_the_docker_argv_is_the_whole_point_of_the_script(tmp_path) -> None:
    """Exit code, stdout and stderr are identical no matter what argv reaches
    docker, so this pins the recorded argv against the port's own builder."""
    root = fixture(tmp_path)
    _reset(root)
    old, _ = _run(root, "old", args=("--arch", "arm64"), produces=False)
    assert old.returncode == 1, "no artifact was produced, so the twin refuses"
    recorded = _docker_argv((root / "old-calls.log").read_text(encoding="utf-8"))
    expected = port.docker_argv(
        platform="linux/arm64",
        repo_root=str(root),
        arch="arm64",
        ci="",
        cli_version="",
        release_build="",
    )
    # The fake escapes newlines so a multi-line argument (the container script,
    # which is the LAST one) survives a line-oriented call log; the expectation
    # is escaped the same way rather than the log being made multi-line, because
    # `shadow-gate.ts` reads findings line by line too.
    assert recorded == ["FAKEBIN docker", *(a.replace("\n", "\\n") for a in expected[1:])]
    assert expected[expected.index("--platform") + 1] == "linux/arm64"
    assert "%s:/workspace" % root in expected
    assert "CLI_VERSION=0.0.0-dev" in expected, "the `${CLI_VERSION:-0.0.0-dev}` default"
    assert expected[-1].rstrip().endswith("--platform linux --arch arm64")
    assert recorded[-1].endswith("--platform linux --arch arm64\\n")


def test_ci_and_release_build_reach_the_container_empty_when_unset(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--arch", "x64"), produces=True)
    argv = _docker_argv(old_t[1])
    assert "CI=" in argv
    assert "RELEASE_BUILD=" in argv
    _agree(old_t, new_t, "empty-env-forwarded")

    old2_t, new2_t = run_both(
        root,
        args=("--arch", "x64"),
        produces=True,
        env_overrides={"CI": "true", "CLI_VERSION": "9.9.9"},
    )
    argv2 = _docker_argv(old2_t[1])
    assert "CI=true" in argv2
    assert "CLI_VERSION=9.9.9" in argv2
    _agree(old2_t, new2_t, "set-env-forwarded")


def test_a_failing_docker_returns_its_own_status_not_a_flattened_one(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--arch", "x64"), env_overrides={"FAKE_DOCKER_RC": "17"})
    assert old_t[0].returncode == 17
    _agree(old_t, new_t, "docker-fails")


def test_no_output_from_the_container_is_a_refusal(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--arch", "x64"), produces=False)
    assert old_t[0].returncode == 1
    assert "\u2717 Docker build produced no output: " in old_t[0].stderr
    _agree(old_t, new_t, "no-output")


def test_defect_a_stale_glibc_binary_ships_as_a_musl_one(tmp_path) -> None:
    """DEFECT 2. `:133` is an EXISTENCE test. A `dist/cli/rdc-linux-x64` left by
    an earlier glibc build satisfies it even though this container produced
    nothing, and the file is renamed, checksummed and reported as a finished
    musl build. The assertion is on the CONTENT, because the log lines are
    indistinguishable from a real success."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--arch", "x64"), produces=False, stale_output=True)
    assert old_t[0].returncode == 0, "the defect is that this is a PASS"
    assert old_t[2]["dist/cli/rdc-linux-musl-x64"] == "STALE-GLIBC-BINARY\n"
    assert "\u2713 CLI musl build complete: " in old_t[0].stderr
    _agree(old_t, new_t, "stale-output")


def test_an_existing_checksum_is_rewritten_rather_than_recomputed(tmp_path) -> None:
    """`:146-149`: when the container left a `.sha256`, the twin `sed`s the
    filename inside it and deletes the original instead of hashing again. The
    fake writes a checksum that is deliberately NOT the file's real hash, which
    is the only way to tell the two branches apart."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--arch", "x64"), produces=True, checksum=True)
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert old_t[2]["dist/cli/rdc-linux-musl-x64.sha256"] == "0000deadbeef  rdc-linux-musl-x64\n"
    assert "dist/cli/rdc-linux-x64.sha256" not in old_t[2], "the original must be removed"
    _agree(old_t, new_t, "checksum-rewritten")


def test_with_no_hashing_tool_at_all_no_checksum_is_written_and_it_still_passes(
    tmp_path,
) -> None:
    """The third outcome of `:151-155` that nobody writes down: `command -v`
    finds neither `sha256sum` nor `shasum`, the `if` falls through, and the run
    completes with no checksum file and exit 0."""
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--arch", "x64"), produces=True, drop_checksum_tools=True)
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert set(old_t[2]) == {"dist/cli/rdc-linux-musl-x64"}
    assert "Checksum:" not in old_t[0].stderr
    _agree(old_t, new_t, "no-hash-tool")


def test_output_selects_where_the_binary_lands(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(
        root,
        args=("--arch", "x64", "--output", str(root / "elsewhere")),
        produces=True,
    )
    assert old_t[0].returncode == 0, old_t[0].stderr
    assert (root / "elsewhere" / "rdc-linux-musl-x64").is_file()
    assert "elsewhere/rdc-linux-musl-x64" in old_t[0].stderr
    _agree(old_t, new_t, "output-dir")


def test_sudo_repairs_ownership_of_the_container_written_directory(tmp_path) -> None:
    root = fixture(tmp_path)
    old_t, new_t = run_both(root, args=("--arch", "x64"), produces=True)
    sudo_lines = [ln for ln in old_t[1].splitlines() if ln.startswith("FAKEBIN sudo")]
    assert len(sudo_lines) == 1, old_t[1]
    fields = sudo_lines[0].split("\t")
    assert fields[1:4] == ["chown", "-R", "%d:%d" % (os.getuid(), os.getgid())]
    assert fields[4] == "%s/dist/cli/" % root
    _agree(old_t, new_t, "sudo-chown")


# ---------------------------------------------------------------------------
# The pure helpers, and the planted defect
# ---------------------------------------------------------------------------


def test_parse_args_is_exercised_directly_in_both_directions(tmp_path) -> None:
    del tmp_path
    assert port.parse_args(["--arch", "x64"]) == ("x64", "", False, None, "")
    assert port.parse_args(["--dry-run", "--arch", "arm64", "--output", "/o"]) == (
        "arm64",
        "/o",
        True,
        None,
        "",
    )
    # Must NOT fire: `--dry-run` in any position is still just a flag.
    assert port.parse_args(["--arch", "x64", "--dry-run"])[3] is None
    # Must fire.
    assert port.parse_args(["--wat"])[3] == 1
    assert port.parse_args(["--arch"])[3] == 1


def test_the_container_script_carries_the_arch_and_nothing_else_changes() -> None:
    x64 = port.container_script("x64")
    arm = port.container_script("arm64")
    assert x64.endswith("--platform linux --arch x64\n")
    assert arm.endswith("--platform linux --arch arm64\n")
    assert x64.replace("--arch x64", "--arch arm64") == arm
    assert "apk add --no-cache python3 make g++ binutils bash jq" in x64


def test_a_planted_defect_is_caught_only_by_the_call_log(tmp_path) -> None:
    """The proof that this differential can fail. Swapping the docker platform
    leaves stdout, stderr and the exit code untouched on both sides; only the
    recorded argv can tell, which is why the call log is compared at all."""
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")
    planted = source.replace('"x64": "linux/amd64",', '"x64": "linux/arm64",')
    assert planted != source, "the plant did not apply; fix the control first"
    root = fixture(tmp_path, port_source=planted)
    old_t, new_t = run_both(root, args=("--arch", "x64"), produces=True)
    assert old_t[0].returncode == new_t[0].returncode == 0
    assert old_t[0].stderr == new_t[0].stderr, "the three streams agree, which is the point"
    assert old_t[2] == new_t[2], "the artifacts agree too"
    assert old_t[1] != new_t[1], "the call log MUST diverge, or this suite proves nothing"
    assert "linux/amd64" in old_t[1]
    assert "linux/arm64" in new_t[1]
