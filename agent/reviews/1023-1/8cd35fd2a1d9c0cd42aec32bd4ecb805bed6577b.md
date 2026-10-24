# Review 8cd35fd2: docs(tutorials): the managing-secrets transcripts and timelines follow the re-recorded cast, narrated afresh in 13 locales (local takes, not yet published)

Commit: 8cd35fd2a1d9c0cd42aec32bd4ecb805bed6577b
Repo: console
Branch: 1023-1
Parent: df478de89b31de2ac3146febafcfd59998b60d2f
Patch-Id: 4c40b4b292951b0cd77ebe8377e9236fdd2e09f1
Reviewed-At: 2026-10-24T00:30:14Z
Model: claude-haiku-5-5
Cost: $0.0095 USD, 1 call(s), 20.6s
Diff: 1256632 bytes, 25 files, truncated: yes
Unreviewed: packages/www/src/data/tutorial-timeline/de/tutorial-managing-secrets.json, packages/www/src/data/tutorial-timeline/en/tutorial-managing-secrets.json, packages/www/src/data/tutorial-timeline/es/tutorial-managing-secrets.json, packages/www/src/data/tutorial-timeline/et/tutorial-managing-secrets.json, packages/www/src/data/tutorial-timeline/fr/tutorial-managing-secrets.json, packages/www/src/data/tutorial-timeline/it/tutorial-managing-secrets.json, packages/www/src/data/tutorial-timeline/ja/tutorial-managing-secrets.json, packages/www/src/data/tutorial-timeline/ko/tutorial-managing-secrets.json, packages/www/src/data/tutorial-timeline/pt/tutorial-managing-secrets.json, packages/www/src/data/tutorial-timeline/ru/tutorial-managing-secrets.json, packages/www/src/data/tutorial-timeline/tr/tutorial-managing-secrets.json, packages/www/src/data/tutorial-timeline/zh/tutorial-managing-secrets.json, packages/www/src/data/tutorial-transcripts/ar/tutorial-managing-secrets.json, packages/www/src/data/tutorial-transcripts/de/tutorial-managing-secrets.json, packages/www/src/data/tutorial-transcripts/es/tutorial-managing-secrets.json, packages/www/src/data/tutorial-transcripts/et/tutorial-managing-secrets.json, packages/www/src/data/tutorial-transcripts/fr/tutorial-managing-secrets.json, packages/www/src/data/tutorial-transcripts/it/tutorial-managing-secrets.json, packages/www/src/data/tutorial-transcripts/ja/tutorial-managing-secrets.json, packages/www/src/data/tutorial-transcripts/ko/tutorial-managing-secrets.json, packages/www/src/data/tutorial-transcripts/pt/tutorial-managing-secrets.json, packages/www/src/data/tutorial-transcripts/ru/tutorial-managing-secrets.json, packages/www/src/data/tutorial-transcripts/tr/tutorial-managing-secrets.json, packages/www/src/data/tutorial-transcripts/zh/tutorial-managing-secrets.json
Verdict: findings
Attempt: 1
Labels: bump=none kind=docs why=Data-only update to tutorial timings and transcript hashes; no user-facing change lands until the audio and timelines are published together.
Dropped: 0
Body-Sig: ee365d64dcd6caec

## Findings

### 8cd35fd2.1 [high] packages/www/src/data/tutorial-timeline/ar/tutorial-managing-secrets.json:20
Anchor: in-diff
Claim: The commit lands re-timed timelines (audioDurationSec and wordTimings changed for every step, transcriptHash changed) while every audioSrc path is unchanged (e.g. the step-01 audioSrc on line 18 keeps textHash 0229e4ac). Once this tree deploys before the new mp3s are uploaded to R2, the site plays the old audio against the new word timings, which the commit message itself says will happen. The same applies to all 13 locale timelines.
Resolution: open
