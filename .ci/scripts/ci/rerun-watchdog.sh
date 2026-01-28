#!/bin/bash
# Rerun Watchdog - Auto-retry flaky jobs (max 3 attempts)
# Monitors specified jobs and triggers rerun on failure.
#
# Usage: rerun-watchdog.sh [options]
#   --run-id ID           Workflow run ID to monitor (default: $GITHUB_RUN_ID)
#   --attempt NUM         Current attempt number (default: $GITHUB_RUN_ATTEMPT)
#   --max-attempts NUM    Maximum retry attempts (default: 3)
#   --timeout MIN         Maximum runtime in minutes (default: 120)
#   --poll-interval SEC   Polling interval in seconds (default: 30)
#   --monitor PATTERN     Job name pattern to monitor (can be repeated)
#   --exclude PATTERN     Job name pattern to exclude (can be repeated)
#
# Environment:
#   GITHUB_REPOSITORY     Required: owner/repo
#   GITHUB_RUN_ID         Default run ID if --run-id not specified
#   GITHUB_RUN_ATTEMPT    Default attempt if --attempt not specified
#   GH_TOKEN              GitHub token for API access

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Defaults
RUN_ID="${GITHUB_RUN_ID:-}"
ATTEMPT="${GITHUB_RUN_ATTEMPT:-1}"
MAX_ATTEMPTS=3
TIMEOUT_MIN=120
POLL_INTERVAL=30
MONITOR_PATTERNS=()
EXCLUDE_PATTERNS=()

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --run-id) RUN_ID="$2"; shift 2 ;;
    --attempt) ATTEMPT="$2"; shift 2 ;;
    --max-attempts) MAX_ATTEMPTS="$2"; shift 2 ;;
    --timeout) TIMEOUT_MIN="$2"; shift 2 ;;
    --poll-interval) POLL_INTERVAL="$2"; shift 2 ;;
    --monitor) MONITOR_PATTERNS+=("$2"); shift 2 ;;
    --exclude) EXCLUDE_PATTERNS+=("$2"); shift 2 ;;
    *) log_error "Unknown option: $1"; exit 1 ;;
  esac
done

# Validation
if [[ -z "$RUN_ID" ]]; then
  log_error "Run ID required (--run-id or GITHUB_RUN_ID)"
  exit 1
fi

if [[ -z "${GITHUB_REPOSITORY:-}" ]]; then
  log_error "GITHUB_REPOSITORY environment variable required"
  exit 1
fi

# Check if we should even run
if [[ "$ATTEMPT" -ge "$MAX_ATTEMPTS" ]]; then
  log_info "Attempt $ATTEMPT >= max $MAX_ATTEMPTS - watchdog disabled"
  exit 0
fi

log_info "Rerun Watchdog started (attempt $ATTEMPT/$MAX_ATTEMPTS)"
log_info "Monitoring run: $RUN_ID"
log_info "Timeout: ${TIMEOUT_MIN}m, Poll interval: ${POLL_INTERVAL}s"

if [[ ${#MONITOR_PATTERNS[@]} -gt 0 ]]; then
  log_info "Monitor patterns: ${MONITOR_PATTERNS[*]}"
fi
if [[ ${#EXCLUDE_PATTERNS[@]} -gt 0 ]]; then
  log_info "Exclude patterns: ${EXCLUDE_PATTERNS[*]}"
fi

# Convert timeout to seconds
TIMEOUT_SEC=$((TIMEOUT_MIN * 60))
START_TIME=$(date +%s)

# Function to check if job name matches any pattern
matches_pattern() {
  local name="$1"
  shift
  local patterns=("$@")

  for pattern in "${patterns[@]}"; do
    if [[ "$name" == $pattern ]]; then
      return 0
    fi
  done
  return 1
}

# Function to filter jobs based on monitor/exclude patterns
should_monitor_job() {
  local job_name="$1"

  # If exclude patterns specified and job matches, skip it
  if [[ ${#EXCLUDE_PATTERNS[@]} -gt 0 ]]; then
    if matches_pattern "$job_name" "${EXCLUDE_PATTERNS[@]}"; then
      return 1
    fi
  fi

  # If monitor patterns specified, job must match one
  if [[ ${#MONITOR_PATTERNS[@]} -gt 0 ]]; then
    if matches_pattern "$job_name" "${MONITOR_PATTERNS[@]}"; then
      return 0
    fi
    return 1
  fi

  # No patterns = monitor all (except excluded)
  return 0
}

# Main monitoring loop
while true; do
  ELAPSED=$(($(date +%s) - START_TIME))
  ELAPSED_MIN=$((ELAPSED / 60))

  # Check timeout
  if [[ $ELAPSED -ge $TIMEOUT_SEC ]]; then
    log_warn "Watchdog reached ${TIMEOUT_MIN}m timeout - some jobs may still be running"
    exit 0
  fi

  # Get job statuses
  JOBS_JSON=$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${RUN_ID}/jobs?per_page=100" \
    --jq '.jobs[] | {name: .name, status: .status, conclusion: .conclusion}' 2>/dev/null) || {
    log_warn "Failed to fetch jobs, retrying..."
    sleep "$POLL_INTERVAL"
    continue
  }

  # Process jobs
  TOTAL=0
  COMPLETED=0
  FAILED=0
  FAILED_NAMES=()
  PENDING_STATUSES=()

  while IFS= read -r job; do
    [[ -z "$job" ]] && continue

    name=$(echo "$job" | jq -r '.name')
    status=$(echo "$job" | jq -r '.status')
    conclusion=$(echo "$job" | jq -r '.conclusion')

    # Check if we should monitor this job
    if ! should_monitor_job "$name"; then
      continue
    fi

    TOTAL=$((TOTAL + 1))

    if [[ "$status" == "completed" ]]; then
      COMPLETED=$((COMPLETED + 1))
      if [[ "$conclusion" == "failure" ]]; then
        FAILED=$((FAILED + 1))
        FAILED_NAMES+=("$name")
      fi
    else
      PENDING_STATUSES+=("$status")
    fi
  done <<< "$JOBS_JSON"

  # Count pending statuses (simple approach without associative arrays)
  PENDING_COUNT=$((TOTAL - COMPLETED))
  if [[ $PENDING_COUNT -gt 0 ]]; then
    # Get unique statuses
    PENDING_STR=$(printf '%s\n' "${PENDING_STATUSES[@]}" | sort | uniq -c | awk '{print $1" "$2}' | tr '\n' ',' | sed 's/,$//' | sed 's/,/, /g')
    [[ -z "$PENDING_STR" ]] && PENDING_STR="$PENDING_COUNT pending"
  else
    PENDING_STR="none"
  fi

  log_info "[${ELAPSED_MIN}m] Jobs: $COMPLETED/$TOTAL done, $FAILED failed, pending: $PENDING_STR"

  # Check if all monitored jobs are complete
  if [[ $COMPLETED -eq $TOTAL ]] && [[ $TOTAL -gt 0 ]]; then
    if [[ $FAILED -gt 0 ]]; then
      echo ""
      log_info "======================================================================"
      log_info "ALL MONITORED JOBS COMPLETED - $FAILED failure(s) detected:"
      for name in "${FAILED_NAMES[@]}"; do
        log_info "  - $name"
      done
      log_info "Triggering rerun of failed jobs..."
      log_info "======================================================================"

      # Trigger rerun via workflow dispatch
      REF="${GITHUB_HEAD_REF:-${GITHUB_REF#refs/heads/}}"
      log_info "Dispatching rerun-failed.yml on ref: $REF"

      gh workflow run rerun-failed.yml \
        --ref "$REF" \
        --field "run_id=$RUN_ID" || {
        log_error "Failed to trigger rerun workflow"
        exit 1
      }

      log_info "Rerun triggered successfully"
      exit 0
    else
      log_info "All monitored jobs completed successfully - no rerun needed"
      exit 0
    fi
  fi

  sleep "$POLL_INTERVAL"
done
