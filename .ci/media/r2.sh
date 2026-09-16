#!/bin/bash
# The tutorial-narration cache in R2: restore before generating, back up after.
#
# Two functions, one module, on purpose. They are a matched pair -- each one's header
# names the other -- and they are the only place in the media pipeline that reads the
# CLOUDFLARE_R2_MEDIA_* credentials. Isolating them is what lets every other module's
# test run with aws and the network absent without having to think about it, and it
# makes the credential-absent path (warn, return 0, never fail the pipeline) a single
# thing to test rather than a branch buried in two orchestrators.
#
# Part of the media pipeline extraction (W10). Moved out of run.sh byte for byte in
# phase 1, comments included; phase 2 deleted run.sh's copies, so these are the only
# definitions of the two names anywhere. .ci/scripts/test/gates/test-media-r2.sh asserts
# that ownership and drives both the credentials-absent and credentials-present paths
# with the sync scripts faked, so no bucket is ever touched.
#
# SOURCED, NEVER EXECUTED. Callers supply ROOT_DIR and the log_* helpers.

www_tutorial_audio_restore() {
    # Best-effort: the tutorial-narration mp3 cache is synced to R2, not
    # committed to git (see .ci/docs/r2-media-setup.md #3). Restoring it
    # before generate/video lets tutorial_tts/cli.py's cache-hit check
    # (keyed on the file existing locally) actually hit, instead of paying
    # for a full TTS re-synthesis on every fresh checkout. Skips with a
    # warning if R2 credentials aren't configured -- local iteration without
    # them still works, just without the cache.
    if [[ -z "${CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID:-}" || -z "${CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY:-}" || -z "${CLOUDFLARE_R2_MEDIA_ENDPOINT:-}" ]]; then
        log_warn "R2_MEDIA_* not set — skipping tutorial-audio cache restore (will regenerate via TTS as needed)"
        return 0
    fi
    log_step "Restoring tutorial-audio cache from R2..."
    "$ROOT_DIR/.ci/scripts/deploy/sync-media-from-r2.sh" --audio-only || log_warn "Audio cache restore failed, continuing without it"
}

www_tutorial_audio_upload() {
    # Counterpart to www_tutorial_audio_restore: backs up newly-synthesized
    # narration so it's not lost/re-paid-for on the next fresh checkout.
    if [[ -z "${CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID:-}" || -z "${CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY:-}" || -z "${CLOUDFLARE_R2_MEDIA_ENDPOINT:-}" ]]; then
        log_warn "R2_MEDIA_* not set — skipping tutorial-audio cache upload"
        return 0
    fi
    log_step "Backing up tutorial-audio cache to R2..."
    "$ROOT_DIR/.ci/scripts/deploy/sync-media-to-r2.sh" --audio-only || log_warn "Audio cache upload failed"
}
