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
    local fixture="$REPO_ROOT/scripts/.gate-paths-exist-fixture.ts"
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
    local fixture="$REPO_ROOT/scripts/.gate-paths-exist-noise-fixture.ts"
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

log_test "test-gate-paths-exist"
test_detector_fires_on_a_deleted_workspace
test_detector_ignores_runtime_and_glob_paths
test_no_dead_path_constants
echo ""
log_pass "all tests passed"
