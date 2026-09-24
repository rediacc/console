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
 *
 * ---- gate ----
 * step: Player CSS scope
 * needs: node
 * lane: quality-www-build
 * slow: true
 * ---- end gate ----
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { reportFindings } from '../lib/findings-report.js';
import { envRoot } from '../lib/repo-root.js';

// ANCHORED ON THIS FILE, not on the caller's working directory. This read `process.env.PLAYER_CSS_ROOT ?? process.cwd()`, which check:ci-gate-cwd-independence did not see: its pattern only matched cwd as the FIRST argument of path.resolve/join, so the commonest shape of its own rule passed. The seam is preserved -- PLAYER_CSS_ROOT still overrides -- but the default is derived from
// this file's location.
const ROOT = envRoot('PLAYER_CSS_ROOT');
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

/**
 * EIGHT PLANTS, EACH WITH A CLEAN COUNTERPART.
 *
 * Six of the eight aim at a FLOOR, and a floor nobody has watched refuse is decoration. Each of those is the baseline corpus with exactly ONE knob moved, which is what makes a single clean baseline an honest counterpart for all six: the corpus that refuses and the corpus that does not differ by the one thing the floor is about, so a refusal cannot be arriving from anywhere
 * else. The other two are the verdict itself, P1, and the over-match control, P4.
 *
 * THE NUMBERS ARE LOAD-BEARING and not decoration either. `test_gate_player_css_scope.py` mutates this gate and asserts the selftest goes red NAMING P4 and P6, so renumbering a plant silently breaks a control one directory away. P4 is the over-match control and P6 is F6, as the plan wrote them.
 *
 * The negative direction is carried by the baseline, by P4, and by the two mount spellings: a gate that reported everything would fail four of these checks rather than pass them.
 */
function selftest(): number {
  let bad = 0;
  const tmps: string[] = [];
  const check = (name: string, ok: boolean, detail = '') => {
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}`);
    if (!ok) {
      bad++;
      if (detail) console.error(`        ${detail}`);
    }
  };

  const page = (link: boolean, mount: boolean, spelling: string, attr: boolean) =>
    `<html><head>${link ? '<link rel="stylesheet" href="/a/player.css">' : ''}</head><body>` +
    `${mount ? `<div class="x ${spelling} y"${attr ? ' data-video-src="v.mp4"' : ''}></div>` : ''}</body></html>`;

  /** One corpus. Every knob defaults to the CLEAN value, so a plant is one argument. */
  const build = (
    o: {
      pages?: number;
      link?: boolean;
      mount?: boolean;
      markers?: string[];
      js?: string;
      spelling?: string;
      attr?: boolean;
    } = {}
  ): string => {
    const {
      pages = MIN_PAGES + 5,
      link = true,
      mount = true,
      markers = MARKERS,
      js = 'import"./player.css";',
      spelling = 'video-player-mount',
      attr = true,
    } = o;
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'player-css-'));
    tmps.push(tmp);
    const d = path.join(tmp, 'dist');
    const mk = (rel: string, body: string) => {
      fs.mkdirSync(path.join(d, path.dirname(rel)), { recursive: true });
      fs.writeFileSync(path.join(d, rel), body);
    };
    mk('a/player.css', markers.map((m) => `${m}{}`).join(''));
    mk('a/other.css', '.tvp-root{}.tvp-toolbar{}'); // the OVER-MATCH control
    mk('a/app.js', js);
    for (let i = 0; i < pages; i++) mk(`p${i}.html`, page(link, mount, spelling, attr));
    // P4's subject, present in EVERY corpus: a page that links the NON-player sheet and has no mount. So every clean verdict below is also a statement that it was not reported.
    mk(
      'over.html',
      '<html><head><link rel="stylesheet" href="/a/other.css"></head><body></body></html>'
    );
    return d;
  };
  const add = (d: string, rel: string, body: string) => fs.writeFileSync(path.join(d, rel), body);

  const clean = build();
  let r = scan(clean);
  check(
    'CLEAN COUNTERPART: the baseline corpus refuses nothing and reports no offender',
    !r.refusal && r.offenders.length === 0,
    r.refusal ?? r.offenders.slice(0, 2).join(', ')
  );
  check(
    'and the baseline is not vacuous: it really carries the pages, the links and the mounts',
    r.pages > MIN_PAGES && r.links > MIN_LINKS && r.mounts > MIN_MOUNTS,
    `pages=${r.pages} links=${r.links} mounts=${r.mounts}`
  );
  check(
    'P4 CONTROL: a sheet with .tvp-root but neither marker is not a player sheet',
    !r.offenders.includes('/over.html') && !r.playerCss.includes('/a/other.css'),
    r.playerCss.join(', ')
  );

  // P1, the verdict itself.
  add(clean, 'bad.html', page(true, false, 'video-player-mount', true));
  r = scan(clean);
  check(
    'P1 PLANT: a page linking the player sheet with NO mount is reported',
    r.offenders.includes('/bad.html'),
    r.refusal ?? `offenders=${r.offenders.length}`
  );
  // The other half of the mount question. The hydrator selects `.tutorial-video-container[data-video-src]`, so a bare div builds no player, and its page is still paying for a stylesheet it cannot use.
  add(clean, 'attrless.html', page(true, true, 'tutorial-video-container', false));
  r = scan(clean);
  check(
    'CONTROL: a mount CLASS with no data-video-src is not a mount, so its page is reported',
    r.offenders.includes('/attrless.html'),
    r.refusal ?? r.offenders.join(', ')
  );
  check(
    'CONTROL: the second mount spelling still counts as a mount',
    scan(build({ spelling: 'tutorial-video-container' })).offenders.length === 0
  );

  // P2, P3, P5 to P8: one floor each, one knob each, against the baseline above.
  r = scan(path.join(clean, 'no-such-build'));
  check(
    'P2 PLANT: F1 fires when there is no build to read',
    !!r.refusal?.startsWith('F1'),
    r.refusal ?? 'no refusal'
  );
  r = scan(build({ pages: 5 }));
  check(
    'P3 PLANT: F2 fires when the page walk loses the corpus',
    !!r.refusal?.startsWith('F2'),
    r.refusal ?? 'no refusal'
  );
  r = scan(build({ link: false }));
  check(
    'P5 PLANT: F3 fires when the link scanner sees nothing',
    !!r.refusal?.startsWith('F3'),
    r.refusal ?? 'no refusal'
  );
  r = scan(build({ js: 'console.log(1);' }));
  check(
    'P6 PLANT: F6 fires when no JS chunk names the stylesheet',
    !!r.refusal?.startsWith('F6'),
    r.refusal ?? 'no refusal'
  );
  r = scan(build({ markers: [MARKERS[0]] }));
  check(
    'P7 PLANT: F4 fires when a marker is absent from every built stylesheet',
    !!r.refusal?.startsWith('F4'),
    r.refusal ?? 'no refusal'
  );
  r = scan(build({ mount: false }));
  check(
    'P8 PLANT: F5 fires when the mount markup changes shape',
    !!r.refusal?.startsWith('F5'),
    r.refusal ?? 'no refusal'
  );

  for (const t of tmps) fs.rmSync(t, { recursive: true, force: true });
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
    return reportFindings({
      header: `✗ ${r.offenders.length} page(s) link the player stylesheet with no player on them:`,
      items: r.offenders,
      limit: 10,
      remedy: [
        `  Each makes a render-blocking request for a component it never builds.`,
        `  See agent/plans/PLAN-plyr-css-on-demand-loading.md.`,
      ],
    });
  }
  console.log(
    `✓ player CSS scope: ${r.pages} page(s), ${r.links} stylesheet link(s), ${r.mounts} with a mount; no page links ${r.playerCss.join(', ')} without one`
  );
  return 0;
}

process.exit(main());
