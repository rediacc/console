r"""Port of `.ci/scripts/test/gates/test-swallowed-failures.sh`, retired in W7 P5.

Both-ways test for `.ci/scripts/quality/check-swallowed-failures.sh`.

THE DEFECT IT POLICES, carried across from the twin's header. A gate captures a probe, throws away the probe's exit status and its stderr, and reads the captured value. A failed probe yields empty, empty is byte-identical to "nothing to report", and the gate prints its success message. The live specimen is the pre-fix probe in `check-go-deps.sh`, recovered here from git history
rather than paraphrased, so this file tests against the bytes that actually shipped.

WHY THE TWO HISTORICAL CASES ARE THE CENTRE OF THIS FILE. A lint of this shape is only worth having if it fires on the real defect and stays quiet on the real fix. Everything else here is calibration: each remaining case pins one exemption, and an exemption that cannot be shown to be load-bearing is just an untested branch.

CALIBRATION IS PART OF THE CONTRACT. `test_real_tree_is_clean` pins the count on the live tree at ZERO. The gate opened at 16 findings; all 16 were fixed, none waived. Pinning zero is what stops the class regrowing one call site at a time, which is how it reached 16 in the first place.

WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP. Two cases drive the subject over the REAL tree: `test_real_tree_is_clean` runs it seam-free, and `test_the_repaired_sites_stay_repaired` greps the real files in REPAIRS. A battery step rewriting either mid-sweep is a divergence that would be blamed on this port. A third case, `test_silent_on_the_fixed_go_deps_probe`, used to point
the subject at the real `.ci/scripts/quality` to prove it stayed silent about the fixed probe in `check-go-deps.sh`; that file was deleted in W7P5-c and the case retired with it, since the subject here only ever scanned `.sh` files and the survivor, `rediacc_ci.quality.go_deps`, is `.py`. What the case proved about the FIX is now a REPAIRS row instead, naming the surviving
module. `REAL_TREE_TWIN = True` buys the serialisation, and it is honoured only
because this module declares no `XDIST_GROUP` of its own; see `real_tree_admission` in `test_twin_parity.py`.

--------------------------------------------------------------------------
IS THIS FILE VISIBLE TO THE SWEEP IT DRIVES? NO, AND IT IS CHECKED
--------------------------------------------------------------------------
THE QUESTION HAD TO BE ASKED BEFORE A SINGLE FIXTURE WAS WRITTEN. Every fire
case below writes out a genuine swallowed-failure shape. If the subject could
see this source, a literal transcription would turn `check:ci-swallowed-failures` red tree-wide for whoever ran it next -- which is exactly what happened to the `label-references` port in an earlier batch, and why that one renders every fixture through a `%s` template.

Here the answer is different, and the difference is worth stating rather than assuming. The subject is scoped TWO ways, and this file is outside both:

  * `DEFAULT_SCAN_DIRS=(".ci/scripts/quality" ".ci/scripts/security"
    ".ci/scripts/lib")`, and this file lives under `.ci/rediacc_ci/tests/gates`.
  * the walker is `find "$ROOT/$d" -type f -name '*.sh'`, and this file is `.py`.

So the fixtures are written out LITERALLY, exactly as the twin writes them, and the port's diff can be read against its original. What replaces the `%s` treatment is a control rather than an argument: `test_this_module_plants_no_capture_the_real_sweep_can_see` points the REAL subject at this very directory and requires it to report that it scanned NOTHING. Either half of the
scoping breaking -- a `.sh` file appearing beside these ports, or the walker widening to `*.py` -- turns that control red HERE, by name, instead of reddening the gate for the next session.
"""

import os
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

# test_real_tree_is_clean, test_the_repaired_sites_stay_repaired and the added inertness control all read the real tree. See the docstring.
REAL_TREE_TWIN = True

GATE_REL = ".ci/scripts/quality/check-swallowed-failures.sh"
GATE = paths.from_root(*GATE_REL.split("/"))
HERE_REL = ".ci/rediacc_ci/tests/gates"

# `<file>.sh:<line>: $<var>` -- the finding line shape test_real_tree_is_clean counts. `grep -cE '^.*\.sh:[0-9]+: \$'` in the twin; `-P`-equivalent here because Python's `re` has no ugrep's alternated-anchor defect.
FINDING_RE = re.compile(r"^.*\.sh:[0-9]+: \$", re.MULTILINE)

# The default scan scope, as this port expects to read it out of the subject.
# Repeated here ONLY so test_scope_is_gates_only can name what it looked for;
# the scope that governs is the one in the subject.
IN_SCOPE = (".ci/scripts/quality", ".ci/scripts/security", ".ci/scripts/lib")
OUT_OF_SCOPE = ".ci/scripts/deploy"

# <repo-relative file>|<needle>|<what it proves>, the twin's `repairs` array.
#
# AFTER A CUTOVER A ROW MUST NAME THE MODULE, NOT THE ENTRY POINT. The
# registered `.py` for the OTLP gate is a three-line shim that imports the port;
# the behaviour this row asserts lives in the module. Repointing it at the entry point (the obvious move, and the one recommended when the cutover landed) made the row grep a shim and fail with "lost its fix" against a fix that was never there.
#
# AND AFTER A RETIREMENT A ROW MUST NAME THE SURVIVOR. W7 P5 batch G1 deleted the bash twins behind the review-comments, resolved-threads and attribution rows; each now names the module that carries the fix, for the same reason the OTLP row does. W7P5-c deleted `check-go-deps.sh` the same way; the row below used
# to be a standalone case, `test_silent_on_the_fixed_go_deps_probe`, that pointed the subject at the real bash file directly (a `.sh`-only scanner CAN see a `.sh` fix). Its survivor, `rediacc_ci.quality.go_deps`, is `.py` and the subject never scans it, so the row moved here instead, where `PROBE_FAILED` is the
# sentinel the fix's whole point is to emit. The remaining `.sh` rows still name live files, and a row whose file is gone fails LOUDLY here rather than quietly passing.
REPAIRS = (
    (
        ".ci/rediacc_ci/quality/go_deps.py",
        "PROBE_FAILED",
        "the go-deps probe reports a failed probe with a sentinel rather than reading as clean",
    ),
    (
        ".ci/rediacc_ci/quality/review_comments.py",
        "gh_json",
        "the review-comment gate fetches through the status-checking helper",
    ),
    (
        ".ci/rediacc_ci/quality/resolved_threads.py",
        "Failing closed",
        "the resolved-threads gate fails closed on an unreadable API",
    ),
    (
        ".ci/rediacc_ci/quality/claude_attribution.py",
        "probe_failed",
        "the attribution gate fails closed on an unreadable API",
    ),
    (
        ".ci/rediacc_ci/quality/branch.py",
        "as up-to-date.",
        "check-branch refuses to guess when rev-list fails",
    ),
    (
        ".ci/rediacc_ci/quality/no_otlp_creds.py",
        "cannot inspect for baked credentials",
        "the OTLP gate errors when it cannot read a binary",
    ),
    (
        ".ci/scripts/quality/check-submodule-branches.sh",
        "refusing to report zero unreplied",
        "the submodule gate refuses to fabricate a zero",
    ),
    (
        ".ci/scripts/security/dependency-inventory.sh",
        "refusing to emit an empty dependency graph",
        "the SBOM refuses to ship an empty graph",
    ),
    (
        ".ci/scripts/lib/common.sh",
        "r2_count_objects: list-objects-v2 failed",
        "r2_count_objects reports an unreachable bucket",
    ),
    (
        ".ci/scripts/lib/release-state-validator.sh",
        "THREE STATES, DELIBERATELY",
        "the release-state validator separates empty from unanswerable",
    ),
)

SCAN_REL = ".ci/scripts/probe"


def require_gate(gate) -> str:
    """The subject, proved present before anything is claimed."""
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % GATE_REL)
    return harness.require_tool("bash", "install bash; the subject IS a bash script")


def write_case(gate, root, name: str, *lines: str):
    """`write_case <basename> <body...>` -- one fixture script per case.

    ANTI-VACUITY, and it is not decoration. A case that plants an EMPTY body would be scanned, found clean, and pass every silence assertion below for the wrong reason. An empty body is therefore a FAILURE here rather than a fixture that says nothing.
    """
    if not lines:
        gate.log_fail(
            "write_case(%s) was given no body, so the fixture would plant NOTHING and "
            "any silence below would be silence about an empty file." % name
        )
    scan = root / SCAN_REL
    scan.mkdir(parents=True, exist_ok=True)
    path = scan / (name + ".sh")
    path.write_text(
        "#!/bin/bash\nset -euo pipefail\n" + "".join(line + "\n" for line in lines),
        encoding="utf-8",
    )
    return path


def run_gate(gate, root, dirs: str = SCAN_REL) -> harness.RunResult:
    """`run_gate [scan-dirs]`: the two env seams, merged streams.

    The twin captures `2>&1` into `LAST_OUT` and asserts on the merged text, so every caller below reads `.combined` for the same reason.
    """
    bash = require_gate(gate)
    return harness.run(
        [bash, os.fspath(GATE)],
        cwd=paths.repo_root(),
        env={"SWALLOWED_SCAN_ROOT": os.fspath(root), "SWALLOWED_SCAN_DIRS": dirs},
    )


# --------------------------------------------------------------------------- The two historical cases. These are the reason the file exists. ---------------------------------------------------------------------------


def test_fires_on_the_prefix_go_deps_probe(gate):
    """THE CONTROL. Byte-for-byte the probe that shipped before 2026-07-28, recovered with `git show <commit>^:.ci/scripts/quality/check-go-deps.sh`. It spans three physical lines with 2>/dev/null on the first and || true on the third, which is why a line-based scanner cannot see it at all."""
    with harness.temp_dir() as d:
        tree = d / "tree"
        write_case(
            gate,
            tree,
            "prefix-go-deps",
            r"    local outdated",
            r"    outdated=$(go list -u -m -json all 2>/dev/null |",
            r"        jq -rs '.[] | select((.Indirect != true) and (.Update != null))",
            r"""                | "\(.Path) \(.Version)"' 2>/dev/null || true)""",
            r'    while IFS=" " read -r path current latest uptime; do',
            r'        [[ -z "$path" ]] && continue',
            r'        echo "$path $current $latest minor"',
            r'    done <<<"$outdated"',
            r'    echo "All Go direct dependencies are up-to-date"',
        )
        result = run_gate(gate, tree)
        gate.assert_eq(result.rc, 1, "the pre-fix go-deps probe must FIRE: %s" % result.combined)
        gate.assert_contains(
            result.combined, "outdated", "the finding must name the swallowed variable"
        )
        gate.assert_contains(
            result.combined, "no test distinguishes", "with the no-downstream-test reason"
        )
        gate.log_pass(
            "fires on the historical pre-fix check-go-deps probe (multi-line shape included)"
        )


# --------------------------------------------------------------------------- The trigger, one shape at a time. ---------------------------------------------------------------------------


def test_clean_file_passes(gate):
    """Baseline. Without it, every silence below could be silence for the wrong reason (a scanner that matches nothing at all)."""
    with harness.temp_dir() as d:
        tree = d / "tree"
        write_case(
            gate,
            tree,
            "clean",
            r"err=$(mktemp)",
            r'raw=$(some-probe 2>"$err") || status=$?',
            r'if ((status != 0)); then log_error "probe failed"; exit 1; fi',
            r'echo "$raw"',
        )
        result = run_gate(gate, tree)
        gate.assert_eq(result.rc, 0, "a properly guarded probe must pass: %s" % result.combined)
        gate.assert_contains(result.combined, "no gate captures a probe", "and say so")
        gate.log_pass("a capture that keeps its exit status and stderr passes")


def test_capture_with_bare_or_true_fires(gate):
    with harness.temp_dir() as d:
        tree = d / "tree"
        write_case(
            gate,
            tree,
            "bare-or-true",
            r"data=$(some-probe --json 2>/dev/null || true)",
            r'echo "done: $data"',
        )
        result = run_gate(gate, tree)
        gate.assert_eq(result.rc, 1, "an unexamined || true capture must fire")
        gate.assert_contains(result.combined, "data", "naming the variable")
        gate.log_pass("a capture ending in || true with no downstream test fires")


def test_quoted_capture_fires(gate):
    """The recall bug found during calibration: NAME="$(...)" is the commonest
    spelling in this repo, and the first pattern only matched NAME=$(...).
    Every quoted capture was invisible, including all five in dependency-inventory.sh."""
    with harness.temp_dir() as d:
        tree = d / "tree"
        write_case(
            gate,
            tree,
            "quoted",
            r'tree_all="$(npm ls --all --json 2>/dev/null || true)"',
            r'echo "$tree_all"',
        )
        result = run_gate(gate, tree)
        gate.assert_eq(result.rc, 1, "a QUOTED capture must fire too")
        gate.assert_contains(result.combined, "tree_all", "naming the variable")
        gate.log_pass("a quoted capture fires (the shape that was invisible at first)")


def test_empty_case_that_exits_zero_fires(gate):
    """The subtlest true positive, and the shape check-review-comments.sh and check-branch.sh BOTH carried before they were repaired: the author DID test
    for empty, and then treated empty as a pass. Both now fail closed (see the
    repairs pinned in test_the_repaired_sites_stay_repaired), so this fixture is the only place the shape still lives -- which is exactly why it is pinned here rather than left to be rediscovered in the wild."""
    with harness.temp_dir() as d:
        tree = d / "tree"
        write_case(
            gate,
            tree,
            "exits-zero",
            r'COMMENTS=$(gh api "repos/x/pulls/1/comments" 2>/dev/null || echo "[]")',
            r'if [[ "$COMMENTS" == "[]" ]]; then',
            r'    echo "No review comments found - OK"',
            r"    exit 0",
            r"fi",
        )
        result = run_gate(gate, tree)
        gate.assert_eq(result.rc, 1, "a tested-but-passed empty case must fire")
        gate.assert_contains(
            result.combined,
            "the empty case exits successfully",
            "with the de-escalation reason",
        )
        gate.log_pass("an emptiness test whose branch exits 0 fires")


def test_multiline_continuation_is_joined(gate):
    """Proves the logical-line folding independently of the go-deps case: the capture and its || true are three physical lines apart."""
    with harness.temp_dir() as d:
        tree = d / "tree"
        write_case(
            gate,
            tree,
            "joined",
            "edges=$(go mod graph \\",
            "    --some-flag \\",
            r"    2>/dev/null || true)",
            r'echo "$edges" | awk "{print}"',
        )
        result = run_gate(gate, tree)
        gate.assert_eq(result.rc, 1, "a backslash-continued capture must fire")
        gate.assert_contains(result.combined, "edges", "naming the variable")
        gate.log_pass("backslash continuations are folded before matching")


# --------------------------------------------------------------------------- The exemptions. Each one must be shown to be load-bearing. ---------------------------------------------------------------------------


def test_distinguishable_sentinel_is_silent(gate):
    with harness.temp_dir() as d:
        tree = d / "tree"
        write_case(
            gate,
            tree,
            "sentinel",
            r'STATUS=$(docker inspect x --format "{{.State.Status}}" 2>/dev/null || echo "missing")',
            r'echo "$STATUS"',
        )
        result = run_gate(gate, tree)
        gate.assert_eq(
            result.rc, 0, "a fallback to a real sentinel must not fire: %s" % result.combined
        )
        gate.log_pass("a distinguishable sentinel (|| echo missing) is not a swallowed failure")


def test_stderr_folded_in_is_silent(gate):
    with harness.temp_dir() as d:
        tree = d / "tree"
        write_case(
            gate,
            tree,
            "stderr-in",
            r'output=$("$binary" --version 2>&1 || true)',
            r'echo "$output"',
        )
        result = run_gate(gate, tree)
        gate.assert_eq(
            result.rc,
            0,
            "2>&1 keeps the failure in the value, so it must not fire: %s" % result.combined,
        )
        gate.log_pass("a capture that folds stderr into the value is not flagged")


def test_answer_is_exit_commands_are_silent(gate):
    """grep and command -v exit non-zero to MEAN "not found". Flagging them cost 8 false positives on the real tree during calibration."""
    with harness.temp_dir() as d:
        tree = d / "tree"
        write_case(
            gate,
            tree,
            "answer-is-exit",
            r'matches=$(grep -n "pattern" "$file" 2>/dev/null || true)',
            r"found=$(command -v shfmt 2>/dev/null || true)",
            r'echo "$matches $found"',
        )
        result = run_gate(gate, tree)
        gate.assert_eq(result.rc, 0, "grep and command -v must not fire: %s" % result.combined)
        gate.log_pass("commands whose non-zero exit is the answer are exempt")


def test_bare_command_without_capture_is_silent(gate):
    """Best-effort cleanup is none of this gate's business, and it is by far the most common `|| true` in the repo. Flagging it is how this class of lint becomes a wall of noise."""
    with harness.temp_dir() as d:
        tree = d / "tree"
        write_case(
            gate,
            tree,
            "cleanup",
            r"rm -f /tmp/whatever 2>/dev/null || true",
            r'docker rm "$cid" >/dev/null 2>&1 || true',
            r'aws s3 rm "s3://b/k" --quiet 2>/dev/null || true',
        )
        result = run_gate(gate, tree)
        gate.assert_eq(
            result.rc, 0, "bare best-effort commands must not fire: %s" % result.combined
        )
        gate.log_pass("an uncaptured || true (cleanup) is not flagged")


def test_reported_empty_case_is_silent(gate):
    with harness.temp_dir() as d:
        tree = d / "tree"
        write_case(
            gate,
            tree,
            "reported",
            r'seen=$(printf "%s" "$raw" | jq -rs "length" 2>/dev/null || echo 0)',
            r'if [[ "$seen" -eq 0 ]]; then',
            r'    log_error "probe returned no modules at all"',
            r"    return 1",
            r"fi",
        )
        result = run_gate(gate, tree)
        gate.assert_eq(result.rc, 0, "an escalated empty case must not fire: %s" % result.combined)
        gate.log_pass("an emptiness test that reports the problem is not flagged")


def test_escalation_in_the_next_function_does_not_count(gate):
    """Found during calibration: the lookahead window ran past the closing brace, so a log_error in the NEXT function counted as handling for this one. That silently cleared r2_count_objects in lib/common.sh, which is a genuine finding AND the helper the sibling gate recommends as a remedy."""
    with harness.temp_dir() as d:
        tree = d / "tree"
        write_case(
            gate,
            tree,
            "boundary",
            r"count_things() {",
            r"    local count",
            r'    count="$(aws s3api list-objects-v2 --query x --output text 2>/dev/null || echo 0)"',
            r'    if ! [[ "$count" =~ ^[0-9]+$ ]]; then',
            r"        count=0",
            r"    fi",
            r'    printf "%s\n" "$count"',
            r"}",
            r"",
            r"other_function() {",
            r'    log_error "this must not count as handling for count_things"',
            r"    exit 1",
            r"}",
        )
        result = run_gate(gate, tree)
        gate.assert_eq(
            result.rc,
            1,
            "an escalation past the function boundary must not exempt the capture",
        )
        gate.assert_contains(result.combined, "count", "naming the variable")
        gate.log_pass("the lookahead window stops at the enclosing function boundary")


# --------------------------------------------------------------------------- The waiver, held to the BLOCKER bar. ---------------------------------------------------------------------------


def test_waiver_suppresses(gate):
    with harness.temp_dir() as d:
        tree = d / "tree"
        write_case(
            gate,
            tree,
            "waived",
            "# swallowed-failure-ok: an absent optional cache file and an unreadable one "
            "are the same event for this probe, and both mean rebuild",
            r'cached=$(cat "$cache" 2>/dev/null || true)',
            r'echo "$cached"',
        )
        result = run_gate(gate, tree)
        gate.assert_eq(
            result.rc,
            0,
            "a properly reasoned waiver must suppress the finding: %s" % result.combined,
        )
        gate.assert_contains(result.combined, "1 waived", "and be counted in the summary")
        gate.log_pass("a waiver with a substantive reason suppresses the finding")


def test_low_effort_waiver_is_rejected(gate):
    """PROVE THE INSTRUMENT. The header claims the waiver is held to the BLOCKER bar. Without this case that claim could be decorative and nothing would say so."""
    with harness.temp_dir() as d:
        tree = d / "tree"
        write_case(
            gate,
            tree,
            "bad-waiver",
            "# swallowed-failure-ok: tbd",
            r'cached=$(cat "$cache" 2>/dev/null || true)',
            r'echo "$cached"',
        )
        result = run_gate(gate, tree)
        gate.assert_eq(result.rc, 1, "a banned-phrase waiver must be rejected")
        gate.assert_contains(
            result.combined,
            "low-effort placeholder",
            "with the shared validator's own diagnostic",
        )
        gate.log_pass("a low-effort waiver reason is rejected by the shared BLOCKER validator")


def test_waiver_must_be_adjacent(gate):
    """A waiver that drifts away from its line starts excusing whatever moved underneath it, which nobody re-reads."""
    with harness.temp_dir() as d:
        tree = d / "tree"
        write_case(
            gate,
            tree,
            "drifted-waiver",
            "# swallowed-failure-ok: an absent optional cache file and an unreadable one "
            "are the same event here, both meaning rebuild",
            "",
            "# an unrelated comment that separates the waiver from the line",
            r'cached=$(cat "$cache" 2>/dev/null || true)',
            r'echo "$cached"',
        )
        result = run_gate(gate, tree)
        gate.assert_eq(result.rc, 1, "a non-adjacent waiver must not suppress")
        gate.assert_contains(result.combined, "cached", "the finding is still reported")
        gate.log_pass("a waiver separated from its line no longer excuses it")


# --------------------------------------------------------------------------- The gate must not become the thing it polices. ---------------------------------------------------------------------------


def test_empty_scope_is_blind_not_clean(gate):
    """Anti-vacuity. A gate that scans zero files reports clean forever. This is the property the repo's test-gate-anti-vacuity.sh harness checks for other validators; that harness cannot check this one, because its fixture COPIES .ci/scripts into the empty tree, so this gate always has input there. The seam makes the same property testable directly."""
    with harness.temp_dir() as d:
        tree = d / "tree"
        (tree / SCAN_REL).mkdir(parents=True, exist_ok=True)
        result = run_gate(gate, tree, ".ci/scripts/does-not-exist")
        gate.assert_eq(result.rc, 1, "an empty scan scope must fail, not report clean")
        gate.assert_contains(result.combined, "scanned nothing", "and say it scanned nothing")
        gate.assert_not_contains(
            result.combined,
            "no gate captures a probe",
            "it must NOT claim a clean result",
        )
        gate.log_pass("an empty scan scope reports blindness instead of success")


def test_dead_scanner_is_not_a_clean_scan(gate):
    """THE GATE'S OWN FIRST BUG, pinned. Its awk program died on all 42 files (backslash escapes are consumed when awk assigns a -v value, so every regex became "Unmatched ("), and it printed "OK: no gate captures a probe..." and exited 0. The empty output of a dead scanner is identical to the empty output of a clean file, which is precisely the defect this gate exists to
    police."""
    with harness.temp_dir() as d:
        tree = d / "tree"
        path = write_case(gate, tree, "unreadable", "x=1")
        path.chmod(0o000)
        try:
            result = run_gate(gate, tree)
        finally:
            path.chmod(0o644)
        gate.assert_eq(result.rc, 1, "a file the scanner cannot read must fail the run")
        gate.assert_contains(
            result.combined,
            "Refusing to report a verdict",
            "rather than reading as clean",
        )
        gate.log_pass("a scanner that cannot read its input refuses to report a verdict")


# --------------------------------------------------------------------------- The live tree. ---------------------------------------------------------------------------


def test_real_tree_is_clean(gate):
    """THE RATCHET. This started at 16 findings, all triaged by hand: 14 gates that could pass vacuously when their probe failed, and 2 that failed safe. All 16 were fixed rather than waived, so the live count is now ZERO and stays that way.

    Zero is the only bound worth pinning here. A range would let the class regrow one call site at a time, which is exactly how it reached 16: nobody was counting. If this case fails, a new capture is throwing away a probe failure. Fix it or waive it with a real reason, and do not relax this assertion to make the failure go away.
    """
    bash = require_gate(gate)
    result = harness.run([bash, os.fspath(GATE)], cwd=paths.repo_root())
    count = len(FINDING_RE.findall(result.combined))
    if result.rc != 0:
        gate.log_fail(
            "the live tree regrew %d swallowed-failure finding(s):\n%s" % (count, result.combined)
        )
    gate.assert_eq(count, 0, "no capture may discard a probe failure on the live tree")
    gate.assert_contains(
        result.combined,
        "no gate captures a probe",
        "and the gate must say so explicitly",
    )
    gate.log_pass("the live tree is clean: 0 swallowed-failure findings across the gate scripts")


def test_the_repaired_sites_stay_repaired(gate):
    """Anti-vacuity for the case above: "0 findings" is also what a gate that stopped scanning would report. Assert that the specific repairs are still present in the real files, so a regression shows up as a failure here rather than as a suspiciously quiet clean run.

    A SUBSTRING TEST AND NOT `assert_contains`: these needles are searched in WHOLE FILES, and a failing assert_contains would dump the entire file into the test output, burying the one line that matters. The bash twin reaches
    for `grep -qF` for the same reason.
    """
    if not REPAIRS:
        gate.log_fail(
            "the repairs table is EMPTY, so this control checked nothing and its green "
            "would say nothing about whether the real tree still carries its fixes."
        )
    for rel, needle, what in REPAIRS:
        path = paths.from_root(*rel.split("/"))
        if not path.is_file():
            gate.log_fail("%s is gone; the repair it carried cannot be verified" % rel)
        gate.assertions += 1
        if needle not in path.read_text(encoding="utf-8"):
            gate.log_fail("%s lost its fix: %s" % (path.name, what))
    gate.log_pass("all %d repaired sites still carry their fix" % len(REPAIRS))


def test_scope_is_gates_only(gate):
    """The scope is the justification for the whole design: only a gate can turn a swallowed failure into a false GREEN that lets a merge through. If the default scope silently widened to the whole repo, the false-positive budget calibrated above would be meaningless."""
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % GATE_REL)
    body = "\n".join(
        line
        for line in GATE.read_text(encoding="utf-8").splitlines()
        if "DEFAULT_SCAN_DIRS=" in line
    )
    if not body:
        gate.log_fail(
            "no DEFAULT_SCAN_DIRS= line in %s, so this case read NOTHING and every "
            "assertion below would be about an empty string." % GATE_REL
        )
    gate.assert_contains(body, IN_SCOPE[0], "quality gates are in scope")
    gate.assert_contains(body, IN_SCOPE[1], "security gates are in scope")
    gate.assert_contains(body, IN_SCOPE[2], "the helpers gates call are in scope")
    gate.assert_not_contains(body, OUT_OF_SCOPE, "deploy scripts are deliberately out of scope")
    gate.log_pass("the default scope is gates and their helpers, nothing wider")


# --------------------------------------------------------------------------- ADDED BY THE PORT. ---------------------------------------------------------------------------


def test_this_module_plants_no_capture_the_real_sweep_can_see(gate):
    """ADDED BY THE PORT, and it is the control on this port's central claim.

    Every fire case above writes a genuine swallowed-failure shape out LITERALLY, which is only safe because the subject cannot see this file: it
    walks `.ci/scripts/{quality,security,lib}` for `*.sh`, and this is a `.py`
    under `.ci/rediacc_ci/tests/gates`. That is an argument, and an argument is not a control.

    So: point the REAL subject at this directory and require it to say it scanned NOTHING. Both halves of the scoping are then observed rather than reasoned about. A `.sh` file appearing beside these ports, or the walker widening to `*.py`, makes the subject find something here and reds this case BY NAME, instead of reddening `check:ci-swallowed-failures` for whoever runs it next
    and sending them hunting.
    """
    here = paths.from_root(*HERE_REL.split("/"))
    if not here.is_dir():
        gate.log_fail("this module's own directory is missing at %s" % HERE_REL)
    modules = sorted(p.name for p in here.glob("*.py"))
    if not modules:
        gate.log_fail(
            "found ZERO python files under %s, so this control swept nothing and its "
            "green would mean nothing." % HERE_REL
        )
    bash = require_gate(gate)
    result = harness.run(
        [bash, os.fspath(GATE)],
        cwd=paths.repo_root(),
        env={
            "SWALLOWED_SCAN_ROOT": os.fspath(paths.repo_root()),
            "SWALLOWED_SCAN_DIRS": HERE_REL,
        },
    )
    gate.assert_exit_code(
        1,
        result.rc,
        "pointing the subject at the ports' own directory must REFUSE as blind "
        "(output: %s)" % result.combined,
    )
    gate.assert_contains(
        result.combined,
        "scanned nothing",
        "the subject must find NO file at all under %s; if it now finds one, this "
        "module's literal fixtures are inside the sweep and must be rendered through "
        "a placeholder or excluded" % HERE_REL,
    )
    # And the directory scope, read off the subject rather than remembered.
    scope = "\n".join(
        line
        for line in GATE.read_text(encoding="utf-8").splitlines()
        if "DEFAULT_SCAN_DIRS=" in line
    )
    gate.assert_not_contains(
        scope, ".ci/rediacc_ci", "the default scope must not reach the ports' package"
    )
    gate.log_pass(
        "%d ported module(s) under %s are invisible to the real sweep: the subject "
        "reports it scanned nothing there, and its default scope names no python tree"
        % (len(modules), HERE_REL)
    )
