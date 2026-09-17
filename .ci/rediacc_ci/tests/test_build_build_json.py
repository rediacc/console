"""Differential: `rediacc_ci.build.build_json` against its twin `.ci/scripts/build/build-json.sh`.

THE FIXTURE SHAPE AND ITS REASONS ARE `test_build_build_www.py`'s and are not restated: neither side takes a root override so both are copied into a throwaway root; `npm` is a recording fake on a PATH that REPLACES the caller's rather than prepending to it; `rediacc_ci` is vendored so no absolute path outside the tree appears in any command string; `$0` is masked to `<SELF>` and
nothing else is.

WHAT THIS FILE ADDS ON TOP OF THAT is the pair assertion. `build-json.sh` is `build-www.sh` with the two output checks hand-rolled instead of delegated to `common.sh`, so the SAME failure prints a different sentence depending on which site failed. `test_the_two_twins_say_different_things_about_the_same_failure` drives BOTH bash twins and pins the disagreement, which is the only way
a reader finds out that the wording is accidental rather than chosen.

K=5 LEDGER: `.ci/shadow/w7p6-build-json.observations.jsonl`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.build import build_json as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()

TWIN_REL = ".ci/scripts/build/build-json.sh"
PORT_REL = ".ci/rediacc_ci/build/build_json.py"
COMMON_REL = ".ci/scripts/lib/common.sh"

# The www twin and its port, copied in for the one cross-pair case below.
WWW_TWIN_REL = ".ci/scripts/build/build-www.sh"

# Everything the port imports, transitively. `build_www` is here because `build_json` reuses its `run_npm`: the two twins are byte-identical through `:23` and duplicating the npm-invocation logic would be a second thing to drift.
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


def fixture(tmp_path: pathlib.Path, *, port_source: str | None = None) -> pathlib.Path:
    root = tmp_path / "repo"
    for rel in (TWIN_REL, PORT_REL, COMMON_REL, WWW_TWIN_REL, *VENDORED):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
    for rel in (TWIN_REL, COMMON_REL, WWW_TWIN_REL, *VENDORED):
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


def _run(
    root: pathlib.Path,
    side: str,
    *,
    drop_npm: bool = False,
    cwd: str | None = None,
    script: str | None = None,
    **extra,
):
    call_log = root / ("%s-calls.log" % side)
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
    if side == "old":
        argv = [BASH, str(root / (script or TWIN_REL))]
    else:
        argv = [sys.executable, str(root / PORT_REL)]
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
    """Both sides from the SAME starting state; `packages/` is reset between."""
    made = root / "packages"
    snapshot = root / ".packages-snapshot"
    if snapshot.exists():
        shutil.rmtree(snapshot)
    if made.exists():
        shutil.copytree(made, snapshot, symlinks=True)
    old, old_calls = _run(root, "old", **kw)
    if made.exists():
        shutil.rmtree(made)
    if snapshot.exists():
        shutil.copytree(snapshot, made, symlinks=True)
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


# --------------------------------------------------------------------------- The control on the control ---------------------------------------------------------------------------


def test_the_scratch_path_cannot_reach_a_real_npm(tmp_path) -> None:
    """`npm run build:json` in this checkout is a real site build. A PREPENDED PATH would still resolve the real binary, so the fixture REPLACES it and this asserts the replacement holds in both directions.
    """
    root = fixture(tmp_path)
    sealed = scratch_bin(root)
    assert shutil.which("npm", path=sealed) == str(root / "fixture-bin" / "npm")
    dropped = scratch_bin(root, drop_npm=True)
    assert shutil.which("npm", path=dropped) is None, "a real npm is reachable from the fixture"
    assert shutil.which("node", path=dropped) is None


# --------------------------------------------------------------------------- The four exit paths ---------------------------------------------------------------------------


def test_a_complete_build_prints_three_lines_and_exits_zero(tmp_path) -> None:
    root = fixture(tmp_path)
    old, new, old_calls, new_calls = run_both(root, FAKE_NPM_MAKE_INDEX=str(root / port.INDEX_HTML))
    assert old.returncode == 0, old.stderr
    assert old.stdout == ""
    assert old.stderr == (
        "→ Building json (template catalog)...\n"
        "✓ json build completed\n"
        "✓ json build complete: packages/json/dist/\n"
    )
    assert old_calls == "CALL npm\trun\tbuild:json\n"
    _agree(old, new, "success", old_calls, new_calls)


def test_a_missing_dist_directory_refuses_in_the_twins_own_words(tmp_path) -> None:
    root = fixture(tmp_path)
    old, new, old_calls, new_calls = run_both(root)
    assert old.returncode == 1
    assert old.stderr.endswith("✗ %s\n" % port.NO_DIST_MESSAGE), old.stderr
    _agree(old, new, "no-dist", old_calls, new_calls)


def test_a_dist_without_an_index_refuses_on_the_file(tmp_path) -> None:
    root = fixture(tmp_path)
    old, new, old_calls, new_calls = run_both(root, FAKE_NPM_MAKE_DIST=str(root / port.DIST_DIR))
    assert old.returncode == 1
    assert old.stderr.endswith("✗ %s\n" % port.NO_INDEX_MESSAGE), old.stderr
    _agree(old, new, "no-index", old_calls, new_calls)


def test_a_failing_npm_is_reported_as_a_failed_build(tmp_path) -> None:
    root = fixture(tmp_path)
    old, new, old_calls, new_calls = run_both(root, FAKE_NPM_RC="1")
    assert old.returncode == 1
    assert old.stderr == "→ Building json (template catalog)...\n✗ json build failed\n"
    _agree(old, new, "npm-fail", old_calls, new_calls)


# --------------------------------------------------------------------------- The shared defects, and the one thing that is this pair's alone ---------------------------------------------------------------------------


def test_defect_npms_exit_code_is_flattened_to_one(tmp_path) -> None:
    """npm exiting 3 or 137 both become a flat 1, as in `build-www.sh`."""
    for npm_rc in ("3", "137"):
        root = fixture(tmp_path / npm_rc)
        old, new, old_calls, new_calls = run_both(root, FAKE_NPM_RC=npm_rc)
        assert old.returncode == 1, "npm rc %s leaked through as %s" % (npm_rc, old.returncode)
        _agree(old, new, "flattened " + npm_rc, old_calls, new_calls)


def test_defect_the_green_tick_precedes_every_verification(tmp_path) -> None:
    """`✓ json build completed` is printed on npm's exit code alone."""
    root = fixture(tmp_path)
    old, new, old_calls, new_calls = run_both(root)
    lines = old.stderr.splitlines()
    assert lines[1] == "✓ json build completed"
    assert lines[2].startswith("✗ ")
    _agree(old, new, "tick-before-check", old_calls, new_calls)


def test_a_missing_npm_reads_as_a_failed_build_with_bashs_line_above_it(tmp_path) -> None:
    root = fixture(tmp_path)
    old, new, old_calls, new_calls = run_both(root, drop_npm=True)
    assert old.returncode == 1
    assert _mask(old.stderr) == (
        "→ Building json (template catalog)...\n"
        "<SELF>: line %d: npm: command not found\n"
        "✗ json build failed\n" % port.NPM_LINE
    ), old.stderr
    assert old_calls == ""
    _agree(old, new, "npm-absent", old_calls, new_calls)


def test_the_two_twins_say_different_things_about_the_same_failure(tmp_path) -> None:
    """THE PAIR ASSERTION. `build-json.sh:26-34` hand-rolls what `build-www.sh:26-27` delegates to `common.sh`, so a build that produced no `dist/` reports one of two unrelated sentences depending on which site it was. Both bash twins are driven here, in one fixture, so the disagreement is recorded rather than inferred from reading.

    The hand-rolled half is the better one: it names the site, which is exactly what `build-www.sh`'s dropped label argument was trying and failing to do.
    """
    root = fixture(tmp_path)
    json_side, _ = _run(root, "old")
    www_side, _ = _run(root, "old", script=WWW_TWIN_REL)
    assert json_side.returncode == www_side.returncode == 1
    assert json_side.stderr.endswith("✗ json dist directory not created\n")
    assert www_side.stderr.endswith("✗ Required directory 'packages/www/dist' does not exist\n")
    assert "json" not in www_side.stderr.splitlines()[-1]
    assert "www build output" not in www_side.stderr


# --------------------------------------------------------------------------- The `cd`, the stream discipline, and the real tree ---------------------------------------------------------------------------


def test_both_sides_cd_to_the_repo_root_whatever_the_caller_did(tmp_path) -> None:
    """Driven from a directory holding a DECOY `packages/json/dist/index.html`: a side reading paths relative to the caller would find it and exit 0.
    """
    root = fixture(tmp_path)
    decoy = tmp_path / "elsewhere"
    (decoy / "packages" / "json" / "dist").mkdir(parents=True)
    (decoy / "packages" / "json" / "dist" / "index.html").write_text("decoy", encoding="utf-8")
    old, new, old_calls, new_calls = run_both(root, cwd=str(decoy))
    assert old.returncode == 1, "the decoy was picked up: the twin did not cd"
    assert old.stderr.endswith("✗ %s\n" % port.NO_DIST_MESSAGE)
    _agree(old, new, "cd", old_calls, new_calls)


def test_npms_own_two_streams_are_inherited_unmerged(tmp_path) -> None:
    root = fixture(tmp_path)
    old, new, old_calls, new_calls = run_both(
        root,
        FAKE_NPM_STDOUT="vite: 12 modules transformed",
        FAKE_NPM_STDERR="vite: warning: empty chunk",
        FAKE_NPM_MAKE_INDEX=str(root / port.INDEX_HTML),
    )
    assert old.returncode == 0, old.stderr
    assert old.stdout == "vite: 12 modules transformed\n"
    assert "vite: warning: empty chunk\n" in old.stderr
    _agree(old, new, "streams", old_calls, new_calls)


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


# --------------------------------------------------------------------------- The control: this differential can actually fail ---------------------------------------------------------------------------


def test_a_planted_defect_is_caught(tmp_path) -> None:
    """A gate that has never been seen to fail is not a gate.

    The plant swaps `is_dir()` for `exists()` on the dist check, which is what a reader "simplifying" the port would reach for. It is invisible on every other case in this file and visible on exactly one: a `packages/json/dist` that is a FILE rather than a directory, which `[[ ! -d ]]` rejects and `exists()` accepts.
    """
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")
    planted = source.replace(
        "if not pathlib.Path(DIST_DIR).is_dir():",
        "if not pathlib.Path(DIST_DIR).exists():",
    )
    assert planted != source, "the plant site moved; this control is not planting anything"
    root = fixture(tmp_path, port_source=planted)
    (root / "packages" / "json").mkdir(parents=True)
    (root / "packages" / "json" / "dist").write_text("not a directory", encoding="utf-8")
    old, new, _old_calls, _new_calls = run_both(root)
    assert old.returncode == 1, old.stderr
    assert old.stderr.endswith("✗ json dist directory not created\n")
    assert new.stderr.endswith("✗ json index.html not found in dist\n")
    assert _mask(new.stderr) != _mask(old.stderr), "the plant did not diverge"
