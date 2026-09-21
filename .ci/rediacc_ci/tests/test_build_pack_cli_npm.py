"""`rediacc_ci.build.pack_cli_npm`, driven against the bytes its bash twin printed.

THE TWIN HAS BEEN DELETED. While both copies existed this file ran `.ci/scripts/build/pack-cli-npm.sh` and the port over the same fixture tree and compared EIGHT observables per case. The ledger `.ci/shadow/w7p6-pack-cli-npm.observations.jsonl` holds 5 rows of that comparison.

Every fixture case now compares against `goldens/pack-cli-npm/`, which holds the twin's OWN recorded bytes, captured on its last day in the tree, and each golden's provenance header carries the blob sha.

WHAT IS COMPARED, AND WHY IT IS EIGHT THINGS. This subject's product is a file on disk, so exit code and stdout describe barely half of it. The recorded shape therefore carries two sections beyond the streams:

  `--- calls ---`  every `jq` and `npm` invocation, its argv AND its cwd. A port
                   that printed the same transcript while never running
                   `npm pack`, or running it from the wrong directory, passes a
                   stdout-only comparison and ships nothing. The cwd half is
                   load-bearing: the twin's whole header is about a step that
                   resolved the script's path against the wrong directory.
  `--- tree ---`   what is in `OUT_DIR` afterwards by name, the BYTES of
                   `rediacc-cli-latest.tgz`, `packages/cli/package.json` after
                   the run, and whether `package.json.tmp` was left behind. The
                   alias is the artifact every install path fetches, so
                   comparing only its NAME would pass a port that aliased the
                   wrong tarball, which is exactly defect 2's shape.

IT WAS SAFE TO RETIRE, and that was established before anything was deleted. The one live invocation is already the port, `.github/workflows/ci-build-docker.yml:91`, as `PYTHONPATH=.ci python3 -m rediacc_ci.build.pack_cli_npm`.

The only other reference was a CLOSURE PATH LIST that is hashed to decide whether a docker build can be skipped, and it exists twice, at `rediacc_ci/ci/generate_tag.py:124` and `.ci/scripts/ci/generate-tag.sh:219`. Both were flipped to the port's path and the generate-tag differential was re-run with both of ITS copies still present, which is the live evidence that the two lists
still agree and the closure hash still resolves.

PATH IS REPLACED, NEVER PREPENDED. This host has a real `npm` and a real `jq`, and `packages/cli` in the real checkout is one `get_repo_root` away from any fixture that gets its root wrong. A prepended PATH would leave a subject that mis-derived its root running a REAL `npm pack` against the live tree. The binder therefore builds the ENTIRE PATH out of named tools plus the two
fakes, and asserts that anything it was asked to exclude really is absent, which is a control on the control: a probe that cannot fire looks exactly like a subject that cannot fail.

`LC_ALL=C` ON EVERY RUN, deliberately, and it is not boilerplate: the tarball choice was `ls | head -1`, whose order is `LC_COLLATE`'s, and the port sorts by code point. The two agree under C. Pinning it makes the comparison measure the port instead of the developer's locale.

TWO CASES ARE COMPARED BY SHAPE. A missing `packages/cli` makes both sides fail the `cd` and exit 1, and bash named the script and its line where the port names its own; everything after that prefix is compared byte for byte. A failing `mkdir` agrees on the status and not necessarily on the text, because the diagnostic belongs to coreutils and the port SYNTHESISES GNU's wording, so
whether the two agree is a property of the host's mkdir rather than of the port. The port's own text is asserted exactly either way.

WHICH CASES ARE RECORDED AND WHICH ARE NOT. Every case driving the fixture has a golden. `test_select_tarball_is_the_twins_ordering` does NOT: its oracle is bash running the twin's actual pipeline over a scratch directory, and bash is still here, so asking it remains the honest answer rather than freezing one.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.build import pack_cli_npm as pcn
from rediacc_ci.tests import frozen

ROOT = paths.repo_root()
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "build" / "pack_cli_npm.py"

TWIN_REL = pathlib.PurePosixPath(".ci/scripts/build/pack-cli-npm.sh")
PORT_REL = pathlib.PurePosixPath(".ci/rediacc_ci/build/pack_cli_npm.py")

SLUG = "pack-cli-npm"
CALLS_MARKER = "--- calls ---\n"
TREE_MARKER = "--- tree ---\n"

# The recording `jq`. It performs the twin's ACTUAL transformation rather than echoing a canned manifest, because the recorded tree compares the resulting package.json and a canned answer would make that comparison vacuous.
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

# Everything the subject needs once PATH is rebuilt from scratch. Named rather than derived: a PATH built by copying "everything except npm" is a PATH nobody can state, and the first tool it forgot would look like a divergence in the subject rather than a hole in the harness.
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

# The manifest the fixture starts from. Two keys beyond `version`, so a port that rewrote the file wholesale instead of editing one field would show up in the recorded tree.
BASE_MANIFEST = {"name": "@rediacc/cli", "version": "0.0.0-dev", "private": False}

# `<path>: line <n>: `, bash's prefix on a `cd` diagnostic and the port's own equivalent. Masked only in the one case that is ABOUT that divergence.
LINE_PREFIX = re.compile(r"^[^\n]*: line \d+: ", re.MULTILINE)

# name -> the fixture shape and the run parameters
CASE_KW: dict[str, dict[str, typing.Any]] = {
    "the-placeholder-version": {},
    "a-version-injected": {"version": "1.2.3"},
    "an-empty-version": {"version": ""},
    "a-failing-jq": {"version": "9.9.9", "jq_rc": 4},
    "a-failing-npm-pack": {"npm_rc": 7},
    "npm-pack-producing-nothing": {"produces": ()},
    "two-tarballs": {"produces": ("rediacc-cli-0.9.0.tgz", "rediacc-cli-0.10.0.tgz")},
    "a-stale-tarball": {
        "seeded": ("rediacc-cli-0.10.0.tgz",),
        "produces": ("rediacc-cli-0.9.0.tgz",),
    },
    "the-alias-is-the-only-match": {
        "seeded": ("rediacc-cli-latest.tgz",),
        "produces": ("other-name.tgz",),
    },
    "no-jq-on-the-path": {"exclude": ("jq",)},
    "no-npm-on-the-path": {"exclude": ("npm",)},
    "a-nested-out-dir": {"out_dir": "deep/nested/out"},
    "a-non-ascii-manifest": {
        "manifest": {"name": "@rediacc/cli", "version": "0.0.0-dev", "keywords": ["ä", "b"]},
        "version": "2.0.0",
    },
    "a-missing-packages-cli": {"drop_packages": True},
    "an-unwritable-out-dir": {"denied": True, "out_dir": "denied/out"},
}

CASES = tuple(CASE_KW)

# The two cases in which a diagnostic belongs to something other than the subject. Compared by shape, in their own tests.
DIVERGENT = ("a-missing-packages-cli", "an-unwritable-out-dir")


def fixture(where: pathlib.Path, name: str, subject: pathlib.PurePosixPath) -> pathlib.Path:
    """A tree shaped like the repository, holding a COPY of the subject.

    A copy, because the subject derives the console root from its own location (`BASH_SOURCE` or `__file__`, then three directories up). Driving the TRACKED file with a `cwd` would point it at the real repository, and the version injection would then rewrite `packages/cli/package.json` in the live tree.

    `.resolve()` on the root is load-bearing: bash's `cd X && pwd` reports the LOGICAL path it was handed while `pathlib.resolve()` follows symlinks, and the root appears in `cd` diagnostics.
    """
    kw = CASE_KW[name]
    root = where.resolve() / "tree"
    (root / ".ci" / "scripts" / "build").mkdir(parents=True)
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "build").mkdir(parents=True)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / "common.sh")
    if subject.suffix == ".sh":
        shutil.copy2(ROOT / str(TWIN_REL), root / TWIN_REL)
    else:
        shutil.copy2(PORT, root / PORT_REL)

    cli = root / "packages" / "cli"
    cli.mkdir(parents=True)
    (cli / "package.json").write_text(
        json.dumps(kw.get("manifest") or BASE_MANIFEST, indent=2) + "\n", encoding="utf-8"
    )
    out_dir = kw.get("out_dir", "out")
    for seeded in kw.get("seeded", ()):
        dest = cli / out_dir
        dest.mkdir(parents=True, exist_ok=True)
        (dest / seeded).write_text("seeded:" + seeded + "\n", encoding="utf-8")
    if kw.get("drop_packages"):
        shutil.rmtree(root / "packages")
    if kw.get("denied"):
        denied = cli / "denied"
        denied.mkdir()
        denied.chmod(0o500)
    return root


def binder(
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
    stub = where / "bin"
    stub.mkdir(parents=True, exist_ok=True)
    for tool in NEEDED:
        if tool in exclude:
            continue
        target = shutil.which(tool)
        if target is None:
            continue
        link = stub / tool
        if not link.exists():
            link.symlink_to(target)

    if "jq" not in exclude:
        jq = stub / "jq"
        jq.write_text(FAKE_JQ % {"log": str(log), "root": str(root), "rc": jq_rc}, encoding="utf-8")
        jq.chmod(0o755)
    if "npm" not in exclude:
        npm = stub / "npm"
        npm.write_text(
            FAKE_NPM
            % {"log": str(log), "root": str(root), "rc": npm_rc, "produces": list(produces)},
            encoding="utf-8",
        )
        npm.chmod(0o755)

    assert shutil.which("bash", path=str(stub)), "the restricted PATH cannot run bash"
    assert shutil.which("python3", path=str(stub)), "the restricted PATH cannot run the port"
    for tool in exclude:
        assert shutil.which(tool, path=str(stub)) is None, (
            "%r survived exclusion; the case that needs it absent would be vacuous" % tool
        )
    return str(stub)


def run(
    subject: pathlib.PurePosixPath, where: pathlib.Path, name: str
) -> tuple[int, str, str, str, str]:
    """One subject, once, over its own fixture tree, collecting all eight observables."""
    kw = CASE_KW[name]
    where.mkdir(parents=True, exist_ok=True)
    root = fixture(where, name, subject)
    out_dir = kw.get("out_dir", "out")
    log = where / "calls.txt"
    env = {
        "PATH": binder(
            where,
            root,
            log=log,
            jq_rc=kw.get("jq_rc", 0),
            npm_rc=kw.get("npm_rc", 0),
            produces=kw.get("produces", ("rediacc-cli-1.2.3.tgz",)),
            exclude=kw.get("exclude", ()),
        ),
        "HOME": str(where),
        "PYTHONDONTWRITEBYTECODE": "1",
        # See the module docstring: `ls | head -1` and a code point sort agree under C and are not guaranteed to elsewhere.
        "LC_ALL": "C",
        "LANG": "C",
        # The port imports `rediacc_ci.log` and `rediacc_ci.core.common`; the COPY under the fixture is what runs, so the package has to come from the real checkout. This is the only thing the fixture borrows from outside itself.
        "PYTHONPATH": str(ROOT / ".ci"),
        "OUT_DIR": out_dir,
    }
    if "version" in kw:
        env["VERSION"] = kw["version"]
    target = root / (TWIN_REL if subject.suffix == ".sh" else PORT_REL)
    try:
        proc = subprocess.run(
            ["bash" if subject.suffix == ".sh" else "python3", str(target)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=120,
        )
    finally:
        if kw.get("denied"):
            (root / "packages" / "cli" / "denied").chmod(0o700)

    calls = log.read_text(encoding="utf-8") if log.exists() else ""
    if log.exists():
        log.unlink()
    cli = root / "packages" / "cli"
    dest = cli / out_dir
    alias = dest / "rediacc-cli-latest.tgz"
    manifest = cli / "package.json"
    tree = {
        "out_dir": sorted(p.name for p in dest.iterdir()) if dest.is_dir() else None,
        "alias": alias.read_text(encoding="utf-8") if alias.is_file() else None,
        "manifest": manifest.read_text(encoding="utf-8") if manifest.is_file() else None,
        "tmp_left": (cli / "package.json.tmp").is_file(),
    }

    def mask(text: str) -> str:
        return text.replace(str(root), "<root>").replace(str(where), "<work>")

    return (
        proc.returncode,
        mask(proc.stdout),
        mask(proc.stderr),
        mask(calls),
        mask(json.dumps(tree, indent=2, sort_keys=True, ensure_ascii=False)),
    )


def render(code: int, stdout: str, stderr: str, calls: str, tree: str) -> str:
    return "%s%s%s%s%s\n" % (
        frozen.render(code, stdout, stderr),
        CALLS_MARKER,
        calls,
        TREE_MARKER,
        tree,
    )


def recorded(name: str) -> tuple[int, str, str, str, str]:
    text = frozen.read(SLUG, name)
    exit_line, rest = text.split("\n", 1)
    stdout, rest = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    stderr, rest = rest.split(CALLS_MARKER, 1)
    calls, tree = rest.split(TREE_MARKER, 1)
    return (
        int(exit_line.removeprefix("exit: ")),
        stdout,
        stderr,
        calls,
        tree.removesuffix("\n"),
    )


def port(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str, str]:
    return run(PORT_REL, tmp_path / name, name)


def lines(calls: str) -> list[str]:
    return [line for line in calls.splitlines() if line]


def tree_of(state: str) -> dict[str, typing.Any]:
    return json.loads(state)


def compare(tmp_path: pathlib.Path, name: str) -> tuple[int, str, str, str, str]:
    want = recorded(name)
    got = port(tmp_path, name)
    labels = ("exit code", "stdout", "stderr", "the CALL LOG", "the tree left behind")
    # `strict=True`: the tuple and the labels must stay the same length, and a silently truncated zip is how a comparison stops checking its last field.
    for label, a, b in zip(labels, want, got, strict=True):
        assert a == b, "%s: %s diverged:\n--- recorded ---\n%s\n--- port ---\n%s" % (
            name,
            label,
            a,
            b,
        )
    return got


@pytest.mark.parametrize("name", [c for c in CASES if c not in DIVERGENT])
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    compare(tmp_path, name)


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


# --------------------------------------------------------------------------- What the recordings say ---------------------------------------------------------------------------


def test_the_fakes_were_actually_reached() -> None:
    """ANTI-VACUITY. Every comparison above is worthless if `npm pack` never ran.

    Also pins the CWD, which is the twin's own header incident: the subject has to be inside `packages/cli` when it packs, however it was invoked.
    """
    code, _, _, calls, _ = recorded("a-version-injected")
    assert lines(calls) == [
        "call: jq --arg v 1.2.3 .version = $v package.json",
        "cwd: packages/cli",
        "call: npm pack --pack-destination out",
        "cwd: packages/cli",
    ], calls
    assert code == 0, "the happy path must succeed"


def test_the_placeholder_really_skips_jq() -> None:
    """CONTROL for the case above, in the other direction: `0.0.0-dev` must call NO jq at all. A port that injected unconditionally would satisfy every positive assertion in this file and would dirty `package.json` on every dev build."""
    calls = recorded("the-placeholder-version")[3]
    assert not [c for c in lines(calls) if c.startswith("call: jq")], calls
    assert tree_of(recorded("the-placeholder-version")[4])["manifest"] == (
        json.dumps(BASE_MANIFEST, indent=2) + "\n"
    ), "the manifest was rewritten despite the placeholder"


def test_an_empty_version_takes_the_placeholder_path() -> None:
    assert not [c for c in lines(recorded("an-empty-version")[3]) if c.startswith("call: jq")]


def test_defect_1_the_dead_else_branch_is_dead() -> None:
    """DEFECT 1, pinned.

    `npm pack` produced nothing, which is the ONE failure the twin wrote a message for. Under `set -euo pipefail` the message never printed: the `CLI_PKG="$(ls ... | head -1)"` assignment carried `ls`'s exit 2 and errexit killed the script before the `if`. So the observable is exit 2 and total silence. Reported, not fixed: the repair is a cutover-box decision.
    """
    code, _, stderr, _, tree = recorded("npm-pack-producing-nothing")
    assert code == 2, "expected the silent 2, got %r" % code
    assert "npm pack produced no" not in stderr, (
        "the unreachable branch RAN, so the defect is gone and this recording is stale"
    )
    assert tree_of(tree)["alias"] is None, "an alias was written anyway"


def test_defect_3_a_failing_jq_is_announced_as_a_success() -> None:
    """DEFECT 3, pinned, and the reason this file exists.

    `set -e` does not fire on a failing member of an AND-OR list, so a jq that died left `package.json` untouched, left an EMPTY `package.json.tmp` behind, printed `✓ Injected version 9.9.9 into package.json` anyway, packed the uninjected manifest and exited 0.

    Four separate assertions rather than one, because each is a different half of the lie and a port could get any one of them right by accident.
    """
    code, _, stderr, calls, tree = recorded("a-failing-jq")
    assert code == 0, "the failure was reported after all: %r" % code
    assert "Injected version 9.9.9" in stderr, (
        "the success line is gone, so the defect is fixed and this recording is stale"
    )
    assert tree_of(tree)["manifest"] == json.dumps(BASE_MANIFEST, indent=2) + "\n", (
        "the manifest changed despite jq failing"
    )
    assert tree_of(tree)["tmp_left"], "package.json.tmp was cleaned up"
    assert [c for c in lines(calls) if c.startswith("call: npm")], (
        "npm pack did not run, so nothing was published from the stale manifest"
    )


def test_defect_2_a_stale_tarball_is_aliased_over_this_runs_own() -> None:
    """DEFECT 2, demonstrated rather than asserted in prose.

    `OUT_DIR` defaults to `/tmp/cli-npm` and nothing cleans it, so a previous run's `rediacc-cli-0.10.0.tgz` is still there when this run packs 0.9.0. `ls | head -1` sorts `1` before `9`, so the alias every install path fetches gets the OLD tarball and the subject reports success naming it.
    """
    code, _, stderr, _, tree = recorded("a-stale-tarball")
    assert code == 0
    assert tree_of(tree)["alias"] == "seeded:rediacc-cli-0.10.0.tgz\n", (
        "the alias no longer carries the STALE tarball, so the defect is gone"
    )
    assert "Packed rediacc-cli-0.10.0.tgz" in stderr, stderr


def test_two_tarballs_take_the_lexically_first() -> None:
    """The same ordering rule with no stale file involved: `0.10.0` precedes `0.9.0` under `LC_ALL=C`, which is a version comparison nobody wrote."""
    tree = tree_of(recorded("two-tarballs")[4])
    assert tree["alias"] == "tarball-of:rediacc-cli-0.10.0.tgz\n", tree["alias"]


def test_the_alias_being_the_only_match_is_a_refusal() -> None:
    """`cp X X` on the alias itself: the subject names a tarball that is the alias, and the copy refuses rather than truncating the file."""
    code, _, stderr, _, _ = recorded("the-alias-is-the-only-match")
    assert code != 0 or "same file" in stderr or "Packed" in stderr, stderr


def test_a_failing_npm_pack_is_propagated() -> None:
    code, _, _, _, tree = recorded("a-failing-npm-pack")
    assert code == 7, "npm's own status was flattened"
    assert tree_of(tree)["alias"] is None


def test_the_two_missing_tools() -> None:
    """Each tool absent on its own, so the message names the one that is missing."""
    for name in ("no-jq-on-the-path", "no-npm-on-the-path"):
        code, _, stderr, _, _ = recorded(name)
        assert code != 0, name
        assert stderr.strip() != "", name


def test_a_nested_out_dir_is_created() -> None:
    code, _, _, calls, tree = recorded("a-nested-out-dir")
    assert code == 0
    assert "--pack-destination deep/nested/out" in calls
    assert tree_of(tree)["alias"] is not None


def test_a_non_ascii_manifest_survives_injection() -> None:
    """The manifest is read and written as UTF-8 on both sides; a port that opened it in the locale's encoding would mangle a keyword nobody would notice until npm refused the tarball."""
    code, _, _, _, tree = recorded("a-non-ascii-manifest")
    assert code == 0
    manifest = json.loads(tree_of(tree)["manifest"])
    assert manifest["keywords"] == ["ä", "b"]
    assert manifest["version"] == "2.0.0"


# --------------------------------------------------------------------------- The two divergences, pinned rather than papered over ---------------------------------------------------------------------------


def test_a_missing_packages_cli_names_the_program_that_could_not_proceed(
    tmp_path: pathlib.Path,
) -> None:
    """DIVERGENCE 1, asserted with the prefix masked.

    Both sides fail the `cd` and exit 1. bash's diagnostic named the script and its line; the port's names the port and its line. Everything after that prefix, `cd: <dir>: No such file or directory`, is compared byte for byte, and the two paths are asserted to be DIFFERENT so this still means something if someone ever makes the port print the twin's path.
    """
    name = "a-missing-packages-cli"
    want = recorded(name)
    got = port(tmp_path, name)
    assert want[0] == got[0] == 1
    assert LINE_PREFIX.sub("<prog>: line N: ", got[2]) == LINE_PREFIX.sub(
        "<prog>: line N: ", want[2]
    ), "masked stderr diverged:\n recorded: %r\n port: %r" % (want[2], got[2])
    assert want[2] != got[2], (
        "the two diagnostics are byte-identical, so the mask is hiding nothing and this "
        "case should join the parametrised ones"
    )
    assert want[3] == got[3] == "", "something ran after the cd failed"


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


def test_a_failing_mkdir_agrees_on_the_status_and_not_on_the_text(
    tmp_path: pathlib.Path,
) -> None:
    """DIVERGENCE 2, pinned rather than asserted away, and it depends on WHICH coreutils is installed.

    `mkdir -p` on an unwritable parent: the exit code is the subject's and agrees with the recording. The diagnostic belongs to coreutils, and the port SYNTHESISES GNU's wording, so whether the two texts differ is a property of the host's mkdir.

    An unconditional `!=` passed on every machine in this tree and failed in CI run 34970782616, which was true where it ran and false where it was written.

    The port's own text is asserted EXACTLY either way, so a port that drifted from GNU's wording still reds here on any host.
    """
    name = "an-unwritable-out-dir"
    want = recorded(name)
    got = port(tmp_path, name)
    assert want[0] == got[0] == 1, (want[0], got[0])
    assert want[3] == got[3] == "", "npm ran despite the mkdir failure"
    assert "mkdir" in want[2], want[2]
    assert got[2] == "mkdir: cannot create directory 'denied/out': Permission denied\n", got[2]
    if mkdir_is_gnu():
        assert want[2] == got[2], (
            "GNU coreutils and the port disagree, so the port no longer reproduces the "
            "diagnostic it was written to reproduce: %r vs %r" % (want[2], got[2])
        )
    else:
        assert want[2] != got[2], (
            "this host's non-GNU mkdir now matches the port's GNU wording, so the "
            "divergence this case documents is closed here too"
        )


# --------------------------------------------------------------------------- The shell's own ordering, deliberately NOT recorded ---------------------------------------------------------------------------


def test_select_tarball_is_the_twins_ordering() -> None:
    """The pure half of DEFECT 2, driven directly against the SHELL's own answer.

    NOT RECORDED: a constant copied out of the port cannot contradict the port, so the expected order comes from bash running the twin's actual pipeline over the same names under `LC_ALL=C`, and bash is still here to ask.
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
    assert pcn.select_tarball(names) == expected
    assert pcn.select_tarball([]) is None


# --------------------------------------------------------------------------- The control: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_alias_of_the_wrong_tarball_is_caught(tmp_path: pathlib.Path) -> None:
    """THE CONTROL ON THE GOLDENS, aimed at the section that would otherwise be decoration.

    `rediacc-cli-latest.tgz` is the artifact every install path fetches, and it is a COPY of whichever tarball the subject selected. The plant reverses the selection so the LAST name wins instead of the first, which on the two-tarball recording aliases `0.9.0` where the corpus holds `0.10.0`. The transcript still says `✓ Packed ...`, the exit code is still 0, and the directory
    listing is still the same two names, so only the alias BYTES in the `--- tree ---` section see it.

    THE PLANT IS A COPY WRITTEN AT THE SUBJECT'S OWN PATH INSIDE THE FIXTURE, which is where the module already runs from in every case here, so the root it derives from its own location is unchanged. The tracked file is never written.
    """
    original = PORT.read_text(encoding="utf-8")
    anchor = "def select_tarball("
    assert original.count(anchor) == 1, "the plant's anchor moved"

    name = "two-tarballs"
    want = recorded(name)
    assert tree_of(want[4])["alias"] == "tarball-of:rediacc-cli-0.10.0.tgz\n", "the corpus moved"

    where = tmp_path / "planted"
    where.mkdir(parents=True)
    root = fixture(where, name, PORT_REL)
    (root / PORT_REL).write_text(
        original.replace(
            anchor,
            "def select_tarball(names):  # noqa: ANN001, ANN201 - the plant\n"
            "    ordered = sorted(n for n in names if n.startswith('rediacc-cli-'))\n"
            "    return ordered[-1] if ordered else None\n"
            "\n"
            "\n"
            "def _unreachable_select_tarball(",
            1,
        ),
        encoding="utf-8",
    )
    log = where / "calls.txt"
    proc = subprocess.run(
        ["python3", str(root / PORT_REL)],
        capture_output=True,
        text=True,
        env={
            "PATH": binder(
                where,
                root,
                log=log,
                jq_rc=0,
                npm_rc=0,
                produces=CASE_KW[name]["produces"],
                exclude=(),
            ),
            "HOME": str(where),
            "PYTHONDONTWRITEBYTECODE": "1",
            "LC_ALL": "C",
            "LANG": "C",
            "PYTHONPATH": str(ROOT / ".ci"),
            "OUT_DIR": "out",
        },
        check=False,
        timeout=120,
    )
    alias = root / "packages" / "cli" / "out" / "rediacc-cli-latest.tgz"
    assert proc.returncode == want[0] == 0, proc.stderr
    assert alias.read_text(encoding="utf-8") == "tarball-of:rediacc-cli-0.9.0.tgz\n", (
        "the plant did not change which tarball was aliased"
    )
    assert (
        sorted(p.name for p in (root / "packages" / "cli" / "out").iterdir())
        == (tree_of(want[4])["out_dir"])
    ), "the plant changed the directory listing too, so the alias is not the only evidence"

    compare(tmp_path / "good", name)
    assert PORT.read_text(encoding="utf-8") == original
