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
 * THE PICKER'S HOME, AND WHY THERE IS ONLY ONE (2026-10-08). The player moved from Plyr to
 * Video.js 10's packaged `VideoSkin` (agent/plans/PLAN-plyr-to-videojs.md). Plyr's settings
 * menu hosted a `language` row with an in-frame overlay as its fallback; the Video.js skin's
 * settings menu hard-codes its children and takes no slot, and ejecting the skin to add one
 * measured 2,786 lines plus a Tailwind 4.3 toolchain. So the in-frame toolbar is now THE
 * picker, unconditional whenever the cast has 2+ locales, and it must sit INSIDE the skin
 * root, because that root is the element the skin's fullscreen button fullscreens: an
 * overlay one level up would vanish the moment a viewer went fullscreen. The Plyr-era
 * `quality`-pane check (a pane that snapped every click to min(options)) is retired with
 * Plyr; that pane no longer exists to be re-added.
 *
 * THE SECOND FAMILY, ADDED 2026-09-23, IS ABOUT THE STYLESHEETS AND NOT THE PICKER. The player's CSS moved out of the component and behind `ensurePlayerStyles()` so it would stop being linked on 794 pages that never build a player; what that move bought has to be paid for by two things the compiler cannot state. The sheets must still be imported with `?url`, or they go
 * straight back into the component chunk, and the mount module must AWAIT them before `createRoot`, or the first frame of player DOM is unstyled. `check:ci-player-css-scope` catches the first from a built `dist`; nothing at all caught the second until now.
 *
 * THE MOUNT PATH MOVED ON 2026-09-30. The video theater split the building of a player out of the hydrator into `tutorial-video-mount.ts` (`mountPlayers`), which both the hydrator and `video-theater.ts` call. The ordering check follows it there, and a third check holds the callers to that one path: a hydrator or theater that called `createRoot` itself would build a player the ordering check never reads.
 *
 * WHAT A GREEN HERE DOES NOT MEAN: nothing is rendered, measured or clicked. A picker
 * that is inside the frame in the DOM and invisible, mispositioned or unclickable passes
 * this gate.
 *
 * ---- gate ----
 * step: Video player invariants
 * needs: node
 * selftest: true
 * lane: quality-content
 * ---- end gate ----
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const PLAYER = path.join(REPO, 'packages/www/src/components/TutorialVideoPlayer.tsx');
const HERO = path.join(REPO, 'packages/www/src/components/solution-pages/SPSolutionVideo.astro');
const CSS = path.join(REPO, 'packages/www/src/styles/tutorial-video.css');
const HYDRATE = path.join(REPO, 'packages/www/src/scripts/tutorial-video-hydrate.ts');
const STYLES = path.join(REPO, 'packages/www/src/scripts/tutorial-video-styles.ts');
const MOUNT = path.join(REPO, 'packages/www/src/scripts/tutorial-video-mount.ts');
const THEATER = path.join(REPO, 'packages/www/src/scripts/video-theater.ts');

/** The one place the toolbar is rendered: inside the skin root, gated only on its own existence. */
export const SANCTIONED_OVERLAY =
  '{toolbar && <div className="tvp-toolbar-overlay">{toolbar}</div>}';

/**
 * The picker renders INSIDE the player frame, on every mount, with no opt-in.
 *
 * It was briefly a per-surface flag and the operator's answer was that every player able
 * to offer a language should offer it the same way. A flag is what lets one surface drift
 * back to a floating dropdown, so its absence is the invariant.
 */
export const placementFaults = (player: string, hero: string): string[] => {
  const out: string[] = [];
  if (!/tvp-toolbar-overlay/.test(player)) {
    out.push(
      'the in-frame language overlay is gone, and it is the ONLY picker: a cast with 2+ locales would offer no language at all'
    );
    return out;
  }
  // The toolbar exists exactly when the cast has 2+ locales. Any further condition is the
  // per-surface drift the operator ruled out, spelled as a ternary instead of a flag.
  if (!/const toolbar =\s*pickerLangs\.length > 1 \?/.test(player))
    out.push(
      'the toolbar is no longer built on `pickerLangs.length > 1` alone, so some mount with 2+ locales can lose its picker'
    );
  // The ONE sanctioned render site, guarded by nothing but the toolbar's own existence.
  const at = player.indexOf(SANCTIONED_OVERLAY);
  if (at < 0)
    out.push(
      `the overlay is no longer rendered as \`${SANCTIONED_OVERLAY}\`, so it carries a condition beyond the toolbar existing (or was reshaped; if so, update SANCTIONED_OVERLAY here deliberately)`
    );
  else {
    // Inside the skin root, which is what the skin's fullscreen button fullscreens.
    const skinOpen = player.indexOf('<VideoSkin');
    const skinClose = player.indexOf('</VideoSkin>');
    if (skinOpen < 0 || skinClose < 0 || at < skinOpen || at > skinClose)
      out.push(
        'the overlay is rendered outside <VideoSkin>, so it is not inside the element fullscreen takes and vanishes in fullscreen'
      );
  }
  // A second picker in the skin's settings menu was measured impossible without ejecting;
  // its Plyr-era machinery coming back means two pickers, or one that renders empty.
  if (/mountLanguagePane|language-pane|menuMounted/.test(player))
    out.push(
      "a settings-menu language picker is back beside the in-frame one; the packaged VideoSkin's settings menu takes no child, so it is the toolbar or nothing"
    );
  if (/inPlayerLanguage|inPlayerPicker/.test(player) || /in-player-language/.test(hero))
    out.push(
      'an opt-in flag is back; the in-frame picker is meant to be unconditional on every mount'
    );
  // Strip the ONE sanctioned use, then any remaining `{toolbar}` is a second render site.
  // The negative-lookahead spelling this replaces could not fire: the planted defect ends
  // in `</div>`, which is exactly what the lookahead excluded.
  if (/\{toolbar\}/.test(player.replace(SANCTIONED_OVERLAY, '')))
    out.push('the toolbar is rendered somewhere other than inside the in-frame overlay');
  return out;
};

/** Over video, a translucent-white control is unreadable on a bright frame. */
export const chromeFaults = (css: string): string[] => {
  const out: string[] = [];
  const rule =
    /\.tvp-root \.tvp-toolbar-overlay \.tvp-toolbar \.language-trigger\s*\{([^}]*)\}/.exec(css);
  if (!rule) {
    out.push(
      'the overlay trigger no longer outranks the hero rule, which paints translucent WHITE over video'
    );
  } else if (!/background:\s*rgba\(0,\s*0,\s*0/.test(rule[1])) {
    out.push(
      'the overlay trigger lost its dark scrim; a bright video frame washes a light control out'
    );
  }
  if (!/\.tvp-toolbar-overlay \.language-menu\s*\{[^}]*max-height/.test(css))
    out.push(
      'the 13-locale menu is uncapped inside the frame, which clips its tail with no scrollbar'
    );
  return out;
};

/**
 * THE MOUNT MODULE MUST AWAIT THE PLAYER'S STYLESHEETS BEFORE IT CREATES A ROOT.
 *
 * The skin's `skin.css` and `tutorial-video.css` are not imported by the component. They were
 * being linked on 794 pages that never build a player, so they moved behind
 * `ensurePlayerStyles()` and load at runtime; PLAN-plyr-css-on-demand-loading.md carries
 * the measurement. The price of that move is an ordering obligation nothing in the type
 * system can state: `createRoot` paints the player's DOM, and if it runs before the sheets
 * are in the document the first frame is unstyled.
 *
 * That regression is invisible to every automated check that is not this one. It is a
 * race, it hides on a warm cache and on any machine fast enough to win it, and the styles
 * arrive a frame later, so a screenshot taken after the fact looks correct.
 *
 * Three ways to break it, so three faults: drop the call, stop awaiting it, or move it
 * after the root. The third is the one a refactor produces by accident.
 */
export const styleOrderFaults = (mount: string): string[] => {
  const out: string[] = [];
  const callAt = mount.indexOf('ensurePlayerStyles(');
  if (callAt < 0) {
    out.push(
      'nothing calls ensurePlayerStyles() in tutorial-video-mount.ts, and the component no longer imports the sheets itself, so the player would mount with no stylesheet at all'
    );
    return out;
  }
  // The statement holding the call must be awaited. Bounded at the nearest `;` or `{`
  // before it, so `await Promise.all([ensurePlayerStyles(), ...])` counts while a bare
  // `void ensurePlayerStyles();` sitting beside an awaited import does not.
  const stmtAt = Math.max(mount.lastIndexOf(';', callAt), mount.lastIndexOf('{', callAt), 0);
  if (!/\bawait\b/.test(mount.slice(stmtAt, callAt)))
    out.push(
      'ensurePlayerStyles() is called but not awaited, so the first frame of player DOM races the stylesheet instead of following it'
    );
  const rootAt = mount.indexOf('createRoot(');
  if (rootAt < 0)
    out.push(
      'tutorial-video-mount.ts no longer calls createRoot(), so this invariant has lost its subject and a green here would mean nothing'
    );
  else if (rootAt < callAt)
    out.push(
      'createRoot( runs ahead of the awaited ensurePlayerStyles(), so React paints the player before its stylesheets are in the document'
    );
  return out;
};

/**
 * EVERY PLAYER IS BUILT THROUGH `mountPlayers`, so the ordering check above covers every one.
 *
 * The hydrator schedules mounts and the theater hosts one; neither may create a React root of its own, and each must still reach `mountPlayers` from the mount module. A caller that grew its own `createRoot` would mount a player whose stylesheet ordering nothing reads, and a caller that stopped importing `mountPlayers` has left this gate checking a path the site no longer takes.
 */
export const mountRoutingFaults = (callers: Record<string, string>): string[] => {
  const out: string[] = [];
  for (const [name, src] of Object.entries(callers)) {
    if (/\bcreateRoot\s*\(/.test(src))
      out.push(
        `${name} calls createRoot() itself, so it builds a player outside mountPlayers and the awaited-stylesheet check never reads that path`
      );
    if (!/import\s*\{[^}]*\bmountPlayers\b[^}]*\}\s*from\s*'\.\/tutorial-video-mount'/.test(src))
      out.push(
        `${name} no longer imports mountPlayers from ./tutorial-video-mount, so the mount path this gate checks may not be the one the site takes`
      );
    else if (!/\bmountPlayers\s*\(/.test(src))
      out.push(
        `${name} imports mountPlayers but never calls it, so it builds no player through the checked path`
      );
  }
  return out;
};

/**
 * And both sheets must still be imported with `?url`.
 *
 * `import 'plyr/dist/plyr.css'` and `import href from 'plyr/dist/plyr.css?url'` differed by
 * four characters and by 37,018 B on 794 pages; the Video.js skin sheet that replaced it on
 * 2026-10-08 builds to 81,643 B, so the same slip now costs more than twice that. Only the second compiles to a
 * transform-only import, which Vite keeps out of the chunk's `importedCss`, which is what
 * stops Astro's page-CSS hoisting from linking the sheet everywhere the hydrator goes.
 *
 * `check:ci-player-css-scope` catches the same regression, but only from a built `dist`,
 * so it cannot answer until after a full `build:www`. This reads it from source in
 * milliseconds and is the reason a bad edit does not survive to the slow lane.
 */
export const styleUrlFaults = (styles: string): string[] => {
  const out: string[] = [];
  for (const spec of ['@videojs/react/video/skin.css', '../styles/tutorial-video.css']) {
    if (!styles.includes(`'${spec}?url'`))
      out.push(
        `'${spec}' is no longer imported with ?url, so its bytes return to the component chunk and Astro links them on every page carrying the hydrator`
      );
  }
  return out;
};

const selftest = (
  player: string,
  hero: string,
  css: string,
  hydrate: string,
  styles: string,
  mount: string,
  theater: string
): number => {
  let fail = 0;
  const check = (name: string, ok: boolean, detail = ''): void => {
    if (!ok) fail += 1;
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${ok || !detail ? '' : ` -- ${detail}`}`);
  };
  const all = () => [
    ...placementFaults(player, hero),
    ...chromeFaults(css),
    ...styleOrderFaults(mount),
    ...mountRoutingFaults({ hydrator: hydrate, theater }),
    ...styleUrlFaults(styles),
  ];
  check('the tree as it stands is clean', all().length === 0, JSON.stringify(all()));

  /**
   * A mutant, or `null` when the text it aims at is gone.
   *
   * The null is the vacuity guard and it is not decoration. Every control below asserts that a mutant produces a fault; a replacement that silently stopped matching would hand the control the UNMUTATED source, and `fires` would then be reading the clean tree and calling it a caught defect.
   */
  const mutate = (src: string, from: string, to: string): string | null =>
    src.includes(from) ? src.replaceAll(from, to) : null;
  const fires = (name: string, mutant: string | null, run: (s: string) => string[]) =>
    check(
      name,
      mutant !== null && run(mutant).length > 0,
      mutant === null
        ? 'the mutation no longer applies, so this control would have tested the unmutated source'
        : 'the mutant reported no fault'
    );

  /**
   * MOVE the awaited style load below `createRoot`, keeping every token.
   *
   * A reorder is the mutant that matters here, because it is what a refactor produces by accident, and a deletion is not a substitute for it: the call is still there, still awaited, and only its position is wrong. Returns null if any anchor is missing.
   */
  const moveStylesBelowRoot = (src: string): string | null => {
    const awaitAt = src.indexOf('await Promise.all([');
    if (awaitAt < 0) return null;
    const start = src.lastIndexOf('\n', awaitAt) + 1;
    const end = src.indexOf(']);', awaitAt);
    if (end < 0) return null;
    const stmt = src.slice(start, end + 3);
    const rest = src.slice(end + 3);
    const rootAt = rest.indexOf('createRoot(');
    if (rootAt < 0) return null;
    const lineEnd = rest.indexOf('\n', rootAt);
    if (lineEnd < 0) return null;
    return `${src.slice(0, start)}${rest.slice(0, lineEnd + 1)}${stmt}\n${rest.slice(lineEnd + 1)}`;
  };

  fires(
    'MUTANT (delete): dropping the ensurePlayerStyles() call is caught',
    mutate(mount, 'ensurePlayerStyles(', 'noop('),
    styleOrderFaults
  );
  fires(
    'MUTANT (reorder): moving the awaited styles below createRoot is caught',
    moveStylesBelowRoot(mount),
    styleOrderFaults
  );
  fires(
    'calling ensurePlayerStyles() without awaiting it is caught',
    mutate(mount, 'await Promise.all([', 'Promise.all(['),
    styleOrderFaults
  );
  fires(
    'losing createRoot( altogether is caught, rather than read as an ordering pass',
    mutate(mount, 'createRoot(el)', 'render(el)'),
    styleOrderFaults
  );
  const routing = (name: 'hydrator' | 'theater') => (s: string) =>
    mountRoutingFaults(
      name === 'hydrator' ? { hydrator: s, theater } : { hydrator: hydrate, theater: s }
    );
  fires(
    'MUTANT: the hydrator building its own root instead of calling mountPlayers is caught',
    mutate(hydrate, 'await mountPlayers([el]);', 'createRoot(el);'),
    routing('hydrator')
  );
  fires(
    'MUTANT: the theater dropping its mountPlayers import is caught',
    mutate(theater, "from './tutorial-video-mount'", "from './somewhere-else'"),
    routing('theater')
  );
  fires(
    'MUTANT: the theater importing mountPlayers but never calling it is caught',
    mutate(theater, 'void mountPlayers([stage])', 'void Promise.resolve([stage])'),
    routing('theater')
  );
  // The negative direction: a mount module that still awaits before the root is NOT reported, even when its spelling changes. Without this the four controls above are satisfied by a function that flags everything.
  check(
    'CONTROL: an awaited load ahead of the root is not reported, in either spelling',
    styleOrderFaults(
      'async function m(){ await ensurePlayerStyles(); const r = createRoot(el); r.render(x); }'
    ).length === 0 &&
      styleOrderFaults(
        "async function m(){ const [, c] = await Promise.all([ensurePlayerStyles(), import('./p')]); createRoot(el); }"
      ).length === 0
  );
  fires(
    'MUTANT: turning the Video.js skin sheet back into a bare import is caught, and it is the edit that re-links it on every hydrator page',
    mutate(styles, "'@videojs/react/video/skin.css?url'", "'@videojs/react/video/skin.css'"),
    styleUrlFaults
  );
  fires(
    'MUTANT: turning the overrides sheet back into a bare import is caught too, which the plan says is required and not optional',
    mutate(styles, "'../styles/tutorial-video.css?url'", "'../styles/tutorial-video.css'"),
    styleUrlFaults
  );

  // THE PICKER. Each control is a mutant of the REAL component, null-guarded by `mutate`, so a
  // rewrite that moved the text it aims at reds this selftest instead of testing nothing.
  const place = (p: string) => placementFaults(p, hero);
  fires(
    'losing the in-frame overlay, the ONLY picker, is caught',
    mutate(player, 'tvp-toolbar-overlay', 'tvp-gone'),
    place
  );
  fires(
    'MUTANT (move): rendering the overlay after </VideoSkin>, outside what fullscreen takes, is caught',
    player.includes(SANCTIONED_OVERLAY) && player.includes('</VideoSkin>')
      ? player
          .replace(SANCTIONED_OVERLAY, '')
          .replace('</VideoSkin>', `</VideoSkin>\n${SANCTIONED_OVERLAY}`)
      : null,
    place
  );
  fires(
    'an extra condition on the overlay is caught',
    mutate(
      player,
      '{toolbar && <div className="tvp-toolbar-overlay">',
      '{toolbar && inTheater && <div className="tvp-toolbar-overlay">'
    ),
    place
  );
  fires(
    'gating the toolbar on anything beyond 2+ locales is caught',
    mutate(player, 'pickerLangs.length > 1 ?', 'pickerLangs.length > 1 && inTheater ?'),
    place
  );
  fires(
    'a settings-menu picker coming back beside the toolbar is caught',
    `${player}\nmountLanguagePane(menu, langs);`,
    place
  );
  check(
    'a per-surface opt-in flag coming back is caught',
    placementFaults(`${player}\nconst inPlayerPicker = false;`, hero).length > 0
  );
  check(
    'a mount re-introducing the data attribute is caught',
    placementFaults(player, `${hero}\n<div data-in-player-language="false" />`).length > 0
  );
  check(
    'rendering the toolbar outside the overlay is caught',
    placementFaults(`${player}\n<div className="tvp-shell">{toolbar}</div>`, hero).length > 0
  );
  check(
    'losing the dark scrim is caught',
    chromeFaults(
      css.replace('background: rgba(0, 0, 0, 0.55);', 'background: rgba(255, 255, 255, 0.12);')
    ).length > 0
  );
  check(
    'losing the whole overlay rule is caught',
    chromeFaults(
      css.replace('.tvp-root .tvp-toolbar-overlay .tvp-toolbar .language-trigger', '.never-matches')
    ).length > 0
  );
  check(
    'uncapping the 13-locale overlay menu is caught',
    chromeFaults(
      css.replace(/(\.tvp-toolbar-overlay \.language-menu\s*\{)[^}]*max-height[^;]*;/, '$1')
    ).length > 0
  );
  return fail === 0 ? 0 : 1;
};

const main = (): number => {
  const player = fs.readFileSync(PLAYER, 'utf8');
  const hero = fs.readFileSync(HERO, 'utf8');
  const css = fs.readFileSync(CSS, 'utf8');
  const hydrate = fs.readFileSync(HYDRATE, 'utf8');
  const styles = fs.readFileSync(STYLES, 'utf8');
  const mount = fs.readFileSync(MOUNT, 'utf8');
  const theater = fs.readFileSync(THEATER, 'utf8');
  // Each subject must still be recognisably itself before any verdict is taken on it. `scheduleHydration` is the hydrator's entry point and the link element is the styles module's whole mechanism; either one gone means this gate is reading a file that has been repurposed, and a fault list computed from it would be arbitrary rather than absent.
  if (
    !/<VideoSkin\b/.test(player) ||
    !/video-player-mount/.test(hero) ||
    !/scheduleHydration/.test(hydrate) ||
    !/document\.createElement\('link'\)/.test(styles) ||
    !/export async function mountPlayers\(/.test(mount) ||
    !/openTheater/.test(theater)
  ) {
    console.error(
      '✗ the video-player sources do not look like themselves; a green here would mean nothing.'
    );
    return 1;
  }
  if (process.argv.slice(2).includes('--selftest'))
    return selftest(player, hero, css, hydrate, styles, mount, theater);

  const picker = [...placementFaults(player, hero), ...chromeFaults(css)];
  const stylesheets = [
    ...styleOrderFaults(mount),
    ...mountRoutingFaults({ hydrator: hydrate, theater }),
    ...styleUrlFaults(styles),
  ];
  const faults = [...picker, ...stylesheets];
  if (faults.length) {
    console.error(`✗ ${faults.length} video-player invariant(s) broken:\n`);
    for (const f of faults) console.error(`  ${f}`);
    // EACH EPILOGUE IS PRINTED ONLY FOR THE FAMILY THAT FIRED. The picker paragraph used to print unconditionally, which was harmless while it was the only family and is a live defect now that it is not: a reader whose stylesheet ordering broke would be handed a paragraph about Plyr's quality pane and no mention of the thing they actually broke.
    if (picker.length) {
      console.error(
        "\n  The in-frame toolbar is the player's ONLY language picker: Video.js 10's packaged"
      );
      console.error(
        '  VideoSkin settings menu takes no child row. It must render inside <VideoSkin>,'
      );
      console.error('  the element fullscreen takes. See agent/plans/PLAN-plyr-to-videojs.md.');
    }
    if (stylesheets.length) {
      console.error("\n  The player's stylesheets load at RUNTIME and are awaited before the root");
      console.error(
        '  is created. Both halves are load-bearing: `?url` keeps the skin sheet (81,643 B) off the 794'
      );
      console.error(
        '  pages that carry the hydrator and no player, and the await is what makes the'
      );
      console.error('  first frame of player DOM styled rather than usually styled.');
      console.error('  See agent/plans/PLAN-plyr-css-on-demand-loading.md.');
    }
    return 1;
  }
  console.log(
    '✓ video-player invariants hold: the in-frame toolbar is the one picker, it renders inside <VideoSkin> on every 2+ locale cast, and its chrome survives a bright video.'
  );
  console.log(
    '  7 source(s) read; mountPlayers awaits ensurePlayerStyles() before createRoot, the hydrator and the theater build only through it, and both sheets are still imported with ?url so they stay off the 794 pages with no player.'
  );
  console.log(
    '  STRUCTURAL ONLY -- nothing was rendered, measured or clicked. A picker that is inside the frame and invisible passes this gate; that is wave D gate 2.'
  );
  return 0;
};

process.exit(main());
