#!/bin/bash
# Re-vendor .ci/breakpoint/ from the canonical repository.
#
# INVOKED BY A HUMAN, NEVER BY CI. This is the deliberate counterpart to
# check-breakpoint-drift.sh: the gate tells you a copy has diverged, and this is
# the one-command way to make it canonical again. It is not wired into any
# workflow on purpose -- an automatic re-vendor would overwrite a local edit
# nobody had reviewed, silently, on a schedule, and the whole point of the gate
# is that such an edit gets NOTICED.
#
# Usage:
#   sync-breakpoint.sh [--from <owner/repo>@<ref>] [--dry-run]
#
# Default source is BREAKPOINT_UPSTREAM_REPO@main from breakpoint.conf.
# Exit: 0 synced (or nothing to do), 1 failure, 2 bad usage.
#
# WHAT IT PRESERVES, AND WHY
#   breakpoint.conf          -- THE per-repo edit point. Overwriting it would
#                               replace this repo's zone, labels and recipients
#                               with console's, which is the one change nobody
#                               ever wants from a sync.
#   .breakpoint-drift-accept -- this repo's justified divergences. Clobbering it
#                               would silently un-accept them.
#   README.md                -- downstream appends local notes.
# Everything else in the frozen set is replaced wholesale.
#
# WHY PER-FILE RAW FETCHES AND NOT A TARBALL
# The upstream MANIFEST.sha256 has to be fetched anyway (it defines the frozen
# set), and once it is in hand every downloaded file can be verified against its
# recorded hash BEFORE it is written. A codeload tarball would arrive
# unverifiable and would drag the whole repository across the wire for a folder.
#
# PATHS FROM THE NETWORK BECOME FILESYSTEM WRITES, so every manifest path is
# validated against a strict allowlist shape below before it is used. A manifest
# containing `../../.github/workflows/release.yml` must not be able to write
# there, and it cannot: nothing outside .ci/breakpoint/ is ever opened.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/breakpoint-common.sh
source "$SCRIPT_DIR/../lib/breakpoint-common.sh"

bp_load_conf "$SCRIPT_DIR"
parse_args "$@"

BP_ROOT="$(bp_root "$SCRIPT_DIR")"
DRY_RUN="${ARG_DRY_RUN:-false}"
FROM="${ARG_FROM:-${BREAKPOINT_UPSTREAM_REPO:-rediacc/console}@main}"

require_cmd curl
require_cmd sha256sum

# parse_args swallows a value that begins with `--`, so `--from --dry-run` would
# set ARG_FROM to the string "true". Catch that here rather than turning it into
# a nonsensical URL.
if [[ "$FROM" == "true" ]]; then
    log_error "--from needs a value, e.g. --from rediacc/console@main"
    exit 2
fi

case "$FROM" in
    *@*)
        SRC_REPO="${FROM%@*}"
        SRC_REF="${FROM##*@}"
        ;;
    *)
        SRC_REPO="$FROM"
        SRC_REF="main"
        ;;
esac

if [[ ! "$SRC_REPO" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]] || [[ -z "$SRC_REF" ]]; then
    log_error "--from must look like <owner>/<repo>[@<ref>], got '$FROM'"
    exit 2
fi

RAW_BASE="https://raw.githubusercontent.com/${SRC_REPO}/${SRC_REF}/.ci/breakpoint"

# =============================================================================
# HELPERS
# =============================================================================

STAGING="$(mktemp -d "$(get_temp_dir)/breakpoint-sync.XXXXXX")"
cleanup() { rm -rf "$STAGING"; }
trap cleanup EXIT

# bp_fetch <remote-relative-path> <local-destination>
# Returns 0 on HTTP 200, 1 otherwise (naming the status).
bp_fetch() {
    local rel="$1" dest="$2" code
    mkdir -p "$(dirname "$dest")"
    code="$(curl -sS -o "$dest" -w '%{http_code}' --max-time 60 "${RAW_BASE}/${rel}" 2>/dev/null || true)"
    if [[ "$code" != "200" ]]; then
        log_error "fetch failed for ${RAW_BASE}/${rel} (HTTP ${code:-none})"
        return 1
    fi
    return 0
}

# A manifest path is only usable if it is one of the shapes the frozen set can
# contain. Anything else -- absolute, dot-dot, a nested directory, a name with a
# space -- is refused rather than sanitised, because a manifest that contains one
# is not an upstream manifest we understand.
bp_path_ok() {
    local p="$1"
    case "$p" in
        */../* | ../* | */.. | /*) return 1 ;;
    esac
    [[ "$p" =~ ^(scripts|lib|workflow)/[A-Za-z0-9._-]+$ ]] && return 0
    [[ "$p" == "versions.sh" ]] && return 0
    return 1
}

# Every write and delete goes through this. BP_ROOT is resolved with `cd`, so a
# target that escapes the folder cannot survive the prefix test.
bp_assert_inside() {
    local target="$1" dir resolved
    dir="$(cd "$(dirname "$BP_ROOT/$target")" 2>/dev/null && pwd || true)"
    if [[ -z "$dir" ]]; then
        return 0 # directory does not exist yet; the path shape check already ran
    fi
    resolved="${dir}/$(basename "$target")"
    case "$resolved" in
        "$BP_ROOT"/*) return 0 ;;
        *)
            log_error "refusing to touch '$resolved': outside $BP_ROOT"
            return 1
            ;;
    esac
}

# =============================================================================
# FETCH THE UPSTREAM MANIFEST
# =============================================================================

log_step "syncing .ci/breakpoint/ from ${SRC_REPO}@${SRC_REF}"
if [[ "$DRY_RUN" == "true" ]]; then
    log_warn "DRY-RUN: nothing will be written; every decision is still evaluated and printed"
fi

if ! bp_fetch "MANIFEST.sha256" "$STAGING/MANIFEST.sha256"; then
    log_error "cannot read the upstream manifest, so there is nothing to sync from"
    echo "  Action: check that ${SRC_REPO}@${SRC_REF} really carries .ci/breakpoint/MANIFEST.sha256," >&2
    echo "          and that the ref exists (try --from ${SRC_REPO}@main)." >&2
    exit 1
fi

declare -A WANT_HASH=()
WANT_ORDER=()
while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
        '#'*) continue ;;
        '') continue ;;
    esac
    hash="${line%% *}"
    path="${line#* }"
    path="${path#"${path%%[![:space:]]*}"}"
    if [[ ! "$hash" =~ ^[0-9a-f]{64}$ ]] || [[ -z "$path" ]]; then
        log_error "upstream manifest line is malformed: $line"
        exit 1
    fi
    if ! bp_path_ok "$path"; then
        log_error "upstream manifest names a path this script will not write: '$path'"
        echo "  Rejected because: manifest paths become filesystem writes. Only scripts/, lib/, workflow/ and" >&2
        echo "                    versions.sh are ever replaced, and never through '..' or an absolute path." >&2
        exit 1
    fi
    WANT_HASH["$path"]="$hash"
    WANT_ORDER+=("$path")
done <"$STAGING/MANIFEST.sha256"

if [[ ${#WANT_ORDER[@]} -eq 0 ]]; then
    log_error "the upstream manifest lists ZERO files; refusing to sync from it"
    echo "  Rejected because: applying an empty manifest would delete the whole frozen set and report success." >&2
    exit 1
fi

log_info "upstream manifest lists ${#WANT_ORDER[@]} file(s)"

# =============================================================================
# DOWNLOAD AND VERIFY, BEFORE ANYTHING LOCAL IS TOUCHED
# =============================================================================
# Staged in full first so a fetch that dies halfway cannot leave the folder as a
# mix of two versions -- which would be a state no manifest describes and no
# gate can explain.

ADDED=0
UPDATED=0
UNCHANGED=0
REMOVED=0

for path in "${WANT_ORDER[@]}"; do
    if ! bp_fetch "$path" "$STAGING/$path"; then
        log_error "aborting: nothing has been written locally"
        exit 1
    fi
    got="$(sha256sum "$STAGING/$path" | cut -d' ' -f1)"
    if [[ "$got" != "${WANT_HASH[$path]}" ]]; then
        log_error "downloaded $path does not match the upstream manifest"
        echo "  expected ${WANT_HASH[$path]}" >&2
        echo "  actual   $got" >&2
        echo "  Rejected because: either the fetch was corrupted or upstream's manifest is stale. Writing an" >&2
        echo "                    unverified file would vendor something nobody hashed." >&2
        log_error "aborting: nothing has been written locally"
        exit 1
    fi
done
log_info "downloaded and hash-verified ${#WANT_ORDER[@]} file(s)"

# =============================================================================
# APPLY
# =============================================================================

for path in "${WANT_ORDER[@]}"; do
    bp_assert_inside "$path" || exit 1

    if [[ -f "$BP_ROOT/$path" ]]; then
        local_hash="$(sha256sum "$BP_ROOT/$path" | cut -d' ' -f1)"
        if [[ "$local_hash" == "${WANT_HASH[$path]}" ]]; then
            UNCHANGED=$((UNCHANGED + 1))
            continue
        fi
        if [[ "$DRY_RUN" == "true" ]]; then
            log_warn "  [DRY-RUN] would replace $path"
        else
            # cp onto an existing file keeps the DESTINATION's mode, so an
            # executable script stays executable without this script having to
            # guess which files are meant to be +x.
            cp "$STAGING/$path" "$BP_ROOT/$path"
            log_info "  replaced $path"
        fi
        UPDATED=$((UPDATED + 1))
    else
        if [[ "$DRY_RUN" == "true" ]]; then
            log_warn "  [DRY-RUN] would add $path"
        else
            mkdir -p "$(dirname "$BP_ROOT/$path")"
            cp "$STAGING/$path" "$BP_ROOT/$path"
            # New files have no destination mode to inherit. Only scripts/ is
            # executed directly; lib/ is sourced and workflow/ is a template.
            case "$path" in
                scripts/*) chmod +x "$BP_ROOT/$path" ;;
                *) chmod 644 "$BP_ROOT/$path" ;;
            esac
            log_info "  added $path"
        fi
        ADDED=$((ADDED + 1))
    fi
done

# Local frozen-set files upstream no longer has. Without this step they linger
# forever as UNTRACKED findings in the drift gate, and the operator's only way
# out is to accept a file that upstream deleted on purpose.
while IFS= read -r path; do
    [[ -z "$path" ]] && continue
    if [[ -n "${WANT_HASH[$path]:-}" ]]; then
        continue
    fi
    bp_assert_inside "$path" || exit 1
    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "  [DRY-RUN] would remove $path (upstream no longer carries it)"
    else
        rm -f "$BP_ROOT/$path"
        log_info "  removed $path (upstream no longer carries it)"
    fi
    REMOVED=$((REMOVED + 1))
done < <(
    {
        find "$BP_ROOT/scripts" -maxdepth 1 -type f -name '*.sh' 2>/dev/null || true
        find "$BP_ROOT/lib" -maxdepth 1 -type f -name '*.sh' 2>/dev/null || true
        find "$BP_ROOT/workflow" -maxdepth 1 -type f -name '*.yml' 2>/dev/null || true
        if [[ -f "$BP_ROOT/versions.sh" ]]; then
            echo "$BP_ROOT/versions.sh"
        fi
    } | sed "s|^${BP_ROOT}/||" | LC_ALL=C sort
)

# The manifest itself is part of the vendored copy: without it the drift gate has
# nothing to compare against. It is written LAST, so an abort above leaves the old
# manifest in place and the gate stays meaningful.
if [[ "$DRY_RUN" == "true" ]]; then
    log_warn "  [DRY-RUN] would update MANIFEST.sha256"
else
    cp "$STAGING/MANIFEST.sha256" "$BP_ROOT/MANIFEST.sha256"
    chmod 644 "$BP_ROOT/MANIFEST.sha256"
fi

log_info "preserved: breakpoint.conf, .breakpoint-drift-accept, README.md"
log_info "summary: ${ADDED} added, ${UPDATED} replaced, ${UNCHANGED} unchanged, ${REMOVED} removed"

# =============================================================================
# PROVE IT
# =============================================================================
# A sync that reports success without re-running the gate is just a claim. The
# gate is the only thing that can say the folder now matches the manifest it
# arrived with.

if [[ "$DRY_RUN" == "true" ]]; then
    log_warn "DRY-RUN: skipping the post-sync verification (nothing changed)"
    exit 0
fi

log_step "verifying the synced copy..."
if "$SCRIPT_DIR/check-breakpoint-drift.sh" --verify; then
    log_info "sync complete and verified against ${SRC_REPO}@${SRC_REF}"
    exit 0
fi

log_error "sync finished but the drift gate still reports findings (see above)"
echo "  Note: findings naming .github/workflows/breakpoint.yml are expected here -- syncing the template" >&2
echo "        does NOT install it. Copy .ci/breakpoint/workflow/breakpoint.yml to" >&2
echo "        .github/workflows/breakpoint.yml yourself, so adding a workflow to a repo stays a visible act." >&2
exit 1
