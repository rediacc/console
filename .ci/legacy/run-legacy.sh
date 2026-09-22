#!/bin/bash
# THE LEGACY run.sh BODY. The router that dispatches into this file is ./run.sh.
#
# WHAT HAPPENED. On 2026-09-06 the repo-root run.sh was split: this file is that
# script, moved here whole, and ./run.sh became a one-page router that sends a
# verb either to the `rediacc_ci` Python package or here. Nothing was rewritten
# in the move and nothing was dropped -- the split is deliberately the largest
# revert boundary in the tooling transformation, so `git diff` between this file
# and the old run.sh must show only the three changes listed below.
#
# THE THREE LINES THAT CHANGED, and why each had to:
#
#   1. THIS HEADER. Added; the file has to say what it is.
#   2. ROOT_DIR. It is derived from BASH_SOURCE, which now points two levels
#      deeper, so the `cd` gained `/../..`. Deriving it from the file rather than
#      inheriting it from the router is deliberate: this file stays runnable on
#      its own (`.ci/legacy/run-legacy.sh quality all` works), so the split can be
#      bisected from either side.
#   3. A COMMENT that cited "line 9" for `set -euo pipefail`. Prepending this
#      header moved that line, and a comment citing a line number is a comment
#      that goes stale the next time anyone touches the top of a file. It now
#      names the setting instead of its address.
#
# STILL SOURCEABLE. The `if [[ "${BASH_SOURCE[0]}" == "${0}" ]]` guard at the end
# means `source .ci/legacy/run-legacy.sh` gives you every function here without
# running anything -- which is how .ci/scripts/test/gates/test-run-sh.sh reads
# `quality_all` and `fix_shell` without executing them.
#
# Console development script
# Aligned with CI workflow from .github/workflows/ci.yml
#
# ⚠️  IMPORTANT: When updating this file:
# ⚠️  1. Check if CI scripts need updates (.ci/config/constants.sh)
# ⚠️  2. Test all affected commands

set -euo pipefail

# Root directory
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Source configuration and utilities
source "$ROOT_DIR/.ci/config/constants.sh"
# The gate toolchain resolver. Sourced HERE rather than lazily, so a gate that
# needs a pinned tool fails with the version mismatch as its reason rather than
# "toolchain_check: command not found", which names the wrong problem.
source "$ROOT_DIR/.ci/scripts/lib/toolchain.sh"
source "$ROOT_DIR/.ci/lib/local-common.sh"
source "$ROOT_DIR/.ci/lib/service.sh"

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

# Check if Docker is running
check_docker() {
    if ! command -v docker &>/dev/null; then
        log_error "Docker is not installed"
        log_info "Install Docker from: https://docs.docker.com/get-docker/"
        exit 1
    fi

    if ! docker info &>/dev/null; then
        log_error "Docker is not running"
        log_info "Start Docker Desktop or Docker daemon"
        exit 1
    fi
}

# =============================================================================
# QUALITY COMMANDS
# =============================================================================

quality_lint() {
    check_node_version
    log_step "Running lint checks"
    npm run lint -- --max-warnings 0
    npm run lint:unused
}

quality_format() {
    check_node_version
    log_step "Checking code formatting"
    npm run check:format
}

quality_types() {
    check_node_version
    log_step "Checking TypeScript types"
    npm run typecheck
}

quality_all() {
    check_node_version
    log_step "Running all quality checks"
    npm run quality

    # Shell formatting/linting. THIS USED TO SKIP AND RETURN SUCCESS.
    #
    # `command -v shfmt` + log_warn + fall through meant that on any machine
    # without shfmt -- which is every non-Debian host, and was this very box
    # until someone hand-installed it -- `./run.sh quality all` reported GREEN
    # having never run a shell gate. A gate that cannot run must not be
    # indistinguishable from a gate that passed.
    #
    # It is also not enough for shfmt to merely EXIST: a different version
    # formats differently, so an unpinned binary on PATH silently decides the
    # verdict. toolchain_check accepts it only AT the pin.
    if toolchain_check shfmt >/dev/null 2>&1; then
        quality_shell
    else
        log_error "shell gates cannot run here:"
        toolchain_check shfmt 2>&1 | sed 's/^/    /' >&2
        log_info "Run them in the devbox instead: ./run.sh devbox exec -- ./run.sh quality shell"
        log_info "Or see what every lane has: .ci/scripts/lib/toolchain.sh --report"
        return 1
    fi
}

quality_deps() {
    check_node_version
    "$ROOT_DIR/.ci/scripts/quality/check-deps.sh"
}

quality_actions() {
    check_node_version
    log_step "Checking GitHub Actions versions..."
    npx tsx "$ROOT_DIR/scripts/gates/check-actions.ts"
}

quality_dead_bash() {
    check_node_version
    log_step "Checking for dead shell functions and orphaned scripts..."
    npx tsx "$ROOT_DIR/scripts/gates/check-dead-bash.ts"
}

quality_suppressions() {
    check_node_version
    log_step "Checking suppression liveness (are allowlist entries still needed?)..."
    npx tsx "$ROOT_DIR/scripts/gates/check-suppression-liveness.ts"
}

quality_audit() {
    check_node_version
    PYTHONPATH="$ROOT_DIR/.ci" python3 -m rediacc_ci.security.audit
}

quality_shell() {
    PYTHONPATH="$ROOT_DIR/.ci" python3 -m rediacc_ci.security.shellcheck
    PYTHONPATH="$ROOT_DIR/.ci" python3 -m rediacc_ci.security.shfmt
}

quality_submodules() {
    log_step "Checking submodule branch alignment"
    "$ROOT_DIR/.ci/scripts/quality/check-submodule-branches.sh"
}

# =============================================================================
# FIX COMMANDS
# =============================================================================

fix_format() {
    check_node_version
    log_step "Auto-fixing code formatting"
    npm run fix:format
}

fix_lint() {
    check_node_version
    log_step "Auto-fixing linting issues"
    npm run fix:lint
}

fix_all() {
    check_node_version
    log_step "Auto-fixing all issues"
    npm run fix:all
}

fix_shell() {
    log_step "Auto-fixing shell script formatting"
    # THE SAME BINARY THE GATE VERIFIES WITH. This used to take whatever `shfmt`
    # was on PATH while .ci/scripts/security/shfmt.sh checked with the pinned
    # one, so `./run.sh fix shell` could reformat a file into a state the gate
    # then rejected -- the nastiest shape of a version split, because the tool
    # that is supposed to fix the problem creates it.
    local shfmt_bin
    if ! shfmt_bin="$(toolchain_acquire shfmt)"; then
        log_error "shfmt is unusable, so formatting would not match the gate"
        log_info "Every lane's toolchain: .ci/scripts/lib/toolchain.sh --report"
        exit 1
    fi
    find .ci -name "*.sh" -type f -exec "$shfmt_bin" -i 4 -ci -w {} +
    "$shfmt_bin" -i 4 -ci -w ./run.sh
    for d in scripts/dev scripts/ops; do
        if [[ -d "$d" ]]; then
            find "$d" -name "*.sh" -type f -exec "$shfmt_bin" -i 4 -ci -w {} +
        fi
    done
    # log_info, not log_success: the latter is defined locally inside
    # .ci/scripts/security/shellcheck.sh and is NOT in the shared common.sh this
    # script sources, so the call died with "log_success: command not found"
    # after the formatting had already succeeded.
    log_info "Shell scripts formatted"
}

# =============================================================================
# SETUP
# =============================================================================

# Prepare this machine for development and hand back a URL.
#
# Idempotent by construction: every phase is guarded, so a second run installs
# nothing, pulls nothing and recreates nothing -- it just prints the URL again.
#
#   1. toolchain node/gcc/Go/gh/jq          (INSTALLED, not just checked)
#   2. account   git identity + credentials (asked once, then remembered)
#   3. docker    Go -> renet -> install-docker (skipped entirely if docker works)
#   4. image     pull the devcontainer image  (skipped if present)
#   5. devbox    one container per worktree; port from its path, hostname from its branch
#   6. report    the URL to open

# Report-only counterpart of setup(). Must never mutate anything: it is what an
# operator runs to find out why setup would do work, and what the CI gate drives.

# =============================================================================
# CLEAN
# =============================================================================

clean() {
    log_step "Cleaning build artifacts"
    rm -rf dist/
    rm -rf node_modules/.vite
    rm -rf packages/*/dist/
    log_info "Build artifacts cleaned"
}

# =============================================================================
# HELP
# =============================================================================

show_help() {
    cat <<EOF
Usage: ./run.sh [COMMAND] [OPTIONS]

SERVICE COMMANDS:
  service start [port] [--no-build]  Build and run rediacc/web (default port: 8080)
  service stop                    Stop service containers
  service status                  Show service status
  service logs [container]        Show logs (web, rustfs, all)

ACCOUNT COMMANDS:
  account dev              Start account dev gateway (API + portal + www on one port)
  account db               Browse the dev database (Drizzle Studio on account.db)
  account test             Run account integration tests (vitest)
  account test e2e [opts]  Run account E2E tests (playwright, with Stripe wiring)
  account stop             Stop account Docker containers
  account reset            Reset .env + database and regenerate
  account seed-demo        Seed a demo partner org end-to-end against the dev gateway (takes <email>)
  account totp [email]     Print the current 2FA code for a dev user (default dev-user@rediacc.io)

ROTATION COMMANDS (private/account/scripts/rotation/):
  rotation init            Bootstrap manifest from current platform state
  rotation list            Show every credential and its current state
  rotation check           Compare manifest to live state (exit 1 on drift)
  rotation rotate <slug>   Mint new credential; old transitions to grace
  rotation deactivate <s>  grace → inactive
  rotation delete <slug>   inactive → deleted (permanent)
  rotation sweep           Run deactivate + delete for everything eligible
  rotation history [<s>]   Show audit history

PROVISION COMMANDS:
  provision start            Provision KVM VMs (bridge + workers)
  provision stop             Destroy all VMs
  provision status           Show VM status

DEVELOPMENT COMMANDS:
  dev                 Start the www (marketing site) development server
  (rdc)               Use ./rdc.sh instead (standalone CLI runner)
  worktree <cmd>      Manage git worktrees (create, switch, prune, list)
  setup [--check]     Prepare this machine: INSTALL the toolchain (node, gcc, Go,
                      gh, jq), set the git identity and credentials, then docker,
                      the devcontainer image, and a browser VS Code for THIS
                      worktree. Idempotent -- a second run installs nothing.
  devbox <cmd>        up | status | url | stop | proxy | remove | shell | exec | doctor | logs

WWW COMMANDS:
  www all [opts]                    Full pipeline for tutorials + team videos

  www tutorials record [name]       Record .cast files inside the bridge VM (auto-provision, change-detected; keeps local ~/.config/rediacc clean)
  www tutorials extract             Sync cast markers to transcripts (preserves text)
  www tutorials scaffold-locales    Sync locale transcripts with English
  www tutorials generate [opts]     Generate TTS audio + timelines (Python venv)
  www tutorials video [name] [--lang <code>] [--jobs N] [--captions-only]  Compile .mp4 from cast+storyboard+timeline+audio
                                     (--jobs N runs N compiles concurrently, default 1; ffmpeg-bound,
                                     safe to raise on a multi-core box -- e.g. --jobs 6 on 20 cores)
                                     (--captions-only recovers scene timing analytically and re-emits
                                     just the vtt/chapters/words.json sidecars, skipping the ffmpeg
                                     re-encode entirely -- use after a --subtitle realignment when the
                                     mp4 itself hasn't changed. Falls back to a full render per-tutorial
                                     if a browser scene's silent-segment cache is cold.)
  www tutorials media [name] [--langs a,b] [--jobs N] [--subtitle] [--force]
                                    Narrate on the GPU and render on the CPU CONCURRENTLY:
                                    each language's videos start rendering as soon as its
                                    narration passes validation, while the next language is
                                    still being narrated. Generates and renders only; never
                                    restores from or uploads to R2.
  www tutorials watch [--jobs N] [--langs a,b] [--poll N] [--once] [--dry-run]
                                    Render each (tutorial, LANGUAGE) PAIR the moment that
                                    pair's narration is final, for narration running in
                                    another shell. Exits once nothing new is ready and no
                                    tutorial_tts.cli is left running. Single instance
                                    (flock on artifacts/tutorial-render-watch/watch.lock);
                                    logs to that same directory. Renders only: never
                                    narrates, never restores from or uploads to R2.
  www tutorials validate            Validate transcripts + audio integrity
  www tutorials all [opts]          Full tutorial pipeline (record -> extract -> generate -> video)


DRILL COMMANDS (scripted walkthroughs; non-zero exit on any failed assertion):
  drill universe      Config isolation, source labels, per-config tokens (headless)
  drill transfer      Config-storage battery vs ./run.sh account dev (headless)
  drill license       Live licensing battery on the ops VMs (declares its VM cost)
  drill backup        Live chunk-store battery: session mint, seed and incremental
                      upload, byte-identical restore, quota refusal (no VMs needed)
  drill <name> --selftest
                      Plant one failing assertion; the run MUST exit non-zero

QUALITY COMMANDS:
  quality lint        Run linting (ESLint + Knip)
  quality format      Check code formatting (Biome)
  quality types       Check TypeScript types
  quality submodules  Check submodule branch alignment
  quality deps        Check for outdated dependencies
  quality actions     Check that the pinned GitHub Actions are current
  quality suppressions  Check that allowlist entries are still needed
  quality dead-bash   Check for dead shell functions and orphaned scripts
  quality audit       Run security audit (npm audit)
  quality shell       Run shellcheck on shell scripts
  quality all         Run all quality checks

FIX COMMANDS:
  fix format          Auto-fix code formatting
  fix lint            Auto-fix linting issues
  fix shell           Auto-fix shell script formatting (shfmt)
  fix all             Auto-fix all issues

MAINTENANCE:
  clean               Clean build artifacts
  setup               Interactive setup: npm deps + native modules + git identity
  help                Show this help message

QUICK START:
  ./run.sh setup          # One-time setup
  ./run.sh dev            # Start www development
  ./rdc.sh subscription login # Run CLI command in dev mode

REQUIREMENTS:
  Node.js v${NODE_VERSION_REQUIRED}.x (https://nodejs.org/)
  Go (for CLI/renet development)
  Docker (for first-time renet asset extraction)

ENVIRONMENT:
  GITHUB_TOKEN        GitHub personal access token (for ghcr.io auth)
EOF
}

# =============================================================================
# MAIN DISPATCHER
# =============================================================================

main() {
    case "${1:-}" in
        # Service mode (rediacc/web + RustFS)
        service)
            shift
            case "${1:-}" in
                start)
                    shift
                    service_start "$@"
                    ;;
                stop) service_stop ;;
                status) service_status ;;
                logs)
                    shift
                    service_logs "$@"
                    ;;
                *)
                    log_error "Unknown service command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh service [start|stop|status|logs]"
                    exit 1
                    ;;
            esac
            ;;

        # `provision` and `www` are NOT here: both are media verbs and both are served
        # by the ROUTER (../../run.sh), which execs .ci/media/media-entry.sh directly.
        # They stayed there because .ci/rediacc_ci/tests/gates/test_gate_media_entry.py drives the
        # chain through a sandbox that copies run.sh and symlinks the rest of .ci -- a
        # media verb arriving here would step outside the sandbox it is being tested in.

        # Account server
        account)
            shift
            source "$ROOT_DIR/.ci/lib/account.sh"
            case "${1:-}" in
                dev) account_dev ;;
                db) account_db ;;
                test)
                    shift
                    case "${1:-}" in
                        e2e)
                            shift
                            account_test_e2e "$@"
                            ;;
                        *)
                            account_test "$@"
                            ;;
                    esac
                    ;;
                stop) account_stop ;;
                reset) account_reset ;;
                seed-demo)
                    shift
                    account_seed_demo "$@"
                    ;;
                totp)
                    shift
                    account_totp "$@"
                    ;;
                *)
                    log_error "Unknown account command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh account [dev|db|test|stop|reset|seed-demo|totp]"
                    exit 1
                    ;;
            esac
            ;;

        # Secret rotation (delegates to private/account/scripts/rotation/)
        rotation)
            shift
            source "$ROOT_DIR/.ci/lib/account.sh"
            account_rotation "$@"
            ;;

        # Development. `dev` is NOT here: it is served by `python3 -m rediacc_ci`
        # and named in the router's PORTED_VERBS table.
        worktree)
            shift
            "$ROOT_DIR/scripts/dev/worktree.sh" "$@"
            ;;
        devbox)
            shift
            # shellcheck source=/dev/null
            source "$ROOT_DIR/.ci/lib/devbox.sh"
            SCRIPT_ENTRYPOINT="$ROOT_DIR/run.sh" reexec_with_docker_group devbox "$@"
            case "${1:-status}" in
                # `up` forwards its remaining args so --no-rehost reaches devbox_up.
                # Without this the flag existed in the library and NOTHING could
                # pass it -- the drift banner advised DEVBOX_NO_REHOST=1 precisely
                # because the CLI form was unreachable.
                up)
                    shift
                    devbox_up false "${1:-}"
                    ;;
                status) devbox_status ;;
                # `url` prints the hostname URL and nothing else, so callers can
                # capture it. `worktree create` needs exactly this to show the URL
                # in its summary; parsing it back out of `status` would couple a
                # script to a human-facing layout.
                #
                # The optional suffix reaches the other routes -- `url term`,
                # `url account`, `url db` -- because a scriptable URL for one
                # service and a status-table scrape for the rest is the coupling
                # this subcommand exists to avoid.
                url)
                    shift
                    devbox_url "${1:-}"
                    ;;
                stop) devbox_stop ;;
                proxy)
                    shift
                    case "${1:-status}" in
                        up) devbox_proxy_ensure ;;
                        stop) devbox_proxy_stop ;;
                        status)
                            if devbox_proxy_running; then
                                log_info "Proxy running on :$DEVBOX_PROXY_PORT"
                            else
                                log_warn "Proxy is not running"
                                exit 1
                            fi
                            ;;
                        *)
                            log_error "Unknown devbox proxy command: $1"
                            exit 1
                            ;;
                    esac
                    ;;
                remove) devbox_remove ;;
                shell) devbox_shell ;;
                exec)
                    shift
                    [[ "${1:-}" == "--" ]] && shift
                    [[ $# -gt 0 ]] || {
                        log_error "devbox exec needs a command: ./run.sh devbox exec -- <cmd>"
                        exit 1
                    }
                    devbox_exec "$@"
                    ;;
                doctor) devbox_doctor ;;
                logs)
                    shift
                    devbox_logs "$@"
                    ;;
                *)
                    log_error "Unknown devbox command: $1"
                    log_info "Usage: ./run.sh devbox [up|status|url [term|account|db]|stop|proxy|remove|shell|exec|doctor|logs]"
                    exit 1
                    ;;
            esac
            ;;

        # Drills: the campaign's manual walkthroughs, scripted. Each one owns
        # its setup, numbered assertions and teardown, and exits non-zero on any
        # failed assertion. Dispatched by literal path (not "$1.sh") so
        # check-dead-bash.ts can see each file is referenced.
        drill)
            shift
            case "${1:-}" in
                universe)
                    shift
                    "$ROOT_DIR/scripts/drills/universe.sh" "$@"
                    ;;
                transfer)
                    shift
                    "$ROOT_DIR/scripts/drills/transfer.sh" "$@"
                    ;;
                license)
                    shift
                    "$ROOT_DIR/scripts/drills/license.sh" "$@"
                    ;;
                backup)
                    shift
                    "$ROOT_DIR/scripts/drills/backup.sh" "$@"
                    ;;
                *)
                    log_error "Unknown drill: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh drill [universe|transfer|license|backup] [--selftest]"
                    exit 1
                    ;;
            esac
            ;;

        # Quality
        quality)
            # ROUTED. The container's toolchain matches CI's and the host's
            # generally does not, so a quality run belongs in the lane that can
            # reach the same verdict CI will. Only GATE verbs route: setup,
            # devbox, provision, www and drill are host runtimes with host-
            # specific dependencies (KVM, GPU, ffmpeg, SSH keys that are
            # deliberately not bound into the container).
            # The lane probe talks to docker, so apply the group first -- without
            # it `devbox_container_running` reports "not running" for a container
            # that is running, and the routed lane silently degrades to the host.
            SCRIPT_ENTRYPOINT="$ROOT_DIR/run.sh" reexec_with_docker_group "$@"
            # Ask FIRST, then run. Collapsing these into one call is what let a
            # gate that failed in the devbox fall through and re-run on the
            # host, where a different toolchain could pass and hide it.
            # `|| _route=$?` is not style: this script runs under `set -euo
            # pipefail`, so a BARE call returning non-zero aborts the whole
            # script. The predicate returns 1 for the ordinary "stay on host"
            # case, so unguarded it killed every host-lane run silently -- the
            # trace ended at `return 1` with no output at all.
            _route=0
            gate_lane_should_route || _route=$?
            case "$_route" in
                0)
                    gate_lane_run "$@"
                    exit $?
                    ;;
                2) exit 2 ;; # unusable devbox: refuse, never degrade
            esac
            shift
            case "${1:-}" in
                lint) quality_lint ;;
                format) quality_format ;;
                types) quality_types ;;
                submodules) quality_submodules ;;
                deps) quality_deps ;;
                actions) quality_actions ;;
                suppressions) quality_suppressions ;;
                dead-bash) quality_dead_bash ;;
                audit) quality_audit ;;
                shell) quality_shell ;;
                all | "") quality_all ;;
                *)
                    log_error "Unknown quality command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh quality [lint|format|types|submodules|deps|actions|suppressions|dead-bash|audit|shell|all]"
                    exit 1
                    ;;
            esac
            ;;

        # Fix
        fix)
            shift
            case "${1:-}" in
                format) fix_format ;;
                lint) fix_lint ;;
                shell) fix_shell ;;
                all | "") fix_all ;;
                *)
                    log_error "Unknown fix command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh fix [format|lint|shell|all]"
                    exit 1
                    ;;
            esac
            ;;

        # Maintenance
        clean) clean ;;
        help | --help | -h | "") show_help ;;

        *)
            log_error "Unknown command: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# Execute main if run directly.
#
# An `if` block, not `[[ … ]] && main "$@"`. With the `&&` form the whole file's exit status is
# the FAILED test when the file is SOURCED, so `source ./run.sh` returned 1 and killed any
# caller running under `set -e` — silently, with no output, because nothing had failed. The
# `if` form returns 0 when sourced while still propagating main's real exit code when run
# directly.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
