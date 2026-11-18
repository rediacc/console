"""`check:ci-record-paths`: the `declared` tier and the files that are not scan code (agent/plans/PLAN-push-decoupling.md F1).

A gate whose lock entry declares `names: ['**']` lists every file name, so a new review or plan file changes its verdict, yet its leaves cite no record path and the four file tiers never saw it: about twenty such gates were not record readers. The declared tier reads each gate's own gates.lock.json entry. And scripts/ci-runner/manifest.ts and trace-ledger.ts hold OTHER gates' globs as data, so every gate importing the gate table used to read as a reader of the plan records, each answered by a hand-written notReader.

Every firing case below has a silent twin that differs in one thing, so a silence is the rule's and not a broken fixture's.
"""

from __future__ import annotations

import importlib.util
import json
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

ROOT = paths.repo_root()
GATE = paths.from_root(".ci", "scripts", "quality", "check_record_paths.py")
LOCK = paths.from_root("scripts", "ci-runner", "gates.lock.json")
MANIFEST = paths.from_root("scripts", "ci-runner", "manifest.ts")
REVIEWS = "agent/reviews/**"
WORKLIST = "agent/worklist/*.jsonl"
POLICY = {
    "version": 1,
    "records": [
        {
            "glob": REVIEWS,
            "except": [],
            "probes": ["agent/reviews/main/clean.jsonl", "agent/reviews/main/%s.md" % ("0" * 40)],
            "readers": [],
        },
        {
            "glob": WORKLIST,
            "except": ["agent/worklist/epics.jsonl"],
            "probes": ["agent/worklist/d778be9d.jsonl"],
            "readers": [],
        },
    ],
}
#: The seven gates whose only path to agent/worklist/*.jsonl was the gate table: each carried a notReader with a manifest.ts reason until F1 deleted it.
TABLE_IMPORTERS = (
    "check:ci-embed-asset-versions",
    "check:ci-gates-lock",
    "check:ci-gen-manifest",
    "check:ci-package-key-budget",
    "check:ci-pin-registry",
    "check:ci-selftest-reachability",
    "check:types:incremental",
)


@pytest.fixture
def gate(monkeypatch):
    """The gate module, loaded by file (its `import _cipath` only puts `.ci` on sys.path, which pytest already has)."""
    monkeypatch.setitem(sys.modules, "_cipath", type(sys)("_cipath"))
    spec = importlib.util.spec_from_file_location("check_record_paths", GATE)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _findings(gate, root, entry, policy=POLICY):
    """record_findings for one fixture gate whose only leaf cites nothing."""
    (root / "leaf.py").write_text('P = "docs/"\n', encoding="utf-8")
    probe = dict({"id": "check:probe", "gate": True, "leaves": ["leaf.py"]}, **entry)
    records = gate.parse_policy(policy)
    derived = gate.derive_readers([probe], records, root, {"check:probe": 3})[0]
    return derived, gate.record_findings(records, derived, {"check:probe"}, root)


def test_a_names_star_gate_with_no_cite_is_an_undeclared_reader(gate, tmp_path):
    derived, findings = _findings(gate, tmp_path, {"names": ["**"]})
    assert (
        derived[REVIEWS]["check:probe"] == "scripts/ci-runner/gates.lock.json:3 (declared) names **"
    )
    assert any("UNDECLARED READER check:probe reads %s" % REVIEWS in f for f in findings), findings
    assert any("UNDECLARED READER check:probe reads %s" % WORKLIST in f for f in findings), findings


def test_the_same_gate_with_a_narrowed_declaration_is_not(gate, tmp_path):
    derived, findings = _findings(gate, tmp_path, {"names": ["**/*.sh", ".github/**"]})
    assert derived == {REVIEWS: {}, WORKLIST: {}}
    assert findings == []


def test_a_paths_glob_reaches_only_the_records_whose_probes_it_matches(gate, tmp_path):
    derived, _ = _findings(gate, tmp_path, {"paths": ["agent/reviews/**", "docs/**"]})
    assert "check:probe" in derived[REVIEWS]
    assert derived[WORKLIST] == {}


@pytest.mark.parametrize(
    ("directory", "reaches"),
    [
        ("agent", True),
        ("agent/reviews", True),
        ("agent/reviews/main", True),
        ("", False),
        ("agent/plans", False),
        ("agent/reviewsx", False),
    ],
)
def test_a_listed_directory_reaches_a_record_from_its_parent_or_inside(
    gate, tmp_path, directory, reaches
):
    derived, _ = _findings(gate, tmp_path, {"lists": [directory]})
    assert ("check:probe" in derived[REVIEWS]) is reaches, (directory, derived)


def test_a_literal_record_is_listed_from_its_own_directory_only(gate):
    record = {"glob": ".ci/config/carried-reds.json"}
    assert gate.lists_reach(".ci/config", record)
    assert not gate.lists_reach(".ci", record)


def test_a_not_reader_cannot_overrule_a_declared_hit(gate, tmp_path):
    exempt = json.loads(json.dumps(POLICY))
    exempt["records"][0]["notReaders"] = [
        {"id": "check:probe", "reason": "it says it does not read"}
    ]
    _, findings = _findings(gate, tmp_path, {"names": ["**"]}, exempt)
    assert any("cannot overrule" in f for f in findings), findings
    # MIRROR: the same exemption over a narrowed declaration is a STALE one, not this finding.
    _, findings = _findings(gate, tmp_path, {"names": ["**/*.sh"]}, exempt)
    assert not any("cannot overrule" in f for f in findings), findings
    assert any("no longer flags it" in f for f in findings), findings


def test_a_record_glob_only_in_the_gate_table_or_trace_ledger_makes_no_reader(gate, tmp_path):
    table = "export const M = [{ id: 'x', paths: ['agent/reviews/**'] }];\n"
    runner = tmp_path / "scripts" / "ci-runner"
    runner.mkdir(parents=True)
    for name in ("manifest.ts", "trace-ledger.ts", "other.ts"):
        (runner / name).write_text(table, encoding="utf-8")
    records = gate.parse_policy(POLICY)

    def reads(module: str) -> bool:
        leaf = tmp_path / ("leaf-%s.ts" % module)
        leaf.write_text("import { M } from './scripts/ci-runner/%s';\n" % module, encoding="utf-8")
        probe = {"id": "check:probe", "gate": True, "leaves": [leaf.name]}
        return "check:probe" in gate.derive_readers([probe], records, tmp_path)[0][REVIEWS]

    assert reads("other"), "the control: the same table text in another file is a citation"
    assert not reads("manifest")
    assert not reads("trace-ledger")


def test_on_the_real_tree_the_gate_table_makes_no_reader(gate):
    """The seven gates that import the gate table, against the real policy and lock: the table still holds an agent/worklist/** literal, and none of them is derived as a reader of the worklist record."""
    assert "'agent/worklist/**'" in MANIFEST.read_text(encoding="utf-8"), (
        "the control's subject moved"
    )
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    chosen = [g for g in lock if g["id"] in TABLE_IMPORTERS]
    assert len(chosen) == len(TABLE_IMPORTERS), sorted(
        set(TABLE_IMPORTERS) - {g["id"] for g in chosen}
    )
    for g in chosen:
        files = gate.closure(g["leaves"], ROOT)
        assert MANIFEST.resolve() in files, "%s no longer imports the gate table" % g["id"]
    records = [
        r
        for r in gate.parse_policy(
            json.loads(
                paths.from_root(".ci", "policy", "record-paths.json").read_text(encoding="utf-8")
            )
        )
        if r["glob"] == WORKLIST
    ]
    derived = gate.derive_readers(chosen, records, ROOT)[0]
    assert derived[WORKLIST] == {}, derived[WORKLIST]


def test_the_seven_table_importers_listing_agent_are_flagged_through_declared(tmp_path):
    """The real-tree control the F1 brief names, as a process: the real lock with `agent` added to those seven gates' `lists`. Each is flagged, every flag is the declared tier's, and none cites manifest.ts. MIRROR: the unplanted lock is green."""
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    for g in lock:
        if g["id"] in TABLE_IMPORTERS:
            g["lists"] = sorted({*g.get("lists", []), "agent"})
    planted = tmp_path / "gates.lock.json"
    planted.write_text(json.dumps(lock, indent=2), encoding="utf-8")
    result = harness.run(
        [sys.executable, str(GATE), "--records-only", "--lock", str(planted)], cwd=ROOT, timeout=600
    )
    assert result.rc == 1, harness.render_output(result)
    flags = [ln for ln in result.err.splitlines() if "UNDECLARED READER" in ln]
    assert {ln.split()[2] for ln in flags} == set(TABLE_IMPORTERS), flags
    assert all("(declared) lists agent" in ln for ln in flags), flags
    assert "manifest.ts" not in result.err, result.err
    clean = harness.run([sys.executable, str(GATE), "--records-only"], cwd=ROOT, timeout=600)
    assert clean.rc == 0, harness.render_output(clean)
    assert "through the declared tier" in clean.out, clean.out
