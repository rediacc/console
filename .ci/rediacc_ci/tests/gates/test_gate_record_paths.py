"""`check:ci-record-paths`, driven as a process against the real tree (agent/plans/PLAN-prepush-full-cpu.md PF23, PF9).

WHAT THIS ADDS TO THE GATE'S OWN `--selftest`. Those controls plant into scratch files and call the pure functions. These cases run the entry point against the REAL gate set and the REAL policies, and plant only into COPIES of the policy and the gate lock (`--policy`, `--lock`, `--widths`), never into the shared tree:
  * the plan's named control: a gate leaf citing agent/reviews/ is reported as an undeclared reader, here through a real gates.lock.json;
  * a real reader dropped from the policy is reported, by name;
  * a real listed width dropped from fixed-widths.json is reported, by file;
  * the guard that admits an advance and this gate read the record globs and the policy identically.
"""

import importlib.util
import json
import os
import subprocess
import sys

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

ROOT = paths.repo_root()
GATE = paths.from_root(".ci", "scripts", "quality", "check_record_paths.py")
POLICY = paths.from_root(".ci", "policy", "record-paths.json")
WIDTHS = paths.from_root(".ci", "policy", "fixed-widths.json")
LOCK = paths.from_root("scripts", "ci-runner", "gates.lock.json")
HOOKS = paths.from_root(".claude")


def _gate(*args):
    return harness.run([sys.executable, str(GATE), *args], cwd=ROOT, timeout=600)


def test_the_selftest_passes_and_is_not_vacuous():
    result = _gate("--selftest")
    assert result.rc == 0, harness.render_output(result)
    count = int(result.out.strip().split()[0])
    assert count >= 40, "only %d selftest control(s) ran:\n%s" % (count, result.out)


def test_the_real_record_policy_matches_the_derivation():
    result = _gate("--records-only")
    assert result.rc == 0, harness.render_output(result)
    line = next(ln for ln in result.out.splitlines() if ln.startswith("record-paths: OK"))
    # The shape, not just the verdict: a derivation that stopped seeing the tree would collapse these numbers.
    scanned = int(line.split(" gate(s) scanned")[0].rsplit(" ", 1)[-1])
    declared = int(line.split(" reader declaration(s)")[0].rsplit(" ", 1)[-1])
    assert scanned >= 200, line
    assert declared >= 10, line


def test_a_planted_leaf_citing_agent_reviews_is_an_undeclared_reader(tmp_path):
    """The plan's control, through the real lock: one more gate whose only leaf cites agent/reviews/."""
    leaf = tmp_path / "check_planted_reader.py"
    leaf.write_text('RECORDS = "agent/reviews/"\n', encoding="utf-8")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    lock.append({"id": "check:planted-reader", "run": "x", "gate": True, "leaves": [str(leaf)]})
    planted = tmp_path / "gates.lock.json"
    planted.write_text(json.dumps(lock), encoding="utf-8")
    result = _gate("--records-only", "--lock", str(planted))
    assert result.rc == 1, harness.render_output(result)
    assert "UNDECLARED READER check:planted-reader reads agent/reviews/**" in result.err, result.err
    # MIRROR: the same leaf citing nothing under agent/ is no finding, so the red above is the citation's.
    leaf.write_text('RECORDS = "docs/"\n', encoding="utf-8")
    clean = _gate("--records-only", "--lock", str(planted))
    assert clean.rc == 0, harness.render_output(clean)


def test_a_real_reader_dropped_from_the_policy_is_reported(tmp_path):
    doc = json.loads(POLICY.read_text(encoding="utf-8"))
    reviews = next(r for r in doc["records"] if r["glob"] == "agent/reviews/**")
    before = len(reviews["readers"])
    reviews["readers"] = [r for r in reviews["readers"] if r["id"] != "check:ci-prose-style"]
    assert len(reviews["readers"]) == before - 1, (
        "the control's subject is no longer a declared reader"
    )
    copy = tmp_path / "record-paths.json"
    copy.write_text(json.dumps(doc), encoding="utf-8")
    result = _gate("--records-only", "--policy", str(copy))
    assert result.rc == 1, harness.render_output(result)
    assert "UNDECLARED READER check:ci-prose-style reads agent/reviews/**" in result.err


def test_a_real_listed_width_dropped_is_reported(tmp_path):
    doc = json.loads(WIDTHS.read_text(encoding="utf-8"))
    before = len(doc["widths"])
    doc["widths"] = [w for w in doc["widths"] if w["file"] != ".ci/rediacc_ci/security/audit.py"]
    assert len(doc["widths"]) == before - 1, "the control's subject is no longer a listed width"
    copy = tmp_path / "fixed-widths.json"
    copy.write_text(json.dumps(doc), encoding="utf-8")
    result = _gate("--widths-only", "--widths", str(copy))
    assert result.rc == 1, harness.render_output(result)
    assert "UNLISTED WIDTH .ci/rediacc_ci/security/audit.py:" in result.err, result.err


GLOB_CORPUS = [
    ("agent/reviews/**", "agent/reviews/1004-2/clean.jsonl"),
    ("agent/reviews/**", "agent/reviews/x.md"),
    ("agent/reviews/**", "agent/reviewsx/a.md"),
    ("agent/reviews/**", "agent/plans/a.md"),
    ("agent/worklist/*.jsonl", "agent/worklist/d778be9d.jsonl"),
    ("agent/worklist/*.jsonl", "agent/worklist/sub/d.jsonl"),
    ("agent/worklist/*.jsonl", "agent/worklist/epics.jsonl"),
    ("agent/reggate/*.jsonl", "agent/reggate/1004-2.shapedup-wide.jsonl"),
    ("**/x.md", "x.md"),
    ("**/x.md", "a/b/x.md"),
    ("a.b/*", "aXb/c"),
]

PARITY_CHILD = """
import json, sys
from rediacc_hooks.guards import block_unverified_push as G
corpus = json.loads(sys.argv[1])
policy = json.loads(open(sys.argv[2], encoding="utf-8").read())
records, error = G.parse_record_policy(policy)
print(json.dumps({
    "matches": [bool(G.record_glob_re(g).match(p)) for g, p in corpus],
    "error": error,
    "records": [{"glob": r["glob"], "except": r["except"], "readers": r["readers"]} for r in records],
}))
"""


def test_the_guard_reads_globs_and_the_policy_exactly_as_this_gate_does(monkeypatch):
    """block_unverified_push cannot import rediacc_ci and this gate should not import a hook, so the two matchers are copies; this pins them equal, and pins the guard's reading of the REAL policy to this gate's."""
    proc = subprocess.run(
        [sys.executable, "-c", PARITY_CHILD, json.dumps(GLOB_CORPUS), str(POLICY)],
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ, PYTHONPATH=str(HOOKS)),
    )
    assert proc.returncode == 0, proc.stderr
    guard = json.loads(proc.stdout)
    # Loaded BY FILE, not through a sys.path hop (test_canonical_sys_path_hop.py freezes those). Its `import _cipath` only puts `.ci` on sys.path, which pytest already has, so a stub scoped to this test stands in for it.
    monkeypatch.setitem(sys.modules, "_cipath", type(sys)("_cipath"))
    spec = importlib.util.spec_from_file_location("check_record_paths", GATE)
    assert spec is not None
    assert spec.loader is not None
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    mine = [bool(gate.glob_re(g).match(p)) for g, p in GLOB_CORPUS]
    assert guard["matches"] == mine, list(zip(GLOB_CORPUS, guard["matches"], mine, strict=True))
    assert any(mine), "the corpus matched nothing, so agreement proves nothing"
    assert not all(mine), "the corpus matched everything, so agreement proves nothing"
    assert guard["error"] is None, guard["error"]
    records = gate.parse_policy(json.loads(POLICY.read_text(encoding="utf-8")))
    assert [
        {"glob": r["glob"], "except": r["exclude"], "readers": sorted(r["readers"])}
        for r in records
    ] == guard["records"]
    assert len(records) == len(guard["records"]) >= 3
