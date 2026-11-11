/**
 * Control for scripts/gen/sync-translations.ts (`npm run i18n:sync`).
 *
 * On 2026-11-11 a sync meant to add 5 CLI keys rewrote all 12 cli.json files (re-sorted),
 * all 12 www catalogs (re-serialized) and 72 account files that had no English change.
 * These checks pin the contract that prevents it:
 *   1. idempotence: with no English delta no file changes, in the flat and the directory layout;
 *   2. delta-only: a delta is an insertion into the files that lack the keys, every other
 *      byte unchanged, at the position each file's own order convention gives;
 *   3. the control: the pre-fix algorithm (sort every key, re-stringify, always write)
 *      is run through the same assertions and MUST fail them.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { SITE_LOCALES } from '@rediacc/locales';
import { syncLocaleDir } from '../gen/sync-translations.ts';

const TARGETS = SITE_LOCALES.filter((l) => l !== 'en');
const fail = (m: string): never => {
  console.error(`FAIL: ${m}`);
  process.exit(1);
};

// A prettier-style file: an inline array that JSON.stringify would expand, own (unsorted) key order.
const unsortedText = (greeting: string) =>
  `{\n  "zeta": "z",\n  "alpha": {\n    "first": "1",\n    "tags": ["a", "b"]\n  },\n  "greeting": "${greeting}"\n}\n`;
// A sorted file.
const sortedText = (suffix: string) =>
  `{\n  "apple": "a${suffix}",\n  "melon": "m${suffix}",\n  "pear": "p${suffix}"\n}\n`;

const enSorted = JSON.parse(sortedText('')) as Record<string, unknown>;

interface Fixture {
  root: string;
  files: Map<string, string>;
}

function build(): Fixture {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'sync-control-'));
  const files = new Map<string, string>();
  const put = (rel: string, text: string) => {
    const p = path.join(root, rel);
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, text);
    files.set(rel, text);
  };
  put('flat/en.json', unsortedText('hello'));
  put('dir/en/ns.json', unsortedText('hello'));
  put('dir/en/sorted.json', sortedText(''));
  for (const l of TARGETS) {
    put(`flat/${l}.json`, unsortedText(`hi-${l}`));
    put(`dir/${l}/ns.json`, unsortedText(`hi-${l}`));
    put(`dir/${l}/sorted.json`, sortedText(`-${l}`));
  }
  return { root, files };
}

type Sync = (root: string) => void;

const current = (fx: Fixture) =>
  new Map(
    [...fx.files.keys()].map((rel) => [rel, fs.readFileSync(path.join(fx.root, rel), 'utf-8')])
  );

const realSync: Sync = (root) => {
  const quiet = console.log;
  console.log = () => undefined;
  try {
    syncLocaleDir({ name: 'flat', dir: path.join(root, 'flat'), flatFiles: true });
    syncLocaleDir({ name: 'dir', dir: path.join(root, 'dir') });
  } finally {
    console.log = quiet;
  }
};

/** The pre-fix algorithm, kept here as the mutant: sort every key, re-stringify, write always. */
const legacySync: Sync = (root) => {
  const sortKeys = (v: unknown): unknown => {
    if (Array.isArray(v)) return v.map(sortKeys);
    if (v && typeof v === 'object') {
      const o = v as Record<string, unknown>;
      return Object.fromEntries(
        Object.keys(o)
          .sort((a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' }))
          .map((k) => [k, sortKeys(o[k])])
      );
    }
    return v;
  };
  const merge = (
    t: Record<string, unknown>,
    s: Record<string, unknown>
  ): Record<string, unknown> => {
    const out = { ...t };
    for (const [k, v] of Object.entries(s)) {
      if (!(k in out)) out[k] = v;
      else if (v && typeof v === 'object' && !Array.isArray(v) && typeof out[k] === 'object')
        out[k] = merge(out[k] as Record<string, unknown>, v as Record<string, unknown>);
    }
    return out;
  };
  const one = (file: string, en: Record<string, unknown>) => {
    const t = JSON.parse(fs.readFileSync(file, 'utf-8')) as Record<string, unknown>;
    // tree-write: safe the file is under the mkdtemp fixture root that build() made; every caller of one() joins that root
    fs.writeFileSync(file, JSON.stringify(sortKeys(merge(t, en)), null, 2) + '\n');
  };
  for (const l of TARGETS) {
    one(
      path.join(root, `flat/${l}.json`),
      JSON.parse(fs.readFileSync(path.join(root, 'flat/en.json'), 'utf-8'))
    );
    for (const ns of ['ns', 'sorted'])
      one(
        path.join(root, `dir/${l}/${ns}.json`),
        JSON.parse(fs.readFileSync(path.join(root, `dir/en/${ns}.json`), 'utf-8'))
      );
  }
};

/** Returns violations of the contract; empty means the sync honoured it. */
function violations(run: Sync): string[] {
  const bad: string[] = [];

  // 1. Idempotence: no English delta, nothing changes.
  const a = build();
  run(a.root);
  for (const [rel, text] of current(a))
    if (text !== a.files.get(rel)) bad.push(`idempotence: ${rel} changed with no English delta`);

  // 2. Delta-only: English gains keys; one locale already has them.
  const b = build();
  const delta = {
    zeta: 'z',
    alpha: { first: '1', mid: 'MID', tags: ['a', 'b', 'c'] },
    newTop: 'NEW',
    greeting: 'hello',
  };
  fs.writeFileSync(path.join(b.root, 'flat/en.json'), JSON.stringify(delta, null, 2) + '\n');
  fs.writeFileSync(path.join(b.root, 'dir/en/ns.json'), JSON.stringify(delta, null, 2) + '\n');
  fs.writeFileSync(
    path.join(b.root, 'dir/en/sorted.json'),
    JSON.stringify({ ...enSorted, banana: 'b', zebra: 'z' }, null, 2) + '\n'
  );
  const keepRel = 'dir/de/ns.json';
  const keepText = JSON.stringify(delta, null, 2) + '\n';
  fs.writeFileSync(path.join(b.root, keepRel), keepText);
  b.files.set(keepRel, keepText);
  run(b.root);

  const after = current(b);
  if (after.get(keepRel) !== keepText)
    bad.push(`delta: ${keepRel} already complete but was rewritten`);

  const flatDe = after.get('flat/de.json') ?? '';
  // The original lines must all survive, in order, byte-identical (insertion only). The inline
  // `tags` array grows on its own line, so it is checked by value below instead.
  const orig = unsortedText('hi-de')
    .split('\n')
    .filter((l) => !l.includes('"tags"'));
  const got = flatDe.split('\n');
  if (!flatDe.includes('"tags": ["a", "b", "c"]'))
    bad.push('delta: inline array was not extended inline');
  let at = 0;
  for (const line of orig) {
    const found = got.indexOf(line, at);
    if (found === -1) {
      bad.push(
        `delta: original line not preserved byte-identical in flat/de.json: ${JSON.stringify(line)}`
      );
      break;
    }
    at = found + 1;
  }
  const parsed = (() => {
    try {
      return JSON.parse(flatDe) as { alpha?: { mid?: string; tags?: string[] }; newTop?: string };
    } catch {
      return {};
    }
  })();
  if (parsed.alpha?.mid !== 'MID' || parsed.newTop !== 'NEW' || parsed.alpha?.tags?.[2] !== 'c')
    bad.push('delta: flat/de.json lacks the added keys or the appended array item');
  // Unsorted file: newTop follows its English predecessor `alpha`, before `greeting`.
  const order = Object.keys(parsed as object);
  if (order.join() !== 'zeta,alpha,newTop,greeting')
    bad.push(`delta: unsorted file key order is ${order.join()}, want zeta,alpha,newTop,greeting`);

  // Sorted file: new keys land at their sorted positions.
  const sortedRu = after.get('dir/ru/sorted.json') ?? '';
  let sortedKeys: string[] = [];
  try {
    sortedKeys = Object.keys(JSON.parse(sortedRu) as object);
  } catch {
    bad.push('delta: dir/ru/sorted.json is not valid JSON');
  }
  if (sortedKeys.join() !== 'apple,banana,melon,pear,zebra')
    bad.push(
      `delta: sorted file key order is ${sortedKeys.join()}, want apple,banana,melon,pear,zebra`
    );
  if (!sortedRu.includes('"apple": "a-ru"'))
    bad.push('delta: existing sorted values were rewritten');

  return bad;
}

const real = violations(realSync);
if (real.length > 0) fail(`the fixed sync broke its contract:\n  ${real.join('\n  ')}`);

const mutant = violations(legacySync);
if (mutant.length === 0)
  fail(
    'CONTROL VACUOUS: the pre-fix algorithm passed every assertion, so they cannot see the defect'
  );

console.log(
  `sync-translations control ok: fixed sync clean; pre-fix algorithm tripped ${mutant.length} violation(s)`
);
