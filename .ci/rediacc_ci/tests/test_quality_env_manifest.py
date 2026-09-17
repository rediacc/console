r"""`rediacc_ci.quality.env_manifest`: the entry point, the real tree, and the plants.

WHAT IS WORTH TESTING HERE, given the gate already runs 26 controls on every invocation. Three things a control inside the gate cannot do:

  1. Drive the ENTRY POINT as a subprocess, the way CI runs it. The controls
     exercise the pure helpers in-process, which proves the arithmetic and proves
     nothing about the shim, the `_cipath` hop or the exit code.
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
manifest corrupted or gone, with the only backup in a temp directory the same kill orphans. That is not a hypothesis -- the identical shape destroyed `.ci/policy/worklist-env-registry.json` twice in one session, once from a `check:ci-pytest` timeout and once from a concurrent pytest run in a second worktree. Every mutation now happens to a TMP COPY, and `ENV_MANIFEST_OVERRIDE_FILE`
points the real entry point at it. The corpus side is untouched: the five readers still derive names from the real tracked tree, so a plant still proves the live gate reads the live repository.

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

ENTRY = ".ci/scripts/quality/check_env_manifest.py"

pytestmark = pytest.mark.xdist_group("env-manifest")


def _run(root, override=None):
    env = None
    if override is not None:
        env = dict(os.environ, ENV_MANIFEST_OVERRIDE_FILE=str(override))
    return subprocess.run(
        [sys.executable, str(root / ENTRY)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


@contextlib.contextmanager
def planted(mutate):
    """Mutate a TMP COPY of the manifest, run the gate against it, yield the run.

    The real file is read and never written, so there is no restore to race and no window a kill can land in. The caller gets the same thing it always got: a real subprocess run of the real entry point over the real tracked tree, disagreeing with a manifest that says something wrong.
    """
    root = paths.repo_root()
    live = root / em.MANIFEST_REL
    before = live.read_bytes()
    with tempfile.TemporaryDirectory() as td:
        mutated = pathlib.Path(td) / "env-manifest-mutated.json"
        data = json.loads(before.decode("utf-8"))
        mutate(data)
        mutated.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        yield _run(root, override=mutated)
    assert live.read_bytes() == before, "the real manifest must never be written at all"


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
    suppress = {k: set(v) for k, v in manifest["tombstone_proof_sites"].items()}
    sources, _per, _pf, _dyn, _seen, _bad = em.derive_sources(root, None, suppress)
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
    manifest = json.loads((root / em.MANIFEST_REL).read_text(encoding="utf-8"))
    suppress = {k: set(v) for k, v in manifest["tombstone_proof_sites"].items()}
    _names, per, _pf, _dyn, _seen, _bad = em.derive_sources(root, None, suppress)
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


def test_the_python_reader_resolves_constant_indirection():
    """The 55-name hole a regex leaves, in one line, both directions."""
    assert em.names_from_py('S = "SEAM"\nimport os\nos.environ.get(S)\n') == {"SEAM"}
    assert em.names_from_py('x = "SEAM"\ny = x\n') == set()


def test_the_python_reader_ignores_a_literal_inside_another_gates_fixture():
    """Why the regex pass was dropped: it read other gates' fixture strings as reads."""
    fixture = 'FIX = """\\nos.environ["NOT_A_READ"] = "x"\\n"""\n'
    assert "NOT_A_READ" not in em.names_from_py(fixture)
