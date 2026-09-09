"""Port of `.ci/scripts/test/gates/test-shadow-gate.sh`.

The shadow comparator (`scripts/lib/shadow-gate.ts`) proves ports equivalent, so the
question this file exists to answer is who proves the comparator.

WHY THAT IS THE WHOLE POINT. A comparator that cannot report a mismatch is worse than
no comparator, because it does not merely fail to help -- it LAUNDERS every port that
follows it. Seventy-four bash quality gates and 131 gate tests are scheduled to move
behind this thing. If it says EQUIVALENT unconditionally, all 205 of those moves
acquire a green artifact and nobody looks again. The failure would be silent, would
look like success, and would be discovered as a missing gate months later.

So this asserts in BOTH directions, and neither is optional:

  IT MUST FIRE.  Real divergences, on real code, are reported and NAMED. Three kinds:
                 a documented divergence between two live implementations, a one-line
                 plant, and total blindness.
  IT MUST BE QUIET. A genuine match across language, stream, marker and order is
                 EQUIVALENT. Without this half, "always mismatch" passes every firing
                 test and is equally useless.
  ITS OWN SELFTEST MUST BE ABLE TO FAIL. Three MUTATION CONTROLS break one
                 load-bearing line each in a COPY of the module and require the copy's
                 selftest to go red.

THE PILOT PAIR IS REAL, NOT A FIXTURE. `.ci/scripts/lib/blocker-validator.sh` and
`scripts/lib/blocker-validator.ts` are two live implementations of one rule.
`.ci/breakpoint/lib/breakpoint-blocker.sh` is a third, DELIBERATELY a subset, and its
five recorded divergences are used here as a divergence nobody planted. The corpus is
lifted verbatim from `test-blocker-golden-corpus.sh`.

NOTHING HERE WRITES TO THE TRACKED TREE. Every fixture, every mutated copy and every
ledger lives under pytest's own `tmp_path`. `.ci/breakpoint/**` is READ and never
written, which matters because invariant 8 forbids any sweep from touching it: the
vendored subset is an INPUT to the divergence case, not a subject of it.

WHY EACH CASE REBUILDS ITS FIXTURES. The twin builds the corpus and the two gate
wrappers ONCE at the bottom of the file and every case shares them. Here each case
builds its own under `tmp_path`, which costs a few `sed`-equivalents and buys the
property the twin gets only by never mutating them: no case can inherit another's
state. The `setup_k_repo` cases already needed it -- the twin's own comment records
that reusing one path left an uncommitted file behind and made every later recording
refuse for the previous test's reason.

WHERE THIS REIMPLEMENTS sed, grep, awk, sort, wc AND cmp, AND WHY THE ANSWERS AGREE.

  `sed -n "/^read -r -d '' CORPUS/,/^EOF$/p" | grep -v "^read -r\\|^EOF" | grep . |
   awk -F'|' '{print $1"|"$2}'`
  is a RANGE extraction, two line filters and a field rejoin. The range is inclusive
  of both anchors and the two `grep -v` alternatives then remove exactly those two
  anchors again, so `corpus_rows` below slices between them and skips blanks --
  identical membership. `awk -F'|' '{print $1"|"$2}'` keeps the first two
  PIPE-separated fields and DROPS the rest, which is `split("|")[:2]` rejoined; a
  row with only one field prints `id|` because awk's `$2` is the empty string, and
  the Python form pads to two for the same reason.

  `grep -c '^  only-old '` counts LINES beginning with that literal, two leading
  spaces included. `grep -c '^PASS: '` likewise. Neither counts occurrences.

  `grep -o 'fp=[0-9a-f]*' | sort -u | wc -l` counts DISTINCT fingerprints, which is
  `len(set(re.findall(...)))`. `sort -u | wc -l` on an empty input is 0 and so is
  `len(set())`, so the "reported with 0 distinct fingerprints" diagnostic survives.

  `grep -q 'ratio=0\\.[0-8]'` is an unanchored regex, kept as one.

  `cmp -s a b` is byte equality, which is `read_bytes() == read_bytes()`.

  `grep -c .` counts NON-EMPTY lines, not bytes and not all lines.

THE STREAMS ARE KEPT APART. The twin says why and it is worth repeating: a stream
swap is a class of defect this repo has actually shipped, and `2>&1` is how a test
stops being able to see it. Every case below reads `.out` or `.err`, never
`.combined`, in the same places the twin reads `$SG_OUT` or `$SG_ERR`.

`node_modules/.bin/tsx` IS USED RATHER THAN `npx`, and that is not a preference: npx
re-resolves the package on every call and prints an unrelated "Unknown project config
minimum-release-age" warning on STDERR, which would land in output this file asserts
on. Its absence is a loud failure naming `npm install`.

NO `xdist_group`. Every fixture, mutant and ledger repository is under `tmp_path`;
the only writes outside it are none.
"""

import pathlib
import re
import shutil

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-shadow-gate.sh"

ROOT = paths.repo_root()
LIB = ROOT / "scripts" / "lib" / "shadow-gate.ts"
TSX = ROOT / "node_modules" / ".bin" / "tsx"
GOLDEN = ROOT / ".ci" / "scripts" / "test" / "gates" / "test-blocker-golden-corpus.sh"
BASH_VALIDATOR = ROOT / ".ci" / "scripts" / "lib" / "blocker-validator.sh"
TS_VALIDATOR = ROOT / "scripts" / "lib" / "blocker-validator.ts"
BP_VALIDATOR = ROOT / ".ci" / "breakpoint" / "lib" / "breakpoint-blocker.sh"
BP_COMMON = ROOT / ".ci" / "breakpoint" / "lib" / "breakpoint-common.sh"

CORPUS_OPEN = "read -r -d '' CORPUS"
CORPUS_CLOSE = "EOF"

GATE_BASH = """#!/bin/bash
set -uo pipefail
LIB="$1"; CORPUS="$2"
source "$LIB"
n=0
while IFS='|' read -r id reason; do
    [ -z "$id" ] && continue
    if out=$(validate_blocker_quality "$id" "$reason" "corpus.txt" 2>&1); then continue; fi
    case "$out" in
        *"low-effort placeholder"*) kind="low-effort" ;;
        *"defers a routine bump"*)  kind="deferral" ;;
        *"is too short"*)           kind="too-short" ;;
        *)                          kind="UNCLASSIFIED" ;;
    esac
    echo "✗ corpus.txt: $id rejected as $kind" >&2
    n=$((n+1))
done < "$CORPUS"
echo "→ $n rejected reason(s)"
[ "$n" -eq 0 ] || exit 1
"""

# The vendored SUBSET. Never edited -- it is drift-locked by
# check-breakpoint-drift.sh and vendored into other repositories. READ ONLY.
GATE_BP = """#!/bin/bash
set -uo pipefail
LIB="$1"; CORPUS="$2"; COMMON="$3"
source "$COMMON" >/dev/null 2>&1
source "$LIB"
n=0
while IFS='|' read -r id reason; do
    [ -z "$id" ] && continue
    if out=$(bp_validate_blocker "$id" "$reason" 2>&1); then continue; fi
    case "$out" in
        *"low-effort placeholder"*) kind="low-effort" ;;
        *"is too short"*)           kind="too-short" ;;
        *)                          kind="UNCLASSIFIED" ;;
    esac
    echo "✗ corpus.txt: $id rejected as $kind" >&2
    n=$((n+1))
done < "$CORPUS"
echo "→ $n rejected reason(s)"
[ "$n" -eq 0 ] || exit 1
"""

# The TypeScript twin, in gate shape. DELIBERATELY DIFFERENT on every axis a port is
# allowed to differ on: `::error::` instead of the cross, stdout instead of stderr,
# reverse order, and a different progress line. If the comparator scores this as a
# mismatch it is comparing bytes, and every real port would be red.
GATE_TS = """import fs from 'node:fs';
async function main(): Promise<number> {
  const [lib, corpus] = process.argv.slice(2);
  const { validateBlockerQuality } = await import(lib);
  const rows = fs.readFileSync(corpus, 'utf-8').split('\\n').filter((l) => l.trim() !== '');
  const out: string[] = [];
  for (const row of rows) {
    const i = row.indexOf('|');
    const r = validateBlockerQuality(row.slice(0, i), row.slice(i + 1), 'corpus.txt');
    if (r !== null) out.push(`::error::corpus.txt: ${row.slice(0, i)} rejected as ${r.kind}`);
  }
  process.stdout.write(`→ inspected ${rows.length} entries in 7ms\\n`);
  for (const line of out.reverse()) process.stdout.write(`${line}\\n`);
  return out.length === 0 ? 0 : 1;
}
main().then((c) => process.exit(c));
"""

# A two-implementation "gate" that agrees: one reports with the cross on stderr, the
# other with `::error::` on stdout in reverse order.
TINY_GATE = """#!/bin/bash
set -uo pipefail
FIX="$1"; SIDE="$2"
lines=$(grep -c . "$FIX" || true)
if [ "$SIDE" = old ]; then
    while IFS= read -r id; do [ -n "$id" ] && echo "✗ fixture.txt: $id is bad" >&2; done <"$FIX"
else
    echo "→ $lines entries"
    # REVERSED ON PURPOSE: this side must emit the same findings in the opposite
    # ORDER, which is what proves the comparator compares sets and not sequences.
    # `tac` did this until 2026-09-06, when check:ci-shell-commands named it as
    # unavailable in the minimal CI image. The sed is the POSIX reverse idiom.
    sed -n '1!G;h;$p' "$FIX" | while IFS= read -r id; do [ -n "$id" ] && echo "::error::fixture.txt: $id is bad"; done
fi
[ "$lines" -eq 0 ] || exit 1
"""

FP_RE = re.compile(r"fp=[0-9a-f]*")
RATIO_RE = re.compile(r"ratio=0\.[0-8]")

# The fixture identity used by .ci/scripts/test/lib/git-fixture.sh. `-c` rather than a
# config write, so nothing depends on the developer's identity and
# .claude/hooks/pre-bash/block-unlinked-commit-author.sh has a recognised address.
GIT_IDENTITY = (
    "-c",
    "user.email=fixture@example.invalid",
    "-c",
    "user.name=git-fixture",
    "-c",
    "commit.gpgsign=false",
)


def require(gate) -> None:
    harness.require_tool("git", "install git")
    if not TSX.is_file():
        gate.log_fail("tsx not installed at %s (run npm install)" % TSX)
    if not LIB.is_file():
        gate.log_fail("the subject is missing: %s" % LIB)


def sg(gate, *argv: str, subject: pathlib.Path | None = None) -> harness.RunResult:
    """The comparator, from the REPO root, stdout and stderr kept APART."""
    require(gate)
    return harness.run([str(TSX), str(subject or LIB), *argv], cwd=ROOT, timeout=900)


def corpus_rows(gate) -> list[str]:
    """The recorded corpus, `id|reason`, exactly the twin's four-stage pipeline."""
    if not GOLDEN.is_file():
        gate.log_fail("the recorded corpus is missing: %s" % GOLDEN)
    lines = GOLDEN.read_text(encoding="utf-8").splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith(CORPUS_OPEN)), None)
    if start is None:
        gate.log_fail(
            "%s no longer opens its corpus with %r, so the extraction below would take "
            "nothing and every case would be vacuous" % (GOLDEN.name, CORPUS_OPEN)
        )
    end = next((i for i in range(start + 1, len(lines)) if lines[i] == CORPUS_CLOSE), None)
    if end is None:
        gate.log_fail("%s's corpus heredoc never closes at `EOF`" % GOLDEN.name)
    rows = []
    for line in lines[start + 1 : end]:
        if not line.strip():
            continue
        fields = line.split("|")
        while len(fields) < 2:
            fields.append("")
        rows.append("%s|%s" % (fields[0], fields[1]))
    # A collapsed corpus would make every case below vacuously green.
    if len(rows) < 14:
        gate.log_fail("corpus collapsed to %d case(s); the recorded floor is 14" % len(rows))
    return rows


class Fixtures:
    """The corpus, both gate wrappers and the three command strings."""

    def __init__(self, gate, directory: pathlib.Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        rows = corpus_rows(gate)
        self.corpus = directory / "corpus.txt"
        self.corpus.write_text("\n".join(rows) + "\n", encoding="utf-8")
        # The accepting subset: nothing for either side to find. This is the tree a
        # blind port gets blessed on, which is why rule 2 has to refuse it.
        clean = [r for r in rows if r.startswith(("real-", "len-30"))]
        self.corpus_clean = directory / "corpus-clean.txt"
        self.corpus_clean.write_text("\n".join(clean) + "\n", encoding="utf-8")

        self.gate_bash = directory / "gate-bash.sh"
        self.gate_bash.write_text(GATE_BASH, encoding="utf-8")
        self.gate_bp = directory / "gate-bp.sh"
        self.gate_bp.write_text(GATE_BP, encoding="utf-8")
        self.gate_ts = directory / "gate-ts.ts"
        self.gate_ts.write_text(GATE_TS, encoding="utf-8")

        self.old_side = "bash %s %s %s" % (self.gate_bash, BASH_VALIDATOR, self.corpus)
        self.new_side = "%s %s %s %s" % (TSX, self.gate_ts, TS_VALIDATOR, self.corpus)
        self.bp_side = "bash %s %s %s %s" % (
            self.gate_bp,
            BP_VALIDATOR,
            self.corpus,
            BP_COMMON,
        )

    def ts_side(self, module: pathlib.Path, corpus: pathlib.Path | None = None) -> str:
        return "%s %s %s %s" % (TSX, self.gate_ts, module, corpus or self.corpus)


def count_prefix(text: str, prefix: str) -> int:
    return len([line for line in text.splitlines() if line.startswith(prefix)])


def test_selftest_battery(gate):
    result = sg(gate, "--selftest")
    gate.assert_exit_code(0, result.rc, "the module selftest must pass")
    controls = count_prefix(result.out, "PASS: ")
    # A FLOOR, not an exact count, so new cases may be added -- but a selftest that
    # quietly shrinks to two cases is the shape this whole file distrusts.
    if controls < 20:
        gate.log_fail("the selftest made %d assertion(s); the recorded floor is 20" % controls)
    if result.err:
        gate.log_fail("a passing selftest wrote to stderr: %s" % result.err)
    gate.log_pass(
        "the comparator's selftest passes with %d assertions and a silent stderr" % controls
    )


def assert_mutation_is_caught(
    gate, tmp_path: pathlib.Path, label: str, old: str, new: str, must_fail: str
) -> None:
    """Break ONE load-bearing line in a COPY and require the selftest to notice."""
    copy = tmp_path / ("mutant-%s.ts" % label)
    source = LIB.read_text(encoding="utf-8")
    if source.count(old) != 1:
        gate.log_fail(
            "the %s mutation anchor appears %d time(s) in %s, not once; the mutation no "
            "longer matches and this control would prove nothing"
            % (label, source.count(old), LIB.name)
        )
    copy.write_text(source.replace(old, new), encoding="utf-8")
    if copy.read_bytes() == LIB.read_bytes():
        gate.log_fail("the %s mutation changed nothing; the anchor no longer matches" % label)
    result = sg(gate, "--selftest", subject=copy)
    if result.rc == 0:
        gate.log_fail(
            "the %s mutation was NOT caught: a broken comparator's selftest passed" % label
        )
    if must_fail not in result.err:
        gate.log_fail(
            "the %s mutation went red, but not on '%s'; got: %s" % (label, must_fail, result.err)
        )
    gate.log_pass(
        "MUTATION CONTROL: breaking %s turns the selftest red on '%s'" % (label, must_fail)
    )


def test_mutation_controls(gate, tmp_path):
    # Rule 2. With the vacuity branch dead, both-empty falls through to the equality
    # test and is scored EQUIVALENT -- the exact laundering this module prevents.
    assert_mutation_is_caught(
        gate,
        tmp_path,
        "the-vacuity-rule",
        "if (oldRun.findings.length === 0 && newRun.findings.length === 0) {",
        "if (false) {",
        "RULE 2",
    )
    # Rule 3. With the blindness branch dead, a port that sees nothing is filed under
    # MISMATCH_EXIT, where a reviewer reads it as a numeric quibble.
    assert_mutation_is_caught(
        gate,
        tmp_path,
        "the-blindness-rule",
        "if (newClean && !oldClean) {",
        "if (false) {",
        "RULE 3",
    )
    # Invariant 5. With the K test dead, forty runs on one checkout satisfy K=40.
    assert_mutation_is_caught(
        gate,
        tmp_path,
        "invariant-5",
        "if (distinctTrees.length < k) {",
        "if (false) {",
        "INVARIANT 5",
    )


def test_real_pair_is_equivalent(gate, tmp_path):
    fx = Fixtures(gate, tmp_path)
    result = sg(gate, "--pair", "t-match", "--old", fx.old_side, "--new", fx.new_side)
    gate.assert_exit_code(0, result.rc, "the two live implementations must be EQUIVALENT")
    gate.assert_contains(result.out, "EQUIVALENT", "the verdict")
    gate.assert_contains(result.out, "agreeing finding(s)", "the summary names the agreeing set")
    # Both fingerprints equal is the strong form: identical normalized sets, not merely
    # sets the diff happened not to separate.
    fingerprints = len(set(FP_RE.findall(result.out)))
    if fingerprints != 1:
        gate.log_fail("EQUIVALENT was reported with %d distinct fingerprints" % fingerprints)
    gate.log_pass("bash and TypeScript twins agree across stream, marker, order and wording")


def test_real_pair_divergence_is_named(gate, tmp_path):
    fx = Fixtures(gate, tmp_path)
    result = sg(gate, "--pair", "t-diverge", "--old", fx.old_side, "--new", fx.bp_side)
    if result.rc != 1:
        gate.log_fail("a real divergence must exit 1, got %d" % result.rc)
    gate.assert_contains(result.out, "MISMATCH_FINDINGS", "the verdict")
    # The five recorded divergences: three where the vendored subset rejects for a
    # different REASON, and two where it accepts what the canonical validator rejects.
    only_old = count_prefix(result.out, "  only-old ")
    only_new = count_prefix(result.out, "  only-new ")
    if only_old != 5:
        gate.log_fail("expected 5 old-only findings, got %d" % only_old)
    if only_new != 3:
        gate.log_fail("expected 3 new-only findings, got %d" % only_new)
    gate.assert_contains(
        result.out, "defer-dedicated rejected as deferral", "the verdict-level divergence"
    )
    gate.assert_contains(
        result.out, "banned-no-fix rejected as too-short", "the reason-level divergence"
    )
    gate.log_pass(
        "the documented vendored-subset divergence is reported as 5 old-only and 3 "
        "new-only findings"
    )


def test_planted_dropped_finding(gate, tmp_path):
    fx = Fixtures(gate, tmp_path)
    # ONE banned substring removed from the port. Nothing else.
    #
    # RETARGETED 2026-09-09, and the twin carries the same note. This used to
    # delete a literal line from the port's own `LOW_EFFORT_BLOCKER_SUBSTRINGS`
    # array. That array is gone: the port reads the table from
    # `rediacc_ci.core.allowlist`, which is also what the bash OLD side reads, so
    # a plant in the shared table would move BOTH sides and produce no divergence
    # at all. The plant therefore sits in the part of the port that is still the
    # port's, the loop that consumes the table. Behaviourally identical defect,
    # unchanged assertions below.
    anchor = "  for (const pattern of c.substrings) {"
    source = TS_VALIDATOR.read_text(encoding="utf-8")
    if source.count(anchor) != 1:
        gate.log_fail("the plant changed nothing; the substring loop moved")
    planted = tmp_path / "planted-drop.ts"
    planted.write_text(
        source.replace(
            anchor,
            "  for (const pattern of c.substrings.filter("
            "(p) => p !== 'deferred to a dedicated dependency-bump pr')) {",
        ),
        encoding="utf-8",
    )

    # REDIACC_CI_ROOT because the planted COPY lives in tmp_path and the port
    # resolves the canonical package relative to its own file. Without it the copy
    # would refuse to run, which is a divergence for the wrong reason.
    result = sg(
        gate,
        "--pair",
        "t-plant",
        "--old",
        fx.old_side,
        "--new",
        "REDIACC_CI_ROOT=%s %s" % (paths.repo_root(), fx.ts_side(planted)),
    )
    if result.rc != 1:
        gate.log_fail("a planted dropped finding must exit 1, got %d" % result.rc)
    gate.assert_contains(result.out, "MISMATCH_FINDINGS", "the verdict")
    gate.assert_contains(
        result.out,
        "only-old  [error] corpus.txt: defer-dedicated rejected as deferral",
        "the exact finding the plant removed",
    )
    # THE ARGUMENT FOR COMPARING FINDINGS AT ALL. Both sides still exit 1 here, so an
    # exit-code-only comparator blesses this port.
    gate.assert_contains(result.out, "exit codes agree at 1", "the exit codes still agree")
    gate.log_pass("a one-line plant is caught and named, while the exit codes still agree")


def blind_port(gate, tmp_path: pathlib.Path) -> pathlib.Path:
    anchor = "export function validateBlockerQuality("
    source = TS_VALIDATOR.read_text(encoding="utf-8")
    if anchor not in source:
        gate.log_fail(
            "the blindness plant's anchor is gone from %s, so this control would prove "
            "nothing" % TS_VALIDATOR.name
        )
    blind = tmp_path / "planted-blind.ts"
    blind.write_text(
        source.replace(anchor, "export function validateBlockerQuality_UNUSED(")
        + "export function validateBlockerQuality"
        "(_e: string, _r: string, _f: string): null { return null; }\n",
        encoding="utf-8",
    )
    return blind


def test_planted_blindness_is_new_side_true(gate, tmp_path):
    fx = Fixtures(gate, tmp_path)
    blind = blind_port(gate, tmp_path)
    result = sg(gate, "--pair", "t-blind", "--old", fx.old_side, "--new", fx.ts_side(blind))
    if result.rc != 1:
        gate.log_fail("a totally blind port must exit 1, got %d" % result.rc)
    gate.assert_contains(result.out, "NEW_SIDE_TRUE", "the blindness class is named as itself")
    gate.assert_not_contains(
        result.out, "MISMATCH_EXIT", "blindness must not be filed as an exit quibble"
    )
    gate.log_pass("a port that accepts everything is NEW_SIDE_TRUE, not a generic mismatch")


def test_both_empty_refuses_to_bless(gate, tmp_path):
    # THE SCENARIO THIS RULE EXISTS FOR, run on real code: the same totally blind port,
    # over a corpus with nothing to find. Exit 0 on both sides, no output on either.
    # Every equality-based comparator calls this equivalence.
    fx = Fixtures(gate, tmp_path)
    blind = blind_port(gate, tmp_path)
    result = sg(
        gate,
        "--pair",
        "t-vacuous",
        "--old",
        "bash %s %s %s" % (fx.gate_bash, BASH_VALIDATOR, fx.corpus_clean),
        "--new",
        fx.ts_side(blind, fx.corpus_clean),
    )
    if result.rc != 1:
        gate.log_fail("a both-empty comparison must not exit 0, got %d" % result.rc)
    gate.assert_contains(result.out, "VACUOUS_BOTH_EMPTY", "the verdict")
    gate.assert_contains(result.out, "proves nothing", "the message says why")
    gate.assert_not_contains(result.out, "EQUIVALENT", "a vacuous comparison is never equivalence")
    gate.log_pass("a blind port on a clean corpus is REFUSED, not blessed")


def test_refusal_suspends_the_comparison(gate, tmp_path):
    # A gate that could not run exits non-zero with zero findings, which is the same
    # shape as a clean run. Filing that under either heading sends the reader to the
    # wrong problem.
    fx = Fixtures(gate, tmp_path)
    result = sg(
        gate,
        "--pair",
        "t-refusal",
        "--old",
        fx.old_side,
        "--new",
        'echo "VACUOUS INPUT: /x is not a git work tree" >&2; exit 1',
    )
    if result.rc != 1:
        gate.log_fail("a refusal must not exit 0, got %d" % result.rc)
    gate.assert_contains(result.out, "ERROR_REFUSAL", "the verdict")
    gate.assert_contains(
        result.out, "refusal-new  VACUOUS INPUT", "the refusal text is echoed back"
    )
    gate.log_pass(
        "a gate refusing to report a verdict suspends the comparison instead of colouring it"
    )


def test_comment_ratio_is_recorded(gate, tmp_path):
    # Driver contract 5c: the differential artifact carries the comment-byte ratio, and
    # a port below 0.90 is refused. The two live implementations sit at roughly 0.63
    # today, so this pair also demonstrates the floor biting.
    fx = Fixtures(gate, tmp_path)
    result = sg(
        gate,
        "--pair",
        "t-comments",
        "--old",
        fx.old_side,
        "--new",
        fx.new_side,
        "--old-file",
        str(BASH_VALIDATOR),
        "--new-file",
        str(TS_VALIDATOR),
    )
    gate.assert_contains(result.out, "comments  old=", "the comment audit line")
    if not RATIO_RE.search(result.out):
        gate.log_fail("expected the recorded sub-0.90 ratio for this pair; got: %s" % result.out)
    gate.assert_contains(result.out, "below the 0.90 floor", "the floor is named when it is missed")
    gate.log_pass("the differential carries the comment-byte ratio and flags the 0.90 floor")


# ---------------------------------------------------------------------------
# The ledger: rule 4, and K distinct trees
# ---------------------------------------------------------------------------


def tgit(repo: pathlib.Path, *argv: str) -> harness.RunResult:
    binary = harness.require_tool("git", "install git")
    return harness.run([binary, "-C", str(repo), *GIT_IDENTITY, *argv], timeout=600)


def setup_k_repo(gate, tmp_path: pathlib.Path, name: str) -> tuple[pathlib.Path, pathlib.Path]:
    """(a fresh git fixture repo, the tiny gate to copy into it).

    A FRESH directory per caller. The twin's first version reused one path and the
    dirty-tree case left an uncommitted file behind, so the next case re-inited over
    it and every recording was refused for the previous test's reason.
    """
    require(gate)
    tiny = tmp_path / "tiny-gate.sh"
    tiny.write_text(TINY_GATE, encoding="utf-8")
    repo = tmp_path / ("k-repo-%s" % name)
    repo.mkdir(parents=True, exist_ok=True)
    tgit(repo, "init", "-q", "-b", "main")
    return repo, tiny


def record_tree(gate, repo: pathlib.Path, tiny: pathlib.Path, ids: str, message: str):
    """Record one observation over a fixture holding `ids`.

    THE TOY GATE IS COPIED INTO THE FIXTURE AND COMMITTED WITH IT, rather than invoked
    from outside. Both sides must live INSIDE the tree being recorded, because the tree
    id is the content of both implementations: a row recorded with either side outside
    it attests to code that tree never held. The comparator refuses that outright as of
    2026-09-06, so the old spelling exited 3 here -- correctly.
    """
    (repo / "fixture.txt").write_text(ids + "\n", encoding="utf-8")
    shutil.copy2(tiny, repo / "tiny-gate.sh")
    tgit(repo, "add", "-A")
    tgit(repo, "commit", "-q", "-m", message)
    return record(gate, repo)


def record(gate, repo: pathlib.Path) -> harness.RunResult:
    return sg(
        gate,
        "--repo",
        str(repo),
        "--pair",
        "k",
        "--old",
        "bash %s/tiny-gate.sh %s/fixture.txt old" % (repo, repo),
        "--new",
        "bash %s/tiny-gate.sh %s/fixture.txt new" % (repo, repo),
        "--record",
    )


def test_dirty_tree_is_refused_and_writes_nothing(gate, tmp_path):
    repo, tiny = setup_k_repo(gate, tmp_path, "dirty")
    record_tree(gate, repo, tiny, "alpha", "one")
    # Now dirty it. Nothing about the comparison changes; only the tree does.
    (repo / "scratch.txt").write_text("uncommitted\n", encoding="utf-8")
    result = sg(
        gate,
        "--repo",
        str(repo),
        "--pair",
        "dirty",
        "--old",
        "bash %s/tiny-gate.sh %s/fixture.txt old" % (repo, repo),
        "--new",
        "bash %s/tiny-gate.sh %s/fixture.txt new" % (repo, repo),
        "--record",
    )
    if result.rc != 3:
        gate.log_fail("a --record over a dirty tree must exit 3, got %d" % result.rc)
    gate.assert_contains(result.out, "EQUIVALENT", "the comparison itself still ran")
    gate.assert_contains(result.err, "DIRTY", "the refusal names the reason")
    gate.assert_contains(result.err, "scratch.txt", "the refusal names the offending path")
    if (repo / ".ci" / "shadow" / "dirty.jsonl").is_file():
        gate.log_fail("a dirty tree WROTE a ledger row")
    gate.log_pass(
        "rule 4: an EQUIVALENT comparison over a dirty tree is refused (exit 3) and writes nothing"
    )


def test_k_counts_distinct_trees_not_runs(gate, tmp_path):
    repo, tiny = setup_k_repo(gate, tmp_path, "k")
    # Three recordings, ONE tree. The comparison is identical every time.
    record_tree(gate, repo, tiny, "alpha", "t1")
    second = record(gate, repo)
    if second.rc != 0:
        gate.log_fail("the second recording on a clean tree should succeed, got %d" % second.rc)
    record(gate, repo)

    ledger = repo / ".ci" / "shadow" / "k.jsonl"
    rows = len([line for line in ledger.read_text(encoding="utf-8").splitlines() if line])
    if rows != 3:
        gate.log_fail("expected 3 ledger rows, found %d" % rows)

    result = sg(gate, "--repo", str(repo), "--pair", "k", "--assert", "--k", "3")
    if result.rc != 1:
        gate.log_fail("three runs on one tree must NOT satisfy K=3, got exit %d" % result.rc)
    gate.assert_contains(result.out, "1 distinct clean tree(s)", "the count is of trees, not rows")
    gate.assert_contains(result.err, "Invariant 5", "the refusal cites the invariant")
    gate.log_pass(
        "invariant 5: 3 ledger rows over 1 tree is 1 observation and does not satisfy K=3"
    )

    # Two more trees, each with a DIFFERENT finding set.
    record_tree(gate, repo, tiny, "beta\ngamma", "t2")
    record_tree(gate, repo, tiny, "delta\nepsilon\nzeta", "t3")
    result = sg(gate, "--repo", str(repo), "--pair", "k", "--assert", "--k", "3")
    if result.rc != 0:
        gate.log_fail(
            "three distinct trees with distinct findings must satisfy K=3: %s" % result.err
        )
    gate.assert_contains(result.out, "3 distinct clean tree(s)", "the tree count")
    gate.assert_contains(result.out, "3 distinct finding set(s)", "the fingerprint count")
    gate.log_pass("CONTROL: three distinct trees with three distinct finding sets satisfy K=3")


def test_reshaded_trees_do_not_count(gate, tmp_path):
    repo, tiny = setup_k_repo(gate, tmp_path, "reshade")
    record_tree(gate, repo, tiny, "alpha", "t1")
    # A new commit, a new TREE ID, and the gate's behaviour is untouched: the only
    # change is a file the comparison never reads. This is invariant 5 defeated by
    # whitespace, and the distinct-evidence rule is what refuses it.
    (repo / "README.md").write_text("unrelated\n", encoding="utf-8")
    record_tree(gate, repo, tiny, "alpha", "t2")
    (repo / "README.md").write_text("unrelated\nunrelated again\n", encoding="utf-8")
    record_tree(gate, repo, tiny, "alpha", "t3")

    result = sg(gate, "--repo", str(repo), "--pair", "k", "--assert", "--k", "3")
    if result.rc != 1:
        gate.log_fail("three re-shaded trees must NOT satisfy K=3, got exit %d" % result.rc)
    gate.assert_contains(result.out, "3 distinct clean tree(s)", "the trees really are distinct")
    gate.assert_contains(result.out, "1 distinct finding set(s)", "but they carry one observation")
    gate.assert_contains(result.err, "re-shaded", "the refusal names the mechanism")
    gate.log_pass(
        "distinct-evidence: 3 distinct tree ids carrying ONE finding set do not satisfy K=3"
    )


def test_a_mismatch_cannot_be_cleared_by_rerunning(gate, tmp_path):
    repo, tiny = setup_k_repo(gate, tmp_path, "mismatch")
    # Record a mismatch: the two sides disagree on this tree.
    (repo / "fixture.txt").write_text("alpha\n", encoding="utf-8")
    shutil.copy2(tiny, repo / "tiny-gate.sh")
    tgit(repo, "add", "-A")
    tgit(repo, "commit", "-q", "-m", "t1")
    sg(
        gate,
        "--repo",
        str(repo),
        "--pair",
        "k",
        "--old",
        "bash %s/tiny-gate.sh %s/fixture.txt old" % (repo, repo),
        "--new",
        'echo "✗ fixture.txt: something else is bad" >&2; exit 1',
        "--record",
    )
    # Now the honest comparison on the SAME tree, twice.
    record(gate, repo)
    record(gate, repo)

    result = sg(gate, "--repo", str(repo), "--pair", "k", "--assert", "--k", "1")
    if result.rc != 1:
        gate.log_fail(
            "a tree with a recorded mismatch must stay disqualified, got exit %d" % result.rc
        )
    gate.assert_contains(result.err, "DISQUALIFIED", "the tree is disqualified by name")
    gate.assert_contains(result.err, "cannot be cleared by re-running", "the message says so")
    gate.log_pass("no run-until-green: a recorded mismatch disqualifies its tree permanently")
