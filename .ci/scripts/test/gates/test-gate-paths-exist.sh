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

# extract_literals <file> -- emit "<line>:<path>" for each quoted path literal.
#
# Only text inside a quote pair is considered, which is what keeps prose out.
# Candidates carrying shell/glob metacharacters are dropped wholesale rather
# than partially matched.
extract_literals() {
    local file="$1"
    grep -noE "['\"\`][^'\"\`]*" "$file" 2>/dev/null | while IFS=: read -r line rest; do
        local seg="${rest:1}"
        # Comment prose names deleted paths on purpose; skip those lines.
        case "$seg" in
            *'*'* | *'?'* | *'{'* | *'}'* | *'['* | *']'* | *'$'*) continue ;;
        esac
        printf '%s\n' "$seg" |
            grep -oE '(packages|private)/[A-Za-z0-9._+-]+(/[A-Za-z0-9._+-]+)*/?' |
            sed -E 's/\.+$//' |
            while read -r path; do
                [[ -n "$path" ]] && printf '%s:%s\n' "$line" "$path"
            done
    done
}

# is_comment_line <file> <lineno> -- true when the line is pure comment prose.
is_comment_line() {
    local file="$1" lineno="$2" text
    text="$(sed -n "${lineno}p" "$file")"
    [[ "$text" =~ ^[[:space:]]*(//|#|\*|/\*) ]]
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
    local file line path root
    while read -r file; do
        while IFS= read -r hit; do
            line="${hit%%:*}"
            path="${hit#*:}"
            is_comment_line "$file" "$line" && continue

            root="$(printf '%s' "$path" | cut -d/ -f1-2)"
            if [[ ! -d "$root" ]]; then
                # An undeclared private/<name> is an external repo, not a dead path.
                [[ "$root" == private/* ]] && ! declared_submodule "$root" && continue
                printf 'TIER-A %s:%s: %s (workspace root %s does not exist)\n' \
                    "$file" "$line" "$path" "$root"
                continue
            fi
            # Tier B only: an uninitialised submodule is not a dead path.
            [[ "$root" == private/* ]] && ! submodule_checked_out "$root" && continue

            [[ "$path" == "$root" ]] && continue
            [[ "$path" =~ $EPHEMERAL_SEGMENTS ]] && continue
            if [[ ! "$path" =~ $SOURCE_EXTENSIONS ]] && [[ "$path" != */ ]]; then
                continue
            fi
            path_resolves "$path" && continue
            printf 'TIER-B %s:%s: %s\n' "$file" "$line" "$path"
        done < <(extract_literals "$file")
    done < <(scan_targets) | sort -u
}

test_no_dead_path_constants() {
    local dead
    dead="$(collect_dead_paths)"
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
    local fixture="$FIXTURE_DIR/.gate-paths-exist-fixture.ts"
    # BLOCKER: expanding fixture now binds the specific path into the trap so cleanup fires even if the variable is later reassigned
    # shellcheck disable=SC2064
    trap "rm -f '$fixture'" RETURN
    printf 'const p = "packages/definitely-not-a-workspace/src/index.ts";\n' >"$fixture"

    local dead
    dead="$(collect_dead_paths)"
    assert_contains "$dead" "packages/definitely-not-a-workspace" \
        "detector must report a path under a nonexistent workspace"
    log_pass "detector fires on a deleted workspace (control case)"
}

test_detector_ignores_runtime_and_glob_paths() {
    # Shape check: the two biggest false-positive sources must stay silent.
    local fixture="$FIXTURE_DIR/.gate-paths-exist-noise-fixture.ts"
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
