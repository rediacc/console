"""Parity of the carry-exempt.json reader: input-hash.ts `exemptRowsOf` and the guard's `_exempt_ids`.

PLAN-ciquick-cpu A4 gives each exempt row an optional `kind` (clock|history|network|cache). The runner and the push guard read one file, so they must accept and refuse exactly the same documents: a row the runner reads as exempt while the guard refuses the file, or the reverse, turns a push verdict on which reader ran. The TS side is driven for real (`input-hash.ts --exempt-rows`), never mocked.
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

ROW = {"id": "check:x", "reason": "r"}
CASES = [
    ("no kind", {"schema": 1, "exempt": [ROW]}, True),
    *[("kind " + k, {"schema": 1, "exempt": [{**ROW, "kind": k}]}, True) for k in G.EXEMPT_KINDS],
    ("unknown kind", {"schema": 1, "exempt": [{**ROW, "kind": "weather"}]}, False),
    ("null kind", {"schema": 1, "exempt": [{**ROW, "kind": None}]}, False),
    ("numeric kind", {"schema": 1, "exempt": [{**ROW, "kind": 1}]}, False),
    ("schema 2", {"schema": 2, "exempt": [ROW]}, False),
    ("empty id", {"schema": 1, "exempt": [{"id": "", "reason": "r"}]}, False),
    ("no exempt list", {"schema": 1}, False),
]


def _ts(doc):
    r = subprocess.run(
        ["npx", "tsx", "scripts/ci-runner/input-hash.ts", "--exempt-rows"],
        cwd=ROOT,
        input=json.dumps(doc),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode in (0, 1), f"--exempt-rows rc={r.returncode}\nstderr:\n{r.stderr}"
    return set(json.loads(r.stdout)) if r.returncode == 0 else None


def _py(doc):
    try:
        return G._exempt_ids(doc)
    except ValueError:
        return None


@pytest.mark.parametrize(("name", "doc", "ok"), CASES, ids=[c[0] for c in CASES])
def test_python_reader_accepts_exactly_the_well_formed(name, doc, ok):
    got = _py(doc)
    assert (got is not None) == ok, f"{name}: python read {got!r}"


@needs_node
@pytest.mark.parametrize(("name", "doc", "ok"), CASES, ids=[c[0] for c in CASES])
def test_ts_reader_agrees_with_python(name, doc, ok):
    ts, py = _ts(doc), _py(doc)
    assert ts == py, f"{name}: ts read {ts!r}, python read {py!r}"
    assert (ts is not None) == ok, (
        f"{name}: both readers {'refused' if ts is None else 'accepted'} it"
    )


def test_kinds_are_one_list():
    """The two EXEMPT_KINDS spellings are the same list, read from the TS source rather than restated here."""
    src = (ROOT / "scripts/ci-runner/input-hash.ts").read_text(encoding="utf-8")
    line = next(ln for ln in src.splitlines() if ln.startswith("export const EXEMPT_KINDS"))
    ts_kinds = tuple(part.strip(" '") for part in line.split("[", 1)[1].split("]", 1)[0].split(","))
    assert ts_kinds == G.EXEMPT_KINDS


def test_live_policy_parses_under_both_shapes():
    """CONTROL: the tree's own carry-exempt.json is well-formed for the guard, so the cases above are not refusing everything."""
    doc = json.loads((ROOT / ".ci/policy/carry-exempt.json").read_text(encoding="utf-8"))
    assert len(G._exempt_ids(doc)) >= 1
