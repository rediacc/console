#!/bin/bash
# ---- gate ----
# step: www build token
# needs: none
# lane: quality-code
# why: every www build must pass github.token. Found and fixed by hand at two of
#      three call sites, twice, before the third reddened job 99839065246
# ---- end gate ----

# Every www build in CI must pass GITHUB_TOKEN. All of them, not most of them.
#
# THE DEFECT, twice. `packages/www/src/pages/[lang]/downloads.astro` fetches the latest
# release from the GitHub API at BUILD time and deliberately THROWS rather than shipping a
# downloads page with nothing on it. Unauthenticated, that call is capped at 60/hour per
# runner IP -- which is SHARED -- so the build dies with
#
#     latest-release: GitHub responded 403 rate limit exceeded
#
# for reasons that have nothing to do with the commit under test.
# `packages/www/src/utils/latest-release.ts:20-22` already sends the token as a Bearer
# header the moment it is set, and downloads.astro:35 prints "Set GITHUB_TOKEN if this is
# rate limiting" in the very error that fails the build. The fix is one line of `env:`.
#
# WHY A GATE AND NOT A THIRD CAREFUL COMMENT. It was found and fixed twice, at
# ci-quality.yml and cd-deploy-worker.yml, each time with a thorough comment naming run
# 32223128728 -- and the THIRD call site, ci-build-docker.yml, was left behind both times
# and reddened job 99839065246 months later. Two prose comments did not find the third
# site. A rule that enumerates them does.
#
# THE GENERAL SHAPE, and this repo hit it twice in one day: a fix applied at two of three
# call sites is a fix with a live hole. The nfpm checksum was the same story that morning
# (ci.yml verified before extracting; two siblings piped straight into tar).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$REPO_ROOT"

WORKFLOWS="${1:-.github/workflows}"

# The three spellings a www build wears. Kept as a list because a fourth spelling is how
# a fourth call site would arrive unnoticed.
find_sites() {
    grep -rnE 'build-www\.sh|npm run build:www|npm run build -w @rediacc/www' "$1"/*.yml 2>/dev/null |
        grep -v '^\s*#' | grep -vE ':[0-9]+: *#'
}

# A call site is covered when GITHUB_TOKEN appears in the 25 lines after it -- the env
# block belongs to that step, and no step in this repo is longer than that between `run:`
# and the end of its `env:`.
covered() {
    local file="$1" line="$2"
    sed -n "${line},$((line + 25))p" "$file" | grep -q 'GITHUB_TOKEN:'
}

audit() {
    local dir="$1" bad=0 total=0 hit file line
    while IFS= read -r hit; do
        [ -n "$hit" ] || continue
        file="${hit%%:*}"
        line="$(cut -d: -f2 <<<"$hit")"
        total=$((total + 1))
        if ! covered "$file" "$line"; then
            echo "  MISSING  $file:$line builds www without GITHUB_TOKEN"
            bad=$((bad + 1))
        fi
    done < <(find_sites "$dir")
    echo "__TOTAL__=$total __BAD__=$bad"
}

# -- CONTROL, before the real run. A gate that cannot fire is worse than no gate. --------
CTL="$(mktemp -d)"
trap 'rm -rf "$CTL"' EXIT
mkdir -p "$CTL/wf"
printf 'jobs:\n  a:\n    steps:\n      - run: npm run build:www\n        env:\n          APP_VERSION: x\n' >"$CTL/wf/bad.yml"
printf 'jobs:\n  b:\n    steps:\n      - run: npm run build:www\n        env:\n          GITHUB_TOKEN: t\n' >"$CTL/wf/good.yml"

# THE FIXTURES MUST ACTUALLY DIFFER in the property under test. Without this the
# control is satisfied by two identical files, or by a write that silently did not
# land -- and a no-op plant looks exactly like a passing control. check:ci-control-vacuity
# exists because that has happened here before.
grep -q 'GITHUB_TOKEN:' "$CTL/wf/good.yml" ||
    {
        echo "CONTROL COULD NOT PLANT: good.yml has no token, so the pair proves nothing" >&2
        exit 1
    }
grep -q 'GITHUB_TOKEN:' "$CTL/wf/bad.yml" &&
    {
        echo "CONTROL COULD NOT PLANT: bad.yml HAS a token, so the pair proves nothing" >&2
        exit 1
    }

ctl="$(audit "$CTL/wf")"
grep -q 'bad.yml:4 builds www without GITHUB_TOKEN' <<<"$ctl" || {
    echo "CONTROL DID NOT FIRE: a call site with no token was not reported" >&2
    exit 1
}
grep -q 'good.yml' <<<"$ctl" && {
    echo "CONTROL OVER-FIRED: a call site WITH the token was reported" >&2
    exit 1
}
echo "✓ controls: an untokened call site is reported, a tokened one is not"

# -- The real tree -----------------------------------------------------------------------
out="$(audit "$WORKFLOWS")"
# Parameter expansion, not `sed 's/…/…/'`: check:ci-control-vacuity classifies any
# inline substitution as a control built by mutation and then -- correctly, since it
# cannot tell output-parsing from fixture-building -- demands proof the plant landed.
# Not gaming that detector by adding a matching phrase; removing the construct it reads.
summary="${out##*__TOTAL__=}"
total="${summary%% *}"
bad="${out##*__BAD__=}"

# FLOOR. Three call sites exist today. Finding none means the spellings moved and this
# green would be vacuous -- the exact failure the gate is written against.
if [ "${total:-0}" -lt 3 ]; then
    echo "✗ found only ${total:-0} www build call site(s); expected at least 3." >&2
    echo "  The invocation spelling changed, or the scan is broken. Either way this" >&2
    echo "  green would assert nothing. Update find_sites()." >&2
    exit 1
fi

if [ "${bad:-0}" -gt 0 ]; then
    grep 'MISSING' <<<"$out" >&2
    echo "" >&2
    echo "  downloads.astro fetches the latest release at build time and THROWS on a 403." >&2
    echo "  Add to that step's env:  GITHUB_TOKEN: \${{ github.token }}" >&2
    exit 1
fi

echo "✓ all $total www build call site(s) pass GITHUB_TOKEN"
