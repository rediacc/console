#!/usr/bin/env bash
# ---- gate ----
# kind: battery
# step: Quality-gate unit tests
# needs: none
# lane: quality-gate-tests
# blocker: BLOCKER: rides the hand-written "Quality-gate unit tests" step, which all 148 gate-tests share and none owns, so no gate-bind region may emit it
# why: Controls for ./run.sh -- the entry point every other command goes through
# ---- end gate ----

# Controls for ./run.sh -- the entry point every other command goes through.
#
# It had no test of its own, and two defects lived in it because of that:
#
#   1. `quality all` logged a warning and returned SUCCESS when shfmt was
#      missing, so on any machine without shfmt -- every non-Debian host, and
#      this one until someone hand-installed it -- the command reported green
#      having run no shell gate at all.
#   2. `fix shell` formatted with whatever shfmt was on PATH while the gate
#      verified with the pinned one, so the fixer could produce a state the
#      checker rejects.
#
# HERMETIC BY CONSTRUCTION: no docker, no network, no submodules. Every case is
# either a dispatch assertion or a source-level invariant, so this runs in the
# bare-checkout CI lane. What it deliberately does NOT do is run a real gate --
# that is what the gates themselves are for.
#
# TWO DESTINATIONS SINCE 2026-10-01. `./run.sh` is a router with two exits: the
# media entry point for `provision` and `www`, and `python3 -m rediacc_ci` for
# everything else. The bash dispatcher `.ci/legacy/run-legacy.sh` is deleted; its
# verbs are the entry functions in `.ci/rediacc_ci/core/run_verbs.py`:
#
#   $RUN  the router, and the thing a person or a workflow actually types. Every
#         DISPATCH case drives this.
#   $SRC  the Python verb module, and the thing the SOURCE-LEVEL cases read.
#         quality_all and fix_shell live there; grepping the router for them
#         would find nothing, and three of the controls in section 2 and 3 PASS
#         on nothing found -- a vacuous green in the exact place this file exists
#         to prevent one.

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
RUN="$ROOT/run.sh"
SRC="$ROOT/.ci/rediacc_ci/core/run_verbs.py"
export PYTHONPATH="$ROOT/.ci${PYTHONPATH:+:$PYTHONPATH}"

# The tally (`ok`, `no`, `tally_finish`) is shared. It lived here in triplicate
# until 2026-09-06; test-helpers.sh carries why all three moved at once.
source "$(dirname "${BASH_SOURCE[0]}")/../lib/test-helpers.sh"
exits() { # exits <label> <want> <args...>
    local label="$1" want="$2"
    shift 2
    local got
    (cd "$ROOT" && "$RUN" "$@" >/dev/null 2>&1)
    got=$?
    if [[ "$got" == "$want" ]]; then ok "$label (exit $got)"; else no "$label (exit $got, want $want)"; fi
}

# --- 1. dispatch: an unknown verb must not look like success -----------------
exits "an unknown verb fails" 1 definitely-not-a-verb
exits "an unknown devbox subcommand fails" 1 devbox not-a-real-subcommand
exits "help succeeds" 0 help
exits "devbox exec with no command fails" 1 devbox exec --

# --- 2. THE VACUOUS GREEN. A gate that cannot run must not report success. ----
# CODE ONLY. An earlier draft grepped a fixed window and matched the word
# `log_warn` inside the COMMENT that explains the old behaviour -- the test
# failed on correct code, which is the wrong direction for a control to fail in.
body() { # body <file> <function-name>  -> the function's body, comments stripped
    awk -v fn="$2" '
        $0 ~ "^def " fn "\\(" { inside = 1; next }
        inside && /^[^ \t#]/ { exit }
        inside { sub(/^[[:space:]]*#.*$/, ""); print }
    ' "$1"
}

QA="$(body "$SRC" quality_all)"
if [[ -z "${QA//[[:space:]]/}" ]]; then
    no "quality_all was not extracted from $SRC, so both controls below would ask their question of an EMPTY string"
fi
# HERE-STRINGS, NOT `printf | grep -q`, and this cost a CI red (run 33432878128, job
# 99628247967). `grep -q` exits the instant it matches; bash's builtin `printf` is then
# left writing into a closed pipe, prints `printf: write error: Broken pipe` and returns
# non-zero; `set -o pipefail` at the top of this file makes that the PIPELINE's status.
# So a MATCH can present as a failed test. A here-string has no second process and no pipe.
if grep -q 'log\.warn' <<<"$QA"; then
    no "CONTROL: quality_all warns and falls through when shfmt is absent (the vacuous green is back)"
else
    ok "quality_all does not warn-and-continue when shfmt is unusable"
fi
if grep -q 'return 1' <<<"$QA"; then
    ok "quality_all returns non-zero when the shell gates cannot run"
else
    no "quality_all has no failure path when the shell gates cannot run"
fi

# --- 3. fix and check must use the SAME binary -------------------------------
FS="$(body "$SRC" fix_shell)"
if [[ -z "${FS//[[:space:]]/}" ]]; then
    no "fix_shell was not extracted from $SRC, so the control below passes on nothing found"
fi
if grep -q 'toolchain\.acquire("shfmt")' <<<"$FS"; then
    ok "fix shell formats with the pinned binary, the one the gate verifies with"
else
    no "fix shell takes shfmt from PATH; it can format into a state the gate rejects"
fi
if grep -qE '\[\s*"shfmt"' <<<"$FS"; then
    no "CONTROL: fix_shell still calls a bare shfmt somewhere"
else
    ok "CONTROL: no bare shfmt invocation survives in fix_shell"
fi

# --- 4. the gate lane ---------------------------------------------------------
# shellcheck source=/dev/null
. "$ROOT/.ci/config/constants.sh" 2>/dev/null
# shellcheck source=/dev/null
. "$ROOT/.ci/lib/local-common.sh" 2>/dev/null

lane() { (cd "$ROOT" && env "$@" bash -c '. .ci/config/constants.sh; . .ci/scripts/lib/toolchain.sh; . .ci/lib/local-common.sh; gate_lane_decide') 2>/dev/null; }

[[ "$(lane REDIACC_IN_DEVBOX=1)" == host ]] &&
    ok "inside the container the lane is 'host' (breaks the re-exec recursion)" ||
    no "REDIACC_IN_DEVBOX did not force the host lane -- routing would recurse"
[[ "$(lane REDIACC_LANE=host)" == host ]] &&
    ok "REDIACC_LANE=host is honoured (the documented opt-out)" ||
    no "the host opt-out is not honoured"
[[ "$(lane REDIACC_LANE=devbox)" == devbox ]] &&
    ok "REDIACC_LANE=devbox is honoured" ||
    no "an explicit devbox lane is not honoured"

# A routed verb must not silently degrade: if it cannot route, it says so.
if [ -n "$(awk -v fn=gate_lane_should_route '$0 ~ "^" fn "\\(\\) \\{" {i=1; next} i && /^}/ {exit} i {sub(/^[[:space:]]*#.*$/, ""); print}' "$ROOT/.ci/lib/local-common.sh" | grep -E 'log_warn|log_error')" ]; then
    ok "a lane that cannot route reports it rather than degrading silently"
else
    no "CONTROL: routing can fail silently, which is the failure this design exists to prevent"
fi

# --- 5. both halves must be runnable at all -----------------------------------
# The router `exec`s the Python package, so a package that does not import fails
# on the FIRST verb anybody types, with the router named in the error and not
# the module at fault. The deleted legacy dispatcher must stay deleted: a file
# that reappears would be a second, unrouted implementation of every verb.
if bash -n "$RUN" 2>/dev/null; then ok "run.sh parses"; else no "run.sh does not parse"; fi
if [[ -x "$RUN" ]]; then ok "run.sh is executable"; else no "run.sh is not executable"; fi
if (cd "$ROOT" && python3 -c 'import rediacc_ci.__main__, rediacc_ci.core.run_verbs') 2>/dev/null; then
    ok "the verb module imports"
else
    no "the verb module does not import"
fi
if [[ ! -e "$ROOT/.ci/legacy/run-legacy.sh" ]]; then
    ok "the legacy dispatcher stays deleted"
else
    no "the legacy dispatcher is back; the router does not reach it, so it is dead code beside the real verbs"
fi

# --- 6. THE ROUTER AND THE PACKAGE PARTITION THE DOCUMENTED VERB SET ----------
#
# WHAT THIS IS FOR. `./run.sh <verb>` has two destinations: the media entry point
# (the router's own arms) and the `rediacc_ci` package (its VERBS table). The two
# ways a verb goes wrong are silent in opposite directions:
#
#   AN ORPHAN. A verb documented in `help` and served by neither falls through to
#     the package's "Unknown command" and is indistinguishable from a typo.
#   AN OVERLAP. A verb served by BOTH is answered by whichever the router reaches
#     first, so the second implementation is dead code that reads as live.
#
# So the assertion is set equality plus disjointness, in both directions, against
# `help` -- the one inventory a person reads. The per-verb `Usage:` lines are
# GENERATED from each dispatch table now, so there is no third inventory to drift.
#
# SECOND LEVEL, NOT JUST TOP LEVEL. A check over top-level verbs alone would have
# missed the seven subcommands the dispatcher once served without documenting.

# Case-nesting DEPTH decides the level, never indentation. The router has no inner
# case today; the rule is kept because a router that grows one must not report its
# numeric arms as verbs.
arms_of() { # arms_of <router> -> "TOP <verb>"
    awk '
        /^main\(\) \{/ { inmain = 1; next }
        !inmain { next }
        /^\}/ { exit }
        {
            line = $0
            sub(/^[ \t]+/, "", line)
            if (line ~ /^#/) next
            if (line ~ /^esac/) { depth--; next }
            if (line ~ /(^|[ \t;])case[ \t].*[ \t]in([ \t]|$)/) { depth++; next }
            if (depth < 1) next
            if (line !~ /^[a-zA-Z0-9_"*-][a-zA-Z0-9_"*|. -]*\)/) next
            arms = line
            sub(/\).*$/, "", arms)
            n = split(arms, parts, "|")
            for (i = 1; i <= n; i++) {
                v = parts[i]
                gsub(/^[ \t]+|[ \t]+$/, "", v)
                gsub(/"/, "", v)
                # `*` is the fallback, `""` the bare-verb default, a leading `-` a
                # flag alias of the verb beside it, a bare number an inner arm.
                if (v == "" || v == "*" || v ~ /^-/ || v ~ /^[0-9]+$/) continue
                if (depth == 1) print "TOP " v
            }
        }
    ' "$1" | sort -u
}

# What the package dispatches: `TOP <verb>` for every VERBS row and `SUB <verb>/<sub>`
# for every key of a dispatch table, read from the code that dispatches.
package_arms() { python3 -m rediacc_ci.core.run_verbs arms; }

# The signature is the part before the first run of TWO spaces. Splitting on a
# single space reads the first word of the prose as a subcommand.
documented_in() { # documented_in <helpfile> -> "TOP <verb>" / "SUB <top>/<sub>"
    awk '
        /^  [a-z]/ {
            line = $0
            sub(/^  /, "", line)
            sig = line
            if (match(sig, /[ \t][ \t]+/)) sig = substr(sig, 1, RSTART - 1)
            desc = substr(line, length(sig) + 1)
            n = split(sig, w, /[ \t]+/)
            top = w[1]
            if (top !~ /^[a-z][a-z0-9-]*$/) next
            print "TOP " top
            if (n < 2) next
            # `<cmd>` means "the subcommands are enumerated in the description",
            # which is how devbox and worktree are written. Anything else in
            # brackets is a PARAMETER (`<slug>`, `[opts]`), not a subcommand.
            if (w[2] == "<cmd>") {
                m = split(desc, parts, "\\|")
                if (m < 2) next
                for (i = 1; i <= m; i++) {
                    v = parts[i]
                    gsub(/^[ \t]+|[ \t]+$/, "", v)
                    if (v ~ /^[a-z][a-z0-9-]*$/) print "SUB " top "/" v
                }
                next
            }
            if (w[2] ~ /^[a-z][a-z0-9-]*$/) print "SUB " top "/" w[2]
        }
    ' "$1" | sort -u
}

# One line per problem, empty when the split is a partition. A findings FUNCTION
# rather than inline assertions, so the control below can drive the same code
# against a deliberately broken copy -- an assertion that has never been seen to
# fire is not yet evidence of anything.
verb_findings() { # verb_findings <router> <package-arms-file> <help-file>
    local router="$1" arms="$2" help="$3" v
    local rt pt dt

    rt="$(arms_of "$router" | sed -n 's/^TOP //p')"
    pt="$(sed -n 's/^TOP //p' "$arms")"
    dt="$(documented_in "$help" | sed -n 's/^TOP //p')"

    # `sed '/^$/d'` on every side: an EMPTY set printed by printf is one blank
    # line, not zero lines, so an empty half would otherwise be reported as a
    # finding about a verb whose name is the empty string -- an instrument
    # inventing a defect, which is worse than one missing a real one.
    comm -12 <(printf '%s\n' "$rt" | sed '/^$/d' | sort -u) <(printf '%s\n' "$pt" | sed '/^$/d' | sort -u) | sed 's/^/overlap /'
    comm -23 <(printf '%s\n' "$rt" "$pt" | sed '/^$/d' | sort -u) <(printf '%s\n' "$dt" | sed '/^$/d' | sort -u) | sed 's/^/dispatched-but-undocumented /'
    comm -13 <(printf '%s\n' "$rt" "$pt" | sed '/^$/d' | sort -u) <(printf '%s\n' "$dt" | sed '/^$/d' | sort -u) | sed 's/^/documented-but-unreachable /'

    # Second level, only for the verbs whose dispatch table lives in the package.
    # `provision`, `www`, `rotation` and `worktree` delegate their whole subcommand
    # tree to another program, so their documented subcommands are that program's
    # inventory -- demanding they appear as arms here would be wrong.
    for v in $(sed -n 's|^SUB \([a-z0-9-]*\)/.*|\1|p' "$arms" | sort -u); do
        comm -23 \
            <(sed -n "s|^SUB $v/||p" "$arms" | sort -u) \
            <(documented_in "$help" | sed -n "s|^SUB $v/||p") | sed "s|^|dispatched-but-undocumented $v/|"
        comm -13 \
            <(sed -n "s|^SUB $v/||p" "$arms" | sort -u) \
            <(documented_in "$help" | sed -n "s|^SUB $v/||p") | sed "s|^|documented-but-unreachable $v/|"
    done
}

# ANTI-VACUITY BEFORE THE ASSERTION, because every claim above is "this set is
# empty" and an extractor that matched nothing satisfies all of them at once.
# `|| true` ON EVERY COUNT: section 4 sources `.ci/lib/local-common.sh`, which
# sources `.ci/scripts/lib/common.sh`, whose `set -euo pipefail` makes everything
# from there on run under an errexit this file never asked for, and `grep -c`
# exits 1 when it counts zero -- so an extractor that matched NOTHING killed the
# script four lines before the control that would have said so.
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
package_arms >"$work/arms.txt"
(cd "$ROOT" && "$RUN" help) >"$work/help.txt" 2>/dev/null
n_router=$(arms_of "$RUN" | grep -c '^TOP ' || true)
n_package=$(grep -c '^TOP ' "$work/arms.txt" || true)
n_docs=$(documented_in "$work/help.txt" | grep -c '^TOP ' || true)
n_subs=$(grep -c '^SUB ' "$work/arms.txt" || true)
n_doc_subs=$(documented_in "$work/help.txt" | grep -c '^SUB ' || true)

# A findings FUNCTION, for the same reason `verb_findings` is one: the control
# below drives it against numbers it chooses, so the clause is seen to fire rather
# than assumed to. Arguments in the order the message prints them.
vacuity_findings() { # vacuity_findings <router> <package> <docs> <subs> <doc_subs>
    local r="$1" p="$2" d="$3" s="$4" ds="$5"
    [[ "$d" -gt 0 ]] ||
        echo "help documents no verb, so both set comparisons are against an empty set"
    [[ $((r + p)) -gt 0 ]] ||
        echo "nothing dispatches anything (router=$r package=$p); the partition is between two empty sets"
    [[ "$ds" -eq 0 || "$s" -gt 0 ]] ||
        echo "help documents $ds subcommand(s), but the package dispatch tables hold $s; the second level is checking nothing"
}

vacuity="$(vacuity_findings "$n_router" "$n_package" "$n_docs" "$n_subs" "$n_doc_subs")"
if [[ -z "$vacuity" ]]; then
    ok "the extractors see a real tree: $n_router router arm(s) + $n_package package verb(s) = $((n_router + n_package)) dispatched, $n_subs subcommand(s), $n_docs documented verb(s)"
else
    no "an extractor returned an EMPTY set; every assertion below would pass on nothing:"$'\n'"$(sed 's/^/    /' <<<"$vacuity")"
fi

findings="$(verb_findings "$RUN" "$work/arms.txt" "$work/help.txt")"
if [[ -z "$findings" ]]; then
    ok "router arms + package verbs == the verbs help documents, with no overlap"
else
    no "the verb sets do not partition:"$'\n'"$(sed 's/^/    /' <<<"$findings")"
fi

# CONTROL, three ways, on COPIES so no tracked file is ever mutated. Each plants
# one of the three failure shapes and requires the report to name it, and each
# plant is asserted to have LANDED: a sed whose pattern stopped matching leaves the
# copy identical to the source, and the control would report PASS having planted
# nothing.
ctl="$work/ctl"
mkdir -p "$ctl"
cp "$RUN" "$ctl/run.sh"
cp "$work/arms.txt" "$ctl/arms.txt"
cp "$work/help.txt" "$ctl/help.txt"

# (a) a verb served by both halves.
grep -q '^        www) exec ' "$ctl/run.sh" ||
    no "CONTROL PLANT DID NOT LAND: run.sh no longer carries a 'www) exec' arm in that shape, so the overlap control below plants nothing and passes for free"
sed -i 's/^        www) exec /        quality) exec elsewhere ;;\n        www) exec /' "$ctl/run.sh"
grep -q '^        quality) exec elsewhere ;;$' "$ctl/run.sh" ||
    no "CONTROL PLANT DID NOT LAND: the overlap was not written into the copy"
if grep -q '^overlap quality$' <<<"$(verb_findings "$ctl/run.sh" "$ctl/arms.txt" "$ctl/help.txt")"; then
    ok "CONTROL: a verb in both the router and the package is reported as an overlap"
else
    no "CONTROL: an overlapping verb was NOT reported; the disjointness half proves nothing"
fi
cp "$RUN" "$ctl/run.sh"

# (b) a documented verb nothing dispatches.
grep -q '^TOP clean$' "$ctl/arms.txt" ||
    no "CONTROL PLANT DID NOT LAND: the package no longer dispatches 'clean', so the unreachable-verb control below plants nothing and passes for free"
sed -i '/^TOP clean$/d' "$ctl/arms.txt"
grep -q '^TOP clean$' "$ctl/arms.txt" &&
    no "CONTROL PLANT DID NOT LAND: the dispatch row survived the deletion in the copy"
if grep -q '^documented-but-unreachable clean$' <<<"$(verb_findings "$ctl/run.sh" "$ctl/arms.txt" "$ctl/help.txt")"; then
    ok "CONTROL: deleting a dispatch row for a documented verb is reported as unreachable"
else
    no "CONTROL: an orphaned verb was NOT reported; the set equality proves nothing"
fi
cp "$work/arms.txt" "$ctl/arms.txt"

# (c) a subcommand that exists but is undocumented.
grep -q '^  fix shell           ' "$ctl/help.txt" ||
    no "CONTROL PLANT DID NOT LAND: the help text no longer documents 'fix shell' in that shape, so the undocumented-subcommand control below plants nothing and passes for free"
sed -i 's/^  fix shell           .*$//' "$ctl/help.txt"
grep -q '^  fix shell           ' "$ctl/help.txt" &&
    no "CONTROL PLANT DID NOT LAND: the help line survived the deletion in the copy"
if grep -q '^dispatched-but-undocumented fix/shell$' <<<"$(verb_findings "$ctl/run.sh" "$ctl/arms.txt" "$ctl/help.txt")"; then
    ok "CONTROL: deleting a help line for a live SUBCOMMAND is reported, so the second level is really checked"
else
    no "CONTROL: an undocumented subcommand was NOT reported; the second-level half proves nothing"
fi

# --- 6b. controls for the vacuity clauses -------------------------------------
# A clause that has never been seen to fire is not yet a check. Each is driven
# directly, in both directions.
fires() { # fires <label> <needle> <args to vacuity_findings...>
    local label="$1" needle="$2"
    shift 2
    if grep -q "$needle" <<<"$(vacuity_findings "$@")"; then
        ok "CONTROL: $label"
    else
        no "CONTROL: $label -- the clause did NOT fire, so its green proves nothing"
    fi
}
fires "an empty help is reported" "documents no verb" 2 12 0 40 40
fires "a tree where nothing dispatches is reported" "nothing dispatches" 0 0 18 40 40
fires "documented subcommands with no extracted dispatch table are reported" \
    "second level is checking nothing" 2 12 18 0 40

if [[ -z "$(vacuity_findings "$n_router" "$n_package" "$n_docs" "$n_subs" "$n_doc_subs")" ]]; then
    ok "CONTROL: today's real numbers are not reported as vacuous either"
else
    no "CONTROL: the clause fires on the live tree, so the cases above prove nothing about it"
fi

# --- 7. the router stays a router --------------------------------------------
# A ceiling, not a style rule. A router that starts absorbing logic re-creates the
# file the split was undoing, one reasonable special case at a time.
router_lines=$(wc -l <"$RUN")
if [[ "$router_lines" -le 120 ]]; then
    ok "run.sh is still a router ($router_lines lines of 120)"
else
    no "run.sh has grown to $router_lines lines; the ceiling is 120 and logic belongs on one side or the other"
fi
# The Python arm names a module that has to exist, or the first verb fails with
# ModuleNotFoundError and nothing is reachable.
if grep -q 'python3 -m rediacc_ci' "$RUN" && [[ -f "$ROOT/.ci/rediacc_ci/__init__.py" ]]; then
    ok "the router's Python arm names rediacc_ci, and that package is on disk"
else
    no "the router's Python arm and .ci/rediacc_ci/__init__.py disagree; the verbs cannot work"
fi

tally_finish "run.sh"
exit $?
