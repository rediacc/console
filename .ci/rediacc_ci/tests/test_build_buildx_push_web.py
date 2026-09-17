"""Differential: `rediacc_ci.build.buildx_push_web` against its twin `.ci/scripts/build/buildx-push-web.sh`.

THE REAL SCRIPT PUSHES TO ghcr.io. `--push` is unconditional and there is no dry-run branch, so one real invocation is a registry write; every case here runs against a RECORDING FAKE `docker` on a PATH that REPLACES the caller's rather than prepending to it, and `test_the_scratch_path_cannot_reach_a_real_docker` asserts the real binary is unreachable before anything is driven. A
prepended PATH is not good enough: it still resolves whatever the developer has installed.

THE CALL LOG IS THE EVIDENCE. The fake prints nothing that depends on its arguments, so a port that swapped two `--build-arg` values, dropped `--push`, or built the wrong `--target` would produce identical stdout, identical stderr and an identical exit code. `test_a_planted_defect_is_caught_only_by_the_call_log` plants exactly that and asserts the three streams agree while the log
does not.

`rediacc_ci` IS VENDORED INTO THE FIXTURE rather than reached through an absolute `PYTHONPATH`, both because it proves the port's dependency set and because `scripts/lib/shadow-gate.ts --record` refuses a command string naming an absolute path outside the recorded tree.

`$0` IS MASKED TO `<SELF>`: bash names the script in its five `${VAR:?...}`
refusals and `sys.argv[0]` ends `.py`. Nothing else is masked, and both streams are compared SEPARATELY.

K=5 LEDGER: `.ci/shadow/w7p6-buildx-push-web.observations.jsonl`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.build import buildx_push_web as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()

TWIN_REL = ".ci/scripts/build/buildx-push-web.sh"
PORT_REL = ".ci/rediacc_ci/build/buildx_push_web.py"
COMMON_REL = ".ci/scripts/lib/common.sh"

VENDORED = (
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/log.py",
    ".ci/rediacc_ci/paths.py",
    ".ci/rediacc_ci/core/__init__.py",
    ".ci/rediacc_ci/core/common.py",
    ".ci/rediacc_ci/build/__init__.py",
)

BASH = shutil.which("bash") or "/bin/bash"

# `dirname` for the twin's own `SCRIPT_DIR` (:23), `uname` because sourcing common.sh runs `detect_os`/`detect_arch` at :509-510. Anything not listed is ABSENT -- including `docker`, unless a case asks for the fake.
PATH_MINIMUM = ("dirname", "uname")

# The recording fake. It writes its own argv AND its working directory to the call log with a distinct prefix. The working directory is not decoration: the twin never `cd`s, so the build context is whatever the caller's was, and `test_defect_the_build_context_is_the_callers_directory` reads it from here.
#
# The `CALL docker` prefix is also what the K=5 ledger scopes `--finding-re` to.
# `shadow-gate.ts` classifies any line starting `→ `/`✓ ` as CHATTER before any message-text regex is consulted, and this script's ONLY success output is a `✓ ` line, so a ledger keyed on message text alone would record `VACUOUS_BOTH_EMPTY` for every row.
FAKE_DOCKER = """#!/bin/bash
{
    printf 'CWD\\t%s\\n' "$PWD"
    printf 'CALL docker'
    for a in "$@"; do printf '\\t%s' "$a"; done
    printf '\\n'
} >>"$FAKE_CALL_LOG"
if [[ -n "${FAKE_DOCKER_STDOUT:-}" ]]; then echo "$FAKE_DOCKER_STDOUT"; fi
if [[ "${FAKE_DOCKER_RC:-0}" != 0 ]]; then
    echo 'ERROR: failed to solve: push access denied' >&2
    exit "$FAKE_DOCKER_RC"
fi
echo '#1 [internal] load build definition'
exit 0
"""

SELF_RE = re.compile(r"\S*(?:%s|%s)" % (re.escape(TWIN_REL), re.escape(PORT_REL)))

# A complete, valid environment. Individual cases remove or replace one key.
FULL_ENV = {
    "PLATFORM": "linux/amd64",
    "VARIANT": "onprem",
    "IMAGE_PATH": "ghcr.io/rediacc/server",
    "WEB_TAG": "1.2.3",
    "ACCOUNT_ENTRY": "on-premise",
}


def fixture(tmp_path: pathlib.Path, *, port_source: str | None = None) -> pathlib.Path:
    root = tmp_path / "repo"
    for rel in (TWIN_REL, PORT_REL, COMMON_REL, *VENDORED):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
    for rel in (TWIN_REL, COMMON_REL, *VENDORED):
        shutil.copy2(ROOT / rel, root / rel)
    if port_source is None:
        shutil.copy2(ROOT / PORT_REL, root / PORT_REL)
    else:
        (root / PORT_REL).write_text(port_source, encoding="utf-8")
    # The twin's build context is `.` with `--file Dockerfile`; a Dockerfile at the fixture root is what a correctly-invoked run would find.
    (root / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    return root


def scratch_bin(root: pathlib.Path, *, drop_docker: bool = False) -> str:
    """The ONLY directory on PATH for either side."""
    stub = root / "fixture-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for name in PATH_MINIMUM:
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
    return str(stub)


def _run(
    root: pathlib.Path,
    side: str,
    *,
    drop_docker: bool = False,
    cwd: str | None = None,
    env_overrides: dict[str, str | None] | None = None,
    **extra,
):
    call_log = root / ("%s-calls.log" % side)
    call_log.write_text("", encoding="utf-8")
    env = {
        # REPLACED, never prepended.
        "PATH": scratch_bin(root, drop_docker=drop_docker),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(root / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
        **FULL_ENV,
    }
    # `None` REMOVES a key, which is the only way to distinguish unset from
    # empty -- and `${VAR:?}` treats them the same while `${VAR?}` would not.
    for key, value in (env_overrides or {}).items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    env.update(extra)
    argv = [BASH, str(root / TWIN_REL)] if side == "old" else [sys.executable, str(root / PORT_REL)]
    proc = subprocess.run(
        argv,
        cwd=cwd or str(root),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )
    return proc, call_log.read_text(encoding="utf-8")


def run_both(root: pathlib.Path, **kw):
    old, old_calls = _run(root, "old", **kw)
    new, new_calls = _run(root, "new", **kw)
    return old, new, old_calls, new_calls


def _mask(text: str) -> str:
    """`$0`, the one thing that cannot agree between the two sides."""
    return SELF_RE.sub("<SELF>", text)


def _agree(old, new, label: str, old_calls: str = "", new_calls: str = "") -> None:
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


def _argv_line(calls: str) -> list[str]:
    """The single recorded docker argv, split back into a list."""
    lines = [ln for ln in calls.splitlines() if ln.startswith("CALL docker")]
    assert len(lines) == 1, "expected exactly one docker call, got %r" % calls
    return lines[0].split("\t")


# --------------------------------------------------------------------------- The control on the control ---------------------------------------------------------------------------


def test_the_scratch_path_cannot_reach_a_real_docker(tmp_path) -> None:
    """One real run of this script is a push to ghcr.io, so the seal on the PATH is load-bearing rather than tidy. Asserted in both directions: the fake is reachable, and removing it leaves nothing behind it.
    """
    root = fixture(tmp_path)
    sealed = scratch_bin(root)
    assert shutil.which("docker", path=sealed) == str(root / "fixture-bin" / "docker")
    dropped = scratch_bin(root, drop_docker=True)
    assert shutil.which("docker", path=dropped) is None, "a real docker is reachable"
    assert shutil.which("buildx", path=dropped) is None
    assert shutil.which("podman", path=dropped) is None


# --------------------------------------------------------------------------- The success path, and the argv that is the whole point of the script ---------------------------------------------------------------------------


def test_amd64_builds_pushes_and_reports_the_tag(tmp_path) -> None:
    root = fixture(tmp_path)
    old, new, old_calls, new_calls = run_both(root)
    assert old.returncode == 0, old.stderr
    assert old.stdout == "#1 [internal] load build definition\n"
    assert old.stderr == "✓ Pushed ghcr.io/rediacc/server:1.2.3-amd64\n"
    assert _argv_line(old_calls) == [
        "CALL docker",
        "buildx",
        "build",
        "--file",
        "Dockerfile",
        "--target",
        "onprem",
        "--platform",
        "linux/amd64",
        "--build-arg",
        "VITE_APP_VERSION=1.2.3",
        "--build-arg",
        "ACCOUNT_ENTRY=on-premise",
        "--build-arg",
        "ACCOUNT_ED25519_PUBLIC_KEY=",
        "--tag",
        "ghcr.io/rediacc/server:1.2.3-amd64",
        "--push",
        ".",
    ]
    _agree(old, new, "amd64", old_calls, new_calls)


def test_arm64_differs_only_in_the_platform_and_the_tag_suffix(tmp_path) -> None:
    """The two live jobs differ by exactly this, so both are driven."""
    root = fixture(tmp_path)
    old, new, old_calls, new_calls = run_both(root, env_overrides={"PLATFORM": "linux/arm64"})
    assert old.returncode == 0, old.stderr
    assert old.stderr == "✓ Pushed ghcr.io/rediacc/server:1.2.3-arm64\n"
    argv = _argv_line(old_calls)
    assert argv[argv.index("--platform") + 1] == "linux/arm64"
    assert argv[argv.index("--tag") + 1] == "ghcr.io/rediacc/server:1.2.3-arm64"
    _agree(old, new, "arm64", old_calls, new_calls)


def test_the_ported_argv_builder_matches_what_the_twin_actually_ran(tmp_path) -> None:
    """`build_argv` is exported so the order can be asserted directly rather than inferred from output, and this pins it against the BASH side's recorded argv rather than against itself.
    """
    root = fixture(tmp_path)
    old, _old_calls = _run(root, "old")
    assert old.returncode == 0, old.stderr
    recorded = _argv_line((root / "old-calls.log").read_text(encoding="utf-8"))
    expected = port.build_argv(
        platform=FULL_ENV["PLATFORM"],
        variant=FULL_ENV["VARIANT"],
        image_path=FULL_ENV["IMAGE_PATH"],
        web_tag=FULL_ENV["WEB_TAG"],
        account_entry=FULL_ENV["ACCOUNT_ENTRY"],
        public_key="",
    )
    assert recorded == ["CALL docker", *expected[1:]]


def test_the_public_key_is_forwarded_when_it_is_set(tmp_path) -> None:
    root = fixture(tmp_path)
    old, new, old_calls, new_calls = run_both(
        root, env_overrides={"ACCOUNT_ED25519_PUBLIC_KEY": "AAAAC3NzaC1lZDI1NTE5"}
    )
    assert old.returncode == 0, old.stderr
    assert "ACCOUNT_ED25519_PUBLIC_KEY=AAAAC3NzaC1lZDI1NTE5" in _argv_line(old_calls)
    _agree(old, new, "pubkey", old_calls, new_calls)


# --------------------------------------------------------------------------- The refusals, in the twin's ORDER ---------------------------------------------------------------------------


def test_a_missing_docker_refuses_before_any_variable_is_read(tmp_path) -> None:
    """`require_cmd docker` (:26) runs BEFORE the five expansions, so a machine
    with no docker hears about docker even when every variable is also missing.
    Driven with the environment emptied, which is the case that would report a variable if the order were reversed.
    """
    root = fixture(tmp_path)
    empty = dict.fromkeys(FULL_ENV)
    old, new, old_calls, new_calls = run_both(root, drop_docker=True, env_overrides=empty)
    assert old.returncode == 1
    assert old.stdout == ""
    assert old.stderr == "✗ Required command 'docker' is not available\n"
    assert old_calls == ""
    _agree(old, new, "no-docker", old_calls, new_calls)


def test_each_required_variable_refuses_in_bashs_own_words(tmp_path) -> None:
    """One case per expansion (:27-31), each removing exactly that variable so the message names it rather than an earlier one.
    """
    for index, (name, line, message) in enumerate(port.REQUIRED_ENV):
        root = fixture(tmp_path / name)
        old, new, old_calls, new_calls = run_both(root, env_overrides={name: None})
        assert old.returncode == 1, old.stderr
        assert old.stdout == ""
        assert _mask(old.stderr) == "<SELF>: line %d: %s: %s\n" % (line, name, message), old.stderr
        assert old_calls == ""
        _agree(old, new, "missing " + name, old_calls, new_calls)
        # The line numbers march with the twin's source order.
        assert line == port.REQUIRED_ENV[0][1] + index


def test_an_empty_variable_refuses_exactly_as_an_unset_one_does(tmp_path) -> None:
    """`:?` with the colon fires on SET-BUT-EMPTY too; `${VAR?...}` would not.
    A port that tested `"NAME" in os.environ` would accept `PLATFORM=` and push
    a tag ending in a bare hyphen.
    """
    root = fixture(tmp_path)
    old, new, old_calls, new_calls = run_both(root, env_overrides={"PLATFORM": ""})
    assert old.returncode == 1
    assert _mask(old.stderr) == (
        "<SELF>: line 27: PLATFORM: PLATFORM is required (linux/amd64 or linux/arm64)\n"
    ), old.stderr
    _agree(old, new, "empty PLATFORM", old_calls, new_calls)


def test_with_nothing_set_the_first_expansion_is_the_one_reported(tmp_path) -> None:
    """ORDER IS OBSERVABLE: five missing variables produce ONE sentence, and it is PLATFORM's. A port that validated in any other order would exit 1 with a different message, which no exit-code comparison would catch.
    """
    root = fixture(tmp_path)
    old, new, old_calls, new_calls = run_both(root, env_overrides=dict.fromkeys(FULL_ENV))
    assert old.returncode == 1
    assert _mask(old.stderr).startswith("<SELF>: line 27: PLATFORM:")
    assert old.stderr.count("\n") == 1, "more than one variable was reported"
    _agree(old, new, "order", old_calls, new_calls)


def test_dockers_own_exit_status_is_propagated_not_flattened(tmp_path) -> None:
    """`set -e` lets docker's 17 through unchanged, and the success line is not printed. This is the OPPOSITE of `build-www.sh`, which flattens npm's status to 1; the two twins are inconsistent with each other and this is the correct half, so a port that normalised it would be wrong here and right there.
    """
    root = fixture(tmp_path)
    old, new, old_calls, new_calls = run_both(root, FAKE_DOCKER_RC="17")
    assert old.returncode == 17, old.stderr
    assert old.stderr == "ERROR: failed to solve: push access denied\n"
    assert "Pushed" not in old.stderr
    _agree(old, new, "docker-17", old_calls, new_calls)


# --------------------------------------------------------------------------- The defects, each with its own case ---------------------------------------------------------------------------


def test_defect_platform_is_never_validated_only_split(tmp_path) -> None:
    """DEFECT 2. The refusal message promises `linux/amd64 or linux/arm64`;
    `ARCH="${PLATFORM##*/}"` accepts anything. Three shapes are driven, and all
    three exit 0 having PUSHED a real tag derived from unvalidated input:

      nonsense  -> `...:1.2.3-nonsense`
      linux/    -> `...:1.2.3-`,  a tag ending in a bare hyphen
      a/b/c     -> `...:1.2.3-c`, the longest prefix removed, not the first
    """
    for slug, platform, suffix in (
        ("nonsense", "nonsense", "nonsense"),
        ("trailing-slash", "linux/", ""),
        ("three-parts", "a/b/c", "c"),
    ):
        root = fixture(tmp_path / slug)
        old, new, old_calls, new_calls = run_both(root, env_overrides={"PLATFORM": platform})
        assert old.returncode == 0, old.stderr
        assert old.stderr == "✓ Pushed ghcr.io/rediacc/server:1.2.3-%s\n" % suffix
        argv = _argv_line(old_calls)
        assert argv[argv.index("--tag") + 1] == "ghcr.io/rediacc/server:1.2.3-%s" % suffix
        assert port.arch_of(platform) == suffix
        _agree(old, new, "unvalidated " + platform, old_calls, new_calls)


def test_defect_the_optional_build_arg_is_always_passed(tmp_path) -> None:
    """DEFECT 3. The twin's header calls `ACCOUNT_ED25519_PUBLIC_KEY` optional;
    `--build-arg "ACCOUNT_ED25519_PUBLIC_KEY=${...:-}"` (:41) passes it as a
    DEFINED-BUT-EMPTY build arg whether or not it has a value, so a Dockerfile cannot tell unset from empty. Driven both ways.
    """
    root = fixture(tmp_path)
    for value in (None, ""):
        old, new, old_calls, new_calls = run_both(
            root, env_overrides={"ACCOUNT_ED25519_PUBLIC_KEY": value}
        )
        assert old.returncode == 0, old.stderr
        argv = _argv_line(old_calls)
        assert argv.count("--build-arg") == 3, argv
        assert "ACCOUNT_ED25519_PUBLIC_KEY=" in argv
        _agree(old, new, "empty pubkey %r" % value, old_calls, new_calls)


def test_defect_the_build_context_is_the_callers_directory(tmp_path) -> None:
    """DEFECT 1. `--file Dockerfile` and the trailing `.` are relative and the script never `cd`s -- unlike BOTH neighbours in the same directory, which open with `cd "$(get_repo_root)"`. Driven from a scratch directory holding a DIFFERENT one-line Dockerfile: the run succeeds, pushes under the production tag, and the fake records the decoy as its working directory.
    """
    root = fixture(tmp_path)
    decoy = tmp_path / "elsewhere"
    decoy.mkdir()
    (decoy / "Dockerfile").write_text(
        "FROM alpine\nRUN echo not-the-real-image\n", encoding="utf-8"
    )
    old, new, old_calls, new_calls = run_both(root, cwd=str(decoy))
    assert old.returncode == 0, "the twin refused; it now checks its context"
    assert old.stderr == "✓ Pushed ghcr.io/rediacc/server:1.2.3-amd64\n"
    assert ("CWD\t%s" % decoy) in old_calls, old_calls
    argv = _argv_line(old_calls)
    assert argv[-1] == "."
    assert argv[argv.index("--file") + 1] == "Dockerfile"
    _agree(old, new, "context", old_calls, new_calls)


def test_arch_of_matches_the_shells_own_parameter_expansion() -> None:
    """`${PLATFORM##*/}` against the real bash, not against a reading of it."""
    cases = ["linux/amd64", "linux/arm64", "nonsense", "linux/", "a/b/c", "/", ""]
    proc = subprocess.run(
        [BASH, "-c", 'for p in "$@"; do printf "%s\\n" "${p##*/}"; done', "bash", *cases],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    assert proc.stdout.split("\n")[: len(cases)] == [port.arch_of(c) for c in cases]


# --------------------------------------------------------------------------- The control: this differential can actually fail ---------------------------------------------------------------------------


def test_a_planted_defect_is_caught_only_by_the_call_log(tmp_path) -> None:
    """A gate that has never been seen to fail is not a gate.

    The plant drops `--push`, which is the single most consequential argument in the file: without it the build succeeds locally and nothing reaches the registry, while the script still prints `✓ Pushed ...` and exits 0. All three streams agree; only the recorded argv disagrees, which is why the log is compared at all.
    """
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")
    planted = source.replace('        "--push",\n', "")
    assert planted != source, "the plant site moved; this control is not planting anything"
    root = fixture(tmp_path, port_source=planted)
    old, new, old_calls, new_calls = run_both(root)
    assert old.returncode == new.returncode == 0
    assert new.stdout == old.stdout
    assert new.stderr == old.stderr, (
        "the plant was visible in stderr, so the log is not the witness"
    )
    assert new_calls != old_calls, "the plant did not diverge"
    assert "--push" in old_calls
    assert "--push" not in new_calls
