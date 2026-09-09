r"""`rediacc_ci.quality.env_manifest`: the entry point, the real tree, and the plants.

WHAT IS WORTH TESTING HERE, given the gate already runs 26 controls on every
invocation. Three things a control inside the gate cannot do:

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

`xdist_group` IS DECLARED, and it is required rather than tidy. Every plant below
mutates ONE shared file in the REAL tree, `.ci/config/env-manifest.json`, and
restores it. Under `-n auto` two of these on different workers would interleave:
worker A plants a STALE entry, worker B runs the gate expecting green, and the
failure lands on B with no explanation in it. The group pins them to one worker,
which serialises them against each other -- and nothing outside this file touches
that manifest, so the group is sufficient as well as necessary.

THE PLANTS RESTORE FROM A COPY MADE FIRST, never from `git show > file`: the
manifest may be untracked when these run, and `cmd > file` truncates the target
BEFORE cmd runs, which destroys an untracked file outright.
"""

import contextlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import env_manifest as em

ENTRY = ".ci/scripts/quality/check_env_manifest.py"

pytestmark = pytest.mark.xdist_group("env-manifest")


def _run(root):
    return subprocess.run(
        [sys.executable, str(root / ENTRY)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


@contextlib.contextmanager
def planted(mutate):
    """Copy the manifest, mutate it, yield the run, restore byte-for-byte."""
    root = paths.repo_root()
    live = root / em.MANIFEST_REL
    tmp = pathlib.Path(tempfile.mkdtemp())
    backup = tmp / "manifest.json"
    shutil.copy2(live, backup)
    try:
        data = json.loads(live.read_text(encoding="utf-8"))
        mutate(data)
        live.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        yield _run(root)
    finally:
        shutil.copy2(backup, live)
        shutil.rmtree(tmp, ignore_errors=True)


def test_entry_point_is_green_on_the_real_tree():
    proc = _run(paths.repo_root())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "the four clauses hold" in proc.stderr, proc.stderr
    # The shape is printed, not just the verdict.
    for reader in em.SOURCES:
        assert reader.id in proc.stdout, proc.stdout


def test_no_current_count_is_written_into_either_authored_file():
    """The box's strongest instruction, held as an assertion rather than a habit.

    WHAT IS FORBIDDEN IS TODAY'S NUMBER, not every digit. The first cut of this
    test banned the historical figures too, and it red-lighted the manifest's own
    header -- which cites 1,014 / 745 / 721 / 777 precisely in order to say that
    none of them reproduced and that no count belongs in the file. Prose ABOUT a
    stale number is the opposite of the defect; a LIVE number is the defect. So
    the tokens are DERIVED here and then looked for, which means this assertion
    cannot go stale either.
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
    """rc 2, not rc 0. An instrument with nothing to compare against has no verdict."""
    root = paths.repo_root()
    live = root / em.MANIFEST_REL
    tmp = pathlib.Path(tempfile.mkdtemp())
    backup = tmp / "manifest.json"
    shutil.copy2(live, backup)
    try:
        live.unlink()
        proc = _run(root)
        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert "is missing" in proc.stderr, proc.stderr
    finally:
        shutil.copy2(backup, live)
        shutil.rmtree(tmp, ignore_errors=True)
    assert _run(root).returncode == 0, "the restore did not restore"


def test_the_python_reader_resolves_constant_indirection():
    """The 55-name hole a regex leaves, in one line, both directions."""
    assert em.names_from_py('S = "SEAM"\nimport os\nos.environ.get(S)\n') == {"SEAM"}
    assert em.names_from_py('x = "SEAM"\ny = x\n') == set()


def test_the_python_reader_ignores_a_literal_inside_another_gates_fixture():
    """Why the regex pass was dropped: it read other gates' fixture strings as reads."""
    fixture = 'FIX = """\\nos.environ["NOT_A_READ"] = "x"\\n"""\n'
    assert "NOT_A_READ" not in em.names_from_py(fixture)
