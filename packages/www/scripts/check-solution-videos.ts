#!/usr/bin/env node
/**
 * Hard-fail gate: every solution page must have its localized videos published
 * for the 10 languages Qwen3-TTS can voice. For each (slug, lang) it asserts
 * the three files the runtime player loads are present in the R2 media
 * manifest, `src/data/video-manifest.json`:
 *
 *   mp4, vertical, poster
 *   (bucket keys: videos/solutions/<lang>/<slug>[.vertical|.poster.jpg])
 *
 * ALL 13 locales now have their own solution videos. ar/et/tr used to fall back to the
 * English video because Qwen3-TTS could not voice them; VoxCPM2 narrates every locale
 * natively and all three are published, so none is exempt here any more.
 *
 * The bound video element is in SPSolutionVideo.astro via resolveSolutionVideo(slug,
 * lang); a missing manifest entry = a 404 / black player on a shipped page. The gate
 * is strict because these are deterministically produced by the video pipeline. On
 * any miss it prints the EXACT commands to fix and exits 1 (so a future
 * maintainer/agent knows the next step without guessing).
 *
 * Slugs are derived from src/pages/[lang]/solutions/<slug>.astro (one per page).
 * VIDEO_LANGS is imported from the resolver so the two never drift.
 *
 * Reads the manifest only -- does NOT check the local filesystem, so this
 * gate is unaffected by whether video files happen to be checked out
 * locally (see .ci/docs/r2-media-setup.md for the R2/CDN migration).
 */
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { isSiteLocale } from '@rediacc/locales';
import { VIDEO_LANGS } from '../src/utils/solution-video.ts';
import type { VideoManifest } from './lib/update-video-manifest.js';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const wwwRoot = path.resolve(scriptDir, '..');
const solutionsPagesDir = path.join(wwwRoot, 'src', 'pages', '[lang]', 'solutions');
const manifestPath = path.join(wwwRoot, 'src', 'data', 'video-manifest.json');

const REQUIRED_FIELDS = ['mp4', 'vertical', 'poster'] as const;

function loadManifest(): VideoManifest {
  if (!fs.existsSync(manifestPath)) {
    return { generatedAt: '', baseUrl: '', tutorials: {}, solutions: {} };
  }
  return JSON.parse(fs.readFileSync(manifestPath, 'utf8')) as VideoManifest;
}

/**
 * The REVERSE direction: what the manifest holds that VIDEO_LANGS does not ask for.
 *
 * The forward loop below iterates VIDEO_LANGS, so it is structurally blind to every
 * manifest key outside that list. Three things hide in that blind spot:
 *
 *  - A **typo'd locale key** (`pt-BR`, `zh_CN`, `jp`). Fatal. The publish wrote real objects
 *    to R2 under a key no page will ever request, so the video is unreachable and the gate
 *    says "OK" — the exact silent-fallback shape this repo has shipped before.
 *  - A locale **complete for every required slug but absent from VIDEO_LANGS**. Not fatal:
 *    this is the deliberate, documented mid-flip state (publish the manifest first, flip
 *    VIDEO_LANGS in a separate commit). Reported, because it is precisely the signal that
 *    the second commit is now safe, and nothing else in the repo surfaces it.
 *  - An **orphaned slug** the manifest carries but no page renders. Not fatal, but it is
 *    paid-for R2 storage nobody serves.
 */
// `declaredLangs` is injectable ONLY so the self-test can exercise the readyToFlip branch:
// it cannot fire in production while VIDEO_LANGS === SITE_LOCALES, and an untestable branch
// is one that silently rots until the day a 14th locale needs it.
export function reverseFindings(
  manifest: VideoManifest,
  required: string[],
  allSlugs: string[],
  declaredLangs: readonly string[] = VIDEO_LANGS
): { badKeys: string[]; readyToFlip: string[]; orphanSlugs: string[] } {
  const declared = new Set<string>(declaredLangs);
  const pages = new Set(allSlugs);
  const badKeys: string[] = [];
  const orphanSlugs: string[] = [];
  const langsSeen = new Map<string, number>();

  for (const [slug, byLang] of Object.entries(manifest.solutions ?? {})) {
    if (!pages.has(slug)) orphanSlugs.push(slug);
    for (const lang of Object.keys(byLang ?? {})) {
      if (!isSiteLocale(lang)) {
        badKeys.push(`${slug}.${lang}`);
        continue;
      }
      // Count only COMPLETE sets, and only for slugs the gate actually requires --
      // a half-published locale is not ready to flip and must not be reported as such.
      if (required.includes(slug) && missingManifestFields(manifest, slug, lang).length === 0) {
        langsSeen.set(lang, (langsSeen.get(lang) ?? 0) + 1);
      }
    }
  }

  const readyToFlip = [...langsSeen.entries()]
    .filter(([lang, n]) => !declared.has(lang) && n === required.length)
    .map(([lang]) => lang)
    .sort();

  return { badKeys: badKeys.sort(), readyToFlip, orphanSlugs: orphanSlugs.sort() };
}

function listSlugs(): string[] {
  if (!fs.existsSync(solutionsPagesDir)) return [];
  return (
    fs
      .readdirSync(solutionsPagesDir)
      .filter((f) => f.endsWith('.astro'))
      .map((f) => f.replace(/\.astro$/, ''))
      // index.astro is the solutions LISTING page, not a solution page; it
      // renders no SPSolutionVideo and has no SOLUTION_PAGES entry.
      .filter((slug) => slug !== 'index')
      .sort()
  );
}

/**
 * A slug needs manifest videos only if its page actually renders the player:
 * SolutionPage.astro emits SPSolutionVideo when the slug's SOLUTION_PAGES
 * `sections` array contains 'video' (or uses ALL_SECTIONS, which does).
 *
 * The config module cannot be imported here (it imports .svg assets, which
 * tsx cannot load), so this reads the slug's config block as text. Fail-safe:
 * a slug we cannot classify (no SOLUTION_PAGES entry, e.g. a legacy-template
 * page, or an unparseable block) is treated as video-bearing, so drift can
 * only ever FAIL the gate, never silently skip a shipped player.
 */
function slugRendersVideo(slug: string): boolean {
  const configPath = path.join(wwwRoot, 'src', 'config', 'solution-pages.ts');
  if (!fs.existsSync(configPath)) return true;
  const text = fs.readFileSync(configPath, 'utf8');
  const start = text.indexOf(`'${slug}': {`);
  if (start === -1) return true;
  // The entry ends where the next two-space-indented quoted key begins.
  const next = text.indexOf("\n  '", start);
  const block = next === -1 ? text.slice(start) : text.slice(start, next);
  if (/sections:\s*ALL_SECTIONS/.test(block)) return true;
  const sections = /sections:\s*\[([^\]]*)\]/.exec(block);
  if (!sections) return true;
  return /['"]video['"]/.test(sections[1]);
}

function missingManifestFields(manifest: VideoManifest, slug: string, lang: string): string[] {
  const entry = manifest.solutions[slug]?.[lang];
  if (!entry) {
    return REQUIRED_FIELDS.map((field) => `${slug}.${lang}.${field} (no manifest entry)`);
  }
  return REQUIRED_FIELDS.filter((field) => !entry[field]?.path).map(
    (field) => `${slug}.${lang}.${field}`
  );
}

interface Miss {
  slug: string;
  lang: string;
  missing: string[];
}

function main(): number {
  const slugs = listSlugs();
  if (slugs.length === 0) {
    console.error('✗ No solution pages found under src/pages/[lang]/solutions/');
    return 1;
  }

  const videoless = slugs.filter((slug) => !slugRendersVideo(slug));
  const required = slugs.filter((slug) => slugRendersVideo(slug));
  // Never truncate silently: name every slug the gate is NOT checking.
  for (const slug of videoless) {
    console.log(`↷ ${slug}: no 'video' section in SOLUTION_PAGES, videos not required`);
  }

  const manifest = loadManifest();
  const misses: Miss[] = [];
  let checked = 0;
  for (const slug of required) {
    for (const lang of VIDEO_LANGS) {
      checked++;
      const missing = missingManifestFields(manifest, slug, lang);
      if (missing.length) {
        misses.push({ slug, lang, missing });
      }
    }
  }

  const { badKeys, readyToFlip, orphanSlugs } = reverseFindings(manifest, required, slugs);
  for (const lang of readyToFlip) {
    console.log(
      `→ ${lang}: complete in the manifest for all ${required.length} required slugs but NOT in ` +
        `VIDEO_LANGS. This is the safe point to add it (solution-video.ts:34).`
    );
  }
  for (const slug of orphanSlugs) {
    console.log(`↷ ${slug}: in the manifest but no solution page renders it (orphaned R2 objects)`);
  }

  if (misses.length === 0 && badKeys.length === 0) {
    console.log(
      `✓ Solution videos OK: ${required.length} slugs × ${VIDEO_LANGS.length} langs ` +
        `(${checked} sets present` +
        (videoless.length ? `; ${videoless.length} videoless slug(s) skipped` : '') +
        `)`
    );
    return 0;
  }

  if (badKeys.length) {
    console.error(
      `✗ ${badKeys.length} manifest entr${badKeys.length === 1 ? 'y' : 'ies'} keyed by a ` +
        `non-site locale. No page can ever request these, so the video is unreachable:\n`
    );
    for (const k of badKeys) console.error(`  ${k}`);
    console.error(
      '\nFix the locale key at its source (the publish step that wrote it), then regenerate\n' +
        'the manifest. Do not add the key to SITE_LOCALES to silence this.\n'
    );
    if (misses.length === 0) return 1;
  }

  console.error(
    `✗ Missing localized solution videos (${misses.length} incomplete slug×lang sets)\n`
  );
  const byLang = new Map<string, Miss[]>();
  for (const m of misses) {
    if (!byLang.has(m.lang)) byLang.set(m.lang, []);
    byLang.get(m.lang)!.push(m);
  }
  for (const [lang, list] of [...byLang.entries()].sort()) {
    console.error(`[${lang}]`);
    for (const m of list) {
      console.error(`  ${m.slug}`);
      for (const f of m.missing) console.error(`    missing: ${f}`);
    }
    console.error('');
  }
  // Actionable remediation -- exactly what to run next.
  const langsAffected = [...byLang.keys()].sort().join(',');
  const slugsAffected = [...new Set(misses.map((m) => m.slug))].sort();
  console.error('To fix (from the repo root):');
  console.error('  cd private/growth/video_pipeline');
  console.error(`  # 1) Ensure the source videos exist (regenerate any missing localizations):`);
  console.error(
    `  ./run.sh --batch --localize --langs ${langsAffected || 'de,es,fr,it,pt,ru,ja,ko,zh'}`
  );
  if (slugsAffected.length <= 5) {
    for (const s of slugsAffected) {
      console.error(
        `  #    (single slug: ./run.sh --slug ${s} --localize --langs ${langsAffected})`
      );
    }
  }
  console.error(
    '  # 2) Publish them (uploads mp4 + vertical + poster to R2, updates the manifest):'
  );
  console.error('  ./run.sh --publish-www');
  console.error('  # 3) Re-run this check.');
  return 1;
}

/**
 * `--selftest` exercises reverseFindings, including the readyToFlip branch that CANNOT fire
 * in production while VIDEO_LANGS === SITE_LOCALES. Without this the branch would sit
 * unexercised until a 14th locale needed it, which is when a latent bug in it would surface.
 * Four of the seven cases are controls that must NOT report.
 */
function selftest(): number {
  const F = ['mp4', 'vertical', 'poster'] as const;
  const full = () => Object.fromEntries(F.map((f) => [f, { path: `x.${f}` }]));
  const mk = (solutions: unknown) =>
    ({ generatedAt: '', baseUrl: '', tutorials: {}, solutions }) as unknown as VideoManifest;
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

  chk(
    'typo locale key is reported',
    reverseFindings(mk({ a: { en: full(), 'pt-BR': full() } }), ['a'], ['a']).badKeys,
    ['a.pt-BR']
  );
  chk(
    'all-valid keys report nothing (control)',
    reverseFindings(mk({ a: { en: full(), de: full() } }), ['a'], ['a']).badKeys,
    []
  );
  chk(
    'manifest slug with no page is reported',
    reverseFindings(mk({ a: { en: full() }, ghost: { en: full() } }), ['a'], ['a']).orphanSlugs,
    ['ghost']
  );
  chk(
    'complete-but-undeclared locale is ready to flip',
    reverseFindings(
      mk({ a: { en: full(), de: full() }, b: { en: full(), de: full() } }),
      ['a', 'b'],
      ['a', 'b'],
      ['en']
    ).readyToFlip,
    ['de']
  );
  chk(
    'partially-published locale is NOT ready to flip (control)',
    reverseFindings(
      mk({ a: { en: full(), de: full() }, b: { en: full() } }),
      ['a', 'b'],
      ['a', 'b'],
      ['en']
    ).readyToFlip,
    []
  );
  // The fixture shape matters here: fields are objects carrying `.path`, not strings. With
  // string fields this control passed vacuously, because EVERY field looked absent.
  chk(
    'locale missing one field is NOT ready to flip (control)',
    reverseFindings(mk({ a: { en: full(), de: { mp4: { path: 'x' } } } }), ['a'], ['a'], ['en'])
      .readyToFlip,
    []
  );
  chk(
    'declared locale is NOT announced (control)',
    reverseFindings(mk({ a: { en: full(), de: full() } }), ['a'], ['a'], ['en', 'de']).readyToFlip,
    []
  );

  if (fails) {
    console.error(`\n✗ ${fails} self-test failure(s)`);
    return 1;
  }
  console.log('\n✓ check-solution-videos self-test passed');
  return 0;
}

// Run only as the entry point. Bare `process.exit(main())` at module scope meant any
// `import` of this file ran the whole gate and exited the importer, which is why
// reverseFindings could not be unit-tested until now.
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exit(process.argv.includes('--selftest') ? selftest() : main());
}
