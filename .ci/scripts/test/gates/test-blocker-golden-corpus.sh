#!/bin/bash
# THREE-WAY GOLDEN CORPUS for the BLOCKER quality validator.
#
# WHAT THIS IS FOR. The same rule -- "a BLOCKER reason must be substantive" --
# is implemented three times in this tree:
#
#   scripts/lib/blocker-validator.ts          the TypeScript gates
#   .ci/scripts/lib/blocker-validator.sh      the bash gates
#   .ci/breakpoint/lib/breakpoint-blocker.sh  a DELIBERATELY vendored subset
#
# They are scheduled to collapse into one. A collapse with nothing to prove
# equivalence against is a rewrite, and a rewrite of a validator is exactly the
# change whose regressions are invisible: a phrase quietly dropped from the
# banned list does not break anything, it just starts accepting "# ok" again.
#
# So this file RECORDS TODAY'S BEHAVIOUR, before the collapse, as a table of
# twenty cases and the verdict each implementation gives each one. After the
# collapse the table must still reproduce, or the change is not a collapse.
# Recorded 2026-09-06 against the three files above.
#
# THE DIVERGENCE IS PART OF THE RECORD, not a defect to fix here. The breakpoint
# copy is a documented SUBSET -- it is vendored into other repositories and must
# not take a dependency on emit-advisory.sh -- and it therefore differs on five
# of the twenty cases:
#
#   * three where its trimmed phrase list misses the phrase, so the reason is
#     rejected for being TOO SHORT instead of for being a placeholder. Same
#     verdict, different reason, and the reason is what the author reads.
#   * two where it has no substring list at all, so a "deferred to a dedicated
#     dependency-bump PR" reason it accepts is one the canonical validator
#     REJECTS. That is a real verdict-level difference and the collapse has to
#     decide about it deliberately rather than discover it.
#
# NEVER EDIT .ci/breakpoint/lib/breakpoint-blocker.sh. It is drift-locked
# (check-breakpoint-drift.sh) and vendored downstream. The perturbation control
# below works on a temp COPY for exactly that reason.
#
# Run with --emit to print the observed table instead of asserting, which is how
# the corpus is re-recorded after a deliberate behaviour change.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

TS_LIB="$REPO_ROOT/scripts/lib/blocker-validator.ts"
SH_LIB="$REPO_ROOT/.ci/scripts/lib/blocker-validator.sh"
BP_LIB="$REPO_ROOT/.ci/breakpoint/lib/breakpoint-blocker.sh"

# ---------------------------------------------------------------------------
# THE CORPUS.  <case-id>|<reason>|<ts>|<sh>|<bp>
#
# Verdicts are `accept` or `reject:<kind>`. The seven `real-*` rows are VERBATIM
# BLOCKER reasons from the live allowlists (.deps-upgrade-blocklist,
# .go-deps-upgrade-blocklist, .dead-bash-allowlist, .ci-parity-exempt,
# .unverified-download-allowlist, .audit-prod-allowlist), because a corpus of
# invented strings proves the validator agrees about strings nobody writes. The
# rest are the boundaries: banned phrases exact and after normalisation, the
# 30-character floor from both sides, the substring class, and the empty reason.
#
# No field may contain a `|`.
# ---------------------------------------------------------------------------
read -r -d '' CORPUS <<'EOF' || true
real-deps-eslint|v10.x requires eslint v10; typescript-eslint/import/react plugins lack v10 peer dep support|accept|accept|accept
real-deps-astro|6.x is a major on the Astro integration stack while astro itself is deliberately held on the 5 line; move it with that migration, not standalone.|accept|accept|accept
real-go-landlock|v0.9.0 is a 0.x minor that can change the Landlock config API; this gates repo-sandbox isolation, so adoption needs sandbox-behavior validation on a live cluster before bumping|accept|accept|accept
real-dead-bash|iterated as a glob by run.sh (for script in tutorials_dir/tutorial-*.sh) and by the readdirSync scans in scripts/check-tutorial-commands.ts and check-tutorial-noninteractive.ts|accept|accept|accept
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
EOF

# Write the corpus reasons, one per line, to $1. Reasons never contain newlines,
# which is what makes line-per-case safe for all three runners.
write_reasons() {
    local out="$1" line
    : >"$out"
    while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        local rest="${line#*|}"
        printf '%s\n' "${rest%%|*}" >>"$out"
    done <<<"$CORPUS"
}

# read_lines <array-name>  -- fill the named array from stdin, one element per
# line. Stands in for `mapfile -t`, which check:ci-shell-commands refuses because
# it is bash-4-only and these tests also run on minimal CI images. A trailing
# line without a newline is kept, which matters for the empty-reason case.
read_lines() {
    local -n _arr="$1"
    _arr=()
    local line
    while IFS= read -r line || [[ -n "$line" ]]; do
        _arr+=("$line")
    done
}

corpus_ids() { awk -F'|' 'NF{print $1}' <<<"$CORPUS"; }
# Fields are 1=id 2=reason 3=ts 4=sh 5=bp, so column 0 is field 3.
corpus_expected() { awk -F'|' -v c="$1" 'NF{print $(3+c)}' <<<"$CORPUS"; }
corpus_size() { grep -c . <<<"$CORPUS"; }

# --- the three runners ------------------------------------------------------
# Each prints one verdict per corpus line, in order. The kind is read back out
# of the implementation's own message rather than assumed, so a message that
# stops naming its reason shows up as UNCLASSIFIED instead of passing silently.

run_ts() {
    local lib="$1" reasons="$2" f rc=0
    f="$(mktemp "${TMPDIR:-/tmp}/blocker-ts-XXXXXX.ts")"
    cat >"$f" <<TS
import fs from 'node:fs';
import { validateBlockerQuality } from '$lib';
const raw = fs.readFileSync('$reasons', 'utf-8').split('\n');
if (raw.length && raw[raw.length - 1] === '') raw.pop();
for (const reason of raw) {
  const r = validateBlockerQuality('ENTRY', reason, 'FILE');
  process.stdout.write((r === null ? 'accept' : 'reject:' + r.kind) + '\n');
}
TS
    (cd "$REPO_ROOT" && "$REPO_ROOT/node_modules/.bin/tsx" "$f") || rc=$?
    rm -f "$f"
    return $rc
}

run_sh() {
    local lib="$1" reasons="$2"
    bash -c '
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
    ' _ "$lib" "$reasons"
}

run_bp() {
    local lib="$1" reasons="$2"
    bash -c '
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
    ' _ "$lib" "$reasons" "$REPO_ROOT/.ci/breakpoint/lib/breakpoint-common.sh"
}

# compare_column <column-index 0..2> <label> <actual-file> -- prints mismatches,
# returns 1 if any.
compare_column() {
    local col="$1" label="$2" actual="$3"
    # read_lines rather than mapfile: check:ci-shell-commands refuses bash-4-only
    # builtins here, because these tests also run on minimal CI images.
    local -a ids expected got
    read_lines ids < <(corpus_ids)
    read_lines expected < <(corpus_expected "$col")
    read_lines got <"$actual"

    if ((${#got[@]} != ${#ids[@]})); then
        log_error "$label produced ${#got[@]} verdict(s) for ${#ids[@]} case(s)"
        return 1
    fi
    local bad=0 i
    for i in "${!ids[@]}"; do
        if [[ "${got[$i]}" != "${expected[$i]}" ]]; then
            log_error "$label  ${ids[$i]}: recorded '${expected[$i]}', got '${got[$i]}'"
            bad=1
        fi
    done
    return $bad
}

# --- cases ------------------------------------------------------------------

test_corpus_is_large_enough_and_real() {
    local n reals
    n=$(corpus_size)
    ((n >= 14)) || {
        log_error "corpus has $n cases; the recorded floor is 14"
        exit 1
    }
    reals=$(corpus_ids | grep -c '^real-')
    ((reals >= 5)) || {
        log_error "corpus has $reals verbatim entries from live allowlists; at least 5 are required"
        exit 1
    }
    log_pass "corpus holds $n cases, $reals of them verbatim BLOCKER reasons from live allowlists"
}

test_three_way_reproduction() {
    local d
    d="$(mktemp -d)"
    write_reasons "$d/reasons"

    run_ts "$TS_LIB" "$d/reasons" >"$d/ts" 2>"$d/ts.err"
    run_sh "$SH_LIB" "$d/reasons" >"$d/sh" 2>"$d/sh.err"
    run_bp "$BP_LIB" "$d/reasons" >"$d/bp" 2>"$d/bp.err"

    local ok=0
    compare_column 0 "typescript" "$d/ts" || ok=1
    compare_column 1 "bash      " "$d/sh" || ok=1
    compare_column 2 "breakpoint" "$d/bp" || ok=1
    if ((ok != 0)); then
        log_error "the golden corpus no longer reproduces. If the change was deliberate, re-record with: $0 --emit"
        rm -rf "$d"
        exit 1
    fi

    # Nothing may land in the UNCLASSIFIED bucket: that is a rejection whose
    # message stopped naming its own reason, which is how a validator turns into
    # something an author cannot act on.
    if grep -q UNCLASSIFIED "$d/ts" "$d/sh" "$d/bp"; then
        log_error "an implementation rejected a case without a recognisable reason in its message"
        rm -rf "$d"
        exit 1
    fi
    rm -rf "$d"
    log_pass "all three implementations reproduce the recorded corpus byte for byte"
}

test_recorded_divergence_is_still_exactly_five() {
    # The corpus is also the RECORD of how far the vendored subset drifts. If the
    # breakpoint copy silently gained or lost a phrase, the divergence count moves
    # and this fires -- which is the only place that drift is visible, since the
    # subset assertion in test-breakpoint-portability.sh checks containment, not
    # behaviour.
    local n
    n=$(awk -F'|' 'NF && $3 != $5' <<<"$CORPUS" | wc -l)
    assert_eq "$n" "5" "the breakpoint subset diverges from canonical on exactly the recorded cases"
    local same
    same=$(awk -F'|' 'NF && $3 != $4' <<<"$CORPUS" | wc -l)
    assert_eq "$same" "0" "typescript and bash agree on every case, which is what makes them collapsible"
    log_pass "recorded drift: breakpoint differs on 5 of $(corpus_size); TS and bash differ on none"
}

# --- the perturbation controls ---------------------------------------------
# A corpus that cannot fail records nothing. Each control copies ONE
# implementation, breaks it in the smallest realistic way (a phrase dropped from
# the banned list -- precisely what a careless collapse does), and requires the
# comparison to notice. The copies are temp files; no tracked file is touched,
# and the breakpoint original is never opened for writing.

test_perturbing_typescript_is_caught() {
    local d rc=0
    d="$(mktemp -d)"
    write_reasons "$d/reasons"
    # Drop exactly one phrase from the banned list, which is what a careless
    # collapse does. 'tbd' is chosen because two corpus cases depend on it -- the
    # bare phrase and the normalised '  TBD  ' -- so the control also proves the
    # normalisation path is being exercised rather than only the literal one.
    sed "s/^  'tbd',$//" "$TS_LIB" >"$d/perturbed.ts"
    grep -q "^  'wip',$" "$d/perturbed.ts" || {
        log_error "the perturbation did not land: the TS banned list no longer has the shape this sed targets"
        exit 1
    }
    run_ts "$d/perturbed.ts" "$d/reasons" >"$d/ts" 2>/dev/null
    compare_column 0 "typescript(perturbed)" "$d/ts" 2>/dev/null || rc=1
    rm -rf "$d"
    assert_eq "$rc" "1" "dropping one banned phrase from the TS list must break the corpus"
    log_pass "control: a perturbed TypeScript validator fails the corpus"
}

test_perturbing_bash_is_caught() {
    local d rc=0
    d="$(mktemp -d)"
    write_reasons "$d/reasons"
    # The canonical bash lib sources emit-advisory.sh from its own directory, so
    # the copy needs its sibling beside it.
    cp "$REPO_ROOT/.ci/scripts/lib/emit-advisory.sh" "$d/emit-advisory.sh"
    sed 's/"tbd" "wip"/"wip"/' "$SH_LIB" >"$d/perturbed.sh"
    run_sh "$d/perturbed.sh" "$d/reasons" >"$d/sh" 2>/dev/null
    compare_column 1 "bash(perturbed)" "$d/sh" 2>/dev/null || rc=1
    rm -rf "$d"
    assert_eq "$rc" "1" "dropping one banned phrase from the bash list must break the corpus"
    log_pass "control: a perturbed bash validator fails the corpus"
}

test_perturbing_breakpoint_copy_is_caught() {
    local d rc=0
    d="$(mktemp -d)"
    write_reasons "$d/reasons"
    # A COPY. .ci/breakpoint/lib/breakpoint-blocker.sh is drift-locked and
    # vendored into other repositories; this test never writes to it.
    sed 's/"tbd" "wip"/"wip"/' "$BP_LIB" >"$d/perturbed.sh"
    run_bp "$d/perturbed.sh" "$d/reasons" >"$d/bp" 2>/dev/null
    compare_column 2 "breakpoint(perturbed)" "$d/bp" 2>/dev/null || rc=1
    rm -rf "$d"
    assert_eq "$rc" "1" "dropping one banned phrase from the vendored subset must break the corpus"
    log_pass "control: a perturbed breakpoint copy fails the corpus (original untouched)"
}

test_breakpoint_original_is_untouched() {
    # Belt and braces on the rule above: the file the three controls copy from
    # must be identical to what git has, so a future edit to this test that
    # accidentally writes in place is caught here rather than in another repo.
    local dirty
    dirty=$(cd "$REPO_ROOT" && git status --porcelain -- .ci/breakpoint/lib/breakpoint-blocker.sh)
    assert_eq "$dirty" "" "the vendored breakpoint validator is unmodified"
    log_pass "the drift-locked breakpoint copy was not written to"
}

emit_table() {
    local d
    d="$(mktemp -d)"
    write_reasons "$d/reasons"
    run_ts "$TS_LIB" "$d/reasons" >"$d/ts" 2>/dev/null
    run_sh "$SH_LIB" "$d/reasons" >"$d/sh" 2>/dev/null
    run_bp "$BP_LIB" "$d/reasons" >"$d/bp" 2>/dev/null
    local -a ids reasons ts sh bp
    read_lines ids < <(corpus_ids)
    read_lines reasons <"$d/reasons"
    read_lines ts <"$d/ts"
    read_lines sh <"$d/sh"
    read_lines bp <"$d/bp"
    local i
    for i in "${!ids[@]}"; do
        printf '%s|%s|%s|%s|%s\n' "${ids[$i]}" "${reasons[$i]}" "${ts[$i]}" "${sh[$i]}" "${bp[$i]}"
    done
    rm -rf "$d"
}

if [[ "${1:-}" == "--emit" ]]; then
    emit_table
    exit 0
fi

log_test "test-blocker-golden-corpus"
test_corpus_is_large_enough_and_real
test_three_way_reproduction
test_recorded_divergence_is_still_exactly_five
test_perturbing_typescript_is_caught
test_perturbing_bash_is_caught
test_perturbing_breakpoint_copy_is_caught
test_breakpoint_original_is_untouched
echo ""
log_pass "all tests passed"
