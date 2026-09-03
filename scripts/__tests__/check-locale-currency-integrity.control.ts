/**
 * Control for check-locale-currency-integrity.
 * A gate nobody has watched fail is not a gate, so this plants the real 2026-08-27
 * corruption and also plants the legitimate translations that a broader rule
 * false-positived on, and requires the gate to separate them.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { findCorruptions } from '../check-locale-currency-integrity.ts';

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'currency-control-'));
const write = (n: string, o: unknown) =>
  fs.writeFileSync(path.join(dir, `${n}.json`), JSON.stringify(o, null, 2));

write('en', {
  a: '$4.88M',
  b: '$90K–$300K',
  legitDe: 'The average cost of downtime is $5,600 per minute',
  legitJa: 'Ransomware costs $4.62 million',
  untouched: '$200/hr',
});
// ar carries the real corruption on a and b, and correct values elsewhere.
write('ar', {
  a: '.88M',
  b: '0K–00K',
  legitDe: '...$5,600...',
  legitJa: '...$4.62...',
  untouched: '$200/hr',
});
// de/ja carry genuine localisation: the amount is rewritten, not eaten.
write('de', {
  a: '4,88 Mio. $',
  b: '90–300 Tsd. $',
  legitDe: 'Ausfallkosten 5.600 $ pro Minute',
  legitJa: '4,62 Mio. $',
  untouched: '200 $/Std.',
});
write('ja', {
  a: '488万ドル',
  b: '9万〜30万ドル',
  legitDe: '1分5,600ドル',
  legitJa: '462万ドル',
  untouched: '200ドル/時',
});

const found = findCorruptions(dir);
const fail = (m: string) => {
  console.error(`FAIL: ${m}`);
  process.exit(1);
};

if (found.length !== 2)
  fail(`expected exactly 2 findings, got ${found.length}: ${JSON.stringify(found)}`);
if (!found.every((f) => f.locale === 'ar'))
  fail(`a legitimate localisation was flagged: ${JSON.stringify(found)}`);
if (new Set(found.map((f) => f.key)).size !== 2) fail('the two findings are not distinct keys');

// And the gate must go quiet once the corruption is repaired.
write('ar', {
  a: '$4.88M',
  b: '$90K–$300K',
  legitDe: '...$5,600...',
  legitJa: '...$4.62...',
  untouched: '$200/hr',
});
const after = findCorruptions(dir);
if (after.length !== 0) fail(`gate still fires after repair: ${JSON.stringify(after)}`);

fs.rmSync(dir, { recursive: true, force: true });
console.log(
  '✓ control: fires on the eaten-amount signature (2), silent on 3 legitimate localisations and after repair.'
);
