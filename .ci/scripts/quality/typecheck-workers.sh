#!/bin/bash
# Typecheck every Cloudflare Worker under workers/, installing its deps first.
#
# WHY THIS EXISTS RATHER THAN MORE `tsc -p` CLAUSES IN package.json. Each worker is a
# SEPARATE npm project: its own package.json, its own lockfile, its own node_modules, and
# none of them is an npm workspace. Their tsconfigs all carry
# `types: ["@cloudflare/workers-types"]`, which tsc resolves from THAT project's
# node_modules and nowhere else -- there is no @cloudflare package at the repo root.
#
# So `tsc --noEmit -p workers/<x>/tsconfig.json` from a root script is green on a machine
# that happens to have run an install in that directory and red everywhere else with
#
#     error TS2688: Cannot find type definition file for '@cloudflare/workers-types'.
#
# That is exactly what happened: c044d6099 appended workers/www to the root typecheck
# chain, it passed here, and the CI job that runs `npm run typecheck` (Quality / Code)
# installs no worker deps at all. The clause could only ever have been green by accident.
# Reproduce in one command: `mv workers/www/node_modules /tmp && npx tsc --noEmit -p
# workers/www/tsconfig.json`.
#
# DISCOVERY, NOT A LIST. The workers are found on disk, so a fifth one is covered the day
# it is added rather than the day someone remembers this file. A run that discovers ZERO
# is a hard failure: a discovery gate that finds nothing has verified nothing.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

# A while-read loop rather than `mapfile`: check:ci-shell-commands rejects bash-4-only
# builtins, because the minimal CI images this repo targets do not all ship one.
CONFIGS=()
while IFS= read -r config; do
    CONFIGS+=("$config")
done < <(find workers -maxdepth 2 -name tsconfig.json -type f | sort)

if [ "${#CONFIGS[@]}" -eq 0 ]; then
    echo "typecheck-workers: found no workers/*/tsconfig.json. The layout moved, or this" >&2
    echo "  script is looking in the wrong place; either way a green here would be vacuous." >&2
    exit 1
fi

# --list prints the set this script would typecheck, one path per line, and does nothing
# else. scripts/check-typecheck-scope-coverage.ts calls it so the coverage gate reads the
# REAL set rather than re-implementing this discovery and drifting from it.
if [ "${1:-}" = "--list" ]; then
    printf '%s\n' "${CONFIGS[@]}"
    exit 0
fi

# --install stops once every worker project has its deps, without typechecking. knip needs
# exactly the same trees: with a worker's node_modules absent it cannot resolve `wrangler`
# and reports it as BOTH an unused devDependency and an unlisted binary. That is not a
# finding, it is the absence of an install -- and it shipped a CI red, because `lint:unused`
# runs BEFORE the TypeScript step that was incidentally producing those trees. A gate must
# not depend on an earlier step's side effect, so `lint:unused` asks for them itself.
INSTALL_ONLY=0
[ "${1:-}" = "--install" ] && INSTALL_ONLY=1

for config in "${CONFIGS[@]}"; do
    dir="$(dirname "$config")"

    if [ ! -d "$dir/node_modules" ]; then
        # `npm ci` when there is a lockfile to be exact about, `npm install` when there is
        # not. --ignore-scripts matches .npmrc's repo-wide setting; none of these workers
        # has a native dependency, so nothing needs `install:natives` afterwards.
        if [ -f "$dir/package-lock.json" ]; then
            echo "typecheck-workers: installing $dir (npm ci)"
            npm ci --prefix "$dir" --ignore-scripts >/dev/null
        else
            echo "typecheck-workers: installing $dir (npm install, no lockfile)"
            npm install --prefix "$dir" --ignore-scripts >/dev/null
        fi
    fi

    [ "$INSTALL_ONLY" -eq 1 ] && continue

    echo "typecheck-workers: $config"
    npx tsc --noEmit -p "$config"
done

if [ "$INSTALL_ONLY" -eq 1 ]; then
    echo "typecheck-workers: ${#CONFIGS[@]} worker project(s) have their deps"
    exit 0
fi

echo "typecheck-workers: ${#CONFIGS[@]} worker project(s) typechecked clean"
