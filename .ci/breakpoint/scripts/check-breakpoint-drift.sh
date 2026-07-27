#!/bin/bash
# Prove that this copy of .ci/breakpoint/ still IS the canonical one.
#
# WHAT THIS DEFENDS AGAINST
# breakpoint is designed to be copied wholesale into other repositories. A copy
# rots in two different ways, and they need different answers:
#
#   TAMPER (the realistic one, and the DEFAULT mode): somebody edited a vendored
#   script in place -- to unblock a job, to "just try something" -- and the edit
#   silently became this repo's private fork. Nothing upstream can ever fix it
#   again, and the next re-vendor overwrites it without anyone knowing what was
#   lost. Detecting this needs NO NETWORK: the manifest shipped with the copy is
#   the reference.
#
#   STALENESS (--verify-upstream): the canonical repo moved on and this copy did
#   not. That needs the network, so it must never be able to redden a build on
#   its own.
#
# Usage:
#   check-breakpoint-drift.sh [--verify]           # default, offline
#   check-breakpoint-drift.sh --verify-upstream    # network, fails soft
#   check-breakpoint-drift.sh --write              # regenerate the manifest
#
# Exit: 0 clean (or a soft network failure), 1 drift / refusal, 2 bad usage.
#
# MANIFEST FORMAT: .ci/breakpoint/MANIFEST.sha256 is native `sha256sum -c` text
# with paths RELATIVE to .ci/breakpoint/, prefixed by `# canonical:` and
# `# generated:` comment lines (which `sha256sum -c` ignores). So
# `cd .ci/breakpoint && sha256sum -c MANIFEST.sha256` works by hand. This script
# does the comparison itself rather than shelling out to `-c` because it has to
# report five distinct failure modes and honour the accept-list, none of which
# `-c` can express.
#
# FROZEN SET: scripts/*.sh, lib/*.sh, versions.sh, workflow/breakpoint.yml.
# EXCLUDED, each for a reason:
#   MANIFEST.sha256          -- cannot hash itself
#   breakpoint.conf          -- THE sanctioned per-repo edit point
#   README.md                -- downstream appends local notes; freezing prose
#                               would train people to regenerate the manifest to
#                               get green, and that habit destroys the gate
#   .breakpoint-drift-accept -- the escape hatch itself

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/breakpoint-common.sh
source "$SCRIPT_DIR/../lib/breakpoint-common.sh"
# shellcheck source=../lib/breakpoint-blocker.sh
source "$SCRIPT_DIR/../lib/breakpoint-blocker.sh"

bp_load_conf "$SCRIPT_DIR"
parse_args "$@"

BP_ROOT="$(bp_root "$SCRIPT_DIR")"
MANIFEST="$BP_ROOT/MANIFEST.sha256"
ACCEPT_FILE="$BP_ROOT/.breakpoint-drift-accept"
UPSTREAM_REPO="${BREAKPOINT_UPSTREAM_REPO:-rediacc/console}"

require_cmd sha256sum

# parse_args turns a valueless flag into the literal string "true", so every
# mode flag is tested against that string and never against a shell boolean.
MODE="verify"
if [[ "${ARG_WRITE:-}" == "true" ]]; then
    MODE="write"
elif [[ "${ARG_VERIFY_UPSTREAM:-}" == "true" ]]; then
    MODE="verify-upstream"
elif [[ "${ARG_VERIFY:-}" == "true" ]]; then
    MODE="verify"
elif [[ $# -gt 0 ]]; then
    case "$1" in
        --verify | --verify-upstream | --write) ;;
        *)
            log_error "unknown argument '$1' (expected --verify, --verify-upstream or --write)"
            exit 2
            ;;
    esac
fi

# =============================================================================
# THE FROZEN SET
# =============================================================================

# Emits frozen-set paths that exist ON DISK, relative to BP_ROOT, sorted.
bp_frozen_files() {
    {
        find "$BP_ROOT/scripts" -maxdepth 1 -type f -name '*.sh' 2>/dev/null || true
        find "$BP_ROOT/lib" -maxdepth 1 -type f -name '*.sh' 2>/dev/null || true
        if [[ -f "$BP_ROOT/versions.sh" ]]; then
            echo "$BP_ROOT/versions.sh"
        fi
        if [[ -f "$BP_ROOT/workflow/breakpoint.yml" ]]; then
            echo "$BP_ROOT/workflow/breakpoint.yml"
        fi
        # The gateway routing table. Frozen because it is BEHAVIOUR, not config:
        # its catch-all rule is what puts the application behind the tunnel, and
        # its /health rule is what makes tunnel liveness independent of the app.
        # It has no file extension, so bp_all_code_files() (which globs .sh/.yml)
        # cannot see it -- without this line it would be neither frozen nor
        # reported as UNTRACKED, i.e. silently unprotected.
        if [[ -f "$BP_ROOT/docker/Caddyfile" ]]; then
            echo "$BP_ROOT/docker/Caddyfile"
        fi
    } | sed "s|^${BP_ROOT}/||" | LC_ALL=C sort
}

# Every .sh / .yml / .yaml anywhere in the folder, relative to BP_ROOT, sorted.
# This is what makes UNTRACKED detectable: without it, a new script can be
# dropped into the folder and the gate stays green forever, which reduces the
# manifest to a list of files somebody once cared about.
bp_all_code_files() {
    find "$BP_ROOT" -type f \( -name '*.sh' -o -name '*.yml' -o -name '*.yaml' \) 2>/dev/null |
        sed "s|^${BP_ROOT}/||" | LC_ALL=C sort
}

bp_hash_of() {
    (cd "$BP_ROOT" && sha256sum "$1" | cut -d' ' -f1)
}

# =============================================================================
# WHOSE REPO IS THIS
# =============================================================================

# Resolve the current repository as owner/name, or fail.
bp_current_repo() {
    local url slug
    if [[ -n "${GITHUB_REPOSITORY:-}" ]]; then
        echo "$GITHUB_REPOSITORY"
        return 0
    fi
    url="$(git -C "$BP_ROOT" remote get-url origin 2>/dev/null || true)"
    [[ -n "$url" ]] || return 1
    slug="$(echo "$url" | sed -E 's#^.*[/:]([^/:]+/[^/]+?)(\.git)?/?$#\1#')"
    [[ "$slug" =~ ^[^/]+/[^/]+$ ]] || return 1
    echo "$slug"
}

# =============================================================================
# MODE: --write
# =============================================================================

if [[ "$MODE" == "write" ]]; then
    # THE REFUSAL BELOW IS THE ENTIRE REASON THIS GATE HAS TEETH.
    # Without it, a downstream operator hitting a drift failure "fixes" it by
    # regenerating the manifest -- which records the local fork as canonical and
    # turns every future comparison into a comparison against itself. The gate
    # then passes forever while the copy diverges without limit. Regeneration is
    # therefore permitted ONLY in the repo the copies come from.
    CURRENT_REPO="$(bp_current_repo || true)"

    if [[ -z "$CURRENT_REPO" ]]; then
        log_error "refusing --write: cannot tell which repository this is"
        echo "  Rejected because: neither GITHUB_REPOSITORY nor 'git remote get-url origin' resolved to owner/name," >&2
        echo "                    so the canonical-repo check cannot be performed, and an unverified --write is" >&2
        echo "                    exactly how a vendored fork gets blessed as canonical." >&2
        echo "  Action: run this in a checkout of ${UPSTREAM_REPO}, or set GITHUB_REPOSITORY=${UPSTREAM_REPO}." >&2
        exit 1
    fi

    if [[ "$CURRENT_REPO" != "$UPSTREAM_REPO" ]]; then
        log_error "refusing --write: this is '$CURRENT_REPO', the canonical repo is '$UPSTREAM_REPO'"
        echo "  Rejected because: regenerating the manifest downstream records THIS COPY as the reference. The" >&2
        echo "                    gate would then compare the fork against itself and pass forever, which is" >&2
        echo "                    strictly worse than no gate, because it still looks like one." >&2
        echo "  Action, pick one:" >&2
        echo "    1. Land the change in ${UPSTREAM_REPO} and run --write there, then re-vendor here with" >&2
        echo "       scripts/sync-breakpoint.sh" >&2
        echo "    2. If the change genuinely cannot be upstreamed, accept it: add the path to" >&2
        echo "       .ci/breakpoint/.breakpoint-drift-accept under a '# BLOCKER: <reason>' line" >&2
        exit 1
    fi

    files="$(bp_frozen_files)"
    if [[ -z "$files" ]]; then
        log_error "refusing --write: the frozen set is EMPTY (vacuous manifest)"
        echo "  Rejected because: a manifest with zero entries verifies nothing while reporting success." >&2
        echo "  Action: run this from a real .ci/breakpoint/ checkout containing scripts/ and lib/." >&2
        exit 1
    fi

    if [[ ! -f "$BP_ROOT/workflow/breakpoint.yml" ]]; then
        log_warn "workflow/breakpoint.yml is absent; the manifest will not cover the workflow template"
    fi

    canonical_sha="$(git -C "$BP_ROOT" rev-parse HEAD 2>/dev/null || echo "unknown")"
    generated_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    {
        # Informational only: this is the commit the manifest was generated ON
        # TOP OF, so it is the PARENT of the commit that will carry it. It exists
        # to answer "which console does this copy come from", not to be verified.
        echo "# canonical: ${UPSTREAM_REPO}@${canonical_sha}"
        echo "# generated: ${generated_at}"
        (cd "$BP_ROOT" && while IFS= read -r f; do
            [[ -z "$f" ]] && continue
            sha256sum "$f"
        done <<<"$files")
    } >"$MANIFEST"

    written="$(grep -cv '^#' "$MANIFEST" || true)"
    log_info "wrote $MANIFEST ($written entries, canonical ${UPSTREAM_REPO}@${canonical_sha})"
    exit 0
fi

# =============================================================================
# SHARED: LOAD MANIFEST + ACCEPT LIST
# =============================================================================

if [[ ! -f "$MANIFEST" ]]; then
    log_error "no manifest at $MANIFEST"
    echo "  Rejected because: without a manifest there is nothing to compare against, and reporting success" >&2
    echo "                    here would mean a copy with its manifest deleted is the easiest way to pass." >&2
    echo "  Action, pick one:" >&2
    echo "    1. Re-vendor the canonical copy: .ci/breakpoint/scripts/sync-breakpoint.sh" >&2
    echo "    2. In ${UPSTREAM_REPO} only, generate one: .ci/breakpoint/scripts/check-breakpoint-drift.sh --write" >&2
    exit 1
fi

declare -A MANIFEST_HASH=()
MANIFEST_COUNT=0
MALFORMED=0

while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
        '#'*) continue ;;
        '') continue ;;
    esac
    hash="${line%% *}"
    path="${line#* }"
    path="${path#"${path%%[![:space:]]*}"}"
    if [[ ! "$hash" =~ ^[0-9a-f]{64}$ ]] || [[ -z "$path" ]]; then
        log_error "manifest line is malformed: $line"
        MALFORMED=$((MALFORMED + 1))
        continue
    fi
    MANIFEST_HASH["$path"]="$hash"
    MANIFEST_COUNT=$((MANIFEST_COUNT + 1))
done <"$MANIFEST"

# Accept list. Parsed and BLOCKER-validated with the vendored subset of the
# canonical validator, so the same "no lazy suppressions" rule from
# docs/agent/suppressions.md applies here as to every other escape hatch.
declare -A ACCEPTED=()
# An accept entry that never FIRES is not the same as one that fired: the count
# line below is the anti-vacuity evidence for this gate, so it reports what the
# run actually waved through, not what the file happens to list.
declare -A ACCEPT_FIRED=()
ACCEPT_BAD=0
ACCEPT_COUNT=0

if [[ -f "$ACCEPT_FILE" ]]; then
    while IFS=$'\t' read -r acc_path acc_reason; do
        [[ -z "$acc_path" ]] && continue
        if ! bp_validate_blocker "$acc_path" "$acc_reason"; then
            ACCEPT_BAD=$((ACCEPT_BAD + 1))
            continue
        fi
        # LIVENESS HALF. A BLOCKER proves a reason EXISTS; it cannot prove the
        # reason is still TRUE. An accept entry for a path the manifest does not
        # even list is dead weight at best and a typo silently protecting
        # nothing at worst -- and it also means an UNTRACKED rogue file can
        # never be waved through, because acceptance only applies to files the
        # manifest already covers.
        if [[ -z "${MANIFEST_HASH[$acc_path]:-}" ]]; then
            log_error "drift-accept: stale accept entry '$acc_path' -- no such path in the manifest"
            echo "  Rejected because: the entry protects a file the manifest does not cover, so it can never" >&2
            echo "                    fire. Either the path is a typo, or the file it named is gone." >&2
            echo "  Action: delete the entry from $ACCEPT_FILE, or fix the path to one listed in MANIFEST.sha256." >&2
            ACCEPT_BAD=$((ACCEPT_BAD + 1))
            continue
        fi
        ACCEPTED["$acc_path"]=1
        ACCEPT_COUNT=$((ACCEPT_COUNT + 1))
    done < <(bp_parse_drift_accept "$ACCEPT_FILE")
fi

# =============================================================================
# FAILURE ACCOUNTING
# =============================================================================

FAILURES=()
add_failure() { FAILURES+=("$1"); }

report_and_exit() {
    local verified="$1"
    local fired=${#ACCEPT_FIRED[@]}
    local p

    # An entry that did not fire is NOT automatically stale: an accept can be
    # there for --verify-upstream (the file matches this copy's manifest but
    # differs from upstream), and --verify never reaches that comparison. So this
    # warns and never fails -- the hard staleness rule is manifest membership,
    # which is checked where the accept list is parsed.
    for p in "${!ACCEPTED[@]}"; do
        if [[ -z "${ACCEPT_FIRED[$p]:-}" ]]; then
            log_warn "accept entry '$p' did not fire in this mode (the file matches); it is stale unless it exists for --verify-upstream"
        fi
    done

    if [[ ${#FAILURES[@]} -eq 0 ]]; then
        log_info "Verified ${verified} files, ${fired} accepted divergences (${ACCEPT_COUNT} entr(ies) in the accept list)"
        exit 0
    fi

    log_error "breakpoint drift detected (${#FAILURES[@]} finding(s)):"
    local f
    for f in "${FAILURES[@]}"; do
        echo "  - $f" >&2
    done
    echo "" >&2
    echo "  Rejected because: .ci/breakpoint/ is a VENDORED copy whose integrity is the only thing making it" >&2
    echo "                    safe to copy. A silent local edit becomes a private fork that upstream can never" >&2
    echo "                    fix and the next re-vendor destroys without trace." >&2
    echo "  Action, pick one:" >&2
    echo "    1. Revert the local edit, if it was not intentional." >&2
    echo "    2. Re-vendor the canonical copy: .ci/breakpoint/scripts/sync-breakpoint.sh" >&2
    echo "    3. Upstream the change: land it in ${UPSTREAM_REPO}, run check-breakpoint-drift.sh --write THERE," >&2
    echo "       then re-vendor here." >&2
    echo "    4. Accept it: add the path to .ci/breakpoint/.breakpoint-drift-accept under a" >&2
    echo "       '# BLOCKER: <what is different about THIS repo and why upstream cannot carry it>' line." >&2
    echo "" >&2
    log_error "Verified ${verified} files, ${fired} accepted divergences (${ACCEPT_COUNT} entr(ies) in the accept list)"
    exit 1
}

if [[ $MALFORMED -gt 0 ]]; then
    add_failure "MALFORMED: ${MALFORMED} unreadable manifest line(s) in MANIFEST.sha256"
fi
if [[ $ACCEPT_BAD -gt 0 ]]; then
    add_failure "ACCEPT: ${ACCEPT_BAD} invalid entr(ies) in .breakpoint-drift-accept (see above)"
fi

# VACUOUS #1: a manifest with no entries. Caught BEFORE any comparison, because
# every subsequent loop would run zero times and report success.
if [[ $MANIFEST_COUNT -eq 0 ]]; then
    add_failure "VACUOUS: MANIFEST.sha256 lists zero files, so this check verified nothing"
    report_and_exit 0
fi

# =============================================================================
# 1 + 2: HASH MISMATCH AND MISSING
# =============================================================================

COMPARED=0
for path in "${!MANIFEST_HASH[@]}"; do
    expected="${MANIFEST_HASH[$path]}"
    if [[ ! -f "$BP_ROOT/$path" ]]; then
        if [[ -n "${ACCEPTED[$path]:-}" ]]; then
            log_warn "accepted (missing): $path"
            ACCEPT_FIRED["$path"]=1
            continue
        fi
        add_failure "MISSING: $path is listed in MANIFEST.sha256 but absent from disk"
        continue
    fi
    actual="$(bp_hash_of "$path")"
    COMPARED=$((COMPARED + 1))
    if [[ "$actual" != "$expected" ]]; then
        if [[ -n "${ACCEPTED[$path]:-}" ]]; then
            log_warn "accepted (modified): $path"
            ACCEPT_FIRED["$path"]=1
            continue
        fi
        add_failure "MISMATCH: $path
      expected $expected
      actual   $actual"
    fi
done

# =============================================================================
# 3: UNTRACKED
# =============================================================================

while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    if [[ -n "${MANIFEST_HASH[$path]:-}" ]]; then
        continue
    fi
    add_failure "UNTRACKED: $path is inside .ci/breakpoint/ but is not in MANIFEST.sha256 (a file nobody froze)"
done < <(bp_all_code_files)

# =============================================================================
# 4: LIVE WORKFLOW DIVERGENCE
# =============================================================================
# The template under .ci/breakpoint/workflow/ is INVISIBLE to every workflow gate
# in this repo -- check-workflows.sh, check-workflow-gates.sh and
# scripts/check-actions.ts all scan .github/ only. So a template carrying an
# unpinned action reference, a missing permissions block, or a stale SHA passes
# all three while looking reviewed. Pinning the live copy to the template is what
# puts the template back inside their reach: if they differ, one of the two was
# edited alone, and only the .github/ one was actually checked.

REPO_ROOT="${GITHUB_WORKSPACE:-$(git -C "$BP_ROOT" rev-parse --show-toplevel 2>/dev/null || echo "")}"
LIVE_WORKFLOW=""
if [[ -n "$REPO_ROOT" ]] && [[ -f "$REPO_ROOT/.github/workflows/breakpoint.yml" ]]; then
    LIVE_WORKFLOW="$REPO_ROOT/.github/workflows/breakpoint.yml"
fi

if [[ -n "$LIVE_WORKFLOW" ]]; then
    if [[ ! -f "$BP_ROOT/workflow/breakpoint.yml" ]]; then
        add_failure "WORKFLOW: $LIVE_WORKFLOW exists but .ci/breakpoint/workflow/breakpoint.yml does not, so the live workflow is unfrozen"
    elif ! cmp -s "$LIVE_WORKFLOW" "$BP_ROOT/workflow/breakpoint.yml"; then
        add_failure "WORKFLOW: .github/workflows/breakpoint.yml differs from .ci/breakpoint/workflow/breakpoint.yml (only the .github copy is scanned by the workflow gates)"
    else
        log_debug "live workflow matches the frozen template"
    fi
else
    log_debug "no .github/workflows/breakpoint.yml here; live-workflow comparison skipped"
fi

# =============================================================================
# 5: VACUOUS (second half) -- nothing was actually compared
# =============================================================================
if [[ $COMPARED -eq 0 ]]; then
    add_failure "VACUOUS: the manifest lists ${MANIFEST_COUNT} file(s) but ZERO were compared, so this check proved nothing"
fi

# =============================================================================
# MODE: --verify-upstream (network half)
# =============================================================================
# FAIL SOFT, on purpose and by precedent: scripts/check-embed-asset-freshness.ts
# exits 0 on any network/HTTP failure because "a GitHub API blip must never be
# somebody's red build". The offline half above has already done the work that
# actually catches tampering; this half only answers "has upstream moved on",
# which is never urgent enough to justify a flaky gate.

if [[ "$MODE" == "verify-upstream" ]]; then
    require_cmd curl
    UPSTREAM_URL="https://raw.githubusercontent.com/${UPSTREAM_REPO}/main/.ci/breakpoint/MANIFEST.sha256"
    log_step "fetching upstream manifest: $UPSTREAM_URL"

    resp="$(curl -sS -w $'\n%{http_code}' --max-time 30 "$UPSTREAM_URL" 2>/dev/null || true)"
    code=""
    body=""
    if [[ -n "$resp" ]]; then
        code="${resp##*$'\n'}"
        body="${resp%$'\n'*}"
    fi

    if [[ "$code" != "200" ]] || [[ -z "$body" ]]; then
        bp_gha_warning "could not fetch the upstream breakpoint manifest (HTTP '${code:-none}'); upstream comparison skipped. The offline integrity check above still ran."
        report_and_exit "$COMPARED"
    fi

    declare -A UPSTREAM_HASH=()
    upstream_count=0
    while IFS= read -r line || [[ -n "$line" ]]; do
        case "$line" in
            '#'*) continue ;;
            '') continue ;;
        esac
        u_hash="${line%% *}"
        u_path="${line#* }"
        u_path="${u_path#"${u_path%%[![:space:]]*}"}"
        [[ "$u_hash" =~ ^[0-9a-f]{64}$ ]] || continue
        [[ -n "$u_path" ]] || continue
        UPSTREAM_HASH["$u_path"]="$u_hash"
        upstream_count=$((upstream_count + 1))
    done <<<"$body"

    # An upstream manifest we fetched but could not parse is a fetch that told us
    # nothing, so it takes the same soft exit as a transport failure rather than
    # reddening the build on a formatting change we have not seen yet.
    if [[ $upstream_count -eq 0 ]]; then
        bp_gha_warning "the upstream breakpoint manifest parsed to ZERO entries; upstream comparison skipped (the offline integrity check above still ran)."
        report_and_exit "$COMPARED"
    fi

    upstream_diff=0
    for u_path in "${!UPSTREAM_HASH[@]}"; do
        u_hash="${UPSTREAM_HASH[$u_path]}"
        local_hash="${MANIFEST_HASH[$u_path]:-}"
        if [[ -z "$local_hash" ]]; then
            add_failure "UPSTREAM-ONLY: $u_path exists in ${UPSTREAM_REPO}@main but not in this copy's manifest"
            upstream_diff=$((upstream_diff + 1))
        elif [[ "$local_hash" != "$u_hash" ]]; then
            if [[ -n "${ACCEPTED[$u_path]:-}" ]]; then
                log_warn "accepted (differs from upstream): $u_path"
                ACCEPT_FIRED["$u_path"]=1
            else
                add_failure "UPSTREAM-DRIFT: $u_path differs from ${UPSTREAM_REPO}@main"
                upstream_diff=$((upstream_diff + 1))
            fi
        fi
    done

    # The other direction. A local manifest entry upstream does not have means
    # somebody ran --write here (which is refused downstream) or upstream deleted
    # the file; either way the copy is no longer a copy.
    for path in "${!MANIFEST_HASH[@]}"; do
        if [[ -z "${UPSTREAM_HASH[$path]:-}" ]]; then
            if [[ -n "${ACCEPTED[$path]:-}" ]]; then
                log_warn "accepted (absent upstream): $path"
                ACCEPT_FIRED["$path"]=1
                continue
            fi
            add_failure "LOCAL-ONLY: $path is in this copy's manifest but not in ${UPSTREAM_REPO}@main"
            upstream_diff=$((upstream_diff + 1))
        fi
    done

    log_info "compared ${MANIFEST_COUNT} local against ${upstream_count} upstream entries (${upstream_diff} divergence(s))"
fi

report_and_exit "$COMPARED"
