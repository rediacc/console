#!/bin/bash
# Check that all machine-level CLI operations have audit logging coverage.
#
# Verifies three invariants:
#   1. localExecutorService.execute() contains auditService.recordOperation()
#      (covers all SSH-based operations automatically)
#   2. Edge-case files (SFTP sync, direct SSH term) contain auditService.recordOperation()
#   3. No new direct SSH/SFTP execution paths exist without audit coverage
#
# This prevents adding new machine-level operations without audit logging.
#
# Usage:
#   .ci/scripts/quality/check-audit-coverage.sh
#
# Exit codes:
#   0 - All operations have audit logging coverage
#   1 - One or more gaps detected

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"

CLI_SRC="$REPO_ROOT/packages/cli/src"
LOCAL_EXECUTOR="$CLI_SRC/services/local-executor.ts"
AUDIT_SERVICE="$CLI_SRC/services/audit.ts"

ERRORS=0

# ── Phase 1: Verify audit service exists ──────────────────────────────
log_step "Checking audit service exists..."

if [[ ! -f "$AUDIT_SERVICE" ]]; then
    log_error "Audit service not found: $AUDIT_SERVICE"
    ERRORS=$((ERRORS + 1))
else
    log_info "Audit service exists"
fi

# ── Phase 2: Verify localExecutorService hook ─────────────────────────
log_step "Checking localExecutorService.execute() audit hook..."

if [[ ! -f "$LOCAL_EXECUTOR" ]]; then
    log_error "Local executor not found: $LOCAL_EXECUTOR"
    ERRORS=$((ERRORS + 1))
elif ! grep -q 'auditService\.recordOperation' "$LOCAL_EXECUTOR"; then
    log_error "localExecutorService.execute() does not contain auditService.recordOperation()"
    log_error "All SSH-based operations must be audit-logged via the executor hook."
    log_error "File: $LOCAL_EXECUTOR"
    ERRORS=$((ERRORS + 1))
else
    log_info "localExecutorService.execute() has audit hook"
fi

# ── Phase 3: Verify edge-case files ──────────────────────────────────
log_step "Checking edge-case files for audit calls..."

# These files execute machine operations outside localExecutorService
# (SFTP sync and direct SSH terminal) and need explicit audit calls.
EDGE_CASE_FILES=(
    "packages/cli/src/commands/repo-sync.ts"
    "packages/cli/src/commands/term.ts"
)

MISSING_EDGE=()
for file in "${EDGE_CASE_FILES[@]}"; do
    full_path="$REPO_ROOT/$file"
    if [[ ! -f "$full_path" ]]; then
        log_warn "Edge-case file not found (may have been moved): $file"
        continue
    fi
    if ! grep -q 'auditService\.recordOperation' "$full_path"; then
        MISSING_EDGE+=("$file")
    fi
done

if [[ ${#MISSING_EDGE[@]} -gt 0 ]]; then
    log_error "Edge-case files missing auditService.recordOperation():"
    for file in "${MISSING_EDGE[@]}"; do
        log_error "  - $file"
    done
    log_error ""
    log_error "These files execute machine operations via SFTP/SSH (not localExecutorService)"
    log_error "and require explicit audit calls."
    ERRORS=$((ERRORS + 1))
else
    log_info "All ${#EDGE_CASE_FILES[@]} edge-case files have audit calls"
fi

# ── Phase 4: Detect unaudited execution paths ────────────────────────
log_step "Scanning for unaudited execution paths..."

# Known files that legitimately import SFTPClient for machine operations.
# If a new file imports SFTPClient, it may need audit logging.
KNOWN_SFTP_COMMAND_FILES=(
    "packages/cli/src/commands/repo-sync.ts"
    "packages/cli/src/commands/storage.ts"
    "packages/cli/src/commands/config-setup.ts"
)

# Find CLI command files that import SFTPClient (potential SFTP-based operations)
SFTP_IMPORTERS=()
while IFS= read -r file; do
    # Convert to relative path
    rel="${file#"$REPO_ROOT"/}"
    # Skip known files
    known=false
    for kf in "${KNOWN_SFTP_COMMAND_FILES[@]}"; do
        if [[ "$rel" == "$kf" ]]; then
            known=true
            break
        fi
    done
    # Skip non-command files (services, utils)
    if [[ "$rel" != *"/commands/"* ]]; then
        continue
    fi
    if ! $known; then
        SFTP_IMPORTERS+=("$rel")
    fi
done < <(grep -rl "SFTPClient\|sftpUploadDirectory\|sftpDownloadDirectory" "$CLI_SRC/commands/" 2>/dev/null || true)

if [[ ${#SFTP_IMPORTERS[@]} -gt 0 ]]; then
    log_warn "New command files with SFTP imports detected (may need audit logging):"
    for file in "${SFTP_IMPORTERS[@]}"; do
        log_warn "  - $file"
    done
    log_warn "If these files perform machine-level operations, add auditService.recordOperation()"
    log_warn "and add them to the EDGE_CASE_FILES list in this script."
    # This is a warning, not an error — new SFTP usage might be internal/utility
fi

# ── Phase 5: Event-type union completeness ───────────────────────────
log_step "Checking event-type union covers every functionName emitted..."

EVENT_SCHEMA="$REPO_ROOT/packages/shared/src/audit/event-schema.ts"
if [[ ! -f "$EVENT_SCHEMA" ]]; then
    log_error "Shared audit event schema missing: $EVENT_SCHEMA"
    ERRORS=$((ERRORS + 1))
else
    # Extract literal event-type strings from the schema file. The schema
    # declares them as 'cli.X.Y' inside ALL_EVENT_TYPES via the per-group
    # const arrays — grep is sufficient because the file is purely declarative.
    declare -A UNION_TYPES=()
    while IFS= read -r line; do
        # Strip quotes and trailing comma
        type="${line//\'/}"
        type="${type//\"/}"
        type="${type//,/}"
        type="${type// /}"
        if [[ -n "$type" ]]; then
            UNION_TYPES["$type"]=1
        fi
    done < <(grep -oE "'cli\.[a-z._]+[a-z_]'" "$EVENT_SCHEMA" | sort -u)

    if [[ ${#UNION_TYPES[@]} -eq 0 ]]; then
        log_error "Could not parse any event types from $EVENT_SCHEMA"
        log_error "Expected literal strings like 'cli.repo.up'. Has the schema format changed?"
        ERRORS=$((ERRORS + 1))
    fi

    # Find every functionName: 'X' literal in CLI source (excluding tests
    # and the audit service itself, where mappings are *defined*).
    MISSING_TYPES=()
    while IFS= read -r fn; do
        # Map fn name to event type using the same rules as
        # functionNameToEventType in event-schema.ts. Keep this in sync.
        case "$fn" in
            repository_*) type="cli.repo.${fn#repository_}" ;;
            backup_*)     type="cli.backup.${fn#backup_}" ;;
            datastore_*)  type="cli.datastore.${fn#datastore_}" ;;
            machine_*)    type="cli.machine.${fn#machine_}" ;;
            sync_upload)  type="cli.sync.upload" ;;
            sync_download) type="cli.sync.download" ;;
            term_connect) type="cli.term.session" ;;
            *)            type="cli.$fn" ;;
        esac
        if [[ -z "${UNION_TYPES[$type]:-}" ]]; then
            MISSING_TYPES+=("$fn -> $type")
        fi
    done < <(grep -rhE "functionName: '[a-z_]+'" "$CLI_SRC/commands/" "$CLI_SRC/services/" \
                --include='*.ts' --exclude-dir=__tests__ 2>/dev/null \
             | grep -v 'audit.ts' \
             | grep -oE "functionName: '[a-z_]+'" \
             | sed -E "s/functionName: '([a-z_]+)'/\\1/" \
             | sort -u)

    if [[ ${#MISSING_TYPES[@]} -gt 0 ]]; then
        log_error "These functionName values map to event types not in the schema union:"
        for entry in "${MISSING_TYPES[@]}"; do
            log_error "  - $entry"
        done
        log_error ""
        log_error "Add the missing literals to ALL_EVENT_TYPES in $EVENT_SCHEMA,"
        log_error "or remove the recordOperation() call if the event is not auditable."
        ERRORS=$((ERRORS + 1))
    else
        log_info "Event-type union covers all ${#UNION_TYPES[@]} declared types"
    fi
fi

# ── Results ───────────────────────────────────────────────────────────
if [[ $ERRORS -gt 0 ]]; then
    log_error ""
    log_error "Audit coverage check failed with $ERRORS error(s)"
    log_error ""
    log_error "To fix:"
    log_error "  1. Ensure auditService.recordOperation() is called in local-executor.ts execute()"
    log_error "  2. Ensure edge-case files (sync, term) have explicit audit calls"
    log_error "  3. See packages/cli/src/services/audit.ts for the audit service API"
    exit 1
fi

log_info "Audit logging coverage check passed"
exit 0
