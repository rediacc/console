"""GLOBAL_INPUTS must reach the ROOT lockfiles, in both readers of the glob grammar.

`**/package-lock.json` needs a `/` before the name, so it never matches `package-lock.json` at the root. A root dependency bump then moved no gate's input hash and receipt carry could reuse a pass across it. The TS list is driven for real (`input-hash.ts` `GLOBAL_INPUTS` and `matchGlob`), and the push guard's Python twin `v2_match_glob` must agree on every case.
"""

import json
import shutil
import subprocess

import pytest
from rediacc_hooks.guards import block_unverified_push as G

from rediacc_ci import paths

ROOT = paths.repo_root()

needs_node = pytest.mark.skipif(
    shutil.which("npx") is None or shutil.which("node") is None,
    reason="npx/node not installed: the TS side of the parity cannot run",
)

# (path, reached by some GLOBAL_INPUTS entry). The last row is the control.
CASES = [
    ("package-lock.json", True),
    ("uv.lock", True),
    ("packages/cli/package-lock.json", True),
    ("a/b/uv.lock", True),
    ("src/unrelated.ts", False),
    ("package-lock.json.bak", False),
]


def _ts_globals():
    script = "import { GLOBAL_INPUTS } from './scripts/ci-runner/input-hash.ts';process.stdout.write(JSON.stringify(GLOBAL_INPUTS));"
    r = subprocess.run(
        ["npx", "tsx", "-e", script], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert r.returncode == 0, f"tsx rc={r.returncode}\nstderr:\n{r.stderr}"
    globs = json.loads(r.stdout)
    assert globs, "GLOBAL_INPUTS is empty: the test is not seeing the list"
    return globs


def test_root_glob_alone_misses_root_lockfile_python():
    """Pins the grammar this fix works around: `**/` does not match at the root."""
    assert G.v2_match_glob("**/package-lock.json", "package-lock.json") is False


def test_ts_source_lists_the_bare_root_lockfiles_without_node():
    """Runs on a machine without node: the TS source still names both bare root entries, so the root-lockfile fix is pinned where the driven tests skip."""
    source = (ROOT / "scripts" / "ci-runner" / "input-hash.ts").read_text(encoding="utf-8")
    block = source.split("export const GLOBAL_INPUTS", 1)[1].split("];", 1)[0]
    entries = [
        line.strip().strip(",").strip("'") for line in block.splitlines()[1:] if line.strip()
    ]
    assert "package-lock.json" in entries
    assert "uv.lock" in entries
    # Control: the block parse also reads the `**/` form beside the bare ones, so the two bare entries above came from real lines and not from a parse that returns everything.
    assert "**/package-lock.json" in entries


@needs_node
@pytest.mark.parametrize(("path", "expected"), CASES)
def test_global_inputs_reach_python(path, expected):
    globs = _ts_globals()
    assert any(G.v2_match_glob(g, path) for g in globs) is expected, (path, globs)


@needs_node
def test_global_inputs_ts_equals_python():
    globs = _ts_globals()
    script = (
        "import { matchGlob } from './scripts/ci-runner/input-hash.ts';"
        f"const globs = {json.dumps(globs)}; const paths = {json.dumps([p for p, _ in CASES])};"
        "process.stdout.write(JSON.stringify(paths.map((p) => globs.some((g) => matchGlob(g, p)))));"
    )
    r = subprocess.run(
        ["npx", "tsx", "-e", script], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert r.returncode == 0, f"tsx rc={r.returncode}\nstderr:\n{r.stderr}"
    assert json.loads(r.stdout) == [e for _, e in CASES]
