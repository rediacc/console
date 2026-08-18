#!/usr/bin/env node
/**
 * CI freshness check for `packages/www/src/i18n/client/*.json` and
 * `packages/www/src/i18n/client-route/*.json`.
 *
 * Those twenty-six files are generated from `src/i18n/translations/*.json` by
 * `generate-client-i18n.ts` and COMMITTED, so they are reviewable in a diff. Editing an
 * English or locale value, or adding a key to a hydrated island, changes what the browser
 * needs. If nobody regenerates, the browser keeps shipping the old slice and the affected
 * string renders as its raw key.
 *
 * This regenerates in memory and compares bytes. It never writes.
 *
 * Registration (root package.json, owned by the CI gate wave):
 *   "check:ci-client-i18n": "tsx packages/www/scripts/check-client-i18n-freshness.ts --selftest && tsx packages/www/scripts/check-client-i18n-freshness.ts"
 */

import { SITE_LOCALES, type SiteLocale } from '@rediacc/locales';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { CLIENT_DIRS, buildClientCatalogs, type ClientBundleName } from './generate-client-i18n.ts';

const FIX = 'npm run i18n:generate-client -w @rediacc/www';

type Committed = Map<ClientBundleName, Map<string, string>>;
type Generated = Map<ClientBundleName, Map<SiteLocale, string>>;

function fail(message: string): never {
  process.stderr.write(`\n\x1b[31mFAIL\x1b[0m  ${message}\n\n`);
  process.exit(1);
}

/** Pure comparison, so `--selftest` can drive it with fabricated inputs. */
function findDrift(committed: Committed, generated: Generated): string[] {
  const problems: string[] = [];
  for (const [bundle, perLocale] of generated) {
    const have = committed.get(bundle) ?? new Map<string, string>();
    for (const locale of SITE_LOCALES) {
      const want = perLocale.get(locale);
      if (want === undefined) {
        problems.push(`${bundle}/${locale}: the generator produced nothing`);
        continue;
      }
      const found = have.get(locale);
      if (found === undefined) {
        problems.push(`${bundle}/${locale}.json: missing`);
        continue;
      }
      if (found !== want) {
        problems.push(
          `${bundle}/${locale}.json: stale (${Buffer.byteLength(found)} B committed, ` +
            `${Buffer.byteLength(want)} B regenerated)`
        );
      }
    }
    for (const locale of have.keys()) {
      if (!(SITE_LOCALES as readonly string[]).includes(locale)) {
        problems.push(`${bundle}/${locale}.json: not a site locale, delete it`);
      }
    }
  }
  return problems;
}

function readCommitted(): Committed {
  const out: Committed = new Map();
  for (const bundle of Object.keys(CLIENT_DIRS) as ClientBundleName[]) {
    const dir = CLIENT_DIRS[bundle];
    const perLocale = new Map<string, string>();
    if (fs.existsSync(dir)) {
      for (const entry of fs.readdirSync(dir)) {
        if (!entry.endsWith('.json')) continue;
        perLocale.set(
          entry.slice(0, -'.json'.length),
          fs.readFileSync(path.join(dir, entry), 'utf8')
        );
      }
    }
    out.set(bundle, perLocale);
  }
  return out;
}

function clone(generated: Generated): Committed {
  const out: Committed = new Map();
  for (const [bundle, perLocale] of generated) {
    out.set(bundle, new Map<string, string>([...perLocale]));
  }
  return out;
}

/**
 * Prove the instrument can fire. Four planted faults, each the shape of a real regression:
 * a stale file, a deleted locale, a file for a locale the site does not ship, and a whole
 * bundle directory gone.
 */
function selftest(): void {
  const generated = buildClientCatalogs();

  const stale = clone(generated);
  stale.get('client')!.set('ja', `${stale.get('client')!.get('ja')!} `);

  const deleted = clone(generated);
  deleted.get('client')!.delete('ru');

  const stray = clone(generated);
  stray.get('client-route')!.set('xx', '{}');

  const emptied = clone(generated);
  emptied.set('client-route', new Map());

  const cases: [string, Committed, RegExp | null][] = [
    ['clean tree', clone(generated), null],
    ['stale client/ja.json', stale, /client\/ja\.json: stale/],
    ['deleted client/ru.json', deleted, /client\/ru\.json: missing/],
    ['stray client-route/xx.json', stray, /client-route\/xx\.json: not a site locale/],
    ['client-route/ wiped', emptied, /client-route\/en\.json: missing/],
  ];

  let failures = 0;
  for (const [name, committed, expected] of cases) {
    const problems = findDrift(committed, generated);
    const joined = problems.join('\n');
    const ok = expected === null ? problems.length === 0 : expected.test(joined);
    process.stdout.write(`  ${ok ? 'pass' : 'FAIL'}  selftest: ${name}\n`);
    if (!ok) {
      failures++;
      const wanted = expected === null ? 'a clean tree' : String(expected);
      const got = problems.length > 0 ? joined : 'a clean tree';
      process.stdout.write(`        expected ${wanted}, got: ${got}\n`);
    }
  }
  if (failures > 0) {
    fail(`${failures} selftest case(s) failed. The freshness check cannot be trusted.`);
  }
  process.stdout.write(
    '\nSelftest passed: the check fires on stale, missing, stray and wiped catalogs.\n'
  );
}

function main(): void {
  if (process.argv.includes('--selftest')) {
    selftest();
    return;
  }

  const problems = findDrift(readCommitted(), buildClientCatalogs());
  if (problems.length > 0) {
    fail(
      `packages/www/src/i18n/{client,client-route}/ is out of date:\n` +
        problems.map((p) => `        ${p}`).join('\n') +
        `\n\n        Fix: ${FIX}`
    );
  }

  process.stdout.write(
    `Client i18n catalogs are fresh (${Object.keys(CLIENT_DIRS).length} bundles x ` +
      `${SITE_LOCALES.length} locales).\n`
  );
}

main();
