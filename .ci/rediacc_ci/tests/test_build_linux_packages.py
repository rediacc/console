"""Differential: `.ci/rediacc_ci/build/build_linux_packages.py` against its twin
`.ci/scripts/build/build-linux-packages.sh`.

WHY A DIFFERENTIAL AND NOT A UNIT TEST. The claim a port makes is not "the new
code is correct", it is "the new code says what the old code said". Only running
BOTH, on the same fixture, in the same run, can support that.

WHAT IS COMPARED. This script produces no output of its own on the happy path --
it is eight delegations and nothing else -- so a stdout comparison would be a
comparison of two empty strings. Every case compares:

  1. the exit code, which on failure is `build-linux-pkg.sh`'s own;
  2. stdout and stderr, separately, which carry the delegate's output verbatim;
  3. the CALL LOG: every invocation of `build-linux-pkg.sh`, its FULL argv and
     its cwd, in order. This is the entire product of the script. The ORDER
     matters and is compared as a list rather than a set: `set -e` aborts the
     matrix at the first failure, so which packages exist after a failed run is
     decided by the nesting order (format outer, arch inner);
  4. `dist/packages/` afterwards, by name, so a port that delegated correctly and
     forgot the `mkdir -p` shows up.

THE DELEGATE IS A FAKE, AND IT HAS TO BE. The real
`.ci/scripts/build/build-linux-pkg.sh` runs nfpm, reads `constants.sh`, and on
the release path imports a GPG key and SIGNS things. It is also a DIFFERENT
file, not this wave's port target. The fixture therefore puts a recording stub
at that exact path -- the path is part of what is under test, since the twin
addresses it repo-root-relatively -- and both subjects call the same stub.

PATH IS REPLACED, NEVER PREPENDED. Nothing here needs `nfpm` or `npm`, but the
subject `cd`s to a root it derives itself, and a subject that derived the WRONG
root would find the real `.ci/scripts/build/build-linux-pkg.sh` and run a real
nfpm build. `_binder` builds the ENTIRE PATH from named tools so that cannot
happen, and asserts every exclusion really took.

THE ONE DELIBERATE DIVERGENCE IS TESTED, NOT HIDDEN.
`test_an_unset_next_version_names_the_program_that_refused` masks the
`<path>: line <n>: ` prefix bash and the port each put on their own refusal, and
compares the rest byte for byte -- then asserts the two unmasked strings DIFFER,
so the test still means something if someone makes the port print the twin's
path. Same treatment for a missing delegate in
`test_a_missing_delegate_agrees_on_127_and_not_on_the_diagnostic`.
"""

import pathlib
import re
import shutil
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.build import build_linux_packages

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "build" / "build-linux-packages.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "build" / "build_linux_packages.py"

TWIN_REL = pathlib.PurePosixPath(".ci/scripts/build/build-linux-packages.sh")
PORT_REL = pathlib.PurePosixPath(".ci/rediacc_ci/build/build_linux_packages.py")
DELEGATE_REL = pathlib.PurePosixPath(".ci/scripts/build/build-linux-pkg.sh")

# The recording delegate. Stands in for the real build-linux-pkg.sh, which runs nfpm and signs packages. `FAIL_ON` is a 1-based call index so a case can fail the third of eight and the comparison can check that the remaining five never happened.
#
# It writes its argv as `call: ...` on STDOUT rather than through a log-step helper, and that is not cosmetic: `scripts/lib/shadow-gate.ts` classifies any line starting with `→ ` or `✓ ` as CHATTER before `--finding-re` is consulted, so a delegate that reported like `common.sh` would make every ledger row read VACUOUS_BOTH_EMPTY. The `call: ` prefix is what the ledger's
# `--finding-re` scopes to.
FAKE_DELEGATE = """#!/usr/bin/env python3
import os, pathlib, sys
LOG = %(log)r
ROOT = %(root)r
FAIL_ON = %(fail_on)d
RC = %(rc)d
COUNTER = pathlib.Path(LOG + ".n")
n = int(COUNTER.read_text()) + 1 if COUNTER.exists() else 1
COUNTER.write_text(str(n))
with pathlib.Path(LOG).open("a", encoding="utf-8") as fh:
    fh.write("call: build-linux-pkg " + " ".join(sys.argv[1:]) + "\\n")
    fh.write("cwd: " + os.path.relpath(os.getcwd(), ROOT) + "\\n")
args = sys.argv[1:]
def opt(name):
    return args[args.index(name) + 1] if name in args else "?"
if FAIL_ON and n == FAIL_ON:
    sys.stderr.write("fake build-linux-pkg: refusing call %%d\\n" %% n)
    sys.exit(RC)
out = pathlib.Path(opt("--output"))
out.mkdir(parents=True, exist_ok=True)
(out / ("rdc-%%s-%%s.%%s" %% (opt("--version"), opt("--arch"), opt("--format")))).write_text(
    "package\\n", encoding="utf-8"
)
"""

# Everything both subjects need once PATH is rebuilt from scratch. Named rather than derived: a PATH built by copying "everything except X" is a PATH nobody can state, and the first tool it forgot would look like a divergence in the subject rather than a hole in the harness.
NEEDED = ("bash", "sh", "python3", "env", "uname", "dirname", "cat", "mkdir", "rm")

# `<path>: line <n>: ` -- the prefix bash puts on its own diagnostics, and the shape the port reproduces with its own path. Masked ONLY in the two tests that are about that divergence.
LINE_PREFIX = re.compile(r"^[^\n]*: line \d+: ", re.MULTILINE)

# The eight (format, arch) pairs, in the twin's nesting order, as a reader can check them against `build-linux-packages.sh:45-58` without running anything.
EXPECTED_MATRIX = [
    ("deb", "amd64"),
    ("deb", "arm64"),
    ("rpm", "amd64"),
    ("rpm", "arm64"),
    ("apk", "amd64"),
    ("apk", "arm64"),
    ("archlinux", "amd64"),
    ("archlinux", "arm64"),
]


def _fixture(
    where: pathlib.Path,
    *,
    binaries: tuple[str, ...] = ("rdc-linux-x64", "rdc-linux-arm64"),
    packages_dir_exists: bool = False,
) -> pathlib.Path:
    """A tree shaped like the repository, holding COPIES of both subjects.

    Copies, because each subject derives the console root from its own location
    (`BASH_SOURCE`/`__file__`, then three directories up). Driving the TRACKED
    files with a `cwd` would point them at the real repository, where the
    delegate is the REAL build-linux-pkg.sh and `dist/packages` is real output.

    `binaries` are created under `dist/cli/`, which is the only thing the musl
    decision looks at. Note the twin never checks that the glibc binaries exist
    either -- that is `build-linux-pkg.sh`'s job -- so a fixture with an EMPTY
    tuple is a legitimate case and not a broken one.
    """
    root = where.resolve() / "tree"
    (root / ".ci" / "scripts" / "build").mkdir(parents=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "build").mkdir(parents=True)
    shutil.copy2(TWIN, root / TWIN_REL)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / "common.sh")
    shutil.copy2(PORT, root / PORT_REL)

    cli = root / "dist" / "cli"
    cli.mkdir(parents=True)
    for name in binaries:
        (cli / name).write_text("binary:" + name + "\n", encoding="utf-8")
    if packages_dir_exists:
        (root / "dist" / "packages").mkdir(parents=True)
    # The delegate stub is written by `_run`, not here: it needs that run's own
    # log path baked into it, and `_run(delegate=False)` is how a case omits it.
    return root


def _binder(where: pathlib.Path, *, exclude: tuple[str, ...]) -> str:
    """The COMPLETE PATH for one run. No fakes live here: the only thing either
    subject executes is the delegate, and the delegate is addressed by path."""
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
    assert shutil.which("bash", path=str(binder)), "the restricted PATH cannot run the twin"
    assert shutil.which("python3", path=str(binder)), "the restricted PATH cannot run the port"
    assert shutil.which("nfpm", path=str(binder)) is None, (
        "nfpm is reachable on the restricted PATH; a subject that found the REAL "
        "delegate could run a real package build"
    )
    for tool in exclude:
        assert shutil.which(tool, path=str(binder)) is None, (
            "%r survived exclusion; the case that needs it absent would be vacuous" % tool
        )
    return str(binder)


def _run(
    subject: pathlib.PurePosixPath,
    root: pathlib.Path,
    *,
    next_version: str | None = "1.2.3",
    delegate: bool = True,
    fail_on: int = 0,
    rc: int = 3,
    exclude: tuple[str, ...] = (),
) -> dict[str, object]:
    """Drive one subject and collect all four observables."""
    tag = pathlib.Path(subject).name
    log = root.parent / ("calls-%s.txt" % tag)

    if delegate:
        stub = root / DELEGATE_REL
        stub.write_text(
            FAKE_DELEGATE % {"log": str(log), "root": str(root), "fail_on": fail_on, "rc": rc},
            encoding="utf-8",
        )
        stub.chmod(0o755)

    env = {
        "PATH": _binder(root.parent / ("fxbin-%s" % tag), exclude=exclude),
        "HOME": str(root.parent),
        "PYTHONDONTWRITEBYTECODE": "1",
        "LC_ALL": "C",
        "LANG": "C",
        # The port imports `rediacc_ci`; the COPY under the fixture is what runs,
        # so the package has to come from the real checkout. This is the only thing the fixture borrows from outside itself.
        "PYTHONPATH": str(ROOT / ".ci"),
    }
    if next_version is not None:
        env["NEXT_VERSION"] = next_version

    runner = "bash" if subject.suffix == ".sh" else "python3"
    proc = subprocess.run(
        [runner, str(root / subject)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
    )

    calls = []
    if log.exists():
        calls = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
        log.unlink()
    counter = pathlib.Path(str(log) + ".n")
    if counter.exists():
        counter.unlink()

    packages = root / "dist" / "packages"
    return {
        "exit": proc.returncode,
        "stdout": proc.stdout.replace(str(root), "<root>"),
        "stderr": proc.stderr.replace(str(root), "<root>"),
        "calls": calls,
        "packages": sorted(p.name for p in packages.iterdir()) if packages.is_dir() else None,
    }


FIELDS = ("exit", "stdout", "stderr", "calls", "packages")

CASES = [
    pytest.param({}, {}, id="no-musl-binaries-glibc-fallback"),
    pytest.param(
        {
            "binaries": (
                "rdc-linux-x64",
                "rdc-linux-arm64",
                "rdc-linux-musl-x64",
                "rdc-linux-musl-arm64",
            )
        },
        {},
        id="both-musl-binaries-preferred-for-apk",
    ),
    pytest.param(
        {"binaries": ("rdc-linux-x64", "rdc-linux-arm64", "rdc-linux-musl-x64")},
        {},
        id="only-x64-musl-mixed-apk",
    ),
    pytest.param({"binaries": ()}, {}, id="no-binaries-at-all-still-delegates"),
    pytest.param({"packages_dir_exists": True}, {}, id="output-dir-already-there"),
    pytest.param({}, {"next_version": "0.0.0-dev"}, id="placeholder-version-is-just-a-string"),
    pytest.param({}, {"next_version": "1.2.3-rc.1+build.7"}, id="semver-with-metadata"),
    pytest.param({}, {"fail_on": 1, "rc": 3}, id="delegate-fails-on-the-first-call"),
    pytest.param({}, {"fail_on": 5, "rc": 9}, id="delegate-fails-at-the-first-apk"),
    pytest.param({}, {"fail_on": 8, "rc": 1}, id="delegate-fails-on-the-last-call"),
]


@pytest.mark.parametrize(("fixture_kw", "run_kw"), CASES)
def test_port_and_twin_agree(tmp_path, fixture_kw, run_kw):
    root_a = _fixture(tmp_path / "a", **fixture_kw)
    old = _run(TWIN_REL, root_a, **run_kw)

    root_b = _fixture(tmp_path / "b", **fixture_kw)
    new = _run(PORT_REL, root_b, **run_kw)

    for field in FIELDS:
        assert new[field] == old[field], "%s diverged:\n twin: %r\n port: %r" % (
            field,
            old[field],
            new[field],
        )


def test_the_delegate_is_actually_reached_eight_times(tmp_path):
    """ANTI-VACUITY. Every comparison above is worthless if the delegate never
    ran, and this also pins the MATRIX and the CWD: eight invocations, in the
    twin's nesting order, all from the repository root.
    """
    root = _fixture(tmp_path / "v")
    out = _run(PORT_REL, root)
    assert out["exit"] == 0, out
    calls = [c for c in out["calls"] if c.startswith("call: ")]
    cwds = {c for c in out["calls"] if c.startswith("cwd: ")}
    assert len(calls) == 8, "expected the whole matrix, got %r" % calls
    assert cwds == {"cwd: ."}, "the delegate did not run from the repo root: %r" % cwds
    seen = [
        (c.split("--format ")[1].split(" ")[0], c.split("--arch ")[1].split(" ")[0]) for c in calls
    ]
    assert seen == EXPECTED_MATRIX, seen
    assert out["packages"] == [
        "rdc-1.2.3-amd64.apk",
        "rdc-1.2.3-amd64.archlinux",
        "rdc-1.2.3-amd64.deb",
        "rdc-1.2.3-amd64.rpm",
        "rdc-1.2.3-arm64.apk",
        "rdc-1.2.3-arm64.archlinux",
        "rdc-1.2.3-arm64.deb",
        "rdc-1.2.3-arm64.rpm",
    ], out["packages"]


def test_a_failure_stops_the_matrix_rather_than_collecting(tmp_path):
    """CONTROL in the other direction: after a failing delegate, NOTHING else
    runs. A port that ran all eight and reported at the end would satisfy every
    positive assertion in this file and would keep packaging against a binary an
    earlier step had already refused."""
    for subject in (TWIN_REL, PORT_REL):
        root = _fixture(tmp_path / ("s-%s" % subject.name))
        out = _run(subject, root, fail_on=3, rc=5)
        assert out["exit"] == 5, "%s: %r" % (subject.name, out["exit"])
        calls = [c for c in out["calls"] if c.startswith("call: ")]
        assert len(calls) == 3, "%s: the matrix kept going: %r" % (subject.name, calls)


def test_the_musl_substitution_only_touches_apk(tmp_path):
    """The Alpine fallback, named rather than left inside a call log.

    With all four binaries present, exactly the two `apk` invocations must carry
    `rdc-linux-musl-*` and the other six must not. A port that substituted for
    every format would produce six packages containing a musl binary for glibc
    distributions, and the call-log comparison above would pass on both sides
    only if BOTH were wrong.
    """
    root = _fixture(
        tmp_path / "m",
        binaries=(
            "rdc-linux-x64",
            "rdc-linux-arm64",
            "rdc-linux-musl-x64",
            "rdc-linux-musl-arm64",
        ),
    )
    out = _run(PORT_REL, root)
    musl = [c for c in out["calls"] if "rdc-linux-musl-" in c]
    assert len(musl) == 2, musl
    for call in musl:
        assert "--format apk" in call, call


def test_the_glibc_fallback_is_real_and_silent(tmp_path):
    """The other half of the same decision, and the one the twin's own header
    calls out: with no musl binary, `apk` packages the GLIBC binary and says
    nothing about it. Pinned in both, because a `.apk` holding a glibc binary
    installs cleanly on Alpine and fails at exec time.
    """
    for subject in (TWIN_REL, PORT_REL):
        root = _fixture(tmp_path / ("g-%s" % subject.name))
        out = _run(subject, root)
        apk = [c for c in out["calls"] if "--format apk" in c]
        assert len(apk) == 2, "%s: %r" % (subject.name, apk)
        for call in apk:
            assert "rdc-linux-musl-" not in call, call
            assert "--binary dist/cli/rdc-linux-" in call, call
        assert "musl" not in out["stderr"], (
            "%s: something now warns about the fallback, so this test is stale: %r"
            % (subject.name, out["stderr"])
        )


def test_an_unset_next_version_names_the_program_that_refused(tmp_path):
    """THE ONE DELIBERATE DIVERGENCE, asserted in both directions with the
    `<path>: line <n>: ` prefix masked.

    `:?` fires on unset AND on empty, so both are driven. The twin's own message
    text -- which embeds `build-linux-packages.sh:` a second time, producing a
    line that reads as though the filename appears twice -- is reproduced
    verbatim, and that is what the masked comparison checks.
    """
    for version in (None, ""):
        root_a = _fixture(tmp_path / ("ua-%s" % (version is None)))
        old = _run(TWIN_REL, root_a, next_version=version)
        root_b = _fixture(tmp_path / ("ub-%s" % (version is None)))
        new = _run(PORT_REL, root_b, next_version=version)

        assert old["exit"] == 1, old
        assert new["exit"] == 1, new
        assert old["calls"] == [], "the twin delegated without a version"
        assert new["calls"] == [], "the port delegated without a version"
        assert LINE_PREFIX.sub("<prog>: line N: ", new["stderr"]) == LINE_PREFIX.sub(
            "<prog>: line N: ", old["stderr"]
        ), "masked stderr diverged:\n twin: %r\n port: %r" % (old["stderr"], new["stderr"])
        assert "NEXT_VERSION: build-linux-packages.sh: NEXT_VERSION must be set" in old["stderr"], (
            "the twin's message changed, so the port's copy of it is stale: %r" % old["stderr"]
        )
        assert old["stderr"] != new["stderr"], (
            "the two diagnostics are byte-identical, so the mask is hiding nothing "
            "and this case belongs in the parametrised set"
        )


def test_a_missing_delegate_agrees_on_127_and_not_on_the_diagnostic(tmp_path):
    """Same treatment for the other interpreter-owned message.

    `build-linux-pkg.sh` absent: bash reports "No such file or directory" against
    its own path and line and exits 127. The port takes the same status and
    prints the same shape against its own. The status is what the workflow step
    branches on, so it is asserted equal; the text is asserted DIFFERENT so the
    divergence stays visible.
    """
    root_a = _fixture(tmp_path / "na")
    old = _run(TWIN_REL, root_a, delegate=False)
    root_b = _fixture(tmp_path / "nb")
    new = _run(PORT_REL, root_b, delegate=False)

    assert old["exit"] == 127, old
    assert new["exit"] == 127, new
    assert LINE_PREFIX.sub("<prog>: line N: ", new["stderr"]) == LINE_PREFIX.sub(
        "<prog>: line N: ", old["stderr"]
    ), "masked stderr diverged:\n twin: %r\n port: %r" % (old["stderr"], new["stderr"])
    assert old["stderr"] != new["stderr"], "the mask is hiding nothing"


def test_binary_for_is_the_twins_parameter_expansion():
    """The pure half, driven against BASH's own `${binary/rdc-linux-/...}` rather
    than against a constant: a constant copied out of the port cannot contradict
    the port. Only the SUBSTITUTION is compared here -- the `-f` test needs a
    filesystem and is covered above.
    """
    for binary in ("dist/cli/rdc-linux-x64", "dist/cli/rdc-linux-arm64", "rdc-linux-rdc-linux-x"):
        expected = subprocess.run(
            ["bash", "-c", 'b="$1"; printf "%s" "${b/rdc-linux-/rdc-linux-musl-}"', "_", binary],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        got = binary.replace(build_linux_packages.GLIBC_INFIX, build_linux_packages.MUSL_INFIX, 1)
        assert got == expected, "substitution diverged for %r: %r vs %r" % (binary, got, expected)


def test_invocations_is_lazy_so_the_f_test_happens_per_pair(tmp_path):
    """`invocations()` is a GENERATOR on purpose, and this is what that buys.

    The twin evaluates `[[ -f "$musl_binary" ]]` immediately before the
    invocation it decides. A musl binary that appears midway through the run --
    which a delegate could plausibly produce -- therefore changes the LATER apk
    decision and not the earlier one. A list comprehension would resolve all
    eight against the filesystem as it stood at the start, which is a different
    program on exactly that input.
    """
    cli = tmp_path / "dist" / "cli"
    cli.mkdir(parents=True)
    (cli / "rdc-linux-x64").write_text("x", encoding="utf-8")
    (cli / "rdc-linux-arm64").write_text("x", encoding="utf-8")

    import os  # noqa: PLC0415 -- one chdir, scoped to this case

    previous = os.getcwd()
    os.chdir(tmp_path)
    try:
        produced = []
        for index, argv in enumerate(build_linux_packages.invocations("1.0.0")):
            produced.append(argv[argv.index("--binary") + 1])
            # After the fourth invocation (both debs, both rpms) the musl binary appears. A lazy generator must pick it up for the apk pair that
            # follows; an eager list cannot.
            if index == 3:
                (cli / "rdc-linux-musl-x64").write_text("x", encoding="utf-8")
    finally:
        os.chdir(previous)

    assert produced[4] == "dist/cli/rdc-linux-musl-x64", (
        "the apk decision did not see a binary created mid-run, so `invocations` "
        "is no longer lazy: %r" % produced
    )
    assert produced[5] == "dist/cli/rdc-linux-arm64", produced
