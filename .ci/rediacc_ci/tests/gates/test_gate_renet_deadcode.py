"""Port of `.ci/scripts/test/gates/test-renet-deadcode.sh`.

`private/renet/.ci/scripts/quality/deadcode.sh`, the Go whole-program
reachability gate, driven through its two pure predicates: `evaluate_deadcode`
over a fixture dead-list plus a fixture allowlist, and `validate_blocker_reason`
over one reason string. Nothing here runs Go, downloads the deadcode tool, or
touches the renet checkout beyond READING the script.

WHY THE SUBJECT IS SOURCED RATHER THAN EXECUTED. `deadcode.sh` guards its main
block with `[[ "${BASH_SOURCE[0]}" == "${0}" ]]`, deliberately, so a gate test
can pull `evaluate_deadcode`, `validate_blocker_reason` and renet's own
`common.sh` logging helpers into scope without the analysis running. The twin
sources it ONCE at file scope and calls the functions in-process; a Python port
has no shell to source into, so each case is one fresh `bash -c` that sources the
script and runs a single call. That is the only structural difference, and it is
in the port's favour: a function that left state behind in the twin's one shell
cannot leak into the next case here.

THE ONE DELIBERATE DIVERGENCE, and it is a verdict divergence, so it is stated
rather than buried. The twin opens with

    if [[ ! -f "$DEADCODE_SH" ]]; then
        echo "renet submodule not present -- skipping renet deadcode gate test"
        exit 0
    fi

which is `exit 0` having asserted nothing. This port REFUSES instead. Two reasons,
and the first is not a matter of taste: `.ci/scripts/test/run-all.sh` already
scores an exit-0 run with no `PASS:` line as a FAILURE ("exited 0 but made no
assertions"), so under the battery that actually runs these files the twin's skip
is a red too -- it is only `bash <twin>` driven directly, which is what
`test_twin_parity.py` does, that reads it as green. The second is the rule this
whole directory is built on: a case that could not run has not been checked, and
unchecked folded into fine is the shape being refused. `check:ci-pytest` runs in
`quality-security`, which checks submodules out, so the absent-submodule state is
not one CI reaches.

NO `xdist_group`. Every case writes its fixtures into pytest's own `tmp_path` and
runs one short-lived `bash -c`; nothing is bound, no module global is mutated, and
the subject is only ever read.
"""

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-renet-deadcode.sh"

DEADCODE_SH = paths.from_root("private", "renet", ".ci", "scripts", "quality", "deadcode.sh")

# The two canonical names the twin uses. A `<pkgpath>.<Func>` and a `<pkgpath>.<Type>.<Method>`, because the stale-entry guard keys on the whole string and a method name is the shape most likely to be mangled by a naive split.
FUNC_A = "github.com/rediacc/renet/pkg/example.DeadFunc"
FUNC_B = "github.com/rediacc/renet/pkg/example.Type.DeadMethod"

# Substantive BLOCKER reasons, both over the module's own BLOCKER_MIN_LENGTH of 30 and neither matching a LOW_EFFORT_BLOCKER_PATTERNS entry.
REASON_A = (
    "reachable only under GOOS=darwin syscall fallback; deleting breaks the cross-platform build"
)
REASON_B = "kept alive only by the btrfs-tagged privileged test suite in pkg/example"


def source_and_run(gate, code: str) -> harness.RunResult:
    """Source the subject in a fresh bash and run one call, streams MERGED.

    Merged rather than kept apart, and this is the case the harness's docstring
    reserves for `.combined`: renet's `common.sh` writes its log lines to stderr
    while the twin captures `2>&1` and asserts on the merged text. Splitting them
    here would make every message assertion below a claim the twin never made.
    """
    if not DEADCODE_SH.is_file():
        gate.log_fail(
            "the subject is missing at %s, so not one case below could run -- which is a "
            "FAILURE and not a pass. The twin exits 0 here; run-all.sh scores that same "
            "run as 'exited 0 but made no assertions'. Fix: git submodule update --init "
            "private/renet" % paths.relative_to_root(DEADCODE_SH)
        )
    bash = harness.require_tool("bash", "install bash; the subject is a bash library")
    return harness.run([bash, "-c", "source '%s'\n%s" % (DEADCODE_SH, code)])


def dead_tsv(directory, *names: str):
    """The `<name>\\tfile:line` table `deadcode` emits, with one row per name.

    An EMPTY file when no names are given, which is a fixture in its own right:
    `test_passes_on_empty_dead_list` needs a table that exists and holds nothing,
    which is not the same input as a table that is absent.
    """
    path = directory / "dead.tsv"
    path.write_text(
        "".join("%s\tpkg/example/file.go:42\n" % name for name in names), encoding="utf-8"
    )
    return path


def test_passes_when_all_dead_allowlisted(gate, tmp_path):
    gate.log_test("a dead function with a substantive BLOCKER reason is suppressed")
    dead = dead_tsv(tmp_path, FUNC_A)
    allow = tmp_path / "allow-good"
    allow.write_text("# BLOCKER: %s\n%s\n" % (REASON_A, FUNC_A), encoding="utf-8")
    result = source_and_run(gate, "evaluate_deadcode '%s' '%s'" % (dead, allow))
    gate.assert_exit_code(0, result.rc, "allowlisted dead function should pass")
    gate.log_pass("allowlisted dead function passes")


def test_fails_on_unlisted_dead_function(gate, tmp_path):
    gate.log_test("a dead function nobody allowlisted must fail, and be NAMED")
    dead = dead_tsv(tmp_path, FUNC_A, FUNC_B)
    absent = tmp_path / "nonexistent-allowlist"
    result = source_and_run(gate, "evaluate_deadcode '%s' '%s'" % (dead, absent))
    gate.assert_exit_code(1, result.rc, "unlisted dead functions should fail")
    gate.assert_contains(result.combined, "unreachable function", "error names the problem")
    gate.assert_contains(result.combined, FUNC_B, "error lists the offending function")
    gate.log_pass("unlisted dead function is rejected")


def test_fails_on_missing_blocker(gate, tmp_path):
    gate.log_test("a bare allowlist entry is not a suppression, it is an unexplained one")
    dead = dead_tsv(tmp_path, FUNC_A)
    allow = tmp_path / "allow-nobloc"
    allow.write_text("%s\n" % FUNC_A, encoding="utf-8")
    result = source_and_run(gate, "evaluate_deadcode '%s' '%s'" % (dead, allow))
    gate.assert_exit_code(1, result.rc, "entry without BLOCKER should fail")
    gate.assert_contains(result.combined, "BLOCKER", "error mentions the BLOCKER requirement")
    gate.log_pass("missing BLOCKER is rejected")


def test_fails_on_low_effort_blocker(gate, tmp_path):
    gate.log_test("'tbd' is shorter than BLOCKER_MIN_LENGTH, so the length rule catches it")
    dead = dead_tsv(tmp_path, FUNC_A)
    allow = tmp_path / "allow-loweffort"
    allow.write_text("# BLOCKER: tbd\n%s\n" % FUNC_A, encoding="utf-8")
    result = source_and_run(gate, "evaluate_deadcode '%s' '%s'" % (dead, allow))
    gate.assert_exit_code(1, result.rc, "low-effort BLOCKER should fail")
    gate.assert_contains(result.combined, "too short", "short low-effort reason is called out")
    gate.log_pass("low-effort BLOCKER is rejected")


def test_fails_on_low_effort_phrase_at_length(gate):
    """The PHRASE list, reached without the length rule getting there first.

    The twin's comment is the whole point of this case and is kept: a banned
    phrase must fail because it is banned, not because it is short. "no fix
    available" is 16 characters, so routing it through `evaluate_deadcode` would
    be caught by BLOCKER_MIN_LENGTH and the phrase list would never be consulted.
    Calling the validator directly is what puts the phrase arm under test.
    """
    gate.log_test("a banned phrase is refused by the validator itself")
    result = source_and_run(gate, "validate_blocker_reason 'x' 'no fix available'")
    gate.assert_exit_code(1, result.rc, "banned phrase should fail validation")
    gate.log_pass("banned phrase is rejected by validator")


def test_fails_on_stale_entry(gate, tmp_path):
    """The guard that keeps a suppression from outliving what it suppressed."""
    gate.log_test("an allowlisted name that is no longer dead must fail, not pass quietly")
    dead = dead_tsv(tmp_path, FUNC_A)
    allow = tmp_path / "allow-stale"
    # FUNC_B is allowlisted and is NOT in the dead list, so it has been deleted, renamed or made reachable. A blank line between the two blocks, because a BLOCKER line covers the entries after it until the next blank line.
    allow.write_text(
        "# BLOCKER: %s\n%s\n\n# BLOCKER: %s\n%s\n" % (REASON_A, FUNC_A, REASON_B, FUNC_B),
        encoding="utf-8",
    )
    result = source_and_run(gate, "evaluate_deadcode '%s' '%s'" % (dead, allow))
    gate.assert_exit_code(1, result.rc, "stale allowlist entry should fail")
    gate.assert_contains(
        result.combined, "Stale allowlist entry", "error names the stale entry guard"
    )
    gate.assert_contains(result.combined, FUNC_B, "error identifies the stale name")
    gate.log_pass("stale allowlist entry is rejected")


def test_passes_on_empty_dead_list(gate, tmp_path):
    gate.log_test("nothing dead and nothing allowlisted is the green state")
    dead = dead_tsv(tmp_path)
    absent = tmp_path / "nonexistent-allowlist"
    result = source_and_run(gate, "evaluate_deadcode '%s' '%s'" % (dead, absent))
    gate.assert_exit_code(0, result.rc, "empty dead list with no allowlist should pass")
    gate.log_pass("empty dead list passes")
