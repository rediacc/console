"""`rediacc_ci.build.build_json`, driven against the bytes its bash twin printed.

WHILE BOTH COPIES EXISTED this file ran `.ci/scripts/build/build-json.sh` and the port over the same throwaway root, one after the other, and compared exit code, stdout, stderr and the npm call log. The K=5 ledger `.ci/shadow/w7p6-build-json.observations.jsonl` recorded that comparison over five distinct trees. The twin has now been deleted and every case that executed it
compares against `goldens/build-json/`, which holds the twin's OWN recorded bytes, captured from the tracked script on its last day in the tree. Each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

THE FIXTURE SHAPE AND ITS REASONS ARE `test_build_build_www.py`'s and are not restated: the port takes no root override so it is copied into a throwaway root; `npm` is a recording fake on a PATH that REPLACES the caller's rather than prepending to it; `rediacc_ci` is vendored so no absolute path outside the tree appears in any command string.

THE CALL LOG IS PART OF THE RECORDING. A build script that printed the right sentences while invoking the wrong npm script would pass a comparison of the two streams alone, so each golden carries a fourth `--- calls ---` section holding the fake npm's argv log. `frozen.render` stops at stderr; the section is appended after it, which `frozen.assert_corpus` accepts because it
checks the header and the `exit: ` opening line.

WHAT IS NORMALIZED is `$0` -- the one token a bash child and a python one never agreed on -- and the fixture root, which a recording compared against a tree built minutes later cannot share. Nothing else.

THE PAIR ASSERTION SURVIVES THE DELETION. `build-json.sh` was `build-www.sh` with the two output checks hand-rolled instead of delegated to `common.sh`, so the SAME failure printed one of two unrelated sentences depending on which site failed. Both twins' bytes on that failure are recorded here, so the disagreement stays a measurement rather than a claim about files a reader can
no longer run.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.build import build_json as port
from rediacc_ci.tests import frozen

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()

SLUG = "build-json"

TWIN_REL = ".ci/scripts/build/build-json.sh"
PORT_REL = ".ci/rediacc_ci/build/build_json.py"
COMMON_REL = ".ci/scripts/lib/common.sh"

# The www twin, RETIRED like `TWIN_REL` above it, whose bytes on the shared failure are recorded beside this pair's.
# The name survives because a frozen golden's header carries it and `test_the_www_golden_names_a_different_twin` reads that header; nothing copies the file any more, because there is no file. Measured 2026-09-23: `fixture()` still listed it, so both planted-defect controls raised FileNotFoundError instead of planting, which is the
# cannot-fail shape this pair exists to refuse.
WWW_TWIN_REL = ".ci/scripts/build/build-www.sh"

# Everything the port imports, transitively. `build_www` is here because `build_json` reuses its `run_npm`: the two twins were byte-identical through `:23` and duplicating the npm-invocation logic would be a second thing to drift.
VENDORED = (
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/log.py",
    ".ci/rediacc_ci/paths.py",
    ".ci/rediacc_ci/core/__init__.py",
    ".ci/rediacc_ci/core/common.py",
    ".ci/rediacc_ci/build/__init__.py",
    ".ci/rediacc_ci/build/build_www.py",
)

BASH = shutil.which("bash") or "/bin/bash"

# `dirname` for `get_repo_root` (common.sh:207), `uname` because sourcing common.sh runs `detect_os`/`detect_arch` at :509-510, `mkdir` for the fake. Anything not listed is ABSENT.
PATH_MINIMUM = ("dirname", "uname", "mkdir")

FAKE_NPM = """#!/bin/bash
printf 'CALL npm' >>"$FAKE_CALL_LOG"
for a in "$@"; do printf '\\t%s' "$a" >>"$FAKE_CALL_LOG"; done
printf '\\n' >>"$FAKE_CALL_LOG"
if [[ -n "${FAKE_NPM_STDOUT:-}" ]]; then echo "$FAKE_NPM_STDOUT"; fi
if [[ -n "${FAKE_NPM_STDERR:-}" ]]; then echo "$FAKE_NPM_STDERR" >&2; fi
if [[ -n "${FAKE_NPM_MAKE_DIST:-}" ]]; then mkdir -p "$FAKE_NPM_MAKE_DIST"; fi
if [[ -n "${FAKE_NPM_MAKE_INDEX:-}" ]]; then
    mkdir -p "$(dirname "$FAKE_NPM_MAKE_INDEX")"
    echo '<html></html>' >"$FAKE_NPM_MAKE_INDEX"
fi
exit "${FAKE_NPM_RC:-0}"
"""

SELF_RE = re.compile(r"\S*(?:%s|%s)" % (re.escape(TWIN_REL), re.escape(PORT_REL)))

CALLS_MARKER = "--- calls ---\n"


def fixture(tmp_path: pathlib.Path, *, port_source: str | None = None) -> pathlib.Path:
    """A throwaway root holding the port and `common.sh`."""
    root = tmp_path / "repo"
    for rel in (PORT_REL, COMMON_REL, *VENDORED):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
    for rel in (COMMON_REL, *VENDORED):
        shutil.copy2(ROOT / rel, root / rel)
    if port_source is None:
        shutil.copy2(ROOT / PORT_REL, root / PORT_REL)
    else:
        (root / PORT_REL).write_text(port_source, encoding="utf-8")
    return root


def scratch_bin(root: pathlib.Path, *, drop_npm: bool = False) -> str:
    """The ONLY directory on PATH for either side."""
    stub = root / "fixture-bin"
    stub.mkdir(parents=True, exist_ok=True)
    for name in PATH_MINIMUM:
        real = shutil.which(name)
        assert real is not None, "%s is missing from this machine" % name
        link = stub / name
        if not link.exists():
            link.symlink_to(real)
    npm = stub / "npm"
    if drop_npm:
        if npm.exists():
            npm.unlink()
    else:
        npm.write_text(FAKE_NPM, encoding="utf-8")
        npm.chmod(0o755)
    return str(stub)


def drive(
    root: pathlib.Path,
    argv: list[str],
    *,
    drop_npm: bool = False,
    cwd: str | None = None,
    tag: str = "new",
    **extra: str,
) -> tuple[int, str, str, str]:
    """One side, once, under a replaced PATH and a fresh call log."""
    call_log = root / ("%s-calls.log" % tag)
    call_log.write_text("", encoding="utf-8")
    env = {
        # REPLACED, never prepended.
        "PATH": scratch_bin(root, drop_npm=drop_npm),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(root / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
    }
    env.update(extra)
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
    return proc.returncode, proc.stdout, proc.stderr, call_log.read_text(encoding="utf-8")


def build(tmp_path: pathlib.Path, name: str, *, port_source: str | None = None):
    """The fixture tree and the run keywords for one recorded case."""
    root = fixture(tmp_path, port_source=port_source)
    kw: dict[str, str | bool] = {}
    if name == "a-complete-build":
        kw["FAKE_NPM_MAKE_INDEX"] = str(root / port.INDEX_HTML)
    elif name == "a-dist-without-an-index":
        kw["FAKE_NPM_MAKE_DIST"] = str(root / port.DIST_DIR)
    elif name == "a-failing-npm":
        kw["FAKE_NPM_RC"] = "1"
    elif name == "npm-exits-three":
        kw["FAKE_NPM_RC"] = "3"
    elif name == "npm-exits-one-hundred-and-thirty-seven":
        kw["FAKE_NPM_RC"] = "137"
    elif name == "a-missing-npm":
        kw["drop_npm"] = True
    elif name == "a-decoy-working-directory":
        decoy = tmp_path / "elsewhere"
        (decoy / "packages" / "json" / "dist").mkdir(parents=True, exist_ok=True)
        (decoy / "packages" / "json" / "dist" / "index.html").write_text("decoy", encoding="utf-8")
        kw["cwd"] = str(decoy)
    elif name == "npms-own-two-streams":
        kw["FAKE_NPM_STDOUT"] = "vite: 12 modules transformed"
        kw["FAKE_NPM_STDERR"] = "vite: warning: empty chunk"
        kw["FAKE_NPM_MAKE_INDEX"] = str(root / port.INDEX_HTML)
    elif name == "a-dist-that-is-a-file":
        (root / "packages" / "json").mkdir(parents=True, exist_ok=True)
        (root / "packages" / "json" / "dist").write_text("not a directory", encoding="utf-8")
    return root, kw


CASES = (
    "a-complete-build",
    "a-missing-dist-directory",
    "a-dist-without-an-index",
    "a-failing-npm",
    "npm-exits-three",
    "npm-exits-one-hundred-and-thirty-seven",
    "a-missing-npm",
    "a-decoy-working-directory",
    "npms-own-two-streams",
    "a-dist-that-is-a-file",
)

# The www twin's bytes on the failure both twins reach, recorded under its own provenance header.
WWW_CASE = "the-www-twin-on-a-missing-dist"

EXPECTED_EXIT = {
    "a-complete-build": 0,
    "a-missing-dist-directory": 1,
    "a-dist-without-an-index": 1,
    "a-failing-npm": 1,
    "npm-exits-three": 1,
    "npm-exits-one-hundred-and-thirty-seven": 1,
    "a-missing-npm": 1,
    "a-decoy-working-directory": 1,
    "npms-own-two-streams": 0,
    "a-dist-that-is-a-file": 1,
}


def mask(text: str, root: pathlib.Path) -> str:
    """`$0` and the fixture root, and nothing else."""
    return frozen.mask_root(SELF_RE.sub("<SELF>", text), root)


def split_golden(text: str) -> tuple[int, str, str, str]:
    """A recorded twin render, back into its four parts."""
    exit_line, rest = text.split("\n", 1)
    body, calls = rest.split(CALLS_MARKER, 1)
    stdout, stderr = body.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr, calls


def run_port(root: pathlib.Path, **kw) -> tuple[int, str, str, str]:
    return drive(root, [sys.executable, str(root / PORT_REL)], **kw)


def compare(root: pathlib.Path, name: str, **kw) -> tuple[int, str, str, str]:
    want_exit, want_out, want_err, want_calls = split_golden(frozen.read(SLUG, name))
    returncode, stdout, stderr, calls = run_port(root, **kw)
    assert returncode == want_exit, "%s: the twin exited %d, the port %d" % (
        name,
        want_exit,
        returncode,
    )
    assert mask(stdout, root) == want_out, "%s: stdout diverged from the recorded bytes" % name
    assert mask(stderr, root) == want_err, "%s: stderr diverged from the recorded bytes" % name
    assert mask(calls, root) == want_calls, "%s: the npm call log diverged" % name
    return returncode, stdout, stderr, calls


# --------------------------------------------------------------------------- The control on the control ---------------------------------------------------------------------------


def test_the_scratch_path_cannot_reach_a_real_npm(tmp_path: pathlib.Path) -> None:
    """`npm run build:json` in this checkout is a real site build. A PREPENDED PATH would still resolve the real binary, so the fixture REPLACES it and this asserts the replacement holds in both directions."""
    root = fixture(tmp_path)
    sealed = scratch_bin(root)
    assert shutil.which("npm", path=sealed) == str(root / "fixture-bin" / "npm")
    dropped = scratch_bin(root, drop_npm=True)
    assert shutil.which("npm", path=dropped) is None, "a real npm is reachable from the fixture"
    assert shutil.which("node", path=dropped) is None


# --------------------------------------------------------------------------- Every recorded case ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", CASES)
def test_port_matches_the_twins_recorded_output(tmp_path: pathlib.Path, name: str) -> None:
    root, kw = build(tmp_path, name)
    returncode, _, _, _ = compare(root, name, **kw)
    assert returncode == EXPECTED_EXIT[name], "the recorded verdict moved"


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, {*CASES, WWW_CASE})


def test_the_green_case_is_not_vacuously_equal() -> None:
    """Two implementations that both print nothing agree about nothing."""
    green = split_golden(frozen.read(SLUG, "a-complete-build"))
    red = split_golden(frozen.read(SLUG, "a-missing-dist-directory"))
    assert green[2] != red[2]
    assert "✓ json build complete: packages/json/dist/\n" in green[2]
    assert green[3] == "CALL npm\trun\tbuild:json\n", "the twin ran the wrong npm script"


# --------------------------------------------------------------------------- The recorded defects ---------------------------------------------------------------------------


def test_defect_npms_exit_code_is_flattened_to_one() -> None:
    """npm exiting 3 or 137 both became a flat 1, as in `build-www.sh`."""
    for name in ("npm-exits-three", "npm-exits-one-hundred-and-thirty-seven"):
        assert split_golden(frozen.read(SLUG, name))[0] == 1, "%s leaked npm's status" % name


def test_defect_the_green_tick_precedes_every_verification() -> None:
    """`✓ json build completed` was printed on npm's exit code alone."""
    lines = split_golden(frozen.read(SLUG, "a-missing-dist-directory"))[2].splitlines()
    assert lines[1] == "✓ json build completed"
    assert lines[2].startswith("✗ ")


def test_a_missing_npm_reads_as_a_failed_build_with_bashs_line_above_it() -> None:
    recorded = split_golden(frozen.read(SLUG, "a-missing-npm"))
    assert recorded[2] == (
        "→ Building json (template catalog)...\n"
        "<SELF>: line %d: npm: command not found\n"
        "✗ json build failed\n" % port.NPM_LINE
    )
    assert recorded[3] == "", "npm was absent, so nothing could have been logged"


def test_the_two_twins_said_different_things_about_the_same_failure() -> None:
    """THE PAIR ASSERTION. `build-json.sh:26-34` hand-rolled what `build-www.sh:26-27` delegates to `common.sh`, so a build that produced no `dist/` reported one of two unrelated sentences depending on which site it was.

    The hand-rolled half was the better one: it names the site, which is exactly what `build-www.sh`'s dropped label argument was trying and failing to do.
    """
    json_side = split_golden(frozen.read(SLUG, "a-missing-dist-directory"))
    www_side = split_golden(frozen.read(SLUG, WWW_CASE))
    assert json_side[0] == www_side[0] == 1
    assert json_side[2].endswith("✗ json dist directory not created\n")
    assert www_side[2].endswith("✗ Required directory 'packages/www/dist' does not exist\n")
    assert "json" not in www_side[2].splitlines()[-1]
    assert "www build output" not in www_side[2]


def test_the_www_golden_names_a_different_twin() -> None:
    """The pair assertion is only a pair if the two recordings came from two programs."""
    header = (frozen.directory(SLUG) / ("%s.golden" % WWW_CASE)).read_text(encoding="utf-8")
    assert WWW_TWIN_REL in header.split("\n", 1)[0]
    assert TWIN_REL not in header.split("\n", 1)[0]


def test_the_port_and_the_twin_agree_about_the_repo_root_in_this_checkout() -> None:
    proc = subprocess.run(
        [BASH, "-c", 'source "$1" && get_repo_root', "bash", str(ROOT / COMMON_REL)],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    assert proc.stdout.strip() == str(port.repo_root())
    assert proc.stdout.strip() == str(ROOT)


# --------------------------------------------------------------------------- The controls: these goldens can actually fail ---------------------------------------------------------------------------


def test_a_planted_dist_check_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """A gate that has never been seen to fail is not a gate.

    The plant swaps `is_dir()` for `exists()` on the dist check, which is what a reader "simplifying" the port would reach for. It is invisible on every other case in this file and visible on exactly one: a `packages/json/dist` that is a FILE rather than a directory, which `[[ ! -d ]]` rejected and `exists()` accepts.
    """
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")
    planted = source.replace(
        "if not pathlib.Path(DIST_DIR).is_dir():",
        "if not pathlib.Path(DIST_DIR).exists():",
    )
    assert planted != source, "the plant site moved; this control is not planting anything"
    root, kw = build(tmp_path, "a-dist-that-is-a-file", port_source=planted)
    with pytest.raises(AssertionError):
        compare(root, "a-dist-that-is-a-file", **kw)
    # And the tracked port still agrees against the same fixture.
    clean_root, clean_kw = build(tmp_path / "clean", "a-dist-that-is-a-file")
    compare(clean_root, "a-dist-that-is-a-file", **clean_kw)
    assert (ROOT / PORT_REL).read_text(encoding="utf-8") == source


def test_a_planted_repair_of_the_premature_tick_is_caught(tmp_path: pathlib.Path) -> None:
    """THE NEW CONTROL ON THE GOLDENS. Move the green tick after the verifications.

    Printing `✓ json build completed` before anything has been verified is the twin's own defect, and repairing it is exactly the improvement a reader would make on sight. The recording forbids it: the tick sits on the second stderr line of every failing case, so a port that withheld it no longer matches the bytes.
    """
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")
    anchor = '    log.info("json build completed")\n'
    assert source.count(anchor) == 1, "the plant's anchor moved"
    planted = source.replace(anchor, "    pass\n")
    root, kw = build(tmp_path, "a-missing-dist-directory", port_source=planted)
    with pytest.raises(AssertionError):
        compare(root, "a-missing-dist-directory", **kw)
    clean_root, clean_kw = build(tmp_path / "clean", "a-missing-dist-directory")
    compare(clean_root, "a-missing-dist-directory", **clean_kw)
    assert (ROOT / PORT_REL).read_text(encoding="utf-8") == source
