# Media assets and the git-history rewrite

Lookup material lifted verbatim out of CLAUDE.md, which keeps the summary and points here. Nothing below was reworded in the move.

## Media Assets (tutorial/solution videos + tutorial-narration audio)

Tutorial/solution videos and the tutorial-narration audio cache live in Cloudflare R2, not git: bucket `rediacc-www-media`. Videos are served at `media.rediacc.com`; this replaced committing media directly under `packages/www/public/`, which bloated `.git` and caused CI timeouts on the `ubuntu-slim` runner's hard 15-minute cap. Measured across full history on 2026-08-23: **7,768
blobs / 5,602.6 MB** over four prefixes, not the three below. The fourth is `packages/www/public/media/founder/` (138 files, narration audio, captions, photos, posters), which was untracked in #512 alongside the others but, unlike them, was never mirrored to R2 and never added to `packages/www/.gitignore`; see `.ci/docs/r2-media-setup.md` §6. The
`packages/www/public/assets/{tutorials/video,videos/solutions,tutorials/audio}` directories are gitignored and no longer tracked — a fresh checkout has none of these files locally; the site fetches videos straight from `media.rediacc.com` at runtime (`src/utils/solution-video.ts`, `src/plugins/remark-tutorial-embed.ts` read `src/data/video-manifest.json` and emit CDN URLs when
`PUBLIC_VIDEO_CDN_BASE_URL` is set — see `.github/workflows/cd-deploy-worker.yml`'s "Build pages" step). The two CI gate scripts (`check-locale-tutorial-assets.ts`, `check-solution-videos.ts`) check the manifest, not the local filesystem, so they're unaffected by whether media happens to be checked out locally. Because the files leave the git tree entirely (not just history), no CI
sparse-checkout workaround was needed — even a full default `actions/checkout` no longer transfers them.

**Solution-video publishing is gated in a repo this file cannot see.** `check-locale-tutorial-assets.ts`/`check-solution-videos.ts` above verify the *manifest* post-publish, in console CI. What verifies *pre*-publish — that a render pass actually produced all 26 slugs × 13 locales × 3 artifacts (main, vertical, teaser) before anything ships — lives entirely in `private/growth`, a
separate, gitignored repo console CI cannot check out or run: `private/growth/.ci/checks/check-locale-completeness.sh --strict` is a mandatory, non-bypassable precondition inside `private/growth/video_pipeline/publish-solutions.sh` (no flag or env var skips it; it runs unconditionally in step 0, before the `--yes` real-upload gate). If you edit `publish-solutions.sh`, keep that
call — its removal reopens the exact defect the two console-side gates above only catch after the fact, on manifest content, not before a bad publish ships.

The tutorial-narration `.mp3` cache (`tutorials/audio/`) is a **different case**: it's never served to a browser (TTS narration muxed into the final `.mp4` at build time by `generate-tutorial-video.ts` / `scripts/lib/ffmpeg-video.ts`), so it's synced to the same bucket under `tutorials/audio/` purely as a build-time cache — not covered by the Cache Rule, only reachable via the S3
API. `./run.sh www tutorials generate|video` restores/backs it up automatically (best-effort, skips with a warning if R2 credentials aren't set) via `www_tutorial_audio_restore` / `www_tutorial_audio_upload` in `run.sh`. Regenerating narration costs real TTS GPU/electricity, so this cache exists specifically to avoid re-paying that cost on a fresh checkout.

See `.ci/docs/r2-media-setup.md` for the full bucket/domain/Cache Rule setup plus the audio-cache details (§9), `.ci/scripts/deploy/sync-media-to-r2.sh` to push changed media (incremental, `--tutorials-only`/`--solutions-only`/ `--audio-only`), and `.ci/scripts/deploy/sync-media-from-r2.sh` to restore media locally (needed for pipeline development / offline ffmpeg work; not needed
for normal `npm run dev` browsing). Credentials: `CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID`/`CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY`/`CLOUDFLARE_R2_MEDIA_ENDPOINT`.

**Corrected 2026-09-06, and it was wrong twice.** This paragraph said the three credentials were "org secrets, scoped to `console`" and that the bucket and domain were "org variables `R2_MEDIA_BUCKET`/`MEDIA_CDN_DOMAIN`". Neither store holds them. `gh api orgs/rediacc/actions/secrets` returns `{"total_count":0,"secrets":[]}`: the org SECRET store is unused, not merely empty, and
every workflow pulls from Bitwarden through `./.github/actions/bws-secrets` with `.ci/config/bws-secret-map.json` as the map, where all three credentials are listed. `MEDIA_CDN_DOMAIN` and `R2_MEDIA_BUCKET` were org variables with no reader anywhere in the org (checked by `gh search code --owner rediacc`), and both were deleted on 2026-09-24, together with the equally unread `AWS_SES_REGION_ASIA`, `AWS_SES_REGION_US`, `SMTP_FROM` and `SMTP_PORT`. Every variable a workflow did read moved to Bitwarden the same day (`agent/plans/PLAN-github-actions-to-bitwarden.md`), so no count of the GitHub variable store is recorded here: `check:ci-actions-vars` is the enumeration, and it holds zero. The bucket is a literal in the sync script itself
(`BUCKET="rediacc-www-media"`), and `R2_MEDIA_BUCKET` was already found dead, with zero readers anywhere, in `agent/plans/PLAN-env-to-bitwarden-v2.md` D2, which named this very sentence as the doc asserting the opposite. Looking in the org store and finding nothing reads as "the secret was deleted" when the truth is "you are looking in the wrong store".

**The git-history rewrite LANDED on 2026-08-23** ([#532](https://github.com/rediacc/console/issues/532)), so `.git` itself finally shrank: `size-pack` went **5.64 GiB to 182 MiB**, and a fresh `git clone --filter=blob:none` is now **49 MB of `.git` in about 10 seconds**. It removed the four media prefixes above and, in the same pass, 78 AI co-author trailers and 16 robot footers
from 73 commit messages.

Two consequences worth knowing before they surprise you:

- **Every commit SHA changed.** Anything citing a pre-rewrite SHA (release
notes, R2 `.released` sentinels, older `agent/` and `docs/` prose) no longer resolves. The old-to-new map is preserved at `~/commit-map-20260823.txt`. `docs/agent-reference/deleted-branches-20260730.md` is the one file whose stated purpose the rewrite voided; its header says so.
- **GitHub's reported repository size will lag**, because the old objects become
unreachable rather than deleted until GitHub's own gc runs. An unchanged size is not a failed push; the check that matters is that a fresh clone's `HEAD^{tree}` still equals what it was before the rewrite.

CI never paid for the dead blobs anyway: all 11 `fetch-depth: 0` checkouts pass `filter: blob:none`. Note that worktrees SHARE one object store, so `.git` was never a per-worktree cost. The full procedure, the controls, and the two traps it cost to get right are in `agent/plans/PLAN-git-history-media-rewrite.md`.
