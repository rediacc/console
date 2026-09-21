"""`rediacc_ci.build.build_linux_packages`, driven against the bytes its bash twin produced.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/build/build-linux-packages.sh` and the port over two identically built fixture trees and compared all five observables below. The K=5 ledger `.ci/shadow/w7p6-build-linux-packages.observations.jsonl` recorded that comparison over five distinct trees. The twin has now been deleted and every case that executed it compares
against `goldens/build-linux-packages/`, which holds the twin's OWN recorded results, captured from the tracked script on its last day in the tree. Each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that produced them.

WHAT IS COMPARED, and what each recording therefore carries. This script produces no output of its own on the happy path -- it is eight delegations and nothing else -- so a stdout comparison would be a comparison of two empty strings. Every case compares:

  1. the exit code, which on failure is `build-linux-pkg.sh`'s own;
  2. stdout and stderr, separately, which carry the delegate's output verbatim;
  3. the CALL LOG: every invocation of `build-linux-pkg.sh`, its FULL argv and
     its cwd, in order. This is the entire product of the script. The ORDER
     matters and is recorded as a list rather than a set: `set -e` aborted the
     matrix at the first failure, so which packages exist after a failed run is
     decided by the nesting order (format outer, arch inner);
  4. `dist/packages/` afterwards, by name, so a port that delegated correctly and
     forgot the `mkdir -p` shows up.

THE DELEGATE IS A FAKE, AND IT HAS TO BE. The real `.ci/scripts/build/build-linux-pkg.sh` runs nfpm, reads `constants.sh`, and on the release path imports a GPG key and SIGNS things. It is also a DIFFERENT file, still tracked and not this wave's port target. The fixture therefore puts a recording stub at that exact path -- the path is part of what is under test, since the
twin addressed it repo-root-relatively -- and the port calls the same stub the recording did.

PATH IS REPLACED, NEVER PREPENDED. Nothing here needs `nfpm` or `npm`, but the subject `cd`s to a root it derives itself, and a subject that derived the WRONG root would find the real `.ci/scripts/build/build-linux-pkg.sh` and run a real nfpm build. `_binder` builds the ENTIRE PATH from named tools so that cannot happen, and asserts every exclusion really took.

THE ONE DELIBERATE DIVERGENCE IS TESTED, NOT HIDDEN. `test_an_unset_next_version_names_the_program_that_refused` masks the `<path>: line <n>: ` prefix bash and the port each put on their own refusal, and compares the rest byte for byte -- then asserts the two unmasked strings DIFFER, so the test still means something if someone makes the port print the twin's path. Same
treatment for a missing delegate in `test_a_missing_delegate_agrees_on_127_and_not_on_the_diagnostic`.
"""

import pathlib
import re
import shutil
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.build import build_linux_packages
from rediacc_ci.tests import frozen

ROOT = paths.repo_root()
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "build" / "build_linux_packages.py"

SLUG = "build-linux-packages"

TWIN_REL = pathlib.PurePosixPath(".ci/scripts/build/build-linux-packages.sh")
PORT_REL = pathlib.PurePosixPath(".ci/rediacc_ci/build/build_linux_packages.py")
DELEGATE_REL = pathlib.PurePosixPath(".ci/scripts/build/build-linux-pkg.sh")

# The recording delegate. Stands in for the real build-linux-pkg.sh, which runs nfpm and signs packages. `FAIL_ON` is a 1-based call index so a case can fail the third of eight and the comparison can check that the remaining five never happened.
#
# It writes its argv as `call: ...` on STDOUT rather than through a log-step helper, and that is not cosmetic: `scripts/lib/shadow-gate.ts` classifies any line starting with `→ ` or `✓ ` as CHATTER before `--finding-re` is consulted, so a delegate that reported like `common.sh` would have made every ledger row read VACUOUS_BOTH_EMPTY. The `call: ` prefix is what the ledger's
# `--finding-re` scoped to.
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

# `<path>: line <n>: ` -- the prefix bash put on its own diagnostics, and the shape the port reproduces with its own path. Masked ONLY in the two tests that are about that divergence.
LINE_PREFIX = re.compile(r"^[^\n]*: line \d+: ", re.MULTILINE)

# The eight (format, arch) pairs, in the twin's nesting order, as a reader can check them against the recorded call logs without running anything.
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

CALLS_MARKER = "--- calls ---\n"
PACKAGES_MARKER = "--- packages ---\n"
NO_PACKAGES_DIR = "<no directory>\n"


def _fixture(
    where: pathlib.Path,
    *,
    binaries: tuple[str, ...] = ("rdc-linux-x64", "rdc-linux-arm64"),
    packages_dir_exists: bool = False,
    port_source: str | None = None,
) -> pathlib.Path:
    """A tree shaped like the repository, holding a COPY of the port.

    A copy, because the subject derives the console root from its own location (`__file__`, then three directories up). Driving the TRACKED file with a `cwd` would point it at the real repository, where the delegate is the REAL build-linux-pkg.sh and `dist/packages` is real output.

    `binaries` are created under `dist/cli/`, which is the only thing the musl decision looks at. Note the twin never checked that the glibc binaries exist either -- that is `build-linux-pkg.sh`'s job -- so a fixture with an EMPTY tuple is a legitimate case and not a broken one.
    """
    root = where.resolve() / "tree"
    (root / ".ci" / "scripts" / "build").mkdir(parents=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "build").mkdir(parents=True)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / "common.sh")
    if port_source is None:
        shutil.copy2(PORT, root / PORT_REL)
    else:
        (root / PORT_REL).write_text(port_source, encoding="utf-8")

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
    """The COMPLETE PATH for one run. No fakes live here: the only thing the subject executes is the delegate, and the delegate is addressed by path."""
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
    assert shutil.which("bash", path=str(binder)), "the restricted PATH cannot run a shell"
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
    """Drive one subject and collect all five observables."""
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
        # The port imports `rediacc_ci`; the COPY under the fixture is what runs, so the package has to come from the real checkout. This is the only thing the fixture borrows from outside itself.
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


def render(result: dict[str, object]) -> str:
    """One run's five observables, in the recorded shape."""
    body = frozen.render(result["exit"], result["stdout"], result["stderr"])
    body += CALLS_MARKER + "".join("%s\n" % line for line in result["calls"])
    packages = result["packages"]
    body += PACKAGES_MARKER
    body += NO_PACKAGES_DIR if packages is None else "".join("%s\n" % name for name in packages)
    return body


def recorded(name: str) -> dict[str, object]:
    """One golden, back into the same five-field shape `_run` returns."""
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    body, packages_text = rest.split(PACKAGES_MARKER, 1)
    streams, calls_text = body.split(CALLS_MARKER, 1)
    stdout, stderr = streams.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return {
        "exit": int(exit_line.removeprefix("exit: ")),
        "stdout": stdout,
        "stderr": stderr,
        "calls": [line for line in calls_text.splitlines() if line],
        "packages": None
        if packages_text == NO_PACKAGES_DIR
        else [line for line in packages_text.splitlines() if line],
    }


# Fixture and run keywords per recorded case. The ids are the golden names.
CASE_KW: dict[str, tuple[dict[str, object], dict[str, object]]] = {
    "no-musl-binaries-glibc-fallback": ({}, {}),
    "both-musl-binaries-preferred-for-apk": (
        {
            "binaries": (
                "rdc-linux-x64",
                "rdc-linux-arm64",
                "rdc-linux-musl-x64",
                "rdc-linux-musl-arm64",
            )
        },
        {},
    ),
    "only-x64-musl-mixed-apk": (
        {"binaries": ("rdc-linux-x64", "rdc-linux-arm64", "rdc-linux-musl-x64")},
        {},
    ),
    "no-binaries-at-all-still-delegates": ({"binaries": ()}, {}),
    "output-dir-already-there": ({"packages_dir_exists": True}, {}),
    "placeholder-version-is-just-a-string": ({}, {"next_version": "0.0.0-dev"}),
    "semver-with-metadata": ({}, {"next_version": "1.2.3-rc.1+build.7"}),
    "delegate-fails-on-the-first-call": ({}, {"fail_on": 1, "rc": 3}),
    "delegate-fails-at-the-first-apk": ({}, {"fail_on": 5, "rc": 9}),
    "delegate-fails-on-the-last-call": ({}, {"fail_on": 8, "rc": 1}),
    "delegate-fails-mid-matrix": ({}, {"fail_on": 3, "rc": 5}),
    "an-unset-next-version": ({}, {"next_version": None}),
    "an-empty-next-version": ({}, {"next_version": ""}),
    "a-missing-delegate": ({}, {"delegate": False}),
}

CASES = tuple(CASE_KW)


def drive(
    tmp_path: pathlib.Path, name: str, *, port_source: str | None = None
) -> dict[str, object]:
    """Run the PORT over one recorded case's fixture."""
    fixture_kw, run_kw = CASE_KW[name]
    root = _fixture(tmp_path / name[:24], port_source=port_source, **fixture_kw)  # type: ignore[arg-type]
    return _run(PORT_REL, root, **run_kw)  # type: ignore[arg-type]


def compare(tmp_path: pathlib.Path, name: str, *, port_source: str | None = None) -> dict:
    want = recorded(name)
    got = drive(tmp_path, name, port_source=port_source)
    for field in FIELDS:
        assert got[field] == want[field], "%s: %s diverged:\n twin: %r\n port: %r" % (
            name,
            field,
            want[field],
            got[field],
        )
    return got


# --------------------------------------------------------------------------- Every recorded case ---------------------------------------------------------------------------

# The three whose recorded stderr is an interpreter diagnostic naming the program that refused, which the port cannot and must not reproduce verbatim.
MASKED = ("an-unset-next-version", "an-empty-next-version", "a-missing-delegate")


@pytest.mark.parametrize("name", [c for c in CASES if c not in MASKED])
def test_port_matches_the_twins_recorded_results(tmp_path, name):
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_the_delegate_is_actually_reached_eight_times(tmp_path):
    """ANTI-VACUITY. Every comparison above is worthless if the delegate never ran, and this also pins the MATRIX and the CWD: eight invocations, in the twin's nesting order, all from the repository root."""
    out = compare(tmp_path, "no-musl-binaries-glibc-fallback")
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
    """CONTROL in the other direction: after a failing delegate, NOTHING else ran. A port that ran all eight and reported at the end would satisfy every positive assertion in this file and would keep packaging against a binary an earlier step had already refused."""
    out = compare(tmp_path, "delegate-fails-mid-matrix")
    assert out["exit"] == 5, out["exit"]
    calls = [c for c in out["calls"] if c.startswith("call: ")]
    assert len(calls) == 3, "the matrix kept going: %r" % calls
    assert recorded("delegate-fails-mid-matrix")["exit"] == 5, "the recorded verdict moved"


def test_the_musl_substitution_only_touches_apk(tmp_path):
    """The Alpine fallback, named rather than left inside a call log.

    With all four binaries present, exactly the two `apk` invocations must carry `rdc-linux-musl-*` and the other six must not. A port that substituted for every format would produce six packages containing a musl binary for glibc distributions.
    """
    out = compare(tmp_path, "both-musl-binaries-preferred-for-apk")
    musl = [c for c in out["calls"] if "rdc-linux-musl-" in c]
    assert len(musl) == 2, musl
    for call in musl:
        assert "--format apk" in call, call
    assert (
        len(
            [
                c
                for c in recorded("both-musl-binaries-preferred-for-apk")["calls"]
                if "rdc-linux-musl-" in c
            ]
        )
        == 2
    )


def test_the_glibc_fallback_is_real_and_silent(tmp_path):
    """The other half of the same decision, and the one the twin's own header called out: with no musl binary, `apk` packages the GLIBC binary and says nothing about it. Pinned in both the recording and the port, because a `.apk` holding a glibc binary installs cleanly on Alpine and fails at exec time."""
    for out in (
        recorded("no-musl-binaries-glibc-fallback"),
        drive(tmp_path, "no-musl-binaries-glibc-fallback"),
    ):
        apk = [c for c in out["calls"] if "--format apk" in c]
        assert len(apk) == 2, apk
        for call in apk:
            assert "rdc-linux-musl-" not in call, call
            assert "--binary dist/cli/rdc-linux-" in call, call
        assert "musl" not in out["stderr"], (
            "something now warns about the fallback, so this test is stale: %r" % out["stderr"]
        )


def test_an_unset_next_version_names_the_program_that_refused(tmp_path):
    """THE ONE DELIBERATE DIVERGENCE, asserted in both directions with the `<path>: line <n>: ` prefix masked.

    `:?` fired on unset AND on empty, so both are recorded. The twin's own message text -- which embeds `build-linux-packages.sh:` a second time, producing a line that reads as though the filename appears twice -- is reproduced verbatim, and that is what the masked comparison checks.
    """
    for name in ("an-unset-next-version", "an-empty-next-version"):
        old = recorded(name)
        new = drive(tmp_path, name)

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

    `build-linux-pkg.sh` absent: bash reported "No such file or directory" against its own path and line and exited 127. The port takes the same status and prints the same shape against its own. The status is what the workflow step branches on, so it is asserted equal; the text is asserted DIFFERENT so the divergence stays visible.
    """
    old = recorded("a-missing-delegate")
    new = drive(tmp_path, "a-missing-delegate")

    assert old["exit"] == 127, old
    assert new["exit"] == 127, new
    assert LINE_PREFIX.sub("<prog>: line N: ", new["stderr"]) == LINE_PREFIX.sub(
        "<prog>: line N: ", old["stderr"]
    ), "masked stderr diverged:\n twin: %r\n port: %r" % (old["stderr"], new["stderr"])
    assert old["stderr"] != new["stderr"], "the mask is hiding nothing"


def test_binary_for_is_the_twins_parameter_expansion():
    """The pure half, driven against BASH's own `${binary/rdc-linux-/...}` rather
    than against a constant: a constant copied out of the port cannot contradict the port. Only the SUBSTITUTION is compared here -- the `-f` test needs a filesystem and is covered above.
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

    The twin evaluated `[[ -f "$musl_binary" ]]` immediately before the invocation it decided. A musl binary that appears midway through the run -- which a delegate could plausibly produce -- therefore changes the LATER apk decision and not the earlier one. A list comprehension would resolve all eight against the filesystem as it stood at the start, which is a different
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
            # After the fourth invocation (both debs, both rpms) the musl binary appears. A lazy generator must pick it up for the apk pair that follows; an eager list cannot.
            if index == 3:
                (cli / "rdc-linux-musl-x64").write_text("x", encoding="utf-8")
    finally:
        os.chdir(previous)

    assert produced[4] == "dist/cli/rdc-linux-musl-x64", (
        "the apk decision did not see a binary created mid-run, so `invocations` "
        "is no longer lazy: %r" % produced
    )
    assert produced[5] == "dist/cli/rdc-linux-arm64", produced


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_musl_substitution_for_every_format_is_caught(tmp_path):
    """THE CONTROL ON THE GOLDENS. Let the musl preference escape `apk`.

    Dropping the format guard in `binary_for` is exactly the simplification a reader would make on sight: the substitution is conditional on a file test either way, so it looks harmless. It is invisible on every fixture with no musl binary and visible on the one with both, where the recorded call log carries a glibc binary for the six non-apk formats. The mutation is written to
    a throwaway copy; the tracked port is never touched.
    """
    source = PORT.read_text(encoding="utf-8")
    anchor = "    if arch_format != MUSL_FORMAT:\n        return binary\n"
    assert source.count(anchor) == 1, "the plant's anchor moved"
    planted = source.replace(anchor, "    del arch_format\n")
    assert planted != source

    with pytest.raises(AssertionError):
        compare(tmp_path / "planted", "both-musl-binaries-preferred-for-apk", port_source=planted)
    # And the tracked port still agrees against the same fixture.
    compare(tmp_path / "clean", "both-musl-binaries-preferred-for-apk")
    assert PORT.read_text(encoding="utf-8") == source
