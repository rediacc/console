#!/usr/bin/env -S npx tsx
/**
 * Publish a rendered tutorial video (and its sidecars) to R2, updating the
 * committed manifest. Separate from generate-tutorial-video.ts on purpose:
 * generation never touches the network (no R2 creds needed to iterate
 * locally — re-record, preview via `npm run dev`, repeat), and this script
 * is the explicit "ready to ship" step run afterward.
 *
 * Usage:
 *   npm run tutorials:publish-video -- --cast tutorial-monitoring --lang en
 *   npm run tutorials:publish-video -- --cast tutorial-monitoring --all-langs
 *   npm run tutorials:publish-video -- --all
 *
 * Requires CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID / CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY /
 * CLOUDFLARE_R2_MEDIA_ENDPOINT in the environment (see .ci/docs/r2-media-setup.md).
 */

import { execFileSync } from 'node:child_process';
import { existsSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadManifest, saveManifest, setManifestEntryOn } from './lib/update-video-manifest.ts';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.join(__dirname, '../../..');
const TUTORIALS_DIR = path.join(__dirname, '../public/assets/tutorials/video');
const UPLOAD_SCRIPT = path.join(REPO_ROOT, '.ci/scripts/deploy/upload-media-to-r2.sh');

const FIELDS: { field: string; suffix: (castKey: string, lang: string) => string }[] = [
  { field: 'mp4', suffix: (castKey) => `${castKey}.mp4` },
  { field: 'poster', suffix: (castKey, lang) => `${castKey}.${lang}.poster.jpg` },
  { field: 'vtt', suffix: (castKey, lang) => `${castKey}.${lang}.vtt` },
  { field: 'chaptersVtt', suffix: (castKey, lang) => `${castKey}.${lang}.chapters.vtt` },
  { field: 'wordsJson', suffix: (castKey, lang) => `${castKey}.${lang}.words.json` },
];

function parseArgs(argv: string[]): {
  cast?: string;
  lang?: string;
  allLangs: boolean;
  all: boolean;
} {
  const out: { cast?: string; lang?: string; allLangs: boolean; all: boolean } = {
    allLangs: false,
    all: false,
  };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--cast') out.cast = argv[++i];
    else if (argv[i] === '--lang') out.lang = argv[++i];
    else if (argv[i] === '--all-langs') out.allLangs = true;
    else if (argv[i] === '--all') out.all = true;
    else {
      console.error(`Unknown argument: ${argv[i]}`);
      process.exit(1);
    }
  }
  return out;
}

function listLangDirs(): string[] {
  return readdirSync(TUTORIALS_DIR, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name);
}

function listCastKeys(lang: string): string[] {
  const dir = path.join(TUTORIALS_DIR, lang);
  if (!existsSync(dir)) return [];
  return readdirSync(dir)
    .filter((f) => f.endsWith('.mp4'))
    .map((f) => f.slice(0, -'.mp4'.length));
}

/**
 * Where upload-media-to-r2.sh appends manifest tuples instead of rewriting the
 * manifest per file. A full sweep is 1170 files; updating per file meant 1170
 * cold `npx tsx` starts each rewriting a 440 KB committed JSON, which dominated
 * the wall clock. Uploads and their HEAD readbacks are unchanged -- only the
 * bookkeeping moves to the end.
 */
let deferFile: string | null = null;

/** Apply every deferred tuple against ONE load/save of the manifest. */
function applyDeferredManifest(): number {
  if (!deferFile || !existsSync(deferFile)) return 0;
  const rows = readFileSync(deferFile, 'utf8').split('\n').filter(Boolean);
  if (rows.length === 0) return 0;
  const manifest = loadManifest();
  for (const row of rows) {
    const [kind, key, lang, field, remotePath, size, sha256, engine] = row.split('\t');
    setManifestEntryOn(manifest, kind as 'tutorials' | 'solutions', key, lang, field, {
      path: remotePath,
      size: Number(size),
      sha256,
      ...(engine ? { engine } : {}),
    });
  }
  saveManifest(manifest);
  return rows.length;
}

function publishOne(castKey: string, lang: string): void {
  const langDir = path.join(TUTORIALS_DIR, lang);
  let uploaded = 0;
  for (const { field, suffix } of FIELDS) {
    const filePath = path.join(langDir, suffix(castKey, lang));
    if (!existsSync(filePath)) {
      console.log(`  skip ${field} (not present: ${suffix(castKey, lang)})`);
      continue;
    }
    console.log(`  uploading ${field}...`);
    execFileSync(
      'bash',
      [
        UPLOAD_SCRIPT,
        '--kind',
        'tutorials',
        '--key',
        castKey,
        '--lang',
        lang,
        '--field',
        field,
        '--file',
        filePath,
        ...(deferFile ? ['--defer-manifest', deferFile] : []),
      ],
      { stdio: 'inherit' }
    );
    uploaded++;
  }
  console.log(`${castKey} (${lang}): ${uploaded} file(s) published`);
}

function main(): void {
  const args = parseArgs(process.argv.slice(2));

  for (const required of [
    'CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID',
    'CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY',
    'CLOUDFLARE_R2_MEDIA_ENDPOINT',
  ]) {
    if (!process.env[required]) {
      console.error(`Missing required env var: ${required} (see .ci/docs/r2-media-setup.md)`);
      process.exit(1);
    }
  }

  // Batch the manifest for the bulk modes only. A single --cast/--lang publish
  // keeps the per-file path, so the common interactive case is unchanged and the
  // batch code cannot silently become the only tested route.
  const bulk = args.all || args.allLangs;
  let tmpDir: string | null = null;
  if (bulk) {
    tmpDir = mkdtempSync(path.join(tmpdir(), 'publish-manifest-'));
    deferFile = path.join(tmpDir, 'entries.tsv');
    writeFileSync(deferFile, '');
  }
  const finishBatch = (): void => {
    if (!bulk) return;
    const applied = applyDeferredManifest();
    console.log(`manifest: ${applied} entr(ies) written in one pass`);
    if (tmpDir) rmSync(tmpDir, { recursive: true, force: true });
  };

  if (args.all) {
    for (const lang of listLangDirs()) {
      for (const castKey of listCastKeys(lang)) {
        publishOne(castKey, lang);
      }
    }
    finishBatch();
    return;
  }

  if (!args.cast) {
    console.error('Usage: --cast <castKey> [--lang <lang> | --all-langs]  or  --all');
    process.exit(1);
  }

  if (args.allLangs) {
    for (const lang of listLangDirs()) {
      if (listCastKeys(lang).includes(args.cast)) {
        publishOne(args.cast, lang);
      }
    }
    finishBatch();
    return;
  }

  if (!args.lang) {
    console.error('Specify --lang <lang> or --all-langs alongside --cast');
    process.exit(1);
  }
  publishOne(args.cast, args.lang);
}

main();
