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
 * CJK exclusion (ja/zh): both the real aligner and the estimate fallback
 * tokenize on `text.matchAll(/\S+/g)` (whitespace-delimited "words"). CJK
 * text has no whitespace word boundaries, so this produces ~1 token per
 * cue regardless of alignment quality -- a duration-variance check can't
 * distinguish real alignment from the estimate for these two languages.
 * This is a distinct, deeper problem (tokenization, not "forgot to run
 * --subtitle") that needs its own fix. Until then, ja/zh are reported as
 * an explicit known gap on every run (not silently skipped) so the gap
 * stays visible.
 *
 * ar/et/tr are out of scope entirely: they intentionally reuse English
 * audio with translated captions and deliberately strip wordTimings (real
 * per-word timing against translated text would render as scrambled
 * karaoke highlighting) -- see derive-fallback-timeline.ts. Flat timing
 * there is by design, not a bug.
 */
import process from 'node:process';
import type { VideoManifest } from './lib/update-video-manifest.js';

const manifestUrl = new URL('../src/data/video-manifest.json', import.meta.url);

// Cross-reference: AUDIO_LANGUAGES in
// private/generative/src/tutorial_tts/cli.py. Keep in sync -- this is the
// TypeScript side of that list and can't import the Python source directly.
const AUDIO_LANGUAGES = ['en', 'de', 'es', 'fr', 'ja', 'ru', 'zh', 'ko', 'pt', 'it'] as const;
const CJK_LANGUAGES = new Set(['ja', 'zh']);

const MIN_WORDS_FOR_CHECK = 3;
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

function collectTargets(manifest: VideoManifest): { targets: Target[]; cjkCount: number } {
  const targets: Target[] = [];
  let cjkCount = 0;
  for (const [slug, byLang] of Object.entries(manifest.tutorials)) {
    for (const lang of AUDIO_LANGUAGES) {
      const entry = byLang[lang]?.wordsJson;
      if (!entry?.path) continue; // covered by check-locale-tutorial-assets.ts
      if (CJK_LANGUAGES.has(lang)) {
        cjkCount++;
        continue;
      }
      targets.push({ slug, lang, url: `${manifest.baseUrl}/${entry.path}` });
    }
  }
  return { targets, cjkCount };
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

function findFlatCues(slug: string, lang: string, doc: WordsDoc): FlatCue[] {
  const flat: FlatCue[] = [];
  doc.cues.forEach((cue, i) => {
    if (cue.words.length < MIN_WORDS_FOR_CHECK) return;
    const durations = cue.words.map((w) => w.end - w.start);
    const spread = Math.max(...durations) - Math.min(...durations);
    if (spread < FLAT_SPREAD_THRESHOLD_SEC) {
      flat.push({ slug, lang, cueIndex: i, text: cue.text });
    }
  });
  return flat;
}

async function checkTarget(target: Target): Promise<FlatCue[] | { error: string }> {
  try {
    const res = await fetch(target.url);
    if (!res.ok) return { error: `HTTP ${res.status}` };
    const doc = (await res.json()) as WordsDoc;
    return findFlatCues(target.slug, target.lang, doc);
  } catch (e) {
    return { error: e instanceof Error ? e.message : String(e) };
  }
}

function printRemediation(slug: string, lang: string): void {
  console.error(`  ./run.sh www tutorials generate --cast ${slug} --lang ${lang} --subtitle`);
  console.error(`  ./run.sh www tutorials video ${slug} --lang ${lang} --captions-only`);
  console.error(
    `  npm run tutorials:publish-video -w @rediacc/www -- --cast ${slug} --lang ${lang}`
  );
  console.error(`  .ci/scripts/deploy/purge-media-cache.sh`);
  console.error(
    `  # --captions-only skips the ffmpeg re-encode (mp4 unchanged) and just re-derives` +
      ` vtt/chapters/words.json; drop it to force a full render if that scene's browser cache is cold`
  );
}

async function main(): Promise<number> {
  const manifest = await loadManifest();
  const { targets, cjkCount } = collectTargets(manifest);

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

  if (cjkCount > 0) {
    console.log(
      `⚠ ${cjkCount} tutorial x language combos in ja/zh are NOT checked by this gate ` +
        `(CJK tokenization gap -- see this file's header comment for why). Known gap, not a failure.`
    );
  }

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
