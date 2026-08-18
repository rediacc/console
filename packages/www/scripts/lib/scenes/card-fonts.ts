/**
 * Which font each locale's tutorial cards are drawn with, and the check that
 * proves the choice can actually draw that locale's script.
 *
 * The bug this exists to prevent, observed in shipped Arabic posters: the card
 * templates asked for `Inter, sans-serif`, Inter has no Arabic coverage, and
 * resvg silently fell through to GNU Unifont — a bitmap face that carries the
 * isolated Arabic code points and no init/medi/fina substitutions. Every letter
 * rendered detached. Bidi ordering was correct; only the joining was gone. The
 * render exited 0, the poster looked plausible to a non-reader, and eighteen
 * Arabic tutorials shipped that way. zh and ko went out as Unifont bitmaps by
 * the same route.
 *
 * Three things were learned the hard way while fixing it, all measured against
 * resvg-js 2.6.2, and all of them constrain what this module may do:
 *
 *  1. A CSS-style family list does NOT chain. `font-family="Noto Sans Arabic,
 *     Inter, sans-serif"` renders byte-identically to `"Noto Sans Arabic"`
 *     alone: resvg picks ONE family from the list and then uses its own
 *     internal fallback for missing glyphs. The list is not a fallback chain.
 *  2. resvg's internal fallback is NOT stable. Merely adding an unrelated face
 *     to `fontFiles` flipped Arabic from correct-in-Unifont to .notdef boxes,
 *     and flipped zh from broken to correct. Selection depends on font-DB
 *     ordering, so anything that relies on it is one font install away from
 *     changing. Never rely on it: name the family that covers the script.
 *  3. Therefore the family must cover EVERY script on the card, not just the
 *     locale's own. Arabic card titles routinely mix Latin ("التفريع، Commit
 *     والاسترجاع", "فتح في VS Code"), so an Arabic-only face such as Noto Sans
 *     Arabic renders the Latin half as .notdef boxes. DejaVu Sans is used for
 *     Arabic precisely because it carries joined Arabic AND full Latin in one
 *     face.
 *
 * The Latin/Cyrillic locales keep Inter and JetBrains Mono exactly as before,
 * so their output is unchanged.
 */
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
/** packages/www/scripts/assets/fonts */
const VENDORED_DIR = path.resolve(HERE, '..', '..', 'assets', 'fonts');

export interface CardFonts {
  /** Family for the title and the localized step labels. */
  sans: string;
  /** Family for the ASCII command column and the eyebrow rules. */
  mono: string;
}

/** Inter + JetBrains Mono: what every Latin/Cyrillic locale has always used. */
const DEFAULT_FONTS: CardFonts = { sans: 'Inter, sans-serif', mono: 'JetBrains Mono, monospace' };

/**
 * Locales whose script neither Inter nor JetBrains Mono covers. The family named
 * here must cover the locale's script AND Latin, because card text mixes them.
 *
 * `ar`  -> DejaVu Sans, vendored below. Joined Arabic plus full Latin.
 * `zh`/`ja`/`ko` -> WenQuanYi Zen Hei, a system face. Covers Han, kana, Hangul
 *        and Latin. Droid Sans Fallback was rejected: it has no Hangul, so `ko`
 *        fell back to Unifont and shipped as bitmap text.
 */
const LOCALE_FONTS: Record<string, CardFonts> = {
  ar: { sans: 'DejaVu Sans', mono: 'DejaVu Sans' },
  zh: { sans: 'WenQuanYi Zen Hei', mono: 'WenQuanYi Zen Hei' },
  ja: { sans: 'WenQuanYi Zen Hei', mono: 'WenQuanYi Zen Hei' },
  ko: { sans: 'WenQuanYi Zen Hei', mono: 'WenQuanYi Zen Hei' },
};

/**
 * Faces shipped in-tree so the Arabic render does not depend on what happens to
 * be installed on the render host. That dependency is the whole bug: the host
 * had no joining Arabic face and nothing said so.
 */
const VENDORED_FILES = ['DejaVuSans.ttf', 'DejaVuSans-Bold.ttf'] as const;

/** Absolute paths of the vendored faces, for resvg's `font.fontFiles`. */
export function vendoredFontFiles(): string[] {
  return VENDORED_FILES.map((f) => path.join(VENDORED_DIR, f));
}

export function cardFontsFor(lang: string): CardFonts {
  return LOCALE_FONTS[lang] ?? DEFAULT_FONTS;
}

/**
 * Representative characters per locale, checked for coverage before rendering.
 *
 * Coverage is a necessary condition, not a sufficient one: a face can carry
 * every Arabic code point and still have no joining forms, which is precisely
 * what Unifont did. Nothing cheap distinguishes the two, so the defence against
 * a non-joining face is the curated map above (a family chosen and eyeballed
 * once), and this check defends against the family being absent or wrong.
 */
const SCRIPT_PROBES: Record<string, string> = {
  ar: 'ضفخ',
  zh: '添服器',
  ja: '最初サ',
  ko: '첫번째',
};

/** Latin is on every card (commands, product names), so every face must have it. */
const LATIN_PROBE = 'RdcA1';

const checked = new Set<string>();

/**
 * Fail closed before rendering: prove the family this locale is about to be
 * drawn with actually contains the glyphs it needs.
 *
 * This is a coverage check against the font's own cmap, not a look at the
 * output, and that is deliberate. Eyeballing the render cannot catch the
 * original failure: Unifont DOES draw Arabic glyphs, just unjoined ones, so a
 * "did anything get drawn" test passes happily on exactly the output that
 * caused the complaint. Asking the font file which code points it carries is
 * the only check that fires on the real defect.
 */
export function assertCardFontsUsable(lang: string): void {
  if (checked.has(lang)) return;

  for (const file of vendoredFontFiles()) {
    if (!existsSync(file)) {
      throw new Error(
        `Card font missing: ${file}. It is committed under ` +
          `packages/www/scripts/assets/fonts/; restore it rather than rendering ` +
          `without it, or Arabic ships as detached letters again.`
      );
    }
  }

  const families = cardFontFamilies(lang);
  const need = (SCRIPT_PROBES[lang] ?? '') + LATIN_PROBE;

  for (const family of families) {
    const file = resolveCardFontFile(family);
    if (file === null) {
      throw new Error(
        `Card font family "${family}" (locale ${lang}) is not installed on this host. ` +
          `Install it or change the mapping in card-fonts.ts. Rendering without it ` +
          `lets resvg substitute a bitmap fallback silently.`
      );
    }
    const missing = missingCodepoints(file, need);
    if (missing.length > 0) {
      throw new Error(
        `Card font "${family}" (${file}) cannot draw ${missing.length} character(s) ` +
          `needed by locale ${lang}: ${missing.map((c) => `U+${c.toString(16).toUpperCase()}`).join(' ')}. ` +
          `The card would render .notdef boxes or a silent bitmap fallback.`
      );
    }
  }

  checked.add(lang);
}

/**
 * The real font families a locale's cards resolve to, deduped, with generic
 * keywords dropped. Both the render-time assert and the CI gate go through this
 * so they cannot disagree about what "the font for this locale" means — passing
 * the raw stack `"Inter, sans-serif"` to a font lookup finds nothing, which is
 * a false alarm rather than a real finding.
 */
export function cardFontFamilies(lang: string): string[] {
  const fonts = cardFontsFor(lang);
  return [...new Set([fonts.sans, fonts.mono])].map(stripGenerics).filter(Boolean);
}

/** "Inter, sans-serif" -> "Inter". Generic keywords are not real families. */
function stripGenerics(stack: string): string {
  const first = stack.split(',')[0]?.trim() ?? '';
  return /^(sans-serif|serif|monospace|cursive|fantasy)$/i.test(first) ? '' : first;
}

/** Families served by a vendored file rather than by whatever the host has. */
// `| undefined` is the honest type: indexing a Record with a missing key yields undefined at
// runtime, and typing it as always-string made the guard below look provably true to the
// linter. The check is right; the type was lying.
const VENDORED_FAMILY_FILES: Record<string, string | undefined> = {
  'DejaVu Sans': 'DejaVuSans.ttf',
};

/**
 * Absolute file for a family name, or null when nothing provides it.
 *
 * Vendored families resolve to the in-tree file, because that is the one resvg
 * is handed. Everything else goes through `fc-match`, which always answers with
 * SOMETHING, so the returned family is compared back against the request — that
 * silent substitution is exactly the failure being detected.
 */
export function resolveCardFontFile(family: string): string | null {
  const vendored = VENDORED_FAMILY_FILES[family];
  if (vendored !== undefined) {
    const file = path.join(VENDORED_DIR, vendored);
    return existsSync(file) ? file : null;
  }
  return resolveFamilyFile(family);
}

function resolveFamilyFile(family: string): string | null {
  try {
    const out = execFileSync('fc-match', ['-f', '%{file}\t%{family}', family], {
      encoding: 'utf8',
    });
    // Split on LENGTH rather than on a nullish check. `fc-match` omits the tab when it has
    // no family to report, so the second field really can be absent, but TypeScript types
    // `split()` as `string[]` and therefore treats `families ?? ''` as a dead branch. A
    // length test is a runtime fact it cannot dismiss, so the defence survives the linter.
    const parts = out.split('\t');
    const file = parts[0];
    const families = parts.length > 1 ? parts[1] : '';
    if (!file || !existsSync(file)) return null;
    const matched = families.split(',').map((f) => f.trim().toLowerCase());
    return matched.includes(family.toLowerCase()) ? file : null;
  } catch {
    return null;
  }
}

/** Code points in `text` that the font at `file` has no glyph for. */
export function missingCodepoints(file: string, text: string): number[] {
  const covered = readCmapCoverage(readFileSync(file));
  const missing: number[] = [];
  for (const ch of text) {
    const cp = ch.codePointAt(0);
    if (cp !== undefined && !covered(cp)) missing.push(cp);
  }
  return missing;
}

/**
 * Minimal TrueType cmap reader: enough to answer "is this code point mapped?"
 * for formats 4 and 12, across both plain fonts and TrueType Collections.
 * Deliberately dependency-free — this runs in a render script, not the site.
 */
function readCmapCoverage(buf: Buffer): (cp: number) => boolean {
  const ranges: [number, number][] = [];
  for (const fontOffset of fontOffsets(buf)) {
    const cmap = findTable(buf, fontOffset, 'cmap');
    if (cmap === null) continue;
    const numTables = buf.readUInt16BE(cmap + 2);
    for (let i = 0; i < numTables; i++) {
      const rec = cmap + 4 + i * 8;
      if (rec + 8 > buf.length) break;
      const sub = cmap + buf.readUInt32BE(rec + 4);
      if (sub + 4 > buf.length) continue;
      const format = buf.readUInt16BE(sub);
      if (format === 4) readFormat4(buf, sub, ranges);
      else if (format === 12) readFormat12(buf, sub, ranges);
    }
  }
  if (ranges.length === 0) {
    throw new Error('Font has no readable cmap subtable in format 4 or 12');
  }
  return (cp: number) => ranges.some(([lo, hi]) => cp >= lo && cp <= hi);
}

/** Offsets of each font in the file: one for a plain font, N for a .ttc. */
function fontOffsets(buf: Buffer): number[] {
  if (buf.length >= 12 && buf.toString('ascii', 0, 4) === 'ttcf') {
    const n = buf.readUInt32BE(8);
    const out: number[] = [];
    for (let i = 0; i < n && 12 + i * 4 + 4 <= buf.length; i++) {
      out.push(buf.readUInt32BE(12 + i * 4));
    }
    return out;
  }
  return [0];
}

function findTable(buf: Buffer, fontOffset: number, tag: string): number | null {
  if (fontOffset + 12 > buf.length) return null;
  const numTables = buf.readUInt16BE(fontOffset + 4);
  for (let i = 0; i < numTables; i++) {
    const rec = fontOffset + 12 + i * 16;
    if (rec + 16 > buf.length) return null;
    if (buf.toString('ascii', rec, rec + 4) === tag) return buf.readUInt32BE(rec + 8);
  }
  return null;
}

function readFormat4(buf: Buffer, sub: number, out: [number, number][]): void {
  const segX2 = buf.readUInt16BE(sub + 6);
  const endBase = sub + 14;
  const startBase = endBase + segX2 + 2;
  for (let s = 0; s < segX2; s += 2) {
    if (startBase + s + 2 > buf.length) return;
    const end = buf.readUInt16BE(endBase + s);
    const start = buf.readUInt16BE(startBase + s);
    // 0xFFFF..0xFFFF is the mandatory terminator segment, not real coverage.
    if (start <= end && start !== 0xffff) out.push([start, end]);
  }
}

function readFormat12(buf: Buffer, sub: number, out: [number, number][]): void {
  const nGroups = buf.readUInt32BE(sub + 12);
  for (let g = 0; g < nGroups; g++) {
    const rec = sub + 16 + g * 12;
    if (rec + 12 > buf.length) return;
    out.push([buf.readUInt32BE(rec), buf.readUInt32BE(rec + 4)]);
  }
}
