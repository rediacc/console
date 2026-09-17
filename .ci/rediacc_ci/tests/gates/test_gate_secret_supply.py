"""The gate test for `check:ci-secret-supply`, which has no bash twin.

NEW GATE, NOT A PORT, so there is no `.ci/scripts/test/gates/test-*.sh` to name here and nothing to compare against. What it tests is the half a selftest structurally cannot: the gate as a PROCESS, invoked the way CI invokes it, against the REAL `.ci/config/secret-supply.json`, the REAL env manifest and the REAL vault map.

WHY THAT DISTINCTION EARNS ITS KEEP HERE SPECIFICALLY. Every control in `secret_supply.selftest()` runs against a five-name fixture. The clauses that matter most on this gate are the ones about the SIZE and SHAPE of the real corpus: 84 declared names, 58 in the map, 26 unstated. A fixture proves the arithmetic; only the real tree proves the gate is pointed at it.

NOTHING THE REPOSITORY OWNS IS MUTATED. The plants below all run against a MIRROR: a scratch root holding copies of the three real config files plus every file the spec cites as evidence, with `$REDIACC_CI_ROOT` pointed at it. Other sessions share this worktree, and a config that is wrong for even a second is a config some other session's gate ran against.

AND THE MIRROR IS PROVEN GREEN BEFORE EVERY PLANT. A plant that reds against a mirror which was already red proves nothing at all, so each case asserts the clean copy first and only then mutates it.
"""

import json
import pathlib
import shutil
import sys

from rediacc_ci import paths
from rediacc_ci.controls import plant
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_secret_supply.py")
SPEC = paths.from_root(".ci", "config", "secret-supply.json")
MANIFEST = paths.from_root(".ci", "config", "env-manifest.json")
VAULT_MAP = paths.from_root(".ci", "config", "bws-secret-map.json")

CONFIGS = (
    ".ci/config/secret-supply.json",
    ".ci/config/env-manifest.json",
    ".ci/config/bws-secret-map.json",
)


def _run(root=None) -> harness.RunResult:
    env = {"REDIACC_CI_ROOT": str(root)} if root else {}
    return harness.run([sys.executable, str(GATE)], cwd=paths.repo_root(), env=env)


def _spec() -> dict:
    return json.loads(SPEC.read_text(encoding="utf-8"))


def _mirror(tmp: pathlib.Path) -> pathlib.Path:
    """A scratch root holding copies of the real inputs, as a git repository.

    The evidence citations are checked against `git ls-files`, so a mirror that is not a repository would report every citation as DEAD and the plants below would all "pass" for the wrong reason.
    """
    rels = list(CONFIGS) + sorted({e["evidence"] for e in _spec()["residue"].values()})
    for rel in rels:
        (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(paths.from_root(rel), tmp / rel)
    for args in (["init", "-q"], ["add", "-A", "-f"]):
        harness.run(["git", "-C", str(tmp), *args])
    return tmp


def _edit(root: pathlib.Path, rel: str, fn) -> None:
    path = root / rel
    obj = json.loads(path.read_text(encoding="utf-8"))
    fn(obj)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def test_the_gate_is_green_on_the_real_tree(gate):
    gate.log_test("the real tree, through the real entry point")
    for subject in (GATE, SPEC, MANIFEST, VAULT_MAP):
        if not subject.is_file():
            gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(subject))
    result = _run()
    gate.assert_exit_code(0, result.rc, "clean tree (stderr: %s)" % result.err)
    # THE SHAPE, NOT JUST THE VERDICT. A gate whose corpus collapsed to nothing would still print a tick; these numbers are what say it did not.
    gate.assert_contains(result.combined, "name(s) in the `secret` shard", "prints its shape")
    gate.assert_contains(result.combined, "unstated", "and how many names are unstated")
    gate.assert_contains(result.combined, "name(s) routed out of", "and the truncation size")
    gate.log_pass("the gate passes on the real tree and says how much it looked at")


def test_the_blocked_names_are_printed_by_name_every_run(gate):
    gate.log_test("the operator-blocked debt is visible, not counted")
    result = _run()
    gate.assert_exit_code(0, result.rc, "clean tree")
    gate.assert_contains(result.combined, "OPERATOR-BLOCKED", "says the seeding is blocked")
    gate.assert_contains(result.combined, "door:operator-only", "and names the door")
    blocked = [
        name
        for name, dest in _spec()["dotenv"]["names"].items()
        if dest in ("dev-shared", "admin-bootstrap")
    ]
    if not blocked:
        # Legal: it means the seeding landed. Then the line must be GONE, not printed empty, and this test has nothing left to assert.
        gate.assert_not_contains(result.combined, "OPERATOR-BLOCKED", "no debt, no line")
        gate.log_pass("no blocked names remain; the line is absent rather than empty")
        return
    for name in blocked:
        gate.assert_contains(result.combined, name, "prints %s by name" % name)
    gate.log_pass("all %d blocked name(s) are printed in full" % len(blocked))


def test_the_mirror_is_green_before_anything_is_planted(gate):
    gate.log_test("CONTROL: the untouched mirror is green, so a red below means the plant")
    with harness.temp_dir() as tmp:
        result = _run(_mirror(tmp))
        gate.assert_exit_code(0, result.rc, "untouched mirror (stderr: %s)" % result.err)
        # The mirror has no private/account/.env, which is the CI shape. The skip has to be LOUD, and it must not be folded into the success line.
        gate.assert_contains(result.combined, "LOCAL ARM SKIPPED", "says the local arm did not run")
    gate.log_pass("the mirror reproduces the real verdict, and reports the arm it could not run")


def test_trimming_a_residue_entry_reds(gate):
    gate.log_test("PLANT: delete one real residue entry whose name is still unstated")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        gate.assert_exit_code(0, _run(root).rc, "the untouched copy is green first")
        victim = min(_spec()["residue"])
        _edit(root, ".ci/config/secret-supply.json", lambda o: o["residue"].pop(victim))
        result = _run(root)
        gate.assert_exit_code(1, result.rc, "a trimmed baseline reds")
        gate.assert_contains(result.combined, "UNSTATED %s" % victim, "names the trimmed entry")
        gate.assert_contains(
            result.combined,
            "trimming this file is not a way past",
            "and says trimming is not a way past the gate",
        )
    gate.log_pass("deleting an entry whose violation persists reds, so the file cannot be trimmed")


def test_banking_an_entry_no_violation_backs_reds(gate):
    gate.log_test("PLANT: bank an entry for a name that IS in the vault")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        gate.assert_exit_code(0, _run(root).rc, "the untouched copy is green first")
        held = min(json.loads(VAULT_MAP.read_text(encoding="utf-8"))["secrets"])

        def bank(obj):
            obj["residue"][held] = {
                "kind": "dev-shared",
                "door": "operator-only",
                "evidence": ".ci/config/bws-secret-map.json",
                "why": "banked by a test for a violation that does not exist",
            }

        _edit(root, ".ci/config/secret-supply.json", bank)
        result = _run(root)
        gate.assert_exit_code(1, result.rc, "a pre-banked entry reds")
        gate.assert_contains(result.combined, "RESOLVED %s" % held, "names the banked entry")
    gate.log_pass("nothing can be pre-loaded into the file either")


def test_the_seeding_starts_being_enforced_the_moment_it_lands(gate):
    gate.log_test("PLANT: the operator creates dev-shared and the map refresh brings the names in")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        gate.assert_exit_code(0, _run(root).rc, "the untouched copy is green first")
        pending = sorted(
            name
            for name, dest in _spec()["dotenv"]["names"].items()
            if dest in ("dev-shared", "admin-bootstrap")
        )
        if not pending:
            gate.log_pass("no pending seeding remains; there is nothing to simulate")
            return

        def seed(obj):
            for name in pending:
                obj["secrets"][name] = {"id": "00000000-0000-0000-0000-000000000000"}

        _edit(root, ".ci/config/bws-secret-map.json", seed)
        result = _run(root)
        gate.assert_exit_code(1, result.rc, "a landed seeding reds until the spec is drained")
        gate.assert_contains(
            result.combined,
            "FALSE DESTINATION %s" % pending[0],
            "the destination row reds with no edit to the gate",
        )
    gate.log_pass("the blocked half enforces itself the moment the block lifts")


def test_a_dead_evidence_citation_reds(gate):
    gate.log_test("PLANT: an evidence file that stops mentioning its name")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        gate.assert_exit_code(0, _run(root).rc, "the untouched copy is green first")
        spec = _spec()
        # Pick a name whose citation mentions it exactly where a rename would take it away. Any entry does; the first sorted one keeps this stable.
        name = min(spec["residue"])
        cited = root / spec["residue"][name]["evidence"]
        cited.write_text(
            plant(cited.read_text(encoding="utf-8"), name, "%s_RENAMED_BY_A_CONTROL" % name),
            encoding="utf-8",
        )
        result = _run(root)
        gate.assert_exit_code(1, result.rc, "a reason that stopped being true reds")
        gate.assert_contains(result.combined, "STALE EVIDENCE %s" % name, "names the dead citation")
    gate.log_pass("every reason is liveness-checked, not merely required to exist")


def test_an_empty_vault_map_refuses_rather_than_reporting_the_whole_shard(gate):
    gate.log_test("PLANT: a refresh that produced an empty map")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        gate.assert_exit_code(0, _run(root).rc, "the untouched copy is green first")
        _edit(root, ".ci/config/bws-secret-map.json", lambda o: o.update({"secrets": {}}))
        result = _run(root)
        gate.assert_exit_code(1, result.rc, "an empty map refuses")
        gate.assert_contains(result.combined, "lists no secrets", "says which input collapsed")
        gate.assert_not_contains(result.combined, "UNSTATED ", "and does not report 84 findings")
    gate.log_pass("a collapsed input is a refusal naming it, not a wall of findings")


def test_deleting_the_spec_refuses_rather_than_passing(gate):
    gate.log_test("PLANT: delete the spec, which is the cheapest way to silence a gate")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        gate.assert_exit_code(0, _run(root).rc, "the untouched copy is green first")
        (root / ".ci" / "config" / "secret-supply.json").unlink()
        result = _run(root)
        gate.assert_exit_code(1, result.rc, "a missing spec refuses")
        gate.assert_contains(result.combined, "does not exist", "says which file is gone")
    gate.log_pass("the file cannot be deleted to make every finding disappear at once")
