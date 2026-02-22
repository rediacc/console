#!/bin/bash
# Worktree management script for console development
# Creates date-based worktrees with tmux session integration
#
# Usage:
#   ./run.sh worktree create       # Create new worktree with MMDD-X format
#   ./run.sh worktree create -t    # Create with Claude agent teams enabled
#   ./run.sh worktree list         # List all console worktrees
#   ./run.sh worktree switch       # Switch branch and sync submodules
#   ./run.sh worktree prune        # Interactive cleanup of merged PRs

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

# Sync main worktree to latest origin/main and update submodules.
# Best-effort: warns and continues on failure so worktree commands
# can proceed with cached state.
sync_main_repo() {
    log_step "Syncing main repo to latest origin/$BASE_BRANCH..."

    # Check if main worktree is on the base branch
    local current_branch
    current_branch="$(git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null)" || {
        log_warn "Could not determine branch in $ROOT_DIR, skipping sync"
        return 0
    }

    # Stash uncommitted changes before switching/pulling
    local needs_stash=false
    if ! git -C "$ROOT_DIR" diff --quiet 2>/dev/null ||
        ! git -C "$ROOT_DIR" diff --cached --quiet 2>/dev/null; then
        needs_stash=true
        git -C "$ROOT_DIR" stash --quiet --include-untracked 2>/dev/null || {
            log_warn "Main worktree has uncommitted changes -- stash failed, skipping sync"
            git -C "$ROOT_DIR" fetch origin "$BASE_BRANCH" --quiet 2>/dev/null || true
            return 0
        }
    fi

    # Checkout base branch if not already on it
    if [[ "$current_branch" != "$BASE_BRANCH" ]]; then
        if ! git -C "$ROOT_DIR" checkout "$BASE_BRANCH" --quiet 2>/dev/null; then
            log_warn "Could not checkout '$BASE_BRANCH', staying on '$current_branch'"
            if [[ "$needs_stash" == true ]]; then
                git -C "$ROOT_DIR" stash pop --quiet 2>/dev/null || true
            fi
            return 0
        fi
        log_info "Checked out $BASE_BRANCH (was on $current_branch)"
    fi

    # Pull latest (fast-forward only)
    if ! git -C "$ROOT_DIR" pull --ff-only origin "$BASE_BRANCH" --quiet 2>/dev/null; then
        log_warn "Pull failed (diverged or network issue), falling back to fetch"
        git -C "$ROOT_DIR" fetch origin "$BASE_BRANCH" --quiet 2>/dev/null || {
            log_warn "Fetch also failed, continuing with cached state"
        }
        if [[ "$needs_stash" == true ]]; then
            git -C "$ROOT_DIR" stash pop --quiet 2>/dev/null || true
        fi
        return 0
    fi

    if [[ "$needs_stash" == true ]]; then
        git -C "$ROOT_DIR" stash pop --quiet 2>/dev/null || {
            log_warn "Stash pop had conflicts -- your changes are still in git stash"
        }
    fi

    log_info "Pulled latest origin/$BASE_BRANCH"

    # Update submodules to the commits recorded in the parent repo.
    # Do NOT checkout local branches — `submodule update` already sets
    # the correct detached HEAD. Checking out stale local branches
    # (e.g. `git checkout main` inside a submodule) can roll back
    # submodule pointers when the local branch hasn't been fast-forwarded.
    log_info "Updating submodules..."
    pushd "$ROOT_DIR" >/dev/null
    git submodule sync --quiet 2>/dev/null || true
    if ! git submodule update --init --recursive --quiet 2>/dev/null; then
        log_warn "Submodule update failed for some modules, continuing"
    fi
    popd >/dev/null

    log_info "Main repo sync complete"
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
    local teams_mode="${3:-false}"

    if ! command -v tmux &>/dev/null; then
        log_warn "tmux not installed, skipping session creation"
        return 0
    fi

    if tmux_session_exists "$session_name"; then
        log_warn "tmux session '$session_name' already exists"
        return 0
    fi

    tmux new-session -d -s "$session_name" -n "$session_name" -c "$work_dir"

    # Enable agent teams env var if teams mode is on
    if [[ "$teams_mode" == "true" ]]; then
        tmux set-environment -t "$session_name" CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS 1
    fi

    local claude_cmd='claude --dangerously-skip-permissions'
    if [[ "$teams_mode" == "true" ]]; then
        claude_cmd='claude --dangerously-skip-permissions --teammate-mode tmux'
    fi

    # New windows (Ctrl+b c) auto-layout: 75% top (claude) + 25% bottom (cli)
    tmux set-hook -t "$session_name" after-new-window \
        "split-window -v -l 25% -c '#{pane_current_path}' ; select-pane -U ; send-keys '${claude_cmd}' C-m"

    log_info "Created tmux session: $session_name"
    if [[ "$teams_mode" == "true" ]]; then
        log_info "Agent teams enabled (teammates will spawn in tmux panes)"
    fi
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
# SUBMODULE HELPERS
# =============================================================================

# List all submodule paths from .gitmodules
list_submodules() {
    git config --file .gitmodules --get-regexp path 2>/dev/null | awk '{ print $2 }'
}

# Create or checkout branch in submodule
setup_submodule_branch() {
    local sm_path="$1"
    local branch="$2"

    if [[ ! -d "$sm_path/.git" ]] && [[ ! -f "$sm_path/.git" ]]; then
        log_warn "Submodule $sm_path not initialized, skipping"
        return 0
    fi

    git -C "$sm_path" fetch origin --quiet 2>/dev/null || log_warn "Could not fetch origin for $sm_path"

    if git -C "$sm_path" rev-parse --verify "origin/$branch" &>/dev/null; then
        log_info "  Checking out existing branch '$branch' in $sm_path"
        git -C "$sm_path" checkout -B "$branch" "origin/$branch" --quiet
    elif git -C "$sm_path" rev-parse --verify "$branch" &>/dev/null; then
        log_info "  Checking out local branch '$branch' in $sm_path"
        git -C "$sm_path" checkout "$branch" --quiet
    else
        log_info "  Creating new branch '$branch' in $sm_path"
        git -C "$sm_path" checkout -b "$branch" --quiet
    fi
}

# Setup matching branches in all submodules
setup_submodule_branches() {
    local branch="$1"
    local wt_path="$2"

    log_step "Setting up submodule branches..."
    pushd "$wt_path" >/dev/null

    for sm_path in $(list_submodules); do
        setup_submodule_branch "$sm_path" "$branch"
    done

    popd >/dev/null
}

# =============================================================================
# COMMANDS
# =============================================================================

# Create a new worktree with MMDD-X naming
worktree_create() {
    local teams_mode=false

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --teams | -t)
                teams_mode=true
                shift
                ;;
            --help | -h)
                echo "Usage: ./run.sh worktree create [--teams]"
                echo ""
                echo "Options:"
                echo "  --teams, -t  Enable Claude agent teams (experimental)"
                echo "               Spawns lead with --teammate-mode tmux so"
                echo "               teammates get their own tmux panes"
                return 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    # Sync main repo to latest origin/main before creating worktree
    sync_main_repo

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

    # Setup matching branches in all submodules
    setup_submodule_branches "$branch_name" "$wt_path"

    # Create tmux session
    create_tmux_session "$session_name" "$wt_path" "$teams_mode"

    # Install deps for submodules that are outside npm workspaces but
    # referenced by quality scripts (check:types, check:lint, check:format).
    local private_install="for pj in \$(find private/ -maxdepth 2 -name package.json ! -path '*/node_modules/*' 2>/dev/null); do echo \"Installing deps in \$(dirname \$pj)...\" && (cd \$(dirname \$pj) && npm install) || true; done"

    # Run npm install + build shared packages, then set up panes
    if command -v tmux &>/dev/null && tmux_session_exists "$session_name"; then
        log_info "Running npm install + build:packages in tmux session..."
        if [[ "$teams_mode" == "true" ]]; then
            # Teams mode: single lead pane + CLI (teammates spawn their own tmux panes)
            #   +-------------------------------------+
            #   |        claude lead (pane 0)         |  75%
            #   +-------------------------------------+
            #   |           cli terminal (pane 1)     |  25%
            #   +-------------------------------------+
            tmux send-keys -t "${session_name}:0" \
                "npm install && npm run build:packages && ${private_install} && tmux split-window -v -l 25% -c '${wt_path}' && clear && claude --dangerously-skip-permissions --teammate-mode tmux" C-m
        else
            # Standard mode: two claude panes + CLI
            #   +------------------+------------------+
            #   | claude (pane 0)  | claude (pane 2)  |  75%
            #   +------------------+------------------+
            #   |           cli terminal (pane 1)     |  25%
            #   +-------------------------------------+
            tmux send-keys -t "${session_name}:0" \
                "npm install && npm run build:packages && ${private_install} && tmux split-window -v -l 25% -c '${wt_path}' && RIGHT_PANE=\$(tmux split-window -h -c '${wt_path}' -P -F '#{pane_id}') && tmux send-keys -t \"\$RIGHT_PANE\" 'claude --dangerously-skip-permissions' C-m && clear && claude --dangerously-skip-permissions" C-m
        fi
    else
        log_info "Run the following in the worktree to set up dependencies:"
        log_info "  npm install && npm run build:packages"
        log_info "  # Install submodule deps (not in npm workspaces):"
        log_info "  (cd private/account && npm install)"
    fi

    echo ""
    log_info "Worktree created successfully!"
    echo ""
    echo "  Path:    $wt_path"
    echo "  Branch:  $branch_name"
    if [[ "$teams_mode" == "true" ]]; then
        echo "  Teams:   enabled (lead + teammate tmux panes)"
    fi
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

    # Sync main repo so merged branches are correctly identified
    sync_main_repo

    log_step "Checking for worktrees to clean up..."
    echo ""

    if [[ ! -d "$WORKTREE_BASE" ]]; then
        log_info "No worktrees found"
        return 0
    fi

    local found_cleanup=false

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
                found_cleanup=true
                echo "  $wt_name (branch: $branch) - PR MERGED"
                remove_worktree "$wt_path" "$session_name" "$branch"
                echo ""
                continue
            fi

            # Check if branch has no commits ahead of main (empty worktree)
            local ahead
            ahead=$(git -C "$ROOT_DIR" rev-list --count "$BASE_BRANCH".."$branch" 2>/dev/null || echo "")
            if [[ "$ahead" == "0" ]]; then
                # Also verify no uncommitted changes in the worktree
                if [[ -d "$wt_path" ]] &&
                    git -C "$wt_path" diff --quiet 2>/dev/null &&
                    git -C "$wt_path" diff --cached --quiet 2>/dev/null; then
                    found_cleanup=true
                    echo "  $wt_name (branch: $branch) - NO COMMITS, NO CHANGES"
                    remove_worktree "$wt_path" "$session_name" "$branch"
                    echo ""
                fi
            fi
        fi
    done < <(git -C "$ROOT_DIR" worktree list --porcelain | grep "^worktree " | cut -d' ' -f2-)

    if [[ "$found_cleanup" == "false" ]]; then
        log_info "No worktrees to clean up"
    fi

    # Clean up any stale worktree entries
    git -C "$ROOT_DIR" worktree prune
}

# Switch branch in current repo and sync submodules
worktree_switch() {
    local branch=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --help | -h)
                echo "Usage: ./run.sh worktree switch <branch>"
                echo ""
                echo "Switch the current repo to <branch> and sync submodules."
                echo ""
                echo "For each submodule:"
                echo "  - If the branch has pointer changes (submodule commit differs"
                echo "    from origin/main), the submodule is switched to a matching branch."
                echo "  - Otherwise, the submodule is updated to the recorded commit."
                echo ""
                echo "Options:"
                echo "  --help, -h  Show this help message"
                return 0
                ;;
            -*)
                log_error "Unknown option: $1"
                exit 1
                ;;
            *)
                if [[ -z "$branch" ]]; then
                    branch="$1"
                else
                    log_error "Unexpected argument: $1"
                    exit 1
                fi
                shift
                ;;
        esac
    done

    # Validate branch argument
    if [[ -z "$branch" ]]; then
        log_error "Usage: ./run.sh worktree switch <branch>"
        log_info "Specify the branch name to switch to."
        exit 1
    fi

    # Determine the repo root for the current checkout/worktree
    local repo_dir
    repo_dir="$(git rev-parse --show-toplevel 2>/dev/null)" || {
        log_error "Not inside a git repository"
        exit 1
    }

    # Safety: check for uncommitted changes in main repo
    if ! git -C "$repo_dir" diff --quiet 2>/dev/null ||
        ! git -C "$repo_dir" diff --cached --quiet 2>/dev/null; then
        log_warn "You have uncommitted changes in $repo_dir"
        log_warn "Please commit or stash them before switching branches."
        exit 1
    fi

    # Safety: check for uncommitted changes in submodules
    for sm_path in $(cd "$repo_dir" && list_submodules); do
        local full_sm_path="$repo_dir/$sm_path"
        if [[ -d "$full_sm_path/.git" ]] || [[ -f "$full_sm_path/.git" ]]; then
            if ! git -C "$full_sm_path" diff --quiet 2>/dev/null ||
                ! git -C "$full_sm_path" diff --cached --quiet 2>/dev/null; then
                log_warn "Submodule $sm_path has uncommitted changes"
                log_warn "Please commit or stash them before switching branches."
                exit 1
            fi
        fi
    done

    # Fetch origin to have latest refs
    log_step "Fetching latest changes..."
    git -C "$repo_dir" fetch origin --quiet

    # Verify the target branch exists
    if ! git -C "$repo_dir" rev-parse --verify "origin/$branch" &>/dev/null &&
        ! git -C "$repo_dir" rev-parse --verify "$branch" &>/dev/null; then
        log_error "Branch '$branch' not found (checked both local and origin)"
        exit 1
    fi

    # Switch the main repo
    log_step "Switching to branch '$branch'..."
    if git -C "$repo_dir" rev-parse --verify "origin/$branch" &>/dev/null; then
        git -C "$repo_dir" checkout -B "$branch" "origin/$branch" --quiet
        log_info "Checked out '$branch' (tracking origin/$branch)"
    else
        git -C "$repo_dir" checkout "$branch" --quiet
        log_info "Checked out local branch '$branch'"
    fi

    # Sync submodules
    log_step "Syncing submodules..."
    pushd "$repo_dir" >/dev/null

    git submodule sync --quiet
    git submodule update --init --quiet

    for sm_path in $(list_submodules); do
        setup_submodule_branch "$sm_path" "$branch"
    done

    popd >/dev/null

    # Summary
    echo ""
    log_info "Switched to branch '$branch'"
    echo "  Path: $repo_dir"
}

# =============================================================================
# MAIN
# =============================================================================

show_help() {
    cat <<EOF
Usage: ./run.sh worktree <command> [options]

Commands:
  create [options]  Create a new worktree with MMDD-X naming format
  list              List all console worktrees with branch and tmux status
  remove <name>     Remove a specific worktree by name
  switch <branch>   Switch current repo to branch and sync submodules
  prune             Interactive cleanup of worktrees with merged PRs

Create Options:
  --teams, -t  Enable Claude agent teams (experimental).
               Sets CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
               and launches lead with --teammate-mode tmux.
               Teammates spawn in their own tmux panes.

Examples:
  ./run.sh worktree create           # Creates 0128-1 with tmux session
  ./run.sh worktree create -t        # Creates with agent teams enabled
  ./run.sh worktree list             # Shows all worktrees
  ./run.sh worktree remove 0128-1    # Remove specific worktree
  ./run.sh worktree switch 0204-1    # Switch branch and sync submodules
  ./run.sh worktree prune            # Cleanup worktrees with merged PRs

After create:
  tmux attach -t console-0128-1
EOF
}

main() {
    case "${1:-}" in
        create)
            shift
            worktree_create "$@"
            ;;
        list)
            worktree_list
            ;;
        remove)
            shift
            worktree_remove "$@"
            ;;
        switch)
            shift
            worktree_switch "$@"
            ;;
        prune)
            worktree_prune
            ;;
        help | --help | -h)
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
