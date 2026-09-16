#!/usr/bin/env bash
# One entry point for the media pipelines under private/growth.
#
#   ./media.sh run <pipeline> [args...]     a normal pipeline invocation
#   ./media.sh teaser <slug> [lang...]      rebuild teasers: drop the sentinel AND rebuild,
#                                           as ONE operation that cannot half-finish
#   ./media.sh luma <mp4>                   measure a rendered file (light is meanY ~210)
#
# THE BODY MOVED TO .ci/media/teaser.sh (W10), and so did every word of the prose that
# used to be here: why the wrapper exists at all, the 2026-08-28 run from the wrong
# working directory that left a tree mid-operation, why pass_owns refuses only the
# in-flight slug, and why `venv_for`'s result is assigned before it is exported. Read
# that file for any of it. What is left here is the spelling an operator's fingers
# already know, which is why the script survives at all rather than becoming
# `./run.sh www ...`; media-entry.sh's `growth` arm is a verb-for-verb mirror, so run,
# teaser, luma and the usage-and-exit-1 for anything else are unchanged.
#
# exec, and the verb is NOT shifted: media_entry_main matches on `growth` itself, and
# exec makes the pipeline's exit status this script's own instead of something to
# forward. `./media.sh` with no arguments still reaches growth_usage and exits 1.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$ROOT/.ci/media/media-entry.sh" growth "$@"
