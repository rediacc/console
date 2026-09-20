"""Differential: `rediacc_ci.build.build_www` against its twin `.ci/scripts/build/build-www.sh`.

NEITHER SIDE TAKES A ROOT OVERRIDE, so both are COPIED into a throwaway fixture root and run from there: the twin resolves the root from `common.sh`'s
`${BASH_SOURCE[0]}` and the port from `__file__` (deliberately NOT
`paths.repo_root()`, see the port's docstring). Running in this checkout would also mean the real `packages/www/dist` decides the branch, which is the shape of green that proves only that a directory existed.

`npm` IS NEVER REAL, and the PATH is REPLACED rather than prepended. That is not a formality here: `npm run build:www` in this checkout is an Astro build of the marketing site, several minutes and several gigabytes, and a scratch PATH with the caller's own appended still resolves the real binary -- `test_the_scratch_path_cannot_reach_a_real_npm` asserts it cannot.

`rediacc_ci` IS VENDORED INTO THE FIXTURE rather than reached through an absolute `PYTHONPATH`. Two reasons: it proves the port needs only the six modules listed in `VENDORED`, and `scripts/lib/shadow-gate.ts --record` refuses any command string naming an absolute path outside the recorded tree, so the
K=5 ledger needs this shape anyway.

`$0` IS MASKED TO `<SELF>` and nothing else is. bash names the script it was invoked with in its `command not found` line and `sys.argv[0]` ends `.py`; two files cannot share one name. Everything else is compared byte-for-byte on both streams SEPARATELY, plus the fake's call log.

K=5 LEDGER: `.ci/shadow/w7p6-build-www.observations.jsonl`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.build import build_www as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()

TWIN_REL = ".ci/scripts/build/build-www.sh"
PORT_REL = ".ci/rediacc_ci/build/build_www.py"
COMMON_REL = ".ci/scripts/lib/common.sh"

# Everything the port imports, transitively, and nothing else. A seventh entry appearing here means the port grew a dependency, which is worth noticing.
VENDORED = (
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/log.py",
    ".ci/rediacc_ci/paths.py",
    ".ci/rediacc_ci/core/__init__.py",
    ".ci/rediacc_ci/core/common.py",
    ".ci/rediacc_ci/build/__init__.py",
)

BASH = shutil.which("bash") or "/bin/bash"

# `dirname` for `get_repo_root` (common.sh:207), `uname` because SOURCING
# common.sh runs `CI_OS="$(detect_os)"` and `CI_ARCH="$(detect_arch)"` at
# :509-510 -- two forks on every source, whether or not the caller wants them -- and `mkdir` for the fake npm's own bookkeeping. Anything not listed is ABSENT.
#
# THE `uname` FORKS ARE A NAMED DIVERGENCE, not a reproduced one: the port imports a module rather than sourcing a library, so it never runs them. It is invisible in output on any machine that HAS uname, and on one that does not the twin prints two `common.sh: line 64: uname: command not found` lines that the port has no reason to forge. The fixture therefore supplies uname.
PATH_MINIMUM = ("dirname", "uname", "mkdir")

# The recording fake. It writes its own argv to the call log with a distinct
# prefix -- the same prefix the K=5 ledger scopes `--finding-re` to, because
# `shadow-gate.ts` classifies every `→ `/`✓ ` line as CHATTER before any message-text regex is consulted, and this script reports ONLY through those two glyphs on its success path.
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


def fixture(tmp_path: pathlib.Path, *, port_source: str | None = None) -> pathlib.Path:
    """A throwaway tree holding both implementations and their libraries."""
    root = tmp_path / "repo"
    for rel in (TWIN_REL, PORT_REL, COMMON_REL, *VENDORED):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / TWIN_REL, root / TWIN_REL)
    shutil.copy2(ROOT / COMMON_REL, root / COMMON_REL)
    for rel in VENDORED:
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


def _run(root: pathlib.Path, side: str, *, drop_npm: bool = False, cwd: str | None = None, **extra):
    call_log = root / ("%s-calls.log" % side)
    call_log.write_text("", encoding="utf-8")
    env = {
        # REPLACED, never prepended. See the module docstring.
        "PATH": scratch_bin(root, drop_npm=drop_npm),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(root / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
    }
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
    """Both sides from the SAME starting state.

    `packages/www` is snapshotted and restored between them, because the fake npm can CREATE the dist directory: without the reset the twin's run would leave it behind and the port would take a different branch and "agree" for the wrong reason.
    """
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


# `$0` as bash prints it: the ABSOLUTE path the script was invoked with, whose fixture-root prefix is also per-test. Both are collapsed to `<SELF>`, and nothing else is masked.
SELF_RE = re.compile(r"\S*(?:%s|%s)" % (re.escape(TWIN_REL), re.escape(PORT_REL)))


def _mask(text: str) -> str:
    """`$0`, the one thing that cannot agree between the two sides."""
    return SELF_RE.sub("<SELF>", text)


def _agree(old, new, label: str, old_calls: str = "", new_calls: str = "") -> None:
    """Both streams SEPARATELY, the exit code, and the call log. Never `2>&1`."""
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


# --------------------------------------------------------------------------- The control on the control: the scratch PATH really is sealed ---------------------------------------------------------------------------


def test_the_scratch_path_cannot_reach_a_real_npm(tmp_path) -> None:
    """A PREPENDED PATH would still resolve the real npm, and the real `npm run build:www` is a multi-minute Astro build of this repository. So the fixture REPLACES PATH, and this asserts the replacement holds in both directions: the fake is reachable, and dropping it leaves nothing behind it."""
    root = fixture(tmp_path)
    sealed = scratch_bin(root)
    assert shutil.which("npm", path=sealed) == str(root / "fixture-bin" / "npm")
    dropped = scratch_bin(root, drop_npm=True)
    assert shutil.which("npm", path=dropped) is None, "a real npm is reachable from the fixture"
    assert shutil.which("node", path=dropped) is None
    assert shutil.which("docker", path=dropped) is None


# --------------------------------------------------------------------------- The four exit paths ---------------------------------------------------------------------------


def test_a_complete_build_prints_three_lines_and_exits_zero(tmp_path) -> None:
    root = fixture(tmp_path)
    old, new, old_calls, new_calls = run_both(root, FAKE_NPM_MAKE_INDEX=str(root / port.INDEX_HTML))
    assert old.returncode == 0, old.stderr
    assert old.stdout == ""
    assert old.stderr == (
        "→ Building www (Astro)...\n"
        "✓ www build completed\n"
        "✓ www build complete: packages/www/dist/\n"
    )
    assert old_calls == "CALL npm\trun\tbuild:www\n"
    _agree(old, new, "success", old_calls, new_calls)


def test_a_missing_dist_directory_refuses_with_the_generic_sentence(tmp_path) -> None:
    """DEFECT 1, driven. `require_dir "packages/www/dist" "www build output"` passes a label that `common.sh:161-167` reads `$1` only, so the label never reaches a terminal and the operator is told nothing about WHICH build produced nothing. The assertion is on the label's ABSENCE, so it fires the day the twin is repaired rather than quietly agreeing with a fixed twin."""
    root = fixture(tmp_path)
    old, new, old_calls, new_calls = run_both(root)
    assert old.returncode == 1
    assert old.stderr.endswith("✗ Required directory 'packages/www/dist' does not exist\n"), (
        old.stderr
    )
    assert port.DIST_DIR_LABEL not in old.stderr
    assert port.DIST_DIR_LABEL not in old.stdout
    _agree(old, new, "no-dist", old_calls, new_calls)


def test_a_dist_without_an_index_refuses_on_the_file(tmp_path) -> None:
    """The second `require_*`, and its label is dropped the same way."""
    root = fixture(tmp_path)
    old, new, old_calls, new_calls = run_both(root, FAKE_NPM_MAKE_DIST=str(root / port.DIST_DIR))
    assert old.returncode == 1
    assert old.stderr.endswith("✗ Required file 'packages/www/dist/index.html' does not exist\n"), (
        old.stderr
    )
    assert port.INDEX_HTML_LABEL not in old.stderr
    _agree(old, new, "no-index", old_calls, new_calls)


def test_a_failing_npm_is_reported_as_a_failed_build(tmp_path) -> None:
    root = fixture(tmp_path)
    old, new, old_calls, new_calls = run_both(root, FAKE_NPM_RC="1")
    assert old.returncode == 1
    assert old.stderr == ("→ Building www (Astro)...\n✗ www build failed\n"), old.stderr
    _agree(old, new, "npm-fail", old_calls, new_calls)


# --------------------------------------------------------------------------- The defects, each with its own case ---------------------------------------------------------------------------


def test_defect_npms_exit_code_is_flattened_to_one(tmp_path) -> None:
    """DEFECT 2. npm exiting 3 -- or 137, an OOM kill -- makes this script exit 1, so the workflow step cannot tell an infrastructure failure from a compilation failure. `buildx-push-web.sh` one file over does the opposite and lets docker's status through, which is what makes this a defect rather than a house rule. A port that "fixed" it would diverge here."""
    for npm_rc in ("3", "137"):
        root = fixture(tmp_path / npm_rc)
        old, new, old_calls, new_calls = run_both(root, FAKE_NPM_RC=npm_rc)
        assert old.returncode == 1, "npm rc %s leaked through as %s" % (npm_rc, old.returncode)
        _agree(old, new, "flattened " + npm_rc, old_calls, new_calls)


def test_defect_the_green_tick_precedes_every_verification(tmp_path) -> None:
    """DEFECT 3. `✓ www build completed` is printed on npm's exit code alone, so a run that produced an empty dist prints a success line and THEN refuses. Pinned by ORDER, which is the only way it is visible."""
    root = fixture(tmp_path)
    old, new, old_calls, new_calls = run_both(root)
    lines = old.stderr.splitlines()
    assert lines[1] == "✓ www build completed"
    assert lines[2].startswith("✗ ")
    _agree(old, new, "tick-before-check", old_calls, new_calls)


def test_a_missing_npm_reads_as_a_failed_build_with_bashs_line_above_it(tmp_path) -> None:
    """The shell's own diagnostic is the ONLY evidence the tool was absent, so the port forges it rather than tracebacking. `$0` differs and is masked; the line number, the binary name and the reason are compared exactly."""
    root = fixture(tmp_path)
    old, new, old_calls, new_calls = run_both(root, drop_npm=True)
    assert old.returncode == 1
    assert _mask(old.stderr) == (
        "→ Building www (Astro)...\n"
        "<SELF>: line %d: npm: command not found\n"
        "✗ www build failed\n" % port.NPM_LINE
    ), old.stderr
    assert old_calls == ""
    _agree(old, new, "npm-absent", old_calls, new_calls)


# --------------------------------------------------------------------------- The `cd`, the stream discipline, and the real tree ---------------------------------------------------------------------------


def test_both_sides_cd_to_the_repo_root_whatever_the_caller_did(tmp_path) -> None:
    """The `cd` is observable: every later path is relative, so a side that skipped it would refuse with the same sentence for a completely different reason. Driven from a directory that is NOT the fixture root and that holds a decoy `packages/www/dist/index.html` -- a side reading paths relative to the CALLER would find the decoy and exit 0."""
    root = fixture(tmp_path)
    decoy = tmp_path / "elsewhere"
    (decoy / "packages" / "www" / "dist").mkdir(parents=True)
    (decoy / "packages" / "www" / "dist" / "index.html").write_text("decoy", encoding="utf-8")
    old, new, old_calls, new_calls = run_both(root, cwd=str(decoy))
    assert old.returncode == 1, "the decoy was picked up: the twin did not cd"
    assert "Required directory 'packages/www/dist' does not exist" in old.stderr
    _agree(old, new, "cd", old_calls, new_calls)


def test_npms_own_two_streams_are_inherited_unmerged(tmp_path) -> None:
    """A build log is the caller's, not this script's. The stream a line arrives on is part of the contract -- the 2026-09-06 emit-advisory incident was a stream SWAP -- so the fake writes to both and each is compared separately."""
    root = fixture(tmp_path)
    old, new, old_calls, new_calls = run_both(
        root,
        FAKE_NPM_STDOUT="astro: building 42 pages",
        FAKE_NPM_STDERR="astro: warning: unused import",
        FAKE_NPM_MAKE_INDEX=str(root / port.INDEX_HTML),
    )
    assert old.returncode == 0, old.stderr
    assert old.stdout == "astro: building 42 pages\n"
    assert "astro: warning: unused import\n" in old.stderr
    _agree(old, new, "streams", old_calls, new_calls)


def test_the_port_and_the_twin_agree_about_the_repo_root_in_this_checkout() -> None:
    """The one assertion made against the REAL tree rather than a fixture. Both answers come from a file's own location three levels up, but from DIFFERENT files, so a directory move that touched one and not the other would go unnoticed until a build ran in the wrong place."""
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

    The plant is the smallest realistic one: the two output checks swapped, so the port asks for the FILE before the DIRECTORY. Both orders exit 1 with an identical call log on a tree with neither, and only the message text tells them apart -- which is exactly the assertion a comparator that only checked exit codes would miss.
    """
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")
    planted = source.replace(
        "        common.require_dir(DIST_DIR)\n        common.require_file(INDEX_HTML)\n",
        "        common.require_file(INDEX_HTML)\n        common.require_dir(DIST_DIR)\n",
    )
    assert planted != source, "the plant site moved; this control is not planting anything"
    root = fixture(tmp_path, port_source=planted)
    old, new, _old_calls, _new_calls = run_both(root)
    assert old.returncode == new.returncode == 1
    assert "Required directory" in old.stderr
    assert "Required file" in new.stderr
    assert _mask(new.stderr) != _mask(old.stderr), "the plant did not diverge"
