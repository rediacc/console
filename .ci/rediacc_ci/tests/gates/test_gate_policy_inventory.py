"""The Python policy seam and the inventory gate that keeps it honest.

TWO SUBJECTS, and they are deliberately in one file because neither is worth much without the other. `rediacc_ci.policy_paths` is the Python twin of `scripts/lib/policy-paths.ts`; `.ci/scripts/quality/check_policy_inventory.py` is what stops the two from drifting apart, which is the ONLY thing that makes writing the list twice acceptable.

WHAT IS PINNED HERE, and what is pinned elsewhere on purpose:

  * THE PURITY PROPERTY, which is the twin's rule 1 and this file's reason for
    existing. `.ci/rediacc_ci/tests/gates/test_gate_policy_path.py` proves it for
    TypeScript with an `rmdir`: rmdir REFUSES a non-empty directory, so a helper
    that had stat'ed, cached or created anything under an empty fixture root
    fails that line. The Python twin is held to the same proof, the same way,
    because a seam that reads the filesystem cannot answer on a tree that does
    not have the file yet -- and "the file is not there" is exactly the state a
    move passes through.
  * THE DIFFERENTIAL. The two seams are asked for the same sixteen paths under
    the same fixture root and must answer BYTE FOR BYTE. A port that quietly
    diverges from its twin is worse than no port: both look right in isolation
    and the tree gets two answers.
  * THE ENV SEAM AND THE EXIT CODE of the gate, which its own in-process
    controls cannot reach: they call `scan()` directly, so nothing in them
    exercises `POLICY_INVENTORY_ROOT`, the process boundary, or the difference
    between exit 1 and exit 2.

The three-way SET equality (directory == TypeScript == Python) is NOT re-asserted
here. It is the gate's whole verdict, it runs in CI as a gate, and restating it in a test would make the same claim twice and leave the impression it was checked twice.
"""

import pathlib
import subprocess

from rediacc_ci import paths, policy_paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_policy_inventory.py")
TS_SEAM = paths.from_root("scripts", "lib", "policy-paths.ts")
# `REFUSED_FILE` in the gate. Kept as a literal rather than imported: the gate is a hyphen-free script under `.ci/scripts/quality/`, not a package module, and every other reference to it in this file is a subprocess argument.
REFUSED_FILE = ".ci/config/bws-secret-map.json"
TSX = paths.from_root("node_modules", ".bin", "tsx")

# A floor, not a count: sixteen names live in both lists today, and a list that has collapsed below this is a reader pointed at nothing. The EQUALITY of the two lists is the gate's job; this only refuses a vacuous corpus here.
MIN_KNOWN_NAMES = 15


def test_policy_path_is_a_pure_join(gate):
    gate.log_test("policy_path resolves against a root that contains nothing at all")
    with harness.temp_dir() as empty:
        # Deliberately EMPTY: no .ci, no .ci/policy, no dotfiles. A helper that stat'ed anything would have to either raise or answer a second location here; a pure join cannot tell the difference and says so.
        answered = policy_paths.policy_path(".deps-upgrade-blocklist", empty)
        gate.assert_eq(
            str(answered),
            str(empty / ".ci" / "policy" / ".deps-upgrade-blocklist"),
            "resolves against a root containing no .ci directory at all",
        )
        # THE `rmdir` HALF, stated the way the bash twin states it: rmdir refuses a non-empty directory, so this line fails if anything was created.
        empty.rmdir()
        gate.assert_eq(
            empty.exists(), False, "and the fixture root rmdir'd, so nothing was created either"
        )
        empty.mkdir()
    gate.log_pass("policy_path is a pure join: no stat, no readdir, no fallback")


def test_unknown_name_is_refused_loudly(gate):
    gate.log_test("a typo must be refused, not resolved to something plausible")
    caught = None
    try:
        policy_paths.policy_path(".audit-allowlst")
    except policy_paths.UnknownPolicyFileError as exc:
        caught = str(exc)
    gate.assert_eq(caught is not None, True, "a typo raises UnknownPolicyFileError")
    gate.assert_contains(caught or "", "is not a known policy file", "says what went wrong")
    gate.assert_contains(caught or "", ".audit-allowlist", "names the valid set")
    gate.assert_contains(caught or "", "POLICY_FILES", "names where to add a genuinely new one")
    # THE SAME REFUSAL ON THE OTHER ENTRY POINT. `policy_rel` is a second door into the same name set, and a door that validates nothing is how a typo gets a plausible relative path instead of an exception.
    rel_caught = None
    try:
        policy_paths.policy_rel(".audit-allowlst")
    except policy_paths.UnknownPolicyFileError as exc:
        rel_caught = str(exc)
    gate.assert_eq(rel_caught is not None, True, "policy_rel refuses the same typo")
    # CONTROL: a name that IS policy answers, so the two checks above are not simply "everything raises".
    gate.assert_eq(
        policy_paths.policy_rel(".audit-allowlist"),
        ".ci/policy/.audit-allowlist",
        "CONTROL: a known name answers rather than raising",
    )
    gate.log_pass("an unknown name is refused loudly by both entry points")


def test_rel_and_path_agree(gate):
    gate.log_test("policy_rel is the tail of policy_path, for every known name")
    with harness.temp_dir() as root:
        mismatched = [
            n
            for n in policy_paths.POLICY_FILES
            if str(policy_paths.policy_path(n, root)) != str(root / policy_paths.policy_rel(n))
        ]
        gate.assert_eq(mismatched, [], "the absolute and relative answers describe one location")
    gate.assert_eq(
        len(policy_paths.POLICY_FILES) >= MIN_KNOWN_NAMES,
        True,
        "and the name list is populated (%d names, floor %d), so the loop asserted something"
        % (len(policy_paths.POLICY_FILES), MIN_KNOWN_NAMES),
    )
    gate.log_pass(
        "policy_rel and policy_path agree over all %d names" % len(policy_paths.POLICY_FILES)
    )


def test_every_known_name_resolves_to_a_real_file(gate):
    gate.log_test("every name the Python seam knows must be a file that exists today")
    missing = [
        str(policy_paths.policy_path(n))
        for n in policy_paths.POLICY_FILES
        if not policy_paths.policy_path(n).is_file()
    ]
    gate.assert_eq(missing, [], "every known policy name resolves to a file that exists today")
    gate.log_pass("all %d known names resolve to real files" % len(policy_paths.POLICY_FILES))


def test_differential_against_the_typescript_twin(gate):
    gate.log_test("both seams answer the same paths, byte for byte, under one fixture root")
    if not TSX.is_file():
        # A MISSING TOOL IS A LOUD FAILURE, not a skip: a differential that cannot run has proved nothing, and reporting that as a pass is the exact vacuity this suite exists to refuse.
        gate.log_fail(
            "the workspace tsx binary is missing at %s, so the differential could not run "
            "at all -- which is a FAILURE and not a pass. Fix: npm install && npm run "
            "install:natives" % paths.relative_to_root(TSX)
        )
        return
    with harness.temp_dir() as root:
        result = harness.run(
            [str(TSX), str(TS_SEAM), "--all-paths", "--root", str(root)],
            cwd=paths.repo_root(),
        )
        gate.assert_exit_code(0, result.rc, "the TypeScript CLI answers (stderr: %s)" % result.err)
        ts_answer = [line for line in result.out.splitlines() if line.strip()]
        py_answer = [str(policy_paths.policy_path(n, root)) for n in policy_paths.POLICY_FILES]
        gate.assert_eq(sorted(ts_answer), sorted(py_answer), "the two seams answer the same set")
        gate.assert_eq(
            len(ts_answer) >= MIN_KNOWN_NAMES,
            True,
            "and both answered something (%d paths, floor %d)" % (len(ts_answer), MIN_KNOWN_NAMES),
        )
        # NEITHER implementation may have touched the fixture root. The twin's rmdir proof, applied to the pair rather than to one side.
        gate.assert_eq(
            sorted(p.name for p in root.iterdir()),
            [],
            "and the fixture root is still empty after BOTH implementations answered",
        )
    gate.log_pass("the Python twin and the TypeScript seam agree on all %d paths" % len(py_answer))


def _fixture_tree(root: pathlib.Path, ts_list, py_list, disk) -> None:
    (root / "scripts" / "lib").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci").mkdir(parents=True)
    (root / "scripts" / "lib" / "policy-paths.ts").write_text(
        "const POLICY_DIR = '.ci/policy';\nconst POLICY_FILES = Object.freeze([\n"
        + "".join("  '%s',\n" % n for n in ts_list)
        + "] as const);\n",
        encoding="utf-8",
    )
    (root / ".ci" / "rediacc_ci" / "policy_paths.py").write_text(
        'POLICY_DIR = ".ci/policy"\nPOLICY_FILES = (\n'
        + "".join('    "%s",\n' % n for n in py_list)
        + ")\n# a comment, so the prose corpus is never empty\n",
        encoding="utf-8",
    )
    for name in disk:
        p = policy_paths.policy_path(name, root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# BLOCKER: fixture\n", encoding="utf-8")
    # DIRECTION 7's SUBJECT, present and clean. The gate asserts every run that `.ci/policy/README.md` section 6's refusal of this file still holds, and one of the three clauses is that the file EXISTS -- a refusal about a file that is gone is a stale paragraph, not a decision. A fixture tree without it is therefore a legitimately RED tree, which is what the clean control below
    # would otherwise be measuring. If the gate's REFUSED_FILE constant ever moves, this writes the wrong path and that control reds loudly rather than drifting.
    refused = root / REFUSED_FILE
    refused.parent.mkdir(parents=True, exist_ok=True)
    refused.write_text('{"refreshed_at": "2026-01-01T00:00:00Z", "secrets": {}}\n', "utf-8")


def test_the_gate_reds_through_its_environment_seam(gate):
    gate.log_test("POLICY_INVENTORY_ROOT points the gate at another tree, and it reds there")
    base = [".audit-allowlist", ".ci-parity-exempt"]
    with harness.temp_dir() as root:
        # The 2026-09-07 shape: one more file on disk than the TypeScript list knows about. This is what the real drift looked like.
        _fixture_tree(
            root, base, [*base, ".deps-upgrade-blocklist"], [*base, ".deps-upgrade-blocklist"]
        )
        drifted = harness.run(
            [str(GATE)], cwd=paths.repo_root(), env={"POLICY_INVENTORY_ROOT": str(root)}
        )
        gate.assert_exit_code(1, drifted.rc, "a drifted tree exits 1, not 0 and not 2")
        gate.assert_contains(
            drifted.err, ".deps-upgrade-blocklist", "and the finding names the drifted file"
        )
        gate.assert_contains(
            drifted.out, "control(s) passed", "with its own controls run first, on stdout"
        )
    with harness.temp_dir() as root:
        # CONTROL, and it is the half that matters: the same gate, the same environment seam, an AGREEING tree. Without it the case above passes
        # for a gate that fails on everything.
        _fixture_tree(root, base, base, base)
        clean = harness.run(
            [str(GATE)], cwd=paths.repo_root(), env={"POLICY_INVENTORY_ROOT": str(root)}
        )
        gate.assert_exit_code(0, clean.rc, "CONTROL: an agreeing tree exits 0")
        gate.assert_contains(clean.out, "policy inventory:", "and prints the shape it measured")
    gate.log_pass("the gate reds on drift and greens on agreement, through the env seam")


def test_the_recorded_refusal_is_asserted_through_the_env_seam(gate):
    gate.log_test("direction 7: the W4 P5 refusal reds through the process boundary too")
    base = [".audit-allowlist", ".ci-parity-exempt"]
    with harness.temp_dir() as root:
        _fixture_tree(root, base, base, base)
        (root / REFUSED_FILE).unlink()
        gone = harness.run(
            [str(GATE)], cwd=paths.repo_root(), env={"POLICY_INVENTORY_ROOT": str(root)}
        )
        gate.assert_exit_code(1, gone.rc, "a refused file that vanished exits 1")
        gate.assert_contains(gone.err, "is GONE", "and the finding says the file is gone")
    with harness.temp_dir() as root:
        _fixture_tree(root, base, base, base)
        (root / REFUSED_FILE).write_text('{"_c": "BLOCKER: a reason"}\n', "utf-8")
        reasoned = harness.run(
            [str(GATE)], cwd=paths.repo_root(), env={"POLICY_INVENTORY_ROOT": str(root)}
        )
        gate.assert_exit_code(1, reasoned.rc, "a BLOCKER: line in the refused file exits 1")
        gate.assert_contains(
            reasoned.err, "no longer failing", "and it says which predicate clause changed"
        )
    with harness.temp_dir() as root:
        # CONTROL: the same seam, the same fixture, nothing flipped. Without it the two cases above pass for a gate that reds on every tree it is handed.
        _fixture_tree(root, base, base, base)
        clean = harness.run(
            [str(GATE)], cwd=paths.repo_root(), env={"POLICY_INVENTORY_ROOT": str(root)}
        )
        gate.assert_exit_code(0, clean.rc, "CONTROL: an intact refusal exits 0")
        gate.assert_contains(
            clean.out, "still refused entry with 0 BLOCKER:", "and prints the count it measured"
        )
    gate.log_pass("the recorded refusal is re-derived every run, in both directions")


def test_the_gate_refuses_a_tree_it_cannot_see(gate):
    gate.log_test("a corpus the gate cannot read is a refusal, never a quiet pass")
    with harness.temp_dir() as root:
        # No seams, no policy directory: the gate must say it cannot see its subject rather than reporting agreement between two empty sets.
        result = harness.run(
            [str(GATE)], cwd=paths.repo_root(), env={"POLICY_INVENTORY_ROOT": str(root)}
        )
        gate.assert_exit_code(1, result.rc, "an unreadable tree exits 1")
        gate.assert_contains(
            result.err, "cannot see its subject", "and says so in the words of the refusal"
        )
        gate.assert_contains(
            result.err, "would mean nothing", "naming why a green would have been worthless"
        )
    gate.log_pass("an unseeable tree is refused rather than passed")


def test_the_five_migrated_readers_go_through_the_seam(gate):
    gate.log_test("the readers W4 P4a migrated import the seam and hold no literal")
    # NAMED, not discovered. These are the five sites the plan enumerated, and naming them is what makes a REGRESSION visible: a discovery loop over "files that import policy_paths" would shrink silently as readers were rewritten, and report success on the empty set.
    readers = [
        ".ci/rediacc_ci/quality/go_deps.py",
        ".ci/rediacc_ci/quality/plan_housekeeping.py",
        ".ci/rediacc_ci/quality/profiler_coverage.py",
        ".ci/scripts/quality/check_language_policy.py",
        ".ci/scripts/quality/check_runner_advice.py",
    ]
    missing_import = []
    for rel in readers:
        text = paths.from_root(*rel.split("/")).read_text(encoding="utf-8")
        if "from rediacc_ci.policy_paths import" not in text:
            missing_import.append(rel)
    gate.assert_eq(missing_import, [], "each migrated reader imports the seam")
    gate.assert_eq(len(readers), 5, "and all five sites the plan named are covered")
    gate.log_pass("all five migrated readers reach their policy file through the seam")


def test_the_gate_is_reachable_as_a_program(gate):
    gate.log_test("the gate runs as a plain path invocation, controls first")
    result = subprocess.run(
        [str(GATE), "--selftest"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(paths.repo_root()),
    )
    gate.assert_exit_code(0, result.returncode, "--selftest passes (stderr: %s)" % result.stderr)
    gate.assert_contains(result.stdout, "control(s) passed", "and reports how many ran")
    gate.assert_eq(result.stderr, "", "with nothing on stderr when it is green")
    gate.log_pass("the gate is invocable by path and its controls pass")
