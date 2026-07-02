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
 * CJK (ja/zh): spaceless text means the duration-variance check alone can't
 * see inside a cue whose words collapsed to one token. The pipeline now
 * segments CJK with Intl.Segmenter (vtt-emit.ts::tokenizeForTiming) and the
 * ASR mapping is char-position based, so real alignment produces multiple
 * per-token entries per cue. This gate therefore checks ja/zh strictly:
 * a CJK cue whose text segments into >= MIN_WORDS_FOR_CHECK tokens but
 * carries <= 1 word entry has no intra-cue timing (the pre-fix data shape)
 * and fails, in addition to the flat-spread check that applies everywhere.
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

const MIN_WORDS_FOR_CHECK = 3;
const FLAT_SPREAD_THRESHOLD_SEC = 0.02;
const FETCH_CONCURRENCY = 16;

// CJK detection + segmentation, mirroring scripts/lib/vtt-emit.ts
// (isCjkDominant / tokenizeForTiming). Duplicated here rather than imported
// because vtt-emit.ts pulls in the whole scene-compile dependency chain,
// which this network-only CI gate must not need. Keep the two in sync.
const CJK_CHAR_RE =
  /[\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f]/;
const KANA_RE = /[\u3040-\u30ff\u31f0-\u31ff\uff66-\uff9f]/;

function isCjkDominant(text: string): boolean {
  let cjk = 0;
  let nonSpace = 0;
  for (const ch of text) {
    if (/\s/.test(ch)) continue;
    nonSpace++;
    if (CJK_CHAR_RE.test(ch)) cjk++;
  }
  return nonSpace > 0 && cjk / nonSpace >= 0.25;
}

function cjkTokenCount(text: string): number {
  const locale = KANA_RE.test(text) ? 'ja' : 'zh';
  const segmenter = new Intl.Segmenter(locale, { granularity: 'word' });
  let count = 0;
  for (const seg of segmenter.segment(text)) {
    if (seg.isWordLike) count++;
  }
  return count;
}

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

function collectTargets(manifest: VideoManifest): Target[] {
  const targets: Target[] = [];
  for (const [slug, byLang] of Object.entries(manifest.tutorials)) {
    for (const lang of AUDIO_LANGUAGES) {
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

function findFlatCues(slug: string, lang: string, doc: WordsDoc): FlatCue[] {
  const flat: FlatCue[] = [];
  doc.cues.forEach((cue, i) => {
    // CJK: a cue whose text segments into several tokens but carries <= 1
    // word entry has no intra-cue timing at all (whole-cue highlight only)
    // -- the shape the pre-Intl.Segmenter pipeline produced.
    if (
      isCjkDominant(cue.text) &&
      cue.words.length <= 1 &&
      cjkTokenCount(cue.text) >= MIN_WORDS_FOR_CHECK
    ) {
      flat.push({ slug, lang, cueIndex: i, text: cue.text });
      return;
    }
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
