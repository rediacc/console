#!/bin/bash
# Preflights for scripts/ops/deploy-bench.sh, run BEFORE the first remote write.
#
# WHY THIS EXISTS. On 2026-09-24 a bench deploy applied 21 D1 migrations and
# THEN failed: wrangler.bench.toml binds R2 bucket rediacc-backups-bench, which
# nothing had created. Bench was left serving its old worker on a newer schema.
# The next attempt bundled from a drifted node_modules (packages/shared and
# workers/account resolving zod 3.25.76 against a lockfile that pins 4.x), and
# Cloudflare refused the worker at startup ("uuid is not a function"). Both
# are knowable before anything remote changes, so both are checked here.
#
# Sourced, not executed; driven by .ci/rediacc_ci/tests/test_bench_preflight.py.

# bench_preflight_lockfile <dir>...
#   Refuse when `npm ls --all` reports the install in any <dir> out of line
#   with its package-lock.json (invalid, missing or extraneous packages).
bench_preflight_lockfile() {
    local dir
    for dir in "$@"; do
        if ! (cd "$dir" && npm ls --all >/dev/null 2>&1); then
            echo "✗ node_modules in ${dir} does not match its package-lock.json (npm ls --all fails)" >&2
            echo "✗ a bundle built from it can pass locally and be refused by Cloudflare; fix: npm ci && npm run install:natives" >&2
            return 1
        fi
    done
}

# bench_preflight_buckets <wrangler-config>
#   Create every R2 bucket the config binds that does not exist yet. A binding
#   that names a jurisdiction is refused rather than guessed: creating it in the
#   default jurisdiction would put the data somewhere the config did not ask for.
bench_preflight_buckets() {
    local config="$1" existing bucket
    if grep -qE '^[[:space:]]*jurisdiction[[:space:]]*=' "$config"; then
        echo "✗ ${config} binds a jurisdictional R2 bucket; create it by hand with --jurisdiction, then rerun" >&2
        return 1
    fi
    existing=$(npx wrangler r2 bucket list 2>/dev/null | awk '/^name:/{print $2}') || return 1
    while IFS= read -r bucket; do
        [[ -n "$bucket" ]] || continue
        if ! grep -qxF "$bucket" <<<"$existing"; then
            echo "→ creating R2 bucket ${bucket} (bound in ${config}, absent)"
            npx wrangler r2 bucket create "$bucket" >/dev/null || return 1
        fi
    done < <(sed -nE 's/^[[:space:]]*bucket_name[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/p' "$config")
}
