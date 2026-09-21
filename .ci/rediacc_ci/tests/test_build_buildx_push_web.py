"""`rediacc_ci.build.buildx_push_web`, driven against the bytes its bash twin printed.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/build/buildx-push-web.sh` and the port inside one throwaway fixture root and compared exit code, stdout, stderr and the recording fake's call log. The ledger `.ci/shadow/w7p6-buildx-push-web.observations.jsonl` holds 5 rows of that comparison.

Every fixture case now compares against `goldens/buildx-push-web/`, which holds the twin's OWN recorded bytes, captured on its last day in the tree, and each golden's provenance header carries the blob sha.

THE REAL SCRIPT PUSHES TO ghcr.io. `--push` is unconditional and there is no dry-run branch, so one real invocation is a registry write. Every case runs against a RECORDING FAKE `docker` on a PATH that REPLACES the caller's rather than prepending to it, and `test_the_scratch_path_cannot_reach_a_real_docker` asserts the real binary is unreachable before anything is driven. A
prepended PATH is not good enough: it still resolves whatever the developer has installed.

THE CALL LOG IS THE EVIDENCE, and it is carried as its own `--- calls ---` section. The fake prints nothing that depends on its arguments, so a port that swapped two `--build-arg` values, dropped `--push`, or built the wrong `--target` would produce identical stdout, identical stderr and an identical exit code. The control at the foot of this file plants exactly that.

IT WAS SAFE TO RETIRE, and that was established before anything was deleted. Both live invocations are already the port, `.github/workflows/ci-build-docker.yml:287` and `:387`.

The only other references were a CLOSURE PATH LIST that exists twice, at `rediacc_ci/ci/generate_tag.py:125` and `.ci/scripts/ci/generate-tag.sh:220`, and one entry in `.ci/scripts/ci/greenlight.cjs:338`.

Both closure copies were flipped to the port's path and the generate-tag differential was re-run with both of ITS copies still present, which is the live evidence that the two lists still agree and the closure hash still resolves. The greenlight entry belongs to another owner and is reported rather than edited.

WHICH CASES ARE RECORDED AND WHICH ARE NOT. Every case driving the fixture has a golden. Three assertions stay live because they are about something other than the subject's own output: the PATH seal, `arch_of` against the real bash's parameter expansion, and `build_argv` against the RECORDED argv, which is the stronger direction now that the recording is the oracle rather than a
second live run.

WHAT IS MASKED, and it is four things. `<SELF>` is the subject's own path, which bash names in its five `${VAR:?...}` refusals and which `sys.argv[0]` spells with a `.py`; `<root>` is the throwaway fixture root; `<work>` is its parent, where the decoy build context lives; `<repo>` is the checkout root.

Nothing else is touched, and both streams are compared SEPARATELY.

THE THREE DEFECTS EACH HAVE THEIR OWN RECORDINGS, all preserved rather than repaired: the build context is the CALLER's directory because the subject never `cd`s, unlike both its neighbours; `PLATFORM` is never validated, only split, so a refusal message promising `linux/amd64 or linux/arm64` accepts anything and pushes a tag derived from it; and the optional public key is always
passed as a defined-but-empty build arg, so a Dockerfile cannot tell unset from empty.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.build import buildx_push_web as bpw
from rediacc_ci.tests import frozen

ROOT = paths.repo_root()

PORT_REL = ".ci/rediacc_ci/build/buildx_push_web.py"
TWIN_REL = ".ci/scripts/build/buildx-push-web.sh"
COMMON_REL = ".ci/scripts/lib/common.sh"

SLUG = "buildx-push-web"
CALLS_MARKER = "--- calls ---\n"

VENDORED = (
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/log.py",
    ".ci/rediacc_ci/paths.py",
    ".ci/rediacc_ci/core/__init__.py",
    ".ci/rediacc_ci/core/common.py",
    ".ci/rediacc_ci/build/__init__.py",
)

BASH = shutil.which("bash") or "/bin/bash"
PYTHON = sys.executable

# `dirname` for the twin's own `SCRIPT_DIR` (:23), `uname` because sourcing common.sh runs `detect_os`/`detect_arch` at :509-510. Anything not listed is ABSENT, including `docker` unless a case asks for the fake.
PATH_MINIMUM = ("dirname", "uname")

# The recording fake. It writes its own argv AND its working directory to the call log. The working directory is not decoration: the subject never `cd`s, so the build context is whatever the caller's was, and one case reads it from here.
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

# name -> the environment overrides and the two fixture switches. A `None` override REMOVES a key, which is the only way to distinguish unset from empty, and `${VAR:?}` treats them the same while `${VAR?}` would not.
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "amd64": {},
    "arm64": {"env": {"PLATFORM": "linux/arm64"}},
    "with-a-public-key": {"env": {"ACCOUNT_ED25519_PUBLIC_KEY": "AAAAC3NzaC1lZDI1NTE5"}},
    "an-unset-public-key": {"env": {"ACCOUNT_ED25519_PUBLIC_KEY": None}},
    "an-empty-public-key": {"env": {"ACCOUNT_ED25519_PUBLIC_KEY": ""}},
    "no-docker-with-nothing-set": {"drop_docker": True, "env": dict.fromkeys(FULL_ENV)},
    "an-empty-platform": {"env": {"PLATFORM": ""}},
    "nothing-set-at-all": {"env": dict.fromkeys(FULL_ENV)},
    "docker-exiting-seventeen": {"extra": {"FAKE_DOCKER_RC": "17"}},
    "an-unvalidated-platform": {"env": {"PLATFORM": "nonsense"}},
    "a-platform-with-a-trailing-slash": {"env": {"PLATFORM": "linux/"}},
    "a-three-part-platform": {"env": {"PLATFORM": "a/b/c"}},
    "a-caller-elsewhere": {"decoy": True},
}
CASE_KW.update(
    {
        "without-%s" % name.lower().replace("_", "-"): {"env": {name: None}}
        for name, _, _ in bpw.REQUIRED_ENV
    }
)

CASES = tuple(CASE_KW)


def fixture(where: pathlib.Path, subject: pathlib.Path) -> pathlib.Path:
    root = where / "repo"
    for rel in (PORT_REL, COMMON_REL, *VENDORED):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
    for rel in (COMMON_REL, *VENDORED):
        shutil.copy2(ROOT / rel, root / rel)
    if subject.suffix == ".sh":
        (root / TWIN_REL).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / TWIN_REL, root / TWIN_REL)
    else:
        shutil.copy2(ROOT / PORT_REL, root / PORT_REL)
    # The build context is `.` with `--file Dockerfile`; a Dockerfile at the fixture root is what a correctly-invoked run would find.
    (root / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    return root


def scratch_bin(root: pathlib.Path, *, drop_docker: bool = False) -> str:
    """The ONLY directory on PATH for the subject."""
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


def run(subject: pathlib.Path, where: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    """One subject, once, inside its own throwaway root."""
    kw = CASE_KW[name]
    where.mkdir(parents=True, exist_ok=True)
    root = fixture(where, subject)
    call_log = root / "calls.log"
    call_log.write_text("", encoding="utf-8")
    cwd = str(root)
    if kw.get("decoy"):
        # A scratch directory holding a DIFFERENT one-line Dockerfile. The subject never `cd`s, so this is the context it will build.
        decoy = where / "elsewhere"
        decoy.mkdir(parents=True, exist_ok=True)
        (decoy / "Dockerfile").write_text(
            "FROM alpine\nRUN echo not-the-real-image\n", encoding="utf-8"
        )
        cwd = str(decoy)
    env = {
        # REPLACED, never prepended.
        "PATH": scratch_bin(root, drop_docker=kw.get("drop_docker", False)),
        "HOME": str(where),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(root / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
        **FULL_ENV,
    }
    for key, value in (kw.get("env") or {}).items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    env.update(kw.get("extra") or {})
    target = root / (TWIN_REL if subject.suffix == ".sh" else PORT_REL)
    proc = subprocess.run(
        [BASH if subject.suffix == ".sh" else PYTHON, str(target)],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )

    def mask(text: str) -> str:
        folded = SELF_RE.sub("<SELF>", text)
        return (
            folded.replace(str(root), "<root>")
            .replace(str(where), "<work>")
            .replace(str(ROOT), "<repo>")
        )

    return (
        proc.returncode,
        mask(proc.stdout),
        mask(proc.stderr),
        mask(call_log.read_text(encoding="utf-8")),
    )


def render(code: int, stdout: str, stderr: str, calls: str) -> str:
    return "%s%s%s" % (frozen.render(code, stdout, stderr), CALLS_MARKER, calls)


def recorded(name: str) -> tuple[int, str, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, calls = rest.split(CALLS_MARKER, 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, calls


def argv_of(calls: str) -> list[str]:
    """The one `CALL docker` line, split back into fields."""
    for line in calls.splitlines():
        if line.startswith("CALL docker"):
            return line.split("\t")
    raise AssertionError("no docker call in %r" % calls)


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str]:
    want = recorded(name)
    got = run(pathlib.Path(PORT_REL), tmp_path / name, name)
    labels = ("exit code", "stdout", "stderr", "the docker CALL LOG")
    # `strict=True`: the tuple and the labels must stay the same length, and a silently truncated zip is how a comparison stops checking its last field.
    for label, a, b in zip(labels, want, got, strict=True):
        assert a == b, "%s: %s diverged:\n--- recorded ---\n%s\n--- port ---\n%s" % (
            name,
            label,
            a,
            b,
        )
    return got


@pytest.mark.parametrize("name", CASES)
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- The control on the control: the scratch PATH really is sealed ---------------------------------------------------------------------------


def test_the_scratch_path_cannot_reach_a_real_docker(tmp_path: pathlib.Path) -> None:
    """One real run of this subject is a push to ghcr.io, so the seal on the PATH is load-bearing rather than tidy. Asserted in both directions: the fake is reachable, and removing it leaves nothing behind it."""
    root = fixture(tmp_path, pathlib.Path(PORT_REL))
    sealed = scratch_bin(root)
    assert shutil.which("docker", path=sealed) == str(root / "fixture-bin" / "docker")
    dropped = scratch_bin(root, drop_docker=True)
    assert shutil.which("docker", path=dropped) is None, "a real docker is reachable"
    assert shutil.which("buildx", path=dropped) is None
    assert shutil.which("podman", path=dropped) is None


# --------------------------------------------------------------------------- What the recordings say: the success path and its argv ---------------------------------------------------------------------------


def test_amd64_builds_pushes_and_reports_the_tag() -> None:
    code, stdout, stderr, calls = recorded("amd64")
    assert code == 0, stderr
    assert stdout == "#1 [internal] load build definition\n"
    assert stderr == "✓ Pushed ghcr.io/rediacc/server:1.2.3-amd64\n"
    assert argv_of(calls) == [
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


def test_arm64_differs_only_in_the_platform_and_the_tag_suffix() -> None:
    """The two live jobs differ by exactly this, so both have recordings."""
    code, _, stderr, calls = recorded("arm64")
    assert code == 0, stderr
    assert stderr == "✓ Pushed ghcr.io/rediacc/server:1.2.3-arm64\n"
    argv = argv_of(calls)
    assert argv[argv.index("--platform") + 1] == "linux/arm64"
    assert argv[argv.index("--tag") + 1] == "ghcr.io/rediacc/server:1.2.3-arm64"


def test_the_ported_argv_builder_matches_what_the_twin_actually_ran() -> None:
    """`build_argv` is exported so the order can be asserted directly rather than inferred from output, and this pins it against the TWIN's recorded argv rather than against itself. That is the stronger direction now: the recording is the oracle, not a second live run of the same program."""
    expected = bpw.build_argv(
        platform=FULL_ENV["PLATFORM"],
        variant=FULL_ENV["VARIANT"],
        image_path=FULL_ENV["IMAGE_PATH"],
        web_tag=FULL_ENV["WEB_TAG"],
        account_entry=FULL_ENV["ACCOUNT_ENTRY"],
        public_key="",
    )
    assert argv_of(recorded("amd64")[3]) == ["CALL docker", *expected[1:]]


def test_the_public_key_is_forwarded_when_it_is_set() -> None:
    code, _, stderr, calls = recorded("with-a-public-key")
    assert code == 0, stderr
    assert "ACCOUNT_ED25519_PUBLIC_KEY=AAAAC3NzaC1lZDI1NTE5" in argv_of(calls)


# --------------------------------------------------------------------------- The refusals, in the twin's ORDER ---------------------------------------------------------------------------


def test_a_missing_docker_refuses_before_any_variable_is_read() -> None:
    """`require_cmd docker` (:26) runs BEFORE the five expansions, so a machine with no docker hears about docker even when every variable is also missing. Recorded with the environment emptied, which is the case that would report a variable if the order were reversed."""
    code, stdout, stderr, calls = recorded("no-docker-with-nothing-set")
    assert code == 1
    assert stdout == ""
    assert stderr == "✗ Required command 'docker' is not available\n"
    assert calls == ""


def test_each_required_variable_refuses_in_bashs_own_words() -> None:
    """One recording per expansion (:27-31), each removing exactly that variable so the message names it rather than an earlier one."""
    for index, (name, line, message) in enumerate(bpw.REQUIRED_ENV):
        case = "without-%s" % name.lower().replace("_", "-")
        code, stdout, stderr, calls = recorded(case)
        assert code == 1, stderr
        assert stdout == ""
        assert stderr == "<SELF>: line %d: %s: %s\n" % (line, name, message), stderr
        assert calls == ""
        # The line numbers march with the twin's source order.
        assert line == bpw.REQUIRED_ENV[0][1] + index


def test_an_empty_variable_refuses_exactly_as_an_unset_one_does() -> None:
    """`:?` with the colon fires on SET-BUT-EMPTY too; `${VAR?...}` would not. A port that tested `"NAME" in os.environ` would accept `PLATFORM=` and push a tag ending in a bare hyphen."""
    code, _, stderr, _ = recorded("an-empty-platform")
    assert code == 1
    assert stderr == (
        "<SELF>: line 27: PLATFORM: PLATFORM is required (linux/amd64 or linux/arm64)\n"
    ), stderr


def test_with_nothing_set_the_first_expansion_is_the_one_reported() -> None:
    """ORDER IS OBSERVABLE: five missing variables produce ONE sentence, and it is PLATFORM's. A port that validated in any other order would exit 1 with a different message, which no exit-code comparison would catch."""
    code, _, stderr, _ = recorded("nothing-set-at-all")
    assert code == 1
    assert stderr.startswith("<SELF>: line 27: PLATFORM:")
    assert stderr.count("\n") == 1, "more than one variable was reported"


def test_dockers_own_exit_status_is_propagated_not_flattened() -> None:
    """`set -e` lets docker's 17 through unchanged, and the success line is not printed. This is the OPPOSITE of `build-www.sh`, which flattened npm's status to 1; the two twins were inconsistent with each other and this is the correct half, so a port that normalised it would be wrong here and right there."""
    code, _, stderr, _ = recorded("docker-exiting-seventeen")
    assert code == 17, stderr
    assert stderr == "ERROR: failed to solve: push access denied\n"
    assert "Pushed" not in stderr


# --------------------------------------------------------------------------- The defects, each with its own recording ---------------------------------------------------------------------------


def test_defect_platform_is_never_validated_only_split() -> None:
    """DEFECT 2. The refusal message promises `linux/amd64 or linux/arm64`; `ARCH="${PLATFORM##*/}"` accepts anything. Three shapes are recorded, and all three exit 0 having PUSHED a real tag derived from unvalidated input:

    nonsense  -> `...:1.2.3-nonsense`
    linux/    -> `...:1.2.3-`,  a tag ending in a bare hyphen
    a/b/c     -> `...:1.2.3-c`, the longest prefix removed, not the first
    """
    for case, platform, suffix in (
        ("an-unvalidated-platform", "nonsense", "nonsense"),
        ("a-platform-with-a-trailing-slash", "linux/", ""),
        ("a-three-part-platform", "a/b/c", "c"),
    ):
        code, _, stderr, calls = recorded(case)
        assert code == 0, stderr
        assert stderr == "✓ Pushed ghcr.io/rediacc/server:1.2.3-%s\n" % suffix, case
        argv = argv_of(calls)
        assert argv[argv.index("--tag") + 1] == "ghcr.io/rediacc/server:1.2.3-%s" % suffix
        assert bpw.arch_of(platform) == suffix


def test_defect_the_optional_build_arg_is_always_passed() -> None:
    """DEFECT 3. The twin's header called `ACCOUNT_ED25519_PUBLIC_KEY` optional; `--build-arg "ACCOUNT_ED25519_PUBLIC_KEY=${...:-}"` (:41) passes it as a DEFINED-BUT-EMPTY build arg whether or not it has a value, so a Dockerfile cannot tell unset from empty. Recorded both ways."""
    for case in ("an-unset-public-key", "an-empty-public-key"):
        code, _, stderr, calls = recorded(case)
        assert code == 0, stderr
        argv = argv_of(calls)
        assert argv.count("--build-arg") == 3, argv
        assert "ACCOUNT_ED25519_PUBLIC_KEY=" in argv


def test_defect_the_build_context_is_the_callers_directory() -> None:
    """DEFECT 1. `--file Dockerfile` and the trailing `.` are relative and the subject never `cd`s, unlike BOTH neighbours in the same directory, which open with `cd "$(get_repo_root)"`. Recorded from a scratch directory holding a DIFFERENT one-line Dockerfile: the run succeeds, pushes under the production tag, and the fake records the decoy as its working directory."""
    code, _, stderr, calls = recorded("a-caller-elsewhere")
    assert code == 0, "the twin refused; it checked its context after all"
    assert stderr == "✓ Pushed ghcr.io/rediacc/server:1.2.3-amd64\n"
    assert "CWD\t<work>/elsewhere" in calls, calls
    argv = argv_of(calls)
    assert argv[-1] == "."
    assert argv[argv.index("--file") + 1] == "Dockerfile"


# --------------------------------------------------------------------------- The shell's own parameter expansion, deliberately NOT recorded ---------------------------------------------------------------------------


def test_arch_of_matches_the_shells_own_parameter_expansion() -> None:
    """`${PLATFORM##*/}` against the real bash, not against a reading of it.

    NOT RECORDED: the claim is about bash's expansion, and the only honest oracle for that is bash itself, which is still here.
    """
    cases = ["linux/amd64", "linux/arm64", "nonsense", "linux/", "a/b/c", "/", ""]
    proc = subprocess.run(
        [BASH, "-c", 'for a in "$@"; do printf "%s\\0" "${a##*/}"; done', "bash", *cases],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    answers = proc.stdout.split("\0")[: len(cases)]
    for value, expected in zip(cases, answers, strict=True):
        assert bpw.arch_of(value) == expected, value


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_drop_of_push_is_caught_only_by_the_call_log(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS, aimed at the section that would otherwise be decoration.

    `--push` is what makes this subject a registry write rather than a local build, and the fake prints nothing that depends on its arguments: dropping the flag leaves the exit code, stdout and the `✓ Pushed ...` line on stderr exactly as they were, and the image simply never leaves the machine. Only the `--- calls ---` section sees it.

    THE PLANT IS A COPY WRITTEN AT THE SUBJECT'S OWN PATH INSIDE THE FIXTURE, which is where the module already runs from in every case here. The tracked file is never written.
    """
    original = (ROOT / PORT_REL).read_text(encoding="utf-8")
    anchor = '"--push",'
    assert original.count(anchor) == 1, "the plant's anchor moved"

    name = "amd64"
    want = recorded(name)
    assert "--push" in argv_of(want[3]), "the recorded corpus moved"

    where = tmp_path / "planted"
    where.mkdir(parents=True)
    root = fixture(where, pathlib.Path(PORT_REL))
    (root / PORT_REL).write_text(original.replace(anchor, ""), encoding="utf-8")
    call_log = root / "calls.log"
    call_log.write_text("", encoding="utf-8")
    proc = subprocess.run(
        [PYTHON, str(root / PORT_REL)],
        cwd=str(root),
        capture_output=True,
        text=True,
        env={
            "PATH": scratch_bin(root),
            "HOME": str(where),
            "LC_ALL": "C.UTF-8",
            "LANG": "C.UTF-8",
            "PYTHONPATH": str(root / ".ci"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "FAKE_CALL_LOG": str(call_log),
            **FULL_ENV,
        },
        check=False,
        timeout=120,
        input="",
    )
    planted_calls = call_log.read_text(encoding="utf-8").replace(str(root), "<root>")
    assert proc.returncode == want[0] == 0, proc.stderr
    assert proc.stdout == want[1], "the plant was supposed to be invisible on stdout"
    assert proc.stderr == want[2], "the plant was supposed to be invisible on stderr"
    assert "--push" not in argv_of(planted_calls), "the plant did not drop the flag"

    compare(tmp_path / "good", name)
    assert (ROOT / PORT_REL).read_text(encoding="utf-8") == original
