#!/usr/bin/env -S npx tsx
/**
 * Build packages/www/src/data/video-manifest.json from scratch by scanning
 * the local tutorial/solution video files on disk.
 *
 * Two uses:
 *   1. One-time backfill (this migration): the 642 files were already synced
 *      to R2 by .ci/scripts/deploy/sync-media-to-r2.sh (Phase 1, already
 *      verified byte-identical), so this just records their existing
 *      size/sha256 from the LOCAL copies — no re-upload, no re-verification
 *      against R2 needed.
 *   2. Disaster recovery: if the manifest is ever lost/corrupted and local
 *      files are still present (or restored via sync-media-from-r2.sh),
 *      re-run this to rebuild it deterministically.
 *
 * Does NOT touch R2 — pure local filesystem scan + manifest write. For
 * publishing a NEWLY re-recorded tutorial/solution (upload + manifest
 * update together), use publish-tutorial-video-to-r2.ts /
 * .ci/scripts/deploy/upload-media-to-r2.sh instead.
 *
 * videos/user-guide/ is deliberately excluded — those are E2E recordings
 * injected post-build by .ci/scripts/docs/inject-e2e-videos.sh from a CI
 * artifact, not part of this migration (see remark-video-embed.ts).
 */

import { createHash } from 'node:crypto';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  type ManifestAsset,
  saveManifest,
  type VideoManifest,
} from './lib/update-video-manifest.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const WWW_PUBLIC = path.join(__dirname, '../public/assets');
const TUTORIALS_DIR = path.join(WWW_PUBLIC, 'tutorials/video');
const SOLUTIONS_DIR = path.join(WWW_PUBLIC, 'videos/solutions');

function hashFile(filePath: string): { size: number; sha256: string } {
  const buf = readFileSync(filePath);
  return { size: buf.length, sha256: createHash('sha256').update(buf).digest('hex') };
}

function asset(bucketKey: string, absPath: string): ManifestAsset {
  const { size, sha256 } = hashFile(absPath);
  return { path: bucketKey, size, sha256 };
}

function listLangDirs(root: string): string[] {
  return readdirSync(root, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name);
}

function scanTutorials(manifest: VideoManifest): { files: number } {
  let files = 0;
  if (!statOrNull(TUTORIALS_DIR)) return { files };
  for (const lang of listLangDirs(TUTORIALS_DIR)) {
    const langDir = path.join(TUTORIALS_DIR, lang);
    const entries = readdirSync(langDir);
    const mp4s = entries.filter((f) => f.endsWith('.mp4'));
    for (const mp4 of mp4s) {
      const castKey = mp4.slice(0, -'.mp4'.length);
      const fields: Array<[string, string]> = [
        ['mp4', `${castKey}.mp4`],
        ['poster', `${castKey}.${lang}.poster.jpg`],
        ['vtt', `${castKey}.${lang}.vtt`],
        ['chaptersVtt', `${castKey}.${lang}.chapters.vtt`],
        ['wordsJson', `${castKey}.${lang}.words.json`],
      ];
      manifest.tutorials[castKey] ??= {};
      manifest.tutorials[castKey][lang] ??= {};
      for (const [field, filename] of fields) {
        const absPath = path.join(langDir, filename);
        if (!statOrNull(absPath)) continue; // sidecar missing for this locale — skip, don't fabricate
        const bucketKey = `tutorials/video/${lang}/${filename}`;
        manifest.tutorials[castKey][lang][field] = asset(bucketKey, absPath);
        files++;
      }
    }
  }
  return { files };
}

function scanSolutions(manifest: VideoManifest): { files: number } {
  let files = 0;
  if (!statOrNull(SOLUTIONS_DIR)) return { files };
  for (const lang of listLangDirs(SOLUTIONS_DIR)) {
    const langDir = path.join(SOLUTIONS_DIR, lang);
    const entries = readdirSync(langDir);
    const mp4s = entries.filter((f) => f.endsWith('.mp4') && !f.endsWith('.vertical.mp4'));
    for (const mp4 of mp4s) {
      const slug = mp4.slice(0, -'.mp4'.length);
      const fields: Array<[string, string]> = [
        ['mp4', `${slug}.mp4`],
        ['vertical', `${slug}.vertical.mp4`],
        ['poster', `${slug}.poster.jpg`],
      ];
      manifest.solutions[slug] ??= {};
      manifest.solutions[slug][lang] ??= {};
      for (const [field, filename] of fields) {
        const absPath = path.join(langDir, filename);
        if (!statOrNull(absPath)) continue;
        const bucketKey = `videos/solutions/${lang}/${filename}`;
        manifest.solutions[slug][lang][field] = asset(bucketKey, absPath);
        files++;
      }
    }
  }
  return { files };
}

function statOrNull(p: string) {
  try {
    return statSync(p);
  } catch {
    return null;
  }
}

function main(): void {
  const manifest: VideoManifest = {
    generatedAt: new Date().toISOString(),
    baseUrl: 'https://media.rediacc.com',
    tutorials: {},
    solutions: {},
  };

  const t = scanTutorials(manifest);
  const s = scanSolutions(manifest);
  saveManifest(manifest);

  const tutorialCount = Object.keys(manifest.tutorials).length;
  const solutionCount = Object.keys(manifest.solutions).length;
  console.log(
    `Wrote video-manifest.json: ${tutorialCount} tutorials (${t.files} files), ` +
      `${solutionCount} solutions (${s.files} files)`
  );
}

main();
