#!/usr/bin/env node
/**
 * Hard-fail gate: every tutorial's published word-timing sidecar
 * (`<slug>.<lang>.words.json`, `src/data/video-manifest.json` ->
 * `tutorials[slug][lang].wordsJson`) must reflect real per-word ASR
 * alignment, not the evenly-distributed estimate fallback in
 * `scripts/lib/vtt-emit.ts::estimateRelativeWordTimings()`. That fallback
 * fires whenever a tutorial's TTS audio was generated without `--subtitle`
 * (Qwen3-ASR + forced alignment) -- captions still render, they're just not
 * synced to the actual audio (every word gets the same duration regardless
 * of length). See rediacc/console caption-sync investigation, 2026-07-01.
 *
 * Ground truth is the PUBLISHED asset, not local git state: the committed
 * `tutorial-timeline/<lang>/<slug>.json` source files are not a reliable
 * signal here. A tutorial can be correctly regenerated and published
 * (real alignment live on the CDN) without that regeneration's timeline
 * JSON diff ever being committed back to git -- checking local state alone
 * produces both false failures and false passes. So this script fetches
 * each words.json from media.rediacc.com and checks the actual per-word
 * durations for real variance.
 *
 * COROLLARY, learned the hard way: fetching the published asset means fetching whatever
 * the CDN currently serves. Immediately after a publish that is the OLD copy, and this
 * gate will report a large, entirely false set of failures. Run
 * `.ci/scripts/deploy/purge-media-cache.sh` and re-check before acting on any mass
 * failure. Once the cache is fresh, a surviving failure is real: it means the published
 * timings themselves are flat, and the fix is to RE-ALIGN (`--subtitle --resubtitle`),
 * not to re-publish the same files.
 *
 * CJK (ja/zh): spaceless text means the duration-variance check alone can't
 * see inside a cue whose words collapsed to one token. The pipeline now
 * segments CJK with Intl.Segmenter (vtt-emit.ts::tokenizeForTiming) and the
 * ASR mapping is char-position based, so real alignment produces multiple
 * per-token entries per cue. This gate therefore checks ja/zh strictly:
 * a CJK cue whose text segments into >= MIN_WORDS_FOR_CHECK tokens but
 * carries <= 1 word entry has no intra-cue timing (the pre-fix data shape)
 * and fails, in addition to the flat-spread check that applies everywhere.
 *
 * All 13 locales are in scope: ar/et/tr are natively narrated by VoxCPM2 and published.
 *
 * ESTONIAN IS A KNOWN, UNFIXABLE CAVEAT. No forced aligner in the stack supports it, so its
 * word timings come from the estimator and ARE flat — measured across the published fleet:
 * 394 of Estonian's cues are flat, against ~107 genuine alignment failures spread over
 * every other locale. An earlier version of this comment claimed Estonian had "zero flat
 * cues"; that was measured before the migration and is simply false now. Until this gate
 * learns to exempt Estonian, its findings for `et` are expected output, not defects.
 */
import process from 'node:process';
import type { VideoManifest } from './lib/update-video-manifest.js';

import { SITE_LOCALES } from '@rediacc/locales';
const manifestUrl = new URL('../src/data/video-manifest.json', import.meta.url);

// All 13 site locales, sourced from packages/locales rather than hand-maintained.
//
// This gate fetches words.json from media.rediacc.com, so it only ever sees PUBLISHED
// state. That has one sharp consequence: right after a publish it will report failures
// from the pre-publish copies Cloudflare is still serving. Run
// `.ci/scripts/deploy/purge-media-cache.sh` and re-check BEFORE believing any en-masse
// finding — a stale cache has already produced one false 53-combo report here.
const AUDIO_LANGUAGES = SITE_LOCALES;

// 4, not 3: ASR timestamps sit on an 0.08s quantization grid, so a REAL
// 3-word cue quite often lands three identical durations (seen live in
// es/ru: [0.72,0.72,0.72]) -- a false positive. Estimate-fallback output
// is uniform across every cue of the narration, so >= 4-word cues still
// catch it reliably.
const MIN_WORDS_FOR_CHECK = 4;
const FLAT_SPREAD_THRESHOLD_SEC = 0.02;
const FETCH_CONCURRENCY = 16;

interface WordEntry {
  start: number;
  end: number;
  char: [number, number];
}
interface CueEntry {
  start: number;
  end: number;
  text: string;
  words: WordEntry[];
}
interface WordsDoc {
  cues: CueEntry[];
}

interface FlatCue {
  slug: string;
  lang: string;
  cueIndex: number;
  text: string;
}

interface Target {
  slug: string;
  lang: string;
  url: string;
}

async function loadManifest(): Promise<VideoManifest> {
  const fs = await import('node:fs');
  return JSON.parse(fs.readFileSync(manifestUrl, 'utf8')) as VideoManifest;
}

/**
 * Locales this gate cannot meaningfully check, with the reason.
 *
 * Estonian has NO forced aligner anywhere in the stack — not in Qwen3-ASR, not in any
 * model the pipeline can reach — so `vtt-emit`'s estimator is the ONLY thing that can
 * produce its word timings. Every Estonian cue is flat by construction (measured: 394 of
 * them across the published fleet), and no amount of re-running alignment will change
 * that. Asserting on it is a permanent false failure, not a finding.
 *
 * This is an EXEMPTION, not a removal: `et` stays in AUDIO_LANGUAGES so every other gate
 * and every locale-count check still sees all 13. Delete this entry the day an
 * Estonian-capable aligner exists.
 */
const FLAT_TIMING_EXEMPT = new Set(['et']);

function collectTargets(manifest: VideoManifest): Target[] {
  const targets: Target[] = [];
  for (const [slug, byLang] of Object.entries(manifest.tutorials)) {
    for (const lang of AUDIO_LANGUAGES) {
      if (FLAT_TIMING_EXEMPT.has(lang)) continue;
      const entry = byLang[lang]?.wordsJson;
      if (!entry?.path) continue; // covered by check-locale-tutorial-assets.ts
      targets.push({ slug, lang, url: `${manifest.baseUrl}/${entry.path}` });
    }
  }
  return targets;
}

async function runPool<T, R>(items: T[], limit: number, fn: (item: T) => Promise<R>): Promise<R[]> {
  const results: R[] = new Array(items.length);
  let next = 0;
  async function worker() {
    while (next < items.length) {
      const i = next++;
      results[i] = await fn(items[i]);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return results;
}

// A 4-5 word cue on ASR's 0.08s quantization grid occasionally collides into
// identical REAL durations (seen live: ko networking [0.4 x5] next to cues
// with varied durations). The estimate fallback, by contrast, spreads ONE
// uniform span across the whole narration -- so it shows up either as a
// long flat cue or as a RUN of adjacent flat cues sharing the same span.
// Isolated short flat cues whose neighbors vary are real alignment.
const DEFINITE_FLAT_WORDS = 6;

function findFlatCues(slug: string, lang: string, doc: WordsDoc): FlatCue[] {
  // NOTE: no special <=1-word rule for CJK. Slide/intro/outro cues carry a
  // single word entry spanning the cue BY DESIGN in every language (see
  // CueGroup in vtt-emit.ts), which is indistinguishable from the old
  // pre-Intl.Segmenter collapsed shape. Post-fix, an estimate fallback
  // always yields multi-token cues (Intl.Segmenter), so the flat-spread
  // logic covers CJK the same way it covers everything else.
  const candidates = doc.cues.map((cue) => {
    if (cue.words.length < MIN_WORDS_FOR_CHECK) return null;
    const durations = cue.words.map((w) => w.end - w.start);
    const spread = Math.max(...durations) - Math.min(...durations);
    if (spread >= FLAT_SPREAD_THRESHOLD_SEC) return null;
    return { span: durations[0], words: cue.words.length };
  });
  const flat: FlatCue[] = [];
  candidates.forEach((cand, i) => {
    if (!cand) return;
    const sameSpan = (other: (typeof candidates)[number]) =>
      other != null && Math.abs(other.span - cand.span) < FLAT_SPREAD_THRESHOLD_SEC;
    const inRun = sameSpan(candidates[i - 1] ?? null) || sameSpan(candidates[i + 1] ?? null);
    if (cand.words >= DEFINITE_FLAT_WORDS || inRun) {
      flat.push({ slug, lang, cueIndex: i, text: doc.cues[i].text });
    }
  });
  return flat;
}

async function checkTarget(target: Target): Promise<FlatCue[] | { error: string }> {
  // 180 single-attempt remote fetches make the gate flaky by construction
  // (one transient reset = red run). Retry network errors and 5xx with
  // backoff; 4xx is a deterministic missing/misplaced asset — fail fast.
  const ATTEMPTS = 3;
  let lastError = 'unknown';
  for (let attempt = 1; attempt <= ATTEMPTS; attempt++) {
    try {
      const res = await fetch(target.url);
      if (res.ok) {
        const doc = (await res.json()) as WordsDoc;
        return findFlatCues(target.slug, target.lang, doc);
      }
      if (res.status < 500) return { error: `HTTP ${res.status}` };
      lastError = `HTTP ${res.status}`;
    } catch (e) {
      lastError = e instanceof Error ? e.message : String(e);
    }
    if (attempt < ATTEMPTS) await new Promise((r) => setTimeout(r, 1000 * attempt));
  }
  return { error: `${lastError} after ${ATTEMPTS} attempts` };
}

function printRemediation(slug: string, lang: string): void {
  console.error(
    `  ./run.sh www tutorials generate --cast ${slug} --lang ${lang} --subtitle --resubtitle`
  );
  console.error(`  ./run.sh www tutorials video ${slug} --lang ${lang} --captions-only`);
  console.error(
    `  npm run tutorials:publish-video -w @rediacc/www -- --cast ${slug} --lang ${lang}`
  );
  console.error(`  .ci/scripts/deploy/purge-media-cache.sh`);
  console.error(
    `  # --resubtitle matters: sparse-but-structurally-valid wordTimings are otherwise` +
      ` reused as-is (has_valid_word_timings in tutorial_tts/cli.py is structural only)`
  );
  console.error(
    `  # --captions-only skips the ffmpeg re-encode (mp4 unchanged) and just re-derives` +
      ` vtt/chapters/words.json; drop it to force a full render if that scene's browser cache is cold`
  );
}

async function main(): Promise<number> {
  const manifest = await loadManifest();
  const targets = collectTargets(manifest);

  console.log(
    `Checking caption sync for ${targets.length} tutorial x language combos ` +
      `(fetching published words.json from ${manifest.baseUrl})...`
  );

  const results = await runPool(targets, FETCH_CONCURRENCY, checkTarget);

  const errors: string[] = [];
  const flatByTutorial = new Map<string, FlatCue[]>();
  results.forEach((result, i) => {
    const target = targets[i];
    if ('error' in result) {
      errors.push(`${target.slug} [${target.lang}]: fetch failed (${result.error})`);
      return;
    }
    if (result.length > 0) {
      const key = `${target.slug}\t${target.lang}`;
      flatByTutorial.set(key, result);
    }
  });

  if (errors.length > 0) {
    console.error(`\n✗ ${errors.length} words.json fetch(es) failed:\n`);
    for (const e of errors) console.error(`  ${e}`);
  }

  if (flatByTutorial.size === 0 && errors.length === 0) {
    console.log(
      `✓ Caption sync OK: ${targets.length} combos checked, 0 flat/estimated timing found.`
    );
    return 0;
  }

  if (flatByTutorial.size > 0) {
    console.error(
      `\n✗ ${flatByTutorial.size} tutorial x language combo(s) have flat/estimated word ` +
        `timing (captions render but aren't synced to audio):\n`
    );
    for (const [key, flatCues] of [...flatByTutorial.entries()].sort()) {
      const [slug, lang] = key.split('\t');
      console.error(
        `[${slug} / ${lang}] ${flatCues.length} flat cue(s), e.g. "${flatCues[0].text}"`
      );
      console.error('To fix:');
      printRemediation(slug, lang);
      console.error('');
    }
  }

  return 1;
}

main()
  .then((code) => process.exit(code))
  .catch((e) => {
    console.error('check-tutorial-caption-sync crashed:', e);
    process.exit(1);
  });
