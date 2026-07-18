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
 * The site's 3 remaining locales (ar/et/tr) intentionally fall back to the English
 * video at render time (see src/utils/solution-video.ts), so they are NOT required
 * here — and we never duplicate the English files for them.
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

  if (misses.length === 0) {
    console.log(
      `✓ Solution videos OK: ${required.length} slugs × ${VIDEO_LANGS.length} langs ` +
        `(${checked} sets present; ar/et/tr fall back to en by design` +
        (videoless.length ? `; ${videoless.length} videoless slug(s) skipped` : '') +
        `)`
    );
    return 0;
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
  console.error(
    '\n  Note: ar/et/tr are intentional English fallbacks (src/utils/solution-video.ts) and are NOT generated.'
  );
  return 1;
}

process.exit(main());
