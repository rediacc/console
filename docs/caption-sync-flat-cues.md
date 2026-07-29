# check-tutorial-caption-sync: why it is red, and why re-aligning will not fix it

Written 2026-07-30 for whoever hits this gate next, and specifically for PR #543, where it
has blocked four consecutive CI rounds. **Do not spend GPU time re-aligning.** That was my
first hypothesis and it is wrong; the evidence is below.

## What is already done

- **The CDN purge has been run.** `CF_EMAIL` was the missing half of the credential pair
  (`CF_GLOBAL_API_KEY` was already in `private/account/.env`); the operator supplied it and it
  is now recorded there too. `source private/account/.env` and you have everything.
  Verified fresh afterwards: `tr/tutorial-add-server.tr.words.json` fetched from the CDN is
  now byte-identical to the local file, where before the purge it showed `start 1.368`
  against local `2.04`.
- **The whole fleet is published** — 4,793 objects, all 234 tutorial videos with their
  `words.json` sidecars, manifest at 21 slugs × 13 locales.
- **Estonian is exempted** in the gate via a named `FLAT_TIMING_EXEMPT`, because no forced
  aligner in the stack supports `et` and its 394 flat cues are unfixable. That alone took the
  gate from 42 combos to 24 — if you are seeing 24, you already have that fix.

## Why a republish is a no-op

I fetched a failing pair straight from the CDN and compared:

    ru/tutorial-backup-restore.ru.words.json
      published === local : true
      flat cues PUBLISHED : 4
      flat cues LOCAL     : 4

Identical bytes, identical defect. Re-uploading the same files changes nothing.

## Why a re-align is a no-op

Ran `--subtitle --resubtitle` over all 24 failing pairs: **24/24 succeeded, and they still
fail the gate.** Alignment is not the failing component:

- A verbose run drains all 27 alignment jobs with **no warnings and no fallback**.
- The resulting timeline's per-step `wordTimings` are **varied** — zero flat groups.

So the flatness is introduced *after* alignment.

## The actual root cause

`packages/www/scripts/lib/vtt-emit.ts:264-277`. Per **cue**, if the aligned words cover less
than `MIN_WORD_TIMING_COVERAGE` (0.5) of that cue's text, vtt-emit **discards the real
timings** and calls `estimateRelativeWordTimings()` for that cue.

Measured on `ar/tutorial-add-server`:

| step | chars | aligned words | coverage | outcome |
|---|---|---|---|---|
| 01 | 128 | 20 | 71% | real timings kept |
| 02 | 112 | 16 | 73% | real timings kept |
| 03 | 115 | 7 | **31%** | **discarded → estimated** |

Coverage is deterministic for a given narration, which is exactly why re-running alignment
produces the same result every time.

The aligner maps words by **character overlap** (`asr.py::_reconcile_words`), so Arabic,
Russian and CJK map fewer words per character than Latin scripts and cross the threshold far
more often. That explains the locale distribution precisely: ar 9, ru 8, zh 4, then pt/ja/fr
one each.

## What this is, and is not

This is a **pre-existing caption-quality limitation that the migration EXPOSED**, not a
regression any single branch introduced. Before the migration the gate was reading
pre-migration `words.json` from a stale CDN cache and passing on data that no longer existed.
Purging the cache made the gate honest, and an honest gate reports this.

## The decision it needs

Three options, put to the operator:

- **(a) Improve the character-overlap mapping** in `_reconcile_words` for those scripts so
  coverage clears 0.5. The real fix, and real work.
- **(b) Lower `MIN_WORD_TIMING_COVERAGE`.** Cheap and **wrong** — partial coverage renders as
  visibly mistimed karaoke, which is worse for a viewer than evenly-spaced timing. Do not do
  this.
- **(c) Give the gate a small per-file estimated-cue budget** instead of demanding zero.
  Honest about a real limitation, and it stops a genuine quality signal from being
  permanently red. This is the recommended default.

## For PR #543 specifically

Leaving the gate red and noting it in the PR body is the right call. It is not that branch's
defect, and nothing that branch can do will clear it.
