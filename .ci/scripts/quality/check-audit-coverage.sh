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
