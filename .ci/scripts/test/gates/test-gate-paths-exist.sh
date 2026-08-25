#!/bin/bash
# Gate: every hardcoded packages/<name>/... and private/<name>/... path constant
# in our tooling must resolve to something that exists in the tree.
#
# WHY THIS EXISTS
# ---------------
# PR #513 deleted packages/web, packages/desktop, packages/e2e and the
# middleware tree. 22+ scripts kept pointing at them. The paths did not throw --
# they silently produced empty globs, empty Sets and empty file lists, so the
# gates built on top of them printed a checkmark for months while asserting
# nothing at all (check-www-only-translations.ts compared two empty sets).
#
# A dead path constant is the cheapest possible signal that a gate has gone
# vacuous, and it is fully static. This gate would have caught every one of
# those 22 sites the day the web console was deleted.
#
# WHAT IT CHECKS
# --------------
# Tier A (package roots): the `packages/<name>` / `private/<name>` prefix of
#   every literal must exist. Near-zero false-positive rate; this is the tier
#   that catches a deleted workspace.
# Tier B (full paths): the whole literal must exist, but only when it is
#   unambiguously a checked-in source path -- it carries a known source
#   extension, or it ends in `/`. Anything else is left to Tier A.
#
# WHAT IT DELIBERATELY DOES NOT CATCH (precision over recall -- a noisy gate
# gets suppressed, and a suppressed gate is the bug we are fixing)
# ---------------------------------------------------------------
#   * Paths assembled at runtime from variables (`packages/${name}/dist`).
#     The literal is a fragment; only its Tier A prefix is meaningful.
#   * Glob patterns and .gitignore-style strings (anything with * ? { } [ ]).
#   * Anything inside a line comment (//, #, *) -- prose and BLOCKER notes
#     name deleted paths on purpose.
#   * Build outputs and vendored trees: dist/, build/, bin/, coverage/,
#     node_modules/, .astro/, .backups/. Absent on a clean checkout by design.
#   * Extensionless paths, which are ambiguous between "directory that should
#     exist" and "prefix of a name completed at runtime"
#     (`private/renet/bin/renet-linux-` + "${arch}").
#   * Submodule interiors when the submodule is not checked out -- the whole
#     scan is skipped for a `private/<name>` whose root is an empty directory.
#
# TypeScript NodeNext note: `./x.js` specifiers legitimately resolve to `x.ts`,
# so a missing `.js`/`.jsx` path is re-checked against its .ts/.tsx sibling
# before being reported.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

# Where the two control cases plant their synthetic scan targets.
#
# NOT scripts/, and not a mktemp -d either. The controls have to sit inside a
# directory scan_targets() actually walks, or the detector never sees them and
# the control silently stops firing -- so a temp dir outside the repo is not an
# option. But scripts/ is ALSO linted (`eslint packages scripts private/account`,
# and knip's project glob `scripts/**/*.ts`), and a file that appears and
# vanishes mid-run raced a concurrent `npm run check:lint` into
# `ENOENT ... open '.../scripts/.gate-paths-exist-fixture.ts'`, exit 2. That was
# never a lint failure; it was this gate polluting a linted tree.
#
# .ci/scripts satisfies both halves, measured rather than assumed on 2026-07-31:
# `find .ci/scripts -type f -name '*.ts'` reaches a dotfile planted here, and
# `eslint packages scripts private/account` reports ZERO hits for it. biome
# (packages/ private/account/) and knip (*.{js,ts}, scripts/**/*.ts) do not
# cover .ci either. Keep it out of .ci/scripts/test/, which scan_targets()
# excludes on purpose.
FIXTURE_DIR="$REPO_ROOT/.ci/scripts"

# The fixture filenames carry THIS PROCESS's pid, and that is a correctness fix
# rather than tidiness. They used to be fixed names, so two concurrent
# invocations -- two sessions each running the battery, which nothing prevents
# -- planted the same two paths and each `trap rm -f` deleted the OTHER run's
# fixture. On 2026-08-05 that surfaced as a false "detector broken": the
# control's collect_dead_paths came back empty because its fixture had already
# been removed by a neighbour. run-all.sh's W chain serialises this test WITHIN
# one battery and cannot serialise across independent processes.
#
# The dotfile prefix is load-bearing (it is what keeps eslint, biome and knip
# off these files) and the `.ts` suffix is what scan_targets() globs for, so the
# pid goes between them. FIXTURE_NAME_PREFIX is the shape both fixtures share
# ACROSS pids: a concurrent run's fixtures are still visible to this one's scan,
# so the assertions below scope themselves with it rather than assuming they are
# alone in the tree.
FIXTURE_PID_SUFFIX="$$"
FIXTURE_NAME_PREFIX='.gate-paths-exist-'

# Where the parallel extraction workers drop their per-batch output. Pid-scoped
# for the same reason the fixtures are, and torn down by the same trap.
PARTS_DIR="${TMPDIR:-/tmp}/gate-paths-exist-parts.$FIXTURE_PID_SUFFIX"

# Belt to the per-test RETURN traps' braces. A RETURN trap does not fire when
# the shell is killed or interrupted, and a Ctrl-C or a `pkill` on this test is
# routine (it used to run for MINUTES; see extract_all_literals). With fixed
# filenames an orphan was invisible (the next run overwrote it); pid-named ones
# ACCUMULATE in a tracked directory instead, so they get cleaned here too.
# Scoped to this pid: a concurrent run's fixtures are not ours to delete, which
# is the whole point of the suffix.
# BLOCKER: pid-scoped so a concurrent invocation's fixtures survive; a wildcard here would recreate the cross-process deletion this suffix exists to fix
trap 'rm -rf "$PARTS_DIR"; rm -f "$FIXTURE_DIR/${FIXTURE_NAME_PREFIX}fixture.$FIXTURE_PID_SUFFIX.ts" "$FIXTURE_DIR/${FIXTURE_NAME_PREFIX}noise-fixture.$FIXTURE_PID_SUFFIX.ts"' EXIT INT TERM

# Directory prefixes that are generated, vendored, or gitignored. A literal
# whose path traverses one of these is skipped in Tier B.
EPHEMERAL_SEGMENTS='/(dist|build|bin|out|coverage|node_modules|\.astro|\.backups|\.cache)(/|$)'

# Extensions that mark a literal as a checked-in source path worth Tier B.
SOURCE_EXTENSIONS='\.(ts|tsx|js|jsx|cjs|mjs|json|jsonc|md|mdx|sh|go|ya?ml|astro|css|html|toml|txt|py)$'

# scan_targets -- the tooling files whose path constants we police.
scan_targets() {
    cd "$REPO_ROOT"
    find scripts -type f \( -name '*.ts' -o -name '*.sh' \) ! -path '*/node_modules/*'
    find packages/www/scripts -type f -name '*.js' ! -path '*/node_modules/*'
    # .ci/scripts is where the ~120 shell gates live -- the largest body of
    # path-constant-bearing tooling in the repo, and it was out of scope here
    # for no documented reason (unlike the deliberate exclusions above).
    # .ci/scripts/test/** is excluded on purpose: those files name planted
    # fixture paths that do not exist by design.
    find .ci/scripts -type f \( -name '*.ts' -o -name '*.sh' \) \
        ! -path '*/node_modules/*' ! -path '.ci/scripts/test/*'
}

# extract_all_literals -- emit "<file>\t<line>\t<path>" for every quoted path
# literal in every scan target, skipping lines that are pure comment prose.
#
# ONE awk pass per BATCH of files, deliberately. The previous shape ran a
# `grep -noE` per file and then, per QUOTED STRING, a `printf | grep -oE |
# sed -E | while read` pipeline, plus a `sed -n <N>p` per hit for the comment
# check. Counted on this tree: 59,443 quoted strings x a four-process pipeline
# = ~238,000 processes per scan, and the gate scans three times -- about
# 715,000 processes, strictly serial, on an 8-core box that sat half idle
# throughout. It is spawn-bound, not CPU-bound. That cost 51 MINUTES of wall
# clock, which is why the quality-gate battery stopped being something anyone
# ran before pushing. The work is unchanged; only the process count is.
# Measured 2026-08-25: 51m02s -> 8s for the whole gate (~6s of which is the
# `npx tsc --listFilesOnly` in the last test), with byte-identical findings --
# 367 extracted literals, diffed line for line against the old pipeline.
#
# The old shape also had a latent vacuity trap that this one cannot have. Its
# inner pipeline exits 1 whenever a quoted string holds no path, and under
# `set -euo pipefail` that killed the whole extraction subshell at the FIRST
# such string. It only ever scanned anything because every caller happened to
# wrap it in `$(...)`, and errexit is not inherited by a command-substitution
# subshell without `shopt -s inherit_errexit`. One caller written without the
# `$(...)` and this gate would have gone quietly, permanently blind -- exactly
# the failure it exists to catch. awk has no such dependency.
#
# Only text inside a quote pair is considered, which is what keeps prose out.
# Splitting each line on the three quote characters and dropping field 1
# reproduces the old grep for a leading quote plus a run of non-quote
# characters exactly: field N+1 is the run that followed the Nth quote.
# Candidates carrying shell/glob metacharacters are dropped wholesale rather
# than partially matched, and the comment-prose skip is the same regex the
# per-hit `sed` used to re-read the line for.
EXTRACT_AWK='
/^[[:space:]]*(\/\/|#|\*|\/\*)/ { next }
{
    n = split($0, seg, "[\"\047\140]")
    for (i = 2; i <= n; i++) {
        s = seg[i]
        if (s ~ /[]*?{}$[]/) continue
        while (match(s, /(packages|private)\/[A-Za-z0-9._+-]+(\/[A-Za-z0-9._+-]+)*\/?/)) {
            p = substr(s, RSTART, RLENGTH)
            s = substr(s, RSTART + RLENGTH)
            sub(/\.+$/, "", p)
            if (p != "") print FILENAME "\t" FNR "\t" p
        }
    }
}'

extract_all_literals() {
    cd "$REPO_ROOT"
    local jobs
    jobs="$(nproc 2>/dev/null || echo 4)"
    rm -rf "$PARTS_DIR"
    mkdir -p "$PARTS_DIR"
    # Each worker writes its OWN part file instead of sharing stdout: awk
    # flushes in block-sized writes, a write larger than PIPE_BUF is not
    # atomic, and interleaved halves of two lines would be a corrupt finding
    # rather than a loud failure. Order does not matter -- collect_dead_paths
    # ends in `sort -u`.
    GATE_EXTRACT_AWK="$EXTRACT_AWK" GATE_PART_DIR="$PARTS_DIR" \
        xargs -r -d '\n' -P "$jobs" -n 48 bash -c '
            if ! awk "$GATE_EXTRACT_AWK" "$@" >"$GATE_PART_DIR/part.$$" 2>/dev/null; then
                # A scan target can VANISH mid-run: a concurrent invocation of
                # this same test plants and removes fixtures inside the scanned
                # tree, and awk abandons the rest of its argument list when one
                # file will not open. The old per-file grep swallowed that with
                # 2>/dev/null, so retry file by file rather than failing the
                # gate on a neighbour cleaning up after itself.
                : >"$GATE_PART_DIR/part.$$"
                for f in "$@"; do
                    [ -r "$f" ] || continue
                    awk "$GATE_EXTRACT_AWK" "$f" >>"$GATE_PART_DIR/part.$$" 2>/dev/null || true
                done
            fi
        ' _ < <(scan_targets)
    if compgen -G "$PARTS_DIR/part.*" >/dev/null; then
        cat "$PARTS_DIR"/part.*
    fi
    rm -rf "$PARTS_DIR"
}

# path_resolves <path> -- existence check with NodeNext .js -> .ts fallback.
path_resolves() {
    local path="$1"
    [[ -e "$path" ]] && return 0
    case "$path" in
        *.js) [[ -e "${path%.js}.ts" ]] && return 0 ;;
        *.jsx) [[ -e "${path%.jsx}.tsx" ]] && return 0 ;;
    esac
    return 1
}

# submodule_checked_out <path> -- false when the private/<name> root is empty,
# meaning the submodule was never initialised in this checkout.
submodule_checked_out() {
    local root="$1"
    [[ -d "$root" ]] || return 1
    [[ -n "$(ls -A "$root" 2>/dev/null)" ]]
}

# declared_submodule <path> -- true when .gitmodules declares this path.
#
# A `private/<name>` that is NOT declared is an EXTERNAL repository this one does
# not track (private/growth and private/generative are separate GitLab repos; the
# scripts referencing them handle their absence). Such a root is legitimately
# missing from a fresh checkout, so its absence is not a dead path -- CI has no
# private/growth at all, which is what made this gate fail there while passing
# locally. Deriving this from .gitmodules rather than a hardcoded list keeps it
# correct when a submodule is added or removed.
declared_submodule() {
    local root="$1"
    grep -qE "^[[:space:]]*path[[:space:]]*=[[:space:]]*${root}[[:space:]]*$" "$REPO_ROOT/.gitmodules" 2>/dev/null
}

collect_dead_paths() {
    cd "$REPO_ROOT"
    local file line path root rest
    # The two submodule probes below spawn a process each and their answer is
    # per-ROOT, not per-hit; memoise them so a tree full of private/* literals
    # costs one probe per submodule rather than one per literal.
    local -A declared_cache=() checkout_cache=()
    while IFS=$'\t' read -r file line path; do
        rest="${path#*/}"
        root="${path%%/*}/${rest%%/*}"
        if [[ ! -d "$root" ]]; then
            # An undeclared private/<name> is an external repo, not a dead path.
            if [[ "$root" == private/* ]]; then
                if [[ -z "${declared_cache[$root]+x}" ]]; then
                    declared_cache[$root]=0
                    declared_submodule "$root" && declared_cache[$root]=1
                fi
                [[ "${declared_cache[$root]}" == 0 ]] && continue
            fi
            printf 'TIER-A %s:%s: %s (workspace root %s does not exist)\n' \
                "$file" "$line" "$path" "$root"
            continue
        fi
        # Tier B only: an uninitialised submodule is not a dead path.
        if [[ "$root" == private/* ]]; then
            if [[ -z "${checkout_cache[$root]+x}" ]]; then
                checkout_cache[$root]=0
                submodule_checked_out "$root" && checkout_cache[$root]=1
            fi
            [[ "${checkout_cache[$root]}" == 0 ]] && continue
        fi

        [[ "$path" == "$root" ]] && continue
        [[ "$path" =~ $EPHEMERAL_SEGMENTS ]] && continue
        if [[ ! "$path" =~ $SOURCE_EXTENSIONS ]] && [[ "$path" != */ ]]; then
            continue
        fi
        path_resolves "$path" && continue
        printf 'TIER-B %s:%s: %s\n' "$file" "$line" "$path"
    done < <(extract_all_literals) | sort -u
}

# The scan must be WHOLE before an empty result means anything. Every
# assertion here reads an empty `dead` list as "no dead paths", so a scan that
# silently walked a fraction of the tree hands back a clean bill of health from
# an instrument that barely ran.
#
# THIS IS NOT HYPOTHETICAL. Inside a full 168-gate `npm run ci` on 2026-08-05
# this suite finished in 90.6s against 210-231s whenever it was healthy, and
# its own planted-defect control -- which writes a fixture naming a workspace
# that has never existed and asserts the detector reports it -- came back
# EMPTY. Alone, in a 2-gate batch, in a 3-gate batch and in a re-run of the
# exact 4-gate batch that failed, it passed every time. The signal was never a
# co-running gate; it was DURATION, i.e. the walk terminating around 40% of
# the way through under whatever pressure a full fleet applies.
#
# The floor converts that silent truncation into a loud refusal. It is set
# well under the ~363 files the three legs yield today (132 + 24 + 207) so
# ordinary churn never trips it, and far above the handful a truncated walk
# would return.
SCAN_FLOOR="${GATE_PATHS_SCAN_FLOOR:-150}"

assert_scan_is_whole() {
    local n
    n="$(scan_targets | wc -l)"
    if ((n < SCAN_FLOOR)); then
        log_fail "scan_targets yielded only $n file(s), floor $SCAN_FLOOR: the walk TRUNCATED, so an empty finding list here would be a false clean bill rather than a clean tree"
    fi
    log_pass "the scan is whole ($n files, floor $SCAN_FLOOR)"
}

test_no_dead_path_constants() {
    assert_scan_is_whole
    local all dead
    # Two steps, not a pipeline: collect_dead_paths keeps its own failure under
    # set -e, which a trailing `|| true` on the same pipeline would swallow.
    #
    # A CONCURRENT invocation of this same test plants its own control fixture,
    # which is a deliberate dead path and would read here as a real finding.
    # Filtering by the fixture filename shape is precise: nothing but this test
    # writes a `.gate-paths-exist-*` file into the scanned tree.
    all="$(collect_dead_paths)"
    dead="$(printf '%s\n' "$all" | grep -vF -- "$FIXTURE_NAME_PREFIX" || true)"
    if [[ -n "$dead" ]]; then
        echo "$dead" >&2
        log_fail "dead path constants found (see list above)"
    fi
    log_pass "every hardcoded packages/* and private/* path constant resolves"
}

test_detector_fires_on_a_deleted_workspace() {
    # Control: prove the instrument can FAIL. A synthetic scan target naming a
    # workspace that has never existed must be reported, otherwise this gate is
    # exactly the vacuous check it was written to prevent.
    local fixture="$FIXTURE_DIR/${FIXTURE_NAME_PREFIX}fixture.$FIXTURE_PID_SUFFIX.ts"
    # BLOCKER: expanding fixture now binds the specific path into the trap so cleanup fires even if the variable is later reassigned
    # shellcheck disable=SC2064
    trap "rm -f '$fixture'" RETURN
    printf 'const p = "packages/definitely-not-a-workspace/src/index.ts";\n' >"$fixture"

    # Guard the CONTROL too, and for the sharper reason: this is the case that
    # actually failed under load. Without the floor its failure message was
    # "not in ''", which reads as "the detector is broken" when the truth was
    # "the walk never reached the fixture". Diagnosing the wrong thing cost a
    # full bisect across four batch shapes.
    assert_scan_is_whole
    local dead own
    dead="$(collect_dead_paths)"
    # Scoped to OUR fixture by name. A concurrent invocation plants the same
    # dead path under its own pid, and an unscoped assertion would pass off that
    # one -- a control that can be satisfied by somebody else's fixture is not a
    # control.
    # Anchored on the full fixture basename: a suffix match ("-fixture.<pid>")
    # also catches this pid's noise-fixture, whose name ends the same way.
    own="$(printf '%s\n' "$dead" | grep -F -- "${FIXTURE_NAME_PREFIX}fixture.$FIXTURE_PID_SUFFIX.ts" || true)"
    assert_contains "$own" "packages/definitely-not-a-workspace" \
        "detector must report a path under a nonexistent workspace"
    log_pass "detector fires on a deleted workspace (control case)"
}

test_detector_ignores_runtime_and_glob_paths() {
    # Shape check: the two biggest false-positive sources must stay silent.
    local fixture="$FIXTURE_DIR/${FIXTURE_NAME_PREFIX}noise-fixture.$FIXTURE_PID_SUFFIX.ts"
    # BLOCKER: expanding fixture now binds the specific path into the trap so cleanup fires even if the variable is later reassigned
    # shellcheck disable=SC2064
    trap "rm -f '$fixture'" RETURN
    {
        printf 'const a = `packages/${name}/src/index.ts`;\n'
        printf 'const b = "packages/*/dist/**/*.js";\n'
        printf '// packages/web/src/App.tsx was deleted in #513\n'
    } >"$fixture"

    local dead
    dead="$(collect_dead_paths)"
    assert_not_contains "$dead" "gate-paths-exist-noise-fixture" \
        "template literals, globs and comment prose must not be reported"
    log_pass "runtime-built paths, globs and comments are ignored"
}

# ---------------------------------------------------------------------------
# Same failure class, one level up: an `include` GLOB that resolves to nothing.
#
# A dead path constant and a dead include pattern fail identically -- both
# produce an empty set that every downstream check reports a checkmark over.
# scripts/tsconfig.json is the live example. It sat in the tree from creation
# until 2026-08-05 covering 70 files that nothing type-checked, and when it was
# finally run it produced 512 errors, ~99% of them artifacts of its own stale
# settings. A config that LOOKS like coverage is worse than no config, because
# it answers the question "is this tree type-checked?" with a yes.
#
# It now also carries `.ci/scripts/**/*.ts`, which has no other config anywhere.
# That tree is a single file today, so a glob edit that quietly dropped it would
# cost exactly one file and would be invisible in any error count. Hence naming
# a known file from EACH tree rather than only counting.
#
# --listFilesOnly resolves the includes without type-checking (~1.7s). This is
# deliberately a COVERAGE assertion, not the type-check itself: wiring
# `tsc -p scripts/tsconfig.json` into check:types is a package.json edit and is
# the operator's call, not this gate's.
# ---------------------------------------------------------------------------
test_scripts_tsconfig_covers_both_tooling_trees() {
    local cfg="$REPO_ROOT/scripts/tsconfig.json"
    [[ -f "$cfg" ]] || log_fail "scripts/tsconfig.json is gone; the tooling trees have no type-check target at all"

    local listed
    if ! listed="$(cd "$REPO_ROOT" && npx tsc -p scripts/tsconfig.json --listFilesOnly 2>/dev/null)"; then
        log_fail "could not resolve scripts/tsconfig.json's file list; a config that cannot be loaded checks nothing"
    fi
    # CONTROL: an unresolvable or empty include would also produce a quiet pass
    # below if we only grepped for absence, so assert the list is non-trivial
    # first.
    # Anchored at REPO_ROOT: an unanchored "/scripts/" also matches
    # packages/www/scripts/, which allowJs pulls in, and would inflate the count
    # with files this config is not responsible for.
    local n_scripts n_ci
    n_scripts="$(grep -c "^${REPO_ROOT}/scripts/.*\.ts$" <<<"$listed" || true)"
    n_ci="$(grep -c "^${REPO_ROOT}/\.ci/scripts/.*\.ts$" <<<"$listed" || true)"
    if [[ "$n_scripts" -lt 10 ]]; then
        log_fail "scripts/tsconfig.json resolves only $n_scripts file(s) under scripts/; the include glob has gone empty or near-empty"
    fi
    if [[ "$n_ci" -lt 1 ]]; then
        log_fail "scripts/tsconfig.json resolves NO file under .ci/scripts/; that tree has no other tsconfig, so it is now unchecked by anything"
    fi
    # And name one known file per tree, so a glob narrowed to a subdirectory
    # still fails even while the counts stay healthy.
    assert_contains "$listed" "/scripts/check-cli-docs.ts" \
        "a known scripts/ file must be in the resolved set"
    assert_contains "$listed" "/.ci/scripts/test/smoke-test-preview.ts" \
        "the only .ci/scripts/ TypeScript file must be in the resolved set"
    log_pass "scripts/tsconfig.json covers both tooling trees ($n_scripts under scripts/, $n_ci under .ci/scripts/)"
}

log_test "test-gate-paths-exist"
test_detector_fires_on_a_deleted_workspace
test_detector_ignores_runtime_and_glob_paths
test_no_dead_path_constants
test_scripts_tsconfig_covers_both_tooling_trees
echo ""
log_pass "all tests passed"
