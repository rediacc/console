r"""check:ci-env-registry (`rediacc_ci.quality.env_registry`) and its `shards` section (`env_manifest`): the entry point, the real tree, and the plants.

WHAT IS WORTH TESTING HERE, given the gate already runs every section's controls on every invocation. Four things a control inside the gate cannot do:

  0. Prove the ONE GATE reds for each section on the real tree: a read nobody
     registered, and a registry row nothing reads, each planted into a tmp copy
     of the whole document and driven through the real gate, beside a control
     where an unmutated copy stays green.
  1. Drive the ENTRY POINT as a subprocess, the way CI runs it. The controls
     exercise the pure helpers in-process, which proves the arithmetic and proves
     nothing about the module entry or the exit code.
  2. PLANT A DEFECT IN THE REAL MANIFEST AND WATCH THE REAL INVOCATION GO RED.
     A control that calls `clause_findings` with a hand-built dict passes while
     the gate reads no file at all. Each plant below copies the real manifest,
     breaks exactly one clause, runs the real entry point against the real tree,
     and restores. That is the only evidence that the green means anything.
  3. Assert that each of the five READERS is live ON THE REAL TREE. Every reader
     has a name no other reader produces; removing one such name per reader from
     the manifest must produce exactly five UNCLASSIFIED findings, which cannot
     happen unless all five readers really parsed real tracked files.

NO PLANT BELOW EVER WRITES THE REAL MANIFEST, and that is the correction this file exists in its current form for. `planted()` used to copy `.ci/config/env-manifest.json`, write a mutated version OVER the tracked file, run the gate, and restore in a `finally`; `test_a_deleted_manifest_...` went further and `unlink`ed it. A hard kill anywhere in those windows leaves the tracked
manifest corrupted or gone, with the only backup in a temp directory the same kill orphans. That is not a hypothesis -- the identical shape destroyed `.ci/policy/worklist-env-registry.json` twice in one session, once from a `check:ci-pytest` timeout and once from a concurrent pytest run in a second worktree. Every mutation now happens to a TMP COPY, and `ENV_REGISTRY_OVERRIDE_FILE`
points the real invocation at it. A `shards` plant drives that section's own `check()` in a child process, so it costs one section's scan rather than all three; the cross-section plants drive the whole gate. The corpus side is untouched: the five readers still derive names from the real tracked tree, so a plant still proves the live gate reads the live repository.

`xdist_group` IS DECLARED, and its justification changed with the seam. It used to be required, because every plant mutated one shared file in the real tree and two of them on different workers would interleave: worker A plants a STALE entry, worker B runs the gate expecting green, and the failure lands on B with no explanation in it. Nothing is shared any more, so the group is no
longer load bearing for correctness; it is kept because each case forks the whole gate across the whole tracked tree, and one worker running them back to back is cheaper than several doing it at once.
"""

import contextlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import env_manifest as em
from rediacc_ci.tests.gates import harness

GATE = [sys.executable, "-m", "rediacc_ci.quality.env_registry"]
SHARDS_CHECK = [
    sys.executable,
    "-c",
    "from rediacc_ci.quality import env_manifest as m; raise SystemExit(m.check())",
]

pytestmark = pytest.mark.xdist_group("env-manifest")


# PLAN-ciquick-cpu.md W17. The clean real-tree run (no override) is a read several cases share, so it runs ONCE per session, controls first, as check:ci-env-registry runs it; this module is one xdist group, so the once is real. A plant run sets an override and skips the controls: a `shards` plant runs only that section's `check()`, a whole-gate plant goes through `harness.without_controls`. The clean run and the gate's own CI step still run them.
_CLEAN: dict[str, subprocess.CompletedProcess] = {}


def _env(root, override=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root / ".ci")
    if override is not None:
        env["ENV_REGISTRY_OVERRIDE_FILE"] = str(override)
    return env


def _run(root, override=None, whole_gate=False):
    """The clean whole-gate run (cached) with no override; else one plant run against `override`."""
    if override is None:
        if str(root) not in _CLEAN:
            _CLEAN[str(root)] = subprocess.run(
                GATE, cwd=root, capture_output=True, text=True, check=False, env=_env(root)
            )
        return _CLEAN[str(root)]
    argv = harness.without_controls(GATE) if whole_gate else SHARDS_CHECK
    return subprocess.run(
        argv, cwd=root, capture_output=True, text=True, check=False, env=_env(root, override)
    )


# The in-process derivation over the real tree, shared the same way: two cases read it with the same manifest's suppressions, and neither mutates what it returns.
_DERIVED: dict[str, tuple] = {}


def _derived(root):
    if str(root) not in _DERIVED:
        manifest = json.loads((root / em.MANIFEST_REL).read_text(encoding="utf-8"))
        suppress = {k: set(v) for k, v in manifest["tombstone_proof_sites"].items()}
        _DERIVED[str(root)] = em.derive_sources(root, None, suppress)
    return _DERIVED[str(root)]


@contextlib.contextmanager
def planted(mutate, whole_gate=False):
    """Mutate a TMP COPY of the whole registry document, run the check against it, yield the run.

    The real file is read and never written, so there is no restore to race and no window a kill can land in. The caller gets a real subprocess run over the real tracked tree, disagreeing with a document that says something wrong: the `shards` section's check, or with `whole_gate` the whole gate.
    """
    root = paths.repo_root()
    live = root / em.MANIFEST_REL
    before = live.read_bytes()
    with tempfile.TemporaryDirectory() as td:
        mutated = pathlib.Path(td) / "env-manifest-mutated.json"
        data = json.loads(before.decode("utf-8"))
        mutate(data)
        mutated.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        yield _run(root, override=mutated, whole_gate=whole_gate)
    assert live.read_bytes() == before, "the real manifest must never be written at all"


# ---- T0: the one gate, both directions, every section ----


def test_the_one_gate_is_green_on_the_real_tree_and_prints_each_section():
    proc = _run(paths.repo_root())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    text = proc.stdout + proc.stderr
    for section in ("shards", "python_reads", "worklist"):
        assert "section `%s`" % section in text, text
        assert "%s rc 0" % section in text, text


def test_control_an_unmutated_copy_through_the_override_stays_green():
    """CONTROL for the plants below: the override seam itself must not turn the gate red."""
    with planted(lambda _data: None, whole_gate=True) as proc:
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "3 section(s)" in proc.stderr, proc.stderr


def _a_python_read(data):
    """A (module, NAME) the real tree reads, in no other module and in a live shard: the victim for an unregistered read."""
    modules = data["python_reads"]["modules"]
    readers: dict[str, list[str]] = {}
    for module, names in modules.items():
        for name in names:
            readers.setdefault(name, []).append(module)
    for module in sorted(modules):
        for name in modules[module]:
            if name.startswith(("*", "WORKLIST_")) or len(readers[name]) != 1:
                continue
            if any(name in entries for entries in data["shards"].values()):
                return module, name
    raise AssertionError("no singly-read Python name found; the victim picker has lost the tree")


def test_an_unregistered_read_reds_the_one_gate():
    """A read the document does not know, in BOTH sections that pin it: unclassified in `shards`, NEW in `python_reads`.

    Taking a real read's rows out of the document is the same input to the gate as a new read the rows were never written for, and it plants nothing into the tracked tree.
    """
    victim: dict = {}

    def mutate(data):
        module, name = _a_python_read(data)
        victim.update(module=module, name=name)
        data["python_reads"]["modules"][module].remove(name)
        for entries in data["shards"].values():
            if name in entries:
                entries.remove(name)

    with planted(mutate, whole_gate=True) as proc:
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "UNCLASSIFIED %s " % victim["name"] in proc.stderr, proc.stderr
        assert "NEW %s:%s" % (victim["module"], victim["name"]) in proc.stderr, proc.stderr
        assert "shards rc 1, python_reads rc 1, worklist rc 0" in proc.stderr, proc.stderr


def test_an_unregistered_worklist_read_reds_the_one_gate():
    def mutate(data):
        data["worklist"]["names"].pop("WORKLIST_JUDGE")

    with planted(mutate, whole_gate=True) as proc:
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "UNREGISTERED WORKLIST_JUDGE" in proc.stderr, proc.stderr
        assert "worklist rc 1" in proc.stderr, proc.stderr


def test_an_orphan_row_reds_the_one_gate_in_every_section():
    """A row nothing reads, one per section: a shard entry, a `python_reads` pair, a `worklist` name."""

    def mutate(data):
        data["shards"]["harness"] = sorted(data["shards"]["harness"] + ["ZZ_ORPHAN_SHARD_ROW"])
        data["python_reads"]["modules"].setdefault(".ci/rediacc_ci/quality/env_doc.py", []).append(
            "ZZ_ORPHAN_PY_ROW"
        )
        data["worklist"]["names"]["WORKLIST_ZZ_ORPHAN_ROW"] = {
            "kind": "tuning",
            "class": "harness",
            "defaults": ["'1'"],
        }

    with planted(mutate, whole_gate=True) as proc:
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "STALE ZZ_ORPHAN_SHARD_ROW" in proc.stderr, proc.stderr
        assert "STALE .ci/rediacc_ci/quality/env_doc.py:ZZ_ORPHAN_PY_ROW" in proc.stderr, (
            proc.stderr
        )
        assert "DEAD WORKLIST_ZZ_ORPHAN_ROW" in proc.stderr, proc.stderr
        assert "shards rc 1, python_reads rc 1, worklist rc 1" in proc.stderr, proc.stderr


def test_entry_point_is_green_on_the_real_tree():
    proc = _run(paths.repo_root())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "the four clauses hold" in proc.stderr, proc.stderr
    # The shape is printed, not just the verdict.
    for reader in em.SOURCES:
        assert reader.id in proc.stdout, proc.stdout


def test_no_current_count_is_written_into_either_authored_file():
    """The box's strongest instruction, held as an assertion rather than a habit.

    WHAT IS FORBIDDEN IS TODAY'S NUMBER, not every digit. The first cut of this test banned the historical figures too, and it red-lighted the manifest's own header -- which cites 1,014 / 745 / 721 / 777 precisely in order to say that none of them reproduced and that no count belongs in the file. Prose ABOUT a stale number is the opposite of the defect; a LIVE number is the defect.
    So the tokens are DERIVED here and then looked for, which means this assertion cannot go stale either.
    """
    root = paths.repo_root()
    manifest = json.loads((root / em.MANIFEST_REL).read_text(encoding="utf-8"))
    sources, _per, _pf, _dyn, _seen, _bad = _derived(root)
    shards = set()
    for entries in manifest["shards"].values():
        shards |= set(entries)
    live = {str(len(sources)), str(len(shards)), "%d," % (len(sources) // 1000)}
    live = {tok for tok in live if len(tok) >= 3}
    for rel in (em.MANIFEST_REL, ".ci/rediacc_ci/quality/env_manifest.py"):
        text = (root / rel).read_text(encoding="utf-8")
        for token in sorted(live):
            assert token not in text, (
                "%s writes down %s, which is a CURRENT count. Derive it, do not type it."
                % (rel, token)
            )


def test_every_reader_is_live_on_the_real_tree():
    """Remove one name UNIQUE to each reader; all five must come back unclassified."""
    root = paths.repo_root()
    _names, per, _pf, _dyn, _seen, _bad = _derived(root)
    victims = {}
    for reader in em.SOURCES:
        others = set()
        for other in em.SOURCES:
            if other.id != reader.id:
                others |= per[other.id]
        unique = sorted(per[reader.id] - others)
        assert unique, "reader %s produces no name of its own; pick a new victim" % reader.id
        victims[reader.id] = unique[0]

    def mutate(data):
        for name in victims.values():
            for entries in data["shards"].values():
                if name in entries:
                    entries.remove(name)

    with planted(mutate) as proc:
        assert proc.returncode == 1, proc.stdout + proc.stderr
        for reader_id, name in victims.items():
            assert "UNCLASSIFIED %s " % name in proc.stderr, (
                "reader %s did not report %s -- it is not seeing the tree" % (reader_id, name)
            )


def _one_live_name(root):
    manifest = json.loads((root / em.MANIFEST_REL).read_text(encoding="utf-8"))
    return manifest["shards"]["gate-seam"][0]


def test_clause_2_stale_entry_reds():
    def mutate(data):
        data["shards"]["harness"].append("ZZ_GATE_PLANT_NEVER_READ")
        data["shards"]["harness"].sort()

    with planted(mutate) as proc:
        assert proc.returncode == 1
        assert "STALE ZZ_GATE_PLANT_NEVER_READ" in proc.stderr, proc.stderr


def test_clause_3_a_name_in_two_live_shards_reds():
    root = paths.repo_root()
    name = _one_live_name(root)

    def mutate(data):
        data["shards"]["harness"].append(name)
        data["shards"]["harness"].sort()

    with planted(mutate) as proc:
        assert proc.returncode == 1
        assert "is in BOTH `gate-seam` and `harness`" in proc.stderr, proc.stderr


def test_clause_4_a_live_name_declared_dead_reds():
    root = paths.repo_root()
    name = _one_live_name(root)

    def mutate(data):
        data["shards"]["tombstone"].append(name)
        data["shards"]["tombstone"].sort()

    with planted(mutate) as proc:
        assert proc.returncode == 1
        assert "RESURRECTED %s" % name in proc.stderr, proc.stderr


def test_a_proof_site_cannot_hide_a_live_name():
    """The suppression mechanism's own tamper direction, on the real tree."""

    def mutate(data):
        data["tombstone_proof_sites"]["packages/cli/src/cli.ts"] = ["REDIACC_YES"]

    with planted(mutate) as proc:
        assert proc.returncode == 1
        assert "NOT in the tombstone shard" in proc.stderr, proc.stderr


def test_a_dangling_proof_site_reds():
    def mutate(data):
        site = "packages/cli/src/__tests__/env-tombstones.test.ts"
        data["tombstone_proof_sites"][site].append("RDC_PROD")

    with planted(mutate) as proc:
        assert proc.returncode == 1
        assert "dangling" in proc.stderr, proc.stderr


def test_collision_authority_is_word_bounded_not_a_substring():
    """The bug a plant found: REDIACC_DAEMON_DEBUG satisfied an authority for DEBUG."""

    def mutate(data):
        data["collisions"][0]["authority"] = "packages/cli/src/services/executor/local-executor.ts"

    with planted(mutate) as proc:
        assert proc.returncode == 1
        assert "no longer mentions it" in proc.stderr, proc.stderr


def test_a_deleted_manifest_is_a_refusal_not_a_pass():
    """rc 2, not rc 0. An instrument with nothing to compare against has no verdict.

    This case used to `unlink` the real tracked manifest and copy it back in a `finally` -- the worst member of the plant class, because a kill in that window leaves no truncated file to notice, just an absence. The override points at a path inside a temp directory that is deliberately never created, which is the same input (a manifest that is not there) with nothing real at risk.
    """
    root = paths.repo_root()
    live = root / em.MANIFEST_REL
    before = live.read_bytes()
    with tempfile.TemporaryDirectory() as td:
        absent = pathlib.Path(td) / "does-not-exist.json"
        proc = _run(root, override=absent)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "is missing" in proc.stderr, proc.stderr
    assert live.read_bytes() == before, "the real manifest must never be touched at all"
    assert _run(root).returncode == 0, "the real tree is still green with no override set"


def test_a_deleted_document_refuses_through_the_whole_gate():
    """rc 2 from the whole gate too: every section refuses, and the worst code wins."""
    with tempfile.TemporaryDirectory() as td:
        proc = _run(paths.repo_root(), override=pathlib.Path(td) / "absent.json", whole_gate=True)
    assert proc.returncode == 2, proc.stdout + proc.stderr


def test_the_python_reader_resolves_constant_indirection():
    """The 55-name hole a regex leaves, in one line, both directions."""
    assert em.names_from_py('S = "SEAM"\nimport os\nos.environ.get(S)\n') == {"SEAM"}
    assert em.names_from_py('x = "SEAM"\ny = x\n') == set()


def test_the_python_reader_ignores_a_literal_inside_another_gates_fixture():
    """Why the regex pass was dropped: it read other gates' fixture strings as reads."""
    fixture = 'FIX = """\\nos.environ["NOT_A_READ"] = "x"\\n"""\n'
    assert "NOT_A_READ" not in em.names_from_py(fixture)


# ---- T2: WORKLIST_* shard membership is RENDERED from the registry's `class` ----


def _registry_classes():
    root = paths.repo_root()
    reg = json.loads((root / em.MANIFEST_REL).read_text(encoding="utf-8"))["worklist"]
    out = {name: entry.get("class") for name, entry in reg["names"].items()}
    out.update({name: entry.get("class") for name, entry in reg.get("foreign_reads", {}).items()})
    return out


def test_every_worklist_shard_member_is_where_the_registry_class_puts_it():
    """The membership is generated output: the real manifest must equal its own re-render."""
    root = paths.repo_root()
    manifest = json.loads((root / em.MANIFEST_REL).read_text(encoding="utf-8"))
    classes = _registry_classes()
    assert classes, "the registry yielded no classes; this case would be vacuous"
    assert all(classes.values()), "a registry entry carries no class"
    lists = em.shard_lists(manifest)
    in_manifest = {n for s in em.LIVE_SHARDS for n in lists[s] if n.startswith("WORKLIST_")}
    assert in_manifest == set(classes), sorted(in_manifest ^ set(classes))
    assert em.render_worklist(lists, classes) == lists


def test_a_worklist_name_hand_placed_in_the_wrong_shard_reds():
    """CONTROL for T2: no other clause sees a move, because the name is still in exactly one shard."""
    name = min(n for n, c in _registry_classes().items() if c == "harness")

    def mutate(data):
        data["shards"]["harness"].remove(name)
        data["shards"]["gate-seam"].append(name)
        data["shards"]["gate-seam"].sort()

    with planted(mutate) as proc:
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "%s is in shard `gate-seam`" % name in proc.stderr, proc.stderr
        assert "npm run env:register" in proc.stderr, proc.stderr


def test_a_worklist_name_the_registry_does_not_know_reds():
    def mutate(data):
        data["shards"]["harness"].append("WORKLIST_ZZ_NOT_REGISTERED")
        data["shards"]["harness"].sort()

    with planted(mutate) as proc:
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "WORKLIST_ZZ_NOT_REGISTERED" in proc.stderr, proc.stderr
        assert "npm run env:register" in proc.stderr, proc.stderr


def test_render_moves_misplaced_members_and_leaves_the_rest_alone():
    lists: dict[str, list[str]] = {s: [] for s in em.ALL_SHARDS}
    lists["harness"] = ["OTHER", "WORKLIST_A", "WORKLIST_B"]
    lists["gate-seam"] = ["SEAM"]
    lists["tombstone"] = ["WORKLIST_DEAD"]
    got = em.render_worklist(lists, {"WORKLIST_A": "harness", "WORKLIST_B": "gate-seam"})
    assert got["harness"] == ["OTHER", "WORKLIST_A"]
    assert got["gate-seam"] == ["SEAM", "WORKLIST_B"]
    assert got["tombstone"] == ["WORKLIST_DEAD"], "a tombstone is never rendered over"
    assert lists["harness"] == ["OTHER", "WORKLIST_A", "WORKLIST_B"], "the input is not mutated"


# ---- T3: every literal name the `python_reads` section records is classified ----


@contextlib.contextmanager
def planted_python_env(mutate):
    """Mutate the `python_reads` section of a TMP COPY of the document and run the `shards` check against it."""

    def whole(data):
        mutate(data["python_reads"])

    with planted(whole) as proc:
        yield proc


def test_gate_harness_ledger_is_classified_as_a_gate_seam():
    """The one name the plan measured as failing the clause, read through `harness.LEDGER_ENV`."""
    manifest = json.loads((paths.repo_root() / em.MANIFEST_REL).read_text(encoding="utf-8"))
    assert "GATE_HARNESS_LEDGER" in manifest["shards"]["gate-seam"]


def test_a_literal_name_in_the_python_env_registry_must_be_classified():
    def mutate(data):
        data["modules"][".ci/rediacc_ci/quality/env_doc.py"].append("ZZ_PLANTED_PY_ENV")

    with planted_python_env(mutate) as proc:
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "UNCLASSIFIED ZZ_PLANTED_PY_ENV" in proc.stderr, proc.stderr
        assert "`python_reads`" in proc.stderr, proc.stderr


def test_an_opaque_star_name_in_the_python_env_registry_is_not_a_finding():
    """CONTROL: `*expr` is an expression, not a name; the clause must not demand it be classified."""

    def mutate(data):
        data["modules"][".ci/rediacc_ci/quality/env_doc.py"].append("*zz_planted_key")

    with planted_python_env(mutate) as proc:
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "zz_planted_key" not in proc.stdout + proc.stderr


def test_a_missing_python_reads_section_is_a_refusal():
    with planted(lambda data: data.pop("python_reads")) as proc:
        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert "is missing" in proc.stderr, proc.stderr
