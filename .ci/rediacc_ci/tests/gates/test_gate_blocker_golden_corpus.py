"""Port of `.ci/scripts/test/gates/test-blocker-golden-corpus.sh`.

THREE-WAY GOLDEN CORPUS for the BLOCKER quality validator. The same rule ("a BLOCKER reason must be substantive") is implemented three times in this tree: `scripts/lib/blocker-validator.ts`, `.ci/scripts/lib/blocker-validator.sh`, and the drift-locked vendored subset at `.ci/breakpoint/lib/breakpoint-blocker.sh`. The corpus is the RECORD of what all three answer today, including
the five cases where the vendored subset deliberately diverges.

THE CORPUS TEXT IS THE TWIN'S, BYTE FOR BYTE, including the seven `real-*` rows that are VERBATIM BLOCKER reasons from the live allowlists. A corpus of invented strings proves the validator agrees about strings nobody writes.

THE VENDORED COPY IS NEVER WRITTEN. Every perturbation control copies its subject into pytest's own `tmp_path` first, and the last case re-asserts that with `git status --porcelain` on the vendored path, so a future edit that wrote in place is caught here rather than in another repository.

WHERE THIS REIMPLEMENTS awk, sed AND `read_lines`, AND WHY THE ANSWERS AGREE:

  * `corpus_ids` / `corpus_expected` are `awk -F'|' 'NF{print $N}'`. The Python
    form splits each non-empty line on `|` and takes the same field. No field may
    contain a `|`, which the twin states and this module ASSERTS on load, so the
    two splits cannot disagree.
  * `read_lines` exists in the twin only because `mapfile` is bash-4-only and
    check:ci-shell-commands refuses it. It keeps a trailing line with no newline,
    which matters for the empty-reason case; `str.split("\\n")` with the final
    empty element dropped is the same list, and the empty reason survives it
    because it is not the LAST line of the reasons file.
  * The perturbations are `sed` substitutions on a COPY. They are the same
    substitutions here, applied with `str.replace`, and each one REFUSES when its
    anchor is missing rather than writing an unperturbed copy: a control that
    silently did not land is the exact vacuity this file exists to refuse.

NO `xdist_group`. Everything is written into pytest's own `tmp_path`. The only tree read that could race is `git status` on one path, which is a read.
"""

import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-blocker-golden-corpus.sh"

TS_LIB = paths.from_root("scripts", "lib", "blocker-validator.ts")
SH_LIB = paths.from_root(".ci", "scripts", "lib", "blocker-validator.sh")
BP_LIB = paths.from_root(".ci", "breakpoint", "lib", "breakpoint-blocker.sh")
BP_COMMON = paths.from_root(".ci", "breakpoint", "lib", "breakpoint-common.sh")
EMIT_ADVISORY = paths.from_root(".ci", "scripts", "lib", "emit-advisory.sh")
TSX = paths.from_root("node_modules", ".bin", "tsx")

BP_RELPATH = ".ci/breakpoint/lib/breakpoint-blocker.sh"

MIN_CASES = 14
MIN_REAL = 5
RECORDED_BP_DIVERGENCE = 5

# THE CORPUS. <case-id>|<reason>|<ts>|<sh>|<bp>
CORPUS_TEXT = """\
real-deps-eslint|v10.x requires eslint v10; typescript-eslint/import/react plugins lack v10 peer dep support|accept|accept|accept
real-deps-astro|6.x is a major on the Astro integration stack while astro itself is deliberately held on the 5 line; move it with that migration, not standalone.|accept|accept|accept
real-go-landlock|v0.9.0 is a 0.x minor that can change the Landlock config API; this gates repo-sandbox isolation, so adoption needs sandbox-behavior validation on a live cluster before bumping|accept|accept|accept
real-dead-bash|iterated as a glob by run.sh (for script in tutorials_dir/tutorial-*.sh) and by the readdirSync scans in scripts/gates/check-tutorial-commands.ts and check-tutorial-noninteractive.ts|accept|accept|accept
real-parity-exempt|reads the PR head/base refs from the GITHUB_* event environment; outside a pull_request event there is no branch pair to validate, so a local run has nothing to check|accept|accept|accept
real-unverified-dl|AWS publishes no sha256 for the CLI bundle -- the .sha256 URL returns 404 -- only a GPG .sig, which needs their signing key imported first; revisit if a checksum ever appears|accept|accept|accept
real-audit-prod|astro 6 is a major migration tracked separately; the marketing site is the only consumer and the advisory is build-time only|accept|accept|accept
banned-no-fix|no fix|reject:low-effort|reject:low-effort|reject:too-short
banned-tbd|tbd|reject:low-effort|reject:low-effort|reject:low-effort
banned-ok|ok|reject:low-effort|reject:low-effort|reject:low-effort
banned-dev-only|dev only|reject:low-effort|reject:low-effort|reject:too-short
banned-override|override|reject:low-effort|reject:low-effort|reject:low-effort
banned-punctuation|No Fix Available.|reject:low-effort|reject:low-effort|reject:too-short
banned-whitespace|  TBD  |reject:low-effort|reject:low-effort|reject:low-effort
short-15|pinned upstream|reject:too-short|reject:too-short|reject:too-short
len-30|abcdefghij abcdefghij abcdefg1|accept|accept|accept
len-29|abcdefghij abcdefghij abcdefg|reject:too-short|reject:too-short|reject:too-short
defer-pr-focused|held back to keep this PR focused; the bump is routine and will land in the dependency sweep|reject:deferral|reject:deferral|accept
defer-dedicated|deferred to a dedicated dependency-bump PR because the tree is mid-migration right now|reject:deferral|reject:deferral|accept
empty||reject:too-short|reject:too-short|reject:too-short
"""

CORPUS = [line.split("|") for line in CORPUS_TEXT.splitlines() if line]

COLUMN_LABELS = ("typescript", "bash      ", "breakpoint")

# The `.ts` driver the twin heredocs into a temp file. `$lib` and `$reasons` become the two format arguments; nothing else changes.
TS_DRIVER = """import fs from 'node:fs';
import { validateBlockerQuality } from '%(lib)s';
const raw = fs.readFileSync('%(reasons)s', 'utf-8').split('\\n');
if (raw.length && raw[raw.length - 1] === '') raw.pop();
for (const reason of raw) {
  const r = validateBlockerQuality('ENTRY', reason, 'FILE');
  process.stdout.write((r === null ? 'accept' : 'reject:' + r.kind) + '\\n');
}
"""

SH_DRIVER = """
        set -u
        source "$1"
        while IFS= read -r reason || [[ -n "$reason" ]]; do
            out=$(validate_blocker_quality "ENTRY" "$reason" "FILE" 2>&1) && { echo accept; continue; }
            case "$out" in
                *"low-effort placeholder"*) echo "reject:low-effort" ;;
                *"defers a routine bump"*)  echo "reject:deferral" ;;
                *"is too short"*)           echo "reject:too-short" ;;
                *)                          echo "reject:UNCLASSIFIED" ;;
            esac
        done <"$2"
"""

BP_DRIVER = """
        set -u
        source "$3" >/dev/null 2>&1
        source "$1"
        while IFS= read -r reason || [[ -n "$reason" ]]; do
            out=$(bp_validate_blocker "PATH" "$reason" 2>&1) && { echo accept; continue; }
            case "$out" in
                *"low-effort placeholder"*) echo "reject:low-effort" ;;
                *"is too short"*)           echo "reject:too-short" ;;
                *)                          echo "reject:UNCLASSIFIED" ;;
            esac
        done <"$2"
"""


def corpus_ids() -> list[str]:
    return [row[0] for row in CORPUS]


def corpus_expected(column: int) -> list[str]:
    """Fields are 1=id 2=reason 3=ts 4=sh 5=bp, so column 0 is field 3."""
    return [row[2 + column] for row in CORPUS]


def write_reasons(directory: pathlib.Path) -> pathlib.Path:
    """The corpus reasons, one per line. Reasons never contain newlines, which is what makes line-per-case safe for all three runners."""
    path = directory / "reasons"
    path.write_text("".join(row[1] + "\n" for row in CORPUS), encoding="utf-8")
    return path


def read_lines(text: str) -> list[str]:
    """`read_lines`: one element per line, keeping a trailing unterminated line."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def require_inputs(gate) -> None:
    for path in (TS_LIB, SH_LIB, BP_LIB, BP_COMMON, EMIT_ADVISORY):
        if not path.is_file():
            gate.log_fail(
                "an implementation this corpus compares is missing: %s -- nothing below "
                "would be checked" % paths.relative_to_root(path)
            )
    if not TSX.is_file():
        gate.log_fail(
            "the workspace tsx binary is missing at %s, so the TypeScript column could "
            "not run at all -- a FAILURE and not a pass. Fix: npm install && npm run "
            "install:natives" % paths.relative_to_root(TSX)
        )


def run_ts(
    gate,
    lib: pathlib.Path,
    reasons: pathlib.Path,
    scratch: pathlib.Path,
    env: dict[str, str] | None = None,
) -> str:
    driver = scratch / "blocker-ts.ts"
    driver.write_text(TS_DRIVER % {"lib": str(lib), "reasons": str(reasons)}, encoding="utf-8")
    result = harness.run([str(TSX), str(driver)], cwd=paths.repo_root(), env=env)
    if not result.out.strip():
        gate.log_fail(
            "the TypeScript runner produced NO verdicts, so the comparison below would "
            "be against nothing (stderr: %s)" % result.err.strip()
        )
    return result.out


def run_sh(
    gate, lib: pathlib.Path, reasons: pathlib.Path, env: dict[str, str] | None = None
) -> str:
    result = harness.run(["bash", "-c", SH_DRIVER, "_", str(lib), str(reasons)], env=env)
    if not result.out.strip():
        gate.log_fail("the bash runner produced NO verdicts (stderr: %s)" % result.err.strip())
    return result.out


def run_bp(gate, lib: pathlib.Path, reasons: pathlib.Path) -> str:
    result = harness.run(["bash", "-c", BP_DRIVER, "_", str(lib), str(reasons), str(BP_COMMON)])
    if not result.out.strip():
        gate.log_fail(
            "the breakpoint runner produced NO verdicts (stderr: %s)" % result.err.strip()
        )
    return result.out


def compare_column(column: int, label: str, actual: str) -> list[str]:
    """`compare_column`: the mismatches, as printable lines. Empty means agreement."""
    ids = corpus_ids()
    expected = corpus_expected(column)
    got = read_lines(actual)
    if len(got) != len(ids):
        return ["%s produced %d verdict(s) for %d case(s)" % (label, len(got), len(ids))]
    return [
        "%s  %s: recorded '%s', got '%s'" % (label, ids[i], expected[i], got[i])
        for i in range(len(ids))
        if got[i] != expected[i]
    ]


def perturb(gate, source: pathlib.Path, target: pathlib.Path, old: str, new: str) -> None:
    """A perturbation that REFUSES when its anchor is missing.

    The twin's TypeScript control checks the shape with a follow-up grep; this applies the same discipline to all three, because a perturbation that did not land makes the control pass for the wrong reason and there is no way to tell
    from the outside.
    """
    text = source.read_text(encoding="utf-8")
    if text.count(old) != 1:
        gate.log_fail(
            "the perturbation did not land: %s carries %d occurrence(s) of the anchor "
            "%r, so this control would run against unperturbed source"
            % (paths.relative_to_root(source), text.count(old), old)
        )
    target.write_text(text.replace(old, new), encoding="utf-8")


def test_corpus_is_large_enough_and_real(gate):
    # No field may contain a `|`; the twin states that and this asserts it, because it is what makes the split-based readers on both sides agree.
    for row in CORPUS:
        if len(row) != 5:
            gate.log_fail(
                "corpus row %r has %d fields, not 5 -- a reason containing '|' would "
                "silently re-column the whole table" % (row[0], len(row))
            )
    count = len(CORPUS)
    if count < MIN_CASES:
        gate.log_fail("corpus has %d cases; the recorded floor is %d" % (count, MIN_CASES))
    reals = len([row for row in CORPUS if row[0].startswith("real-")])
    if reals < MIN_REAL:
        gate.log_fail(
            "corpus has %d verbatim entries from live allowlists; at least %d are required"
            % (reals, MIN_REAL)
        )
    gate.log_pass(
        "corpus holds %d cases, %d of them verbatim BLOCKER reasons from live allowlists"
        % (count, reals)
    )


def test_three_way_reproduction(gate, tmp_path):
    require_inputs(gate)
    reasons = write_reasons(tmp_path)
    columns = (
        run_ts(gate, TS_LIB, reasons, tmp_path),
        run_sh(gate, SH_LIB, reasons),
        run_bp(gate, BP_LIB, reasons),
    )
    problems: list[str] = []
    for index, label in enumerate(COLUMN_LABELS):
        problems.extend(compare_column(index, label, columns[index]))
    if problems:
        gate.log_fail(
            "the golden corpus no longer reproduces. If the change was deliberate, "
            "re-record with: bash %s --emit\n%s" % (BASH_TWIN, "\n".join(problems))
        )
    # Nothing may land in the UNCLASSIFIED bucket: that is a rejection whose message stopped naming its own reason, which is how a validator turns into something an author cannot act on.
    if any("UNCLASSIFIED" in column for column in columns):
        gate.log_fail(
            "an implementation rejected a case without a recognisable reason in its message"
        )
    gate.log_pass("all three implementations reproduce the recorded corpus byte for byte")


def test_recorded_divergence_is_still_exactly_five(gate):
    # The corpus is also the RECORD of how far the vendored subset drifts. If the breakpoint copy silently gained or lost a phrase, the divergence count moves and this fires, which is the only place that drift is visible.
    diverge = len([row for row in CORPUS if row[2] != row[4]])
    gate.assert_eq(
        diverge,
        RECORDED_BP_DIVERGENCE,
        "the breakpoint subset diverges from canonical on exactly the recorded cases",
    )
    same = len([row for row in CORPUS if row[2] != row[3]])
    gate.assert_eq(
        same,
        0,
        "typescript and bash agree on every case, which is what makes them collapsible",
    )
    gate.log_pass(
        "recorded drift: breakpoint differs on %d of %d; TS and bash differ on none"
        % (diverge, len(CORPUS))
    )


def scratch_canonical(gate, scratch: pathlib.Path) -> pathlib.Path:
    """A four-file minimum `rediacc_ci` under <scratch>/.ci, with "tbd" removed.

    THE TWIN'S `scratch_canonical`, function for function. Both clients used to carry their own copy of the banned list, so "drop one phrase" was a sed on each file; they are CLIENTS now, and a sed on the bash mirror would perturb nothing while still looking like a control. The phrase is dropped from the CANONICAL instead, and the assertion is that the clients FOLLOW, which is a
    strictly stronger claim: it proves the delegation is live.
    """
    root = paths.repo_root()
    core = scratch / "canonical" / ".ci" / "rediacc_ci" / "core"
    core.mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", "paths.py"):
        (core.parent / name).write_text(
            (root / ".ci" / "rediacc_ci" / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    (core / "__init__.py").write_text(
        (root / ".ci" / "rediacc_ci" / "core" / "__init__.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    source = root / ".ci" / "rediacc_ci" / "core" / "allowlist.py"
    text = source.read_text(encoding="utf-8")
    if text.count('\n    "tbd",\n') != 1:
        gate.log_fail(
            "the perturbation did not land: LOW_EFFORT_PHRASES no longer holds exactly "
            "one bare '\"tbd\",' line, so this control would run against an "
            "unperturbed canonical"
        )
    (core / "allowlist.py").write_text(text.replace('\n    "tbd",\n', "\n", 1), encoding="utf-8")
    # AND IT MUST STILL IMPORT. A python file broken by the edit makes every client fail loudly, which is also a mismatch and would let this control pass for the wrong reason.
    probe = harness.run(
        ["python3", "-m", "rediacc_ci.core.allowlist", "contract"],
        env={"PYTHONPATH": str(core.parent.parent)},
    )
    if probe.rc != 0:
        gate.log_fail(
            "the perturbed canonical does not import (%s); the control would fail for "
            "the wrong reason" % probe.err.strip()[:200]
        )
    return scratch / "canonical"


def test_perturbing_the_canonical_is_followed_by_typescript(gate, tmp_path):
    require_inputs(gate)
    reasons = write_reasons(tmp_path)
    root = scratch_canonical(gate, tmp_path)
    problems = compare_column(
        0,
        "typescript(perturbed canonical)",
        run_ts(gate, TS_LIB, reasons, tmp_path, env={"REDIACC_CI_ROOT": str(root)}),
    )
    if not problems:
        gate.log_fail(
            "dropping one banned phrase from the canonical must change the TypeScript "
            "verdicts; it did not, so the client is not reading the canonical"
        )
    gate.log_pass("control: the TypeScript client follows a perturbed canonical")


def test_perturbing_the_canonical_is_followed_by_bash(gate, tmp_path):
    require_inputs(gate)
    reasons = write_reasons(tmp_path)
    root = scratch_canonical(gate, tmp_path)
    problems = compare_column(
        1,
        "bash(perturbed canonical)",
        run_sh(gate, SH_LIB, reasons, env={"REDIACC_CI_ROOT": str(root)}),
    )
    if not problems:
        gate.log_fail(
            "dropping one banned phrase from the canonical must change the bash verdicts; "
            "it did not, so the client is not reading the canonical"
        )
    gate.log_pass("control: the bash client follows a perturbed canonical")


def test_perturbing_the_typescript_normaliser_is_caught(gate, tmp_path):
    """THE ONE DECISION STILL WRITTEN IN TYPESCRIPT.

    The client renders from the canonical's templates and matches against the canonical's tables, but it lowercases and trims the reason itself, because doing that in a subprocess would cost one interpreter start per entry. That step needs its own control: without it the normalised ' TBD ' case would stop being normalised and nothing above would notice.
    """
    require_inputs(gate)
    reasons = write_reasons(tmp_path)
    perturbed = tmp_path / "perturbed.ts"
    perturb(gate, TS_LIB, perturbed, "\n    .toLowerCase()", "")
    problems = compare_column(
        0,
        "typescript(no lowercase)",
        run_ts(
            gate,
            perturbed,
            reasons,
            tmp_path,
            env={"REDIACC_CI_ROOT": str(paths.repo_root())},
        ),
    )
    if not problems:
        gate.log_fail("dropping the lowercase step from the TS normaliser must break the corpus")
    gate.log_pass("control: the TypeScript-side normalisation is exercised")


def test_perturbing_breakpoint_copy_is_caught(gate, tmp_path):
    require_inputs(gate)
    reasons = write_reasons(tmp_path)
    # A COPY. .ci/breakpoint/lib/breakpoint-blocker.sh is drift-locked and vendored into other repositories; this test never writes to it.
    perturbed = tmp_path / "perturbed-bp.sh"
    perturb(gate, BP_LIB, perturbed, '"tbd" "wip"', '"wip"')
    problems = compare_column(2, "breakpoint(perturbed)", run_bp(gate, perturbed, reasons))
    if not problems:
        gate.log_fail("dropping one banned phrase from the vendored subset must break the corpus")
    gate.log_pass("control: a perturbed breakpoint copy fails the corpus (original untouched)")


def test_breakpoint_original_is_untouched(gate):
    # Belt and braces on the rule above: the file the three controls copy from must be identical to what git has, so a future edit to this test that accidentally writes in place is caught here rather than in another repo.
    git = harness.require_tool("git", "install git")
    result = harness.run(
        [git, "-C", str(paths.repo_root()), "status", "--porcelain", "--", BP_RELPATH]
    )
    gate.assert_exit_code(0, result.rc, "git status must be readable for this claim")
    gate.assert_eq(result.out.strip(), "", "the vendored breakpoint validator is unmodified")
    gate.log_pass("the drift-locked breakpoint copy was not written to")
