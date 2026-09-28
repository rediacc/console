#!/usr/bin/env bash
# Waits until a freshly minted installation token can read every repository it was scoped to, so a submodule checkout never races the token.
#
# Usage: probe-repos.sh <owner> <repo>[,<repo>...]
#
# Probes each repository with `git ls-remote https://github.com/<owner>/<repo>.git HEAD`, which is the same git transport and the same global url.insteadOf credential the later `git submodule update` uses, and retries a failing one on a bounded backoff of 1+2+4+8+15+15+15 = 60 seconds.
# A repository still unreadable when the schedule runs out fails the step with its name and git's last error line, so the job reds here rather than as a bare "repository not found" inside actions/checkout.
#
# Why it exists: E2E Workers jobs 108876231507 (run 36406096086) and 109010480668 (run 36445908686) minted a token scoped to console,renet,account,elite,homebrew-tap, then cloned elite, homebrew-tap and renet with it while account answered "Repository not found" twice, 1-6 seconds after the mint.
# The same token reading three sibling private repositories rules out a missing credential, a wrong scope list and a rate limit, which leaves the grant for one repository not yet visible on the git frontend.
set -uo pipefail

owner="${1:-}"
repos_csv="${2:-}"
if [[ -z "$owner" ]]; then
    echo "::error::probe-repos.sh: owner argument is empty"
    exit 2
fi

repos=()
IFS=',' read -r -a raw <<<"$repos_csv"
for r in "${raw[@]}"; do
    r="$(echo "$r" | xargs)"
    [[ -n "$r" ]] && repos+=("$r")
done
if ((${#repos[@]} == 0)); then
    echo "::notice::app-token: no repositories input, so there is no named set to probe; the token covers every repository of the installation."
    exit 0
fi

delays=(1 2 4 8 15 15 15)
export GIT_TERMINAL_PROMPT=0

failed=()
for repo in "${repos[@]}"; do
    url="https://github.com/${owner}/${repo}.git"
    attempt=1
    last_err=""
    while :; do
        if err="$(timeout 30 git ls-remote "$url" HEAD 2>&1 >/dev/null)"; then
            if ((attempt > 1)); then
                echo "::warning::app-token: ${owner}/${repo} became readable on attempt ${attempt}; the token was not yet valid for it right after the mint."
            else
                echo "app-token: ${owner}/${repo} readable"
            fi
            break
        fi
        last_err="$(printf '%s\n' "$err" | grep -v '^[[:space:]]*$' | tail -n 1)"
        if ((attempt > ${#delays[@]})); then
            echo "::error::app-token: ${owner}/${repo} still unreadable with the minted token after ${attempt} attempts over 60s: ${last_err}"
            failed+=("$repo")
            break
        fi
        d="${delays[attempt - 1]}"
        echo "app-token: ${owner}/${repo} not readable yet (attempt ${attempt}: ${last_err}); retrying in ${d}s"
        sleep "$d"
        attempt=$((attempt + 1))
    done
done

if ((${#failed[@]} > 0)); then
    echo "::error::app-token: the minted token cannot read: ${failed[*]}"
    exit 1
fi
