#!/usr/bin/env bash
# Fetch credentials from Bitwarden Secrets Manager into the current shell.
#
# THIS IS THE PIECE THAT LETS private/account/.env SHRINK. Every plan for
# emptying that file has been blocked on the same absence: 19 of its 49 keys are
# already in Bitwarden and simply duplicated locally, but nothing could put a
# stored value into a local shell, so deleting a key broke `./run.sh account dev`,
# `scripts/dev/deploy-bench.sh`, `./rdc.sh --dev`, `private/renet/build.sh` and
# private/growth's publish pipeline. Sourcing this replaces that.
#
# USAGE
#   source .ci/lib/bws-env.sh
#   bws_env_load                      # every mapped name
#   bws_env_load ACCOUNT_JWT_SECRET   # only these
#
# WHAT IT WILL NOT DO, and each is deliberate:
#   * It never PRINTS a value. Names, counts and errors only -- this repo is
#     public and a shell trace is a log surface.
#   * It never writes a value to disk. No cache file, no temp env file. A cache
#     is a second copy with its own staleness and its own leak, and the whole
#     point of the migration is to stop having local copies.
#   * It never falls back to .env. A silent fallback is how a value that stopped
#     being fetched keeps working locally and fails in CI -- the shape this whole
#     programme exists to remove. Absent is an error, loudly.
#
# Resolution is by UUID through .ci/config/bws-secret-map.json, the same map
# .github/actions/bws-secrets uses, so local and CI resolve identically.

_bws_env_root() {
    local d="${BWS_ENV_ROOT:-}"
    [[ -n "$d" ]] && { printf '%s' "$d"; return; }
    d="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    printf '%s' "$d"
}

bws_env_load() {
    local root map bin want=("$@") rc=0
    root="$(_bws_env_root)"
    map="$root/.ci/config/bws-secret-map.json"

    if [[ -z "${BWS_ACCESS_TOKEN:-}" ]]; then
        echo "bws-env: BWS_ACCESS_TOKEN is not set." >&2
        echo "  It is the one credential that cannot come from Bitwarden -- no bws verb" >&2
        echo "  mints or rotates a machine-account token. Put it in private/account/.env." >&2
        return 1
    fi
    bin="${BWS_BIN:-$(command -v bws || true)}"
    if [[ -z "$bin" || ! -x "$bin" ]]; then
        echo "bws-env: the bws CLI is not on PATH (set BWS_BIN to point at it)." >&2
        echo "  The devcontainer installs it; see .devcontainer/Dockerfile." >&2
        return 1
    fi
    if [[ ! -f "$map" ]]; then
        echo "bws-env: $map is missing; nothing can be resolved by name." >&2
        return 1
    fi

    # `--color no` is load-bearing: bws 2.1.0 does not detect a non-tty and wraps
    # --output json in truecolor escapes, which no JSON parser survives.
    local listing
    listing="$("$bin" secret list --output json --color no 2>/dev/null)" || {
        echo "bws-env: bws secret list failed. If the token is expired this is what" >&2
        echo "  that looks like; see .ci/config/bws-token-expiry.json." >&2
        return 1
    }

    local exported=0 missing=()
    local names
    if [[ ${#want[@]} -gt 0 ]]; then
        names="$(printf '%s\n' "${want[@]}")"
    else
        names="$(python3 -c 'import json,sys; print("\n".join(sorted(json.load(open(sys.argv[1]))["secrets"])))' "$map")"
    fi

    local n val
    while IFS= read -r n; do
        [[ -n "$n" ]] || continue
        # Names only cross this boundary; the value goes straight into the shell.
        val="$(printf '%s' "$listing" | python3 -c '
import json, sys
rows = json.load(sys.stdin)
want = sys.argv[1]
for r in rows:
    if r.get("key") == want:
        sys.stdout.write(r.get("value") or "")
        break
' "$n")" || { missing+=("$n"); continue; }
        if [[ -z "$val" ]]; then
            missing+=("$n")
            continue
        fi
        export "$n=$val"
        exported=$((exported + 1))
    done <<<"$names"

    if [[ ${#missing[@]} -gt 0 ]]; then
        echo "bws-env: ${#missing[@]} name(s) absent or empty in the store: ${missing[*]}" >&2
        echo "  An empty value is treated as ABSENT on purpose: zod strips an unknown key and" >&2
        echo "  sm-action exports \"\" without complaint, so a blank ships a broken feature that" >&2
        echo "  still returns 200. Fix the store; do not fall back to a local copy." >&2
        rc=1
    fi
    echo "bws-env: exported $exported secret(s)" >&2
    return "$rc"
}
