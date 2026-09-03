#!/usr/bin/env tsx
/**
 * An SVG that expects theme tokens must be INLINE. An external `<img>` can never see them.
 *
 * WHY THIS EXISTS. 521 of 521 illustrations shipped with a hardcoded `#f5f5f5`
 * background and no dark-mode hook, and it read like nobody had got round to theming
 * them. They could not be themed: an SVG loaded through `<img src="...">` is a separate
 * document, so `var(--illustration-ink)` inside it resolves against nothing. Meanwhile
 * the token existed with zero consumers. Two checks passed independently, one confirming
 * the tokens were declared and one confirming the assets were present, and the thing
 * that was broken was the CONNECTION between them, which neither could see.
 *
 * THE INVARIANT, deliberately narrow so it cannot produce a false positive: an SVG
 * referenced as an external image must not contain `var(--`. A logo or a favicon with
 * literal colours is fine and is not flagged. Only a file that asks for a custom property
 * it can never receive is a finding, and that file is broken by construction.
 *
 * Usage:
 *   npx tsx scripts/check-svg-theme-reach.ts [--selftest]
 */
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { globSync } from 'glob';
import { GREEN, NC, RED } from './utils/console.js';

const ROOT = path.resolve(import.meta.dirname, '..');
const WWW = path.join(ROOT, 'packages/www');

/** SVG paths referenced as an EXTERNAL image, i.e. through src=, not inlined. */
export function externalSvgRefs(source: string): string[] {
  const out: string[] = [];
  // <img src="...svg">, and Astro's <Image src={...}> only matters when it emits <img>,
  // which it does for anything it does not inline.
  for (const m of source.matchAll(/<img\b[^>]*\bsrc\s*=\s*["'{]([^"'}]+\.svg)["'}]?/gi)) {
    out.push(m[1]);
  }
  for (const m of source.matchAll(/\bstyle\s*=\s*["'][^"']*url\(\s*["']?([^"')]+\.svg)/gi)) {
    out.push(m[1]);
  }
  return out;
}

/** Does this SVG ask for a custom property it can only get from a host document? */
export function wantsHostTokens(svg: string): boolean {
  return /var\(\s*--/.test(svg);
}

function resolve(ref: string): string | null {
  const cleaned = ref.split('?')[0].replace(/^\/+/, '');
  for (const base of [path.join(WWW, 'public'), path.join(WWW, 'src'), WWW, ROOT]) {
    const p = path.join(base, cleaned);
    if (existsSync(p)) return p;
  }
  return null;
}

function selftest(): number {
  let bad = 0;
  const check = (label: string, ok: boolean) => {
    console.log(`  ${ok ? `${GREEN}PASS${NC}` : `${RED}FAIL${NC}`}  ${label}`);
    if (!ok) bad++;
  };
  check(
    'an <img src=*.svg> is collected',
    externalSvgRefs('<img src="/a/b.svg" alt="">').length === 1
  );
  check(
    'an INLINE <svg> is NOT collected',
    externalSvgRefs('<svg><rect fill="var(--x)"/></svg>').length === 0
  );
  check(
    'a css url(*.svg) is collected',
    externalSvgRefs('<div style="background:url(/c.svg)">').length === 1
  );
  check(
    'CONTROL: an svg asking for a token is detected',
    wantsHostTokens('<svg><rect fill="var(--ink)"/></svg>')
  );
  check(
    'CONTROL: a literal-colour svg is NOT flagged',
    !wantsHostTokens('<svg><rect fill="#f5f5f5"/></svg>')
  );
  return bad;
}

function main(): void {
  if (process.argv.includes('--selftest')) {
    console.log('SVG theme-reach gate selftest');
    const bad = selftest();
    console.log(
      bad === 0 ? '\n${GREEN}✓${NC} 5/5 controls pass' : `\n${RED}✗${NC} ${bad} control(s) failed`
    );
    process.exit(bad === 0 ? 0 : 1);
  }
  if (selftest() !== 0) {
    console.error('controls failed; the gate cannot be trusted');
    process.exit(1);
  }

  const findings: string[] = [];
  let scanned = 0;
  const files = [...globSync(`${WWW}/src/**/*.astro`), ...globSync(`${WWW}/src/**/*.tsx`)];
  for (const file of files) {
    const src = readFileSync(file, 'utf8');
    for (const ref of externalSvgRefs(src)) {
      const abs = resolve(ref);
      if (abs === null) continue; // a build-time import or a remote URL; not ours to judge
      scanned++;
      if (wantsHostTokens(readFileSync(abs, 'utf8'))) {
        findings.push(
          `${path.relative(ROOT, file)} loads ${ref} as an external image, but that file uses var(--...)`
        );
      }
    }
  }

  if (scanned === 0) {
    console.error(
      '✗ zero resolvable external SVG references were scanned. The gate is not seeing the site; its green means nothing.'
    );
    process.exit(1);
  }
  if (findings.length > 0) {
    console.error(
      `\n${RED}✗${NC} ${findings.length} SVG(s) ask for host tokens they can never receive:`
    );
    for (const f of findings) console.error(`    ${f}`);
    console.error(
      '\nAn <img> SVG is a separate document; var(--...) inside it resolves against nothing.'
    );
    console.error(
      'Inline the SVG (set:html of a ?raw import) or replace the tokens with literals.'
    );
    process.exit(1);
  }
  console.log(
    `${GREEN}✓${NC} ${scanned} external SVG reference(s) checked; none expects host tokens`
  );
}

main();
