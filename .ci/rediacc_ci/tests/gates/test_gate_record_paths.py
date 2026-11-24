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
import re
import subprocess
import sys

import pytest

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


def test_the_guard_reads_globs_and_the_policy_exactly_as_this_gate_does():
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
    gate = importlib.import_module("rediacc_ci.quality.record_paths")
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
#: 2026-11-18 (PLAN-push-decoupling F1): 36 -> 58. The declared tier reads each gate's own lock entry, so the `names: ['**']` gates (they list every file name, and a new plan file changes that list) and the gates that list `agent` or `.ci/config` joined; check:ci-parity was a notReader on a manifest.ts reason and now reads through its `names`.
#: 2026-11-23 (PLAN-tooling-code-reduction CR2): 58 -> 56. check:ci-doc-region-parity, check:ci-gate-bind and check:ci-parity retired into check:ci-gen-gates, whose leaf spawns their scripts as legs; the derivation follows those legs (check_record_paths TS_LEG_RE), so it reads the plan files through the doc-region leg's `*.md` glob.
#: 2026-11-24 (PLAN-tooling-code-reduction CR1-CR4 integration): 58 -> 59, the set as the derivation now reports it.
#: Joined: the nine gates whose lock entry names `**` and that dcee36e930 declared as readers of the record set (agent-browser-exit, docker-npm-pins, go-module-sync, lint-rule-liveness, model-invocable-commands, plant-proofs, secret-supply, standalone-selftests, unverified-downloads), and check:ci-max-lines through plan-boxes.json alone.
#: Left the derivation: dead-service-methods, git-history-depth, jq-boolean-default, merge-method-prose, no-inline-python, python-gate-deps, retired-commands, schema-call-sites and tracked-sidecars; the policy still declares each one a reader (record_paths reports them beyond the derivation), so a plan-only commit still re-runs them.
PLAN_READERS = frozenset(
    {
        "check:ci-account-env-retired",
        "check:ci-actionlint",
        "check:ci-agent-browser-exit",
        "check:ci-agent-hint-liveness",
        "check:ci-agent-session-archival",
        "check:ci-allowlist-key-matching",
        "check:ci-cli-contract",
        "check:ci-commit-citations",
        "check:ci-container-build-context",
        "check:ci-dead-python",
        "check:ci-decision-ids",
        "check:ci-docker-npm-pins",
        "check:ci-dockerfile-mirror-resilience",
        "check:ci-durable-paths-tracked",
        "check:ci-env-registry",
        "check:ci-fetch-integrity",
        "check:ci-fetch-retry",
        "check:ci-gate-reachability-coverage",
        "check:ci-gate-test-real-file-plants",
        "check:ci-gen-gates",
        "check:ci-generated-artifacts",
        "check:ci-gh-retry-reads",
        "check:ci-go-module-sync",
        "check:ci-hint-corpus",
        "check:ci-i18n-cli-key-usage",
        "check:ci-i18n-value-types",
        "check:ci-inner-timeout-reachable",
        "check:ci-lint-rule-liveness",
        "check:ci-literal-sources",
        "check:ci-max-lines",
        "check:ci-model-invocable-commands",
        "check:ci-plan-bindings",
        "check:ci-plan-boxes",
        "check:ci-plan-citations",
        "check:ci-plan-deps",
        "check:ci-plan-feedback",
        "check:ci-plan-folders",
        "check:ci-plan-housekeeping",
        "check:ci-plan-implementation",
        "check:ci-plan-live-proof",
        "check:ci-plan-record",
        "check:ci-plant-proofs",
        "check:ci-portal-sitekey-guard",
        "check:ci-prose-style",
        "check:ci-retired-terms",
        "check:ci-review-resolutions",
        "check:ci-scope-mirrors",
        "check:ci-script-exec-bit",
        "check:ci-secret-supply",
        "check:ci-shape-duplication",
        "check:ci-shell-commands",
        "check:ci-shell-format",
        "check:ci-source-rules",
        "check:ci-standalone-selftests",
        "check:ci-trap-registry",
        "check:ci-tree-shape",
        "check:ci-typecheck-scope-coverage",
        "check:ci-unverified-downloads",
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
        "check:ci-gen-gates",
        "check:ci-scope-mirrors",
        "check:ci-retired-terms",
        "check:ci-tree-shape",
        "check:ci-generated-artifacts",
        "check:ci-dead-python",
    }
)


def _load_gate():
    """The gate module, imported from the package that holds its logic."""
    return importlib.import_module("rediacc_ci.quality.record_paths")


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


def test_a_path_in_code_is_a_citation(tmp_path):
    """The firing halves: a whole-literal path, a path joined from literal segments, and a template literal."""
    gate = _load_gate()
    assert _reads_plans(gate, tmp_path, "opens.py", 'F = open("agent/plans/x.md")\n')
    assert _reads_plans(gate, tmp_path, "joins.py", 'D = ROOT / "agent" / "plans"\n')
    assert _reads_plans(gate, tmp_path, "tpl.ts", "const p = `${root}/agent/plans/${n}.md`;\n")


def test_a_path_in_prose_is_not_a_citation(tmp_path):
    """The silent halves, each a firing source with the path moved into prose. Before the fix every one of these made its gate a reader, which is how 168 gates came to read the plan set."""
    gate = _load_gate()
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


def test_an_exclusion_key_in_a_config_is_not_a_scope(tmp_path):
    """.ci/config/pins.json lists `agent/**` under `literalExclude`; read as a scope it made eleven pin gates readers. The same glob under an inclusion key still counts."""
    gate = _load_gate()
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


@pytest.fixture(scope="module")
def real_derivation():
    """The real-tree derivation, run once for the module: a full scan of the tracked tree is the test's whole cost, and fixture setup is shared time the slow-test ratchet does not charge to a test."""
    gate = _load_gate()
    records = gate.parse_policy(json.loads(POLICY.read_text(encoding="utf-8")))
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    derived, scanned, _read = gate.derive_readers(lock, records, ROOT)
    return records, derived, scanned


def test_the_plan_records_have_exactly_the_measured_readers(real_derivation):
    """The real tree: the derived reader set of the six plan records, less the exemptions the policy names, is PLAN_READERS exactly. Red before the fix, when the derivation flagged 168 gates for the plan glob alone."""
    records, derived, scanned = real_derivation
    by_glob = {r["glob"]: r for r in records}
    assert set(PLAN_RECORDS) <= set(by_glob), sorted(set(PLAN_RECORDS) - set(by_glob))
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
    # check:ci-pytest re-runs the reader gates from its real-tree tests and costs about 1750 s, so it is never a reader of a plan record. The decision taken here (2026-11-23): since 957bf23a89 the derivation sees ONE citation in it, the `*.json` glob green_receipt_heads runs over the ci:quick receipt directories, which opens nothing under .ci/config/; that one citation is exempt by name in notReaders. Any OTHER citation, or that one without its exemption, is red here and is a new decision.
    for glob in PLAN_RECORDS:
        evidence = derived[glob].get("check:ci-pytest")
        if evidence is None:
            continue
        assert evidence.startswith(".ci/rediacc_ci/check_pytest.py:"), (glob, evidence)
        assert evidence.endswith("(glob) *.json"), (glob, evidence)
        assert "check:ci-pytest" in by_glob[glob]["notReaders"], glob


def test_the_plan_text_records_stay_under_review():
    """A plan and the index of plans advance a receipt and are still reviewed per commit (`"review": "keep"`, read by wl_review.skip_globs); the ledgers and the box table are records the reviewer skips."""
    doc = json.loads(POLICY.read_text(encoding="utf-8"))
    kept = {r["glob"] for r in doc["records"] if r.get("review") == "keep"}
    assert kept == {PLAN_RECORD, "agent/INDEX.md"}, sorted(kept)
    # Not a bare agent/plans/**: a non-.md file there (a .tsv inventory, a .patch attachment) is judged by check:ci-language-policy, which scans every tracked path, so it must void the receipt.
    globs = {r["glob"] for r in doc["records"]}
    assert "agent/plans/**" not in globs
    # A session's hand-over is a record (box R20261123.4), and nothing else named STATE.md is: agent/STATE.md at the agent/ root stays a voiding path.
    assert {g for g in globs if g.endswith("STATE.md")} == {STATE_RECORD}, sorted(globs)


# ---------------------------------------------------------------- a carried verdict over a touched record

CARRY_CHILD = """
import json, pathlib, subprocess, sys
from rediacc_hooks.guards import block_unverified_push as G

def world(base, record_path, refresh):
    root = G._repo_v2_carried(base, "ok")
    def git(*args):
        return subprocess.run(["git", *args], cwd=str(root), check=True, capture_output=True, env=G._env()).stdout.decode().strip()
    receipt_path = root / ".ci" / "cache" / "prepush-receipt.json"
    body = json.loads(receipt_path.read_text(encoding="utf-8"))
    policy = root / G.RECORD_POLICY_REL
    policy.parent.mkdir(parents=True, exist_ok=True)
    reader = [{"id": G.V2_FX, "evidence": "fixture:1"}]
    policy.write_text(json.dumps({"version": 1, "records": [
        {"glob": "src/rec/**", "except": [], "readers": reader},
        {"glob": "agent/reviews/**", "except": [], "readers": reader},
    ]}), encoding="utf-8")
    git("add", "-A", "--", G.RECORD_POLICY_REL)
    git("commit", "-q", "-m", "the policy")
    start = git("rev-parse", "HEAD^{tree}")
    body["headTree"] = start
    target = root / record_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{}\\n", encoding="utf-8")
    git("add", "-A", "--", record_path)
    git("commit", "-q", "-m", "a record-only commit")
    end = git("rev-parse", "HEAD^{tree}")
    body["advances"] = [{"from": start, "to": end, "paths": [record_path], "gates": {G.V2_FX: 0}, "finishedAt": "2026-11-16T00:00:00Z"}]
    carried = body["gates"][G.V2_FX].get("carriedFrom") is not None
    if refresh:
        body["gates"][G.V2_FX] = dict(body["gates"][G.V2_FX], **{k: (end if v == "$to" else v) for k, v in json.loads(sys.argv[2]).items()})
    receipt_path.write_text(json.dumps(body), encoding="utf-8")
    return {"carried": carried, "inputs": body["gates"][G.V2_FX]["inputs"]["globs"], "refusal": G.receipt_refusal(str(root), end, G.read_receipt(str(root), end))}

base = pathlib.Path(sys.argv[1])
print(json.dumps({
    "outside": world(base / "outside", "agent/reviews/main/clean.jsonl", False),
    "inside": world(base / "inside", "src/rec/x.jsonl", False),
    "refreshed": world(base / "refreshed", "src/rec/x.jsonl", True),
}))
"""


RUNNER = paths.from_root("scripts", "ci-runner", "run.ts")
TS_VALUES = {"null": None, "'ok'": "ok", "0": 0, "to": "$to"}


def runner_refresh_fields() -> dict[str, object]:
    """The fields scripts/ci-runner/run.ts `refreshCarried` writes over a refreshed entry, read from its source (`$to` is the step's end tree), so the world below is the runner's own output shape and not a copy of it."""
    text = RUNNER.read_text(encoding="utf-8")
    start = text.index("function refreshCarried(")
    block = re.search(r"out\[id\] = \{\s*\.\.\.entry,(.*?)\};", text[start:], re.DOTALL)
    assert block, "refreshCarried no longer writes `out[id] = { ...entry, ... }`"
    fields: dict[str, object] = {}
    for line in block.group(1).split(","):
        if line.strip():
            key, _, value = line.partition(":")
            assert value.strip() in TS_VALUES, (
                "refreshCarried field %r has an unmapped value" % line
            )
            fields[key.strip()] = TS_VALUES[value.strip()]
    return fields


def test_the_runner_refresh_fields_are_read_from_its_source():
    """Review ba4dba67.2: the guard test below uses what refreshCarried writes; this pins that read, so a runner change that adds or drops a field reaches the world."""
    assert runner_refresh_fields() == {
        "inputHash": None,
        "verdict": "ok",
        "exitCode": 0,
        "findings": None,
        "judgedTree": "$to",
        "carriedFrom": None,
    }


def test_the_guard_refuses_a_carried_verdict_over_a_touched_record_until_it_is_refreshed(tmp_path):
    """Found 2026-11-16 while checking that the push guard admits a plan-only advance. block_unverified_push recomputes every CARRIED gate entry's filesHash at the pushed tree, so a receipt that carries a gate whose inputs cover the touched record is refused although the step re-ran that gate green. check:ci-plan-bindings is carried in 12 of the last 40 real receipts and its inputs cover agent/plans/**. The runner now rewrites such an entry as a verdict of the step's tree (scripts/ci-runner/run.ts refreshCarried, pinned by its selftest), and this pins the guard's side of that contract: refused as carried, admitted as refreshed."""
    proc = subprocess.run(
        [sys.executable, "-c", CARRY_CHILD, str(tmp_path), json.dumps(runner_refresh_fields())],
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ, PYTHONPATH=str(HOOKS), GIT_CONFIG_GLOBAL=os.devnull),
    )
    assert proc.returncode == 0, proc.stderr
    worlds = json.loads(proc.stdout)
    assert all(w["carried"] for w in worlds.values()), worlds
    assert all(w["inputs"] == ["src/**"] for w in worlds.values()), worlds
    # CONTROL: the record lies outside the carried gate's inputs, so the same receipt and step are admitted. The refusal below is therefore about the carried inputs and not about the chain.
    assert worlds["outside"]["refusal"] is None, worlds["outside"]
    assert "filesHash differs" in (worlds["inside"]["refusal"] or ""), worlds["inside"]
    assert worlds["refreshed"]["refusal"] is None, worlds["refreshed"]


# ---------------------------------------------------------------- a session hand-over advances the receipt (box R20261123.4)

STATE_RECORD = "agent/*/STATE.md"
STATE_PATH = "agent/ace763dd/STATE.md"

STATE_CHILD = """
import json, pathlib, subprocess, sys
from rediacc_hooks.guards import block_unverified_push as G

policy_doc = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))

def world(base, record_path, policy):
    root = G._repo_v2_carried(base, "ok")
    def git(*args):
        return subprocess.run(["git", *args], cwd=str(root), check=True, capture_output=True, env=G._env()).stdout.decode().strip()
    receipt_path = root / ".ci" / "cache" / "prepush-receipt.json"
    body = json.loads(receipt_path.read_text(encoding="utf-8"))
    target = root / G.RECORD_POLICY_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(policy), encoding="utf-8")
    git("add", "-A", "--", G.RECORD_POLICY_REL)
    git("commit", "-q", "-m", "the real policy")
    start = git("rev-parse", "HEAD^{tree}")
    body["headTree"] = start
    hand = root / record_path
    hand.parent.mkdir(parents=True, exist_ok=True)
    hand.write_text("# STATE\\n\\n## Next action\\n\\nkeep going\\n", encoding="utf-8")
    git("add", "-A", "--", record_path)
    git("commit", "-q", "-m", "chore(state): hand-over")
    end = git("rev-parse", "HEAD^{tree}")
    records, error = G.parse_record_policy(policy)
    readers = sorted({r for rec in records if G.record_of(record_path, [rec]) for r in rec["readers"]})
    # What scripts/ci-runner/run.ts runAdvance appends: the step from the receipt's tree to the new one, every reader of the touched record re-run green.
    body["advances"] = [{"from": start, "to": end, "paths": [record_path], "gates": {r: 0 for r in readers}, "finishedAt": "2026-11-23T00:00:00Z"}]
    receipt_path.write_text(json.dumps(body), encoding="utf-8")
    return {"error": error, "readers": readers, "refusal": G.receipt_refusal(str(root), end, G.read_receipt(str(root), end))}

without = dict(policy_doc, records=[r for r in policy_doc["records"] if r["glob"] != sys.argv[3]])
base = pathlib.Path(sys.argv[1])
print(json.dumps({
    "state": world(base / "state", sys.argv[4], policy_doc),
    "before": world(base / "before", sys.argv[4], without),
    "root-state": world(base / "root-state", "agent/STATE.md", policy_doc),
}))
"""


def test_a_session_hand_over_commit_advances_the_receipt(tmp_path):
    """The wisdom commit of 2026-11-23 (ea95248e0f, 72 s into a ci:quick run) voided the receipt because agent/<session>/STATE.md was no record, and the push was refused "judged a different tree" after 54 minutes. With the REAL policy:

    * the runner's side: the hand-over lies inside exactly one record and every reader of it is a `gate: true` gate of the real lock, the two policy facts scripts/ci-runner/run.ts planAdvance needs to plan an advance rather than the whole lane (the three matchers agree, pinned above);
    * the guard's side: block_unverified_push admits the pushed tree over the step runAdvance appends (receipt at T0, a commit touching only the hand-over, its readers re-run green at T1);
    * the inverse: the same world under the policy WITHOUT the record is refused as outside the record set, which is the pre-fix behaviour, and agent/STATE.md at the agent/ root is refused under the real policy.
    """
    gate = importlib.import_module("rediacc_ci.quality.record_paths")
    records = gate.parse_policy(json.loads(POLICY.read_text(encoding="utf-8")))
    owners = [r["glob"] for r in records if gate.covers(r, STATE_PATH)]
    assert owners == [STATE_RECORD], owners
    assert not [r["glob"] for r in records if gate.covers(r, "agent/STATE.md")]
    state = next(r for r in records if r["glob"] == STATE_RECORD)
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    known = {g["id"] for g in lock if isinstance(g, dict) and g.get("gate") is True}
    assert state["readers"], "a record with no reader proves nothing about an advance"
    assert set(state["readers"]) <= known, sorted(set(state["readers"]) - known)

    proc = subprocess.run(
        [sys.executable, "-c", STATE_CHILD, str(tmp_path), str(POLICY), STATE_RECORD, STATE_PATH],
        capture_output=True,
        text=True,
        check=False,
        env=dict(os.environ, PYTHONPATH=str(HOOKS), GIT_CONFIG_GLOBAL=os.devnull),
        timeout=300,
    )
    assert proc.returncode == 0, proc.stderr
    worlds = json.loads(proc.stdout)
    assert all(w["error"] is None for w in worlds.values()), worlds
    assert worlds["state"]["readers"] == sorted(state["readers"]), worlds["state"]["readers"]
    assert worlds["state"]["refusal"] is None, worlds["state"]["refusal"]
    assert "outside the record set" in (worlds["before"]["refusal"] or ""), worlds["before"]
    assert STATE_PATH in worlds["before"]["refusal"]
    assert "outside the record set" in (worlds["root-state"]["refusal"] or ""), worlds["root-state"]


@pytest.mark.parametrize(
    "args", [("--update",), ("--records-only", "--write-baseline"), ("--policy",)]
)
def test_an_unknown_or_incomplete_argument_is_refused_by_name(args):
    """`npm run check:ci-record-paths -- --update` once exited 0 and did nothing: the script has no --update. An argument the gate does not know is a usage error (rc 2) naming the argument and the flags it accepts, never a silent green."""
    result = _gate(*args)
    assert result.rc == 2, harness.render_output(result)
    offending = args[-1]
    assert offending in result.err, harness.render_output(result)
    for accepted in (
        "--selftest",
        "--records-only",
        "--widths-only",
        "--policy",
        "--lock",
        "--widths",
    ):
        assert accepted in result.err, harness.render_output(result)
    assert "record-paths: OK" not in result.out, harness.render_output(result)


def test_the_bare_run_still_passes_on_the_real_tree():
    """The silent control for the refusal above: the no-argument run, as package.json drives it, judges both modes and passes."""
    result = _gate()
    assert result.rc == 0, harness.render_output(result)
    assert "record-paths: OK" in result.out, harness.render_output(result)
