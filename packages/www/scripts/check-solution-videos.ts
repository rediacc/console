#!/usr/bin/env node
/**
 * Hard-fail gate: every solution page must have its localized videos present for
 * the 10 languages Qwen3-TTS can voice. For each (slug, lang) it asserts:
 *
 *   public/assets/videos/solutions/<lang>/<slug>.mp4
 *   public/assets/videos/solutions/<lang>/<slug>.vertical.mp4
 *   public/assets/videos/solutions/<lang>/<slug>.poster.jpg
 *
 * The site's 3 remaining locales (ar/et/tr) intentionally fall back to the English
 * video at render time (see src/utils/solution-video.ts), so they are NOT required
 * here — and we never duplicate the English files for them.
 *
 * The bound video element is in SPSolutionVideo.astro via resolveSolutionVideo(slug,
 * lang); a missing file = a 404 / black player on a shipped page. The gate is strict
 * because these are deterministically produced by the video pipeline. On any miss it
 * prints the EXACT commands to fix and exits 1 (so a future maintainer/agent knows the
 * next step without guessing).
 *
 * Slugs are derived from src/pages/[lang]/solutions/<slug>.astro (one per page).
 * VIDEO_LANGS is imported from the resolver so the two never drift.
 */
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { VIDEO_LANGS } from '../src/utils/solution-video.ts';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const wwwRoot = path.resolve(scriptDir, '..');
const solutionsPagesDir = path.join(wwwRoot, 'src', 'pages', '[lang]', 'solutions');
const videosDir = path.join(wwwRoot, 'public', 'assets', 'videos', 'solutions');

function listSlugs(): string[] {
  if (!fs.existsSync(solutionsPagesDir)) return [];
  return fs
    .readdirSync(solutionsPagesDir)
    .filter((f) => f.endsWith('.astro'))
    .map((f) => f.replace(/\.astro$/, ''))
    .sort();
}

function expectedFiles(lang: string, slug: string): string[] {
  const base = path.join(videosDir, lang, slug);
  return [`${base}.mp4`, `${base}.vertical.mp4`, `${base}.poster.jpg`];
}

interface Miss {
  slug: string;
  lang: string;
  files: string[];
}

function main(): number {
  const slugs = listSlugs();
  if (slugs.length === 0) {
    console.error('✗ No solution pages found under src/pages/[lang]/solutions/');
    return 1;
  }

  const misses: Miss[] = [];
  let checked = 0;
  for (const slug of slugs) {
    for (const lang of VIDEO_LANGS) {
      checked++;
      const missing = expectedFiles(lang, slug).filter((p) => !fs.existsSync(p));
      if (missing.length) {
        misses.push({ slug, lang, files: missing.map((p) => path.relative(wwwRoot, p)) });
      }
    }
  }

  if (misses.length === 0) {
    console.log(
      `✓ Solution videos OK: ${slugs.length} slugs × ${VIDEO_LANGS.length} langs ` +
        `(${checked} sets present; ar/et/tr fall back to en by design)`
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
      for (const f of m.files) console.error(`    missing: ${f}`);
    }
    console.error('');
  }
  // Actionable remediation — exactly what to run next.
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
    '  # 2) Publish them (copies mp4 + vertical + generates posters) into www public/:'
  );
  console.error('  ./run.sh --publish-www');
  console.error('  # 3) git add packages/www/public/assets/videos/solutions && re-run this check.');
  console.error(
    '\n  Note: ar/et/tr are intentional English fallbacks (src/utils/solution-video.ts) and are NOT generated.'
  );
  return 1;
}

process.exit(main());
