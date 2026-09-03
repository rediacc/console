#!/usr/bin/env tsx
/**
 * A page may not link the video player's stylesheet unless it contains a player.
 *
 * THE DEFECT. `TutorialVideoPlayer.tsx` imports `plyr/dist/plyr.css` at module scope.
 * Astro's page-CSS hoisting reads every chunk's `viteMetadata.importedCss` and attaches
 * client-chunk CSS to every page carrying that script -- DYNAMIC IMPORT BOUNDARIES ARE
 * IRRELEVANT TO IT. So the sheet is linked wherever the HYDRATOR is, not wherever a
 * PLAYER is. Measured on 2026-09-03: 1,366 pages link it, 572 have a mount, and 794
 * carry 37,018 B raw / 6,087 B gzip of render-blocking CSS for a player that does not
 * exist on them. All 794 are docs pages.
 *
 * WHY DETECTION IS BY CONTENT AND NOT BY FILENAME. A rename or a re-bundle would make a
 * filename-matching gate silently blind, and this gate's whole subject is a file whose
 * name is a content hash. The markers were chosen by measurement: `.tvp-root` and
 * `.tvp-toolbar` also appear in a NON-player bundle, so matching on those would
 * over-report; `.plyr__control` and `.tvp-caption-word` each appear in exactly one
 * built asset.
 *
 * THE FLOORS EXIST BECAUSE THE ASSERTION IS A NEGATIVE. "No page links it without a
 * mount" is satisfied perfectly by a broken scanner, an absent build, or a deleted
 * stylesheet. Six floors make each of those a loud refusal instead of a green run, and
 * F6 is the positive half: the stylesheet must still REACH the player through a JS
 * chunk, or deleting plyr outright would pass this gate.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';

const ROOT = process.env.PLAYER_CSS_ROOT ?? process.cwd();
const DIST = path.join(ROOT, 'packages/www/dist');

/** Both spellings of a mount, token-matched inside the class attribute. */
const MOUNT =
  /class="[^"]*\b(?:video-player-mount|tutorial-video-container)\b[^"]*"[^>]*data-video-src/;
/** Content markers. Each appears in exactly one built asset; see the header. */
const MARKERS = ['.plyr__control', '.tvp-caption-word'];
const LINK = /<link[^>]+rel="stylesheet"[^>]+href="([^"]+\.css)"/g;

const MIN_PAGES = 1000;
const MIN_LINKS = 1000;
const MIN_MOUNTS = 500;

function walk(dir: string, ext: string, out: string[] = []): string[] {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const e of entries) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, ext, out);
    else if (e.name.endsWith(ext)) out.push(p);
  }
  return out;
}

interface Result {
  offenders: string[];
  pages: number;
  links: number;
  mounts: number;
  playerCss: string[];
  refusal?: string;
}

export function scan(dist: string): Result {
  const r: Result = { offenders: [], pages: 0, links: 0, mounts: 0, playerCss: [] };
  if (!fs.existsSync(dist)) {
    r.refusal = `F1: no build at ${dist}. Run \`npm run build:www\` -- this gate reads the OUTPUT, so with no dist it would report a clean tree having inspected nothing.`;
    return r;
  }

  // Which built stylesheets are the player's, by content.
  const cssFiles = walk(dist, '.css');
  const found = new Set<string>();
  for (const f of cssFiles) {
    const t = fs.readFileSync(f, 'utf8');
    for (const m of MARKERS) if (t.includes(m)) found.add(m);
    if (MARKERS.some((m) => t.includes(m))) r.playerCss.push('/' + path.relative(dist, f));
  }
  if (found.size !== MARKERS.length) {
    r.refusal = `F4: expected every marker ${MARKERS.join(', ')} in some built stylesheet, found ${[...found].join(', ') || 'none'}. The player's CSS is absent from the build entirely, which is a worse defect than the one this gate looks for and must not wear its green.`;
    return r;
  }

  const pages = walk(dist, '.html');
  r.pages = pages.length;
  if (r.pages < MIN_PAGES) {
    r.refusal = `F2: scanned ${r.pages} page(s), floor ${MIN_PAGES}. The walk lost the corpus; refusing a verdict.`;
    return r;
  }

  const playerSet = new Set(r.playerCss);
  for (const p of pages) {
    const t = fs.readFileSync(p, 'utf8');
    const hasMount = MOUNT.test(t);
    if (hasMount) r.mounts++;
    let linksPlayer = false;
    LINK.lastIndex = 0;
    for (const m of t.matchAll(LINK)) {
      r.links++;
      if (playerSet.has(m[1])) linksPlayer = true;
    }
    if (linksPlayer && !hasMount) r.offenders.push('/' + path.relative(dist, p));
  }

  if (r.links < MIN_LINKS) {
    r.refusal = `F3: saw ${r.links} stylesheet link(s), floor ${MIN_LINKS}. The link scanner is broken, so "no page links the player" would mean nothing.`;
    return r;
  }
  if (r.mounts < MIN_MOUNTS) {
    r.refusal = `F5: found ${r.mounts} page(s) with a mount, floor ${MIN_MOUNTS}. The mount markup changed shape, which would silently make every page look clean.`;
    return r;
  }

  // F6, the positive half: the styles must still REACH the player.
  const js = walk(dist, '.js');
  const jsText = js.map((f) => fs.readFileSync(f, 'utf8')).join('\n');
  const unreferenced = r.playerCss.filter((c) => !jsText.includes(path.basename(c)));
  if (unreferenced.length === r.playerCss.length) {
    r.refusal = `F6: no JS chunk names any player stylesheet (${r.playerCss.join(', ')}). Nothing loads them, so the pages are "clean" because the player has no styles at all -- which deleting plyr outright would also achieve.`;
    return r;
  }
  return r;
}

function selftest(): number {
  let bad = 0;
  const check = (name: string, ok: boolean, detail = '') => {
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}`);
    if (!ok) {
      bad++;
      if (detail) console.error(`        ${detail}`);
    }
  };
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'player-css-'));
  const d = path.join(tmp, 'dist');
  const mk = (rel: string, body: string) => {
    fs.mkdirSync(path.join(d, path.dirname(rel)), { recursive: true });
    fs.writeFileSync(path.join(d, rel), body);
  };
  const page = (link: boolean, mount: boolean) =>
    `<html><head>${link ? '<link rel="stylesheet" href="/a/player.css">' : ''}</head><body>` +
    `${mount ? '<div class="x video-player-mount y" data-video-src="v.mp4"></div>' : ''}</body></html>`;

  mk('a/player.css', '.plyr__control{}.tvp-caption-word{}');
  mk('a/other.css', '.tvp-root{}.tvp-toolbar{}'); // the OVER-MATCH control
  mk('a/app.js', 'import"./player.css";');
  for (let i = 0; i < MIN_PAGES + 5; i++) mk(`p${i}.html`, page(true, true));
  // P4: a page linking the NON-player sheet with no mount must NOT be reported.
  mk(
    'over.html',
    '<html><head><link rel="stylesheet" href="/a/other.css"></head><body></body></html>'
  );
  let r = scan(d);
  check(
    'a clean corpus reports no offender',
    !r.refusal && r.offenders.length === 0,
    r.refusal ?? r.offenders.slice(0, 2).join(', ')
  );
  check(
    'P4 CONTROL: a sheet with .tvp-root but neither marker is not a player sheet',
    !r.offenders.includes('/over.html')
  );

  // P1: the plant.
  mk('bad.html', page(true, false));
  r = scan(d);
  check(
    'PLANT: a page linking the player sheet with NO mount is reported',
    r.offenders.includes('/bad.html'),
    r.refusal ?? ''
  );

  // P6: F6 fires when nothing loads the sheet.
  fs.writeFileSync(path.join(d, 'a/app.js'), 'console.log(1);');
  r = scan(d);
  check(
    'F6 fires when no JS chunk names the stylesheet',
    !!r.refusal?.startsWith('F6'),
    r.refusal ?? 'no refusal'
  );

  fs.rmSync(tmp, { recursive: true, force: true });
  return bad;
}

function main(): number {
  console.log('player CSS scope: controls first, then the verdict');
  if (selftest()) {
    console.error('✗ instrument control failed; every verdict below would be meaningless');
    return 2;
  }
  const r = scan(DIST);
  if (r.refusal) {
    console.error(`✗ ${r.refusal}`);
    return 1;
  }
  if (r.offenders.length) {
    console.error(
      `✗ ${r.offenders.length} page(s) link the player stylesheet with no player on them:`
    );
    for (const o of r.offenders.slice(0, 10)) console.error(`    ${o}`);
    if (r.offenders.length > 10) console.error(`    ... and ${r.offenders.length - 10} more`);
    console.error(`  Each makes a render-blocking request for a component it never builds.`);
    console.error(`  See agent/PLAN-plyr-css-on-demand-loading.md.`);
    return 1;
  }
  console.log(
    `✓ player CSS scope: ${r.pages} page(s), ${r.links} stylesheet link(s), ${r.mounts} with a mount; no page links ${r.playerCss.join(', ')} without one`
  );
  return 0;
}

process.exit(main());
