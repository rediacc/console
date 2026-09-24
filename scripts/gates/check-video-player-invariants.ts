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
 * THE SECOND FAMILY, ADDED 2026-09-23, IS ABOUT THE STYLESHEETS AND NOT THE PICKER. The player's CSS moved out of the component and behind `ensurePlayerStyles()` so it would stop being linked on 794 pages that never build a player; what that move bought has to be paid for by two things the compiler cannot state. The sheets must still be imported with `?url`, or they go
 * straight back into the component chunk, and the hydrator must AWAIT them before `createRoot`, or the first frame of player DOM is unstyled. `check:ci-player-css-scope` catches the first from a built `dist`; nothing at all caught the second until now.
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

/** The broken host must not come back, in any spelling. */
export const qualityPaneFaults = (player: string): string[] => {
  const out: string[] = [];
  if (/settings:\s*[^;]*['"]quality['"]/.test(player))
    out.push(
      "the Plyr settings array lists 'quality' again; that pane snaps every click to min(options)"
    );
  if (/quality:\s*\{[^}]*forced/.test(player))
    out.push('`quality.forced` is configured again, which is the pane this work removed');
  return out;
};

/**
 * The picker renders INSIDE the player frame, on every mount, with no opt-in.
 *
 * It was briefly a per-surface flag and the operator's answer was that every player able
 * to offer a language should offer it the same way. A flag is what lets one surface drift
 * back to a floating dropdown, so its absence is the invariant.
 */
export const placementFaults = (player: string, hero: string): string[] => {
  const out: string[] = [];
  // The picker's HOME is a `language` row in Plyr's own settings menu, beside Captions
  // and Speed. `config.settings` is iterated with no allowlist (plyr.mjs:2645), so an
  // entry Plyr does not know still gets its row, pane, shortcuts and animation; only
  // populating the pane is ours. The `i18n` label is required: `i18n.get` returns '' for
  // an unknown key and the row would render blank.
  if (!/'language'/.test(player))
    out.push(
      'the `language` entry is gone from config.settings; the picker has no row in the settings menu'
    );
  if (!/i18n:\s*\{\s*language:/.test(player))
    out.push('the `language` i18n label is gone, so the settings row would render blank');
  // The populator moved to its own module when the component hit eslint's max-lines; what
  // matters is that the player still CALLS it, not where it lives.
  if (!/mountLanguagePane\(/.test(player))
    out.push('nothing populates the language pane, so the row opens onto an empty menu');
  if (!/tvp-toolbar-overlay/.test(player))
    out.push('the in-frame overlay fallback is gone; a Plyr upgrade would leave no picker at all');
  if (!/!menuMounted/.test(player))
    out.push(
      'the overlay is no longer conditional on the menu failing, so both pickers can show at once'
    );
  // The overlay belongs to the keyed root subtree, not the shell above it.
  const rootAt = player.indexOf('className={`tvp-root');
  const overlayAt = player.indexOf('tvp-toolbar-overlay');
  if (rootAt >= 0 && overlayAt >= 0 && overlayAt < rootAt)
    out.push('the overlay is emitted before the player root, so it is not inside the frame');
  if (/inPlayerLanguage|inPlayerPicker/.test(player) || /in-player-language/.test(hero))
    out.push(
      'an opt-in flag is back; the in-frame picker is meant to be unconditional on every mount'
    );
  // Strip the ONE sanctioned use, then any remaining `{toolbar}` is a second render site.
  // The negative-lookahead spelling this replaces could not fire: the planted defect ends
  // in `</div>`, which is exactly what the lookahead excluded.
  const withoutOverlay = player.replace(
    '{toolbar && !menuMounted && <div className="tvp-toolbar-overlay">{toolbar}</div>}',
    ''
  );
  if (/\{toolbar\}/.test(withoutOverlay))
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
  // MEASURED, not stylistic: `.tvp-root` is overflow:hidden, so an unclamped 13-entry pane
  // is 488px tall starting 127px ABOVE the container. The first four languages are not
  // scrolled off, they are invisible and unreachable.
  if (!/\[id\$='-language'\] \[role='menu'\]\s*\{[^}]*max-height/.test(css))
    out.push(
      "the settings-menu language pane is uncapped; at 13 entries the top of the list is CLIPPED by .tvp-root's overflow, not scrollable"
    );
  return out;
};

/**
 * THE HYDRATOR MUST AWAIT THE PLAYER'S STYLESHEETS BEFORE IT CREATES A ROOT.
 *
 * `plyr.css` and `tutorial-video.css` are no longer imported by the component. They were
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
export const styleOrderFaults = (hydrate: string): string[] => {
  const out: string[] = [];
  const callAt = hydrate.indexOf('ensurePlayerStyles(');
  if (callAt < 0) {
    out.push(
      'nothing calls ensurePlayerStyles() in the hydrator, and the component no longer imports the sheets itself, so the player would mount with no stylesheet at all'
    );
    return out;
  }
  // The statement holding the call must be awaited. Bounded at the nearest `;` or `{`
  // before it, so `await Promise.all([ensurePlayerStyles(), ...])` counts while a bare
  // `void ensurePlayerStyles();` sitting beside an awaited import does not.
  const stmtAt = Math.max(hydrate.lastIndexOf(';', callAt), hydrate.lastIndexOf('{', callAt), 0);
  if (!/\bawait\b/.test(hydrate.slice(stmtAt, callAt)))
    out.push(
      'ensurePlayerStyles() is called but not awaited, so the first frame of player DOM races the stylesheet instead of following it'
    );
  const rootAt = hydrate.indexOf('createRoot(');
  if (rootAt < 0)
    out.push(
      'the hydrator no longer calls createRoot(), so this invariant has lost its subject and a green here would mean nothing'
    );
  else if (rootAt < callAt)
    out.push(
      'createRoot( runs ahead of the awaited ensurePlayerStyles(), so React paints the player before its stylesheets are in the document'
    );
  return out;
};

/**
 * And both sheets must still be imported with `?url`.
 *
 * `import 'plyr/dist/plyr.css'` and `import href from 'plyr/dist/plyr.css?url'` differ by
 * four characters and by 37,018 B on 794 pages. Only the second compiles to a
 * transform-only import, which Vite keeps out of the chunk's `importedCss`, which is what
 * stops Astro's page-CSS hoisting from linking the sheet everywhere the hydrator goes.
 *
 * `check:ci-player-css-scope` catches the same regression, but only from a built `dist`,
 * so it cannot answer until after a full `build:www`. This reads it from source in
 * milliseconds and is the reason a bad edit does not survive to the slow lane.
 */
export const styleUrlFaults = (styles: string): string[] => {
  const out: string[] = [];
  for (const spec of ['plyr/dist/plyr.css', '../styles/tutorial-video.css']) {
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
  styles: string
): number => {
  let fail = 0;
  const check = (name: string, ok: boolean, detail = ''): void => {
    if (!ok) fail += 1;
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}${ok || !detail ? '' : ` -- ${detail}`}`);
  };
  const all = () => [
    ...qualityPaneFaults(player),
    ...placementFaults(player, hero),
    ...chromeFaults(css),
    ...styleOrderFaults(hydrate),
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
    mutate(hydrate, 'ensurePlayerStyles(', 'noop('),
    styleOrderFaults
  );
  fires(
    'MUTANT (reorder): moving the awaited styles below createRoot is caught',
    moveStylesBelowRoot(hydrate),
    styleOrderFaults
  );
  fires(
    'calling ensurePlayerStyles() without awaiting it is caught',
    mutate(hydrate, 'await Promise.all([', 'Promise.all(['),
    styleOrderFaults
  );
  fires(
    'losing createRoot( altogether is caught, rather than read as an ordering pass',
    mutate(hydrate, 'createRoot(el)', 'render(el)'),
    styleOrderFaults
  );
  // The negative direction: a hydrator that still awaits before the root is NOT reported, even when its spelling changes. Without this the four controls above are satisfied by a function that flags everything.
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
    'MUTANT: turning plyr.css back into a bare import is caught, and it is the edit that re-links 37,018 B',
    mutate(styles, "'plyr/dist/plyr.css?url'", "'plyr/dist/plyr.css'"),
    styleUrlFaults
  );
  fires(
    'MUTANT: turning the overrides sheet back into a bare import is caught too, which the plan says is required and not optional',
    mutate(styles, "'../styles/tutorial-video.css?url'", "'../styles/tutorial-video.css'"),
    styleUrlFaults
  );

  // THE CONTROL THAT MATTERS: the pane that plays the wrong language must be caught.
  check(
    "re-adding 'quality' to the settings array is caught",
    qualityPaneFaults(`${player}\n      settings: ['captions', 'speed', 'quality'],`).length > 0
  );
  check(
    're-adding a forced-quality config is caught',
    qualityPaneFaults(`${player}\nconst x = { quality: { forced: true, options: [] } };`).length > 0
  );
  check(
    'dropping the settings-menu row is caught',
    placementFaults(
      player.replace("'language',", "'nope',").replaceAll("'language'", "'nope'"),
      hero
    ).length > 0
  );
  check(
    'losing the pane populator is caught',
    placementFaults(player.replaceAll('mountLanguagePane(', 'gone('), hero).length > 0
  );
  check(
    'losing the overlay FALLBACK is caught, not just the row',
    placementFaults(player.replaceAll('tvp-toolbar-overlay', 'tvp-gone'), hero).length > 0
  );
  check(
    'showing overlay and menu at once is caught',
    placementFaults(player.replace('!menuMounted && ', ''), hero).length > 0
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
    'uncapping the settings-menu language pane is caught',
    chromeFaults(
      css.replace(/(\[id\$='-language'\] \[role='menu'\]\s*\{)[^}]*max-height[^;]*;/, '$1')
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
  // Each subject must still be recognisably itself before any verdict is taken on it. `scheduleHydration` is the hydrator's entry point and the link element is the styles module's whole mechanism; either one gone means this gate is reading a file that has been repurposed, and a fault list computed from it would be arbitrary rather than absent.
  if (
    !/new Plyr\(/.test(player) ||
    !/video-player-mount/.test(hero) ||
    !/scheduleHydration/.test(hydrate) ||
    !/document\.createElement\('link'\)/.test(styles)
  ) {
    console.error(
      '✗ the video-player sources do not look like themselves; a green here would mean nothing.'
    );
    return 1;
  }
  if (process.argv.slice(2).includes('--selftest'))
    return selftest(player, hero, css, hydrate, styles);

  const picker = [
    ...qualityPaneFaults(player),
    ...placementFaults(player, hero),
    ...chromeFaults(css),
  ];
  const stylesheets = [...styleOrderFaults(hydrate), ...styleUrlFaults(styles)];
  const faults = [...picker, ...stylesheets];
  if (faults.length) {
    console.error(`✗ ${faults.length} video-player invariant(s) broken:\n`);
    for (const f of faults) console.error(`  ${f}`);
    // EACH EPILOGUE IS PRINTED ONLY FOR THE FAMILY THAT FIRED. The picker paragraph used to print unconditionally, which was harmless while it was the only family and is a live defect now that it is not: a reader whose stylesheet ordering broke would be handed a paragraph about Plyr's quality pane and no mention of the thing they actually broke.
    if (picker.length) {
      console.error(
        "\n  Plyr's quality pane cannot host the language picker: it snaps every click to"
      );
      console.error('  min(options), so the video plays a language nobody chose. The picker lives');
      console.error('  inside the player frame instead. See the comment on the Plyr config.');
    }
    if (stylesheets.length) {
      console.error("\n  The player's stylesheets load at RUNTIME and are awaited before the root");
      console.error(
        '  is created. Both halves are load-bearing: `?url` keeps 37,018 B off the 794'
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
    '✓ video-player invariants hold: no quality pane, the picker is inside the frame and mutually exclusive, and its chrome survives a bright video.'
  );
  console.log(
    '  5 source(s) read; the hydrator awaits ensurePlayerStyles() before createRoot, and both sheets are still imported with ?url so they stay off the 794 pages with no player.'
  );
  console.log(
    '  STRUCTURAL ONLY -- nothing was rendered, measured or clicked. A picker that is inside the frame and invisible passes this gate; that is wave D gate 2.'
  );
  return 0;
};

process.exit(main());
