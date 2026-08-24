#!/usr/bin/env tsx
/**
 * check:ci-video-player-invariants -- the mechanisms the 2026-08-24 video-player work
 * rests on.
 *
 * WHY NOT AN E2E CASE, which is where this was routed. `packages/e2e-tests` drives the
 * CLI and renet against real VMs over the bridge; the www marketing site is not deployed
 * on those machines and that suite cannot reach a solution page at all. The surface that
 * could is a browser gate, which is wave D gate 2 and unowned. So this covers what is
 * checkable from source, and says plainly what it cannot see.
 *
 * THE REGRESSION THAT MATTERS MOST is the first one. Plyr's `quality` pane was tried as
 * the host for the language picker and it snaps every click to min(options): the radio
 * whose DOM value was "4" delivered 0, and with 1-based values "5" delivered 1, because
 * `setQuality`'s `options.includes()` disagrees with the list `setQualityMenu` rendered
 * the rows from. Re-adding `quality` to the settings array would silently bring back a
 * control that plays a different language than the one clicked -- the worst kind of
 * regression, because it looks like it works.
 *
 * WHAT A GREEN HERE DOES NOT MEAN: nothing is rendered, measured or clicked. A picker
 * that is inside the frame in the DOM and invisible, mispositioned or unclickable passes
 * this gate.
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PLAYER = path.join(REPO, 'packages/www/src/components/TutorialVideoPlayer.tsx');
const HERO = path.join(REPO, 'packages/www/src/components/solution-pages/SPSolutionVideo.astro');
const CSS = path.join(REPO, 'packages/www/src/styles/tutorial-video.css');

/** The broken host must not come back, in any spelling. */
export const qualityPaneFaults = (player: string): string[] => {
  const out: string[] = [];
  if (/settings:\s*[^;]*['"]quality['"]/.test(player))
    out.push("the Plyr settings array lists 'quality' again; that pane snaps every click to min(options)");
  if (/quality:\s*\{[^}]*forced/.test(player))
    out.push('`quality.forced` is configured again, which is the pane this work removed');
  return out;
};

/** The picker must render INSIDE the player frame, and only one of the two positions. */
export const placementFaults = (player: string, hero: string): string[] => {
  const out: string[] = [];
  if (!/tvp-toolbar-overlay/.test(player))
    out.push('the in-frame overlay is gone from the player; the picker floats above it again');
  // The overlay belongs to the keyed root subtree, not the shell above it.
  const rootAt = player.indexOf('className={`tvp-root');
  const overlayAt = player.indexOf('tvp-toolbar-overlay');
  if (rootAt >= 0 && overlayAt >= 0 && overlayAt < rootAt)
    out.push('the overlay is emitted before the player root, so it is not inside the frame');
  if (!/\{!inPlayerPicker && toolbar\}/.test(player))
    out.push('the above-player toolbar is no longer mutually exclusive with the overlay');
  if (!/data-in-player-language="true"/.test(hero))
    out.push('the solution hero no longer opts into the in-frame picker');
  return out;
};

/** Over video, a translucent-white control is unreadable on a bright frame. */
export const chromeFaults = (css: string): string[] => {
  const out: string[] = [];
  const rule = /\.tvp-root \.tvp-toolbar-overlay \.tvp-toolbar \.language-trigger\s*\{([^}]*)\}/.exec(css);
  if (!rule) {
    out.push('the overlay trigger no longer outranks the hero rule, which paints translucent WHITE over video');
  } else if (!/background:\s*rgba\(0,\s*0,\s*0/.test(rule[1])) {
    out.push('the overlay trigger lost its dark scrim; a bright video frame washes a light control out');
  }
  if (!/\.tvp-toolbar-overlay \.language-menu\s*\{[^}]*max-height/.test(css))
    out.push('the 13-locale menu is uncapped inside the frame, which clips its tail with no scrollbar');
  return out;
};

const selftest = (player: string, hero: string, css: string): number => {
  let fail = 0;
  const check = (name: string, ok: boolean, detail = ''): void => {
    if (!ok) fail += 1;
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${ok || !detail ? '' : ` -- ${detail}`}`);
  };
  const all = () => [
    ...qualityPaneFaults(player),
    ...placementFaults(player, hero),
    ...chromeFaults(css),
  ];
  check('the tree as it stands is clean', all().length === 0, JSON.stringify(all()));

  // THE CONTROL THAT MATTERS: the pane that plays the wrong language must be caught.
  check(
    "re-adding 'quality' to the settings array is caught",
    qualityPaneFaults(player.replace("settings: activeSubtitles ? ['captions', 'speed'] : ['speed'],", "settings: ['captions', 'speed', 'quality'],")).length > 0
  );
  check(
    're-adding a forced-quality config is caught',
    qualityPaneFaults(`${player}\nconst x = { quality: { forced: true, options: [] } };`).length > 0
  );
  check(
    'losing the in-frame overlay is caught',
    placementFaults(player.replaceAll('tvp-toolbar-overlay', 'tvp-gone'), hero).length > 0
  );
  check(
    'showing BOTH pickers at once is caught',
    placementFaults(player.replace('{!inPlayerPicker && toolbar}', '{toolbar}'), hero).length > 0
  );
  check(
    'the hero opting out is caught',
    placementFaults(player, hero.replace('data-in-player-language="true"', 'data-in-player-language="false"')).length > 0
  );
  check(
    'losing the dark scrim is caught',
    chromeFaults(css.replace('background: rgba(0, 0, 0, 0.55);', 'background: rgba(255, 255, 255, 0.12);')).length > 0
  );
  check(
    'losing the whole overlay rule is caught',
    chromeFaults(css.replace('.tvp-root .tvp-toolbar-overlay .tvp-toolbar .language-trigger', '.never-matches')).length > 0
  );
  check(
    'uncapping the 13-locale menu is caught',
    chromeFaults(css.replace(/(\.tvp-toolbar-overlay \.language-menu\s*\{)[^}]*max-height[^;]*;/, '$1')).length > 0
  );
  return fail === 0 ? 0 : 1;
};

const main = (): number => {
  const player = fs.readFileSync(PLAYER, 'utf8');
  const hero = fs.readFileSync(HERO, 'utf8');
  const css = fs.readFileSync(CSS, 'utf8');
  if (!/new Plyr\(/.test(player) || !/video-player-mount/.test(hero)) {
    console.error('✗ the video-player sources do not look like themselves; a green here would mean nothing.');
    return 1;
  }
  if (process.argv.slice(2).includes('--selftest')) return selftest(player, hero, css);

  const faults = [...qualityPaneFaults(player), ...placementFaults(player, hero), ...chromeFaults(css)];
  if (faults.length) {
    console.error(`✗ ${faults.length} video-player invariant(s) broken:\n`);
    for (const f of faults) console.error(`  ${f}`);
    console.error('\n  Plyr\'s quality pane cannot host the language picker: it snaps every click to');
    console.error('  min(options), so the video plays a language nobody chose. The picker lives');
    console.error('  inside the player frame instead. See the comment on the Plyr config.');
    return 1;
  }
  console.log('✓ video-player invariants hold: no quality pane, the picker is inside the frame and mutually exclusive, and its chrome survives a bright video.');
  console.log('  STRUCTURAL ONLY -- nothing was rendered, measured or clicked. A picker that is inside the frame and invisible passes this gate; that is wave D gate 2.');
  return 0;
};

process.exit(main());
