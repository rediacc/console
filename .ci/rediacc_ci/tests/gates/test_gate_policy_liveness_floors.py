"""Port of `.ci/scripts/test/gates/test-policy-liveness-floors.sh`.

Test for the PER-PROBE INPUT FLOORS in `scripts/check-suppression-liveness.ts`.

THE HOLE THIS CLOSES. The gate's anti-vacuity guard keys on `entriesChecked` across
the WHOLE run (`isVacuous` in `scripts/lib/suppression-liveness.ts`), so it only
fires when the run asserted nothing AT ALL. The failure that actually happens is
one list going empty while the other eleven stay full: the total stays healthy, the
report still prints "every suppression entry is still load-bearing", and the probe
over the emptied list has quietly stopped being a check. Measured on the real tree
2026-09-06: 12 probes, 87 entries, of which the largest single probe is 28 --
emptying any one of the others leaves a total that looks entirely normal.

TWO FLOORS, TWO SHAPES, and each is proven in both directions:

    ENTRIES   the file is there but has been emptied   -> BELOW FLOOR
    PRESENCE  the file is not where the probe looks    -> MISSING FILE

The presence floor only applies to a FULL CHECKOUT, because the gate's own fixtures
are deliberately partial. That predicate is the thing most likely to rot into a
check that cannot fail, so it is asserted in BOTH directions: the same missing file
must be red in a full-shaped root and silent in a partial one, with nothing else
changed between the two runs.

WHERE THE PORT REIMPLEMENTS THE TWIN, and it is one place worth naming. The twin
reads the census back with two `awk` programs -- one summing the ` entries  floor `
rows, one pulling the ` probe(s), ` roll-up -- and asserts the two agree. That
self-consistency check is the reason the census cannot drift from the run it
describes, and a hard-coded 87 would be a hand-typed floor that reds on the next
legitimate edit. The port does the same arithmetic with two regexes over the same
text. Both read the SAME two shapes out of the SAME output; neither knows the
number in advance.

NO `xdist_group`. Each case builds a complete fixture root under `mkdtemp`, points
`SUPPRESSION_LIVENESS_ROOT` at it, and removes it afterwards. The two cases that
run against the real tree only READ it.
"""

import pathlib
import re
import shutil

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-policy-liveness-floors.sh"

GATE = paths.from_root("scripts", "check-suppression-liveness.ts")
TSX = paths.from_root("node_modules", ".bin", "tsx")

POLICY_FILES = (
    ".deps-upgrade-blocklist",
    ".go-deps-upgrade-blocklist",
    ".embed-assets-upgrade-blocklist",
    ".devcontainer-upgrade-blocklist",
    ".unverified-download-allowlist",
    ".actions-upgrade-blocklist",
    ".cli-i18n-orphan-allowlist",
    ".dead-bash-allowlist",
    ".ci-parity-exempt",
)

ROW_RE = re.compile(r"(\d+) entries\s+floor ")
ROLLUP_RE = re.compile(r"(\d+) entr\(ies\)")


def _require_tools(gate) -> None:
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(GATE))
    if not TSX.is_file():
        gate.log_fail(
            "node_modules/.bin/tsx is absent, so the gate could not be executed at all -- "
            "which is a FAILURE and not a pass. Fix: npm install && npm run install:natives"
        )


def make_full_fixture(gate, base: pathlib.Path) -> pathlib.Path:
    """A fixture that is FULL-SHAPED and GREEN, so every case changes exactly one thing.

    Each probe's file is present and satisfies its floor; the oracles are mostly
    left unavailable on purpose (no `packages/`, no `go.mod`, not a git repo) so
    those probes SKIP rather than condemn copied entries whose supporting tree is
    not here. Two probes run for real -- `deps` against the root `package.json`, and
    `parity-exempt` against the copied workflow tree -- which is what keeps the run
    from being vacuous and the baseline from being green for the wrong reason.
    """
    _require_tools(gate)
    root = base / "fixture"
    for rel in (
        ".ci/scripts/quality",
        ".ci/config",
        ".ci/policy",
        ".github/workflows",
        ".github/actions/app-token",
        "packages/json",
    ):
        (root / rel).mkdir(parents=True)

    # Marker 1 of 3: package.json. Also the deps probe's oracle.
    shutil.copy2(paths.from_root("package.json"), root / "package.json")
    # Marker 2 of 3: .ci/scripts/quality, created above; only its existence is read.
    # Marker 3 of 3: .github/workflows, and the parity-exempt probe's oracle. The
    # WHOLE directory, not just ci.yml: the exempt entries name gates stepped from
    # ci-quality.yml, and copying one workflow would condemn them all.
    for workflow in sorted(paths.from_root(".github", "workflows").glob("*.yml")):
        shutil.copy2(workflow, root / ".github" / "workflows" / workflow.name)
    shutil.copy2(
        paths.from_root(".github", "actions", "app-token", "action.yml"),
        root / ".github" / "actions" / "app-token" / "action.yml",
    )
    for name in POLICY_FILES:
        shutil.copy2(paths.from_root(".ci", "policy", name), root / ".ci" / "policy" / name)
    shutil.copy2(
        paths.from_root("packages", "json", ".templates-skiplist"),
        root / "packages" / "json" / ".templates-skiplist",
    )
    allowlist = root / ".ci" / "config" / "content-quality-allowlist.txt"
    shutil.copy2(paths.from_root(".ci", "config", "content-quality-allowlist.txt"), allowlist)

    # The deps oracle here is the root manifest alone, so the copied blocklist's
    # entries -- declared in packages/*/package.json in the real tree -- would be
    # condemned as dead. Replace it with one entry the root manifest really does
    # declare, which keeps the probe RUNNING (that is the point) without a false
    # finding.
    (root / ".ci" / "policy" / ".deps-upgrade-blocklist").write_text(
        "# BLOCKER: live package pinned deliberately so this fixture exercises the deps "
        "probe for real\neslint\n",
        encoding="utf-8",
    )

    # The content-quality probe's oracle is per-path existence, and creating
    # packages/json above is enough to make it RUN. Materialise the paths its
    # allowlist names, empty, so it runs and finds them live. Copying the allowlist
    # without them would have made the baseline red for a reason that has nothing
    # to do with input floors.
    for line in allowlist.read_text(encoding="utf-8").splitlines():
        rel = line.strip()
        if not rel or rel.startswith("#"):
            continue
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).touch()
    return root


def run_gate(root: pathlib.Path, *args: str) -> harness.RunResult:
    """The gate, with the actions vacuity floor set to the fixture's TRUE corpus size.

    `ACTION_REFS_MIN_FILES` matches what this root really holds rather than
    switching the floor off; counted by globbing rather than by a pipeline, because
    a `find` that matched nothing would silently make the floor 0.
    """
    n = len(list((root / ".github" / "workflows").glob("*.yml"))) + len(
        list((root / ".github" / "actions").glob("*/action.yml"))
    )
    return harness.run(
        [str(TSX), str(GATE), *args],
        cwd=paths.repo_root(),
        env={"SUPPRESSION_LIVENESS_ROOT": str(root), "ACTION_REFS_MIN_FILES": str(n)},
    )


def test_real_tree_reports_per_probe_numbers(gate):
    gate.log_test("the live tree reports a per-probe census, and the census adds up")
    _require_tools(gate)
    result = harness.run([str(TSX), str(GATE)], cwd=paths.repo_root())
    gate.assert_exit_code(0, result.rc, "the live tree has no unmet input floor")
    gate.assert_contains(result.out, "Per-probe inputs", "prints the per-probe census")
    gate.assert_contains(result.out, "floor 1", "each row carries the floor it was judged against")
    gate.assert_contains(result.out, "probe(s),", "and a roll-up of probes and entries")
    gate.assert_not_contains(result.out, "BELOW FLOOR", "no probe is starved on the real tree")
    gate.assert_not_contains(
        result.out, "MISSING FILE", "no probe's file is missing on the real tree"
    )

    # SELF-CONSISTENCY, so the census cannot drift from the run it describes: the
    # roll-up total must equal the sum of the rows it is a roll-up of. A hard-coded
    # 87 would be a hand-typed floor and would red on the next legitimate edit.
    rows_sum = sum(int(n) for n in ROW_RE.findall(result.out))
    rollup = ROLLUP_RE.search(result.out)
    if not rollup:
        gate.log_fail(
            "no roll-up line matched, so there was nothing to compare the rows against. "
            "Output:\n%s" % result.out
        )
    if rows_sum == 0:
        gate.log_fail(
            "the census reported ZERO entries across every row, so the equality below "
            "would hold over nothing. Output:\n%s" % result.out
        )
    gate.assert_eq(
        rows_sum, int(rollup.group(1)), "the roll-up equals the sum of the per-probe rows"
    )
    gate.log_pass(
        "the real tree reports per-probe inputs, and the census adds up (%d entries)" % rows_sum
    )


def test_full_fixture_is_green(gate):
    gate.log_test("the baseline every mutation below is measured against")
    with harness.temp_dir() as base:
        result = run_gate(make_full_fixture(gate, base))
        gate.assert_exit_code(0, result.rc, "the untouched full-shaped fixture must pass")
        gate.assert_not_contains(result.out, "BELOW FLOOR", "nothing starved in the baseline")
        gate.assert_not_contains(result.out, "MISSING FILE", "nothing missing in the baseline")
        gate.assert_not_contains(
            result.out, "vacuous", "and the baseline actually checked something"
        )
    gate.log_pass("baseline: a full-shaped fixture with every policy file passes")


def test_emptying_one_list_fails(gate):
    gate.log_test("ONE list emptied while the other probes stay full")
    with harness.temp_dir() as base:
        root = make_full_fixture(gate, base)
        # The shape a bad edit or a truncating rewrite leaves behind: the header
        # survives, the entries do not. Every other probe is untouched, so the run's
        # TOTALS still look healthy and only the per-probe floor can see it.
        (root / ".ci" / "policy" / ".deps-upgrade-blocklist").write_text(
            "# BLOCKER: header left behind by an edit that dropped every entry beneath it\n",
            encoding="utf-8",
        )
        result = run_gate(root)
        gate.assert_exit_code(1, result.rc, "an emptied list must fail the gate")
        gate.assert_contains(result.out, "BELOW FLOOR", "the census marks the starved probe")
        gate.assert_contains(
            result.out, 'the "deps" probe parsed 0 entr(ies)', "names the probe and the count"
        )
        gate.assert_contains(
            result.out, "totals stay healthy", "explains why the totals did not catch it"
        )
        gate.assert_contains(
            result.out, "minEntries to 0", "offers the legitimate-empty escape and where it lives"
        )
    gate.log_pass("emptying ONE list fails, even while the other probes stay full")


def test_declared_empty_lists_do_not_fail(gate):
    gate.log_test("a list that is ALLOWED to hold nothing is not starvation")
    # Three lists are DELIBERATELY empty in this repo (.actions-upgrade-blocklist,
    # .embed-assets-upgrade-blocklist, .devcontainer-upgrade-blocklist each say so
    # in their own header). The fixture copies them as-is, so this asserts the
    # floors distinguish "allowed to hold nothing" from "went empty". No mutation:
    # the baseline IS the case.
    with harness.temp_dir() as base:
        result = run_gate(make_full_fixture(gate, base))
        gate.assert_exit_code(0, result.rc, "declared-empty lists are not starvation")
        gate.assert_contains(
            result.out, "empty by design", "and they are labelled as such, not hidden"
        )
    gate.log_pass("a list that is allowed to hold nothing is not reported as starved")


def test_missing_file_fails_in_a_full_checkout(gate):
    gate.log_test("the move hazard: the file is gone from where the probe looks")
    with harness.temp_dir() as base:
        root = make_full_fixture(gate, base)
        (root / ".ci" / "policy" / ".cli-i18n-orphan-allowlist").unlink()
        result = run_gate(root)
        gate.assert_exit_code(1, result.rc, "a probe whose file is not there must fail the gate")
        gate.assert_contains(result.out, "MISSING FILE", "the census marks the missing input")
        gate.assert_contains(
            result.out,
            "is not at .ci/policy/.cli-i18n-orphan-allowlist",
            "names the path it looked at",
        )
        gate.assert_contains(
            result.out, "policy-paths.ts", "points at the seam that moves a reader"
        )
    gate.log_pass("a policy file missing from a full checkout fails the gate")


def test_missing_file_is_silent_in_a_partial_checkout(gate):
    gate.log_test("THE CONTROL FOR THE PREDICATE: the same deletion in a partial root")
    # If this run ALSO failed, the gate's own fixtures could never be minimal; if
    # the case above passed while this one did too, the predicate would be satisfied
    # by everything and the presence floor would be decorative. Both directions
    # have to hold, and the ONLY difference is one of the three full-checkout
    # markers being taken away.
    with harness.temp_dir() as base:
        root = make_full_fixture(gate, base)
        (root / ".ci" / "policy" / ".cli-i18n-orphan-allowlist").unlink()
        shutil.rmtree(root / ".ci" / "scripts" / "quality")
        result = run_gate(root)
        gate.assert_exit_code(
            0, result.rc, "a partial root must not be judged for files it never had"
        )
        gate.assert_not_contains(
            result.out, "MISSING FILE", "and says nothing about the missing file"
        )
    gate.log_pass("the same missing file is silent in a partial checkout (predicate control)")


def test_undeclared_probe_is_refused(gate):
    gate.log_test("a probe with no PROBE_INPUT_FLOORS row must refuse, not run silently")
    _require_tools(gate)
    # Driven through --probe with a name no probe has, which is the nearest
    # reachable proof that the lookup is REQUIRED rather than optional.
    result = harness.run([str(TSX), str(GATE), "--probe", "not-a-probe"], cwd=paths.repo_root())
    gate.assert_exit_code(2, result.rc, "an unknown probe name is refused")
    gate.assert_contains(result.combined, "unknown probe", "and named")
    gate.log_pass("an unknown probe name is refused rather than silently running nothing")
