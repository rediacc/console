#!/usr/bin/env -S npx tsx
/**
 * Read-modify-write helper for packages/www/src/data/video-manifest.json.
 *
 * This is the single place that knows the manifest's on-disk shape, reused
 * by:
 *   - generate-video-manifest.ts (one-time/rebuild: scans all local files)
 *   - publish-tutorial-video-to-r2.ts (per-tutorial publish, TS import)
 *   - .ci/scripts/deploy/upload-media-to-r2.sh (per-file publish from bash,
 *     via the CLI entry point below — also used by private/growth/video_pipeline/
 *     publish.py for solution videos, which can't import a TS module directly)
 *
 * Manifest shape:
 *   {
 *     "generatedAt": "<ISO8601>",
 *     "baseUrl": "https://media.rediacc.com",
 *     "tutorials": { "<castKey>": { "<lang>": { "<field>": { path, size, sha256 } } } },
 *     "solutions": { "<slug>":    { "<lang>": { "<field>": { path, size, sha256 } } } }
 *   }
 *
 * "field" is one of: mp4, poster, vtt, chaptersVtt, wordsJson (tutorials) or
 * mp4, vertical, poster (solutions). Bucket keys never include an "assets/"
 * prefix (see .ci/docs/r2-media-setup.md #1 — the backfill in Phase 1 mirrors
 * public/assets/{tutorials/video,videos}/... minus BOTH "public/" and "assets/").
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const MANIFEST_PATH = path.join(__dirname, '../../src/data/video-manifest.json');
export const CDN_BASE_URL = 'https://media.rediacc.com';

export type MediaKind = 'tutorials' | 'solutions';

export interface ManifestAsset {
  path: string;
  size: number;
  sha256: string;
}

export interface VideoManifest {
  generatedAt: string;
  baseUrl: string;
  tutorials: Record<string, Record<string, Record<string, ManifestAsset>>>;
  solutions: Record<string, Record<string, Record<string, ManifestAsset>>>;
}

export function loadManifest(): VideoManifest {
  if (!existsSync(MANIFEST_PATH)) {
    return {
      generatedAt: new Date().toISOString(),
      baseUrl: CDN_BASE_URL,
      tutorials: {},
      solutions: {},
    };
  }
  return JSON.parse(readFileSync(MANIFEST_PATH, 'utf8')) as VideoManifest;
}

export function saveManifest(manifest: VideoManifest): void {
  manifest.generatedAt = new Date().toISOString();
  mkdirSync(path.dirname(MANIFEST_PATH), { recursive: true });
  writeFileSync(MANIFEST_PATH, `${JSON.stringify(manifest, null, 2)}\n`, 'utf8');
}

/**
 * Set a single asset entry (e.g. tutorials.tutorial-monitoring.en.mp4) and
 * persist the manifest immediately. Safe to call repeatedly — read-modify-
 * write, no batching required for the volumes involved here (a few hundred
 * KB of JSON total).
 */
export function setManifestEntry(
  kind: MediaKind,
  key: string,
  lang: string,
  field: string,
  asset: ManifestAsset
): void {
  const manifest = loadManifest();
  manifest[kind][key] ??= {};
  manifest[kind][key][lang] ??= {};
  manifest[kind][key][lang][field] = asset;
  saveManifest(manifest);
}

// ─── CLI entry point (used by upload-media-to-r2.sh and Python callers) ───
// Usage: npx tsx update-video-manifest.ts --kind tutorials --key <castKey> \
//          --lang <lang> --field mp4 --path <bucket-key> --size <bytes> --sha256 <hex>
function parseCliArgs(argv: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (let i = 0; i < argv.length; i += 2) {
    const flag = argv[i];
    if (!flag.startsWith('--')) throw new Error(`Expected flag, got "${flag}"`);
    out[flag.slice(2)] = argv[i + 1];
  }
  return out;
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1]);
if (isMain) {
  const args = parseCliArgs(process.argv.slice(2));
  const required = ['kind', 'key', 'lang', 'field', 'path', 'size', 'sha256'];
  const missing = required.filter((r) => !(r in args));
  if (missing.length > 0) {
    console.error(`Missing required arguments: ${missing.join(', ')}`);
    process.exit(1);
  }
  if (args.kind !== 'tutorials' && args.kind !== 'solutions') {
    console.error(`--kind must be "tutorials" or "solutions", got "${args.kind}"`);
    process.exit(1);
  }
  setManifestEntry(args.kind, args.key, args.lang, args.field, {
    path: args.path,
    size: Number(args.size),
    sha256: args.sha256,
  });
  console.log(
    `Updated manifest: ${args.kind}.${args.key}.${args.lang}.${args.field} -> ${args.path}`
  );
}
