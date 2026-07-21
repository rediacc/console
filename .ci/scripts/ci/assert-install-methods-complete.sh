#!/bin/bash
# Aggregate the six per-platform install-method jobs into one verdict, and
# render the platform table into the job summary.
#
# Every platform is hard-required: an install method that silently stops being
# tested is the failure this gate exists to prevent, so "skipped" is NOT
# accepted here (unlike the soft-required tier in assert-ci-complete.sh).
#
# Usage (one env var per platform, plus the version for the summary line):
#   RESULT_LINUX_X64=success ... VERSION=1.2.3 \
#     .ci/scripts/ci/assert-install-methods-complete.sh
#
# Optional env:
#   GITHUB_STEP_SUMMARY   when set, the table is appended to it

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/null}"

# label|env-var-suffix
PLATFORMS=(
    "Linux x64 (Binary, Docker, APT, DNF, APK, Pacman, Quick, Linuxbrew)|LINUX_X64"
    "Linux arm64 (Binary, Docker, Quick)|LINUX_ARM64"
    "macOS ARM64 (Binary, Homebrew)|MACOS_ARM64"
    "macOS x64 (Binary, Homebrew)|MACOS_X64"
    "Windows x64 (Binary)|WINDOWS_X64"
    "Windows arm64 (Binary)|WINDOWS_ARM64"
)

{
    echo "## Install Method Test Results"
    echo ""
    echo "| Platform | Result |"
    echo "|----------|--------|"
} >>"$SUMMARY"

failed=false
for entry in "${PLATFORMS[@]}"; do
    label="${entry%%|*}"
    var="RESULT_${entry##*|}"
    value="${!var:-<unset>}"
    echo "| ${label} | ${value} |" >>"$SUMMARY"
    [[ "$value" != "success" ]] && failed=true
done
echo "" >>"$SUMMARY"

if [[ "$failed" == "true" ]]; then
    echo "**Status:** Some installation method tests failed" >>"$SUMMARY"
    log_error "Some installation method tests failed"
    exit 1
fi

echo "**Status:** All installation method tests passed for version ${VERSION:-<unset>}" >>"$SUMMARY"
log_info "All installation method tests passed for version ${VERSION:-<unset>}"
