#!/bin/bash
# A gate test that WRITES INTO THE REAL TREE must be registered as a WRITER in
# .ci/scripts/test/run-all.sh. This gate catches the one that is not.
#
# THE DEFECT THIS COMES FROM, 2026-08-17. run-all.sh fans the gate battery out
# over the runner cores in three sets: W (writers, one serial chain, exclusive),
# S (scanners, read the real tree, released after W), and T (everything else,
# isolated by construction). test-generate-tag-inputs.sh swaps the REAL
# .ci/scripts/version/resolve-version.sh for a stub and restores it a second
# later, and it was classified T -- in the pool -- on the strength of its own
# comment, which claimed it "cannot disturb a shared tree". That was true of the
# tag namespace it carefully avoids writing and false of the working tree it
# overwrites.
#
# WHY THIS CLASS IS WORTH A GATE RATHER THAN A CODE REVIEW. The symptom is not a
# clean failure. A concurrent gate read resolve-version.sh mid-restore and
# reddened gate-test:claude-hooks with a bash syntax error in a file that parses
# clean and passes 884/0 serially. That is a CONCURRENCY ARTIFACT: it does not
# reproduce on the serial re-run, so the re-run "clears" it and the next session
# pays for the diagnosis again. docs/agent-reference/TRAPS.md carries the entry.
# The misclassification is invisible to every other gate in the repo, and it is
# cheap to make -- the run-all.sh comment says it outright: "Adding to this list
# is cheap; leaving something off it is a flake."
#
# WHY THIS SIGNAL AND NOT A BROADER ONE. "Detect a write to shared state" is not
# decidable in general, and a fuzzy version gets skimmed and then suppressed,
# which is the failure mode this repo keeps finding. So the rule is ONE
# mechanical shape, chosen because it is what all three real writers actually
# look like: a write whose TARGET PATH is rooted at a variable that derives from
# the repo root, and not at one that derives from mktemp.
#
# Two candidate signals were measured against the real battery and DROPPED for
# precision, both on evidence:
#   - `git tag` / `git commit` / `git add`: zero true positives (the one real
#     tag-namespace risk, test-generate-tag-inputs.sh, deliberately drives the
#     resolver instead of cutting a tag) and one guaranteed false positive at
#     test-age-check.sh:26-30, which runs git against a `git init` fixture in a
#     temp dir. Deciding that apart needs cwd tracking through a subshell.
#   - a literal repo-relative redirect (`>.ci/...`): zero true positives, and
#     its only match in the battery is a docs path inside a JS string literal at
#     test-scope-engine.sh:523. Matching inside strings is exactly the cry-wolf
#     shape.
# The surviving signal alone flags all three registered writers and nothing else
# across all 93 gate tests: measured false-positive rate zero.
#
# THE RULE IS ONE-DIRECTIONAL, deliberately. A file that writes must be declared;
# a file declared W that no longer writes is NOT reported. Over-declaring costs a
# little wall time, under-declaring manufactures a flake, and the gate should not
# push anybody toward the expensive side of that asymmetry.
#
# Usage: check-pool-writer-safety.sh
#
# Exit codes:
#   0 - every real-tree writer is registered in WRITER_TESTS
#   1 - an unregistered writer, or the gate could not prove itself (see CONTROL)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
# BLOCKER: shared log_* helpers and get_repo_root used by every quality gate
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

# Seams, so the CONTROL below can point the same scanner at planted fixtures.
GATES_DIR="${POOL_SAFETY_GATES_DIR:-$REPO_ROOT/.ci/scripts/test/gates}"
RUNNER="${POOL_SAFETY_RUNNER:-$REPO_ROOT/.ci/scripts/test/run-all.sh}"

# ---------------------------------------------------------------------------
# The scanner.
#
# Two passes over each file. Pass 1 classifies every variable as REPO-ROOTED or
# TEMP-ROOTED and propagates that through assignment; pass 2 reports writes
# aimed at a repo-rooted target. Two passes rather than one because a function
# body can textually precede the assignment of a global it uses.
#
# The taint SEED is the idiom, never the name: any variable assigned from
# `$(cd ... && pwd)`, `get_repo_root`, or `git rev-parse --show-toplevel`. That
# is what makes it self-maintaining -- 79 of the 93 gate tests spell it
# REPO_ROOT and 4 use get_repo_root, but a new file picking a different name is
# still caught. It also, correctly, taints SCRIPT_DIR: the gates directory is
# itself inside the real tree, so a write aimed there is a real-tree write.
#
# TEMP beats REPO in propagation. `ROOT="$FIXTURE/repo"` where
# `FIXTURE="$(mktemp -d)"` is a temp path even though the name looks like a root,
# and that exact pair is 15 of the 21 lines an earlier draft of this scanner got
# wrong before propagation was ordered this way.
#
# Heredoc bodies are stripped in both passes: 40 of the 93 gate tests carry a
# heredoc, and a redirect quoted inside one is text, not a write.
# ---------------------------------------------------------------------------
AWK_SCANNER='
function lastarg(line,   n, a) {
    n = split(line, a, /[ \t]+/)
    return a[n]
}
function nonflagargs(line,   n, a, i, out) {
    n = split(line, a, /[ \t]+/)
    out = ""
    for (i = 2; i <= n; i++) {
        if (a[i] ~ /^-/) continue
        out = out " " a[i]
    }
    return out
}
function reftype(txt,   rest, name, hasSafe, hasTaint) {
    hasSafe = 0
    hasTaint = 0
    rest = txt
    while (match(rest, /\$\{?[A-Za-z_][A-Za-z0-9_]*\}?/)) {
        name = substr(rest, RSTART, RLENGTH)
        gsub(/[${}]/, "", name)
        if (name in safe) hasSafe = 1
        else if (name in taint) hasTaint = 1
        rest = substr(rest, RSTART + RLENGTH)
    }
    if (hasSafe) return "safe"
    if (hasTaint) return "taint"
    return "none"
}
FNR == 1 { inhd = 0; hd = "" }
{
    line = $0
    if (inhd) {
        if (line ~ ("^[ \t]*" hd "[ \t]*$")) inhd = 0
        next
    }
    if (line ~ /^[ \t]*#/) next
    opened = 0
    if (line !~ /<<</ && match(line, /<<-?[ \t]*[\047"]?[A-Za-z_][A-Za-z0-9_]*/)) {
        tok = substr(line, RSTART, RLENGTH)
        sub(/^<<-?[ \t]*/, "", tok)
        gsub(/[\047"]/, "", tok)
        hd = tok
        opened = 1
    }

    if (NR == FNR) {
        # --- pass 1: classify assignments ---
        if (match(line, /^[ \t]*(local|declare|readonly|export|typeset)?[ \t]*[A-Za-z_][A-Za-z0-9_]*=/)) {
            head = substr(line, RSTART, RLENGTH)
            val = substr(line, RSTART + RLENGTH)
            sub(/=$/, "", head)
            sub(/^[ \t]*(local|declare|readonly|export|typeset)?[ \t]*/, "", head)
            if (val ~ /mktemp|TMPDIR|get_temp_dir|\/tmp\//) {
                safe[head] = 1
                delete taint[head]
            } else if (val ~ /\$\(cd .*pwd\)|rev-parse --show-toplevel|get_repo_root/) {
                taint[head] = 1
            } else {
                t = reftype(val)
                if (t == "safe") { safe[head] = 1; delete taint[head] }
                else if (t == "taint") { taint[head] = 1 }
            }
        }
    } else {
        # --- pass 2: report repo-rooted write targets ---
        tgt = ""
        # The file these WRITE is their last argument. Taking the whole line
        # instead reads the source path and, for sed, the expression -- which is
        # how an earlier draft flagged test-installmethods-args.sh:141, where
        # a real-tree dir appears in the REPLACEMENT TEXT while the file being
        # edited is a temp copy. That is a false positive of exactly the kind
        # that trains a reader to skim this gate.
        if (line ~ /^[ \t]*(cp|mv|install|ln)[ \t]/) tgt = tgt " " lastarg(line)
        if (line ~ /sed_in_place|sed -i/) tgt = tgt " " lastarg(line)
        # These take a list of targets rather than a source/target pair, so
        # every non-flag argument is a write target.
        if (line ~ /^[ \t]*(rm|mkdir|chmod|touch|truncate)[ \t]/) tgt = tgt " " nonflagargs(line)
        rest = line
        while (match(rest, />>?[ \t]*"?\$\{?[A-Za-z_][A-Za-z0-9_]*\}?/)) {
            seg = substr(rest, RSTART, RLENGTH)
            pre = substr(rest, 1, RSTART - 1)
            # `&` and `<` rule out fd duplication and input redirection. `-` rules
            # out the ASCII arrow: test-generate-tag-inputs.sh:309 logs
            # "($before -> $after -> $restored)", and $restored is repo-rooted,
            # so without this the gate reports a log line as a write.
            if (pre !~ /[-&<]$/) tgt = tgt " " seg
            rest = substr(rest, RSTART + RLENGTH)
        }
        if (tgt != "" && reftype(tgt) == "taint") {
            body = line
            sub(/^[ \t]+/, "", body)
            print fname ":" FNR ": " body
        }
    }
    if (opened) inhd = 1
}
'

# scan_file <path> -- one line per repo-rooted write site, empty when clean.
scan_file() {
    local f="$1"
    awk -v fname="$(basename "$f")" "$AWK_SCANNER" "$f" "$f"
}

# ---------------------------------------------------------------------------
# CONTROL FIRST. A gate whose green has never been contrasted with a red is a
# gate nobody has checked. This one plants both directions and refuses to report
# on the real tree unless BOTH land.
#
# The NEGATIVE half is not decoration. A scanner that flagged every file would
# satisfy the positive control perfectly while being worthless, and "it fired"
# is the reassuring half of the evidence. The planted temp-writer uses the exact
# mktemp-into-a-root-shaped-name pair that broke the first draft.
# ---------------------------------------------------------------------------
CONTROL_DIR="$(mktemp -d)"
trap 'rm -rf "$CONTROL_DIR"' EXIT

cat >"$CONTROL_DIR/test-planted-writer.sh" <<'PLANTED'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
run_it() {
    local real="$REPO_ROOT/.ci/scripts/version/resolve-version.sh"
    printf 'stub\n' >"$real"
}
PLANTED

cat >"$CONTROL_DIR/test-planted-tempsafe.sh" <<'PLANTED'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
FIXTURE="$(mktemp -d)"
ROOT="$FIXTURE/repo"
run_it() {
    mkdir -p "$ROOT/.ci/scripts/ci"
    cp "$REPO_ROOT/.ci/scripts/lib/common.sh" "$ROOT/.ci/scripts/lib/"
    printf 'seed\n' >"$ROOT/seed.txt"
    cat >"$ROOT/here.txt" <<'INNER'
printf 'not a real write\n' >"$REPO_ROOT/decoy.txt"
INNER
}
PLANTED

if [[ -z "$(scan_file "$CONTROL_DIR/test-planted-writer.sh")" ]]; then
    log_error "CONTROL FAILED: the scanner did not catch a planted real-tree write, so its verdict on the real battery means nothing"
    exit 1
fi
control_noise="$(scan_file "$CONTROL_DIR/test-planted-tempsafe.sh")"
if [[ -n "$control_noise" ]]; then
    log_error "CONTROL FAILED: the scanner flagged a planted temp-only writer, so it is not discriminating and its findings would be noise:"
    printf '  %s\n' "$control_noise" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# The registered writer set, read from the runner itself.
# ---------------------------------------------------------------------------
[[ -f "$RUNNER" ]] || log_fail "check-pool-writer-safety: runner not found at $RUNNER; refusing to pass while measuring nothing"

# Comment lines inside the array name test files while describing them (the
# test-generate-tag-inputs.sh entry cites two line numbers), so they are dropped
# before the names are read.
REGISTERED="$(sed -n '/^WRITER_TESTS=(/,/^)/p' "$RUNNER" |
    grep -vE '^[[:space:]]*#' |
    grep -oE 'test-[A-Za-z0-9._-]+\.sh' || true)"

if [[ -z "$REGISTERED" ]]; then
    log_fail "check-pool-writer-safety: parsed an EMPTY WRITER_TESTS out of $RUNNER; the array shape changed and this gate would pass everything"
fi

shopt -s nullglob
GATE_FILES=("$GATES_DIR"/test-*.sh)
shopt -u nullglob
if ((${#GATE_FILES[@]} == 0)); then
    log_fail "check-pool-writer-safety: no gate tests found under $GATES_DIR; refusing to report a clean battery over an empty set"
fi

# ---------------------------------------------------------------------------
# The real scan.
# ---------------------------------------------------------------------------
violations=0
for f in "${GATE_FILES[@]}"; do
    base="$(basename "$f")"
    hits="$(scan_file "$f")"
    [[ -n "$hits" ]] || continue
    if grep -qxF "$base" <<<"$REGISTERED"; then
        continue
    fi
    log_error "$base writes into the real tree but is NOT in WRITER_TESTS in ${RUNNER#"$REPO_ROOT"/}, so run-all.sh schedules it in the pool alongside tests that read the same paths:"
    printf '  %s\n' "$hits" >&2
    violations=$((violations + 1))
done

if ((violations > 0)); then
    log_error "$violations unregistered real-tree writer(s). Add each to WRITER_TESTS in ${RUNNER#"$REPO_ROOT"/} so it runs in the serial W chain. A write left in the pool does not fail cleanly: it corrupts a concurrent reader and presents as an unrelated gate going red in a file that parses fine on the serial re-run."
    exit 1
fi

log_info "every real-tree writer among ${#GATE_FILES[@]} gate tests is registered in WRITER_TESTS (controls fired in both directions, so this verdict is real)"
