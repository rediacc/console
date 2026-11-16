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
    ("agent/reviews/**", "agent/reviews/main/clean.jsonl"),
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


# ---------------------------------------------------------------- code, not prose (the plan records, 2026-11-16)

PLAN_RECORD = "agent/plans/**/*.md"
#: The six records a plan commit touches: the plan files, the generated index of them, the box table, and the three plan ledgers.
PLAN_RECORDS = (
    PLAN_RECORD,
    "agent/INDEX.md",
    ".ci/config/plan-boxes.json",
    "agent/ledgers/plan-investigation.jsonl",
    "agent/ledgers/plan-box-progress.jsonl",
    "agent/ledgers/live-proof.jsonl",
)
#: THE MEASURED READER SET of those six records, derived on 2026-11-16 by the fixed derivation and classified by hand (the exemptions and their reasons are in the policy). This is what a plan-only commit re-runs instead of the lane. A gate joining or leaving it is a decision, so it is written down here as well as in the policy: the gate itself only proves the policy equals the derivation, and would stay green if both lost a reader together.
PLAN_READERS = frozenset(
    {
        "check:ci-account-env-retired",
        "check:ci-agent-hint-liveness",
        "check:ci-agent-session-archival",
        "check:ci-allowlist-key-matching",
        "check:ci-cli-contract",
        "check:ci-commit-citations",
        "check:ci-dead-python",
        "check:ci-decision-ids",
        "check:ci-doc-region-parity",
        "check:ci-durable-paths-tracked",
        "check:ci-gate-reachability-coverage",
        "check:ci-generated-artifacts",
        "check:ci-hint-corpus",
        "check:ci-i18n-cli-key-usage",
        "check:ci-i18n-value-types",
        "check:ci-inner-timeout-reachable",
        "check:ci-literal-sources",
        "check:ci-plan-bindings",
        "check:ci-plan-boxes",
        "check:ci-plan-citations",
        "check:ci-plan-deps",
        "check:ci-plan-folders",
        "check:ci-plan-housekeeping",
        "check:ci-plan-implementation",
        "check:ci-plan-live-proof",
        "check:ci-plan-record",
        "check:ci-portal-sitekey-guard",
        "check:ci-prose-style",
        "check:ci-retired-terms",
        "check:ci-review-resolutions",
        "check:ci-scope-mirrors",
        "check:ci-script-exec-bit",
        "check:ci-trap-registry",
        "check:ci-tree-shape",
        "check:ci-worklist-env-registry",
        "check:cli-examples",
    }
)
#: The gates whose subject is the plan files. Each must be derived for the plan glob itself, whatever else moves.
PLAN_FAMILY = frozenset(
    {
        "check:ci-plan-bindings",
        "check:ci-plan-boxes",
        "check:ci-plan-citations",
        "check:ci-plan-deps",
        "check:ci-plan-folders",
        "check:ci-plan-housekeeping",
        "check:ci-plan-implementation",
        "check:ci-plan-live-proof",
        "check:ci-plan-record",
        "check:ci-decision-ids",
        "check:ci-commit-citations",
        "check:cli-examples",
        "check:ci-prose-style",
        "check:ci-doc-region-parity",
        "check:ci-scope-mirrors",
        "check:ci-retired-terms",
        "check:ci-tree-shape",
        "check:ci-generated-artifacts",
        "check:ci-dead-python",
    }
)


def _load_gate(monkeypatch):
    """The gate module, loaded by file as the parity test above loads it."""
    monkeypatch.setitem(sys.modules, "_cipath", type(sys)("_cipath"))
    spec = importlib.util.spec_from_file_location("check_record_paths", GATE)
    assert spec is not None
    assert spec.loader is not None
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    return gate


def _reads_plans(gate, root, leaf_name, source):
    """Whether one scratch leaf holding `source` is derived as a reader of the plan record."""
    (root / leaf_name).write_text(source, encoding="utf-8")
    records = gate.parse_policy(
        {
            "version": 1,
            "records": [
                {
                    "glob": PLAN_RECORD,
                    "except": [],
                    "probes": ["agent/plans/PLAN-x.md"],
                    "readers": [],
                }
            ],
        }
    )
    gates = [{"id": "check:probe", "gate": True, "leaves": [leaf_name]}]
    return "check:probe" in gate.derive_readers(gates, records, root)[0][PLAN_RECORD]


def test_a_path_in_code_is_a_citation(monkeypatch, tmp_path):
    """The firing halves: a whole-literal path, a path joined from literal segments, and a template literal."""
    gate = _load_gate(monkeypatch)
    assert _reads_plans(gate, tmp_path, "opens.py", 'F = open("agent/plans/x.md")\n')
    assert _reads_plans(gate, tmp_path, "joins.py", 'D = ROOT / "agent" / "plans"\n')
    assert _reads_plans(gate, tmp_path, "tpl.ts", "const p = `${root}/agent/plans/${n}.md`;\n")


def test_a_path_in_prose_is_not_a_citation(monkeypatch, tmp_path):
    """The silent halves, each a firing source with the path moved into prose. Before the fix every one of these made its gate a reader, which is how 168 gates came to read the plan set."""
    gate = _load_gate(monkeypatch)
    # CONTROL FIRST: the instrument fires in this very tree, so a silence below is the rule's.
    assert _reads_plans(gate, tmp_path, "control.py", 'F = open("agent/plans/x.md")\n')
    docstring = '"""WHY (agent/plans/PLAN-x.md): like open("agent/plans/x.md")."""\nX = 1\n'
    assert not _reads_plans(gate, tmp_path, "docstring.py", docstring)
    comment = 'X = 1  # see "agent/plans/x.md"\n# "agent/plans/"\n'
    assert not _reads_plans(gate, tmp_path, "comment.py", comment)
    message = 'MSG = "the design is in agent/plans/PLAN-x.md (part 5)"\n'
    assert not _reads_plans(gate, tmp_path, "message.py", message)
    jsdoc = "/**\n * WHY: 'agent/plans/PLAN-x.md'.\n */\nexport const x = 1;\n"
    assert not _reads_plans(gate, tmp_path, "jsdoc.ts", jsdoc)


def test_an_exclusion_key_in_a_config_is_not_a_scope(monkeypatch, tmp_path):
    """.ci/config/pins.json lists `agent/**` under `literalExclude`; read as a scope it made eleven pin gates readers. The same glob under an inclusion key still counts."""
    gate = _load_gate(monkeypatch)
    cfg = tmp_path / ".cfg"
    cfg.mkdir()
    (cfg / "out.json").write_text('{"literalExclude": [{"glob": "agent/**"}]}', encoding="utf-8")
    (cfg / "in.json").write_text('{"literalInclude": [{"glob": "agent/**"}]}', encoding="utf-8")
    assert _reads_plans(gate, tmp_path, "includes.py", 'C = ".cfg/in.json"\n')
    assert not _reads_plans(gate, tmp_path, "excludes.py", 'C = ".cfg/out.json"\n')
    # The real file, so the rule is pinned to the case it was written for and not only to a fixture shaped like it.
    pins = json.loads(paths.from_root(".ci", "config", "pins.json").read_text(encoding="utf-8"))
    assert any(e.get("glob") == "agent/**" for e in pins["literalExclude"]), "pins.json moved"
    assert "agent/**" not in gate._json_globs({"literalExclude": pins["literalExclude"]})
    assert "agent/**" in gate._json_globs({"scope": pins["literalExclude"]})


def test_the_plan_records_have_exactly_the_measured_readers(monkeypatch):
    """The real tree: the derived reader set of the six plan records, less the exemptions the policy names, is PLAN_READERS exactly. Red before the fix, when the derivation flagged 168 gates for the plan glob alone."""
    gate = _load_gate(monkeypatch)
    doc = json.loads(POLICY.read_text(encoding="utf-8"))
    records = gate.parse_policy(doc)
    by_glob = {r["glob"]: r for r in records}
    assert set(PLAN_RECORDS) <= set(by_glob), sorted(set(PLAN_RECORDS) - set(by_glob))
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    derived, scanned, _read = gate.derive_readers(lock, records, ROOT)
    assert scanned >= 200, scanned
    readers = set()
    declared = set()
    for glob in PLAN_RECORDS:
        readers |= set(derived[glob]) - set(by_glob[glob]["notReaders"])
        declared |= set(by_glob[glob]["readers"])
    assert readers == PLAN_READERS, (sorted(readers - PLAN_READERS), sorted(PLAN_READERS - readers))
    assert declared == PLAN_READERS, sorted(declared ^ PLAN_READERS)
    missing = PLAN_FAMILY - set(derived[PLAN_RECORD])
    assert not missing, "plan gates the derivation no longer sees: %s" % sorted(missing)
    # check:ci-pytest re-runs the reader gates from its real-tree tests and costs about 1750 s. It is not derived, so it is not a reader and needs no exemption; if it ever is derived, that is a decision to take here, not a line to add quietly.
    assert all("check:ci-pytest" not in derived[glob] for glob in PLAN_RECORDS)


def test_the_plan_text_records_stay_under_review():
    """A plan and the index of plans advance a receipt and are still reviewed per commit (`"review": "keep"`, read by wl_review.skip_globs); the ledgers and the box table are records the reviewer skips."""
    doc = json.loads(POLICY.read_text(encoding="utf-8"))
    kept = {r["glob"] for r in doc["records"] if r.get("review") == "keep"}
    assert kept == {PLAN_RECORD, "agent/INDEX.md"}, sorted(kept)
    # Not a bare agent/plans/**: a non-.md file there (a .tsv inventory, a .patch attachment) is judged by check:ci-language-policy, which scans every tracked path, so it must void the receipt.
    globs = {r["glob"] for r in doc["records"]}
    assert "agent/plans/**" not in globs
    assert not any(g.endswith("STATE.md") for g in globs), "STATE.md is not a record path"
