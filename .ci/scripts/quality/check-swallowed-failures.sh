#!/bin/bash
# Catch a GATE that cannot tell a failed probe from a clean tree.
#
# THE CLASS. A gate captures a probe's output, discards the probe's exit status
# AND its stderr, and then reads the captured value. When the probe fails the
# value is empty, and empty is byte-identical to "nothing to report". The gate
# then prints its success message and exits 0. It is not reporting that things
# are fine; it is reporting nothing, in the voice of success.
#
# THE LIVE SPECIMEN, fixed 2026-07-28 in .ci/scripts/quality/check-go-deps.sh:
#
#     outdated=$(go list -u -m -json all 2>/dev/null |
#         jq -rs '...' 2>/dev/null || true)
#     while IFS=' ' read -r path current latest uptime; do ... done <<<"$outdated"
#
# `go list` was exiting 1 on the machine (go.mod wanted >= 1.25, PATH had 1.24).
# The `2>/dev/null` hid the reason, the `|| true` hid the status, the loop ran
# zero times, and the gate printed "All Go direct dependencies are up-to-date"
# and exited 0 while CI failed on the same commit.
#
# NOT THE SAME AS check-silent-failure-patterns.sh, and this is a SIBLING to it
# rather than an extension of it, for four reasons:
#   1. Opposite polarity. That gate says "your probe is UNDER-guarded, a
#      non-zero exit will abort the script"; this one says "your probe is
#      OVER-guarded, a non-zero exit vanishes". One recommends adding `|| true`;
#      the other flags it. Merging them makes a single script whose two halves
#      give contradictory advice and whose one waiver comment is ambiguous about
#      which direction is being waived.
#   2. Different scan unit. That gate is strictly line-based. The specimen above
#      spans three physical lines, with `2>/dev/null` on the first and
#      `|| true` on the third, so a line-based scanner cannot see the shape at
#      all. This gate joins continuations into logical lines first.
#   3. Different precondition. That gate only inspects files that set
#      `pipefail`, because an abort is what it is about. A swallowed failure
#      lies with or without strict mode.
#   4. Different scope. That gate is about any script aborting; this one is
#      about a VERDICT being wrong, so it scans only the directories that hold
#      gates.
#
# WHAT IT FLAGS, precisely. All four must hold:
#   a. The value is CAPTURED into a variable via $( ). A bare `cmd || true` on
#      its own line is best-effort cleanup and is none of this gate's business.
#   b. The capture ends in a fallback that discards the exit status AND yields a
#      value indistinguishable from a legitimate empty result: `|| true`,
#      `|| :`, `|| echo` with nothing, "", 0, [] or {}. A fallback with a
#      DISTINGUISHABLE sentinel (`|| echo unknown`, `|| echo missing`,
#      `|| echo 000`) is fine: the caller can still tell.
#   c. stderr is not folded into the value. `2>&1` keeps the failure visible IN
#      the captured data, so the caller can still tell.
#   d. Nothing downstream distinguishes the empty case. Either no test of the
#      variable follows at all, or the test's own branch treats empty as
#      success (`exit 0` / `return 0` with no error reported inside it).
#
# WHAT IT DELIBERATELY DOES NOT FLAG (precision over recall: a noisy gate gets
# suppressed, and a suppressed gate is the bug being fixed here)
#   * Commands whose non-zero exit IS the answer rather than an error:
#     `grep`, `command -v`, `type`, `which`, `hash`, `diff`, `cmp`. For these,
#     "no match" and "failed" are the same event by design. Residual risk,
#     stated rather than hidden: `grep` also exits 2 on an unreadable file or a
#     bad pattern, and `2>/dev/null || true` swallows that too. Flagging it
#     costs 8 false positives on the current tree, which is the trade taken.
#   * Anything where the fallback is a real sentinel (rule b).
#   * Captures that fold stderr in (rule c).
#
# WAIVER. Put `# swallowed-failure-ok: <reason>` on the line above. The reason
# is held to the same bar as a BLOCKER (>= 30 characters, no banned filler
# phrase), because a waiver here re-opens the exact hole this gate closes.
#
# TEST SEAM. SWALLOWED_SCAN_ROOT overrides the repo root; SWALLOWED_SCAN_DIRS
# overrides the scanned directories (space-separated, root-relative).
#
# Usage:
#   ./check-swallowed-failures.sh
#   ./check-swallowed-failures.sh --json
#
# Exits 0 on no findings, 1 on any finding.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
# BLOCKER: log_info / log_error and get_repo_root are used throughout this gate
source "$SCRIPT_DIR/../lib/common.sh"
# shellcheck source=../lib/blocker-validator.sh
# BLOCKER: waiver reasons are a suppression mechanism and must meet the same quality bar as every other allowlist reason in this repo
source "$SCRIPT_DIR/../lib/blocker-validator.sh"

JSON_OUTPUT=false
for arg in "$@"; do
    case "$arg" in
        --json) JSON_OUTPUT=true ;;
        --help | -h)
            sed -n '2,75p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            log_error "unknown argument: $arg"
            exit 2
            ;;
    esac
done

ROOT="${SWALLOWED_SCAN_ROOT:-$(get_repo_root)}"

# Scope: the directories that hold verdict-producing scripts. quality/ and
# security/ are where gates live; lib/ is where they get their helpers, and a
# helper that swallows a failure lies on every caller's behalf (r2_count_objects
# in lib/common.sh is exactly that shape, which is why lib/ is not optional).
DEFAULT_SCAN_DIRS=(".ci/scripts/quality" ".ci/scripts/security" ".ci/scripts/lib")
if [[ -n "${SWALLOWED_SCAN_DIRS:-}" ]]; then
    read -r -a SCAN_DIRS <<<"$SWALLOWED_SCAN_DIRS"
else
    SCAN_DIRS=("${DEFAULT_SCAN_DIRS[@]}")
fi

# ---------------------------------------------------------------------------
# The scanner. One awk pass per file: join continuations into logical lines,
# remember which of them carried a waiver comment, then apply the four rules.
#
# The patterns live INSIDE the awk program rather than being passed with -v.
# awk processes backslash escapes when it assigns a -v value, so `\(` arrived as
# a bare `(` and every regex became "Unmatched (". That is not a style point:
# the first version of this gate died on all 42 files and still printed
# "OK: no gate captures a probe...", because the empty output of a dead awk is
# indistinguishable from the empty output of a clean scan. It committed the
# defect it polices, which is why scan_file now treats a non-zero awk exit as
# fatal.
# ---------------------------------------------------------------------------
scan_file() {
    local rc=0
    awk -v file="$1" '
    BEGIN {
        n = 0; buf = ""; pending_waiver = ""
        # A capture: optional local/export/readonly, then NAME=$( or NAME="$(.
        # The optional quote is load-bearing: `tree_all="$(npm ls ... || true)"`
        # is the commonest spelling in this repo, and omitting it hid every
        # quoted capture, including the dependency-inventory specimens.
        capture_re = "(^|[ \t]|\\()(local[ \t]+|export[ \t]+|readonly[ \t]+)?[A-Za-z_][A-Za-z0-9_]*=[\"\\047]?[$]\\("
        # A status-discarding fallback whose value cannot be told from a
        # legitimate empty result.
        swallow_re = "\\|\\|[ \t]*(true|:|echo[ \t]*\\)|echo[ \t]+\"\"|echo[ \t]+0[ \t]*\\)|echo[ \t]+\"0\"|echo[ \t]+.\\[\\].|echo[ \t]+.\\{\\}.|printf[ \t]+..[ \t]*\\))"
        # Commands whose non-zero exit is a routine answer rather than an error.
        answer_re = "(^|[ \t]|\\(|\\|)(grep|egrep|fgrep|rg|command -v|type -|which|hash|diff|cmp)[ \t]"
        # Tokens meaning the empty case was reported rather than passed over.
        escalate_re = "(log_error|log_warn|log_fail|ci_error|ci_warn|die[ \t]|exit[ \t]+[1-9]|return[ \t]+[1-9]|FAIL|ERROR|::error|::warning|PROBE_FAILED)"
        # Tokens meaning the empty case ended the script successfully.
        pass_re = "(exit[ \t]+0|return[ \t]+0)"
        # How many logical lines after the capture count as downstream.
        window = 12
    }

    # --- pass 1: fold physical lines into logical ones -------------------
    {
        line = $0
        sub(/^[[:space:]]+/, "", line)
        sub(/[[:space:]]+$/, "", line)

        if (buf == "") {
            if (line ~ /^#[[:space:]]*swallowed-failure-ok:/) {
                pending_waiver = line
                next
            }
            # Any other comment or a blank line clears a dangling waiver: a
            # waiver must sit immediately above the line it excuses, or it
            # drifts and starts excusing something nobody read.
            if (line == "" || line ~ /^#/) { pending_waiver = ""; next }
            start = FNR
            buf = line
        } else {
            buf = buf " " line
        }

        tmp = buf
        o = gsub(/\(/, "(", tmp)
        c = gsub(/\)/, ")", tmp)
        if (o > c) next
        if (buf ~ /(\||&&|\\)$/) next

        n++
        LL[n] = buf
        LN[n] = start
        WV[n] = pending_waiver
        pending_waiver = ""
        buf = ""
    }

    # --- pass 2: apply the rules ----------------------------------------
    END {
        # An unterminated buffer (unbalanced parens through EOF) still has to
        # be seen; dropping it would let a defect hide behind a stray paren.
        if (buf != "") { n++; LL[n] = buf; LN[n] = start; WV[n] = pending_waiver }

        for (i = 1; i <= n; i++) {
            s = LL[i]
            if (s !~ capture_re) continue
            if (s !~ swallow_re) continue
            if (s ~ /2>&1/) continue
            if (s ~ answer_re) continue

            var = capture_var(s)
            if (var == "") continue

            if (WV[i] != "") { printf "WAIVER\t%s\t%d\t%s\t%s\n", file, LN[i], var, WV[i]; continue }

            verdict = classify(i, var)
            if (verdict != "") {
                printf "FINDING\t%s\t%d\t%s\t%s\t%s\n", file, LN[i], var, verdict, s
            }
        }
    }

    # Name of the variable being assigned in a capture.
    function capture_var(s,   t) {
        t = s
        sub(/=["\047]?[$]\(.*$/, "", t)
        sub(/^.*[[:space:](]/, "", t)
        sub(/^(local|export|readonly)$/, "", t)
        if (t !~ /^[A-Za-z_][A-Za-z0-9_]*$/) return ""
        return t
    }

    # "" when the empty case is distinguished downstream; otherwise the reason.
    #
    # The test pattern is built per variable rather than templated once: an
    # emptiness test on some OTHER variable says nothing about this one, and
    # that distinction is what keeps the pre-fix check-go-deps probe flagged
    # (its loop tests $path, never $outdated).
    function classify(i, var,   j, tre, limit, branch) {
        # Four shapes count as "the author looked at the empty case":
        #   [[ -z/-n $VAR ]]        emptiness test
        #   [[ $VAR -eq/==/=~ ... ]]  value test, including the =~ normalisers
        #                             that lib/common.sh and the release-state
        #                             validator use
        #   (( VAR ... ))           arithmetic test
        #   jq -e / jq empty <<<$VAR  validity test, which is how
        #                             dependency-inventory checks its npm trees
        tre = "(\\[\\[?[^]]*(-z|-n)[ \t]+.?[$]\\{?" var \
            "|\\[\\[?[^]]*[$]\\{?" var "[^]]*(-eq|-gt|-lt|==|!=|=~)" \
            "|\\(\\([^)]*" var \
            "|jq[ \t]+(-e|empty)[^|]*[$]\\{?" var ")"
        limit = i + window
        if (limit > n) limit = n
        for (j = i + 1; j <= limit; j++) {
            # A capture is only answered for within its own function. Letting
            # the window run past the closing brace made a log_error in the
            # NEXT function count as handling for this one, which silently
            # cleared r2_count_objects in lib/common.sh: a genuine finding, and
            # the one the sibling gate recommends as a remedy.
            if (is_boundary(LL[j])) { limit = j - 1; break }
            if (LL[j] !~ tre) continue
            branch = branch_of(j)
            if (branch ~ escalate_re) return ""
            if (branch ~ pass_re) return "the empty case exits successfully"
            # A test with neither an escalation nor an exit in its own branch:
            # accept it if the surrounding window reports the problem at all.
            if (window_has_escalation(i, limit)) return ""
            return "nothing reports the empty case"
        }
        return "no test distinguishes a failed probe from an empty result"
    }

    # The body governed by the test on logical line j: for an `if`, everything
    # up to the matching else/elif/fi; for a one-line && or || form, the rest of
    # that same line.
    function branch_of(j,   depth, k, body) {
        if (LL[j] !~ /(^|[[:space:]])if[[:space:]]/ && LL[j] !~ /;[[:space:]]*then/) {
            return LL[j]
        }
        body = LL[j]
        depth = 0
        for (k = j; k <= n; k++) {
            if (LL[k] ~ /(^|[[:space:]])if[[:space:]]/) depth++
            if (LL[k] ~ /(^|[[:space:]])fi([[:space:]]|;|$)/) depth--
            if (k > j) body = body " " LL[k]
            if (depth <= 0 && k > j) break
            if (depth == 1 && k > j && LL[k] ~ /^(else|elif)([[:space:]]|$)/) break
        }
        return body
    }

    function window_has_escalation(i, limit,   j) {
        for (j = i + 1; j <= limit; j++) {
            if (is_boundary(LL[j])) return 0
            if (LL[j] ~ escalate_re) return 1
        }
        return 0
    }

    # End of the enclosing function, or the start of the next one.
    function is_boundary(s) {
        if (s ~ /^\}/) return 1
        if (s ~ /^[A-Za-z_][A-Za-z0-9_]*\(\)[ \t]*\{/) return 1
        if (s ~ /^function[ \t]/) return 1
        return 0
    }
    ' "$1" >"$AWK_OUT" 2>"$AWK_ERR" || rc=$?

    # The scanner is fatal on any hiccup, and it must be fatal in the CALLER,
    # not here. The first version ran this function inside `< <(scan_file "$f")`,
    # and an `exit` inside a process substitution kills only that subshell: the
    # gate carried on and reported a clean scan over files it had never read.
    # That is the same shape as the defect being policed, and it is why the
    # caller now checks this return value instead.
    if ((rc != 0)); then
        log_error "awk failed on $1 (exit $rc):"
        cat "$AWK_ERR" >&2
        log_error "A dead scanner produces the same empty output as a clean file."
        log_error "Refusing to report a verdict."
        return 1
    fi
    # A warning on stderr (an invalid escape, a locale complaint) means the
    # program running is not the program that was written, even at exit 0.
    if [[ -s "$AWK_ERR" ]]; then
        log_error "awk wrote to stderr while scanning $1:"
        cat "$AWK_ERR" >&2
        log_error "Refusing to report a verdict."
        return 1
    fi
    return 0
}

# ---------------------------------------------------------------------------
# Drive.
# ---------------------------------------------------------------------------

FILES=()
for d in "${SCAN_DIRS[@]}"; do
    [[ -d "$ROOT/$d" ]] || continue
    while IFS= read -r f; do
        [[ -n "$f" ]] && FILES+=("$f")
    done < <(find "$ROOT/$d" -type f -name '*.sh' | sort)
done

# Anti-vacuity. A gate that scans zero files reports "clean" forever, which is
# the exact failure mode this gate exists to police. Refuse to be that.
if ((${#FILES[@]} == 0)); then
    log_error "No shell scripts found under: ${SCAN_DIRS[*]}"
    log_error "This gate scanned nothing, so its verdict would be meaningless. Fix the scope."
    exit 1
fi

AWK_ERR="$(mktemp)"
AWK_OUT="$(mktemp)"
trap 'rm -f "$AWK_ERR" "$AWK_OUT"' EXIT

findings=()
waivers=()
for f in "${FILES[@]}"; do
    # Status first, output second. Reading through a process substitution would
    # discard exactly the failure this gate is about (see scan_file).
    scan_file "$f" || exit 1
    while IFS= read -r row; do
        [[ -z "$row" ]] && continue
        case "$row" in
            FINDING*) findings+=("${row#FINDING	}") ;;
            WAIVER*) waivers+=("${row#WAIVER	}") ;;
        esac
    done <"$AWK_OUT"
done

# Every waiver reason is held to the BLOCKER quality bar. A waiver reopens the
# hole this gate closes, so "# swallowed-failure-ok: fine" must not pass.
waiver_bad=false
for w in "${waivers[@]}"; do
    IFS=$'\t' read -r wfile wline wvar wcomment <<<"$w"
    reason="${wcomment#*swallowed-failure-ok:}"
    reason="${reason# }"
    if ! validate_blocker_quality "${wfile}:${wline} (\$$wvar)" "$reason" "$wfile"; then
        waiver_bad=true
    fi
done

if [[ "$JSON_OUTPUT" == "true" ]]; then
    printf '{"ok": %s, "scanned": %d, "waived": %d, "findings": [' \
        "$([[ ${#findings[@]} -eq 0 && "$waiver_bad" == "false" ]] && echo true || echo false)" \
        "${#FILES[@]}" "${#waivers[@]}"
    sep=""
    for row in "${findings[@]}"; do
        IFS=$'\t' read -r ffile fline fvar freason ftext <<<"$row"
        esc="$(printf '%s' "$ftext" | sed 's/\\/\\\\/g; s/"/\\"/g')"
        printf '%s{"file": "%s", "line": %s, "var": "%s", "reason": "%s", "text": "%s"}' \
            "$sep" "${ffile#"$ROOT/"}" "$fline" "$fvar" "$freason" "$esc"
        sep=","
    done
    printf ']}\n'
    [[ ${#findings[@]} -eq 0 && "$waiver_bad" == "false" ]] && exit 0
    exit 1
fi

echo ""
echo "Swallowed Failures"
echo "============================================================"
echo "${#FILES[@]} gate script(s) scanned in ${SCAN_DIRS[*]}; ${#waivers[@]} waived."
echo ""

if [[ ${#findings[@]} -eq 0 && "$waiver_bad" == "false" ]]; then
    log_info "OK: no gate captures a probe whose failure is indistinguishable from an empty result."
    exit 0
fi

if ((${#findings[@]} > 0)); then
    log_error "Found ${#findings[@]} capture(s) whose failure is indistinguishable from an empty result:"
    for row in "${findings[@]}"; do
        IFS=$'\t' read -r ffile fline fvar freason ftext <<<"$row"
        log_error "  ${ffile#"$ROOT/"}:${fline}: \$$fvar: $freason"
        echo "      $ftext"
    done
    echo ""
    echo "Each one discards both the exit status and stderr, so a failed probe"
    echo "produces the same value as a clean result and the gate reports success."
    echo "Fix one of these ways:"
    echo "  - Capture the status: raw=\$(cmd 2>\"\$err\") || status=\$?, then act on it."
    echo "  - Fall back to a DISTINGUISHABLE sentinel (|| echo unavailable), not to empty."
    echo "  - Test the captured value and report the empty case as a failure."
    echo "  - Add '# swallowed-failure-ok: <reason>' above the line if empty genuinely"
    echo "    means the same thing as failure here."
fi

exit 1
