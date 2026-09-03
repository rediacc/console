#!/bin/bash
# Gate: docs/agent-reference/TRAPS.md is a REGISTRY, not a pile of prose. Every
# `## ` entry declares which instrument enforces it, that pointer resolves, and
# that instrument is LIVE.
#
# WHY THIS EXISTS. A trap that names no enforcement is indistinguishable from
# one that is fully mechanized, so the unprotected surface cannot be measured
# and the stop-hook judge briefs every session from headings it is already
# protected against. `agent/PLAN-trap-enforcement.md` section 3 is the
# specification; this is its W1.
#
# THE HAZARD THE PLAN NAMES, AND WHY LIVENESS IS THE POINT (plan section 3.2):
# "a gate that demands every trap name an enforced_by creates pressure to name
# one, and the cheapest thing to name is a grep that pattern-matches the trap's
# title." A gate that only checked PRESENCE would industrialize the corpus's own
# most expensive entry, manufacturing checks that cannot fail at a rate of one
# per trap and reporting 100% coverage while doing it. So every pointer is
# checked twice: it must RESOLVE (F4) and it must be LIVE (F5).
#
# ASSERTIONS
#   F1  POPULATION FLOOR. At least TRAP_FLOOR entries. An emptied, truncated or
#       relocated corpus reds instead of passing vacuously.
#   F2  IDENTITY. Every entry carries a Trap-Id; ids are unique and match
#       ^[a-z0-9][a-z0-9-]{2,48}$.
#   F3  DISPOSITION. Every entry carries an Enforced-By and a Residue LINE. The
#       disposition is either >=1 pointer or the single token JUDGMENT-ONLY, and
#       JUDGMENT-ONLY requires a non-empty Residue.
#   F4  POINTERS RESOLVE. gate: exists in the ci-runner manifest AND in
#       package.json; hook: exists in the trapguard dispatcher's RULES tuple;
#       file: exists on disk, and its :line is within the file and non-blank.
#   F5  POINTERS ARE LIVE.
#         gate: the manifest entry declares `gate: true`, i.e. `npm run ci`
#               actually schedules it. This is the same claim
#               wl_reggate.gate_reachable makes: `ci` is the ci-runner
#               dispatcher, so manifest membership IS reachability.
#         hook: the rule has BOTH a firing case and a silent case in the hook
#               suite. One-sided coverage is how a rule that always fires, or
#               never fires, passes as covered.
#         file: the file is reachable from something that runs it, in at most
#               two hops from .claude/settings.json or the ci-runner manifest.
#   F6  SELF-CONTROL, FIRST. Every assertion above is planted against a mktemp
#       fixture and required to red WITH THE MATCHING MESSAGE, and two clean
#       fixtures are required to stay green. If any control misbehaves the gate
#       exits non-zero WITHOUT judging the real tree. The count is printed
#       rather than written here, because a hardcoded count decays silently.
#
# DEVIATIONS FROM THE PLAN, CHOSEN AND STATED (plan section 3.1 left these open):
#   * The plan's pointer grammar is `gate:` / `hook:` / `suite:<harness>#<case>`.
#     `suite:` is NOT implemented, because the one entry that would use it points
#     at a case inside .claude/hooks/stop/worklist-cases/, and `file:<path>:<line>`
#     already resolves and proves liveness for it through the same two-hop rule.
#     A third pointer kind with its own resolution path would be one more thing
#     to get wrong for zero extra coverage. Add it when something needs it.
#   * `file:<path>` without a line is accepted, and is the preferred form for a
#     whole guard script: the script IS the instrument, and a line number there
#     would decay on every edit for no gain. Use `file:<path>:<line>` only when
#     one specific site is the enforcement.
#   * F3b (a `block`-tier hook rule must declare certain_failure or a policy) is
#     NOT implemented: the trapguard dispatcher has no tiers today. Every rule is
#     a PostToolUse injector that cannot deny anything, so there is no block tier
#     to police. Restore F3b in the same commit that adds one.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"
set +e # common.sh sets -e; this gate counts findings rather than dying on one

REPO_ROOT="$(get_repo_root)"

# The corpus and the four artifacts pointers resolve against. Every one is a
# seam so F6 can drive the whole gate against fixtures instead of the real tree.
TRAP_CORPUS="${TRAP_CORPUS:-$REPO_ROOT/docs/agent-reference/TRAPS.md}"
TRAP_MANIFEST="${TRAP_MANIFEST:-$REPO_ROOT/scripts/ci-runner/manifest.ts}"
TRAP_PACKAGE_JSON="${TRAP_PACKAGE_JSON:-$REPO_ROOT/package.json}"
TRAP_DISPATCH="${TRAP_DISPATCH:-$REPO_ROOT/.claude/hooks/trapguard/dispatch.py}"
TRAP_HOOK_SUITE="${TRAP_HOOK_SUITE:-$REPO_ROOT/.claude/hooks/test-hooks.sh}"
TRAP_SETTINGS="${TRAP_SETTINGS:-$REPO_ROOT/.claude/settings.json}"
TRAP_FILE_ROOT="${TRAP_FILE_ROOT:-$REPO_ROOT}"

# A RATCHET, not a target. 48 entries on 2026-08-27, 49 on 2026-08-28. Raising
# it is the only direction that keeps meaning something: lowering it to get past
# a red is how a corpus shrinks silently, so lowering it requires saying why, out
# loud, in the commit that does it.
#
# THE RATCHET MUST MOVE WITH THE CORPUS, and this is what it costs when it does
# not. Commit 0b47292e1 added a 49th entry and left the floor at 48, so F1's
# control -- delete one entry, expect a red -- landed on exactly 48, which is
# not BELOW 48. The gate stopped being able to detect a deletion at all, and
# CI reported it as "a shrinking corpus must red (F1): expected 1, got 0".
# An unratcheted floor does not merely lag; it disarms the check it belongs to.
#
# AND IT HAPPENED AGAIN, 2026-08-31, with the paragraph above already on the page:
# `mark-done-all-stale-is-a-bulk-verb` became the 50th entry and the floor stayed at
# 49, producing the identical CI line. `check:ci-trap-registry` was GREEN throughout --
# a floor only fails when the corpus is below it, so an unratcheted floor is invisible
# to the gate and visible only to its own control. Adding an entry means bumping this
# number in the same commit; there is no other signal.
TRAP_FLOOR="${TRAP_FLOOR:-70}"

ID_RE='^[a-z0-9][a-z0-9-]{2,48}$'

errors=0
err() {
    log_error "$*"
    errors=$((errors + 1))
}

# ---------------------------------------------------------------------------
# THE PARSER. Shared shape with wl_store.trap_headings, and it tracks FENCED
# CODE BLOCKS for the reason the plan gives at section 3.1: once every `## `
# entry must carry a Trap-Id, a `## ` inside a fenced example in a trap body
# becomes a phantom entry with no id, and the gate reds on a document that is
# correct. Trap bodies routinely carry markdown examples.
#
# Emits one TSV row per entry: lineno, id, enforced-by, residue, residue-line-
# seen, title. Trailer lines are read only from the block between the heading
# and the first blank line, so a body paragraph beginning "Residue:" is body.
# ---------------------------------------------------------------------------
parse_corpus() {
    awk '
    # US (0x1f) rather than TAB: tab is IFS whitespace in bash, so a run of two
    # tabs COLLAPSES and an entry with an empty Residue silently reads as an
    # entry with no Residue LINE. Found by the clean-corpus control going red.
    function emit() {
        if (ln > 0) printf "%d\037%s\037%s\037%s\037%d\037%s\n", ln, id, enf, res, resseen, title
    }
    BEGIN { fence=""; ln=0; intrailer=0 }
    {
        line = $0
        if (match(line, /^[ \t]*(```+|~~~+)/)) {
            marker = substr(line, RSTART, RLENGTH)
            gsub(/[ \t]/, "", marker)
            c = substr(marker, 1, 1)
            if (fence == "") fence = c
            else if (fence == c) fence = ""
            next
        }
        if (fence != "") next
        if (line ~ /^## / && line !~ /^### /) {
            emit()
            ln = NR; title = substr(line, 4); id = ""; enf = ""; res = ""; resseen = 0
            intrailer = 1
            next
        }
        if (intrailer) {
            if (line == "") { intrailer = 0; next }
            if (line ~ /^Trap-Id:/)     { id  = substr(line, 9);  sub(/^ +/, "", id);  next }
            if (line ~ /^Enforced-By:/) { enf = substr(line, 13); sub(/^ +/, "", enf); next }
            if (line ~ /^Residue:/)     { res = substr(line, 9);  sub(/^ +/, "", res); resseen = 1; next }
            intrailer = 0
        }
    }
    END { emit() }
    ' "$1"
}

# ---------------------------------------------------------------------------
# RESOLUTION AND LIVENESS
# ---------------------------------------------------------------------------

# F4: the manifest declares this id, and package.json defines the npm script.
gate_resolves() {
    grep -qF "id: '$1'," "$TRAP_MANIFEST" && grep -qF "\"$1\":" "$TRAP_PACKAGE_JSON"
}

# F5: the manifest entry declares `gate: true`, so `npm run ci` schedules it.
# Scoped to the block between this id and the next one, or a neighbouring
# entry's `gate: true` would answer for it.
gate_is_live() {
    awk -v want="id: '$1'," '
        index($0, want) { inblock = 1; next }
        inblock && index($0, "id: \047") { exit }   # \047 is a single quote: the awk program is single-quoted
        inblock && /gate: true/  { found = 1; exit }
        END { exit(found ? 0 : 1) }
    ' "$TRAP_MANIFEST"
}

# F4: the dispatcher defines the rule AND lists it in RULES. A defined-but-
# unlisted rule is dead code that never runs, which is the whole hazard.
hook_resolves() {
    local fn="rule_${1//-/_}"
    grep -qE "^def $fn\(" "$TRAP_DISPATCH" || return 1
    awk -v fn="$fn" '
        /^RULES = \(/ { inblock = 1; next }
        inblock && /^\)/ { exit }
        inblock && index($0, fn) { found = 1; exit }
        END { exit(found ? 0 : 1) }
    ' "$TRAP_DISPATCH"
}

# The rule's own source text. A suite case is attributed to a rule when the
# string it asserts on appears in that rule's body: the needle is text the rule
# PRODUCES, so matching it is evidence the case exercises that rule and not a
# neighbour. Attribution by section order alone would credit any rule with its
# neighbour's coverage.
rule_body() {
    awk -v fn="rule_${1//-/_}" '
        $0 ~ ("^def " fn "\\(") { inb = 1 }
        inb && /^def / && $0 !~ ("^def " fn "\\(") { exit }
        inb && /^RULES = / { exit }
        inb { print }
    ' "$TRAP_DISPATCH"
}

# F5: BOTH directions present in the hook suite for this rule.
#
# Firing cases carry the needle as their last quoted argument; silent cases
# carry no needle at all, so they are attributed to the most recent firing case
# that resolved to a rule. That is the file's actual layout (one rule per
# contiguous block) and it fails SAFE: an unattributable silent case credits
# nobody rather than crediting the wrong rule.
hook_is_live() {
    local rule="$1" body needles fires=0 silent=0
    [ -f "$TRAP_HOOK_SUITE" ] || return 1
    body="$(rule_body "$rule")"
    [ -n "$body" ] || return 1
    while IFS=$'\037' read -r kind needle; do
        if [ "$kind" = "fires" ]; then
            if [ -n "$needle" ] && [[ "$body" == *"$needle"* ]]; then
                fires=$((fires + 1))
                current=1
            else
                current=0
            fi
        elif [ "${current:-0}" = "1" ]; then
            silent=$((silent + 1))
        fi
    done < <(inject_cases)
    [ "$fires" -gt 0 ] && [ "$silent" -gt 0 ]
}

# Joined `check_inject` invocations as `<fires|silent>\t<needle-or-empty>`.
# The suite writes them across continuation lines, so an unjoined read would
# see every needle as belonging to no call at all.
inject_cases() {
    awk '
        {
            line = $0
            while (line ~ /\\$/) {
                sub(/\\$/, "", line)
                if ((getline nxt) > 0) line = line " " nxt; else break
            }
            if (line !~ /check_inject[ \t]+(fires|silent)/) next
            kind = (line ~ /check_inject[ \t]+fires/) ? "fires" : "silent"
            needle = ""
            if (match(line, /"[^"]*"[^"]*$/)) {
                tail = substr(line, RSTART)
                if (match(tail, /"[^"]*"/)) {
                    needle = substr(tail, RSTART + 1, RLENGTH - 2)
                }
            }
            printf "%s\037%s\n", kind, needle
        }
    ' "$TRAP_HOOK_SUITE"
}

# F4 for `file:` pointers. Accepts `path` and `path:line`.
file_resolves() {
    local spec="$1" path line
    path="${spec%%:*}"
    line=""
    case "$spec" in
        *:*) line="${spec#*:}" ;;
    esac
    [ -f "$TRAP_FILE_ROOT/$path" ] || return 1
    if [ -n "$line" ]; then
        case "$line" in
            '' | *[!0-9]*) return 1 ;;
        esac
        local total
        total="$(wc -l <"$TRAP_FILE_ROOT/$path")"
        [ "$line" -ge 1 ] && [ "$line" -le "$total" ] || return 1
        local text
        text="$(sed -n "${line}p" "$TRAP_FILE_ROOT/$path")"
        [ -n "${text// /}" ] || return 1
    fi
    return 0
}

# The set of files that .claude/settings.json and the ci-runner manifest name
# directly. These are hop 1: something registered or scheduled runs them.
LIVE_L1_CACHE=""
live_l1_files() {
    if [ -z "$LIVE_L1_CACHE" ]; then
        local p
        LIVE_L1_CACHE="$(
            {
                [ -f "$TRAP_SETTINGS" ] && cat "$TRAP_SETTINGS"
                [ -f "$TRAP_MANIFEST" ] && cat "$TRAP_MANIFEST"
            } 2>/dev/null |
                grep -oE '[A-Za-z0-9_./-]+\.(sh|py|ts|js|mjs|cjs)' |
                sed 's|^.*CLAUDE_PROJECT_DIR/||' | sort -u |
                while read -r p; do
                    [ -f "$TRAP_FILE_ROOT/$p" ] && printf '%s\n' "$TRAP_FILE_ROOT/$p"
                done
        )"
        # Sentinel so an empty result is computed once, not on every lookup.
        [ -n "$LIVE_L1_CACHE" ] || LIVE_L1_CACHE=$'\n'
    fi
    printf '%s\n' "$LIVE_L1_CACHE"
}

# F5 for `file:` pointers, in at most two hops:
#   hop 1  the file is named in settings.json or the manifest (registered hook,
#          gate script, gate-test), so something runs it directly;
#   hop 2  the file is named by a hop-1 file (a lib a guard sources, a case file
#          a suite runner globs in, a gate a gate-test drives).
# Two hops is the whole rule, deliberately: a deeper closure would eventually
# call anything reachable from anything "live", which is how a liveness check
# stops meaning anything.
file_is_live() {
    local path="${1%%:*}" base
    base="$(basename "$path")"
    if [ -f "$TRAP_SETTINGS" ] && grep -qF "$base" "$TRAP_SETTINGS"; then return 0; fi
    if [ -f "$TRAP_MANIFEST" ] && grep -qF "$base" "$TRAP_MANIFEST"; then return 0; fi
    local f
    while read -r f; do
        [ -n "$f" ] || continue
        [ "$f" = "$TRAP_FILE_ROOT/$path" ] && continue
        if grep -qF "$base" "$f" 2>/dev/null; then return 0; fi
    done < <(live_l1_files)
    return 1
}

# ---------------------------------------------------------------------------
# THE SCAN. Returns the finding count; prints one actionable line per finding.
# ---------------------------------------------------------------------------
n_entries=0
n_judgment=0
n_residue=0
n_gate=0
n_hook=0
n_file=0

scan() {
    errors=0
    n_entries=0
    n_judgment=0
    n_residue=0
    n_gate=0
    n_hook=0
    n_file=0

    if [ ! -f "$TRAP_CORPUS" ]; then
        err "the corpus is not at $TRAP_CORPUS. The gate cannot see the tree, so its green would mean nothing."
        [ "$errors" -eq 0 ]
        return
    fi

    local seen_ids=""
    local ln id enf res resseen title
    while IFS=$'\037' read -r ln id enf res resseen title; do
        n_entries=$((n_entries + 1))

        # F2 IDENTITY
        if [ -z "$id" ]; then
            err "$TRAP_CORPUS:$ln: entry '$title' has no Trap-Id. Add the three-line trailer (Trap-Id / Enforced-By / Residue) directly under the heading."
            continue
        fi
        if ! [[ "$id" =~ $ID_RE ]]; then
            err "$TRAP_CORPUS:$ln: Trap-Id '$id' is not kebab-case within 3..49 characters ($ID_RE)."
        fi
        case " $seen_ids " in
            *" $id "*) err "$TRAP_CORPUS:$ln: Trap-Id '$id' is a DUPLICATE. Ids are permanent and unique; never reuse a retired one." ;;
            *) seen_ids="$seen_ids $id" ;;
        esac

        # F3 DISPOSITION
        if [ "$resseen" != "1" ]; then
            err "$TRAP_CORPUS:$ln: '$id' has no Residue line. Write 'Residue:' with nothing after it when the instruments cover the whole trap."
        fi
        if [ -z "$enf" ]; then
            err "$TRAP_CORPUS:$ln: '$id' has no Enforced-By. Name a pointer (gate:/hook:/file:) or declare JUDGMENT-ONLY with a Residue."
            continue
        fi
        if [ "$enf" = "JUDGMENT-ONLY" ]; then
            n_judgment=$((n_judgment + 1))
            [ -n "$res" ] || err "$TRAP_CORPUS:$ln: '$id' is JUDGMENT-ONLY with an empty Residue. Say what no instrument reaches; that sentence is the only record of the unprotected surface."
        elif [[ "$enf" == *JUDGMENT-ONLY* ]]; then
            err "$TRAP_CORPUS:$ln: '$id' mixes JUDGMENT-ONLY with pointers. It is a terminal disposition: name the instruments, and put what they do not reach in Residue."
        fi
        [ -n "$res" ] && n_residue=$((n_residue + 1))

        # F4 + F5, per pointer
        local ptr
        for ptr in ${enf//,/ }; do
            [ -n "$ptr" ] || continue
            [ "$ptr" = "JUDGMENT-ONLY" ] && continue
            case "$ptr" in
                gate:*)
                    n_gate=$((n_gate + 1))
                    local gid="${ptr#gate:}"
                    if ! gate_resolves "$gid"; then
                        err "$TRAP_CORPUS:$ln: '$id' names gate:$gid, which is not both a manifest entry and a package.json script. A dangling pointer is a lie about coverage."
                    elif ! gate_is_live "$gid"; then
                        err "$TRAP_CORPUS:$ln: '$id' names gate:$gid, which the manifest does not mark 'gate: true', so 'npm run ci' never schedules it. A gate nobody runs is not an instrument."
                    fi
                    ;;
                hook:*)
                    n_hook=$((n_hook + 1))
                    local hid="${ptr#hook:}"
                    if ! hook_resolves "$hid"; then
                        err "$TRAP_CORPUS:$ln: '$id' names hook:$hid, which is not a rule listed in RULES in $TRAP_DISPATCH."
                    elif ! hook_is_live "$hid"; then
                        err "$TRAP_CORPUS:$ln: '$id' names hook:$hid, which lacks a FIRING case or a SILENT case in $TRAP_HOOK_SUITE. One-sided coverage cannot tell a rule that always fires from one that never does."
                    fi
                    ;;
                file:*)
                    n_file=$((n_file + 1))
                    local fspec="${ptr#file:}"
                    if ! file_resolves "$fspec"; then
                        err "$TRAP_CORPUS:$ln: '$id' names file:$fspec, which does not resolve (missing file, or a line number past the end, or a blank line)."
                    elif ! file_is_live "$fspec"; then
                        err "$TRAP_CORPUS:$ln: '$id' names file:$fspec, which nothing registered or scheduled reaches within two hops of .claude/settings.json or the ci-runner manifest. Point at something that RUNS."
                    fi
                    ;;
                *)
                    err "$TRAP_CORPUS:$ln: '$id' has an unknown pointer '$ptr'. Use gate:<check id>, hook:<trapguard rule>, file:<path>[:line], or JUDGMENT-ONLY."
                    ;;
            esac
        done
    done < <(parse_corpus "$TRAP_CORPUS")

    # F1 POPULATION FLOOR, last so a truncated corpus reports its content
    # problems too. Zero entries is a FAILURE, never a pass: a gate that saw
    # nothing has verified nothing.
    if [ "$n_entries" -lt "$TRAP_FLOOR" ]; then
        err "the corpus holds $n_entries entries, below the floor of $TRAP_FLOOR. Either the parser stopped seeing the tree, or entries were deleted; both are reds."
    fi

    # NOT `return "$errors"`. A shell return is taken mod 256, so exactly 256 findings
    # would return 0 and read as a clean scan. Only the STATUS is made boolean here;
    # the count itself is still printed with the findings.
    [ "$errors" -eq 0 ]
}

# ---------------------------------------------------------------------------
# F6 SELF-CONTROL, FIRST. Every assertion above gets a planted defect that must
# make this gate red, AND a converse that must leave it green. A gate that has
# never been seen to fail is worthless, and one with only positive controls will
# happily flag a correct corpus.
# ---------------------------------------------------------------------------
CONTROL_DIR=""
cleanup() { [ -n "$CONTROL_DIR" ] && rm -rf "$CONTROL_DIR"; }
trap cleanup EXIT

control_failures=0
controls_red=0
controls_green=0

# A corpus body that satisfies the floor: `n` filler entries plus whatever extra
# text the caller appends. Built by CONSTRUCTION rather than by substituting
# into a copy of the real file, so the plant cannot silently fail to apply.
fixture_corpus() {
    local out="$1" extra="$2" n="$3" i
    : >"$out"
    for ((i = 1; i <= n; i++)); do
        {
            printf '## filler trap %d\n' "$i"
            printf 'Trap-Id: filler-trap-%d\n' "$i"
            printf 'Enforced-By: JUDGMENT-ONLY\n'
            printf 'Residue: nothing reaches this filler.\n\n'
            printf 'body\n\n'
        } >>"$out"
    done
    printf '%s\n' "$extra" >>"$out"
}

# Run the gate's scan against one fixture corpus, in a subshell so the seams and
# the finding counter cannot leak between controls. SEAMS is set once by
# run_controls; findings go to a file so a red control can be checked for its
# REASON as well as its exit code.
SEAMS=()
CONTROL_LOG=""
control_run() {
    (
        export TRAP_CORPUS="$1"
        for kv in "${SEAMS[@]}"; do export "${kv?}"; done
        scan >/dev/null 2>"$CONTROL_LOG"
    )
}

# A red control must red for the RIGHT REASON. Three plants in a neighbouring
# session were themselves invalid and still "passed" as controls, so the needle
# is mandatory: a fixture that reds because its filler count is wrong proves
# nothing about the assertion it was written for.
expect_red() {
    local label="$1" corpus="$2" needle="$3" rc
    controls_red=$((controls_red + 1))
    control_run "$corpus"
    rc=$?
    if [ "$rc" -eq 0 ]; then
        log_error "CONTROL FAILED ($label): the planted defect did not red the gate, so its verdict on the real tree means nothing"
        control_failures=$((control_failures + 1))
    elif ! grep -qF "$needle" "$CONTROL_LOG"; then
        log_error "CONTROL FIRED FOR THE WRONG REASON ($label): expected a finding containing '$needle', got: $(tr '\n' ' ' <"$CONTROL_LOG" | cut -c1-300)"
        control_failures=$((control_failures + 1))
    fi
    [ -n "${TRAP_CONTROL_VERBOSE:-}" ] && cat "$CONTROL_LOG" >&2
    return 0
}

expect_green() {
    local label="$1" corpus="$2" rc
    controls_green=$((controls_green + 1))
    control_run "$corpus"
    rc=$?
    if [ "$rc" -ne 0 ]; then
        log_error "CONTROL FAILED ($label): a clean fixture went red ($rc finding(s)), so this gate would flag correct corpora: $(tr '\n' ' ' <"$CONTROL_LOG" | cut -c1-300)"
        control_failures=$((control_failures + 1))
    fi
    return 0
}

run_controls() {
    CONTROL_DIR="$(mktemp -d)"
    local d="$CONTROL_DIR"
    mkdir -p "$d/files/sub"

    # A live pointer target for the positive controls: named by a fake manifest,
    # so it is live at hop 1.
    printf '#!/bin/bash\necho real\n' >"$d/files/sub/ctl-guard.sh"
    printf 'x\n' >"$d/files/sub/ctl-orphan.sh"

    cat >"$d/manifest.ts" <<'EOF'
export const GATES = [
  {
    id: 'check:ctl-live',
    run: 'npm run check:ctl-live',
    gate: true,
    leaves: ['sub/ctl-guard.sh'],
  },
  {
    id: 'check:ctl-dark',
    run: 'npm run check:ctl-dark',
    gate: false,
    leaves: ['nothing.sh'],
  },
];
EOF
    cat >"$d/package.json" <<'EOF'
{ "scripts": { "check:ctl-live": "true", "check:ctl-dark": "true" } }
EOF
    cat >"$d/settings.json" <<'EOF'
{ "hooks": {} }
EOF
    cat >"$d/dispatch.py" <<'EOF'
def rule_ctl_two_sided(cmd, out, root, resp):
    return "trapguard[ctl-two-sided]: fired"


def rule_ctl_one_sided(cmd, out, root, resp):
    return "trapguard[ctl-one-sided]: fired"


def rule_ctl_unlisted(cmd, out, root, resp):
    return "trapguard[ctl-unlisted]: fired"


RULES = (
    rule_ctl_two_sided,
    rule_ctl_one_sided,
)
EOF
    cat >"$d/test-hooks.sh" <<'EOF'
check_inject fires "$(inject_json 'x' 'y')" \
    "ctl: the two-sided rule fires" "trapguard[ctl-two-sided]"
check_inject silent "$(inject_json 'x' '')" \
    "ctl CONTROL: the two-sided rule stays silent"
check_inject fires "$(inject_json 'x' 'y')" \
    "ctl: the one-sided rule fires" "trapguard[ctl-one-sided]"
EOF

    CONTROL_LOG="$d/findings.log"
    SEAMS=(
        "TRAP_MANIFEST=$d/manifest.ts"
        "TRAP_PACKAGE_JSON=$d/package.json"
        "TRAP_DISPATCH=$d/dispatch.py"
        "TRAP_HOOK_SUITE=$d/test-hooks.sh"
        "TRAP_SETTINGS=$d/settings.json"
        "TRAP_FILE_ROOT=$d/files"
        "TRAP_FLOOR=5"
    )

    # --- the converse first: a correct corpus must stay GREEN, exercising one
    # pointer of every kind. Without this the positive controls below would pass
    # just as happily for a gate that reds on everything.
    fixture_corpus "$d/clean.md" '## a clean mechanized entry
Trap-Id: ctl-clean
Enforced-By: gate:check:ctl-live, hook:ctl-two-sided, file:sub/ctl-guard.sh
Residue:

body
' 5
    expect_green "clean corpus, one pointer of each kind" "$d/clean.md"

    # --- the fence control. A `## ` inside a fenced block is an EXAMPLE, not an
    # entry, and reading it as one reds a correct document. This is the negative
    # direction of the parser fix; the positive direction is the F2 control below.
    fixture_corpus "$d/fenced.md" '## a real entry with a fenced example
Trap-Id: ctl-fenced
Enforced-By: JUDGMENT-ONLY
Residue: the example below must not become an entry.

```markdown
## Not A Trap
```

~~~
## Also Not A Trap
~~~
' 5
    expect_green "a fenced ## heading is an example, not an entry" "$d/fenced.md"

    # --- and the same line UNFENCED must red, or the control above is proving
    # only that the gate ignores everything.
    fixture_corpus "$d/unfenced.md" '## Not A Trap
' 5
    expect_red "an unfenced ## with no trailer is a finding (F2)" "$d/unfenced.md" "has no Trap-Id"

    # --- F1
    : >"$d/empty.md"
    expect_red "an empty corpus reds instead of passing vacuously (F1)" "$d/empty.md" "below the floor"
    fixture_corpus "$d/short.md" '' 3
    expect_red "a corpus below the floor reds (F1)" "$d/short.md" "below the floor"
    expect_red "a missing corpus reds (F1)" "$d/does-not-exist.md" "the corpus is not at"

    # --- F2
    fixture_corpus "$d/dup.md" '## duplicate id
Trap-Id: filler-trap-1
Enforced-By: JUDGMENT-ONLY
Residue: x.
' 5
    expect_red "a duplicate Trap-Id reds (F2)" "$d/dup.md" "DUPLICATE"
    fixture_corpus "$d/badid.md" '## bad id
Trap-Id: Not_Kebab_Case
Enforced-By: JUDGMENT-ONLY
Residue: x.
' 5
    expect_red "a non-kebab Trap-Id reds (F2)" "$d/badid.md" "is not kebab-case"

    # --- F3
    fixture_corpus "$d/nodisp.md" '## no disposition
Trap-Id: ctl-no-disposition
Residue: x.
' 5
    expect_red "an entry with no Enforced-By reds (F3)" "$d/nodisp.md" "has no Enforced-By"
    fixture_corpus "$d/nores.md" '## judgment with no residue
Trap-Id: ctl-no-residue
Enforced-By: JUDGMENT-ONLY
Residue:
' 5
    expect_red "JUDGMENT-ONLY with an empty Residue reds (F3)" "$d/nores.md" "with an empty Residue"
    fixture_corpus "$d/noresline.md" '## no residue line at all
Trap-Id: ctl-no-residue-line
Enforced-By: gate:check:ctl-live
' 5
    expect_red "a missing Residue LINE reds (F3)" "$d/noresline.md" "has no Residue line"
    fixture_corpus "$d/mixed.md" '## mixed disposition
Trap-Id: ctl-mixed
Enforced-By: JUDGMENT-ONLY, gate:check:ctl-live
Residue: x.
' 5
    expect_red "JUDGMENT-ONLY mixed with a pointer reds (F3)" "$d/mixed.md" "mixes JUDGMENT-ONLY"

    # --- F4
    fixture_corpus "$d/badgate.md" '## dangling gate
Trap-Id: ctl-dangling-gate
Enforced-By: gate:check:does-not-exist
Residue:
' 5
    expect_red "a gate: pointer at a non-existent id reds (F4)" "$d/badgate.md" "is not both a manifest entry"
    fixture_corpus "$d/badhook.md" '## dangling hook
Trap-Id: ctl-dangling-hook
Enforced-By: hook:no-such-rule
Residue:
' 5
    expect_red "a hook: pointer at a non-existent rule reds (F4)" "$d/badhook.md" "not a rule listed in RULES"
    fixture_corpus "$d/unlisted.md" '## rule defined but not dispatched
Trap-Id: ctl-unlisted-rule
Enforced-By: hook:ctl-unlisted
Residue:
' 5
    expect_red "a hook: rule missing from RULES reds (F4)" "$d/unlisted.md" "not a rule listed in RULES"
    fixture_corpus "$d/badfile.md" '## dangling file
Trap-Id: ctl-dangling-file
Enforced-By: file:no/such/guard.sh
Residue:
' 5
    expect_red "a file: pointer at a missing path reds (F4)" "$d/badfile.md" "does not resolve"
    fixture_corpus "$d/badline.md" '## line past the end
Trap-Id: ctl-line-past-end
Enforced-By: file:sub/ctl-guard.sh:9999
Residue:
' 5
    expect_red "a file: pointer past the end of the file reds (F4)" "$d/badline.md" "does not resolve"
    fixture_corpus "$d/unknown.md" '## unknown pointer kind
Trap-Id: ctl-unknown-kind
Enforced-By: grep:the-trap-title
Residue:
' 5
    expect_red "an unknown pointer kind reds (F4), which is what stops 'name a grep' from being the cheap answer" "$d/unknown.md" "unknown pointer"

    # --- F5
    fixture_corpus "$d/darkgate.md" '## a gate nobody runs
Trap-Id: ctl-dark-gate
Enforced-By: gate:check:ctl-dark
Residue:
' 5
    expect_red "a gate: pointer at a manifest entry with gate:false reds (F5)" "$d/darkgate.md" "does not mark 'gate: true'"
    fixture_corpus "$d/onesided.md" '## a rule with no silent case
Trap-Id: ctl-one-sided
Enforced-By: hook:ctl-one-sided
Residue:
' 5
    expect_red "a hook: rule with a firing case and no silent case reds (F5)" "$d/onesided.md" "lacks a FIRING case or a SILENT case"
    fixture_corpus "$d/orphanfile.md" '## a file nothing runs
Trap-Id: ctl-orphan-file
Enforced-By: file:sub/ctl-orphan.sh
Residue:
' 5
    expect_red "a file: pointer nothing reaches within two hops reds (F5)" "$d/orphanfile.md" "within two hops"

    if [ "$control_failures" -gt 0 ]; then
        log_error "$control_failures of the gate's own controls misbehaved. NOT judging the real tree: a gate whose controls are broken cannot report anything about anything."
        exit 1
    fi
    log_info "controls: $controls_red planted defects red (each matched against the finding it was written for), $controls_green clean fixtures green"
}

# ---------------------------------------------------------------------------
main() {
    # --scan-only exists for the gate test and for debugging a single fixture:
    # it runs the scan WITHOUT the controls. Nothing in package.json or CI uses
    # it, deliberately. The controls are not an option on the real run.
    if [ "${1:-}" != "--scan-only" ]; then
        run_controls
    fi

    scan
    local found=$?
    if [ "$found" -gt 0 ]; then
        log_error "$found trap-registry finding(s) in $TRAP_CORPUS. Fix the disposition, do not delete the entry and do not point at something that cannot fire."
        exit 1
    fi

    # Print the SHAPE, not just the verdict: a reader can notice when a number
    # collapses, and "OK" tells nobody that the corpus stopped being parsed.
    log_info "trap registry OK: $n_entries entries (floor $TRAP_FLOOR), $n_judgment JUDGMENT-ONLY, $n_residue carrying residue, $((n_gate + n_hook + n_file)) live pointers ($n_gate gate, $n_hook hook, $n_file file)"

    # THE UNRATCHETED FLOOR, SAID OUT LOUD WHERE THE AUTHOR IS LOOKING.
    # An entry added without bumping TRAP_FLOOR leaves this gate GREEN -- a floor only
    # fails when the corpus is BELOW it -- and reds `gate-test:trap-registry` instead,
    # which is `slow: true` and therefore deferred out of the pre-push `--quick` lane.
    # So the signal arrives ~45 minutes later, from CI, as "a shrinking corpus must red
    # (F1): expected 1, got 0", which names neither the floor nor the entry that moved.
    # It has now happened twice (0b47292e1, and again on 2026-08-31 with the warning
    # already written into this file's header).
    #
    # This is an ADVISORY, not a failure, because making it fatal means asserting
    # `n_entries == TRAP_FLOOR`, and several of the 21 control fixtures below are
    # deliberately built at floor+1 to exercise other rules. Tightening it means
    # auditing every one of those first; the line below costs nothing and puts the
    # number in the sub-second lane where the mistake is made.
    if [ "$n_entries" -gt "$TRAP_FLOOR" ]; then
        log_info "  ratchet: $n_entries entries against a floor of $TRAP_FLOOR. Bump TRAP_FLOOR to $n_entries in this commit, or gate-test:trap-registry (F1) reds in CI."
    fi
}

main "$@"
