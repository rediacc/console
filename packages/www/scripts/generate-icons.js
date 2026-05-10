#!/usr/bin/env node

/**
 * Icon generation for www, web, and desktop packages.
 *
 * Sources of truth:
 *   - bolt-only:  packages/www/public/favicon.svg          (small browser favicons)
 *   - full logo:  packages/www/public/assets/images/icon-rediacc.svg  (apple-touch + desktop)
 *
 * packages/web/public/favicon.svg is mirrored from www's bolt-only SVG.
 *
 * Usage:  node packages/www/scripts/generate-icons.js
 * Requires: sharp (npm). Optional: icotool (Windows multi-res .ico for desktop).
 */

import { execFileSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdtempSync, renameSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

let sharp;
try {
  ({ default: sharp } = await import('sharp'));
} catch {
  console.error('Sharp not installed. Run: npm install sharp');
  process.exit(1);
}

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..', '..', '..');

const boltSvg = join(repoRoot, 'packages/www/public/favicon.svg');
const fullSvg = join(repoRoot, 'packages/www/public/assets/images/icon-rediacc.svg');

for (const src of [boltSvg, fullSvg]) {
  if (!existsSync(src)) {
    console.error('Missing source SVG:', src);
    process.exit(1);
  }
}

const renders = [
  { src: boltSvg, out: 'packages/www/public/favicon-16x16.png', size: 16 },
  { src: boltSvg, out: 'packages/www/public/favicon-32x32.png', size: 32 },
  { src: fullSvg, out: 'packages/www/public/apple-touch-icon.png', size: 180 },
  { src: fullSvg, out: 'packages/www/public/android-chrome-192x192.png', size: 192 },
  { src: fullSvg, out: 'packages/www/public/android-chrome-512x512.png', size: 512 },
  { src: fullSvg, out: 'packages/desktop/resources/icon.png', size: 512 },
];

console.log('Rendering PNGs');
for (const { src, out, size } of renders) {
  const outPath = join(repoRoot, out);
  await sharp(src).resize(size, size).png({ quality: 90, compressionLevel: 9 }).toFile(outPath);
  console.log(`  ${out} (${size}x${size})`);
}

// favicon.ico: sharp can't emit ICO directly, so emit a 32x32 PNG with .ico extension.
// Browsers accept this; matches the previous generator's convention.
const faviconIco = join(repoRoot, 'packages/www/public/favicon.ico');
const tmpPng = `${faviconIco}.tmp.png`;
await sharp(boltSvg).resize(32, 32).png().toFile(tmpPng);
renameSync(tmpPng, faviconIco);
console.log('  packages/www/public/favicon.ico (32x32 PNG-as-ICO)');

// Mirror bolt SVG into web package so both consoles stay aligned.
const webSvg = join(repoRoot, 'packages/web/public/favicon.svg');
copyFileSync(boltSvg, webSvg);
console.log('  packages/web/public/favicon.svg (mirrored from www)');

// Desktop icon.ico — true multi-res Windows ICO via icotool (icoutils package).
const desktopIco = join(repoRoot, 'packages/desktop/resources/icon.ico');
let icotoolAvailable = true;
try {
  execFileSync('icotool', ['--version'], { stdio: 'ignore' });
} catch {
  icotoolAvailable = false;
}

if (icotoolAvailable) {
  const tmp = mkdtempSync(join(tmpdir(), 'rdc-ico-'));
  const sizes = [16, 32, 48, 64, 128, 256];
  const pngPaths = [];
  for (const s of sizes) {
    const p = join(tmp, `${s}.png`);
    await sharp(fullSvg).resize(s, s).png().toFile(p);
    pngPaths.push(p);
  }
  execFileSync('icotool', ['-c', '-o', desktopIco, ...pngPaths], { stdio: 'inherit' });
  rmSync(tmp, { recursive: true, force: true });
  console.log(`  packages/desktop/resources/icon.ico (${sizes.join('/')} multi-res)`);
} else {
  console.warn(
    '  packages/desktop/resources/icon.ico SKIPPED (icotool not installed; apt install icoutils)'
  );
}

console.log('Done.');
