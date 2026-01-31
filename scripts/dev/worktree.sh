#!/bin/bash
# Worktree management script for console development
# Creates date-based worktrees with tmux session integration
#
# Usage:
#   ./run.sh worktree create    # Create new worktree with MMDD-X format
#   ./run.sh worktree list      # List all console worktrees
#   ./run.sh worktree prune     # Interactive cleanup of merged PRs

set -euo pipefail

# Get script and repo directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Source common utilities
source "$ROOT_DIR/.ci/scripts/lib/common.sh"

# Configuration
WORKTREE_BASE="$ROOT_DIR/.worktrees"
BASE_BRANCH="main"
TMUX_PREFIX="console"

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# Get today's date in MMDD format
get_date_prefix() {
    date +%m%d
}

# Get the next sequence number for today's date
# Scans .worktrees/ for MMDD-* dirs, returns max+1
get_next_sequence_number() {
    local date_prefix="$1"
    local max_seq=0

    if [[ -d "$WORKTREE_BASE" ]]; then
        for dir in "$WORKTREE_BASE"/${date_prefix}-*; do
            if [[ -d "$dir" ]]; then
                local name
                name="$(basename "$dir")"
                # Extract sequence number after the dash
                local seq="${name#${date_prefix}-}"
                if [[ "$seq" =~ ^[0-9]+$ ]] && [[ "$seq" -gt "$max_seq" ]]; then
                    max_seq="$seq"
                fi
            fi
        done
    fi

    echo $((max_seq + 1))
}

# Check if a tmux session exists
tmux_session_exists() {
    local session_name="$1"
    tmux has-session -t "$session_name" 2>/dev/null
}

# Create a tmux session for a worktree
create_tmux_session() {
    local session_name="$1"
    local work_dir="$2"

    if ! command -v tmux &>/dev/null; then
        log_warn "tmux not installed, skipping session creation"
        return 0
    fi

    if tmux_session_exists "$session_name"; then
        log_warn "tmux session '$session_name' already exists"
        return 0
    fi

    tmux new-session -d -s "$session_name" -n "$session_name" -c "$work_dir"

    # New windows (Ctrl+b c) auto-layout: 75% top (claude) + 25% bottom (cli)
    tmux set-hook -t "$session_name" after-new-window \
        "split-window -v -l 25% -c '#{pane_current_path}' ; select-pane -U ; send-keys 'claude --dangerously-skip-permissions' C-m"

    log_info "Created tmux session: $session_name"
}

# Check if a PR for a branch is merged using gh CLI
is_pr_merged() {
    local branch_name="$1"

    if ! command -v gh &>/dev/null; then
        log_error "gh CLI is required for prune command"
        log_info "Install from: https://cli.github.com/"
        exit 1
    fi

    local state
    state=$(gh pr list --head "$branch_name" --state merged --json state --jq '.[0].state // empty' 2>/dev/null || echo "")

    [[ "$state" == "MERGED" ]]
}

# Remove a worktree and optionally its branch and tmux session
remove_worktree() {
    local wt_path="$1"
    local session_name="$2"
    local branch_name="$3"

    # Kill tmux session if exists
    if command -v tmux &>/dev/null && tmux_session_exists "$session_name"; then
        tmux kill-session -t "$session_name" 2>/dev/null || true
        log_info "Killed tmux session: $session_name"
    fi

    # Remove worktree
    git -C "$ROOT_DIR" worktree remove --force "$wt_path" 2>/dev/null || {
        log_warn "Could not remove worktree normally, trying force removal"
        rm -rf "$wt_path"
        git -C "$ROOT_DIR" worktree prune
    }
    log_info "Removed worktree: $wt_path"

    # Delete branch
    if git -C "$ROOT_DIR" rev-parse --verify "$branch_name" &>/dev/null; then
        git -C "$ROOT_DIR" branch -D "$branch_name" 2>/dev/null || true
        log_info "Deleted branch: $branch_name"
    fi
}

# =============================================================================
# COMMANDS
# =============================================================================

# Create a new worktree with MMDD-X naming
worktree_create() {
    local date_prefix
    date_prefix="$(get_date_prefix)"

    local seq_num
    seq_num="$(get_next_sequence_number "$date_prefix")"

    local wt_name="${date_prefix}-${seq_num}"
    local wt_path="$WORKTREE_BASE/$wt_name"
    local branch_name="$wt_name"
    local session_name="${TMUX_PREFIX}-${wt_name}"

    log_step "Creating worktree: $wt_name"

    # Create worktrees directory if needed
    mkdir -p "$WORKTREE_BASE"

    # Ensure we have latest main
    log_info "Fetching latest changes..."
    git -C "$ROOT_DIR" fetch origin "$BASE_BRANCH" --quiet

    # Check if branch already exists
    if git -C "$ROOT_DIR" rev-parse --verify "$branch_name" &>/dev/null; then
        log_error "Branch '$branch_name' already exists"
        log_info "Delete it with: git branch -D $branch_name"
        exit 1
    fi

    # Create worktree with new branch
    log_info "Creating worktree at $wt_path"
    git -C "$ROOT_DIR" worktree add -b "$branch_name" "$wt_path" "origin/$BASE_BRANCH"

    # Initialize submodules
    log_info "Initializing submodules..."
    git -C "$wt_path" submodule update --init --recursive

    # Create tmux session
    create_tmux_session "$session_name" "$wt_path"

    # Run npm install + build shared packages, then set up panes:
    #   +------------------+------------------+
    #   | claude (pane 0)  | claude (pane 2)  |  75%
    #   +------------------+------------------+
    #   |           cli terminal (pane 1)     |  25%
    #   +-------------------------------------+
    if command -v tmux &>/dev/null && tmux_session_exists "$session_name"; then
        log_info "Running npm install + build:packages in tmux session..."
        tmux send-keys -t "${session_name}:0" \
            "npm install && npm run build:packages && tmux split-window -v -l 25% -c '${wt_path}' && RIGHT_PANE=\$(tmux split-window -h -c '${wt_path}' -P -F '#{pane_id}') && tmux send-keys -t \"\$RIGHT_PANE\" 'claude --dangerously-skip-permissions' C-m && clear && claude --dangerously-skip-permissions" C-m
    else
        log_info "Run 'npm install && npm run build:packages' in the worktree to set up dependencies"
    fi

    echo ""
    log_info "Worktree created successfully!"
    echo ""
    echo "  Path:    $wt_path"
    echo "  Branch:  $branch_name"
    if command -v tmux &>/dev/null; then
        echo "  Session: $session_name"
        echo ""
        echo "Attach with: tmux attach -t $session_name"
    fi
}

# List all console worktrees with status
worktree_list() {
    log_step "Console worktrees"
    echo ""

    if [[ ! -d "$WORKTREE_BASE" ]]; then
        log_info "No worktrees found"
        return 0
    fi

    local found=false

    # Get list of worktrees from git
    while IFS= read -r line; do
        if [[ "$line" == "$WORKTREE_BASE"* ]]; then
            found=true
            local wt_path="$line"
            local wt_name
            wt_name="$(basename "$wt_path")"
            local session_name="${TMUX_PREFIX}-${wt_name}"

            # Get branch name
            local branch=""
            if [[ -d "$wt_path" ]]; then
                branch=$(git -C "$wt_path" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
            fi

            # Check tmux session
            local tmux_status="no session"
            if command -v tmux &>/dev/null && tmux_session_exists "$session_name"; then
                tmux_status="$session_name"
            fi

            printf "  %-12s  branch: %-12s  tmux: %s\n" "$wt_name" "$branch" "$tmux_status"
        fi
    done < <(git -C "$ROOT_DIR" worktree list --porcelain | grep "^worktree " | cut -d' ' -f2-)

    if [[ "$found" == "false" ]]; then
        log_info "No worktrees found in $WORKTREE_BASE"
    fi
}

# Remove a specific worktree by name
worktree_remove() {
    local wt_name="${1:-}"

    if [[ -z "$wt_name" ]]; then
        log_error "Usage: ./run.sh worktree remove <name>"
        log_info "Use './run.sh worktree list' to see available worktrees"
        exit 1
    fi

    local wt_path="$WORKTREE_BASE/$wt_name"
    local session_name="${TMUX_PREFIX}-${wt_name}"

    if [[ ! -d "$wt_path" ]]; then
        log_error "Worktree not found: $wt_name"
        log_info "Use './run.sh worktree list' to see available worktrees"
        exit 1
    fi

    # Get branch name
    local branch=""
    branch=$(git -C "$wt_path" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "$wt_name")

    log_step "Removing worktree: $wt_name"
    remove_worktree "$wt_path" "$session_name" "$branch"
    log_info "Done"
}

# Interactive cleanup of worktrees with merged PRs
worktree_prune() {
    if ! command -v gh &>/dev/null; then
        log_error "gh CLI is required for prune command"
        log_info "Install from: https://cli.github.com/"
        exit 1
    fi

    log_step "Checking for worktrees with merged PRs..."
    echo ""

    if [[ ! -d "$WORKTREE_BASE" ]]; then
        log_info "No worktrees found"
        return 0
    fi

    local found_merged=false

    # Get list of worktrees
    while IFS= read -r line; do
        if [[ "$line" == "$WORKTREE_BASE"* ]]; then
            local wt_path="$line"
            local wt_name
            wt_name="$(basename "$wt_path")"
            local session_name="${TMUX_PREFIX}-${wt_name}"

            # Get branch name
            local branch=""
            if [[ -d "$wt_path" ]]; then
                branch=$(git -C "$wt_path" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
            fi

            if [[ -z "$branch" ]]; then
                continue
            fi

            # Check if PR is merged
            if is_pr_merged "$branch"; then
                found_merged=true
                echo "  $wt_name (branch: $branch) - PR MERGED"

                read -p "  Delete this worktree? (y/N): " response
                if [[ "$response" =~ ^[yY]$ ]]; then
                    remove_worktree "$wt_path" "$session_name" "$branch"
                else
                    log_info "Skipped $wt_name"
                fi
                echo ""
            fi
        fi
    done < <(git -C "$ROOT_DIR" worktree list --porcelain | grep "^worktree " | cut -d' ' -f2-)

    if [[ "$found_merged" == "false" ]]; then
        log_info "No worktrees with merged PRs found"
    fi

    # Clean up any stale worktree entries
    git -C "$ROOT_DIR" worktree prune
}

# =============================================================================
# MAIN
# =============================================================================

show_help() {
    cat <<EOF
Usage: ./run.sh worktree <command>

Commands:
  create        Create a new worktree with MMDD-X naming format
  list          List all console worktrees with branch and tmux status
  remove <name> Remove a specific worktree by name
  prune         Interactive cleanup of worktrees with merged PRs

Examples:
  ./run.sh worktree create       # Creates 0128-1 with tmux session console-0128-1
  ./run.sh worktree create       # Creates 0128-2 (next sequence)
  ./run.sh worktree list         # Shows all worktrees
  ./run.sh worktree remove 0128-1  # Remove specific worktree
  ./run.sh worktree prune        # Interactive cleanup of merged PRs

After create:
  tmux attach -t console-0128-1
EOF
}

main() {
    case "${1:-}" in
        create)
            worktree_create
            ;;
        list)
            worktree_list
            ;;
        remove)
            shift
            worktree_remove "$@"
            ;;
        prune)
            worktree_prune
            ;;
        help|--help|-h)
            show_help
            ;;
        "")
            show_help
            ;;
        *)
            log_error "Unknown command: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

main "$@"
