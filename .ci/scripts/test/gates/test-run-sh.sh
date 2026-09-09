#!/usr/bin/env bash
# ---- gate ----
# kind: battery
# step: Quality-gate unit tests
# needs: none
# lane: quality-security
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
# TWO FILES SINCE 2026-09-06. `./run.sh` is now a router and the body it used to
# hold is `.ci/legacy/run-legacy.sh`. The distinction below is deliberate and it
# matters in both directions:
#
#   $RUN  the router, and the thing a person or a workflow actually types. Every
#         DISPATCH case drives this, because dispatch is what the split must not
#         change: `./run.sh quality all` has to reach the same code it did before.
#   $SRC  the legacy body, and the thing the SOURCE-LEVEL cases read. quality_all
#         and fix_shell live there now; grepping the router for them would find
#         nothing, and three of the controls in section 2 and 3 PASS on nothing
#         found -- a vacuous green in the exact place this file exists to prevent
#         one.

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
RUN="$ROOT/run.sh"
SRC="$ROOT/.ci/legacy/run-legacy.sh"

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
        $0 ~ "^" fn "\\(\\) \\{" { inside = 1; next }
        inside && /^}/ { exit }
        inside { sub(/^[[:space:]]*#.*$/, ""); print }
    ' "$1"
}

QA="$(body "$SRC" quality_all)"
# HERE-STRINGS, NOT `printf | grep -q`, and this cost a CI red (run 33432878128, job
# 99628247967). `grep -q` exits the instant it matches; bash's builtin `printf` is then
# left writing into a closed pipe, prints `printf: write error: Broken pipe` and returns
# non-zero; `set -o pipefail` at the top of this file makes that the PIPELINE's status.
# So a MATCH can present as a failed test. It did: `quality_all` carries `return 1` on
# line 23 of its 1129-byte body -- grep found it, quit, and the `if` took the else branch
# anyway, reporting "quality_all has no failure path" against correct code.
#
# Whether printf gets that far is a scheduling race, so this is intermittent, and the
# check on the NEXT line fails in the worse direction: there the else branch is the PASS,
# so a broken pipe turns the control guarding against a vacuous green into a vacuous
# green itself. A here-string has no second process and no pipe.
if grep -q 'log_warn' <<<"$QA"; then
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
if grep -A 12 '^fix_shell()' "$SRC" | grep -q 'toolchain_acquire shfmt'; then
    ok "fix shell formats with the pinned binary, the one the gate verifies with"
else
    no "fix shell takes shfmt from PATH; it can format into a state the gate rejects"
fi
if grep -A 20 '^fix_shell()' "$SRC" | grep -qE '^\s+(find [^|]*-exec |")shfmt'; then
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
if [ -n "$(body "$ROOT/.ci/lib/local-common.sh" gate_lane_should_route | grep -E 'log_warn|log_error')" ]; then
    ok "a lane that cannot route reports it rather than degrading silently"
else
    no "CONTROL: routing can fail silently, which is the failure this design exists to prevent"
fi

# --- 5. both halves must be runnable at all -----------------------------------
# The legacy file is checked too, and not as symmetry: the router `exec`s it, so
# a legacy file that does not parse or has lost its +x bit fails on the FIRST
# verb anybody types, with the router named in the error and not the file at
# fault. That is also why the router prints the path when the exec target is
# missing rather than letting bash say it.
if bash -n "$RUN" 2>/dev/null; then ok "run.sh parses"; else no "run.sh does not parse"; fi
if [[ -x "$RUN" ]]; then ok "run.sh is executable"; else no "run.sh is not executable"; fi
if bash -n "$SRC" 2>/dev/null; then ok "the legacy body parses"; else no "the legacy body does not parse"; fi
if [[ -x "$SRC" ]]; then ok "the legacy body is executable"; else no "the legacy body is not executable"; fi

# --- 6. THE SPLIT IS A PARTITION OF THE DOCUMENTED VERB SET -------------------
#
# WHAT THIS IS FOR. `./run.sh <verb>` now has three possible destinations: the
# media entry point, the `rediacc_ci` Python package, and the legacy body. Every
# workstream in the tooling transformation moves verbs between them, and the two
# ways that goes wrong are silent in opposite directions:
#
#   AN ORPHAN. A verb deleted from the legacy dispatcher and not added to
#     PORTED_VERBS falls through to the legacy file's `*)` arm and reports
#     "Unknown command" -- indistinguishable from a typo, on a verb that is
#     documented three lines above in the same file's own help.
#   AN OVERLAP. A verb left in BOTH is served by whichever the router reaches
#     first, so the port appears to work while the code it was meant to replace
#     is what actually ran. That is the failure the whole program is about.
#
# So the assertion is set equality plus disjointness, in both directions, against
# `show_help` -- the one inventory a person reads.
#
# IT ALSO CATCHES WHAT WAS ALREADY WRONG, which is why it is worth having beyond
# the split. On the day it was written the dispatcher served SEVEN subcommands
# `show_help` did not mention (`account seed-demo`, `devbox url`, `devbox exec`,
# `devbox doctor`, `quality actions`, `quality suppressions`, `quality dead-bash`)
# and the per-verb `Usage:` strings were a THIRD inventory that agreed with
# neither -- `Usage: ./run.sh account [...]` had never listed `db`, which
# `show_help` has documented all along.
#
# SECOND LEVEL, NOT JUST TOP LEVEL. All seven of those are subcommands. A check
# over top-level verbs alone finds nothing here and would have shipped green.

# Case-nesting DEPTH decides the level, never indentation: the docker-group route
# code contains an inner `case` whose arms sit at the same indent as a real
# subcommand, and an indentation rule reports its numeric arms as verbs.
arms_of() { # arms_of <file> -> "TOP <verb>" / "SUB <top>/<sub>"
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
                if (depth == 1) { top = v; print "TOP " v }
                else if (depth == 2 && top != "") print "SUB " top "/" v
            }
        }
    ' "$1" | sort -u
}

# The signature is the part before the first run of TWO spaces. Splitting on a
# single space reads the first word of the prose as a subcommand.
documented_in() { # documented_in <file> -> "TOP <verb>" / "SUB <top>/<sub>"
    awk '
        /^show_help\(\) \{/ { inh = 1; next }
        !inh { next }
        /^EOF$/ { exit }
        /^\}/ { exit }
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

# Read the table, never a regex over it: `. "$1"` gives the array bash sees, so a
# multi-line or commented entry cannot fool the parser. The BASH_SOURCE guard at
# the end of the router means sourcing it runs nothing.
ported_of() { # ported_of <router> -> one verb per line
    (
        . "$1" >/dev/null 2>&1
        printf '%s\n' ${PORTED_VERBS[@]+"${PORTED_VERBS[@]}"}
    ) | sed '/^$/d' | sort -u
}

# "<rows> <bad>" then one indented line per non-verb row. A FUNCTION, so the
# controls below can drive it against copies rather than only against the one file
# it will ever be called on in anger.
router_table_of() { # router_table_of <router>
    awk '
        !intable && /^PORTED_VERBS=\(/ {
            rows++
            if ($0 !~ /\)[ \t]*$/) intable = 1
            next
        }
        intable {
            if ($0 ~ /^[ \t]*\)/) { rows++; intable = 0; next }
            line = $0
            sub(/[ \t]*#.*$/, "", line)
            gsub(/^[ \t]+|[ \t]+$/, "", line)
            if (line == "" || line ~ /^[a-z][a-z0-9-]*$/) { rows++; next }
            bad++; badlines = badlines "\n    " line
        }
        END { printf "%d %d%s", rows + 0, bad + 0, badlines }
    ' "$1"
}

# The per-verb `Usage:` string, with nested groups removed first -- `devbox`
# writes `url [term|account|db]` inside its own list, and cutting at the first
# `]` would take those three for subcommands and lose the seven that follow.
usage_of() { # usage_of <file> <verb> -> one subcommand per line
    grep -oE "Usage: \./run\.sh $2 \[.*" "$1" |
        head -n 1 |
        sed -e 's/^[^[]*\[//' -e 's/\[[^]]*\]//g' -e 's/\].*$//' |
        tr '|' '\n' |
        sed -e 's/^[ \t]*//' -e 's/[ \t]*$//' -e '/^$/d' |
        sort -u
}

# One line per problem, empty when the split is a partition. A findings FUNCTION
# rather than inline assertions, so the control below can drive the same code
# against a deliberately broken copy -- an assertion that has never been seen to
# fire is not yet evidence of anything.
verb_findings() { # verb_findings <router> <legacy>
    local router="$1" legacy="$2" v
    local rt lt dt

    rt="$( (
        arms_of "$router" | sed -n 's/^TOP //p'
        ported_of "$router"
    ) | sort -u)"
    lt="$(arms_of "$legacy" | sed -n 's/^TOP //p')"
    dt="$(documented_in "$legacy" | sed -n 's/^TOP //p')"

    # `sed '/^$/d'` on every side: an EMPTY set printed by printf is one blank
    # line, not zero lines, so an empty half would otherwise be reported as a
    # finding about a verb whose name is the empty string -- an instrument
    # inventing a defect, which is worse than one missing a real one.
    comm -12 <(printf '%s\n' "$rt" | sed '/^$/d') <(printf '%s\n' "$lt" | sed '/^$/d') | sed 's/^/overlap /'
    comm -23 <(printf '%s\n' "$rt" "$lt" | sed '/^$/d' | sort -u) <(printf '%s\n' "$dt" | sed '/^$/d') | sed 's/^/dispatched-but-undocumented /'
    comm -13 <(printf '%s\n' "$rt" "$lt" | sed '/^$/d' | sort -u) <(printf '%s\n' "$dt" | sed '/^$/d') | sed 's/^/documented-but-unreachable /'

    # Second level, only for the verbs that OWN a nested case. `provision`, `www`,
    # `rotation` and `worktree` delegate their whole subcommand tree to another
    # program, so their documented subcommands are that program's inventory and
    # not this file's -- demanding they appear as arms here would be wrong.
    for v in $(arms_of "$legacy" | sed -n 's|^SUB \([a-z0-9-]*\)/.*|\1|p' | sort -u); do
        comm -23 \
            <(arms_of "$legacy" | sed -n "s|^SUB $v/||p") \
            <(documented_in "$legacy" | sed -n "s|^SUB $v/||p") | sed "s|^|dispatched-but-undocumented $v/|"
        comm -13 \
            <(arms_of "$legacy" | sed -n "s|^SUB $v/||p") \
            <(documented_in "$legacy" | sed -n "s|^SUB $v/||p") | sed "s|^|documented-but-unreachable $v/|"
        # The third inventory. A verb's own `Usage:` line is what a user sees after
        # a typo, and it drifted from both of the others unnoticed for months.
        if [[ -n "$(usage_of "$legacy" "$v")" ]]; then
            comm -3 <(arms_of "$legacy" | sed -n "s|^SUB $v/||p") <(usage_of "$legacy" "$v") |
                tr -d '\t' | sed "s|^|usage-line-drift $v/|"
        fi
    done
}

# ANTI-VACUITY BEFORE THE ASSERTION, because every claim above is "this set is
# empty" and an extractor that matched nothing satisfies all of them at once.
# Set-derived rather than a typed count: the sets must be non-empty and the two
# halves must together cover every documented verb, which is the same fact the
# assertion needs anyway.
# `|| true` ON ALL FOUR, and without it this whole block was UNREACHABLE in the
# one state it exists for. Section 4 sources `.ci/lib/local-common.sh`, which at
# :21 sources `.ci/scripts/lib/common.sh`, whose :11 is `set -euo pipefail` -- so
# everything from there on runs under an errexit this file never asked for.
# `grep -c` exits 1 when it counts zero, so an extractor that matched NOTHING
# killed the script here, four lines before the control below that would have
# said so. Measured 2026-09-08 by renaming `main()` in the subject: rc=1, last
# traced command this line, 12 of 23 PASS lines printed, and NO verdict at all.
# The control written for the empty-set case could not fire in the empty-set case.
#
# REWRITTEN 2026-09-09. The clause that stood here required `n_legacy > 0`, and that
# is a floor the migration is TRYING TO BREACH: the whole point of PORTED_VERBS is
# that the legacy dispatcher ends at zero arms, so the gate guarding the port would
# have gone red at the exact moment the port succeeded, and the cheap way out of that
# is to lower the floor, which retires the assertion. There is no named budget
# anywhere in the tree -- `LEGACY_ARMS_MAX` does not exist and never did -- so the
# number that reaches zero is `n_legacy` on the line below and nothing else.
#
# WHAT REPLACES IT, and why nothing is lost. The floor was belt-and-braces over an
# assertion that already catches a blind extractor much more loudly: with `arms_of`
# returning nothing for the legacy file, `verb_findings` reports every documented
# verb as `documented-but-unreachable`, which is 16 findings today rather than one.
# And the extractor's LIVENESS is proven every run by control (b) below, which
# deletes a real dispatch arm from a copy and requires the report to name it -- an
# extractor that saw nothing could not pass that. So the three clauses here are the
# ones that stay true in every state of the migration INCLUDING its last:
#
#   1. something is documented          -- both set comparisons are against `dt`
#   2. something is dispatched          -- by the router, the ported table, or legacy
#   3. subcommands are still extracted  -- but only WHILE the legacy file still
#                                          dispatches top-level verbs, because when
#                                          it dispatches none it owns no second level
#
# THE ONE THING THIS CANNOT PRE-SOLVE, stated so the last port does not discover it.
# `documented_in` reads `$SRC`, so `show_help` moving to Python is the commit where
# `$SRC` and clause 1 have to be retargeted at whatever owns the help text then
# (`rediacc_ci/__main__.py` derives `--help` from its VERBS table already). Every
# port BEFORE that one is now safe; that one still needs a hand on it.
n_router=$(arms_of "$RUN" | grep -c '^TOP ' || true)
n_ported=$(ported_of "$RUN" | grep -c . || true)
n_legacy=$(arms_of "$SRC" | grep -c '^TOP ' || true)
n_docs=$(documented_in "$SRC" | grep -c '^TOP ' || true)
n_subs=$(arms_of "$SRC" | grep -c '^SUB ' || true)
n_doc_subs=$(documented_in "$SRC" | grep -c '^SUB ' || true)

# A findings FUNCTION, for the same reason `verb_findings` is one: the control below
# drives it against numbers it chooses, so the clause is seen to fire rather than
# assumed to. Arguments in the order the message prints them.
vacuity_findings() { # vacuity_findings <router> <ported> <legacy> <docs> <subs> <doc_subs>
    local r="$1" p="$2" l="$3" d="$4" s="$5" ds="$6"
    [[ "$d" -gt 0 ]] ||
        echo "show_help documents no verb, so both set comparisons are against an empty set"
    [[ $((r + p + l)) -gt 0 ]] ||
        echo "nothing dispatches anything (router=$r ported=$p legacy=$l); the partition is between two empty sets"
    [[ "$l" -eq 0 || "$ds" -eq 0 || "$s" -gt 0 ]] ||
        echo "the legacy file dispatches $l verb(s) and documents $ds subcommand(s), but the arm extractor found 0 of them; the second level is checking nothing"
}

vacuity="$(vacuity_findings "$n_router" "$n_ported" "$n_legacy" "$n_docs" "$n_subs" "$n_doc_subs")"
if [[ -z "$vacuity" ]]; then
    ok "the extractors see a real tree: $n_router router arm(s) + $n_ported ported + $n_legacy legacy = $((n_router + n_ported + n_legacy)) dispatched, $n_subs subcommand(s), $n_docs documented verb(s)"
else
    no "an extractor returned an EMPTY set; every assertion below would pass on nothing:"$'\n'"$(sed 's/^/    /' <<<"$vacuity")"
fi

findings="$(verb_findings "$RUN" "$SRC")"
if [[ -z "$findings" ]]; then
    ok "router arms + legacy arms == the verbs show_help documents, with no overlap"
else
    no "the verb sets do not partition:"$'\n'"$(sed 's/^/    /' <<<"$findings")"
fi

# CONTROL, three ways, on a COPY so no tracked file is ever mutated. Each plants
# one of the three failure shapes and requires the report to name it.
ctl="$(mktemp -d)"
cp "$RUN" "$ctl/run.sh"
cp "$SRC" "$ctl/legacy.sh"

# (a) a verb served by both halves.
#
# THE PLANT IS ASSERTED TO HAVE LANDED, because this sed is anchored to a literal
# line of the real run.sh (`PORTED_VERBS=()`). The day that line gains a verb the
# pattern matches nothing, the copy already contains the overlap the control means
# to introduce, and the control reports PASS having planted NOTHING -- it would be
# green for a reason that has nothing to do with what it claims to check.
if ! grep -qE '^PORTED_VERBS=\(' "$ctl/run.sh"; then
    no "CONTROL PLANT DID NOT LAND: run.sh no longer carries a PORTED_VERBS table at all, so the overlap control below plants nothing and passes for free"
fi
sed -i -E 's/^PORTED_VERBS=\(.*/PORTED_VERBS=(quality)/' "$ctl/run.sh"
grep -q '^PORTED_VERBS=(quality)$' "$ctl/run.sh" ||
    no "CONTROL PLANT DID NOT LAND: the overlap was not written into the copy"
if grep -q '^overlap quality$' <<<"$(verb_findings "$ctl/run.sh" "$ctl/legacy.sh")"; then
    ok "CONTROL: a verb in both PORTED_VERBS and the legacy dispatcher is reported as an overlap"
else
    no "CONTROL: an overlapping verb was NOT reported; the disjointness half proves nothing"
fi
cp "$RUN" "$ctl/run.sh"

# (b) a documented verb nothing dispatches.
#
# PLANT ASSERTED, both halves, for the reason (a) states above: this sed is anchored to a
# literal dispatch arm of the real legacy file, and the day that arm is reindented or
# reworded the pattern matches nothing, the copy is IDENTICAL to the source, and the
# control below reports PASS having deleted nothing.
grep -q '^        clean) clean ;;$' "$ctl/legacy.sh" ||
    no "CONTROL PLANT DID NOT LAND: the legacy dispatcher no longer carries a 'clean)' arm in that shape, so the unreachable-verb control below plants nothing and passes for free"
sed -i 's/^        clean) clean ;;$//' "$ctl/legacy.sh"
grep -q '^        clean) clean ;;$' "$ctl/legacy.sh" &&
    no "CONTROL PLANT DID NOT LAND: the dispatch arm survived the deletion in the copy"
if grep -q '^documented-but-unreachable clean$' <<<"$(verb_findings "$ctl/run.sh" "$ctl/legacy.sh")"; then
    ok "CONTROL: deleting a dispatch arm for a documented verb is reported as unreachable"
else
    no "CONTROL: an orphaned verb was NOT reported; the set equality proves nothing"
fi
cp "$SRC" "$ctl/legacy.sh"

# (c) a subcommand that exists but is undocumented -- the seven this gate found.
#
# PLANT ASSERTED, same argument as (a) and (b).
grep -q '^  fix shell           ' "$ctl/legacy.sh" ||
    no "CONTROL PLANT DID NOT LAND: the legacy help text no longer documents 'fix shell' in that shape, so the undocumented-subcommand control below plants nothing and passes for free"
sed -i 's/^  fix shell           .*$//' "$ctl/legacy.sh"
grep -q '^  fix shell           ' "$ctl/legacy.sh" &&
    no "CONTROL PLANT DID NOT LAND: the help line survived the deletion in the copy"
if grep -q '^dispatched-but-undocumented fix/shell$' <<<"$(verb_findings "$ctl/run.sh" "$ctl/legacy.sh")"; then
    ok "CONTROL: deleting a help line for a live SUBCOMMAND is reported, so the second level is really checked"
else
    no "CONTROL: an undocumented subcommand was NOT reported; the second-level half proves nothing"
fi
rm -rf "$ctl"

# --- 6b. controls for the two clauses REWRITTEN 2026-09-09 (E3) ----------------
# Both branches below are new, and a new branch that has never been seen to fire is
# not yet a check. Each clause is driven directly, in both directions.

# (d) THE VACUITY CLAUSE FIRES on each of the three shapes it names.
fires() { # fires <label> <needle> <args to vacuity_findings...>
    local label="$1" needle="$2"
    shift 2
    if grep -q "$needle" <<<"$(vacuity_findings "$@")"; then
        ok "CONTROL: $label"
    else
        no "CONTROL: $label -- the clause did NOT fire, so its green proves nothing"
    fi
}
fires "an empty show_help is reported" "documents no verb" 2 0 16 0 50 50
fires "a tree where nothing dispatches is reported" "nothing dispatches" 0 0 0 18 50 50
fires "a live legacy dispatcher with no extracted subcommands is reported" \
    "second level is checking nothing" 2 0 16 18 0 50

# (e) THE CLAUSE THIS REWRITE EXISTS FOR, and the one the old one got wrong. When
# every top-level verb has been ported, the legacy dispatcher holds ZERO arms and the
# second level is legitimately empty with it. The old clause required n_legacy > 0
# and would have gone red at the exact moment the migration succeeded, on the gate
# whose whole job is guarding that migration.
if [[ -z "$(vacuity_findings 2 16 0 18 0 50)" ]]; then
    ok "CONTROL: the TERMINAL state (every verb ported, legacy dispatcher empty) is not a vacuity failure"
else
    no "CONTROL: the terminal state is reported as vacuous; this gate reds when the migration succeeds:"$'\n'"$(vacuity_findings 2 16 0 18 0 50)"
fi
if [[ -z "$(vacuity_findings "$n_router" "$n_ported" "$n_legacy" "$n_docs" "$n_subs" "$n_doc_subs")" ]]; then
    ok "CONTROL: today's real numbers are not reported as vacuous either"
else
    no "CONTROL: the clause fires on the live tree, so the two cases above prove nothing about it"
fi

# (f) THE TABLE EXCLUSION, both directions, on copies. A multi-line PORTED_VERBS must
# cost the ceiling nothing, and anything in it that is not a verb name must cost it a
# line AND be named.
tctl="$(mktemp -d)"
{
    echo 'PORTED_VERBS=('
    echo '    setup'
    echo '    quality   # already ported'
    echo ''
    echo ')'
} >"$tctl/table.sh"
if [[ "$(router_table_of "$tctl/table.sh")" == "5 0" ]]; then
    ok "CONTROL: a multi-line verb table is excluded WHOLE, structural lines included"
else
    no "CONTROL: the verb-table exclusion miscounted: got '$(router_table_of "$tctl/table.sh")', want '5 0'"
fi
{
    echo 'PORTED_VERBS=('
    echo '    setup'
    echo '    $(curl -s http://example.invalid/verbs)'
    echo ')'
} >"$tctl/smuggled.sh"
smuggled="$(router_table_of "$tctl/smuggled.sh")"
if [[ "${smuggled%%$'\n'*}" == "3 1" ]]; then
    ok "CONTROL: code smuggled into the verb table is counted as logic and named, not exempted"
else
    no "CONTROL: code inside PORTED_VERBS was silently exempted from the ceiling: got '${smuggled%%$'\n'*}', want '3 1'"
fi
printf 'PORTED_VERBS=(setup quality)\n' >"$tctl/oneline.sh"
if [[ "$(router_table_of "$tctl/oneline.sh")" == "1 0" ]]; then
    ok "CONTROL: the single-line form is excluded too, so the two spellings cost the same"
else
    no "CONTROL: the single-line form was counted as logic: got '$(router_table_of "$tctl/oneline.sh")', want '1 0'"
fi
rm -rf "$tctl"

# --- 7. the router stays a router --------------------------------------------
# A ceiling, not a style rule. The whole point of the split is that porting a verb
# touches one line here; a router that starts absorbing logic re-creates the file
# the split was undoing, one reasonable special case at a time.
#
# THE TABLE IS NOT LOGIC, decided 2026-09-09 rather than discovered later. run.sh:16
# promises that "porting a verb is one line in PORTED_VERBS and nothing else moves",
# and the file sits at 120 of 120: the moment that array goes multi-line, the very
# next port has to raise this ceiling in the same commit, which is a second edit per
# port and the exact contradiction of the promise. Worse, raising a ceiling to land a
# change is how a ceiling stops meaning anything. So the ceiling measures the
# router's LOGIC and the verb table is excluded from it.
#
# THE WHOLE TABLE IS EXCLUDED, its two structural lines included, and that is the
# difference between "cheaper" and "free". Excluding only the verb rows leaves the
# `PORTED_VERBS=(` / `)` pair costing one line more than the single-line form, so the
# FIRST port that needs a multi-line table still has to raise the ceiling -- measured
# on the real file 2026-09-09: 124 lines, 3 rows excluded, 121 of 120, red by one.
# The single-line form is excluded too, so the two spellings cost the same nothing
# and no port ever pays for the shape of the table.
#
# THE HOLE THAT OPENS, AND WHAT CLOSES IT. An exclusion is somewhere to hide code. A
# row is excluded only when it is a BARE VERB NAME (optionally with a trailing
# comment) or blank; anything else inside the array is counted as logic AND reported
# by name, so a `$(...)` smuggled between two verbs costs a line and a finding rather
# than buying an exemption.
router_table="$(router_table_of "$RUN")"
table_rows="${router_table%% *}"
table_rest="${router_table#* }"
table_bad="${table_rest%%$'\n'*}"
table_bad="${table_bad%% *}"
router_lines=$(wc -l <"$RUN")
logic_lines=$((router_lines - table_rows))
if [[ "$table_bad" -gt 0 ]]; then
    no "PORTED_VERBS holds $table_bad line(s) that are not a bare verb name; the array is a table, not somewhere to put code:$(sed "s/^[0-9]* [0-9]*//" <<<"$router_table")"
fi
if [[ "$logic_lines" -le 120 ]]; then
    ok "run.sh is still a router ($logic_lines logic lines of 120, plus $table_rows verb-table row(s) = $router_lines)"
else
    no "run.sh has grown to $logic_lines lines of logic (plus $table_rows verb-table row(s)); the ceiling is 120 and logic belongs on one side or the other"
fi
# The Python arm names a module that has to exist, or the first port fails with
# ModuleNotFoundError and a verb nobody can reach.
if grep -q 'python3 -m rediacc_ci' "$RUN" && [[ -f "$ROOT/.ci/rediacc_ci/__init__.py" ]]; then
    ok "the router's Python arm names rediacc_ci, and that package is on disk"
else
    no "the router's Python arm and .ci/rediacc_ci/__init__.py disagree; the ported half cannot work"
fi

tally_finish "run.sh"
exit $?
