#!/bin/bash
# COMPATIBILITY ENTRY POINT. The per-file media publish primitive is
# .ci/media/tools/upload-r2.sh now; it moved there in W10 phase 3, because it was the one
# thing under .ci/scripts/deploy that publishes a rendered video rather than the product.
# Its bulk siblings (sync-media-to-r2.sh, sync-media-from-r2.sh, purge-media-cache.sh)
# are unchanged and stayed here.
#
# WHY THIS FILE STILL EXISTS. One of its two callers is
# private/growth/video_pipeline/publish.py, in a gitignored repository this checkout
# cannot open, commit to, or even read to confirm how it spells this path. The other,
# packages/www/scripts/publish-tutorial-video-to-r2.ts, is right here and could have been
# repointed -- and deliberately was not, because two callers spelling one primitive two
# different ways is a worse state than either spelling alone, and the cross-repo one
# cannot be moved in this change. When the growth-side change lands, both move together
# and this file goes with them.
#
# NOT A WRAPPER WITH OPINIONS. exec, with no argument handling of its own, so argv,
# stdin, stdout, stderr, signals and the exit status all belong to the real script.
# Anything added here becomes a second implementation of a contract that already has one.
#
# HOW THE FORWARD IS PROVEN, given private/growth cannot be inspected:
# .ci/rediacc_ci/tests/gates/test_gate_media_shims.py drives THIS path with aws, npx and the
# network absent and requires the invocation to arrive in .ci/media/tools/upload-r2.sh with
# argv byte-identical, from an arbitrary cwd, with the exit status forwarded. The same
# gate freezes the accepted flag set (--kind --key --lang --field --file --engine
# --defer-manifest), which is the part a caller actually depends on, so a rename on the
# far side of this exec is red here rather than at the next publish run.
#
# DELETING THIS FILE IS A CROSS-REPO BREAKING CHANGE.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
exec "$ROOT/.ci/media/tools/upload-r2.sh" "$@"
