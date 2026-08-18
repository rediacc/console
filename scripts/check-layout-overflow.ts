#!/usr/bin/env tsx
/**
 * The two CSS shapes that make this site scroll sideways.
 *
 * WHAT IS BROKEN TODAY.
 *   `/ar/contact` and `/ar/partners` scroll horizontally by about 10,000 px (measured
 *     9,823 and 9,984, reproduced 3 of 3, at both viewports). The honeypot input is hidden
 *     with `left: -9999px` (`public/styles/contact-modal.css:288`,
 *     `src/pages/[lang]/partners.astro:519`). Under `dir="rtl"` the LEFT edge is the
 *     trailing edge, so an element parked 9,999 px to the left is 9,999 px of scrollable
 *     page. Arabic visitors scroll two lead-capture pages into a white void.
 *   The homepage and pricing page scroll 133 px at 1440 and up to 398 px in ja/de/ru.
 *     `.cf-feature-info::after` (`src/styles/pricing-page.css:1804`) is
 *     `position: absolute; white-space: nowrap; opacity: 0`, so a 575 px tooltip that
 *     nobody can see still occupies layout width.
 *
 * WHY THIS IS A STYLESHEET SCAN AND NOT A BROWSER RUN, WHICH IS THE WHOLE POINT.
 * Two independent browser-driven overflow hunts reported "no offending elements" on a page
 * that overflows by 133 px. Both were honest and both were blind for the same reason:
 * `document.querySelectorAll('*')` DOES NOT RETURN PSEUDO-ELEMENTS. The culprit was an
 * `::after`. A scan that walks the DOM cannot see the thing causing this bug, and a scan
 * that reads the stylesheet sees it as plainly as any other rule -- pseudo-element
 * selectors are ordinary rules in the source. That is not a compromise made for
 * convenience; it is the only one of the two instruments that can observe the defect.
 *
 * THE LIMIT, STATED PLAINLY. This gate detects two CAUSE SHAPES, not overflow itself. It
 * cannot see a width computed at runtime, a long unbreakable string, or a grid that
 * overflows only in Japanese. A rendered-width measurement is the complement to this, not
 * a replacement for it, and it needs a browser and a built site; this needs neither and
 * runs in under a second on every commit.
 *
 * Usage:
 *   tsx scripts/check-layout-overflow.ts [--root <dir>] [--selftest]
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const WWW = 'packages/www';

/** Where stylesheets live. The main sheet is NOT under src/, which surprises everyone. */
const STYLE_DIRS = ['src/styles', 'public/styles'];
/** Files that carry `<style>` blocks inline. */
const INLINE_STYLE_DIRS = ['src'];

/**
 * How far off-axis counts as "parked offscreen". A real layout offset is a handful of
 * pixels; the offscreen-hiding idiom is thousands. 1,000 px sits between them with room to
 * spare, so a legitimate `left: -20px` nudge is never reported.
 */
const OFFSCREEN_PX = 1000;

/** Fewer stylesheets than this is a broken glob, not a simple site. */
const MIN_BLOCKS = 200;

export interface OverflowFinding {
  file: string;
  line: number;
  selector: string;
  rule: 'offscreen-inline-axis' | 'phantom-nowrap' | 'static-nowrap';
  detail: string;
}

interface Block {
  selector: string;
  body: string;
  line: number;
}

/**
 * Every declaration block in a stylesheet, with its selector and source line.
 *
 * At-rules that WRAP other rules (`@media`, `@supports`, `@container`, `@layer`) are
 * descended into rather than treated as blocks, so a rule inside a media query is judged
 * exactly like one outside it. That matters here: responsive overrides are where a
 * sideways-scroll bug is most likely to be reintroduced.
 */
export function declarationBlocks(css: string, startLine = 1): Block[] {
  const out: Block[] = [];
  const i = 0;
  const selectorStart = 0;
  const lineAt = (idx: number) => startLine + css.slice(0, idx).split('\n').length - 1;

  const parse = (from: number, to: number): void => {
    let sel = from;
    for (let j = from; j < to; j++) {
      const c = css[j];
      if (c === '/' && css[j + 1] === '*') {
        const end = css.indexOf('*/', j + 2);
        j = end < 0 ? to : end + 1;
        continue;
      }
      if (c === '}') {
        sel = j + 1;
        continue;
      }
      if (c !== '{') continue;

      // Find the matching close brace.
      let depth = 1;
      let k = j + 1;
      for (; k < to && depth > 0; k++) {
        if (css[k] === '{') depth++;
        else if (css[k] === '}') depth--;
      }
      // Comments are SKIPPED during the walk but still sit inside the slice, so a rule
      // preceded by a `/* ... */` note would otherwise report the note as its selector.
      const selector = css
        .slice(sel, j)
        .replace(/\/\*[\s\S]*?\*\//g, '')
        .trim();
      const body = css.slice(j + 1, k - 1);
      if (/^@(media|supports|container|layer|scope)\b/.test(selector)) {
        parse(j + 1, k - 1);
      } else if (selector && !selector.startsWith('@')) {
        out.push({ selector, body, line: lineAt(j) });
      }
      j = k - 1;
      sel = k;
    }
  };

  parse(i, css.length);
  void selectorStart;
  return out;
}

/** `prop: value` pairs of one declaration block, last-wins as the cascade does. */
function declarations(body: string): Map<string, string> {
  const out = new Map<string, string>();
  for (const part of body.split(';')) {
    const at = part.indexOf(':');
    if (at < 0) continue;
    const prop = part.slice(0, at).trim().toLowerCase();
    const value = part
      .slice(at + 1)
      .trim()
      .toLowerCase();
    if (prop && !prop.startsWith('--') && !prop.includes('{')) out.set(prop, value);
  }
  return out;
}

export function judgeBlock(block: Block, file: string): OverflowFinding[] {
  const d = declarations(block.body);
  const findings: OverflowFinding[] = [];

  // RULE 1: parked offscreen on the inline axis.
  for (const prop of ['left', 'right']) {
    const value = d.get(prop);
    if (!value) continue;
    const m = value.match(/^-\s*(\d+(?:\.\d+)?)px$/);
    if (!m || Number(m[1]) < OFFSCREEN_PX) continue;
    findings.push({
      file,
      line: block.line,
      selector: block.selector,
      rule: 'offscreen-inline-axis',
      detail:
        `${prop}: ${value} hides the element by pushing it off the ${prop} edge. Under ` +
        `dir="rtl" that edge is the TRAILING edge, so the page becomes ${m[1]}px wider ` +
        `instead. Use a clip-based visually-hidden rule (width:1px; height:1px; ` +
        `clip-path:inset(50%); overflow:hidden) which is direction-neutral.`,
    });
  }

  // RULE 2: an invisible element that still claims a line's worth of width.
  const position = d.get('position');
  const invisible = d.get('opacity') === '0' || d.get('visibility') === 'hidden';
  const contained =
    d.has('max-width') || d.has('contain') || d.has('clip-path') || d.get('overflow') === 'hidden';
  if (
    (position === 'absolute' || position === 'fixed') &&
    d.get('white-space') === 'nowrap' &&
    invisible &&
    !contained
  ) {
    findings.push({
      file,
      line: block.line,
      selector: block.selector,
      rule: 'phantom-nowrap',
      detail:
        `position:${position} with white-space:nowrap and ${
          d.get('opacity') === '0' ? 'opacity:0' : 'visibility:hidden'
        } is invisible but still LAID OUT, at whatever width its longest line needs. It ` +
        `contributes to the scrollable overflow area and widens the page. Add a ` +
        `max-width, or keep it out of layout until it is shown (content-visibility, or ` +
        `display:none until :hover/:focus-visible).`,
    });
  }
  // RULE 3: `white-space: nowrap` on an element that is IN NORMAL FLOW.
  //
  // WHY THIS EXISTS, and why rules 1 and 2 could not see it. Both require the box to be
  // out of flow (`position: absolute|fixed`). A wave re-introduced
  // `.comparison-table .metric-label { white-space: nowrap }` on a plain table cell;
  // "Dedicated Account Manager" is 269px on its own, which drove the table's min-content
  // width to 557px and scrolled a 390px page. The gate was green throughout, because a
  // statically positioned cell is neither shape it was built for.
  //
  // A stylesheet cannot know how long the text will be, so this CANNOT be a hard
  // failure. It is a SHRINK-ONLY inventory: every `nowrap` in normal flow is baselined,
  // and the gate fails when a NEW one appears. That is exactly the event that caused the
  // defect. An existing nowrap that is genuinely safe stays baselined and costs nothing.
  //
  // Residual, stated rather than implied: this cannot prove a page does not overflow.
  // Only measuring `scrollWidth > clientWidth` on a RENDERED page can, and attribution
  // must be by bisection, because three causes have now been found on three pages and no
  // property-matching rule catches all three.
  if (
    d.get('white-space') === 'nowrap' &&
    position !== 'absolute' &&
    position !== 'fixed' &&
    !contained &&
    d.get('overflow-x') !== 'auto' &&
    d.get('overflow-x') !== 'scroll'
  ) {
    findings.push({
      file,
      line: block.line,
      selector: block.selector,
      rule: 'static-nowrap',
      detail:
        'white-space:nowrap in normal flow, with no max-width, containment or scroll ' +
        'container. Its min-content width is whatever its longest string needs, which ' +
        'the stylesheet cannot bound. If the text is user-facing copy or translated, ' +
        'let it wrap at narrow viewports or give its wrapper overflow-x:auto.',
    });
  }

  return findings;
}

function walk(dir: string, exts: string[], out: string[] = []): string[] {
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs
    .readdirSync(dir, { withFileTypes: true })
    .sort((a, b) => a.name.localeCompare(b.name))) {
    if (entry.name.startsWith('.') || entry.name === 'node_modules') continue;
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(abs, exts, out);
    else if (exts.some((e) => entry.name.endsWith(e))) out.push(abs);
  }
  return out;
}

/** `<style>` blocks of an .astro/.tsx file, each with the line it starts on. */
export function inlineStyleBlocks(source: string): { css: string; line: number }[] {
  const out: { css: string; line: number }[] = [];
  for (const m of source.matchAll(/<style\b[^>]*>([\s\S]*?)<\/style>/g)) {
    out.push({ css: m[1], line: source.slice(0, m.index!).split('\n').length });
  }
  return out;
}

function selftest(): boolean {
  const failures: string[] = [];
  const check = (name: string, ok: boolean, detail = '') => {
    if (ok) console.log(`  PASS  ${name}`);
    else {
      console.error(`  FAIL  ${name}${detail ? `\n        ${detail}` : ''}`);
      failures.push(name);
    }
  };
  const scan = (css: string, file = 'f.css') =>
    declarationBlocks(css).flatMap((b) => judgeBlock(b, file));

  // ---- PLANT 1: the honeypot, byte for byte from contact-modal.css:285-292.
  const HONEYPOT = `.contact-honeypot {
  position: absolute;
  left: -9999px;
  width: 1px;
  height: 1px;
  overflow: hidden;
}`;
  const honeypot = scan(HONEYPOT);
  check(
    'PLANT: `left: -9999px` offscreen hiding is reported',
    honeypot.length === 1 && honeypot[0].rule === 'offscreen-inline-axis',
    JSON.stringify(honeypot)
  );

  // ---- PLANT 2: the pseudo-element tooltip, from pricing-page.css:1804.
  // THIS IS THE ONE A BROWSER SCAN CANNOT SEE. `querySelectorAll('*')` returns no
  // pseudo-elements, so two independent runtime hunts reported a clean page while this
  // rule was widening it by 133 px.
  const TOOLTIP = `.cf-feature-info::after {
  content: attr(data-tooltip);
  position: absolute;
  left: 50%;
  bottom: calc(100% + 8px);
  transform: translateX(-50%);
  white-space: nowrap;
  opacity: 0;
  pointer-events: none;
  z-index: 10;
}`;
  const tooltip = scan(TOOLTIP);
  check(
    'PLANT: an invisible nowrap PSEUDO-ELEMENT is reported',
    tooltip.length === 1 && tooltip[0].rule === 'phantom-nowrap',
    JSON.stringify(tooltip)
  );
  check(
    'the pseudo-element selector is preserved in the finding',
    tooltip[0]?.selector === '.cf-feature-info::after',
    tooltip[0]?.selector
  );

  // Inside a media query, which is where a responsive override would reintroduce it.
  check(
    'a finding inside @media is reported exactly like one outside it',
    scan(`@media (max-width: 768px) {\n${HONEYPOT}\n}`).length === 1
  );

  // `visibility: hidden` is the same defect with a different spelling.
  check(
    'visibility:hidden is judged like opacity:0',
    scan(TOOLTIP.replace('opacity: 0', 'visibility: hidden')).length === 1
  );

  // ---- CONTROLS THAT MUST NOT FIRE ------------------------------------------------
  check(
    'a small negative offset is not reported (control)',
    scan('.badge { position: absolute; left: -8px; }').length === 0
  );
  check(
    'a VISIBLE nowrap tooltip is not reported (control)',
    scan('.tip { position: absolute; white-space: nowrap; opacity: 1; }').length === 0
  );
  check(
    'an invisible nowrap rule with a max-width is not reported (control)',
    scan(`${TOOLTIP.slice(0, -1)}  max-width: 20ch;\n}`).length === 0
  );
  check(
    'the direction-neutral clip idiom is not reported (control)',
    scan(
      '.sr-only { position:absolute; width:1px; height:1px; clip-path: inset(50%); overflow:hidden; }'
    ).length === 0
  );
  check(
    'a custom property holding a negative value is not a declaration (control)',
    scan(':root { --offset-left: -9999px; }').length === 0
  );
  check(
    'a commented-out rule is not parsed as a rule (control)',
    scan('/* .old { left: -9999px; } */\n.new { left: 0; }').length === 0
  );
  check(
    'a comment above a rule is not reported as its selector (control)',
    scan('/* Honeypot spam trap */\n.hp { position:absolute; left:-9999px; }')[0]?.selector ===
      '.hp',
    scan('/* Honeypot spam trap */\n.hp { position:absolute; left:-9999px; }')[0]?.selector
  );

  // The parser itself must find blocks, or every assertion above is over an empty list.
  check(
    'the parser finds every block in a multi-rule sheet',
    declarationBlocks('.a{color:red}\n@media screen{.b{color:blue}}\n.c{color:green}').length === 3,
    String(
      declarationBlocks('.a{color:red}\n@media screen{.b{color:blue}}\n.c{color:green}').length
    )
  );

  // Inline `<style>` extraction: partners.astro:519 lives in one.
  const ASTRO = `---\nconst x = 1;\n---\n<form></form>\n<style>\n.hp { position: absolute; left: -9999px; }\n</style>`;
  const blocks = inlineStyleBlocks(ASTRO);
  check(
    'a <style> block inside an .astro file is extracted and judged',
    blocks.length === 1 && scan(blocks[0].css).length === 1,
    JSON.stringify(blocks.map((b) => b.line))
  );

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'overflow-'));
  fs.writeFileSync(path.join(tmp, 'a.css'), HONEYPOT);
  check('the walker finds stylesheets on disk', walk(tmp, ['.css']).length === 1);
  fs.rmSync(tmp, { recursive: true, force: true });

  if (failures.length > 0) {
    console.error(`\n✗ ${failures.length} self-test failure(s)`);
    return false;
  }
  return true;
}

function main(): void {
  const argv = process.argv.slice(2);
  const arg = (name: string): string | undefined => {
    const i = argv.indexOf(name);
    return i >= 0 ? argv[i + 1] : undefined;
  };

  if (argv.includes('--selftest')) process.exit(selftest() ? 0 : 1);
  if (!argv.includes('--skip-control') && !selftest()) process.exit(1);

  const base = path.resolve(arg('--root') ?? REPO_ROOT);
  const www = path.join(base, WWW);
  if (!fs.existsSync(www)) {
    console.error(`✗ Refusing to run: ${www} does not exist.`);
    process.exit(1);
  }

  let findings: OverflowFinding[] = [];
  let blocks = 0;

  for (const dir of STYLE_DIRS) {
    for (const file of walk(path.join(www, dir), ['.css'])) {
      const rel = path.relative(base, file);
      const parsed = declarationBlocks(fs.readFileSync(file, 'utf-8'));
      blocks += parsed.length;
      for (const b of parsed) findings.push(...judgeBlock(b, rel));
    }
  }
  for (const dir of INLINE_STYLE_DIRS) {
    for (const file of walk(path.join(www, dir), ['.astro', '.tsx'])) {
      const rel = path.relative(base, file);
      const source = fs.readFileSync(file, 'utf-8');
      for (const styleBlock of inlineStyleBlocks(source)) {
        const parsed = declarationBlocks(styleBlock.css, styleBlock.line);
        blocks += parsed.length;
        for (const b of parsed) findings.push(...judgeBlock(b, rel));
      }
    }
  }

  // FLOOR. The stylesheets are not in the obvious place (the main sheet lives under
  // public/, not src/), so a path that quietly stops matching is a real risk here, and
  // "zero offending rules" would be its output.
  if (blocks < MIN_BLOCKS) {
    console.error(
      `✗ Refusing to run: only ${blocks} declaration block(s) parsed under ${www}, below the ` +
        `floor of ${MIN_BLOCKS}.\n  A scan of no CSS reports no overflow causes.`
    );
    process.exit(1);
  }

  // static-nowrap is SHRINK-ONLY: the stylesheet cannot know how long a string is, so
  // the existing set is frozen and only a NEW one fails. Rules 1 and 2 stay hard.
  const NOWRAP_BASELINE = 'scripts/data/static-nowrap-baseline.json';
  const nowrapKey = (f: OverflowFinding) => `${f.file}:${f.selector}`;
  const nowrapFound = findings.filter((f) => f.rule === 'static-nowrap');
  const hard = findings.filter((f) => f.rule !== 'static-nowrap');
  if (argv.includes('--write-baseline')) {
    fs.writeFileSync(
      NOWRAP_BASELINE,
      `${JSON.stringify({ note: 'shrink-only; see RULE 3', entries: nowrapFound.map(nowrapKey).sort() }, null, 2)}\n`
    );
    console.log(`static-nowrap baseline written: ${nowrapFound.length} entr(ies)`);
    process.exit(0);
  }
  const knownNowrap = new Set<string>(
    fs.existsSync(NOWRAP_BASELINE)
      ? JSON.parse(fs.readFileSync(NOWRAP_BASELINE, 'utf8')).entries
      : []
  );
  const newNowrap = nowrapFound.filter((f) => !knownNowrap.has(nowrapKey(f)));
  findings = [...hard, ...newNowrap];
  // A baselined finding that has been FIXED is a hard error, not a note.
  //
  // This printed a friendly line and still exited 0, which is precisely how a stale entry
  // survives: nobody re-reads the log of a green gate. One sat here undetected through a
  // whole wave (`blog/index.astro:.post-date`, retired by a template rewrite) and was
  // found by a person reading output, not by the gate. check-em-dash-surfaces.ts:329 treats
  // the identical condition as exit 1, and it is the one that is right: a shrink-only
  // baseline whose shrinking is never enforced does not shrink.
  const staleNowrap = knownNowrap.size - nowrapFound.length;
  if (staleNowrap > 0) {
    console.error(
      `\n\x1b[31m✗\x1b[0m ${staleNowrap} baselined static-nowrap entr(ies) are already fixed.\n` +
        'This baseline only SHRINKS, so drain it:\n' +
        '    npx tsx scripts/check-layout-overflow.ts --write-baseline\n' +
        'If another writer is live in this tree, hand-edit the stale line instead: a full\n' +
        'rewrite banks whatever fresh finding they have just introduced.'
    );
    process.exit(1);
  }

  if (findings.length === 0) {
    console.log(`✓ No horizontal-overflow cause shapes in ${blocks} declaration block(s).`);
    return;
  }

  console.error(
    `✗ ${findings.length} rule(s) that make the page scroll sideways, across ${blocks} declaration block(s):\n`
  );
  for (const f of findings) {
    console.error(`  ${f.file}:${f.line}  ${f.selector}   [${f.rule}]`);
    console.error(`    ${f.detail}`);
    console.error('');
  }
  process.exit(1);
}

main();
