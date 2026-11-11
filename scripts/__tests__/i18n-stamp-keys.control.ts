/**
 * Control for scripts/gen/i18n-stamp-keys.ts (`npm run i18n:stamp-keys`).
 *
 * Pinned: (1) stamping a prefix touches only keys under it, appends after the existing
 * entries, and leaves every existing entry (a stale one under the prefix included)
 * byte-identical; (2) the
 * fingerprint written is the one check-i18n-naturalization.ts compares (flattenAndHash);
 * (3) an empty prefix is refused; (4) a dry run writes nothing; (5) a missing locale value
 * and a disallowed English-identical value are refused, an `.id` anchor is not; (6) the
 * control: an unscoped planner (every key matches) MUST fail assertion 1.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { NON_ENGLISH_LOCALES } from '@rediacc/locales';
import { type Ledger, planStamps, run, serializeLedger } from '../gen/i18n-stamp-keys.ts';
import { flattenAndHash } from '../lib/crc32.ts';

const fail = (m: string): never => {
  console.error(`FAIL: ${m}`);
  process.exit(1);
};

const en = {
  legal: { consent: { a: 'Agree to the {{doc}}', b: 'Decline' } },
  legalNotes: { c: 'Sibling outside the prefix' },
  pages: { tos: { sections: { s1: { id: 'scope', title: '1. Definitions' } } } },
  old: { d: 'Changed English' },
};
const tr = {
  legal: { consent: { a: 'Übersetzt {{doc}}', b: 'Ablehnen' } },
  legalNotes: { c: 'Geschwister' },
  pages: { tos: { sections: { s1: { id: 'scope', title: '1. Definitions' } } } },
  old: { d: 'Alt' },
};

const root = fs.mkdtempSync(path.join(os.tmpdir(), 'stamp-keys-control-'));
const put = (name: string, v: unknown) =>
  fs.writeFileSync(path.join(root, name), `${JSON.stringify(v, null, 2)}\n`);
put('en.json', en);
for (const l of NON_ENGLISH_LOCALES) {
  put(`${l}.json`, l === 'it' ? { ...tr, legal: { consent: { a: 'Accetta {{doc}}' } } } : tr);
}
const seed: Ledger = {
  $meta: { algorithm: 'crc32', note: 'é kept unescaped' },
  languages: Object.fromEntries(
    NON_ENGLISH_LOCALES.map((l) => [l, { 'old.d': 'deadbeef', 'legal.consent.a': '0badc0de' }])
  ),
};
const ledgerPath = path.join(root, '.naturalized-hashes.json');
fs.writeFileSync(ledgerPath, serializeLedger(seed));
const readLedger = () => fs.readFileSync(ledgerPath, 'utf8');
const hashes = flattenAndHash(en, '');

const quiet = { out: process.stdout.write, err: process.stderr.write };
const mute = () => {
  process.stdout.write = (() => true) as typeof process.stdout.write;
  process.stderr.write = (() => true) as typeof process.stderr.write;
};
const unmute = () => {
  process.stdout.write = quiet.out;
  process.stderr.write = quiet.err;
};

try {
  mute();
  const before = readLedger();
  const dry = run(['--prefix', 'legal.consent', '--lang', 'de'], root);
  const afterDry = readLedger();
  const emptyRc = run(['--prefix', ''], root);
  const noneRc = run([], root);
  const writeRc = run(
    ['--prefix', 'legal.consent', '--lang', 'de', '--lang', 'it', '--write'],
    root
  );
  const tosRc = run(['--prefix', 'pages.tos', '--lang', 'de', '--write'], root);
  unmute();

  // (4) dry run writes nothing; (3) empty / absent prefix refused before any read
  if (dry !== 0) fail(`dry run rc ${dry}, want 0`);
  if (afterDry !== before) fail('a dry run wrote the ledger');
  if (emptyRc !== 2 || noneRc !== 2) fail(`empty prefix rc ${emptyRc}/${noneRc}, want 2`);

  const after = JSON.parse(readLedger()) as Ledger;
  const de = after.languages?.de ?? {};
  // (1) scope, order, existing entries untouched
  const deKeys = Object.keys(de);
  const want = ['old.d', 'legal.consent.a', 'legal.consent.b', 'pages.tos.sections.s1.id'];
  if (JSON.stringify(deKeys) !== JSON.stringify(want)) {
    fail(`de keys ${JSON.stringify(deKeys)}, want ${JSON.stringify(want)}`);
  }
  if (de['old.d'] !== 'deadbeef') fail('an existing entry outside the prefix was rewritten');
  if (de['legal.consent.a'] !== '0badc0de') fail('a stale entry under the prefix was restamped');
  if ('legalNotes.c' in de) fail('a sibling key sharing the prefix text was stamped');
  if (Object.keys(after.languages?.fr ?? {}).length !== 2) fail('an unnamed locale was stamped');
  // (2) the gate's own fingerprint
  if (de['legal.consent.b'] !== hashes['legal.consent.b']) fail('fingerprint differs from gate');
  // (5) refusals: it lacks legal.consent.b; de's "1. Definitions" is English-identical
  if (writeRc !== 1) fail(`missing locale value rc ${writeRc}, want 1`);
  if ('legal.consent.b' in (after.languages?.it ?? {})) fail('a missing locale value was stamped');
  if (tosRc !== 1) fail(`identical title rc ${tosRc}, want 1`);
  if ('pages.tos.sections.s1.title' in de) fail('an English-identical title was stamped');
  if (!readLedger().includes('é kept unescaped')) fail('non-ASCII was escaped on write');
  if (before === readLedger()) fail('a --write run changed nothing');

  // (6) control: the scope assertion must reject the pre-dot matcher `k.startsWith(p)`,
  // which treats `legalNotes.c` as under `legal`. Real planner first, then the mutant.
  const enHashes = { 'legal.consent.a': '1', 'legalNotes.c': '2' };
  const scopedTo = (keys: string[], p: string) =>
    keys.every((k) => k === p || k.startsWith(`${p}.`));
  const plans = planStamps({
    enValues: { 'legal.consent.a': 'x', 'legalNotes.c': 'y' },
    enHashes,
    localeValues: { de: { 'legal.consent.a': 'x2', 'legalNotes.c': 'y2' } },
    ledger: { languages: {} },
    prefixes: ['legal'],
    langs: ['de'],
  });
  const real = plans.de.stamp.map(([k]) => k);
  if (JSON.stringify(real) !== '["legal.consent.a"]' || !scopedTo(real, 'legal')) {
    fail(`planner scope ${JSON.stringify(real)}`);
  }
  const mutant = Object.keys(enHashes).filter((k) => k.startsWith('legal'));
  if (scopedTo(mutant, 'legal')) fail('control: the scope assertion passes an unscoped stamp');
} finally {
  unmute();
  fs.rmSync(root, { recursive: true, force: true });
}
console.log('OK: prefix-scoped append-only stamps with the gate fingerprint; refusals hold');
