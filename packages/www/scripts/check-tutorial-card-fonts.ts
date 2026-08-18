#!/usr/bin/env tsx
/**
 * Gate: every character that lands on a tutorial title/outro card must exist in
 * the font that card will actually be drawn with.
 *
 * The failure this exists to catch shipped: eighteen Arabic tutorials rendered
 * every letter DETACHED. The card SVGs are rasterized by resvg
 * (`lib/scenes/svg-render.ts`), the templates asked for `Inter`, Inter has no
 * Arabic, and resvg silently substituted GNU Unifont — a bitmap face with the
 * isolated Arabic code points and no joining forms. Right-to-left ordering was
 * correct, so the render looked plausible to anyone who does not read Arabic.
 * zh and ko shipped as Unifont bitmaps by the same route.
 *
 * Why every gate at the time was blind to it: `check:ci-locale-tutorial-assets`
 * checks the five files EXIST, `check:ci-tutorial-caption-sync` checks caption
 * timings, `check:ci-tutorial-render-queue` checks staleness. All of them pass
 * on a video whose text is unreadable, because none of them look at glyphs. A
 * "did something render" test cannot catch this: Unifont DOES render Arabic,
 * just wrongly.
 *
 * So this gate does not render. It reads the real card strings out of the real
 * transcripts, resolves the font each locale is mapped to in `card-fonts.ts`,
 * and asks that font's own cmap whether it carries every code point. That
 * catches a missing face, a wrong mapping, and a new title using a character
 * the mapped face lacks.
 *
 * It does NOT catch a face that has the code points but no joining forms —
 * nothing cheap does. That is why `card-fonts.ts` keeps a curated map rather
 * than picking a font dynamically, and why the map is the thing to review.
 *
 *   npm run check:ci-tutorial-card-fonts
 *   tsx packages/www/scripts/check-tutorial-card-fonts.ts --selftest
 */
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import {
  cardFontFamilies,
  missingCodepoints,
  resolveCardFontFile,
} from './lib/scenes/card-fonts.ts';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const WWW_ROOT = path.resolve(HERE, '..');
const TRANSCRIPTS = path.join(WWW_ROOT, 'src', 'data', 'tutorial-transcripts');

interface Offence {
  lang: string;
  tutorial: string;
  family: string;
  text: string;
  missing: number[];
}

/** Every string the title/outro cards draw for one tutorial in one locale. */
function cardStrings(doc: Record<string, unknown>): string[] {
  const out: string[] = [];
  if (typeof doc.title === 'string') out.push(doc.title);
  const steps = (doc.steps ?? doc.events) as Record<string, unknown>[] | undefined;
  for (const step of steps ?? []) {
    for (const key of ['cardLabel', 'label']) {
      const v = step[key];
      if (typeof v === 'string') out.push(v);
    }
  }
  return out.filter((s) => s.trim().length > 0);
}

function scan(): Offence[] {
  const offences: Offence[] = [];
  const langs = readdirSync(TRANSCRIPTS).filter((d) => existsSync(path.join(TRANSCRIPTS, d, '.')));
  for (const lang of langs.sort()) {
    const dir = path.join(TRANSCRIPTS, lang);
    // Same helper the render-time assert uses, so the gate and the renderer
    // cannot disagree about which families this locale actually resolves to.
    const families = cardFontFamilies(lang);
    for (const family of families) {
      const file = resolveCardFontFile(family);
      if (file === null) {
        offences.push({ lang, tutorial: '(all)', family, text: '', missing: [] });
        continue;
      }
      for (const entry of readdirSync(dir)
        .filter((f) => f.endsWith('.json'))
        .sort()) {
        const doc = JSON.parse(readFileSync(path.join(dir, entry), 'utf8'));
        for (const text of cardStrings(doc)) {
          const missing = missingCodepoints(file, text);
          if (missing.length > 0) {
            offences.push({
              lang,
              tutorial: entry.replace(/\.json$/, ''),
              family,
              text,
              missing,
            });
          }
        }
      }
    }
  }
  return offences;
}

/**
 * Control: the detector must FIRE on the exact defect that shipped. A gate that
 * cannot fail is worse than no gate, because it reports confidence. If Inter is
 * not on this host the control cannot run, and that is a hard failure too — a
 * skipped control is an unproven gate.
 */
function selftest(): number {
  const cases: [string, string, string, boolean][] = [
    ['Arabic in Inter must be reported missing', 'Inter', 'إضافة خادمك الأول', true],
    ['Hangul in Inter must be reported missing', 'Inter', '첫 번째 서버 추가', true],
    ['Han in Inter must be reported missing', 'Inter', '添加您的第一台服务器', true],
    ['Arabic in its mapped face must pass', cardFontFamilies('ar')[0], 'إضافة خادمك الأول', false],
    ['Latin in the Arabic face must pass', cardFontFamilies('ar')[0], 'Commit VS Code rdc', false],
    ['Hangul in its mapped face must pass', cardFontFamilies('ko')[0], '첫 번째 서버 추가', false],
    ['Latin in Inter must pass', 'Inter', 'Branching Commit Rollback', false],
  ];
  let failed = 0;
  for (const [name, family, text, expectMissing] of cases) {
    const file = resolveCardFontFile(family);
    if (file === null) {
      console.error(`FAIL  ${name}: family "${family}" not resolvable, control cannot run`);
      failed++;
      continue;
    }
    const missing = missingCodepoints(file, text);
    const fired = missing.length > 0;
    if (fired !== expectMissing) {
      console.error(
        `FAIL  ${name}: expected ${expectMissing ? 'missing' : 'covered'}, got ` +
          `${fired ? `missing ${missing.map((c) => `U+${c.toString(16)}`).join(',')}` : 'covered'}`
      );
      failed++;
    } else {
      console.log(`ok    ${name}`);
    }
  }
  if (failed > 0) {
    console.error(`\nselftest: ${failed} control(s) failed. The gate is not trustworthy.`);
    return 1;
  }
  console.log(`\nselftest: ${cases.length} controls passed, detector fires and clears.`);
  return 0;
}

function main(): number {
  if (process.argv.includes('--selftest')) return selftest();

  const offences = scan();
  if (offences.length === 0) {
    console.log('check:ci-tutorial-card-fonts: every card string is covered by its mapped font.');
    return 0;
  }

  console.error('Tutorial card text cannot be drawn by the font mapped to its locale.\n');
  for (const o of offences) {
    if (o.text === '') {
      console.error(`  ${o.lang}: font family "${o.family}" is not installed on this host`);
      continue;
    }
    const cps = o.missing.map((c) => `U+${c.toString(16).toUpperCase()}`).join(' ');
    console.error(`  ${o.lang}/${o.tutorial}  "${o.text}"`);
    console.error(`    "${o.family}" has no glyph for: ${cps}`);
  }
  console.error(
    '\nresvg does not fail on a missing glyph. It substitutes silently, and the last\n' +
      'time it did that eighteen Arabic tutorials shipped with every letter detached.\n' +
      'Fix by mapping the locale to a covering face in\n' +
      'packages/www/scripts/lib/scenes/card-fonts.ts, not by ignoring this.'
  );
  return 1;
}

process.exit(main());
