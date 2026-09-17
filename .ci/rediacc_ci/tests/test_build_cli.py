"""Differential: `.ci/rediacc_ci/build/build_cli.py` against its twin
`.ci/scripts/build/build-cli.sh`.

WHY A DIFFERENTIAL AND NOT A UNIT TEST. The claim a port makes is not "the new code is correct", it is "the new code says what the old code said". Only running BOTH, on the same fixture, in the same run, can support that.

WHAT IS COMPARED, AND WHY THE CALL LOG IS THE IMPORTANT ONE. This script's whole job is to decide WHICH of three commands to run, so a comparison of its own transcript would agree happily with a port that ran none of them. Every case compares:

  1. the exit code -- always 1 on any failure, never the delegate's own, which is
     DEFECT 2;
  2. stdout, which is where `ls -lah` lands;
  3. stderr, the `→ Building CLI...` / `✓ CLI build completed` transcript;
  4. the CALL LOG: every `npm` and `ls` invocation, its argv AND its cwd. A port
     that got the flags right and ran `npm run build` instead of
     `npm run build:cli`, or ran it from `packages/cli` instead of the root,
     passes a transcript comparison and builds the wrong thing.

`ls` IS FAKED, AND IT HAS TO BE. The twin ends `--verify` with a literal `ls -lah packages/cli/dist/`, whose output carries sizes, mtimes and a locale date. Two fixture trees are created milliseconds apart in different directories, so a REAL `ls` would differ between the two runs on the timestamp alone and every
case would report a false MISMATCH. The fake records its argv and prints a fixed
listing, which makes the comparison about the argv -- the thing the port could actually get wrong -- rather than about the clock.

PATH IS REPLACED, NEVER PREPENDED. This host has a real `npm`, and the subject
`cd`s to a root it derives itself; a subject that mis-derived it would run a REAL
`npm run build:cli` inside the live checkout. `_binder` builds the ENTIRE PATH
from named tools plus the two fakes, and asserts every exclusion really took --
a control on the control, because a probe that cannot fire looks exactly like a subject that cannot fail.

THE ONE DELIBERATE DIVERGENCE IS TESTED, NOT HIDDEN.
`test_a_missing_npm_agrees_on_the_branch_and_not_on_the_diagnostic` masks the `<path>: line <n>: ` prefix each side puts on the interpreter's own "command not found", compares the rest, and then asserts the two unmasked strings DIFFER so the mask cannot quietly start hiding nothing.
"""

import pathlib
import re
import shutil
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.build import build_cli

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "build" / "build-cli.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "build" / "build_cli.py"

TWIN_REL = pathlib.PurePosixPath(".ci/scripts/build/build-cli.sh")
PORT_REL = pathlib.PurePosixPath(".ci/rediacc_ci/build/build_cli.py")

# The recording `npm`. `FAIL` names the script that must fail (`build:cli` or `build:bundle`), so a case can fail the bundle while the workspace build succeeds -- the two are separate `if`s in the twin and a port could easily collapse them.
#
# It reports on STDOUT with a `call: ` prefix rather than through a log-step helper, and that is not cosmetic: `scripts/lib/shadow-gate.ts` classifies any line starting with `→ ` or `✓ ` as CHATTER before `--finding-re` is consulted, so a fake that reported like `common.sh` would make every ledger row read VACUOUS_BOTH_EMPTY. `call: ` is what the ledger's `--finding-re` scopes to.
FAKE_NPM = """#!/usr/bin/env python3
import os, pathlib, sys
LOG = %(log)r
ROOT = %(root)r
FAIL = %(fail)r
RC = %(rc)d
with pathlib.Path(LOG).open("a", encoding="utf-8") as fh:
    fh.write("call: npm " + " ".join(sys.argv[1:]) + "\\n")
    fh.write("cwd: " + os.path.relpath(os.getcwd(), ROOT) + "\\n")
args = sys.argv[1:]
if FAIL and FAIL in args:
    sys.stderr.write("fake npm: " + FAIL + " failed\\n")
    sys.exit(RC)
sys.stdout.write("fake npm ran " + " ".join(args) + "\\n")
"""

# The recording `ls`. A fixed listing, for the reason in the module docstring.
FAKE_LS = """#!/usr/bin/env python3
import os, pathlib, sys
LOG = %(log)r
ROOT = %(root)r
with pathlib.Path(LOG).open("a", encoding="utf-8") as fh:
    fh.write("call: ls " + " ".join(sys.argv[1:]) + "\\n")
    fh.write("cwd: " + os.path.relpath(os.getcwd(), ROOT) + "\\n")
sys.stdout.write("total 4.0K\\n-rw-r--r-- 1 u u 12 Jan  1 00:00 index.js\\n")
"""

# Everything both subjects need once PATH is rebuilt from scratch. `ls` is NOT here: it is a fake, and listing it would let the real one win the symlink race in `_binder`.
NEEDED = ("bash", "sh", "python3", "env", "uname", "dirname", "cat", "mkdir", "rm")

# `<path>: line <n>: ` -- the prefix bash puts on its own diagnostics, and the shape the port reproduces with its own path. Masked ONLY in the test that is about that divergence.
LINE_PREFIX = re.compile(r"^[^\n]*: line \d+: ", re.MULTILINE)


def _fixture(
    where: pathlib.Path,
    *,
    dist: bool = True,
    index_js: bool = True,
) -> pathlib.Path:
    """A tree shaped like the repository, holding COPIES of both subjects.

    Copies, because each subject derives the console root from its own location (`BASH_SOURCE`/`__file__`, then three directories up). Driving the TRACKED files with a `cwd` would point them at the real repository, where `npm run build:cli` is a real build and `packages/cli/dist` is real output.

    `dist` and `index_js` are the two `--verify` probes, separately settable because the twin checks them in order and reports them differently.
    """
    root = where.resolve() / "tree"
    (root / ".ci" / "scripts" / "build").mkdir(parents=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "build").mkdir(parents=True)
    shutil.copy2(TWIN, root / TWIN_REL)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / "common.sh")
    shutil.copy2(PORT, root / PORT_REL)

    if dist:
        out = root / "packages" / "cli" / "dist"
        out.mkdir(parents=True)
        if index_js:
            (out / "index.js").write_text("console.log(1)\n", encoding="utf-8")
    return root


def _binder(
    where: pathlib.Path,
    root: pathlib.Path,
    *,
    log: pathlib.Path,
    fail: str,
    rc: int,
    exclude: tuple[str, ...],
) -> str:
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

    if "npm" not in exclude:
        npm = binder / "npm"
        npm.write_text(
            FAKE_NPM % {"log": str(log), "root": str(root), "fail": fail, "rc": rc},
            encoding="utf-8",
        )
        npm.chmod(0o755)
    if "ls" not in exclude:
        fake_ls = binder / "ls"
        fake_ls.write_text(FAKE_LS % {"log": str(log), "root": str(root)}, encoding="utf-8")
        fake_ls.chmod(0o755)

    assert shutil.which("bash", path=str(binder)), "the restricted PATH cannot run the twin"
    assert shutil.which("python3", path=str(binder)), "the restricted PATH cannot run the port"
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
    fail: str = "",
    rc: int = 2,
    env_extra: dict[str, str] | None = None,
    exclude: tuple[str, ...] = (),
) -> dict[str, object]:
    """Drive one subject and collect all four observables."""
    tag = pathlib.Path(subject).name
    log = root.parent / ("calls-%s.txt" % tag)
    env = {
        "PATH": _binder(
            root.parent / ("fxbin-%s" % tag), root, log=log, fail=fail, rc=rc, exclude=exclude
        ),
        "HOME": str(root.parent),
        "PYTHONDONTWRITEBYTECODE": "1",
        "LC_ALL": "C",
        "LANG": "C",
        # The port imports `rediacc_ci.log`; the COPY under the fixture is what
        # runs, so the package has to come from the real checkout. This is the only thing the fixture borrows from outside itself.
        "PYTHONPATH": str(ROOT / ".ci"),
    }
    env.update(env_extra or {})

    runner = "bash" if subject.suffix == ".sh" else "python3"
    proc = subprocess.run(
        [runner, str(root / subject), *argv],
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

    return {
        "exit": proc.returncode,
        "stdout": proc.stdout.replace(str(root), "<root>"),
        "stderr": proc.stderr.replace(str(root), "<root>"),
        "calls": calls,
    }


FIELDS = ("exit", "stdout", "stderr", "calls")

CASES = [
    pytest.param({}, {}, id="default-bundle-and-verify"),
    pytest.param({}, {"argv": ("--no-bundle",)}, id="no-bundle"),
    pytest.param({}, {"argv": ("--no-verify",)}, id="no-verify"),
    pytest.param({}, {"argv": ("--no-bundle", "--no-verify")}, id="neither"),
    pytest.param({}, {"argv": ("--bundle", "--verify")}, id="documented-flags-are-no-ops"),
    pytest.param({}, {"argv": ("--no-bundle", "--bundle")}, id="last-wins"),
    pytest.param({}, {"argv": ("--no-bundl",)}, id="typo-silently-accepted"),
    pytest.param({}, {"argv": ("--help",)}, id="help-runs-the-whole-build"),
    pytest.param({}, {"argv": ("--no-bundle=true",)}, id="equals-form-silently-accepted"),
    pytest.param({}, {"env_extra": {"ARG_BUNDLE": "false"}}, id="env-turns-the-bundle-off"),
    pytest.param({}, {"env_extra": {"ARG_VERIFY": "false"}}, id="env-turns-verify-off"),
    pytest.param({}, {"env_extra": {"ARG_BUNDLE": "1"}}, id="env-1-is-not-true"),
    pytest.param({}, {"env_extra": {"ARG_BUNDLE": ""}}, id="env-empty-takes-the-default"),
    pytest.param(
        {},
        {"env_extra": {"ARG_BUNDLE": "false"}, "argv": ("--bundle",)},
        id="flag-overrides-the-env",
    ),
    pytest.param({}, {"fail": "build:cli", "rc": 2}, id="workspace-build-fails"),
    pytest.param({}, {"fail": "build:bundle", "rc": 9}, id="bundle-fails"),
    pytest.param({"dist": False}, {}, id="dist-directory-missing"),
    pytest.param({"index_js": False}, {}, id="index-js-missing"),
    pytest.param(
        {"dist": False},
        {"argv": ("--no-verify",)},
        id="missing-dist-is-invisible-without-verify",
    ),
    pytest.param({}, {"exclude": ("npm",)}, id="no-npm"),
]


@pytest.mark.parametrize(("fixture_kw", "run_kw"), CASES)
def test_port_and_twin_agree(tmp_path, fixture_kw, run_kw):
    root_a = _fixture(tmp_path / "a", **fixture_kw)
    old = _run(TWIN_REL, root_a, **run_kw)

    root_b = _fixture(tmp_path / "b", **fixture_kw)
    new = _run(PORT_REL, root_b, **run_kw)

    if run_kw.get("exclude"):
        # The one case whose stderr carries the INTERPRETER's diagnostic rather than the script's. Compared with the `<path>: line <n>: ` prefix
        # masked; `test_a_missing_npm_agrees_on_the_branch_and_not_on_the_
        # diagnostic` is where that divergence is asserted in both directions.
        old = {**old, "stderr": LINE_PREFIX.sub("<prog>: line N: ", old["stderr"])}
        new = {**new, "stderr": LINE_PREFIX.sub("<prog>: line N: ", new["stderr"])}

    for field in FIELDS:
        assert new[field] == old[field], "%s diverged:\n twin: %r\n port: %r" % (
            field,
            old[field],
            new[field],
        )


def test_the_fakes_are_actually_reached(tmp_path):
    """ANTI-VACUITY. Every comparison above is worthless if npm never ran, and
    this also pins the exact argv and the CWD: the twin builds from the
    REPOSITORY ROOT, not from `packages/cli`."""
    root = _fixture(tmp_path / "v")
    out = _run(PORT_REL, root)
    assert out["calls"] == [
        "call: npm run build:cli",
        "cwd: .",
        "call: npm run build:bundle -w @rediacc/cli",
        "cwd: .",
        "call: ls -lah packages/cli/dist/",
        "cwd: .",
    ], out["calls"]
    assert out["exit"] == 0, "the happy path must succeed: %r" % out


def test_no_bundle_really_skips_the_bundle(tmp_path):
    """CONTROL in the other direction: `--no-bundle` must run NO bundle command.
    A port that bundled unconditionally would satisfy every positive assertion in
    this file and would double the cost of five CI jobs."""
    root = _fixture(tmp_path / "s")
    out = _run(PORT_REL, root, argv=("--no-bundle",))
    assert not [c for c in out["calls"] if "build:bundle" in c], out["calls"]
    assert "CLI bundle" not in out["stderr"], out["stderr"]


def test_an_unknown_argument_is_a_full_build_in_both(tmp_path):
    """DEFECT 1, pinned in BOTH implementations.

    There is no `*)` arm, so `--no-bundl` (one letter short) and `--help` are accepted in silence and the script runs everything. `--help` in particular runs a full CLI build and a bundle for anyone who typed it hoping for usage text. Reported, not fixed -- the repair is a cutover-box decision.
    """
    for subject in (TWIN_REL, PORT_REL):
        for arg in ("--no-bundl", "--help", "-h", "--no_verify", "gibberish"):
            root = _fixture(tmp_path / ("u-%s-%s" % (subject.name, arg.strip("-") or "dash")))
            out = _run(subject, root, argv=(arg,))
            assert out["exit"] == 0, "%s %s: %r" % (subject.name, arg, out["exit"])
            names = [c for c in out["calls"] if c.startswith("call: ")]
            assert names == [
                "call: npm run build:cli",
                "call: npm run build:bundle -w @rediacc/cli",
                "call: ls -lah packages/cli/dist/",
            ], (
                "%s %s: the argument was REJECTED, so the defect is fixed and this "
                "test is stale: %r" % (subject.name, arg, names)
            )


def test_the_delegates_exit_code_is_thrown_away_in_both(tmp_path):
    """DEFECT 2, pinned in BOTH implementations.

    npm exits 9; both subjects report 1. Every npm failure mode -- a failed
    script, a missing one, a signal -- arrives at the workflow as the same number and the same sentence. Reported, not fixed.
    """
    for subject in (TWIN_REL, PORT_REL):
        root = _fixture(tmp_path / ("e-%s" % subject.name))
        out = _run(subject, root, fail="build:cli", rc=9)
        assert out["exit"] == 1, (
            "%s: npm's own 9 now survives, so the defect is fixed and this test is "
            "stale: %r" % (subject.name, out["exit"])
        )
        assert "CLI build failed" in out["stderr"], out["stderr"]


def test_verify_only_checks_that_two_paths_exist(tmp_path):
    """What `--verify` does NOT do, pinned in both, because the step is named
    "Verifying CLI build output" and a reader assumes more of it.

    An EMPTY `index.js` -- the shape a half-finished build leaves -- passes.
    """
    for subject in (TWIN_REL, PORT_REL):
        root = _fixture(tmp_path / ("q-%s" % subject.name))
        (root / "packages" / "cli" / "dist" / "index.js").write_text("", encoding="utf-8")
        out = _run(subject, root)
        assert out["exit"] == 0, "%s: %r" % (subject.name, out["exit"])
        assert "CLI build output verified" in out["stderr"], out["stderr"]


def test_a_missing_npm_agrees_on_the_branch_and_not_on_the_diagnostic(tmp_path):
    """THE ONE DELIBERATE DIVERGENCE, asserted in both directions.

    With no `npm` on PATH, bash prints `<script>: line <n>: npm: command not found`, the `if` sees 127, and the `else` arm exits 1 with the script's own message. The port prints the same shape naming ITS path and line and takes the same branch. The BRANCH is what matters and is compared with the prefix
    masked; the unmasked strings are asserted DIFFERENT so the mask cannot
    quietly start hiding nothing.
    """
    root_a = _fixture(tmp_path / "na")
    old = _run(TWIN_REL, root_a, exclude=("npm",))
    root_b = _fixture(tmp_path / "nb")
    new = _run(PORT_REL, root_b, exclude=("npm",))

    assert old["exit"] == 1, old
    assert new["exit"] == 1, new
    assert "CLI build failed" in old["stderr"], old["stderr"]
    assert "CLI build failed" in new["stderr"], new["stderr"]
    assert LINE_PREFIX.sub("<prog>: line N: ", new["stderr"]) == LINE_PREFIX.sub(
        "<prog>: line N: ", old["stderr"]
    ), "masked stderr diverged:\n twin: %r\n port: %r" % (old["stderr"], new["stderr"])
    assert old["stderr"] != new["stderr"], "the mask is hiding nothing"


def test_parse_flags_is_the_twins_case_statement():
    """The pure half, driven against BASH's own `case` rather than a constant.

    A constant copied out of the port cannot contradict the port, so each argument list is fed to a bash snippet holding the twin's four arms verbatim and the two answers are compared. This is also where the ABSENCE of a `*)` arm is proven rather than asserted: an unrecognised argument changes nothing on either side.
    """
    snippet = """
    BUNDLE="$1"; VERIFY="$2"; shift 2
    for arg in "$@"; do
        case "$arg" in
            --no-bundle) BUNDLE=false ;;
            --no-verify) VERIFY=false ;;
            --bundle) BUNDLE=true ;;
            --verify) VERIFY=true ;;
        esac
    done
    printf '%s %s' "$BUNDLE" "$VERIFY"
    """
    argvs = [
        [],
        ["--no-bundle"],
        ["--no-verify"],
        ["--no-bundle", "--bundle"],
        ["--bundle", "--no-bundle"],
        ["--no-bundl"],
        ["--help"],
        ["--no-verify", "--verify", "--no-verify"],
        ["gibberish", "--no-bundle", "more"],
    ]
    for start in ((True, True), (False, True), (True, False), (False, False)):
        for argv in argvs:
            expected = subprocess.run(
                [
                    "bash",
                    "-c",
                    snippet,
                    "_",
                    "true" if start[0] else "false",
                    "true" if start[1] else "false",
                    *argv,
                ],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            bundle, verify = build_cli.parse_flags(argv, bundle=start[0], verify=start[1])
            got = "%s %s" % ("true" if bundle else "false", "true" if verify else "false")
            assert got == expected, "diverged for %r from %r: %r vs %r" % (
                argv,
                start,
                got,
                expected,
            )
