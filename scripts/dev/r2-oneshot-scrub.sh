#!/bin/bash
# One-shot R2 scrub to clear accumulated orphans and PR-pollution of
# versioned release paths. Safe to re-run; idempotent.
#
# Targets:
#   Stage 1 - Hard-delete entire prefixes:
#     staging/            (pre-channel-model legacy)
#     packages/           (pre-channel-model legacy)
#     cli/latest/         (pre-manifest.json legacy; 2.5 GB)
#     {format}/dryrun-*/  (workflow_dispatch / nightly orphans, all formats)
#     cli/v0.7.2/         (pre-tracker; no git tag)
#     cli/v0.7.7/         (same)
#     desktop/v0.7.5/     (same)
#     desktop/v0.8.1/     (same)
#     cli/v1.0.3/         (PR #451 pollution; never released)
#     desktop/v1.0.3/     (same)
#
#   Stage 2 - Selective scrub under desktop/v1.0.{1,2}/:
#     Delete rediacc-desktop-0.0.0-dev-* (PR CI artifacts).
#     Keep rediacc-desktop-1.0.${N}-*    (authoritative release).
#     Skip v1.0.0 entirely; its "0.0.0-dev" files ARE the authoritative release.
#
#   Stage 3 - Delete polluted desktop/v1.0.{1,2}/latest-*.yml:
#     electron-updater reads from desktop/stable/latest-*.yml (channel path),
#     not the versioned path. The versioned-path YML was always a byproduct;
#     clients never depended on it.
#
# Usage:
#   scripts/dev/r2-oneshot-scrub.sh                    # dry-run default
#   scripts/dev/r2-oneshot-scrub.sh --execute          # actually delete
#   scripts/dev/r2-oneshot-scrub.sh --execute --yes    # skip confirmation prompts
#
# Required env: R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT
#   (source from private/account/.env for local runs).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=../../.ci/scripts/lib/common.sh
source "$REPO_ROOT/.ci/scripts/lib/common.sh"

BUCKET="rediacc-releases"
DRY_RUN=true
ASSUME_YES=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --execute)
            DRY_RUN=false
            shift
            ;;
        --yes | -y)
            ASSUME_YES=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h | --help)
            sed -n '/^# /,/^$/p' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

for var in R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY R2_ENDPOINT; do
    if [[ -z "${!var:-}" ]]; then
        log_error "Missing required env: $var"
        exit 1
    fi
done

export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export AWS_DEFAULT_REGION="auto"

# Helpers -----------------------------------------------------------------

# Pretty-print size + count under a prefix; returns 0 if prefix has content.
describe_prefix() {
    local prefix="$1"
    local out
    out="$(aws s3 ls "s3://${BUCKET}/${prefix}" --recursive --summarize --human-readable \
        --endpoint-url "$R2_ENDPOINT" 2>/dev/null | tail -3 || true)"
    if [[ -z "$out" ]]; then
        log_info "  (empty or missing: ${prefix})"
        return 1
    fi
    echo "$out" | sed 's/^/  /'
    return 0
}

confirm() {
    local msg="$1"
    $ASSUME_YES && return 0
    read -r -p "  ${msg} [y/N] " reply
    [[ "$reply" == "y" || "$reply" == "Y" ]]
}

rm_prefix() {
    local prefix="$1" label="$2"
    log_step "About to delete s3://${BUCKET}/${prefix} (${label})"
    describe_prefix "$prefix" || {
        log_info "  skipping (nothing to delete)"
        return 0
    }
    if $DRY_RUN; then
        log_warn "  [DRY-RUN] Would delete s3://${BUCKET}/${prefix}"
        return 0
    fi
    if ! confirm "Proceed with deletion?"; then
        log_info "  skipped by user"
        return 0
    fi
    aws s3 rm "s3://${BUCKET}/${prefix}" --recursive \
        --endpoint-url "$R2_ENDPOINT" --quiet
    log_info "  Deleted."
}

# Stage 0 - Manifest backup ----------------------------------------------

backup_manifests() {
    local out
    out="/tmp/r2-manifest-backup-$(date -u +%Y%m%d-%H%M%S).tar.gz"
    log_step "Backing up all manifests (*.json / *.yml) before scrub -> $out"
    local tmp
    tmp="$(mktemp -d)"
    for prefix in cli/ desktop/ npm/ apt/ rpm/ apk/ archlinux/; do
        aws s3 sync "s3://${BUCKET}/${prefix}" "${tmp}/${prefix}" \
            --endpoint-url "$R2_ENDPOINT" \
            --exclude '*' --include '*.json' --include '*.yml' \
            --quiet 2>/dev/null || true
    done
    tar -czf "$out" -C "$tmp" . 2>/dev/null || true
    rm -rf "$tmp"
    log_info "  Backup: $out"
}

# Stage 1 - Hard-delete whole prefixes -----------------------------------

stage1() {
    log_step "Stage 1: hard-delete whole orphan prefixes"

    # Legacy dead top-level prefixes
    rm_prefix "staging/" "legacy pre-channel-model"
    rm_prefix "packages/" "legacy pre-channel-model"
    rm_prefix "cli/latest/" "legacy pre-manifest.json path"

    # Dryrun orphans across every format dir
    for fmt in cli desktop npm apt rpm apk archlinux; do
        local out
        out="$(aws s3 ls "s3://${BUCKET}/${fmt}/" --endpoint-url "$R2_ENDPOINT" 2>/dev/null |
            awk '/^[[:space:]]*PRE[[:space:]]dryrun-/ {print $2}' || true)"
        while IFS= read -r sub; do
            [[ -z "$sub" ]] && continue
            rm_prefix "${fmt}/${sub}" "dryrun orphan"
        done <<<"$out"
    done

    # Ancient versioned prefixes (no tag, not in tracker)
    for p in cli/v0.7.2/ cli/v0.7.7/ desktop/v0.7.5/ desktop/v0.8.1/; do
        rm_prefix "$p" "ancient, past retention"
    done

    # PR #451 pollution (v1.0.3 never released)
    rm_prefix "cli/v1.0.3/" "PR #451 pollution"
    rm_prefix "desktop/v1.0.3/" "PR #451 pollution"

    # Top-level stray pointer files from the pre-channel-model era.
    # Consumers all read {cli,desktop}/{channel}/... today; top-level
    # manifest.json / latest.json / latest-*.yml have no reader.
    # cli/versions.json and desktop/versions.json are ALIVE (retention
    # tracker written by upload-to-r2.sh) -- do NOT delete.
    for f in cli/manifest.json cli/latest.json \
        desktop/latest-linux.yml desktop/latest-linux-arm64.yml \
        desktop/latest-mac.yml desktop/latest-win.yml; do
        if aws s3api head-object --bucket "$BUCKET" --key "$f" --endpoint-url "$R2_ENDPOINT" >/dev/null 2>&1; then
            if $DRY_RUN; then
                log_warn "  [DRY-RUN] Would delete s3://${BUCKET}/${f} (legacy top-level stray)"
            elif confirm "Delete legacy top-level s3://${BUCKET}/${f}?"; then
                aws s3 rm "s3://${BUCKET}/${f}" --endpoint-url "$R2_ENDPOINT" --quiet
                log_info "  Deleted s3://${BUCKET}/${f}"
            else
                log_info "  skipped: $f"
            fi
        fi
    done
}

# Stage 2 - Selective scrub of 0.0.0-dev-named files under v1.0.{1,2}/ ----

stage2() {
    log_step "Stage 2: selective scrub of 0.0.0-dev-* under desktop/v1.0.{1,2}/"
    log_info "  Skipping desktop/v1.0.0/ -- its 0.0.0-dev files ARE the authoritative release."
    for n in 1 2; do
        local prefix="desktop/v1.0.${n}/"
        log_step "  Processing $prefix"
        local files
        files="$(aws s3 ls "s3://${BUCKET}/${prefix}" --endpoint-url "$R2_ENDPOINT" 2>/dev/null |
            awk '{print $NF}' | grep -E '^rediacc-desktop-0\.0\.0-dev-' || true)"
        if [[ -z "$files" ]]; then
            log_info "    no 0.0.0-dev-* files under $prefix"
            continue
        fi
        echo "$files" | sed 's/^/    would delete: /'
        if $DRY_RUN; then
            log_warn "    [DRY-RUN] Would delete $(echo "$files" | wc -l) file(s)"
            continue
        fi
        if ! confirm "Delete $(echo "$files" | wc -l) 0.0.0-dev-* file(s) from ${prefix}?"; then
            log_info "    skipped by user"
            continue
        fi
        while IFS= read -r f; do
            [[ -z "$f" ]] && continue
            aws s3 rm "s3://${BUCKET}/${prefix}${f}" --endpoint-url "$R2_ENDPOINT" --quiet
            log_info "    deleted ${prefix}${f}"
        done <<<"$files"
    done
}

# Stage 2b - Abort abandoned multipart uploads ---------------------------

stage2b() {
    log_step "Stage 2b: abort abandoned multipart uploads (any age)"
    local uploads
    uploads="$(aws s3api list-multipart-uploads --bucket "$BUCKET" \
        --endpoint-url "$R2_ENDPOINT" \
        --query 'Uploads[].{Key:Key,UploadId:UploadId,Initiated:Initiated}' \
        --output json 2>/dev/null || echo "[]")"
    local count
    count="$(echo "$uploads" | jq 'length')"
    if [[ "$count" -eq 0 ]]; then
        log_info "  No ongoing multipart uploads"
        return 0
    fi
    log_info "  Found $count ongoing multipart upload(s)"
    echo "$uploads" | jq -r '.[] | "    \(.Initiated)  \(.Key)"' | head -20
    if $DRY_RUN; then
        log_warn "  [DRY-RUN] Would abort $count upload(s)"
        return 0
    fi
    if ! confirm "Abort all $count ongoing multipart uploads?"; then
        log_info "  skipped by user"
        return 0
    fi
    local aborted=0
    while IFS=$'\t' read -r key upload_id; do
        [[ -z "$key" ]] && continue
        aws s3api abort-multipart-upload \
            --bucket "$BUCKET" --key "$key" --upload-id "$upload_id" \
            --endpoint-url "$R2_ENDPOINT" 2>/dev/null || continue
        aborted=$((aborted + 1))
    done < <(echo "$uploads" | jq -r '.[] | "\(.Key)\t\(.UploadId)"')
    log_info "  Aborted $aborted of $count"
}

# Stage 2c - Reap pr-N/ channel artifacts older than 3 days or closed -----

stage2c() {
    # Locally relax set -e; the many aws/gh pipes here have annoying SIGPIPE
    # edge cases that can silently kill the whole script otherwise.
    set +e
    log_step "Stage 2c: reap pr-N/ older than 3d or closed"
    local pr_age_max=$((3 * 86400))
    local now_epoch
    now_epoch="$(date -u +%s)"
    local deleted=0
    for fmt in cli desktop npm apt rpm apk archlinux; do
        local listing
        listing="$(aws s3 ls "s3://${BUCKET}/${fmt}/" --endpoint-url "$R2_ENDPOINT" 2>/dev/null |
            awk '/^[[:space:]]*PRE[[:space:]]pr-[0-9]+\// {print $2}')"
        [[ -z "$listing" ]] && continue
        while IFS= read -r sub; do
            [[ -z "$sub" ]] && continue
            local pr_num="${sub#pr-}"
            pr_num="${pr_num%/}"
            local prefix="${fmt}/${sub}"
            local last
            last="$(aws s3 ls "s3://${BUCKET}/${prefix}" --recursive --endpoint-url "$R2_ENDPOINT" 2>/dev/null |
                awk 'NR==1 {print $1"T"$2"Z"; exit}')"
            [[ -z "$last" ]] && continue
            local last_epoch
            last_epoch="$(date -u -d "$last" +%s 2>/dev/null || echo 0)"
            [[ "$last_epoch" -eq 0 ]] && continue
            local age=$((now_epoch - last_epoch))
            local reason=""
            if ((age > pr_age_max)); then
                reason="stale $((age / 86400))d"
            else
                local state
                state="$(gh pr view "$pr_num" --repo rediacc/console --json state --jq '.state' 2>/dev/null)"
                [[ -z "$state" ]] && state="UNKNOWN"
                if [[ "$state" != "OPEN" ]]; then
                    reason="PR #${pr_num} ${state}"
                fi
            fi
            if [[ -n "$reason" ]]; then
                log_info "  reaping $prefix ($reason)"
                aws s3 rm "s3://${BUCKET}/${prefix}" --recursive --endpoint-url "$R2_ENDPOINT" --quiet 2>/dev/null
                deleted=$((deleted + 1))
            fi
        done <<<"$listing"
    done
    log_info "  processed; reaped $deleted prefix(es)"
    set -e
}

# Stage 2d - Package-manager channel retention (keep 7v or 10d) ----------

stage2d() {
    set +e
    log_step "Stage 2d: channel artifact retention (keep 7v or 10d; zap 0.0.0-dev)"
    # Patterns:
    #   apt/<ch>/rediacc-cli_<ver>_<arch>.deb
    #   rpm/<ch>/rediacc-cli-<ver>.<arch>.rpm
    #   apk/<ch>/rediacc-cli-<ver>.apk
    #   archlinux/<ch>/rediacc-cli-<ver>-<arch>.pkg.tar.zst
    #   npm/<ch>/rediacc-cli-<ver>.tgz
    #   desktop/<ch>/rediacc-desktop-<ver>-<platform>.<ext>(+.blockmap)
    # Metadata (Packages.gz, Release*, APKINDEX, repodata/, *.db.tar.gz,
    # latest-*.yml, manifest.json, gpg.key, rediacc-cli-latest.tgz) stays.
    local keep_versions=7
    local keep_days=10
    local keep_age=$((keep_days * 86400))
    local now_epoch
    now_epoch="$(date -u +%s)"
    local deleted=0
    for fmt in apt rpm apk archlinux npm desktop; do
        for channel in stable edge; do
            local root="${fmt}/${channel}/"
            log_step "  $root"
            local listing
            listing="$(aws s3 ls "s3://${BUCKET}/${root}" --recursive --endpoint-url "$R2_ENDPOINT" 2>/dev/null |
                awk '{
                    n = split($4, p, "/"); fname = p[n];
                    if (fname !~ /^rediacc-(cli|desktop)[-_]/) next
                    rest = fname; sub(/^rediacc-(cli|desktop)[-_]/, "", rest);
                    if (match(rest, /^[0-9]+\.[0-9]+\.[0-9]+/)) {
                        semver = substr(rest, 1, RLENGTH);
                        after = substr(rest, RLENGTH + 1);
                        is_dev = (semver == "0.0.0" && after ~ /^-dev/) ? 1 : 0;
                        print $1"T"$2"Z""|"semver"|"is_dev"|"$4
                    }
                }' | sort -t'|' -k2,2 -V -r || true)"
            if [[ -z "$listing" ]]; then
                log_info "    empty or no artifact files"
                continue
            fi
            local idx=0
            while IFS='|' read -r ts semver is_dev key; do
                [[ -z "$key" ]] && continue
                local ts_epoch
                ts_epoch="$(date -u -d "$ts" +%s 2>/dev/null || echo 0)"
                local age=$((now_epoch - ts_epoch))
                if [[ "$is_dev" != "1" ]]; then
                    if ((idx < keep_versions)) || ((age < keep_age)); then
                        log_info "    keep v${semver} ($((age / 86400))d, rank $idx) -> ${key}"
                        idx=$((idx + 1))
                        continue
                    fi
                fi
                local tag="v${semver}, $((age / 86400))d"
                [[ "$is_dev" == "1" ]] && tag="0.0.0-dev pollution, $((age / 86400))d"
                if $DRY_RUN; then
                    log_warn "    [DRY-RUN] Would delete ${key} (${tag})"
                elif confirm "Delete ${key} (${tag})?"; then
                    aws s3 rm "s3://${BUCKET}/${key}" --endpoint-url "$R2_ENDPOINT" --quiet
                    log_info "    deleted ${key} (${tag})"
                fi
                deleted=$((deleted + 1))
                idx=$((idx + 1))
            done <<<"$listing"
        done
    done
    log_info "  reaped $deleted stale artifact(s)"
    set -e
}

# Stage 3 - Delete polluted latest-*.yml under v1.0.{1,2}/ ----------------

stage3() {
    log_step "Stage 3: delete polluted desktop/v1.0.{1,2}/latest-*.yml"
    log_info "  electron-updater reads desktop/stable/latest-*.yml; the versioned-path YML is a byproduct."
    for n in 1 2; do
        local prefix="desktop/v1.0.${n}/"
        for yml in latest-linux.yml latest-linux-arm64.yml latest-mac.yml latest-win.yml; do
            local key="${prefix}${yml}"
            if ! aws s3api head-object --bucket "$BUCKET" --key "$key" --endpoint-url "$R2_ENDPOINT" >/dev/null 2>&1; then
                continue
            fi
            if $DRY_RUN; then
                log_warn "  [DRY-RUN] Would delete s3://${BUCKET}/${key}"
                continue
            fi
            if ! confirm "Delete polluted manifest s3://${BUCKET}/${key}?"; then
                log_info "    skipped: $key"
                continue
            fi
            aws s3 rm "s3://${BUCKET}/${key}" --endpoint-url "$R2_ENDPOINT" --quiet
            log_info "  Deleted $key"
        done
    done
}

# Main -------------------------------------------------------------------

log_step "R2 one-shot scrub on s3://${BUCKET}/"
if $DRY_RUN; then
    log_warn "DRY-RUN mode: nothing will be deleted. Re-run with --execute to actually delete."
else
    log_warn "EXECUTE mode: deletions are permanent. No R2 version history."
    backup_manifests
fi
echo ""
stage1
echo ""
stage2
echo ""
stage2b
echo ""
stage2c
echo ""
stage2d
echo ""
stage3
echo ""
log_info "Done."
