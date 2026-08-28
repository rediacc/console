#!/usr/bin/env bash
# The one measurement harness for page-density work. Frozen build only, never a dev server.
#
# WHY NOT THE DEV SERVER. One server, one working tree, HMR. `packages/www/.astro/` is
# derived from `config.root` with no override, so ANY build rewrites the cache every
# running dev server in the checkout reads. A stale dev server does not fail: it serves a
# SMALLER page, and a census against one returns plausible numbers that describe less site.
# See .claude/agents/browser-probe.md.
#
# THREE THINGS ARE VERIFIED BEFORE ANY NUMBER IS TRUSTED, because each has produced
# internally consistent fiction in this repo before:
#   1. the listening pid is the server THIS script started, not a squatter on the port
#   2. the served page links a hashed asset that is present in the dist on disk
#   3. every page clears a DOM-node FLOOR; a wiped dist once returned success with 5 nodes
#
# Usage:  packages/www/scripts/measure-page-density.sh [out.csv]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
WWW="$ROOT/packages/www"
OUT="${1:-/tmp/page-density-$(date -u +%Y%m%dT%H%M%SZ).csv}"
FLOOR=50

[[ -d "$WWW/dist" ]] || { echo "no dist/. Run: npm run build -w @rediacc/www" >&2; exit 1; }

PORT=$(python3 -c "import random;print(random.randint(20000,60000))")
python3 -m http.server "$PORT" --directory "$WWW/dist" >/dev/null 2>&1 &
SRV=$!
trap 'kill '"$SRV"' 2>/dev/null || true' EXIT
sleep 2

# 1. the pid on the port must be the one we just started
ss -lptn "sport = :$PORT" 2>/dev/null | grep -q "pid=$SRV," || {
    echo "port $PORT is not served by our pid $SRV. Another server holds it; every byte would be theirs." >&2
    exit 1
}

# 2. the served HTML must link a hashed asset that exists in dist. An EMPTY needle is a
#    failure, not a pass: that is how this check went vacuous the first time it was written.
ASSET=$(curl -s "http://localhost:$PORT/en/" | grep -oE '/assets/[A-Za-z0-9_.-]+\.(css|js)' | head -1)
[[ -n "$ASSET" ]] || { echo "no hashed asset in the served HTML; refusing to call this verified" >&2; exit 1; }
[[ -f "$WWW/dist$ASSET" ]] || { echo "served $ASSET is not in dist/; reading someone else's build" >&2; exit 1; }

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-$HOME/.cache/xdg-runtime}"
mkdir -p "$XDG_RUNTIME_DIR"
export AGENT_BROWSER_SESSION="${AGENT_BROWSER_SESSION:-page-density}"

echo "slug,height,screens,words,atoms,nodes" > "$OUT"
measure() {
    local path="$1" label="$2" r h w a n vph vpw
    # `open --viewport WxH` is SILENTLY IGNORED: it reports 1280x577 whatever you pass,
    # and so does a bare `viewport 1280 900`. The width happens to be the 1280 we want, so
    # every reflow-dependent number here is sound; the HEIGHT never was. Do not divide by a
    # height you asked for. Read innerHeight back and divide by that.
    # `|| true` is NOT laziness, and it does not weaken this harness. Measured 2026-08-28:
    # `agent-browser open` exits 1 when its stdout is REDIRECTED and 0 on a terminal, for
    # the same URL that loads correctly either way -- the eval immediately after returns a
    # real scrollHeight in both cases. Under `set -e` that killed the run at the first
    # page, silently, with an empty log and a CSV containing only its header.
    # A genuinely failed load is still caught, by the DOM-node FLOOR below, which is a
    # statement about the page rather than about a wrapper's exit code.
    agent-browser open "http://localhost:$PORT$path" --viewport 1280x900 >/dev/null 2>&1 || true
    r=$(agent-browser eval "JSON.stringify({vph:innerHeight,vpw:innerWidth,h:document.documentElement.scrollHeight,words:(document.body.innerText||'').trim().split(/\s+/).filter(Boolean).length,atoms:document.body.querySelectorAll('h1,h2,h3,h4,li,td,th,[class*=card],[class*=chip],[class*=stat],[class*=step],[class*=item],[class*=row]').length,nodes:document.body.querySelectorAll('*').length})" 2>/dev/null | tail -1)
    # Parsed as JSON, not grepped: `grep -oE '"?h"?:[0-9]+'` also matches the h inside vph.
    read -r h w a n vph vpw < <(python3 -c '
import json,sys,re
raw=sys.stdin.read().strip().replace(chr(92)+chr(34), chr(34))
m=re.search(r"\{.*\}",raw,re.S)
if not m: sys.exit(0)
d=json.loads(m.group(0))
print(d["h"],d["words"],d["atoms"],d["nodes"],d["vph"],d["vpw"])' <<<"$r")
    if [[ -z "${n:-}" || "$n" -lt "$FLOOR" ]]; then
        echo "FLOOR: $label has ${n:-no} DOM nodes (< $FLOOR). That is not a page." >&2
        return 1
    fi
    if [[ -z "${vph:-}" || "$vph" -lt 200 ]]; then
        echo "VIEWPORT: $label reported innerHeight=${vph:-none}. Refusing to invent screens." >&2
        return 1
    fi
    printf '%s,%s,%s,%s,%s,%s\n' "$label" "$h" "$(python3 -c "print(round($h/$vph,1))")" "$w" "$a" "$n" >> "$OUT"
}

for f in "$WWW"/src/pages/\[lang\]/solutions/*.astro; do
    s=$(basename "$f" .astro); [[ "$s" == index ]] && continue
    measure "/en/solutions/$s/" "$s"
done
for p in home for-devops for-ctos for-ceos for-ai-agents; do
    [[ "$p" == home ]] && measure "/en/" home || measure "/en/$p/" "$p"
done

echo "wrote $OUT"
column -s, -t "$OUT"
