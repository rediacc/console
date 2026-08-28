#!/usr/bin/env bash
# One entry point for the media pipelines under private/growth.
#
# WHY THIS EXISTS. Every pipeline must run with cwd = private/growth and ITS OWN venv on
# PATH. `run.sh` does that for a full pipeline invocation, but there is no wrapper for
# driving a SINGLE step, so doing that by hand means retyping the setup. On 2026-08-28 a
# session ran a step-8000 rebuild from `video_pipeline/` instead of `private/growth/`,
# which made config resolve `packages/www/...` to a path that does not exist:
#     FileNotFoundError: .../private/growth/packages/www/src/config/persona-pages.ts
# The sentinels had ALREADY been deleted by then, so the tree was left mid-operation with
# no way back except completing the rebuild. A wrapper that cannot get the directory
# wrong removes that whole class.
#
#   ./media.sh run <pipeline> [args...]     a normal pipeline invocation
#   ./media.sh teaser <slug> [lang...]      rebuild teasers: drop the sentinel AND rebuild,
#                                           as ONE operation that cannot half-finish
#   ./media.sh luma <mp4>                   measure a rendered file (light is meanY ~210)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GROWTH="$ROOT/private/growth"

die() { printf '%s\n' "$*" >&2; exit 1; }

# Refuse ONLY the slug a live pass is processing right now, which is the last marker in
# its log. An earlier version refused any slug the log mentioned at all, which meant every
# slug once phase A had walked the fleet: a guard that blocks everything gets switched off,
# and then it guards nothing. A finished slug is safe to rebuild; the in-flight one is not.
pass_owns() {
    local slug="$1" log current
    for log in /tmp/claude-*/*/*/scratchpad/full-pass.log; do
        [ -f "$log" ] || continue
        # Only consider a log still being written; a finished pass owns nothing.
        # stat arithmetic, NOT `find -newermt '-10 minutes'`: find here is bfs, which
        # rejects relative timestamps outright, and under 2>/dev/null that failure reads
        # as "no match" and the guard silently stops guarding.
        [ $(( $(date +%s) - $(stat -c %Y "$log") )) -lt 600 ] || continue
        current=$(grep -oP '^######## [AB] \K[^ ]+' "$log" | tail -1)
        [ "$current" = "$slug" ] && return 0
    done
    return 1
}

venv_for() {
    local p="$GROWTH/$1/.venv/bin"
    [ -d "$p" ] || die "no venv for pipeline '$1' (looked in $p)"
    printf '%s' "$p"
}

cmd="${1:-}"; shift || true
case "$cmd" in
run)
    pipeline="${1:-}"; shift || true
    [ -n "$pipeline" ] || die "usage: ./media.sh run <pipeline> [args...]"
    [ -d "$GROWTH/$pipeline" ] || die "no such pipeline: $pipeline"
    # Assign separately: `die` inside a command substitution exits only the SUBSHELL, so
    # an inline export would swallow the failure and set an empty PATH prefix instead of
    # stopping. shellcheck SC2155 caught this; it is a real bug here, not a style nit.
    vbin=$(venv_for "$pipeline") || exit 1
    export PATH="$vbin:$PATH"
    cd "$GROWTH"                       # THE point of this wrapper
    exec python3 "$GROWTH/$pipeline/main.py" "$@"
    ;;
teaser)
    slug="${1:-}"; shift || true
    [ -n "$slug" ] || die "usage: ./media.sh teaser <slug> [lang...]"
    [ -d "$GROWTH/video_pipeline/processing/$slug" ] || die "no such slug: $slug"
    if pass_owns "$slug"; then
        die "refusing: a live fleet pass has started '$slug'. Deleting its sentinels would race a running render."
    fi
    vbin=$(venv_for video_pipeline) || exit 1
    export PATH="$vbin:$PATH"
    cd "$GROWTH"
    langs="$*"
    exec python3 - "$slug" "$langs" <<'PY'
import sys, asyncio, logging
sys.path.insert(0, '.')
logging.basicConfig(level=logging.INFO, format='%(message)s')
from pathlib import Path
from video_pipeline.config import LOCALIZE_LANGS, PROCESSING_DIR
from video_pipeline.main import load_record, _import_step

slug = sys.argv[1]
langs = sys.argv[2].split() if len(sys.argv) > 2 and sys.argv[2].strip() else list(LOCALIZE_LANGS)
step = _import_step("step8000_teaser")
rec = load_record(slug, "en")
proc = Path(PROCESSING_DIR) / slug

ok = failed = 0
for lang in langs:
    # Drop the sentinel and rebuild in the SAME breath. Deleting it as a separate step is
    # what left a tree half-done when the rebuild then failed on a wrong working directory.
    suf = "" if lang == "en" else f".{lang}"
    # A teaser is CUT FROM the main video, so rebuilding it from a main that predates the
    # palette change just produces another dark teaser. Measured 2026-08-28: rebuilding
    # safe-os-testing.teaser.ru from a July main gave meanY 46.9, indistinguishable from
    # the artifact it replaced. Say so rather than let the rebuild look like progress.
    src = proc / "video" / f"{slug}{suf}.mp4"
    palette = Path("video_pipeline/remotion/src/palette.ts")
    if src.exists() and palette.exists() and src.stat().st_mtime < palette.stat().st_mtime:
        print(f"  WARNING {lang}: {src.name} is older than palette.ts, so this teaser will "
              f"inherit the OLD look. Re-render the main first.")
    (proc / f"8000_teaser{suf}.json").unlink(missing_ok=True)
    try:
        asyncio.run(step.run(rec, lang=lang)); ok += 1
    except Exception as e:
        failed += 1
        print(f"  {lang} FAILED: {type(e).__name__}: {e}")
print(f"teasers rebuilt: {ok} ok, {failed} failed, of {len(langs)}")
sys.exit(1 if failed else 0)
PY
    ;;
luma)
    mp4="${1:-}"; [ -f "$mp4" ] || die "usage: ./media.sh luma <mp4>"
    ffmpeg -nostdin -v error -i "$mp4" \
        -vf "fps=1/3,scale=192:-1,signalstats,metadata=print:file=-" -f null - 2>/dev/null |
        sed -n 's/.*lavfi\.signalstats\.YAVG=//p' |
        awk '{n++; s+=$1; if($1<64)d++} END{if(!n){print "no frames"; exit 1}
             printf "frames=%d meanY=%.1f pct_dark=%.1f\n", n, s/n, 100*d/n}'
    ;;
*)
    cat >&2 <<'USAGE'
media.sh - one entry point for the pipelines under private/growth.

It exists so the working directory and venv cannot be wrong. Every pipeline must run
with cwd = private/growth and its own venv on PATH; getting that wrong resolves config
paths against the wrong root and fails deep inside a step.

  ./media.sh run <pipeline> [args...]   a normal pipeline invocation
  ./media.sh teaser <slug> [lang...]    rebuild teasers: drops the sentinel AND rebuilds
                                        as one operation, and refuses a slug a live
                                        fleet pass has started
  ./media.sh luma <mp4>                 measure luminance (light is meanY about 210,
                                        the pre-palette artifacts measure 30 to 50)
USAGE
    exit 1
    ;;
esac
