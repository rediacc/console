"""Differential: `.ci/rediacc_ci/build/pack_cli_npm.py` against its twin `.ci/scripts/build/pack-cli-npm.sh`.

WHY A DIFFERENTIAL AND NOT A UNIT TEST. The claim a port makes is not "the new code is correct", it is "the new code says what the old code said". Only running BOTH, on the same fixture, in the same run, can support that.

WHAT IS COMPARED, AND WHY IT IS SEVEN THINGS. This script's product is a file on disk, so exit code and stdout describe barely half of it. Every case compares:

  1. the exit code, which is where DEFECT 1 lives (a silent 2 where the
     unreachable `else` intended a 1 with a message);
  2. stdout -- npm's own tarball line, passed through untouched;
  3. stderr -- the `✓ Injected ...` / `✓ Packed ...` transcript;
  4. the CALL LOG: every `jq` and `npm` invocation, its argv AND its cwd. A port
     that printed the same transcript while never running `npm pack`, or running
     it from the wrong directory, passes a stdout-only comparison and ships
     nothing. The cwd half is load-bearing: the twin's whole header is about a
     step that resolved the script's path against the wrong directory;
  5. what is in `OUT_DIR` afterwards, by name;
  6. the BYTES of `rediacc-cli-latest.tgz`, which is the artifact every install
     path fetches -- comparing only its NAME would pass a port that aliased the
     wrong tarball, which is exactly DEFECT 2's shape;
  7. `packages/cli/package.json` after the run, plus whether `package.json.tmp`
     was left behind. The manifest is what `npm pack` names the tarball from, so
     a port that wrote it differently would be caught here rather than in a
     release.

PATH IS REPLACED, NEVER PREPENDED. This host has a real `npm` and a real `jq`, and `packages/cli` in the real checkout is one `get_repo_root` away from any fixture that gets its root wrong. A prepended PATH would leave a subject that mis-derived its root running a REAL `npm pack` against the live tree. `_binder` therefore builds the ENTIRE PATH out of named tools plus the two
fakes, and asserts that anything it was asked to exclude really is absent -- a control on the control, because a probe that cannot fire looks exactly like a subject that cannot fail.

`LC_ALL=C` ON BOTH SIDES, deliberately, and it is not boilerplate: the twin's
tarball choice is `ls | head -1`, whose order is `LC_COLLATE`'s, and the port sorts by code point. The two agree under C. Pinning it makes the comparison measure the port instead of the developer's locale, and `select_tarball`'s docstring says the same thing from the other side.

THE TWO DELIBERATE DIVERGENCES ARE TESTED, NOT HIDDEN:
`test_a_missing_packages_cli_names_the_program_that_could_not_proceed` masks the `<path>: line <n>: ` prefix and compares the rest, and `test_a_failing_mkdir_agrees_on_the_status_and_not_on_the_text` asserts the exit codes match AND that the coreutils diagnostic does not, so the difference is a recorded decision rather than an absence.
"""

import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile

import pytest

from rediacc_ci import paths
from rediacc_ci.build import pack_cli_npm

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "build" / "pack-cli-npm.sh"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "build" / "pack_cli_npm.py"

TWIN_REL = pathlib.PurePosixPath(".ci/scripts/build/pack-cli-npm.sh")
PORT_REL = pathlib.PurePosixPath(".ci/rediacc_ci/build/pack_cli_npm.py")

# The recording `jq`. It performs the twin's ACTUAL transformation rather than echoing a canned manifest, because observable 7 compares the resulting
# package.json and a canned answer would make that comparison vacuous. Both
# subjects run this same fake, so whatever it does, it does identically to both;
# what is under test is whether each one CALLS it with the same argv and then moves the output into place.
FAKE_JQ = """#!/usr/bin/env python3
import json, os, pathlib, sys
LOG = %(log)r
ROOT = %(root)r
RC = %(rc)d
with pathlib.Path(LOG).open("a", encoding="utf-8") as fh:
    fh.write("call: jq " + " ".join(sys.argv[1:]) + "\\n")
    fh.write("cwd: " + os.path.relpath(os.getcwd(), ROOT) + "\\n")
if RC != 0:
    sys.stderr.write("fake jq: refusing, rc=%%d\\n" %% RC)
    sys.exit(RC)
args = sys.argv[1:]
version = args[args.index("--arg") + 2]
data = json.loads(pathlib.Path(args[-1]).read_text(encoding="utf-8"))
data["version"] = version
sys.stdout.write(json.dumps(data, indent=2) + "\\n")
"""

# The recording `npm`. Creates whatever tarballs the case asks for, in --pack-destination, and prints the last one the way `npm pack` prints a name.
FAKE_NPM = """#!/usr/bin/env python3
import os, pathlib, sys
LOG = %(log)r
ROOT = %(root)r
RC = %(rc)d
PRODUCES = %(produces)r
with pathlib.Path(LOG).open("a", encoding="utf-8") as fh:
    fh.write("call: npm " + " ".join(sys.argv[1:]) + "\\n")
    fh.write("cwd: " + os.path.relpath(os.getcwd(), ROOT) + "\\n")
args = sys.argv[1:]
dest = args[args.index("--pack-destination") + 1] if "--pack-destination" in args else "."
for name in PRODUCES:
    out = pathlib.Path(dest) / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("tarball-of:" + name + "\\n", encoding="utf-8")
    sys.stdout.write(name + "\\n")
sys.exit(RC)
"""

# Everything both subjects need once PATH is rebuilt from scratch. Named rather than derived: a PATH built by copying "everything except npm" is a PATH nobody can state, and the first tool it forgot would look like a divergence in the subject rather than a hole in the harness.
NEEDED = (
    "bash",
    "sh",
    "python3",
    "env",
    "uname",
    "dirname",
    "cat",
    "cp",
    "mv",
    "mkdir",
    "ls",
    "head",
    "rm",
)

# The manifest the fixture starts from. Two keys beyond `version`, so a port that rewrote the file wholesale instead of editing one field would show up in observable 7.
BASE_MANIFEST = {"name": "@rediacc/cli", "version": "0.0.0-dev", "private": False}

# `<path>: line <n>: ` -- bash's prefix on a `cd` diagnostic, and the port's own equivalent. Masked only in the two tests that are ABOUT that divergence.
LINE_PREFIX = re.compile(r"^[^\n]*: line \d+: ", re.MULTILINE)


def _fixture(
    where: pathlib.Path,
    *,
    manifest: dict | None = None,
    seeded: tuple[str, ...] = (),
    out_dir: str = "out",
) -> pathlib.Path:
    """A tree shaped like the repository, holding COPIES of both subjects.

    Copies, because each subject derives the console root from its own location (`BASH_SOURCE`/`__file__`, then three directories up). Driving the TRACKED files with a `cwd` would point them at the real repository, and the version injection would then rewrite `packages/cli/package.json` in the live tree.

    `.resolve()` on the root is load-bearing: bash's `cd X && pwd` reports the LOGICAL path it was handed while `pathlib.resolve()` follows symlinks, and the root appears in `cd` diagnostics. Handing both subjects an already-resolved root makes them agree for the right reason.

    `seeded` pre-creates names in OUT_DIR, which is how the stale-tarball half of DEFECT 2 is reached without waiting for a second run.
    """
    root = where.resolve() / "tree"
    (root / ".ci" / "scripts" / "build").mkdir(parents=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "build").mkdir(parents=True)
    shutil.copy2(TWIN, root / TWIN_REL)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / "common.sh")
    shutil.copy2(PORT, root / PORT_REL)

    cli = root / "packages" / "cli"
    cli.mkdir(parents=True)
    (cli / "package.json").write_text(
        json.dumps(BASE_MANIFEST if manifest is None else manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    if seeded:
        dest = cli / out_dir
        dest.mkdir(parents=True, exist_ok=True)
        for name in seeded:
            (dest / name).write_text("seeded:" + name + "\n", encoding="utf-8")
    return root


def _binder(
    where: pathlib.Path,
    root: pathlib.Path,
    *,
    log: pathlib.Path,
    jq_rc: int,
    npm_rc: int,
    produces: tuple[str, ...],
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

    if "jq" not in exclude:
        jq = binder / "jq"
        jq.write_text(FAKE_JQ % {"log": str(log), "root": str(root), "rc": jq_rc}, encoding="utf-8")
        jq.chmod(0o755)
    if "npm" not in exclude:
        npm = binder / "npm"
        npm.write_text(
            FAKE_NPM
            % {"log": str(log), "root": str(root), "rc": npm_rc, "produces": list(produces)},
            encoding="utf-8",
        )
        npm.chmod(0o755)

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
    *,
    version: str | None = None,
    out_dir: str | None = "out",
    jq_rc: int = 0,
    npm_rc: int = 0,
    produces: tuple[str, ...] = ("rediacc-cli-1.2.3.tgz",),
    exclude: tuple[str, ...] = (),
) -> dict[str, object]:
    """Drive one subject and collect all seven observables."""
    tag = pathlib.Path(subject).name
    log = root.parent / ("calls-%s.txt" % tag)
    env = {
        "PATH": _binder(
            root.parent / ("fxbin-%s" % tag),
            root,
            log=log,
            jq_rc=jq_rc,
            npm_rc=npm_rc,
            produces=produces,
            exclude=exclude,
        ),
        "HOME": str(root.parent),
        "PYTHONDONTWRITEBYTECODE": "1",
        # LC_ALL/LANG: see the module docstring. `ls | head -1` versus a code point sort agree under C and are not guaranteed to elsewhere.
        "LC_ALL": "C",
        "LANG": "C",
        # The port imports `rediacc_ci.log` and `rediacc_ci.core.common`; the COPY under the fixture is what runs, so the package has to come from the real checkout. This is the only thing the fixture borrows from outside itself.
        "PYTHONPATH": str(ROOT / ".ci"),
    }
    if version is not None:
        env["VERSION"] = version
    if out_dir is not None:
        env["OUT_DIR"] = out_dir

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

    cli = root / "packages" / "cli"
    dest = cli / (out_dir or "")
    alias = dest / "rediacc-cli-latest.tgz"
    manifest = cli / "package.json"
    return {
        "exit": proc.returncode,
        "stdout": proc.stdout.replace(str(root), "<root>"),
        "stderr": proc.stderr.replace(str(root), "<root>"),
        "calls": calls,
        "out_dir": sorted(p.name for p in dest.iterdir()) if dest.is_dir() else None,
        "alias": alias.read_text(encoding="utf-8") if alias.is_file() else None,
        "manifest": manifest.read_text(encoding="utf-8") if manifest.is_file() else None,
        "tmp_left": (cli / "package.json.tmp").is_file(),
    }


FIELDS = ("exit", "stdout", "stderr", "calls", "out_dir", "alias", "manifest", "tmp_left")

CASES = [
    pytest.param({}, {}, id="placeholder-version-no-injection"),
    pytest.param({}, {"version": "1.2.3"}, id="version-injected"),
    pytest.param({}, {"version": ""}, id="empty-version-takes-the-placeholder"),
    pytest.param(
        {},
        {"version": "1.2.3", "produces": ("rediacc-cli-1.2.3.tgz",)},
        id="injected-then-packed",
    ),
    pytest.param({}, {"jq_rc": 4, "version": "9.9.9"}, id="jq-fails-manifest-untouched"),
    pytest.param({}, {"npm_rc": 7}, id="npm-pack-fails"),
    pytest.param({}, {"produces": ()}, id="npm-pack-produces-nothing"),
    pytest.param(
        {},
        {"produces": ("rediacc-cli-0.9.0.tgz", "rediacc-cli-0.10.0.tgz")},
        id="two-tarballs-lexically-first-wins",
    ),
    pytest.param(
        {"seeded": ("rediacc-cli-0.10.0.tgz",)},
        {"produces": ("rediacc-cli-0.9.0.tgz",)},
        id="stale-tarball-beats-this-run",
    ),
    pytest.param(
        {"seeded": ("rediacc-cli-latest.tgz",)},
        {"produces": ("other-name.tgz",)},
        id="alias-is-the-only-match-cp-refuses",
    ),
    pytest.param({}, {"exclude": ("jq",)}, id="no-jq"),
    pytest.param({}, {"exclude": ("npm",)}, id="no-npm"),
    pytest.param({}, {"out_dir": "deep/nested/out"}, id="out-dir-is-created"),
    pytest.param(
        {"manifest": {"name": "@rediacc/cli", "version": "0.0.0-dev", "keywords": ["ä", "b"]}},
        {"version": "2.0.0"},
        id="non-ascii-manifest-survives-injection",
    ),
]


@pytest.mark.parametrize(("fixture_kw", "run_kw"), CASES)
def test_port_and_twin_agree(tmp_path, fixture_kw, run_kw):
    out_dir = run_kw.get("out_dir", "out")
    root_a = _fixture(tmp_path / "a", out_dir=out_dir, **fixture_kw)
    old = _run(TWIN_REL, root_a, **run_kw)

    root_b = _fixture(tmp_path / "b", out_dir=out_dir, **fixture_kw)
    new = _run(PORT_REL, root_b, **run_kw)

    for field in FIELDS:
        assert new[field] == old[field], "%s diverged:\n twin: %r\n port: %r" % (
            field,
            old[field],
            new[field],
        )


def test_the_fakes_are_actually_reached(tmp_path):
    """ANTI-VACUITY. Every comparison above is worthless if `npm pack` never ran.

    Also pins the CWD, which is the twin's own header incident: the script has to be inside `packages/cli` when it packs, however it was invoked.
    """
    root = _fixture(tmp_path / "v")
    out = _run(PORT_REL, root, version="1.2.3")
    assert out["calls"], "no fake was invoked; this file proves nothing"
    assert out["calls"] == [
        "call: jq --arg v 1.2.3 .version = $v package.json",
        "cwd: packages/cli",
        "call: npm pack --pack-destination out",
        "cwd: packages/cli",
    ], out["calls"]
    assert out["exit"] == 0, "the happy path must succeed: %r" % out


def test_the_placeholder_really_skips_jq(tmp_path):
    """CONTROL for the case above, in the other direction: `0.0.0-dev` must call NO jq at all. A port that injected unconditionally would satisfy every positive assertion in this file and would dirty `package.json` on every dev build."""
    root = _fixture(tmp_path / "s")
    out = _run(PORT_REL, root)
    assert not [c for c in out["calls"] if c.startswith("call: jq")], out["calls"]
    assert out["manifest"] == json.dumps(BASE_MANIFEST, indent=2) + "\n", (
        "the manifest was rewritten despite the placeholder: %r" % out["manifest"]
    )


def test_the_dead_else_branch_is_dead_in_both(tmp_path):
    """DEFECT 1, pinned in BOTH implementations.

    `npm pack` produced nothing, which is the ONE failure the twin wrote a message for. Under `set -euo pipefail` the message never prints: the
    `CLI_PKG="$(ls ... | head -1)"` assignment carries `ls`'s exit 2 and errexit
    kills the script before the `if`. So the observable is exit 2 and total silence, in both. If either half ever changes, this reds here rather than on somebody's release day. Reported, not fixed -- the repair is a cutover-box decision.
    """
    for subject in (TWIN_REL, PORT_REL):
        root = _fixture(tmp_path / ("d-%s" % subject.name))
        out = _run(subject, root, produces=())
        assert out["exit"] == 2, "%s: expected the silent 2, got %r" % (subject.name, out["exit"])
        assert "npm pack produced no" not in out["stderr"], (
            "%s: the unreachable branch RAN, so the defect is gone and this test is stale: %r"
            % (subject.name, out["stderr"])
        )
        assert out["alias"] is None, "%s: an alias was written anyway" % subject.name


def test_a_failing_jq_is_announced_as_a_success_in_both(tmp_path):
    """DEFECT 3, pinned in BOTH implementations, and the reason this file exists.

    `set -e` does not fire on a failing member of an AND-OR list, so a jq that dies leaves `package.json` untouched, leaves an EMPTY `package.json.tmp` behind, prints `✓ Injected version 9.9.9 into package.json` anyway, packs the uninjected manifest and exits 0.

    Four separate assertions rather than one, because each is a different half of the lie and a port could get any one of them right by accident. Reported, not fixed -- the repair is a cutover-box decision.
    """
    for subject in (TWIN_REL, PORT_REL):
        root = _fixture(tmp_path / ("j-%s" % subject.name))
        out = _run(subject, root, version="9.9.9", jq_rc=4)
        assert out["exit"] == 0, "%s: the failure was reported after all: %r" % (
            subject.name,
            out["exit"],
        )
        assert "Injected version 9.9.9" in out["stderr"], (
            "%s: the success line is gone, so the defect is fixed and this test is "
            "stale: %r" % (subject.name, out["stderr"])
        )
        assert out["manifest"] == json.dumps(BASE_MANIFEST, indent=2) + "\n", (
            "%s: the manifest changed despite jq failing: %r" % (subject.name, out["manifest"])
        )
        assert out["tmp_left"], "%s: package.json.tmp was cleaned up" % subject.name
        assert [c for c in out["calls"] if c.startswith("call: npm")], (
            "%s: npm pack did not run, so nothing was published from the stale "
            "manifest and the consequence is not what this test claims" % subject.name
        )


def test_a_stale_tarball_is_aliased_over_this_runs_own(tmp_path):
    """DEFECT 2, demonstrated rather than asserted in prose, in BOTH.

    `OUT_DIR` defaults to `/tmp/cli-npm` and nothing cleans it, so the previous run's `rediacc-cli-0.10.0.tgz` is still there when this run packs 0.9.0. `ls | head -1` sorts `1` before `9`, so the alias every install path fetches gets the OLD tarball and the script reports success naming it.
    """
    for subject in (TWIN_REL, PORT_REL):
        root = _fixture(tmp_path / ("t-%s" % subject.name), seeded=("rediacc-cli-0.10.0.tgz",))
        out = _run(subject, root, produces=("rediacc-cli-0.9.0.tgz",))
        assert out["exit"] == 0, "%s: %r" % (subject.name, out["exit"])
        assert out["alias"] == "seeded:rediacc-cli-0.10.0.tgz\n", (
            "%s: the alias no longer carries the STALE tarball, so the defect is gone "
            "and this test is stale: %r" % (subject.name, out["alias"])
        )
        assert "Packed rediacc-cli-0.10.0.tgz" in out["stderr"], out["stderr"]


def test_a_missing_packages_cli_names_the_program_that_could_not_proceed(tmp_path):
    """DIVERGENCE 1, asserted in both directions with the prefix masked.

    Both subjects fail the `cd` and exit 1. bash's diagnostic names the script and its line; the port's names the port and its line. Everything after that prefix -- `cd: <dir>: No such file or directory` -- is compared byte for byte, and the two paths are asserted to be DIFFERENT so this test still means something if someone ever makes the port print the twin's path.
    """
    root_a = _fixture(tmp_path / "ma")
    shutil.rmtree(root_a / "packages")
    old = _run(TWIN_REL, root_a)
    root_b = _fixture(tmp_path / "mb")
    shutil.rmtree(root_b / "packages")
    new = _run(PORT_REL, root_b)

    assert old["exit"] == 1, old["exit"]
    assert new["exit"] == 1, new["exit"]
    assert LINE_PREFIX.sub("<prog>: line N: ", new["stderr"]) == LINE_PREFIX.sub(
        "<prog>: line N: ", old["stderr"]
    ), "masked stderr diverged:\n twin: %r\n port: %r" % (old["stderr"], new["stderr"])
    assert old["stderr"] != new["stderr"], (
        "the two diagnostics are byte-identical, so the mask is hiding nothing and "
        "this test should be folded into the parametrised cases"
    )
    assert old["calls"] == [], "the twin ran something after the cd failed"
    assert new["calls"] == [], "the port ran something after the cd failed"


def mkdir_is_gnu() -> bool:
    """Is the `mkdir` on PATH GNU coreutils, or a reimplementation?

    ASKED, because the answer decides what the case below may assert and it is NOT the same on every machine that runs this suite:

        GNU coreutils 9.7 (the CI runner)
            mkdir: cannot create directory 'denied/out': Permission denied
        uutils coreutils 0.8.0 (this tree's hosts)
            mkdir: Permission denied
    """
    try:
        proc = subprocess.run(
            ["mkdir", "--version"], capture_output=True, text=True, check=False, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return True
    return "GNU coreutils" in proc.stdout


def test_a_failing_mkdir_agrees_on_the_status_and_not_on_the_text(tmp_path):
    """DIVERGENCE 2, pinned rather than asserted away -- and it depends on WHICH coreutils is installed, which is the part this case used to get wrong.

    `mkdir -p` on an unwritable parent: the exit code is the script's and agrees. The diagnostic belongs to coreutils, and the port SYNTHESISES GNU's wording, so whether the two texts differ is a property of the host's mkdir:

        GNU coreutils 9.7 (the CI runner)  -> identical; the divergence is CLOSED
        uutils coreutils 0.8.0 (here)      -> different; the divergence is REAL

    An unconditional `!=` therefore passed on every machine in this tree and
    failed in CI run 34970782616 with its own message -- "the coreutils diagnostic and the port's now match, so this divergence is closed" -- which was true where it ran and false where it was written.

    The port's own text is asserted EXACTLY either way, so a port that drifted
    from GNU's wording still reds here on any host.
    """
    outs = {}
    for subject in (TWIN_REL, PORT_REL):
        root = _fixture(tmp_path / ("k-%s" % subject.name))
        denied = root / "packages" / "cli" / "denied"
        denied.mkdir()
        denied.chmod(0o500)
        try:
            outs[subject.name] = _run(subject, root, out_dir="denied/out")
        finally:
            denied.chmod(0o700)

    old = outs[TWIN_REL.name]
    new = outs[PORT_REL.name]
    assert old["exit"] == new["exit"] == 1, (old["exit"], new["exit"])
    assert old["calls"] == new["calls"] == [], "npm ran despite the mkdir failure"
    assert "mkdir" in old["stderr"], old["stderr"]
    assert "mkdir" in new["stderr"], new["stderr"]
    # The PORT is pinned absolutely: it promises GNU's wording on every host.
    assert new["stderr"] == "mkdir: cannot create directory 'denied/out': Permission denied\n", new[
        "stderr"
    ]
    if mkdir_is_gnu():
        assert old["stderr"] == new["stderr"], (
            "GNU coreutils and the port disagree, so the port no longer reproduces "
            "the diagnostic it was written to reproduce: %r vs %r" % (old["stderr"], new["stderr"])
        )
    else:
        assert old["stderr"] != new["stderr"], (
            "this host's non-GNU mkdir now matches the port's GNU wording, so the "
            "divergence this case documents is closed here too and the docstring "
            "in pack_cli_npm.py is stale"
        )


def test_select_tarball_is_the_twins_ordering():
    """The pure half of DEFECT 2, driven directly against the SHELL's own answer.

    A constant copied out of the port cannot contradict the port, so the expected order comes from bash running the twin's actual pipeline over the same names
    under `LC_ALL=C`.
    """
    names = [
        "rediacc-cli-0.9.0.tgz",
        "rediacc-cli-0.10.0.tgz",
        "rediacc-cli-latest.tgz",
        "rediacc-cli-1.0.0-rc.1.tgz",
    ]
    script = 'cd "$1" && ls rediacc-cli-*.tgz 2>/dev/null | head -1'
    # A directory rather than an argument list, because `ls` sorts what the SHELL globbed off the filesystem and handing it a pre-sorted argv would test the test.
    with tempfile.TemporaryDirectory() as scratch:
        for name in names:
            (pathlib.Path(scratch) / name).write_text("x", encoding="utf-8")
        expected = subprocess.run(
            ["bash", "-c", script, "_", scratch],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "LC_ALL": "C"},
        ).stdout.strip()
    assert expected == "rediacc-cli-0.10.0.tgz", "the twin's own pipeline said %r" % expected
    assert pack_cli_npm.select_tarball(names) == expected
    assert pack_cli_npm.select_tarball([]) is None
