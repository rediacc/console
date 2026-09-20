"""`rediacc_ci.quality.gate_id_convention` against the real lock and package.json.

WHAT IS WORTH TESTING HERE. The shadow ledger `.ci/shadow/w7p2-gate-id-convention.observations.jsonl` drove the whole gate over five distinct trees: a direct gates/ script under the wrong id, the 2026-08-08 alias shape, a missing lock, a missing corpus directory, and a reader seeing less than the corpus. That licensed the port at K=5 and the bash twin
`.ci/scripts/quality/check-gate-id-convention.sh` was retired in W7 P5.

THE TWIN CARRIED THIS GATE'S ENTIRE LOGIC AS PYTHON INSIDE A HEREDOC, so while both copies existed the cases here extracted that heredoc and ran it as a subprocess over the same inputs, line for line against the port. There is one copy now, so those comparison cases were retired with the file they read; what remains is the pair that drives the port against the REAL lock and the
REAL package.json, which is where a narrowing would show up, plus the gate's own controls.

The alias resolver is driven directly on the shapes the header argues about:
the one-hop unwind that must resolve, the `ci: { test: ... }` mention that must
NOT, and the two-hop chain the #557 review accepted as out of scope.
"""

import json
import pathlib

from rediacc_ci import paths
from rediacc_ci.quality import gate_id_convention as gi


def test_the_planted_control_entry_still_fires_against_the_real_lock(
    tmp_path: pathlib.Path,
) -> None:
    """CONTROL 1's plant, run against the REAL lock and the REAL package.json.

    This is the control the gate itself runs on every invocation; asserting it here means a change to either real file that made the plant stop firing is a test failure rather than a gate that quietly cannot detect its own defect.
    """
    root = paths.repo_root()
    entries = json.loads((root / gi.LOCK_REL).read_text(encoding="utf-8"))
    entries.append(gi.PLANTED_ENTRY)
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps(entries), encoding="utf-8")

    manifest = json.loads((root / gi.PKG_REL).read_text(encoding="utf-8"))
    manifest.setdefault("scripts", {})[gi.PLANTED_ID] = gi.PLANTED_SCRIPT
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps(manifest), encoding="utf-8")

    out, _err = gi.evaluate(str(lock), str(pkg), str(root / gi.GATES_DIR_REL))
    assert any(line.startswith("CONVENTION:") for line in out), out[:3]


def test_the_corpus_floor_fires_on_a_five_entry_lock(tmp_path: pathlib.Path) -> None:
    """CONTROL 2, against the real lock truncated the way the gate truncates it."""
    root = paths.repo_root()
    short = json.loads((root / gi.LOCK_REL).read_text(encoding="utf-8"))[:5]
    lock = tmp_path / "short.json"
    lock.write_text(json.dumps(short), encoding="utf-8")
    out, _err = gi.evaluate(str(lock), str(root / gi.PKG_REL), str(root / gi.GATES_DIR_REL))
    assert any(line.startswith("FLOOR:") for line in out), out


def test_selftest_runs_and_meets_its_floor() -> None:
    """The gate's own both-direction controls, over locks written by construction."""
    assert gi.selftest() == 0
