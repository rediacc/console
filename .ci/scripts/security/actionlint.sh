#!/bin/bash
# Validate workflow YAML with actionlint.
#
# WHY THIS GATE EXISTS
# Every other workflow check in this repo reads workflow files as TEXT: grep for
# banned keys, count inline logic lines, match action SHAs. None of them parse
# `${{ }}` expressions or check them against the context they run in, so a whole
# class of defect reached main repeatedly and was only ever caught by dispatching
# the workflow and watching it produce nothing:
#
#   timeout-minutes: ${{ fromJSON(inputs.duration) + 40 }}
#
# GitHub Actions expressions have NO arithmetic operators. That line is a syntax
# error; the run started with ZERO jobs and the workflow was listed by file path
# instead of name, with no error anywhere pointing at the cause. actionlint finds
# it in about one second.
#
# COVERAGE IS DELIBERATELY WIDER THAN .github/workflows
# `.ci/breakpoint/workflow/breakpoint.yml` is a workflow TEMPLATE meant to be
# vendored into other repositories. check-workflows.sh, check-workflow-gates.sh
# and check-actions.ts all scan `.github/` only, so the template is invisible to
# every one of them -- it could carry an unpinned action SHA or a broken
# expression and no gate would say a word. It is the file that broke twice.
#
# THE SHELLCHECK INTEGRATION IS ON, which closes a real hole: check-shellcheck.sh
# covers shell FILES, and nothing covered the inline `run:` blocks, which are
# just as much executable shell. Turning it on required clearing 44 pre-existing
# findings first (38 SC2086, 3 SC2129, 2 SC2162, 1 SC2155); they are fixed, so
# the gate now starts from zero and any new one is a regression.
#
# Do NOT disable this flag to get past a finding. If a `run:` block genuinely
# needs word-splitting, annotate that block with a `# shellcheck disable=SC2086`
# line carrying a reason, so the exception is local, visible and reviewable
# rather than global and silent.
#
# Usage: actionlint.sh
# Exit:  0 clean, 1 findings, 2 tool unavailable, 3 nothing to check (vacuous).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"
# shellcheck source=../../config/constants.sh
source "$REPO_ROOT/.ci/config/constants.sh"

CACHE_DIR="${CI_TEMP:-${RUNNER_TEMP:-/tmp}}/actionlint-${ACTIONLINT_VERSION}"
BIN="$CACHE_DIR/actionlint"

# -----------------------------------------------------------------------------
# Acquire the tool: pinned, checksum-verified BEFORE extraction.
# -----------------------------------------------------------------------------
ensure_actionlint() {
    # A matching binary already on PATH wins, so a developer's own install is
    # honoured and CI does not re-download on every invocation.
    if command -v actionlint >/dev/null 2>&1; then
        local have
        have="$(actionlint --version 2>/dev/null | head -1 | tr -d 'v')"
        if [[ "$have" == "$ACTIONLINT_VERSION" ]]; then
            BIN="$(command -v actionlint)"
            return 0
        fi
        log_info "actionlint $have is on PATH but this gate pins $ACTIONLINT_VERSION; fetching the pinned build"
    fi

    [[ -x "$BIN" ]] && return 0

    local arch sha url tmp
    arch="$(uname -m)"
    case "$arch" in
        x86_64 | amd64)
            arch="amd64"
            sha="$ACTIONLINT_SHA256_LINUX_AMD64"
            ;;
        aarch64 | arm64)
            arch="arm64"
            sha="$ACTIONLINT_SHA256_LINUX_ARM64"
            ;;
        *)
            log_error "no pinned actionlint checksum for architecture '$arch'"
            log_error "add one to .ci/config/constants.sh rather than downloading unverified"
            exit 2
            ;;
    esac

    url="https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VERSION}/actionlint_${ACTIONLINT_VERSION}_linux_${arch}.tar.gz"
    mkdir -p "$CACHE_DIR"
    tmp="$CACHE_DIR/actionlint.tar.gz"

    log_info "fetching actionlint ${ACTIONLINT_VERSION} (${arch})"
    if ! curl -fsSL --max-time 180 --retry 3 --retry-delay 5 -o "$tmp" "$url"; then
        log_error "could not download actionlint from $url"
        exit 2
    fi

    # Verify BEFORE extracting. An unverified tarball is arbitrary code, and
    # extraction is the point at which it starts to matter.
    if ! echo "${sha}  ${tmp}" | sha256sum -c - >/dev/null 2>&1; then
        log_error "actionlint checksum MISMATCH -- refusing to extract"
        log_error "  expected: $sha"
        log_error "  actual:   $(sha256sum "$tmp" | cut -d' ' -f1)"
        log_error "if the release was legitimately re-cut, update the pin in .ci/config/constants.sh"
        rm -f "$tmp"
        exit 2
    fi

    tar -xzf "$tmp" -C "$CACHE_DIR" actionlint
    rm -f "$tmp"
    chmod +x "$BIN"
}

# -----------------------------------------------------------------------------
# Collect the files to check.
# -----------------------------------------------------------------------------
collect_targets() {
    local f
    for f in "$REPO_ROOT"/.github/workflows/*.yml "$REPO_ROOT"/.github/workflows/*.yaml; do
        [[ -f "$f" ]] && echo "$f"
    done
    # Workflow TEMPLATES that live outside .github/ and are therefore invisible
    # to every other workflow gate. See the header.
    for f in "$REPO_ROOT"/.ci/*/workflow/*.yml; do
        [[ -f "$f" ]] && echo "$f"
    done
}

main() {
    ensure_actionlint

    local targets count
    targets="$(collect_targets)"
    count="$(echo "$targets" | grep -c . || true)"

    # Anti-vacuity: a linter with no input exits 0 and looks like a pass. If the
    # workflow directory is ever renamed or moved, this must say so rather than
    # quietly retire itself.
    if [[ "$count" -eq 0 ]]; then
        log_error "no workflow files found under .github/workflows/ or .ci/*/workflow/"
        log_error "a lint run over zero files reports success while checking nothing"
        exit 3
    fi

    log_step "Running actionlint over $count workflow file(s)"

    local rc=0
    # shellcheck disable=SC2086  # word-splitting the newline-separated list is intended
    "$BIN" -no-color $targets || rc=$?

    if [[ "$rc" -ne 0 ]]; then
        log_error "actionlint reported findings in the workflow files above"
        log_error "these are parse/expression/context errors or ShellCheck findings in"
        log_error "an inline run: block. A bad \${{ }} expression makes a run start with"
        log_error "ZERO jobs and no error message anywhere."
        exit 1
    fi

    log_info "actionlint clean across $count workflow file(s)"
}

main "$@"
