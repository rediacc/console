"""The gate test for `check:ci-actions-vars`, which has no bash twin.

NEW GATE, NOT A PORT. What it tests is the half a selftest structurally cannot: the gate as a PROCESS, invoked the way CI invokes it, against the REAL workflow corpus, the REAL `.ci/config/actions-vars.json`, the REAL vault map and the REAL bootstrap ruling. The selftest proves the clauses on a one-file fixture; only the real tree proves the gate is pointed at thirty-odd workflows and sees the seventy-odd `secrets.BWS_ACCESS_TOKEN` reads that make its anti-vacuity clause mean something.

NOTHING THE REPOSITORY OWNS IS MUTATED. Every plant runs against a MIRROR: a scratch root holding copies of every corpus file plus the three config files, with `$REDIACC_CI_ROOT` pointed at it. Other sessions share this worktree, and a workflow that is wrong for even a second is a workflow some other session's gate ran against.

EVERY PLANT IS RED-THEN-GREEN. The untouched mirror is proven green first, so a red means the plant; and the plant is then taken back out and the mirror proven green again, so the red means THAT plant and not some damage the mutation did on the way in.
"""

import json
import pathlib
import shutil
import sys

from rediacc_ci import paths, workflows
from rediacc_ci.controls import plant
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_actions_vars.py")
SPEC_REL = ".ci/config/actions-vars.json"
CONFIGS = (SPEC_REL, ".ci/config/bws-secret-map.json", ".ci/config/secret-supply.json")

# The file every plant edits. The breakpoint session job is the one the plan's no-fetch-job kind was designed around, so it is the honest place to plant one.
BREAKPOINT = ".github/workflows/breakpoint.yml"
# An existing live line in the session job, used as an anchor: a plant inserts after it, and plant() raises if it ever stops being there, so a drifted anchor fails loudly rather than planting nothing.
ANCHOR = "          BP_LABEL: ${{ inputs.tunnel-label }}\n          GITHUB_RUN_ID: ${{ github.run_id }}\n        run: |\n          .ci/breakpoint/scripts/stop-breakpoint.sh"


def _run(root=None) -> harness.RunResult:
    env = {"REDIACC_CI_ROOT": str(root)} if root else {}
    return harness.run([sys.executable, str(GATE)], cwd=paths.repo_root(), env=env)


def _mirror(tmp: pathlib.Path) -> pathlib.Path:
    """A scratch root holding the corpus and the three config files. No git: the gate reads files, not the index."""
    rels = [
        p.relative_to(paths.repo_root()).as_posix() for p in workflows.call_sites(paths.repo_root())
    ]
    for rel in [*rels, *CONFIGS]:
        (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(paths.from_root(rel), tmp / rel)
    return tmp


def _edit_text(root: pathlib.Path, rel: str, old: str, new: str) -> None:
    path = root / rel
    path.write_text(plant(path.read_text(encoding="utf-8"), old, new, count=1), encoding="utf-8")


def _edit_spec(root: pathlib.Path, fn) -> None:
    path = root / SPEC_REL
    obj = json.loads(path.read_text(encoding="utf-8"))
    fn(obj)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def _green(gate, root, label: str) -> None:
    result = _run(root)
    gate.assert_exit_code(0, result.rc, "%s (stderr: %s)" % (label, result.err))


def test_the_gate_is_green_on_the_real_tree(gate):
    gate.log_test("the real tree, through the real entry point")
    for subject in (GATE, *(paths.from_root(rel) for rel in CONFIGS)):
        if not subject.is_file():
            gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(subject))
    result = _run()
    gate.assert_exit_code(0, result.rc, "clean tree (stderr: %s)" % result.err)
    # THE SHAPE, NOT JUST THE VERDICT. A gate whose corpus collapsed would still print a tick; these lines are what say it did not.
    gate.assert_contains(result.combined, "workflow file(s) scanned", "prints the corpus size")
    gate.assert_contains(result.combined, "BWS_ACCESS_TOKEN", "and the secrets it saw, by name")
    gate.assert_contains(
        result.combined, "commented mentions skipped", "and the blind spot as a number"
    )
    gate.log_pass("the gate passes on the real tree and says how much it looked at")


def test_the_real_commented_mentions_do_not_fire(gate):
    gate.log_test("FALSE POSITIVE, real fixtures: the comments the sibling sweep recorded")
    # Each of these sits in the real corpus inside a comment. If one stops being there the fixture is gone and this test says so rather than passing on nothing.
    for rel, needle in (
        (
            ".github/workflows/claude-review-reusable.yml",
            "secrets.ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN",
        ),
        (".github/workflows/cd-deploy-account.yml", "set-account-worker-secrets.sh"),
        (".github/workflows/ci.yml", "vars.TURNSTILE_SITE_KEY"),
    ):
        gate.assert_contains(
            paths.from_root(rel).read_text(encoding="utf-8"),
            needle,
            "%s still carries %s" % (rel, needle),
        )
    result = _run()
    gate.assert_exit_code(0, result.rc, "the real tree stays green with them present")
    gate.assert_not_contains(
        result.combined, "ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN", "the commented secret is not reported"
    )
    gate.assert_not_contains(
        result.combined, "TURNSTILE_SITE_KEY", "the commented variable is not reported"
    )
    gate.log_pass("the recorded comment-only mentions are skipped and counted, not reported")


def test_plant_an_undeclared_vars_read(gate):
    gate.log_test("PLANT 1: a vars.X read with no entry")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        _green(gate, root, "the untouched mirror is green first")
        planted = ANCHOR.replace(
            "          BP_LABEL:",
            "          PLANTED: ${{ vars.PLANTED_VAR }}\n          BP_LABEL:",
            1,
        )
        _edit_text(root, BREAKPOINT, ANCHOR, planted)
        result = _run(root)
        gate.assert_exit_code(1, result.rc, "an undeclared read reds")
        gate.assert_contains(result.combined, "UNDECLARED %s:" % BREAKPOINT, "names the file")
        gate.assert_contains(
            result.combined, "job session reads vars.PLANTED_VAR", "and the job and name"
        )
        _edit_text(root, BREAKPOINT, planted, ANCHOR)
        _green(gate, root, "and green again once the plant is taken out")
    gate.log_pass("a new GitHub variable dependency reds at the commit that adds it")


def test_plant_an_entry_whose_last_read_is_removed(gate):
    gate.log_test("PLANT 2: an entry whose last read was removed")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        planted = ANCHOR.replace(
            "          BP_LABEL:",
            "          PLANTED: ${{ vars.PLANTED_VAR }}\n          BP_LABEL:",
            1,
        )
        _edit_text(root, BREAKPOINT, ANCHOR, planted)
        _edit_spec(
            root,
            lambda o: o["vars"].update(
                PLANTED_VAR={"kind": "migrated", "bws": "GITHUB_APP_ID", "why": "a planted read"}
            ),
        )
        _green(gate, root, "a declared read with a real twin is green first")
        _edit_text(root, BREAKPOINT, planted, ANCHOR)
        result = _run(root)
        gate.assert_exit_code(1, result.rc, "an entry nothing reads reds")
        gate.assert_contains(result.combined, "RESOLVED PLANTED_VAR", "names the drained entry")
        _edit_spec(root, lambda o: o["vars"].pop("PLANTED_VAR"))
        _green(gate, root, "and green again once the entry is drained")
    gate.log_pass("the file cannot keep an entry its reads have left")


def test_plant_a_no_fetch_job_row_whose_job_no_longer_reads(gate):
    gate.log_test("PLANT 3: a no-fetch-job row whose job no longer contains the read")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        planted = ANCHOR.replace(
            "          BP_LABEL:",
            "          PLANTED: ${{ vars.PLANTED_VAR }}\n          BP_LABEL:",
            1,
        )
        _edit_text(root, BREAKPOINT, ANCHOR, planted)

        def exempt(obj):
            obj["vars"]["PLANTED_VAR"] = {
                "kind": "no-fetch-job",
                "why": "a planted human-shell read",
            }
            obj["no_fetch_jobs"]["%s#session" % BREAKPOINT] = {
                "names": ["PLANTED_VAR"],
                "reason": "BLOCKER: a planted exemption for the job that hands a human a shell, proven live then stale",
            }

        _edit_spec(root, exempt)
        _green(gate, root, "a live no-fetch-job exemption is green first")
        _edit_text(root, BREAKPOINT, planted, ANCHOR)
        result = _run(root)
        gate.assert_exit_code(1, result.rc, "an exemption that forgives nothing reds")
        gate.assert_contains(
            result.combined, "STALE no_fetch_jobs '%s#session'" % BREAKPOINT, "names the stale row"
        )

        def drain(obj):
            obj["vars"].pop("PLANTED_VAR")
            obj["no_fetch_jobs"].pop("%s#session" % BREAKPOINT)

        _edit_spec(root, drain)
        _green(gate, root, "and green again once the row is drained")
    gate.log_pass("a no-fetch-job exemption is liveness-checked, not believed")


def test_plant_a_new_github_secret_read(gate):
    gate.log_test("PLANT 4: a new secrets.SOMETHING read")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        _green(gate, root, "the untouched mirror is green first")
        planted = ANCHOR.replace(
            "          BP_LABEL:",
            "          PLANTED: ${{ secrets.SOMETHING }}\n          BP_LABEL:",
            1,
        )
        _edit_text(root, BREAKPOINT, ANCHOR, planted)
        result = _run(root)
        gate.assert_exit_code(1, result.rc, "a new GitHub secret read reds")
        gate.assert_contains(result.combined, "GITHUB SECRET %s:" % BREAKPOINT, "names the file")
        gate.assert_contains(result.combined, "reads secrets.SOMETHING", "and the secret")
        _edit_text(root, BREAKPOINT, planted, ANCHOR)
        _green(gate, root, "and green again once the plant is taken out")
    gate.log_pass("the only GitHub secrets are the bootstrap token and the runner's")


def test_false_positive_guards_do_not_fire(gate):
    gate.log_test("FALSE POSITIVE, planted: a secrets.sh path and a commented ${{ vars.X }}")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        _green(gate, root, "the untouched mirror is green first")
        planted = ANCHOR.replace(
            "          BP_LABEL:",
            "          # set-account-worker-secrets.sh and ${{ vars.PLANTED_COMMENTED }} are prose\n"
            "          PATHISH: ./scripts/set-www-worker-secrets.sh  # vars.PLANTED_TRAILING\n"
            "          BP_LABEL:",
            1,
        )
        _edit_text(root, BREAKPOINT, ANCHOR, planted)
        result = _run(root)
        gate.assert_exit_code(0, result.rc, "neither shape is a read (stderr: %s)" % result.err)
        gate.assert_not_contains(result.combined, "PLANTED_", "and neither is reported")
    gate.log_pass("a path ending in secrets.sh and a commented reference stay silent")


def test_deleting_the_spec_refuses_rather_than_passing(gate):
    gate.log_test("PLANT: delete the spec, the cheapest way to silence a gate")
    with harness.temp_dir() as tmp:
        root = _mirror(tmp)
        _green(gate, root, "the untouched mirror is green first")
        (root / SPEC_REL).unlink()
        result = _run(root)
        gate.assert_exit_code(1, result.rc, "a missing spec refuses")
        gate.assert_contains(result.combined, "does not exist", "says which file is gone")
    gate.log_pass("the file cannot be deleted to make every finding disappear at once")
