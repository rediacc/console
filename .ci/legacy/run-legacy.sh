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
source "$ROOT_DIR/.ci/lib/setup.sh"

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
# DEVELOPMENT COMMANDS
# =============================================================================

dev() {
    check_node_version

    log_step "Starting www development server"

    # Same reasoning as setup(): ensure_deps carries the hash stamp, and its
    # mtime test here was a weaker duplicate of it.
    ensure_deps

    # Start dev server (marketing site)
    npm run dev -w @rediacc/www
}

# =============================================================================
# TEST COMMANDS
# =============================================================================

test_unit() {
    check_node_version
    ensure_packages_built
    log_step "Running unit tests"
    "$ROOT_DIR/.ci/scripts/test/run-unit.sh" "$@"
}

test_bridge() {
    check_node_version
    ensure_packages_built

    log_step "Running E2E tests"
    "$ROOT_DIR/.ci/scripts/test/run-e2e.sh" "$@"
}

test_all() {
    test_unit
}

# =============================================================================
# BUILD COMMANDS
# =============================================================================

build_cli() {
    check_node_version
    log_step "Building CLI application"
    "$ROOT_DIR/.ci/scripts/build/build-cli.sh"
}

build_packages() {
    check_node_version
    log_step "Building shared packages"
    "$ROOT_DIR/.ci/scripts/setup/build-packages.sh"
}

build_renet() {
    check_go_installed
    log_step "Building renet binary"
    local renet_dir="$ROOT_DIR/private/renet"
    (cd "$renet_dir" && ./go dev)

    if [[ ! -f "$renet_dir/bin/renet" ]]; then
        log_error "Renet build failed"
        exit 1
    fi

    log_info "Renet built: private/renet/bin/renet"
}

build_all() {
    check_node_version
    log_step "Building all components"
    build_packages
    build_cli
}

# =============================================================================
# PR COMMANDS
# =============================================================================

pr_publish() {
    check_node_version
    require_var CLOUDFLARE_API_TOKEN

    if ! command -v gh &>/dev/null; then
        log_error "GitHub CLI (gh) is not installed"
        log_info "Install from: https://cli.github.com/"
        exit 1
    fi

    # Auto-discover Cloudflare account ID from GitHub repo variables
    if [[ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]]; then
        log_step "Fetching CLOUDFLARE_ACCOUNT_ID from repo variables..."
        CLOUDFLARE_ACCOUNT_ID=$(gh variable get CLOUDFLARE_ACCOUNT_ID 2>/dev/null) || {
            log_error "Failed to fetch CLOUDFLARE_ACCOUNT_ID from repo variables"
            log_info "Set CLOUDFLARE_ACCOUNT_ID env var or check 'gh auth status'"
            exit 1
        }
        export CLOUDFLARE_ACCOUNT_ID
    fi

    log_step "Discovering PR number..."
    local pr_number
    pr_number=$(gh pr view --json number -q .number 2>/dev/null) || {
        log_error "No PR found for current branch"
        log_info "Push your branch and open a PR first"
        exit 1
    }
    log_info "PR #${pr_number} → https://pr-${pr_number}.rediacc.workers.dev"

    # Source private/account/.env for secrets and R2 credentials
    local account_env="$ROOT_DIR/private/account/.env"
    local env_vars=""
    if [[ -f "$account_env" ]]; then
        env_vars=$(set -a && source "$account_env" && set +a && env)
    fi
    _env() { echo "$env_vars" | grep "^$1=" | head -1 | cut -d= -f2-; }

    # Build shared packages
    log_step "Building shared packages..."
    build_packages

    # Build static sites (set PUBLIC_SITE_URL so install commands point to the preview)
    local preview_url="https://pr-${pr_number}.rediacc.workers.dev"

    log_step "Building www (marketing site)..."
    PUBLIC_SITE_URL="$preview_url" PUBLIC_REPO_CHANNEL="pr-${pr_number}" npm run build:www

    log_step "Building json (template catalog)..."
    npm run build:json

    # Build CLI binary (linux-x64) and upload to R2 channel via wrangler
    local cli_version
    cli_version=$(git describe --tags --match 'v*' --abbrev=0 2>/dev/null | sed 's/^v//' || echo "0.0.0-dev")
    local channel="pr-${pr_number}"

    log_step "Building CLI binary (linux-x64)..."
    "$ROOT_DIR/.ci/scripts/build/build-cli-executables.sh" --platform linux --arch x64

    log_step "Generating CLI manifest..."
    bash "$ROOT_DIR/.ci/scripts/build/generate-cli-manifest.sh" \
        --version "$cli_version" --input dist/cli/

    log_step "Uploading CLI binary to R2 (channel: ${channel})..."
    local r2_bucket="rediacc-releases"
    for f in dist/cli/rdc-*; do
        [[ -f "$f" ]] || continue
        local fname
        fname="$(basename "$f")"
        npx wrangler r2 object put "${r2_bucket}/cli/${channel}/${fname}" --file "$f" --content-type application/octet-stream --remote
    done
    if [[ -f "dist/cli/manifest.json" ]]; then
        npx wrangler r2 object put "${r2_bucket}/cli/${channel}/manifest.json" --file dist/cli/manifest.json --content-type application/json --remote
    fi
    echo "{\"version\":\"${cli_version}\"}" >/tmp/latest.json
    npx wrangler r2 object put "${r2_bucket}/cli/${channel}/latest.json" --file /tmp/latest.json --content-type application/json --remote
    rm -f /tmp/latest.json
    log_info "CLI binary uploaded to R2 channel: ${channel}"

    # Assemble pages into workers/www/dist/
    log_step "Assembling pages..."
    "$ROOT_DIR/.ci/scripts/build/build-pages.sh" --output dist/pages

    # Install script defaults (channel, server URL) are rewritten at runtime
    # by the worker based on the deployment hostname. No sed needed.

    # Build account portal
    log_step "Building account portal..."
    (cd "$ROOT_DIR/private/account/web" && npm install && npx vite build --outDir ../../../workers/www/dist/account)

    # Install www worker deps
    (cd "$ROOT_DIR/workers/www" && npm install)

    # Deploy
    log_step "Deploying pr-${pr_number}..."
    "$ROOT_DIR/.ci/scripts/deploy/deploy-www.sh" --name "pr-${pr_number}"

    # Set worker secrets from private/account/.env (secrets persist across deploys)
    local worker_name="pr-${pr_number}"
    if [[ -f "$account_env" ]] && [[ -n "$(_env ACCOUNT_ED25519_PRIVATE_KEY)" ]]; then
        log_step "Setting worker secrets for ${worker_name} (from private/account/.env)..."

        # ─── Non-empty guards, same shape as the deploy builders ─────────────
        # This block used to rely on `with_entries(select(.value != ""))` alone
        # to drop empties. That is the right treatment for a key that is
        # genuinely optional here, and exactly the WRONG one for a key that is
        # not: an unreadable name (a rename landed in one file and not the
        # other, a key never added to .env) yields "", the entry silently
        # disappears from the payload, `wrangler secret bulk` succeeds, and the
        # preview Worker keeps whatever it had -- or, on a fresh Worker, runs
        # with the feature turned off. Nothing in that chain says a name was
        # wrong. Measured 2026-09-02: STRIPE_SANDBOX_SECRET_KEY is NOT a key
        # `private/account/.env` has ever carried, so every local preview
        # shipped with no Stripe credential at all and reported success.
        #
        # So this demands, by name, every key the deploy builders demand with
        # `_require_nonempty` plus the six env.ts declares non-optional. Each
        # entry is `<.env key>:<Worker key>` -- they differ only where the
        # preview deliberately fills a role with a different credential (see
        # the Stripe note below), and printing both is what makes a failure
        # actionable.
        local _required=(
            ACCOUNT_ED25519_PRIVATE_KEY:ACCOUNT_ED25519_PRIVATE_KEY
            ACCOUNT_ED25519_PUBLIC_KEY:ACCOUNT_ED25519_PUBLIC_KEY
            ACCOUNT_X25519_PRIVATE_KEY:ACCOUNT_X25519_PRIVATE_KEY
            ACCOUNT_X25519_PUBLIC_KEY:ACCOUNT_X25519_PUBLIC_KEY
            ACCOUNT_SERVER_API_KEY:ACCOUNT_SERVER_API_KEY
            ACCOUNT_JWT_SECRET:ACCOUNT_JWT_SECRET
            ROOT_EMAIL:ROOT_EMAIL
            AWS_SES_ACCESS_KEY_ID:AWS_SES_ACCESS_KEY_ID
            AWS_SES_SECRET_ACCESS_KEY:AWS_SES_SECRET_ACCESS_KEY
            AWS_SES_REGION:AWS_SES_REGION
            CLOUDFLARE_TURNSTILE_SECRET_KEY:CLOUDFLARE_TURNSTILE_SECRET_KEY
            STRIPE_SANDBOX_SECRET_KEY:STRIPE_SECRET_KEY
            STRIPE_E2E_WEBHOOK_SECRET:STRIPE_WEBHOOK_SECRET
        )
        local _missing=() _pair _envkey _workerkey
        for _pair in "${_required[@]}"; do
            _envkey="${_pair%%:*}"
            _workerkey="${_pair##*:}"
            if [[ -z "$(_env "$_envkey")" ]]; then
                if [[ "$_envkey" == "$_workerkey" ]]; then
                    _missing+=("$_envkey")
                else
                    _missing+=("$_envkey (worker key $_workerkey)")
                fi
            fi
        done
        if ((${#_missing[@]})); then
            log_error "private/account/.env is missing worker secret(s) the preview needs:"
            for _pair in "${_missing[@]}"; do log_error "    $_pair"; done
            log_error "  Pushing a preview without these does not fail -- the empty entry is"
            log_error "  dropped and the Worker silently runs without the feature, so this"
            log_error "  refuses instead. Add the key(s) to private/account/.env; './run.sh"
            log_error "  account reset' regenerates the six ACCOUNT_* ones."
            return 1
        fi

        # Build secrets JSON. AWS_SES_FROM / AWS_SES_CONFIGURATION_SET are the
        # only two left unguarded -- both are optional() in env.ts and neither
        # turns a feature off by its absence -- so the `with_entries` filter
        # below now drops nothing else.
        #
        # THE ONE REMAINING NAME-CROSSING, and it is deliberate: the .env key
        # STRIPE_SANDBOX_SECRET_KEY fills the Worker's STRIPE_SECRET_KEY. A
        # preview is a sandbox deployment, and app.ts reads STRIPE_SECRET_KEY
        # for the ordinary billing path (STRIPE_SANDBOX_SECRET_KEY is a
        # separate, additional binding), so a preview that wants working
        # billing must receive the sandbox key in the live key's slot. CI does
        # exactly the same thing at ci.yml's set-preview-worker-secrets step.
        jq -n \
            --arg ed25519_priv "$(_env ACCOUNT_ED25519_PRIVATE_KEY)" \
            --arg ed25519_pub "$(_env ACCOUNT_ED25519_PUBLIC_KEY)" \
            --arg x25519_priv "$(_env ACCOUNT_X25519_PRIVATE_KEY)" \
            --arg x25519_pub "$(_env ACCOUNT_X25519_PUBLIC_KEY)" \
            --arg api_key "$(_env ACCOUNT_SERVER_API_KEY)" \
            --arg jwt "$(_env ACCOUNT_JWT_SECRET)" \
            --arg stripe "$(_env STRIPE_SANDBOX_SECRET_KEY)" \
            --arg stripe_wh "$(_env STRIPE_E2E_WEBHOOK_SECRET)" \
            --arg admin "$(_env ROOT_EMAIL)" \
            --arg ses_key "$(_env AWS_SES_ACCESS_KEY_ID)" \
            --arg ses_secret "$(_env AWS_SES_SECRET_ACCESS_KEY)" \
            --arg ses_region "$(_env AWS_SES_REGION)" \
            --arg ses_from "$(_env AWS_SES_FROM)" \
            --arg ses_cs "$(_env AWS_SES_CONFIGURATION_SET)" \
            --arg turnstile "$(_env CLOUDFLARE_TURNSTILE_SECRET_KEY)" \
            '{
              ACCOUNT_ED25519_PRIVATE_KEY: $ed25519_priv,
              ACCOUNT_ED25519_PUBLIC_KEY: $ed25519_pub,
              ACCOUNT_X25519_PRIVATE_KEY: $x25519_priv,
              ACCOUNT_X25519_PUBLIC_KEY: $x25519_pub,
              ACCOUNT_SERVER_API_KEY: $api_key,
              ACCOUNT_JWT_SECRET: $jwt,
              STRIPE_SECRET_KEY: $stripe,
              STRIPE_WEBHOOK_SECRET: $stripe_wh,
              ROOT_EMAIL: $admin,
              AWS_SES_ACCESS_KEY_ID: $ses_key,
              AWS_SES_SECRET_ACCESS_KEY: $ses_secret,
              AWS_SES_REGION: $ses_region,
              AWS_SES_FROM: $ses_from,
              AWS_SES_CONFIGURATION_SET: $ses_cs,
              CLOUDFLARE_TURNSTILE_SECRET_KEY: $turnstile
            } | with_entries(select(.value != ""))' | npx wrangler secret bulk --name "$worker_name"

        log_info "Secrets set for ${worker_name}"
    else
        log_warn "Skipping secrets (private/account/.env missing or empty)"
        log_info "Secrets persist across deploys. Run './run.sh account reset' to generate .env."
    fi

    log_info "Published to https://pr-${pr_number}.rediacc.workers.dev"
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
    npx tsx "$ROOT_DIR/scripts/check-actions.ts"
}

quality_dead_bash() {
    check_node_version
    log_step "Checking for dead shell functions and orphaned scripts..."
    npx tsx "$ROOT_DIR/scripts/check-dead-bash.ts"
}

quality_suppressions() {
    check_node_version
    log_step "Checking suppression liveness (are allowlist entries still needed?)..."
    npx tsx "$ROOT_DIR/scripts/check-suppression-liveness.ts"
}

quality_audit() {
    check_node_version
    "$ROOT_DIR/.ci/scripts/security/audit.sh"
}

quality_shell() {
    "$ROOT_DIR/.ci/scripts/security/shellcheck.sh"
    "$ROOT_DIR/.ci/scripts/security/shfmt.sh"
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
    if [[ -d "scripts/dev" ]]; then
        find scripts/dev -name "*.sh" -type f -exec "$shfmt_bin" -i 4 -ci -w {} +
    fi
    # log_info, not log_success: the latter is defined locally inside
    # .ci/scripts/security/shellcheck.sh and is NOT in the shared common.sh this
    # script sources, so the call died with "log_success: command not found"
    # after the formatting had already succeeded.
    log_info "Shell scripts formatted"
}

# =============================================================================
# CHECK COMMANDS (PRE-PUSH VALIDATION)
# =============================================================================

check_quick() {
    check_node_version
    log_step "Running quick checks"
    npm run check:lint || exit 1
    npm run check:format || exit 1
    npm run typecheck || exit 1
    log_info "Quick checks passed!"
}

check_full() {
    check_node_version
    log_step "Running full validation"

    log_step "Phase 1/3: Quality Checks"
    quality_all || exit 1

    log_step "Phase 2/3: Security Audit"
    quality_audit || exit 1

    log_step "Phase 3/3: Unit Tests"
    test_unit || exit 1

    log_info "Full validation passed!"
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
setup() {
    local do_check=false force_pull=false do_start=true

    # Make docker usable in THIS run if the group was added but not activated.
    SCRIPT_ENTRYPOINT="$ROOT_DIR/run.sh" reexec_with_docker_group setup "$@"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --check)
                do_check=true
                shift
                ;;
            --pull)
                force_pull=true
                shift
                ;;
            --no-start)
                do_start=false
                shift
                ;;
            --help | -h)
                cat <<'EOF'
Usage: ./run.sh setup [OPTIONS]

  --check      Report what is missing and change nothing
  --pull       Re-pull the devcontainer image even if present
  --no-start   Prepare the host and image, but do not create the container
  --help       Show this help

Related: ./run.sh devbox [up|status|stop|remove|shell|logs]
EOF
                return 0
                ;;
            *)
                log_error "Unknown option for setup: $1"
                return 2
                ;;
        esac
    done

    # shellcheck source=/dev/null
    source "$ROOT_DIR/.ci/lib/devbox.sh"

    if [[ "$do_check" == true ]]; then
        setup_check
        return $?
    fi

    log_step "Rediacc console setup"
    echo ""

    # TOOLCHAIN, AND IT IS ALLOWED TO INSTALL. Two waves wrote this function on
    # the same day and the rebase offered them as either/or, which they are not:
    # 0826-2 built the devcontainer flow whose step 1 CHECKED for tooling and
    # never installed it, and 0826-3 built the installers because a bare machine
    # stopped at that check with a bare report. The check was the gap; these are
    # what fills it.
    setup_node_toolchain || return 1
    # NO `:-22.0.0` DEFAULT ANY MORE. The fallback did not make this line more
    # robust, it made a real failure invisible: it fired precisely when
    # .ci/config/constants.sh had NOT been sourced, and then let setup pass a
    # machine on Node 22.4 that the repo's own engines.node (">=22.13.0")
    # rejects. The operator would see a green setup and a failure later, inside
    # npm, naming neither this file nor the floor. `:?` turns that same
    # condition into one loud line naming the missing variable.
    check_node_version "${NODE_VERSION_MIN:?constants.sh was not sourced, so the Node floor is unknown}" || return 1
    echo ""

    # Before npm install: install:natives hard-requires a compiler.
    setup_system_tools || return 1
    echo ""

    # Submodules BEFORE the first phase that READS one, and the merge moved
    # which phase that is. 0826-2 put this immediately before the docker phase,
    # correctly, because that phase read private/renet/go.mod. 0826-3's
    # setup_go_toolchain reads the SAME file and now runs earlier, so leaving
    # the init where it was would resurrect the exact failure the comment below
    # describes -- on a fresh clone, "Cannot determine the required Go version",
    # a message that never mentions submodules. check:ci-setup-idempotency
    # caught this ordering, which is the whole reason that gate exists.
    #
    # Best-effort (`|| true`) for the same reason devcontainer.json is: a
    # developer without access to every private submodule should still get a
    # working devbox.
    if [[ -f "$ROOT_DIR/.gitmodules" ]]; then
        log_step "Initializing submodules"
        bash "$ROOT_DIR/.devcontainer/init-submodules.sh" --quiet || true
        echo ""
    fi

    # Mandatory: ./rdc.sh rebuilds renet from source and stops dead without Go.
    setup_go_toolchain || return 1
    echo ""

    # Mandatory: the PR guards fail closed without gh.
    setup_gh_cli || return 1
    echo ""

    # KEPT, not replaced. ensure_host_tools also checks zstd, curl and git,
    # which none of the installers above cover, so deleting it would quietly
    # narrow the preflight while looking like a simplification. After the
    # installers it should pass; if it does not, it names what is still missing.
    ensure_host_tools || return 1
    ensure_bashcov_sup
    echo ""

    log_step "Git and GitHub account"
    setup_git_identity
    setup_git_credentials || return 1
    echo ""

    # Dependencies THROUGH ensure_deps, never a raw npm install: it hashes
    # package.json, package-lock.json and .npmrc and skips on a match, so a
    # second setup does not recompile cpu-features through node-gyp for nothing.
    ensure_deps

    # Credential-drift REPORT, advisory and never fatal. The bench equivalent in
    # scripts/dev/deploy-bench.sh blocks and is right to -- it guards a DEPLOY.
    # Setup ships nothing, and blocking a developer's bootstrap on a credential
    # only an ops owner can rotate strands the one person who cannot fix it.
    # Reported at all because nothing else reports it: a rotated-out SES key sat
    # in private/account/.env until the stop hook's operator email began 403ing
    # days later, with the symptom several steps removed from the cause. That
    # consumer has since been removed; the exposure has not, because run.sh
    # itself pushes the same quartet into the account worker's secrets.
    #
    # It compares IDENTIFIERS against rotation-manifest.json, never secrets, and
    # never contacts a provider: liveness is `rotation check`'s job and needs
    # admin credentials. Skips loudly when the private submodule is absent.
    if [[ "${SKIP_ENV_DRIFT_CHECK:-}" != "1" ]] && [[ -f "$ROOT_DIR/private/account/.env" ]]; then
        echo ""
        log_step "Credential drift check"
        if ! npm run --silent check:env-credential-drift; then
            log_warn "A credential in private/account/.env is not in the rotation manifest."
            log_warn "ROTATION IS AN OPS TASK, NOT A DEVELOPER ONE, so this does not stop setup."
            log_warn "It surfaces later as an unrelated failure (a 403 from an API days on),"
            log_warn "and the developer who hits that is not the person who can fix it."
            log_warn "Whoever owns rotation: ./run.sh rotation rotate <slug>"
        fi
    fi

    if ! ensure_docker_installed; then
        log_error "Docker could not be prepared; cannot continue"
        return 1
    fi

    if ! devbox_ensure_image "$force_pull"; then
        log_error "Could not obtain $DEVBOX_IMAGE"
        return 1
    fi

    if [[ "$do_start" != true ]]; then
        log_info "Host prepared. Create the container with: ./run.sh devbox up"
        return 0
    fi

    devbox_up || return 1

    # THE URLS ARE THE DELIVERABLE. devbox_up has already printed the probed
    # route table, so these two lines are the bookmark, not the report: the pair
    # a person actually needs after a fresh machine setup. Terminal is named
    # explicitly because it is new and nothing else would tell anyone it exists.
    echo ""
    log_info "Setup complete."
    log_info "  VS Code:  $(devbox_url)"
    log_info "  Terminal: $(devbox_url term)   tmux in the browser"
    echo ""
    log_info "Everything below runs INSIDE the devbox:"
    log_info "  ./run.sh account dev    start the account dev stack"
    log_info "  ./run.sh account db     browse the dev database"
    log_info "  ./run.sh devbox shell   a shell in the container"
    return 0
}

# Report-only counterpart of setup(). Must never mutate anything: it is what an
# operator runs to find out why setup would do work, and what the CI gate drives.
setup_check() {
    local pending=0

    log_step "Setup status for $(devbox_worktree)"
    echo ""

    if command -v node &>/dev/null; then
        printf '  node        %s\n' "$(node --version)"
    else
        printf '  node        MISSING (install Node >= %s)\n' "$NODE_VERSION_MIN"
        pending=$((pending + 1))
    fi

    if command -v go &>/dev/null; then
        printf '  go          %s\n' "$(go version | awk '{print $3}')"
    else
        printf '  go          absent (setup installs it only if docker is missing)\n'
    fi

    # THE PHASES THE MERGE ADDED TO setup() MUST ALSO BE REPORTED HERE. This
    # function's whole contract is to be the report-only counterpart -- what an
    # operator runs to find out why setup would do work -- so a phase that setup
    # performs and check does not mention makes the count a lie. Caught by
    # running `--check` after merging the two waves' setup(): it said "2 item(s)
    # would be acted on" while setup would also have installed gh and written a
    # git identity.
    if command -v gh &>/dev/null; then
        printf '  gh          %s\n' "$(gh --version | head -1 | awk '{print $3}')"
    else
        printf '  gh          MISSING (setup installs it; the PR guards fail closed without it)\n'
        pending=$((pending + 1))
    fi

    if command -v cc &>/dev/null || command -v gcc &>/dev/null; then
        printf '  compiler    %s\n' "$( (cc --version 2>/dev/null || gcc --version) | head -1 | awk '{print $1, $NF}')"
    else
        printf '  compiler    MISSING (setup installs build-essential; install:natives needs it)\n'
        pending=$((pending + 1))
    fi

    if [[ -n "$(git config --global user.email 2>/dev/null)" ]]; then
        printf '  git identity %s\n' "$(git config --global user.email)"
    else
        printf '  git identity UNSET (setup asks for it once, then remembers)\n'
        pending=$((pending + 1))
    fi

    if docker version &>/dev/null; then
        printf '  docker      %s\n' "$(docker --version | sed 's/,.*//')"
    elif command -v docker &>/dev/null; then
        printf '  docker      installed but NOT usable as %s (log out/in, or newgrp docker)\n' "$USER"
        pending=$((pending + 1))
    else
        printf '  docker      MISSING (setup installs it via renet install-docker --source=docker-repo)\n'
        pending=$((pending + 1))
    fi

    if devbox_image_present; then
        printf '  image       present (%s)\n' "$DEVBOX_IMAGE"
    else
        printf '  image       MISSING (%s)\n' "$DEVBOX_IMAGE"
        pending=$((pending + 1))
    fi

    # THE '?' FALLBACK WAS A LANDMINE. run.sh is `set -euo pipefail`, and
    # $(('?' + N)) is an arithmetic syntax error ("operand expected"), so the
    # printf never ran and setup_check ABORTED. The visible symptom would have
    # been check-setup-idempotency failing with "setup --check never mentioned
    # 'port block'" -- a gate failure naming the wrong cause entirely. It is
    # unreachable today only because find_port_block walks all 100 slots before
    # giving up, which is luck, not design.
    local base_port
    base_port="$(devbox_base_port 2>/dev/null || echo '')"
    if [[ "$base_port" =~ ^[0-9]+$ ]]; then
        printf '  port block  %s-%s\n' "$base_port" "$((base_port + DEVBOX_PORT_BLOCK - 1))"
    else
        printf '  port block  unavailable (no free block in %s-%s)\n' \
            "$DEVBOX_PORT_RANGE_START" "$DEVBOX_PORT_RANGE_END"
    fi

    if devbox_container_running; then
        printf '  devbox      running (%s)\n' "$(devbox_container_name)"
    elif [[ -n "$(devbox_container_id 2>/dev/null)" ]]; then
        printf '  devbox      stopped (%s)\n' "$(devbox_container_name)"
        pending=$((pending + 1))
    else
        printf '  devbox      not created\n'
        pending=$((pending + 1))
    fi

    echo ""
    if [[ "$pending" -eq 0 ]]; then
        log_info "Nothing to do; ./run.sh setup would be a no-op"
        devbox_status
        return 0
    fi
    log_warn "$pending item(s) would be acted on by ./run.sh setup"
    return 1
}

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


TEST COMMANDS:
  test unit           Run unit tests
  test bridge [opts]  Run bridge tests (requires VMs)
  test all            Run all tests

DRILL COMMANDS (scripted walkthroughs; non-zero exit on any failed assertion):
  drill universe      Config isolation, source labels, per-config tokens (headless)
  drill transfer      Config-storage battery vs ./run.sh account dev (headless)
  drill license       Live licensing battery on the ops VMs (declares its VM cost)
  drill backup        Live chunk-store battery: session mint, seed and incremental
                      upload, byte-identical restore, quota refusal (no VMs needed)
  drill <name> --selftest
                      Plant one failing assertion; the run MUST exit non-zero

BUILD COMMANDS:
  build cli           Build CLI application
  build renet         Build renet binary (Go, with embedded assets)
  build packages      Build shared packages
  build all           Build everything

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

PR COMMANDS:
  pr publish          Build and deploy to PR preview (pr-N.rediacc.workers.dev)
                      Auto-discovers PR number and Cloudflare account ID via gh CLI.
                      Sets worker secrets from private/account/.env if present.
                      Requires: CLOUDFLARE_API_TOKEN

CHECK COMMANDS (PRE-PUSH):
  check quick         Fast checks (lint, format, types)
  check full          Full validation (quality + audit + tests)

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
        # They stayed there because .ci/scripts/test/gates/test-media-entry.sh drives the
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

        # Development
        dev) dev ;;
        worktree)
            shift
            "$ROOT_DIR/scripts/dev/worktree.sh" "$@"
            ;;
        setup)
            shift
            setup "$@"
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

        # Tests
        test)
            shift
            case "${1:-}" in
                unit)
                    shift
                    test_unit "$@"
                    ;;
                bridge)
                    shift
                    test_bridge "$@"
                    ;;
                all) test_all ;;
                *)
                    log_error "Unknown test command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh test [unit|bridge|all]"
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

        # Build
        build)
            shift
            case "${1:-}" in
                cli) build_cli ;;
                renet) build_renet ;;
                packages) build_packages ;;
                all | "") build_all ;;
                *)
                    log_error "Unknown build command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh build [cli|renet|packages|all]"
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

        # Check
        check)
            shift
            case "${1:-}" in
                quick) check_quick ;;
                full) check_full ;;
                *)
                    log_error "Unknown check command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh check [quick|full]"
                    exit 1
                    ;;
            esac
            ;;

        # PR commands
        pr)
            shift
            case "${1:-}" in
                publish) pr_publish ;;
                *)
                    log_error "Unknown pr command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh pr [publish]"
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
