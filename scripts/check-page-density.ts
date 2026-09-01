#!/usr/bin/env tsx
/**
 * Drive the BUILT solution and persona pages and fail when a visitor cannot act, or when
 * reserved space is not occupied by content.
 *
 * WHY THIS EXISTS. Every defect it guards was fixed BY HAND on 2026-08-31 and nothing
 * prevented its return, because every existing gate was blind to it by construction:
 *
 *   - `check:ci-browser-smoke` asserts the page renders and the console is clean. A page
 *     with no call to action and a 397px black void renders perfectly and logs nothing.
 *   - `check:ci-layout-overflow` asserts nothing sticks out sideways. Dead vertical space
 *     is not overflow, and a column that loses its header is not overflow either.
 *   - `check:ci-dead-css` / `check:ci-css-dom-refs` ask whether rules and classes pair up.
 *     Both were green while `.sp-tech-detail-compare` rendered ten unlabelled cells.
 *
 * The measurements that motivated each assertion, all taken with a real browser:
 *   1. FOLD CTA. Across 21 solution and 4 persona pages, the first thing a visitor could
 *      act on sat at 84 to 91 percent of page depth, and ZERO of 25 offered anything
 *      inside the first viewport.
 *   2. RESERVED SPACE. At 390x844 the hero video mount was a correct 327x581 while the
 *      <video> inside it was 327x184 with `object-fit: contain`: the portrait cut
 *      letterboxed into a landscape wrapper, leaving 397px of black, 69% of the fold.
 *   3. COLUMN IDENTITY. At <=768px the tech-diff grid collapsed to one column and its two
 *      headers stayed at the top, so ten cells carried no indication of which side they
 *      belonged to. The only surviving cue was a 20%-alpha tint.
 *
 * It runs against `packages/www/dist`, never a dev server: a long-lived dev server in a
 * busy tree goes stale and reports failures that are not in the shipped site.
 *
 * Usage:
 *   npx tsx scripts/check-page-density.ts [--selftest] [--routes a,b]
 */
import { existsSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { serveDist } from './lib/serve-dist.ts';

const ROOT = path.resolve(import.meta.dirname, '..');
const DIST = path.join(ROOT, 'packages/www/dist');

/**
 * One page per template family plus the two shapes that differ.
 *
 * Deliberately NOT all 25: the templates are shared, so a per-page sweep buys repetition
 * rather than coverage, and this gate drives a real browser at four viewports. `for-ctos`
 * earns its place because it is the page that had no self-serve path at all.
 */
const ROUTES = ['/en/solutions/environment-cloning', '/en/solutions/ai-pentesting', '/en/for-ctos'];

/**
 * The four widths are the CSS's own boundaries, not round numbers.
 * `solution-pages.css` breaks at 600/768/900/1024 and the constellation reflows under
 * 1200. `max-width` is inclusive, so a width sitting ON a boundary is inside that rule:
 * 768 is where the tech-diff collapse applies and 1024 is where it must not.
 */
/**
 * How far an overlay's centre may sit from the viewport's, in CSS pixels.
 *
 * Not zero: a sub-pixel layout and an odd-width viewport each land half a pixel off. Not
 * loose either: the defect that motivated ruling R2 was 7.5px, from a `scrollbar-gutter:
 * stable` containing block 15px narrower than the viewport, so anything above ~3 would
 * pass the bug it exists to catch.
 */
const MAX_CENTRE_OFFSET_PX = 2;

const VIEWPORTS = [
  { label: 'mobile', width: 390, height: 844 },
  { label: 'tablet-portrait', width: 768, height: 1024 },
  { label: 'tablet-landscape', width: 1024, height: 768 },
  { label: 'desktop', width: 1440, height: 900 },
];

/**
 * Dead space tolerated inside a media mount, as a fraction of the mount's height.
 *
 * Not zero: a player's control bar and a sub-pixel rounding both legitimately occupy a
 * few pixels the video does not. 15% is far below the 68% the defect produced and far
 * above anything chrome accounts for.
 */
const MAX_DEAD_FRACTION = 0.15;

/**
 * DOM-node floor. A probe against a wiped or half-built `dist` returns success with a
 * handful of nodes and every assertion below passes vacuously, which is exactly how a
 * gate reports green having verified nothing.
 */
const MIN_DOM_NODES = 300;

interface Finding {
  route: string;
  viewport: string;
  kind: string;
  detail: string;
}

/** The whole measurement, run inside the page. Exported shape kept flat for logging. */
interface Probe {
  domNodes: number;
  navHydrated: boolean;
  ctaInFold: boolean;
  ctaLabel: string;
  ctaDepthPct: number;
  media: { sel: string; deadFraction: number; mountH: number; videoH: number }[];
  techDiff: { cells: number; visibleLabels: number; headerVisible: boolean } | null;
  hiddenOverflow: { sel: string; right: number; clientWidth: number }[];
  overlayCentring: { sel: string; centre: number; viewportCentre: number; offset: number }[];
}

/**
 * Passed to `page.evaluate` as SOURCE TEXT, not as a function.
 *
 * tsx compiles this file with esbuild's `keepNames`, which wraps every function in a
 * `__name()` helper. Playwright serializes a function argument and evaluates it in the
 * page, where that helper does not exist, so the probe died with
 * `ReferenceError: __name is not defined` and the gate failed for a reason that had
 * nothing to do with the site. A string is immune to whatever the bundler adds.
 */
const PROBE_SRC = String.raw`(() => {
  var vh = window.innerHeight;
  var root = document.querySelector('.sp-page');
  var inFold = function (el) {
    var r = el.getBoundingClientRect();
    return r.top + window.scrollY < vh && r.height > 0;
  };

  var ctaInFold = false, ctaLabel = '', ctaDepthPct = -1;
  if (root) {
    var links = Array.prototype.slice.call(root.querySelectorAll('a[href]'));
    var ctas = links.filter(function (a) {
      return /\/(account|contact|pricing|checkout)/.test(a.getAttribute('href') || '');
    });
    if (ctas[0]) {
      var top = ctas[0].getBoundingClientRect().top + window.scrollY;
      ctaDepthPct = +((top / document.documentElement.scrollHeight) * 100).toFixed(1);
      ctaLabel = (ctas[0].innerText || '').trim().slice(0, 40);
    }
    ctaInFold = ctas.some(inFold);
  }

  // EVERY media container, not just the one that broke. The defect class is "a box with
  // a hardcoded ratio meets content of another orientation", and it has four possible
  // homes on this site; guarding only the one that failed is guarding the instance.
  var media = [];
  var MEDIA_SEL = '.video-player-mount, .tvp-root, .video-container, .yt-embed';
  Array.prototype.slice.call(document.querySelectorAll(MEDIA_SEL)).forEach(function (box) {
    var content = box.querySelector('video, iframe');
    if (!content) return;
    var bh = box.getBoundingClientRect().height;
    var ch = content.getBoundingClientRect().height;
    if (bh <= 0) return;
    // A nested match (.tvp-root lives inside .video-player-mount) would double-count and,
    // worse, report the inner box as dead space inside the outer. Keep the OUTERMOST.
    if (box.parentElement && box.parentElement.closest(MEDIA_SEL)) return;
    media.push({
      sel: box.className ? String(box.className).split(' ')[0] : box.tagName,
      deadFraction: +((bh - ch) / bh).toFixed(3),
      mountH: Math.round(bh),
      videoH: Math.round(ch)
    });
  });

  var techDiff = null;
  var table = document.querySelector('.sp-tech-detail-compare');
  if (table) {
    // OPEN THE POPOVER FIRST, and use checkVisibility() rather than a computed display.
    //
    // Since the table moved behind a native popover this probe was measuring nothing:
    // getComputedStyle returns an element's OWN display, never an ancestor's, so with
    // the popover closed (display: none) every label still reported 'block' and the
    // assertion passed on ten elements no user could see. checkVisibility() walks the
    // ancestor chain, and showPopover() puts the content in the state the reader
    // actually meets it in.
    var pop = table.closest('[popover]');
    if (pop && pop.showPopover && !pop.matches(':popover-open')) {
      try { pop.showPopover(); } catch (e) { /* already open, or unsupported */ }
    }
    var vis = function (e) {
      return e.checkVisibility ? e.checkVisibility() : getComputedStyle(e).display !== 'none';
    };
    var head = table.querySelector('thead');
    techDiff = {
      cells: table.querySelectorAll('.sp-tech-detail-cell').length,
      visibleLabels: Array.prototype.slice
        .call(table.querySelectorAll('.sp-tech-detail-cell-label'))
        .filter(vis).length,
      headerVisible: head ? vis(head) : false
    };
  }

  // A BOX THAT IS HIDDEN STILL OCCUPIES SCROLL WIDTH, and that surprise cost 227px.
  //
  // .sp-callout-pop was a source tooltip parked beside its chip with
  // 'inset-inline-start: calc(100% + 12px)'. On the THIRD callout of a three-column row
  // that put it past the viewport, and 'position: absolute' + 'visibility: hidden' does
  // NOT remove a box from scrollable overflow the way 'display: none' does. Measured on
  // /en/solutions/instant-recovery at 1024x768: right=1251 against a 1024 client width,
  // 227px of horizontal overflow with nothing visible on screen to explain it.
  //
  // The repo carries FOUR more rules in the same shape (.cf-feature-info::after,
  // .docs-card-description, .tvp-caption, .tvp-chapter-tooltip). None reproduces today,
  // which is exactly why this is an assertion and not a note: the next one to drift is
  // invisible to a reader and to every static check, because the element renders nothing.
  //
  // THE OPTIONS ARE THE WHOLE ASSERTION, and a bare checkVisibility() made this vacuous.
  // Its DEFAULTS consider only display:none and content-visibility, so the exact element
  // this exists to catch reports VISIBLE. Measured on the planted defect:
  //
  //   checkVisibility()                                      -> true
  //   checkVisibility({visibilityProperty, opacityProperty}) -> false
  //   (display: block, visibility: hidden, opacity: 0)
  //
  // The first version of this probe shipped with the bare call, its fixture control
  // passed, and re-planting the real CSS defect and rebuilding the site produced NO
  // finding. The fixture proved the judge; only the plant proved the probe.
  //
  // display is still checked separately because it is an element's OWN value and never an
  // ancestor's: a child of a closed popover reports 'block' either way, and a
  // display:none subtree has no layout to overflow with. Zero-size boxes are skipped,
  // since a collapsed element cannot overflow anything.
  //
  // TWO NARROWINGS, both paid for by a false positive on the restored tree.
  //
  // (a) RIGHT EDGE ONLY (no backticks in this comment: PROBE_SRC is a String.raw
  //     template, so one would end the literal). An earlier version also flagged boxes
  //     with a negative left edge,
  //     and reported '.btn--icon' nine times: the nav carousel's previous button, parked
  //     off-canvas INSIDE a clipping scroller, which is a legitimate technique and adds
  //     nothing to document scroll width.
  // (b) ONLY WHEN THE DOCUMENT ACTUALLY SCROLLS SIDEWAYS. A hidden box may extend past
  //     the viewport inside an 'overflow: hidden' ancestor and be clipped away. Requiring
  //     documentElement.scrollWidth > clientWidth makes the assertion about the OBSERVABLE
  //     symptom, with the hidden element named as its cause, rather than about a shape
  //     that is sometimes fine.
  var hiddenOverflow = [];
  var cw = document.documentElement.clientWidth;
  var docOverflows = document.documentElement.scrollWidth - cw > 1;
  var VIS_OPTS = { visibilityProperty: true, opacityProperty: true, contentVisibilityAuto: true };
  if (docOverflows) Array.prototype.slice.call(document.querySelectorAll('*')).forEach(function (el) {
    if (el.checkVisibility ? el.checkVisibility(VIS_OPTS) : true) return;
    if (getComputedStyle(el).display === 'none') return;
    var r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return;
    if (r.right <= cw + 1) return;
    var cls = el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className;
    hiddenOverflow.push({
      sel: String(cls || el.tagName).split(' ')[0].slice(0, 40),
      right: Math.round(r.right),
      clientWidth: cw
    });
  });

  // OPERATOR RULING R2: an overlay centres on the VIEWPORT, not on its containing block.
  //
  // The two are not the same here and the gap is small enough to look like a rounding
  // artefact. 'scrollbar-gutter: stable' reserves the scrollbar, so a 'position: fixed;
  // inset: 0' element gets a 1425px containing block on a 1440px viewport, and an overlay
  // centred inside it sits ~7px left of where the reader's eye expects it. Seven pixels
  // is exactly the size of bug that survives review and that no static check can see: it
  // exists only once a browser has resolved a containing block.
  //
  // SCOPED TO THE OVERLAYS THAT MEAN TO BE VIEWPORT-CENTRED, which is not every popover.
  // Measured on /en/solutions/environment-cloning at 1440: .learn-menu-panel (224px) and
  // .nav-cta-menu (192px) are anchored under their triggers at 608px and 536px off
  // centre, and .cx-pop positions itself deliberately (SolutionConstellation.astro). All
  // three are correct; asserting on them would make this gate red on working code.
  //
  // Every popover in scope is OPENED to measure it, because a closed one has no box.
  var overlayCentring = [];
  var vpCentre = window.innerWidth / 2;
  Array.prototype.slice.call(document.querySelectorAll('.sp-disclosure-pop, .overlay-panel, .overlay-backdrop, .persona-menu-panel')).forEach(function (el) {
    var pop = el.matches('[popover]') ? el : el.closest('[popover]');
    if (pop && pop.showPopover && !pop.matches(':popover-open')) {
      try { pop.showPopover(); } catch (e) { /* already open, or unsupported */ }
    }
    var r = el.getBoundingClientRect();
    if (r.width === 0) return;
    var centre = r.left + r.width / 2;
    var cls = el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className;
    overlayCentring.push({
      sel: String(cls || el.tagName).split(' ')[0].slice(0, 40),
      centre: Math.round(centre * 10) / 10,
      viewportCentre: Math.round(vpCentre * 10) / 10,
      offset: Math.round(Math.abs(centre - vpCentre) * 10) / 10
    });
  });

  return {
    overlayCentring: overlayCentring,
    hiddenOverflow: hiddenOverflow,
    domNodes: document.querySelectorAll('*').length,
    navHydrated: !!document.querySelector('.nav-translate'),
    ctaInFold: ctaInFold,
    ctaLabel: ctaLabel,
    ctaDepthPct: ctaDepthPct,
    media: media,
    techDiff: techDiff
  };
})()`;

function judge(route: string, viewport: string, width: number, p: Probe): Finding[] {
  const out: Finding[] = [];
  const add = (kind: string, detail: string) => out.push({ route, viewport, kind, detail });

  // FLOOR FIRST. Everything below is vacuous against an empty page.
  if (p.domNodes < MIN_DOM_NODES) {
    add(
      'floor',
      `${p.domNodes} DOM nodes, under the ${MIN_DOM_NODES} floor: this is not a rendered page`
    );
    return out;
  }
  if (!p.navHydrated) {
    add('floor', 'no .nav-translate, so the Navigation island never hydrated');
    return out;
  }

  if (!p.ctaInFold) {
    add(
      'fold-cta',
      `no conversion CTA in the first viewport; first one is ${p.ctaLabel ? `"${p.ctaLabel}" ` : ''}at ${p.ctaDepthPct}% of page depth`
    );
  }

  for (const m of p.media ?? []) {
    if (m.deadFraction > MAX_DEAD_FRACTION) {
      add(
        'reserved-space',
        `.${m.sel} is ${m.mountH}px tall holding ${m.videoH}px of content: ` +
          `${(m.deadFraction * 100).toFixed(0)}% dead space, over the ${(MAX_DEAD_FRACTION * 100).toFixed(0)}% ceiling`
      );
    }
  }

  // 2px, not 0: sub-pixel layout and an odd-width viewport both land half a pixel off,
  // and a scrollbar gutter is 15. The defect this catches was 7.5px.
  for (const o of p.overlayCentring ?? []) {
    if (o.offset > MAX_CENTRE_OFFSET_PX) {
      add(
        'overlay-centring',
        `.${o.sel} centres at x=${o.centre} against a viewport centre of ` +
          `${o.viewportCentre}: ${o.offset}px off, over the ${MAX_CENTRE_OFFSET_PX}px ` +
          'tolerance. It is centred on its containing block, not on the viewport ' +
          '(operator ruling R2).'
      );
    }
  }

  for (const h of p.hiddenOverflow ?? []) {
    add(
      'hidden-overflow',
      `.${h.sel} is not visible yet its box reaches x=${h.right} against a ` +
        `${h.clientWidth}px client width: a hidden element still counts toward scroll ` +
        'width unless it is display:none, so the page scrolls sideways over nothing'
    );
  }

  if (p.techDiff && p.techDiff.cells > 0) {
    // At <=768 the header row is dropped, so every cell must carry its own label.
    // Above it the header row carries them and per-cell labels must stay hidden.
    if (width <= 768) {
      if (p.techDiff.visibleLabels !== p.techDiff.cells) {
        add(
          'column-identity',
          `${p.techDiff.cells} cells but ${p.techDiff.visibleLabels} visible labels: ` +
            'a stacked comparison whose cells do not say which side they are on'
        );
      }
    } else if (!p.techDiff.headerVisible) {
      add('column-identity', 'the two-column layout lost its header row');
    }
  }

  return out;
}

async function main(): Promise<void> {
  const selftest = process.argv.includes('--selftest');
  const routeArg = process.argv.find((a) => a.startsWith('--routes='));
  const routes = routeArg ? routeArg.slice('--routes='.length).split(',') : ROUTES;

  if (!existsSync(DIST)) {
    console.error(`\x1b[31m✗\x1b[0m no built site at ${DIST}`);
    console.error('    build it first: npm run build -w @rediacc/www');
    process.exit(1);
  }

  const { chromium } = await import('playwright');
  let browser;
  try {
    browser = await chromium.launch();
  } catch {
    console.error('\x1b[31m✗\x1b[0m could not launch chromium');
    console.error('    npx playwright install --with-deps chromium');
    process.exit(1);
  }

  const { port, close } = await serveDist(DIST);
  const base = `http://127.0.0.1:${port}`;
  const findings: Finding[] = [];
  let measured = 0;

  try {
    for (const route of routes) {
      for (const vp of VIEWPORTS) {
        const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } });
        // `domcontentloaded`, NOT `networkidle`. These pages carry a video player and lazy
        // images, so the network never goes idle and `networkidle` timed out at 30s on a
        // page that had finished rendering long before. check-browser-smoke.ts waits the
        // same way for the same reason; the settle below is what actually covers hydration.
        await page.goto(`${base}${route}`, { waitUntil: 'domcontentloaded' });
        // The calculator island and the video hydrate late; a census without a settle
        // understates exactly the interactive pages this gate cares about.
        await page.waitForTimeout(1200);
        const probe = (await page.evaluate(PROBE_SRC)) as Probe;
        await page.close();
        measured += 1;
        findings.push(...judge(route, vp.label, vp.width, probe));
      }
    }

    if (selftest) {
      // CONTROL, one per assertion. A gate that cannot be shown to fail is a gate that
      // has not been shown to run: each case below is the real defect, reconstructed.
      const controls: { name: string; probe: Probe; width: number; expect: string }[] = [
        {
          name: 'a page with no CTA in the fold is reported',
          width: 1440,
          expect: 'fold-cta',
          probe: {
            domNodes: 900,
            navHydrated: true,
            ctaInFold: false,
            ctaLabel: 'Start free trial',
            ctaDepthPct: 89.8,
            media: [],
            techDiff: null,
            hiddenOverflow: [],
            overlayCentring: [],
          },
        },
        {
          name: 'a 9:16 mount holding a 16:9 video is reported',
          width: 390,
          expect: 'reserved-space',
          probe: {
            domNodes: 900,
            navHydrated: true,
            ctaInFold: true,
            ctaLabel: 'x',
            ctaDepthPct: 5,
            media: [{ sel: 'video-player-mount', deadFraction: 0.683, mountH: 581, videoH: 184 }],
            techDiff: null,
            hiddenOverflow: [],
            overlayCentring: [],
          },
        },
        {
          name: 'ten stacked cells under one header row is reported',
          width: 390,
          expect: 'column-identity',
          probe: {
            domNodes: 900,
            navHydrated: true,
            ctaInFold: true,
            ctaLabel: 'x',
            ctaDepthPct: 5,
            media: [],
            techDiff: { cells: 10, visibleLabels: 0, headerVisible: false },
            hiddenOverflow: [],
            overlayCentring: [],
          },
        },
        {
          name: 'an empty page is reported as a floor breach, not as clean',
          width: 1440,
          expect: 'floor',
          probe: {
            domNodes: 5,
            navHydrated: false,
            ctaInFold: false,
            ctaLabel: '',
            ctaDepthPct: -1,
            media: [],
            techDiff: null,
            hiddenOverflow: [],
            overlayCentring: [],
          },
        },
        {
          name: 'a hidden-but-positioned tooltip reaching past the viewport is reported',
          width: 1024,
          expect: 'hidden-overflow',
          probe: {
            domNodes: 900,
            navHydrated: true,
            ctaInFold: true,
            ctaLabel: 'x',
            ctaDepthPct: 5,
            media: [],
            techDiff: null,
            // The real numbers off /en/solutions/instant-recovery at 1024x768.
            hiddenOverflow: [{ sel: 'sp-callout-pop', right: 1251, clientWidth: 1024 }],
            overlayCentring: [],
          },
        },
        {
          name: 'an overlay centred on its containing block, not the viewport, is reported',
          width: 1440,
          expect: 'overlay-centring',
          probe: {
            domNodes: 900,
            navHydrated: true,
            ctaInFold: true,
            ctaLabel: 'x',
            ctaDepthPct: 5,
            media: [],
            techDiff: null,
            hiddenOverflow: [],
            // The real geometry: scrollbar-gutter: stable gives a 1425px containing
            // block on a 1440px viewport, so its centre is 712.5 against 720.
            overlayCentring: [
              { sel: 'overlay-backdrop', centre: 712.5, viewportCentre: 720, offset: 7.5 },
            ],
          },
        },
        {
          name: 'CONTROL: a half-pixel offset is tolerated, not reported',
          width: 1440,
          expect: '',
          probe: {
            domNodes: 900,
            navHydrated: true,
            ctaInFold: true,
            ctaLabel: 'x',
            ctaDepthPct: 5,
            media: [],
            techDiff: null,
            hiddenOverflow: [],
            overlayCentring: [
              { sel: 'sp-disclosure-pop', centre: 719.5, viewportCentre: 720, offset: 0.5 },
            ],
          },
        },
      ];
      let allFired = true;
      for (const c of controls) {
        const got = judge('control', 'control', c.width, c.probe);
        // An empty `expect` is the INVERSE control: this shape must produce nothing.
        // Without it a tolerance can be tightened to zero and every run becomes a finding.
        const fired = c.expect === '' ? got.length === 0 : got.some((f) => f.kind === c.expect);
        allFired &&= fired;
        console.log(
          `  ${fired ? '\x1b[32mPASS\x1b[0m' : '\x1b[31mFAIL\x1b[0m'}  CONTROL: ${c.name}`
        );
      }
      // And the inverse: a healthy shape must produce NOTHING, or every run is a finding.
      const clean = judge('control', 'control', 390, {
        domNodes: 900,
        navHydrated: true,
        ctaInFold: true,
        ctaLabel: 'Start cloning',
        ctaDepthPct: 5,
        media: [{ sel: 'video-player-mount', deadFraction: 0.02, mountH: 581, videoH: 570 }],
        techDiff: { cells: 10, visibleLabels: 10, headerVisible: false },
        hiddenOverflow: [],
        overlayCentring: [],
      });
      const quiet = clean.length === 0;
      allFired &&= quiet;
      console.log(
        `  ${quiet ? '\x1b[32mPASS\x1b[0m' : '\x1b[31mFAIL\x1b[0m'}  CONTROL: a healthy page produces no findings`
      );
      if (!allFired) {
        console.error('\x1b[31m✗\x1b[0m a control did not behave, so this gate cannot be trusted');
        process.exit(1);
      }
    }
  } finally {
    await browser.close();
    await close();
  }

  if (measured === 0) {
    console.error('\x1b[31m✗\x1b[0m measured nothing');
    process.exit(1);
  }

  if (findings.length > 0) {
    console.error(
      `\x1b[31m✗\x1b[0m ${findings.length} finding(s) across ${measured} page/viewport pairs:\n`
    );
    for (const f of findings) {
      console.error(`  ${f.route} @ ${f.viewport}  [${f.kind}]`);
      console.error(`    ${f.detail}`);
    }
    process.exit(1);
  }

  console.log(
    `\x1b[32m✓\x1b[0m ${measured} page/viewport pairs: CTA in the fold, reserved space occupied, columns labelled, nothing hidden overflowing.`
  );
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
