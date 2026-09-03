/**
 * A translated value must not lose a currency amount that English carries.
 *
 * Found 2026-08-27: Arabic shipped `.88M` where English reads `$4.88M`, and
 * `0K–00K` where English reads `$90K–$300K`, on the problem statCallouts of
 * six solution pages. The signature is a `$` plus exactly one digit removed
 * and nothing else changed, which is what an unescaped `$n` backreference
 * does to a replacement string. Six leaves, all Arabic; the amounts are the
 * headline numbers on those pages, so the corruption was load-bearing.
 *
 * The rule is deliberately narrow: it fires only when the locale value equals
 * the English value with every `$<digit>` deleted. It therefore does NOT fire
 * on legitimate localisation, where the amount is rewritten wholesale
 * (`462万ドル`, `4,62 milyon USD`, `600 $/Tag`). A broader "the locale must
 * contain the English amount" rule was tried first and produced 483 findings,
 * nearly all of them correct translations.
 */
import fs from 'node:fs';
import path from 'node:path';

const DIR = path.join(process.cwd(), 'packages/www/src/i18n/translations');

type Leaf = [string, string];
function leaves(node: unknown, prefix = ''): Leaf[] {
  if (typeof node === 'string') return [[prefix, node]];
  if (Array.isArray(node)) return node.flatMap((v, i) => leaves(v, `${prefix}.${i}`));
  if (node && typeof node === 'object')
    return Object.entries(node).flatMap(([k, v]) => leaves(v, prefix ? `${prefix}.${k}` : k));
  return [];
}

const eaten = (s: string) => s.replace(/\$\d/g, '');

export function findCorruptions(
  dir = DIR
): { locale: string; key: string; en: string; got: string }[] {
  const en = new Map(leaves(JSON.parse(fs.readFileSync(path.join(dir, 'en.json'), 'utf8'))));
  const out: { locale: string; key: string; en: string; got: string }[] = [];
  for (const f of fs
    .readdirSync(dir)
    .filter((f) => f.endsWith('.json') && f !== 'en.json' && !f.startsWith('.'))) {
    const loc = new Map(leaves(JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'))));
    for (const [key, ev] of en) {
      if (!ev.includes('$')) continue;
      const lv = loc.get(key);
      if (lv === undefined || lv === ev) continue;
      if (lv === eaten(ev)) out.push({ locale: f.replace('.json', ''), key, en: ev, got: lv });
    }
  }
  return out;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const bad = findCorruptions();
  if (bad.length === 0) {
    console.log('✓ No currency amounts eaten by a $<digit> substitution.');
    process.exit(0);
  }
  console.error(`✗ ${bad.length} translated value(s) lost a currency amount:\n`);
  for (const b of bad)
    console.error(
      `  ${b.locale}  ${b.key}\n     en  ${JSON.stringify(b.en)}\n     got ${JSON.stringify(b.got)}`
    );
  console.error('\nRestore the amount from English. These are headline figures on the page.');
  process.exit(1);
}
