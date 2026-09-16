"""Differential: `.ci/rediacc_ci/infra/build_renet.py` against its twin
`.ci/scripts/infra/build-renet.sh`.

WHY A DIFFERENTIAL AND NOT A UNIT TEST. The claim a port makes is not "the new
code is correct", it is "the new code says what the old code said". Only running
BOTH, on the same fixture, in the same run, can support that.

WHAT IS COMPARED, AND WHY IT IS SIX THINGS AND NOT ONE. This script's job is a
SIDE EFFECT, so exit code and stdout between them describe almost none of it.
Every case below compares:

  1. the exit code;
  2. stdout, which is the single `RENET_BINARY=<path>` line callers parse;
  3. stderr, which is the whole `log_info`/`log_step`/`log_error` transcript;
  4. the CALL LOG -- every `./build.sh` invocation, its argv AND its cwd. A port
     that printed the same transcript while never running the build, or running
     it from the wrong directory, passes a stdout-only comparison and ships
     nothing;
  5. the build-identity stamp on disk, byte for byte, which is what decides
     whether the NEXT run rebuilds. Getting this wrong is exactly the incident
     the stamp was introduced for;
  6. whether the binary is present afterwards, and what was appended to
     `$GITHUB_ENV`.

ANTI-VACUITY. `test_the_fake_build_is_actually_reached` fails if the recording
`build.sh` was never invoked. Without it, the cases below could be "two programs
that both refused to start, agreeing".

PATH IS REPLACED, NEVER PREPENDED. The subject asks `command -v go` and runs
`uname -s`, and this host has a real `go`. A prepend would leave the "no go"
case passing while occasionally consulting the machine's real toolchain, and
would let a real `uname` answer a question the MINGW case needs a fake for.
`_binder` therefore builds the ENTIRE PATH out of named tools, and asserts that
what it was asked to exclude really is absent -- a control on the control,
because a probe that cannot fire looks exactly like a subject that cannot fail.

THE ONE DELIBERATE DIVERGENCE IS TESTED, NOT HIDDEN, and writing that test is
what found a real defect in the twin.
`test_a_missing_sha256sum_is_the_one_deliberate_divergence` asserts both sides of
a `sha256sum`-less host: the twin's identity silently collapses to `<mode>|`
(losing the key component the stamp exists to carry) while exiting 0, and the
port keeps it. `test_the_collapsed_identity_defeats_the_rebuild_the_stamp_exists
_for` then demonstrates the consequence -- two different keys, one stamp, no
rebuild. The first draft of that test asserted exit 127 and FAILED, which is how
the defect surfaced: a failing pipeline inside a command substitution used as an
ARGUMENT is invisible to `set -e` and `pipefail`.
"""

import os
import pathlib
import shutil
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.infra import build_renet

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "infra" / "build-renet.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "infra" / "build_renet.py"

TWIN_REL = pathlib.PurePosixPath(".ci/scripts/infra/build-renet.sh")
PORT_REL = pathlib.PurePosixPath(".ci/rediacc_ci/infra/build_renet.py")

# The recording `./build.sh`, standing in for the real Go build. Written as
# Python and configured by its own TEXT rather than through the environment: the
# subject under test reads three environment variables of its own, and a fixture
# that added five more would make any env-shaped divergence unattributable.
FAKE_BUILD_SH = """#!/usr/bin/env python3
import os, pathlib, sys
LOG = %(log)r
ROOT = %(root)r
RC = %(rc)d
PRODUCES = %(produces)r
with pathlib.Path(LOG).open("a", encoding="utf-8") as fh:
    fh.write("\\t".join(["build.sh", os.path.relpath(os.getcwd(), ROOT), *sys.argv[1:]]) + "\\n")
if PRODUCES:
    out = pathlib.Path(os.getcwd()) / "bin" / PRODUCES
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("fake-renet-binary\\n", encoding="utf-8")
sys.exit(RC)
"""

# The fake `uname`. TWO forms are answered, and the second one is a finding
# about the harness worth recording: `-m` is asked by `common.sh:510`
# (`CI_ARCH="$(detect_arch)"`, evaluated AT SOURCE TIME), and `-s` twice by the
# twin -- once for `common.sh:509`'s `detect_os` and once for the twin's own
# `.exe` decision. The port sources nothing, so it asks `-s` once and `-m`
# never. That call-count difference is NOT compared anywhere below, deliberately:
# it comes from a library the twin happens to source and not from the subject's
# own logic, and the OBSERVABLE it feeds (`CI_OS`/`CI_ARCH`, exported into a
# child that no longer exists) is unread by either subject.
#
# Any OTHER form exits 1 loudly rather than answering, so a subject that started
# asking a different question shows up as a failure instead of a silent default.
# The first draft answered only `-s` and the `-m` call put a diagnostic into the
# twin's stderr on every case, which read as a divergence in the subject.
FAKE_UNAME = """#!/usr/bin/env python3
import sys
SYSTEM = %(system)r
if sys.argv[1:] == ["-s"]:
    sys.stdout.write(SYSTEM + "\\n")
elif sys.argv[1:] == ["-m"]:
    sys.stdout.write("x86_64\\n")
else:
    sys.stderr.write("fake uname: unexpected args %%r\\n" %% (sys.argv[1:],))
    sys.exit(1)
"""

# A `go` that exists and is never run: the subject only asks `command -v go`.
FAKE_GO = """#!/usr/bin/env python3
import sys
sys.stderr.write("fake go should never be executed: %r\\n" % (sys.argv[1:],))
sys.exit(97)
"""

# Prints one identity from the port, for the digest cross-check below. A
# separate process, so the environment `build_identity()` reads can be STATED
# rather than inherited from whoever is running the suite.
IDENTITY_HARNESS = (
    "import sys; sys.path.insert(0, sys.argv[1]); "
    "from rediacc_ci.infra import build_renet; "
    "print(build_renet.build_identity([]))"
)

# Everything both subjects need once PATH is rebuilt from scratch. Named rather
# than derived: a PATH built by copying "everything except go" is a PATH nobody
# can state, and the first tool it forgot would look like a divergence in the
# subject rather than a hole in the harness.
NEEDED = (
    "bash",
    "sh",
    "python3",
    "dirname",
    "cat",
    "rm",
    "cut",
    "sha256sum",
    "env",
    "mkdir",
    "ls",
)


def _fixture(
    where: pathlib.Path,
    *,
    submodule: bool = True,
    build_sh: bool = True,
    binary: str | None = None,
    stamp: str | None = None,
    build_rc: int = 0,
    produces: str = "renet",
) -> pathlib.Path:
    """A tree shaped like the repository, holding COPIES of both subjects.

    Copies, because each subject derives the console root from its own location
    (`BASH_SOURCE`/`__file__`, then three directories up). Driving the tracked
    files with a `cwd` would point them at the real repository, and case 13
    below would then delete the real `private/renet/bin/renet`.

    `.resolve()` on the root is load-bearing: bash's `cd X && pwd` reports the
    LOGICAL path it was handed while `pathlib.resolve()` follows symlinks, and
    the root string is printed verbatim in `RENET_BINARY=<path>`. Handing both
    subjects an already-resolved root makes the two agree for the right reason.
    """
    root = where.resolve() / "tree"
    (root / ".ci" / "scripts" / "infra").mkdir(parents=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "infra").mkdir(parents=True)
    shutil.copy2(TWIN, root / TWIN_REL)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / "common.sh")
    shutil.copy2(PORT, root / PORT_REL)

    if submodule:
        src = root / "private" / "renet"
        src.mkdir(parents=True)
        if build_sh:
            script = src / "build.sh"
            script.write_text(
                FAKE_BUILD_SH
                % {
                    "log": str(root.parent / "buildlog.txt"),
                    "root": str(root),
                    "rc": build_rc,
                    "produces": produces,
                },
                encoding="utf-8",
            )
            script.chmod(0o755)
        if binary is not None:
            (src / "bin").mkdir(exist_ok=True)
            (src / "bin" / binary).write_text("stale-binary\n", encoding="utf-8")
        if stamp is not None:
            (src / "bin").mkdir(exist_ok=True)
            (src / "bin" / ".renet-build-identity").write_text(stamp, encoding="utf-8")
    return root


def _binder(where: pathlib.Path, *, go: bool, system: str, exclude: tuple[str, ...]) -> str:
    """The COMPLETE PATH for one run: named tools, plus the two fakes."""
    binder = where / "bin"
    binder.mkdir(parents=True, exist_ok=True)
    for tool in NEEDED:
        if tool in exclude:
            continue
        target = shutil.which(tool)
        if target is None:
            continue
        link = binder / tool
        if not link.exists():
            link.symlink_to(target)

    uname = binder / "uname"
    uname.write_text(FAKE_UNAME % {"system": system}, encoding="utf-8")
    uname.chmod(0o755)

    if go:
        gob = binder / "go"
        gob.write_text(FAKE_GO, encoding="utf-8")
        gob.chmod(0o755)

    assert shutil.which("bash", path=str(binder)), "the restricted PATH cannot run the twin"
    assert shutil.which("python3", path=str(binder)), "the restricted PATH cannot run the port"
    if not go:
        assert shutil.which("go", path=str(binder)) is None, (
            "the restricted PATH still resolves go; the no-go case would be vacuous"
        )
    for tool in exclude:
        assert shutil.which(tool, path=str(binder)) is None, (
            "%r survived exclusion; the case that needs it absent would be vacuous" % tool
        )
    return str(binder)


def _run(
    subject: pathlib.PurePosixPath,
    root: pathlib.Path,
    argv: tuple[str, ...] = (),
    *,
    go: bool = True,
    system: str = "Linux",
    exclude: tuple[str, ...] = (),
    env_extra: dict[str, str] | None = None,
    github_env: bool = False,
) -> dict[str, object]:
    """Drive one subject and collect all six observables."""
    tag = pathlib.Path(subject).name
    env = {
        "PATH": _binder(root.parent / ("fxbin-%s" % tag), go=go, system=system, exclude=exclude),
        "HOME": str(root.parent),
        "PYTHONDONTWRITEBYTECODE": "1",
        # The port imports `rediacc_ci.log`; the COPY under the fixture is what
        # runs, so the package has to come from the real checkout. This is the
        # only thing the fixture borrows from outside itself.
        "PYTHONPATH": str(ROOT / ".ci"),
    }
    env.update(env_extra or {})
    gh = root.parent / ("github-env-%s" % tag)
    if github_env:
        gh.write_text("", encoding="utf-8")
        env["GITHUB_ENV"] = str(gh)

    runner = "bash" if subject.suffix == ".sh" else "python3"
    proc = subprocess.run(
        [runner, str(root / subject), *argv],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
    )

    log = root.parent / "buildlog.txt"
    calls = []
    if log.exists():
        calls = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
        log.unlink()

    stamp_path = root / "private" / "renet" / "bin" / ".renet-build-identity"
    bin_dir = root / "private" / "renet" / "bin"
    return {
        "exit": proc.returncode,
        "stdout": proc.stdout.replace(str(root), "<root>"),
        "stderr": proc.stderr.replace(str(root), "<root>"),
        "calls": calls,
        "stamp": stamp_path.read_text(encoding="utf-8") if stamp_path.exists() else None,
        "binaries": sorted(p.name for p in bin_dir.iterdir()) if bin_dir.is_dir() else None,
        # Masked like stdout/stderr: the fixture root differs between the two
        # runs by construction, and an unmasked comparison would report every
        # case as divergent for that reason alone.
        "github_env": (
            gh.read_text(encoding="utf-8").replace(str(root), "<root>") if github_env else None
        ),
    }


KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIexamplekeymaterialforthetestfixture"

# `default|` plus the first 16 hex of sha256("") and of KEY. Computed here rather
# than imported from the port: a constant the SUBJECT supplies cannot contradict
# the subject.
EMPTY_KEY_DIGEST = "e3b0c44298fc1c14"

CASES = [
    pytest.param({}, {}, id="fresh-build-no-args"),
    pytest.param({}, {"argv": ("--nolicense",)}, id="fresh-build-nolicense"),
    pytest.param({}, {"argv": ("--license",)}, id="fresh-build-license"),
    pytest.param({}, {"argv": ("--nolicense", "--license")}, id="both-flags-license-wins"),
    pytest.param({}, {"argv": ("--nolicence",)}, id="typo-flag-silently-dropped"),
    pytest.param({}, {"argv": ("--verbose", "--nolicense")}, id="unknown-arg-dropped-flag-kept"),
    pytest.param(
        {},
        {"argv": ("--nolicense",), "env_extra": {"RDC_RENET_LICENSE": "1"}},
        id="license-env-overrides-flag",
    ),
    pytest.param(
        {},
        {"env_extra": {"RDC_RENET_LICENSE": "0"}},
        id="license-env-zero-is-not-enforce",
    ),
    pytest.param(
        {},
        {"env_extra": {"ACCOUNT_ED25519_PUBLIC_KEY": KEY}},
        id="key-changes-the-identity",
    ),
    pytest.param({"submodule": False}, {}, id="no-submodule"),
    pytest.param(
        {"binary": "renet", "stamp": "default|" + EMPTY_KEY_DIGEST},
        {},
        id="stamp-matches-skip-build",
    ),
    pytest.param(
        {"binary": "renet", "stamp": "nolicense|" + EMPTY_KEY_DIGEST},
        {},
        id="stamp-mismatch-rebuild",
    ),
    pytest.param({"binary": "renet"}, {}, id="binary-without-stamp-rebuild"),
    pytest.param(
        {"binary": "renet", "stamp": "default|" + EMPTY_KEY_DIGEST + "\n"},
        {},
        id="stamp-with-trailing-newline-still-matches",
    ),
    pytest.param({"build_rc": 3}, {}, id="build-sh-fails"),
    pytest.param({"produces": ""}, {}, id="build-sh-produces-nothing"),
    pytest.param({"produces": "renet.exe"}, {"system": "MINGW64_NT-10.0"}, id="mingw-exe-suffix"),
    pytest.param({"produces": "renet"}, {"system": "Darwin"}, id="darwin-no-suffix"),
    pytest.param({}, {"go": False}, id="no-go-nothing-to-delete"),
    pytest.param(
        {"binary": "renet", "stamp": "nolicense|" + EMPTY_KEY_DIGEST},
        {"go": False},
        id="no-go-after-deleting-the-binary",
    ),
    pytest.param({}, {"github_env": True}, id="github-env-appended"),
    pytest.param(
        {"binary": "renet", "stamp": "default|" + EMPTY_KEY_DIGEST},
        {"github_env": True},
        id="github-env-appended-on-the-skip-path",
    ),
]


@pytest.mark.parametrize(("fixture_kw", "run_kw"), CASES)
def test_port_and_twin_agree(tmp_path, fixture_kw, run_kw):
    root_a = _fixture(tmp_path / "a", **fixture_kw)
    old = _run(TWIN_REL, root_a, **run_kw)

    root_b = _fixture(tmp_path / "b", **fixture_kw)
    new = _run(PORT_REL, root_b, **run_kw)

    for field in ("exit", "stdout", "stderr", "calls", "stamp", "binaries", "github_env"):
        assert new[field] == old[field], "%s diverged:\n twin: %r\n port: %r" % (
            field,
            old[field],
            new[field],
        )


def test_the_fake_build_is_actually_reached(tmp_path):
    """ANTI-VACUITY. Every comparison above is worthless if build.sh never ran."""
    root = _fixture(tmp_path / "v")
    out = _run(PORT_REL, root)
    assert out["calls"], "the recording build.sh was never invoked; this file proves nothing"
    fields = out["calls"][0].split("\t")
    assert fields[0] == "build.sh"
    assert fields[1] == "private/renet", "build.sh ran in %r, not the renet source dir" % fields[1]
    assert fields[2:] == ["dev"], "build.sh got %r, not the twin's `dev`" % fields[2:]
    assert out["exit"] == 0, "the happy path must succeed: %r" % out


def test_the_skip_path_really_skips(tmp_path):
    """CONTROL for the case above: a matching stamp must run NO build at all.

    A port that rebuilt unconditionally would satisfy every positive assertion in
    this file and would re-run a Go build in ten CI steps."""
    root = _fixture(tmp_path / "s", binary="renet", stamp="default|" + EMPTY_KEY_DIGEST)
    out = _run(PORT_REL, root)
    assert out["calls"] == [], "a build ran despite a matching stamp: %r" % out["calls"]
    assert "already built the same way" in out["stderr"]


def test_the_stamp_is_not_written_when_the_build_fails(tmp_path):
    """The twin's Step 5 comment is the whole reason the stamp exists; a stamp
    written ahead of a failed build makes the NEXT run skip and hand back
    nothing."""
    for subject in (TWIN_REL, PORT_REL):
        root = _fixture(tmp_path / ("f-%s" % subject.name), build_rc=3)
        out = _run(subject, root)
        assert out["exit"] == 3, "%s: expected build.sh's own status, got %r" % (
            subject.name,
            out["exit"],
        )
        assert out["stamp"] is None, "%s: stamped a failed build" % subject.name


def test_a_deleted_binary_is_not_restored_when_go_is_missing(tmp_path):
    """A REAL DEFECT IN THE TWIN, pinned in BOTH implementations.

    The twin removes the differently-built binary BEFORE it checks that go is
    installed, so a host without go loses a working binary and gets exit 1. The
    port keeps that order deliberately (see its comment): reordering would make
    the port's filesystem effect differ from the twin's on the exact input that
    exposes the bug, and the differential would then certify the wrong script.
    Reported, not fixed -- the repair is a cutover-box decision.
    """
    for subject in (TWIN_REL, PORT_REL):
        root = _fixture(
            tmp_path / ("d-%s" % subject.name),
            binary="renet",
            stamp="nolicense|" + EMPTY_KEY_DIGEST,
        )
        out = _run(subject, root, go=False)
        assert out["exit"] == 1, "%s: %r" % (subject.name, out["exit"])
        assert out["binaries"] == [".renet-build-identity"], (
            "%s: the binary survived, so the defect is gone and this test is stale: %r"
            % (subject.name, out["binaries"])
        )
        assert "Go is not installed" in out["stderr"]


def test_a_missing_sha256sum_is_the_one_deliberate_divergence(tmp_path):
    """THE ONE DELIBERATE DIVERGENCE, asserted in BOTH directions, and it is a
    REAL DEFECT in the twin rather than a stylistic difference.

    With no `sha256sum` on PATH -- stock macOS ships `shasum`, not `sha256sum`,
    and this script advertises itself as locally runnable -- the twin does NOT
    die. `printf '%s|%s' "$mode" "$(... | sha256sum | cut ...)"` puts the failing
    pipeline in a COMMAND SUBSTITUTION USED AS AN ARGUMENT, so `set -e` and
    `pipefail` never see a failing command: printf succeeds with an empty second
    field and the identity collapses to `default|`.

    The consequence is precise and is exactly what the stamp was introduced to
    prevent: the ACCOUNT_ED25519_PUBLIC_KEY half of the identity disappears, so
    a binary linked against one key is handed to a job wanting another and no
    rebuild happens. The only trace is one line of stderr under exit 0.

    A first draft of this test asserted exit 127 and failed, which is how the
    defect was found: the premise "a failing pipeline under `set -e` kills the
    script" is false inside a command substitution.

    The port stamps the real digest. If either half ever changes, it reds here
    rather than on somebody's laptop. Reported, not fixed.
    """
    root_a = _fixture(tmp_path / "ha")
    old = _run(TWIN_REL, root_a, exclude=("sha256sum",))
    root_b = _fixture(tmp_path / "hb")
    new = _run(PORT_REL, root_b, exclude=("sha256sum",))

    assert old["exit"] == 0, "the twin's quiet success is the premise; it exited %r" % old["exit"]
    assert "sha256sum: command not found" in old["stderr"], (
        "the twin's only trace of the failure: %r" % old["stderr"]
    )
    assert old["stamp"] == "default|", (
        "the twin's identity must have lost its key component: %r" % old["stamp"]
    )
    assert new["exit"] == 0, "the port must also succeed; it exited %r" % new["exit"]
    assert new["stamp"] == "default|" + EMPTY_KEY_DIGEST, (
        "the port must keep the key component: %r" % new["stamp"]
    )
    # The rest of the run agrees, which is what makes this a scoped divergence
    # rather than two unrelated programs.
    assert new["stdout"] == old["stdout"]
    assert new["calls"] == old["calls"]
    assert new["binaries"] == old["binaries"]


def test_the_collapsed_identity_defeats_the_rebuild_the_stamp_exists_for(tmp_path):
    """The consequence of the case above, demonstrated rather than asserted in
    prose: with `sha256sum` gone, TWO DIFFERENT KEYS produce the SAME twin stamp,
    so the second run skips the build. The port rebuilds.

    This is the incident build-renet.sh:44-63 describes, reachable again on any
    host without coreutils' `sha256sum`.
    """
    root = _fixture(tmp_path / "k1")
    first = _run(
        TWIN_REL, root, exclude=("sha256sum",), env_extra={"ACCOUNT_ED25519_PUBLIC_KEY": "KEY-A"}
    )
    assert first["stamp"] == "default|"
    second = _run(
        TWIN_REL, root, exclude=("sha256sum",), env_extra={"ACCOUNT_ED25519_PUBLIC_KEY": "KEY-B"}
    )
    assert second["calls"] == [], "the twin rebuilt after all, so this test is stale"
    assert "already built the same way" in second["stderr"]

    proot = _fixture(tmp_path / "k2")
    pfirst = _run(
        PORT_REL, proot, exclude=("sha256sum",), env_extra={"ACCOUNT_ED25519_PUBLIC_KEY": "KEY-A"}
    )
    assert pfirst["stamp"] != "default|"
    psecond = _run(
        PORT_REL, proot, exclude=("sha256sum",), env_extra={"ACCOUNT_ED25519_PUBLIC_KEY": "KEY-B"}
    )
    assert psecond["calls"], "the port must rebuild for a different key: %r" % psecond
    assert "built differently" in psecond["stderr"]


def test_the_identity_digest_is_the_twins_own_pipeline():
    """`hashlib` is only allowed to stand in for `sha256sum | cut -c1-16` if it
    produces the same 16 characters. Driven against the REAL bash pipeline
    rather than against a constant -- a constant copied out of the port cannot
    contradict the port -- for both the empty key and a realistic one.

    The port half runs in a SUBPROCESS with a controlled environment, because
    `build_identity()` reads `$RDC_RENET_LICENSE` and `$ACCOUNT_ED25519_PUBLIC_KEY`
    directly (deliberately: an `os.environ` alias is invisible to the env
    manifest reader), and a developer with either exported would otherwise see a
    green here for the wrong reason.
    """
    env = dict(os.environ)
    env.pop("RDC_RENET_LICENSE", None)
    for key in ("", KEY):
        expected = subprocess.run(
            ["bash", "-c", 'printf "%s" "$1" | sha256sum | cut -c1-16', "_", key],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert len(expected) == 16, "the bash half produced %r, not 16 chars" % expected
        got = subprocess.run(
            ["python3", "-c", IDENTITY_HARNESS, str(ROOT / ".ci")],
            capture_output=True,
            text=True,
            check=True,
            env={**env, "ACCOUNT_ED25519_PUBLIC_KEY": key, "PYTHONDONTWRITEBYTECODE": "1"},
        ).stdout.strip()
        assert got == "default|%s" % expected, "digest diverged for key %r: %r" % (key, got)


def test_build_args_drops_what_the_twin_drops():
    """The pure half of the filter, driven directly. The parametrised cases
    above prove the two agree; this one names WHAT they agree on, so a reader
    does not have to reconstruct it from a build log."""
    assert build_renet.build_args([]) == []
    assert build_renet.build_args(["--nolicence"]) == []
    assert build_renet.build_args(["-v", "--license", "x"]) == ["--license"]
    assert build_renet.build_args(["--nolicense", "--license"]) == ["--nolicense", "--license"]
