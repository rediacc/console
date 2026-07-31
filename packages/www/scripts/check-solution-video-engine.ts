#!/usr/bin/env tsx
/**
 * Every published solution video must be narrated by the CURRENT TTS engine.
 *
 * WHY THIS EXISTS
 * ---------------
 * On 2026-07-30 a live marketing page was still playing Qwen3-TTS narration months after
 * the VoxCPM2 migration. 207 of 273 solution narrations were stale and nothing said so:
 * `check:ci-solution-videos` asserts a video EXISTS, never that it is current, and the
 * pipeline that makes them lives in gitignored `private/` where CI cannot look. The drift
 * was found by a human noticing a voice on edge.rediacc.com — the slowest possible detector.
 *
 * The fix that makes this checkable at all is upstream: the narration engine now rides from
 * `tts_bridge`'s `timing.json` -> `4000_voiceover.json` -> `publish.py` -> the COMMITTED
 * manifest. That manifest is the only media oracle CI can see, which is why the assertion
 * lives here and not in the pipeline.
 *
 * WHAT COUNTS AS STALE
 * --------------------
 * A missing `engine` is stale, not "unknown, assume fine". Every entry published before
 * 2026-07-30 predates the field, so treating absence as passing would have made this gate
 * green on exactly the fleet it was written to catch — the vacuity failure this repo keeps
 * paying for. If you are backfilling old entries, backfill them honestly; do not weaken this.
 *
 * Scope comes from `check-solution-videos.ts` (`listSlugs`/`slugRendersVideo`) so the two
 * gates cannot disagree about which slugs require video.
 *
 * Usage:
 *   tsx scripts/check-solution-video-engine.ts [--selftest]
 */
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { VIDEO_LANGS } from '../src/utils/solution-video.ts';
import { listSlugs, slugRendersVideo } from './check-solution-videos.ts';
import type { VideoManifest } from './lib/update-video-manifest.js';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const manifestPath = path.join(scriptDir, '..', 'src', 'data', 'video-manifest.json');

/**
 * The engine every published narration is expected to carry.
 *
 * Bumping this is a DELIBERATE act that declares the whole fleet stale until it is
 * re-narrated and re-published. Bump it in the same change that starts that work, never
 * ahead of it — a red gate nobody can clear teaches people to suppress the gate.
 */
const CURRENT_ENGINE = 'voxcpm2';

export type EngineFinding = { slug: string; lang: string; engine: string | null };

/** Slug x locale pairs whose narration is not on `expected`. `null` = no engine recorded. */
export function findStaleNarrations(
  manifest: VideoManifest,
  slugs: string[],
  langs: readonly string[],
  expected: string = CURRENT_ENGINE
): EngineFinding[] {
  const out: EngineFinding[] = [];
  for (const slug of slugs) {
    const byLang = manifest.solutions?.[slug];
    // A slug absent from the manifest is check-solution-videos' finding, not ours. Reporting
    // it here too would double-count one defect and bury this gate's actual signal.
    if (!byLang) continue;
    for (const lang of langs) {
      const mp4 = byLang[lang]?.mp4;
      if (!mp4) continue; // likewise: a missing asset is the other gate's job
      const engine = mp4.engine ?? null;
      if (engine !== expected) out.push({ slug, lang, engine });
    }
  }
  return out;
}

function loadManifest(): VideoManifest {
  if (!fs.existsSync(manifestPath)) {
    console.error(`✗ Manifest not found at ${manifestPath}`);
    process.exit(1);
  }
  return JSON.parse(fs.readFileSync(manifestPath, 'utf8')) as VideoManifest;
}

function main(): number {
  const slugs = listSlugs().filter(slugRendersVideo);
  // Anti-vacuity: a gate that checks nothing must not report success. Without this, a broken
  // checkout or a rename of the solutions page directory reads as "all narrations current".
  if (slugs.length === 0) {
    console.error(
      '✗ Refusing to run: no solution pages require video, so this check would assert nothing.'
    );
    return 1;
  }

  const manifest = loadManifest();
  const stale = findStaleNarrations(manifest, slugs, VIDEO_LANGS);
  const checked = slugs.length * VIDEO_LANGS.length;

  if (stale.length === 0) {
    console.log(
      `✓ Solution narration engine OK: ${checked} slug×locale pair(s) all on ${CURRENT_ENGINE}.`
    );
    return 0;
  }

  const byEngine = new Map<string, EngineFinding[]>();
  for (const f of stale) {
    const k = f.engine ?? '(no engine recorded)';
    if (!byEngine.has(k)) byEngine.set(k, []);
    byEngine.get(k)!.push(f);
  }

  console.error(
    `✗ ${stale.length} of ${checked} solution narration(s) are not on ${CURRENT_ENGINE}:\n`
  );
  for (const [engine, list] of [...byEngine.entries()].sort()) {
    const byLang = new Map<string, string[]>();
    for (const f of list) {
      if (!byLang.has(f.lang)) byLang.set(f.lang, []);
      byLang.get(f.lang)!.push(f.slug);
    }
    console.error(`[${engine}] ${list.length} pair(s)`);
    for (const [lang, ss] of [...byLang.entries()].sort()) {
      console.error(
        `  ${lang}: ${ss.length} slug(s) — ${ss.slice(0, 4).join(', ')}${ss.length > 4 ? ', …' : ''}`
      );
    }
    console.error('');
  }

  const langs = [...new Set(stale.map((f) => f.lang))].sort();
  const en = langs.includes('en');
  console.error('To fix, from private/growth/video_pipeline:');
  if (en) {
    console.error('  # English first — localize refuses a slug whose English render is missing');
    console.error('  rm processing/<slug>/{4000_voiceover.json,6000_render.json,8000_teaser.json}');
    console.error('  ./run.sh --slug <slug>');
  }
  const others = langs.filter((l) => l !== 'en');
  if (others.length) {
    console.error(`  rm processing/*/6000_render.{${others.join(',')}}.json \\`);
    console.error(`     processing/*/8000_teaser.{${others.join(',')}}.json`);
    console.error(`  ./run.sh --localize --batch --langs ${others.join(',')} --render-jobs 2`);
  }
  console.error('  # then publish, or the manifest keeps reporting the old engine:');
  console.error(
    '  ./run.sh --publish-www && .ci/scripts/deploy/sync-media-to-r2.sh --solutions-only'
  );
  console.error('  .ci/scripts/deploy/purge-media-cache.sh');
  console.error('\nDo NOT silence this by widening CURRENT_ENGINE or by treating a missing');
  console.error('engine as current — that is what let the fleet drift unnoticed for months.');
  return 1;
}

/**
 * Controls matter more than cases here. This gate's failure mode is passing on a fleet it
 * should condemn, so four of the seven assertions below check that something does NOT report.
 */
function selftest(): number {
  let fails = 0;
  const chk = (name: string, got: unknown, want: unknown) => {
    if (JSON.stringify(got) === JSON.stringify(want)) console.log(`  PASS  ${name}`);
    else {
      console.error(
        `  FAIL  ${name}\n        want ${JSON.stringify(want)}\n        got  ${JSON.stringify(got)}`
      );
      fails++;
    }
  };
  const mk = (solutions: unknown) =>
    ({ generatedAt: '', baseUrl: '', tutorials: {}, solutions }) as unknown as VideoManifest;
  const asset = (engine?: string) => ({
    path: 'p',
    size: 1,
    sha256: 'h',
    ...(engine ? { engine } : {}),
  });
  const ids = (f: EngineFinding[]) => f.map((x) => `${x.slug}/${x.lang}:${x.engine}`);

  chk(
    'a stale engine is reported',
    ids(findStaleNarrations(mk({ a: { en: { mp4: asset('qwen3-tts') } } }), ['a'], ['en'])),
    ['a/en:qwen3-tts']
  );
  chk(
    'a MISSING engine is reported as stale, not skipped',
    ids(findStaleNarrations(mk({ a: { en: { mp4: asset() } } }), ['a'], ['en'])),
    ['a/en:null']
  );
  chk(
    'the current engine is NOT reported (control)',
    findStaleNarrations(mk({ a: { en: { mp4: asset('voxcpm2') } } }), ['a'], ['en']).length,
    0
  );
  chk(
    'a slug absent from the manifest is NOT reported (control — that is the other gate)',
    findStaleNarrations(mk({}), ['a'], ['en']).length,
    0
  );
  chk(
    'a locale with no mp4 asset is NOT reported (control — that is the other gate)',
    findStaleNarrations(mk({ a: { en: {} } }), ['a'], ['en']).length,
    0
  );
  chk(
    'a locale outside the requested set is NOT reported (control)',
    findStaleNarrations(mk({ a: { de: { mp4: asset('qwen3-tts') } } }), ['a'], ['en']).length,
    0
  );
  chk(
    'mixed fleet reports only the stale pairs, in slug×lang order',
    ids(
      findStaleNarrations(
        mk({
          a: { en: { mp4: asset('voxcpm2') }, de: { mp4: asset('qwen3-tts') } },
          b: { en: { mp4: asset() }, de: { mp4: asset('voxcpm2') } },
        }),
        ['a', 'b'],
        ['en', 'de']
      )
    ),
    ['a/de:qwen3-tts', 'b/en:null']
  );

  if (fails) {
    console.error(`\n✗ ${fails} self-test failure(s)`);
    return 1;
  }
  console.log('\n✓ check-solution-video-engine self-test passed');
  return 0;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exit(process.argv.includes('--selftest') ? selftest() : main());
}
