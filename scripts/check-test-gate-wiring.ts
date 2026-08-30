#!/usr/bin/env tsx
/**
 * A `check:test*` key that exists only in package.json is a test suite nobody runs.
 *
 * WHY THIS EXISTS. `check:test:tutorial-player` sat in package.json, fully defined
 * (`node scripts/test-tutorial-player-release-gate.js`), for three months without a single
 * CI run: `scripts/ci-runner/manifest.ts` had no entry for it and `ci-quality.yml` never
 * called it. Found by hand this session, not by any gate -- `check:ci-gate-manifest`
 * validates the INTERNAL consistency of entries already IN manifest.ts (leaves, paths,
 * tiers); it has no way to notice a package.json key that was never added to manifest.ts
 * at all, because that key is simply not part of its input. This closes that specific gap
 * for the `check:test*` namespace, where "defined but never run" is worst: a whole browser-
 * driven regression suite can silently stop protecting anything.
 *
 * WHAT IT CHECKS. Every package.json `scripts` key matching `^check:test[:-]` must appear
 * in `scripts/ci-runner/manifest.ts` (as an `id` or inside a `run:` string) AND that
 * manifest entry's `ci.workflow` must be `.github/workflows/ci-quality.yml` -- reachable
 * from `npm run ci`, not merely mentioned somewhere.
 *
 * WHAT IT DOES NOT DO. It does not check every `check:*` key (that is the much broader,
 * already-answered-elsewhere sweep this session did by hand); `check:test*` is singled out
 * because it is the namespace for real regression suites, where an unwired entry is a
 * silent coverage hole rather than a convenience alias.
 *
 * Usage:
 *   npx tsx scripts/check-test-gate-wiring.ts [--selftest]
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const REPO_ROOT = path.resolve(import.meta.dirname, '..');

interface WiringCheck {
  key: string;
  inManifest: boolean;
  wiredToCiQuality: boolean;
}

function findUnwired(
  packageJsonScripts: Record<string, string>,
  manifestSource: string
): WiringCheck[] {
  const results: WiringCheck[] = [];
  for (const key of Object.keys(packageJsonScripts)) {
    if (!/^check:test[:-]/.test(key)) continue;
    const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    // The key appears either as the entry's own id ('check:test:x') or inside its
    // `run: 'npm run check:test:x'` string -- both are legitimate registrations.
    const mentionRe = new RegExp(`['"]${escaped}['"]`);
    const mentionIdx = manifestSource.search(mentionRe);
    const inManifest = mentionIdx !== -1;
    let wiredToCiQuality = false;
    if (inManifest) {
      // Scan forward from the mention to the entry's closing brace (next top-level
      // `},\n  {` boundary or `ci: {` block) for the workflow this entry targets.
      const slice = manifestSource.slice(mentionIdx, mentionIdx + 2000);
      wiredToCiQuality = /workflow:\s*'\.github\/workflows\/ci-quality\.yml'/.test(slice);
    }
    results.push({ key, inManifest, wiredToCiQuality });
  }
  return results.sort((a, b) => a.key.localeCompare(b.key));
}

function selftest(): number {
  let failures = 0;
  const check = (name: string, ok: boolean) => {
    if (ok) {
      console.log(`ok   control: ${name}`);
    } else {
      console.log(`FAIL control: ${name}`);
      failures++;
    }
  };

  const fakeManifest = `
  {
    id: 'check:test:wired',
    run: 'npm run check:test:wired',
    ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'x', step: 'y' },
  },
  {
    id: 'check:test:wrong-workflow',
    run: 'npm run check:test:wrong-workflow',
    ci: { kind: 'step', workflow: '.github/workflows/ci.yml', job: 'x', step: 'y' },
  },
  `;
  const fakeScripts = {
    'check:test:wired': 'x',
    'check:test:wrong-workflow': 'x',
    'check:test:missing': 'x',
    'check:test-dashform': 'x',
    'check:other-thing': 'x', // must NOT be picked up: not a check:test* key
  };

  const found = findUnwired(fakeScripts, fakeManifest);

  check(
    'a package.json check:test* key absent from manifest.ts is caught',
    found.find((f) => f.key === 'check:test:missing')?.inManifest === false
  );
  check(
    'a key present in manifest.ts but wired to the wrong workflow is caught',
    found.find((f) => f.key === 'check:test:wrong-workflow')?.wiredToCiQuality === false
  );
  check(
    'a fully wired key passes both checks',
    found.find((f) => f.key === 'check:test:wired')?.inManifest === true &&
      found.find((f) => f.key === 'check:test:wired')?.wiredToCiQuality === true
  );
  check(
    'the dash-form namespace (check:test-x) is scanned too, not only the colon form',
    found.some((f) => f.key === 'check:test-dashform')
  );
  check(
    'an unrelated check:* key outside the test namespace is not scanned',
    !found.some((f) => f.key === 'check:other-thing')
  );

  return failures;
}

function main(): number {
  if (process.argv.includes('--selftest')) {
    console.log('test-gate wiring selftest');
    const bad = selftest();
    console.log(bad === 0 ? 'selftest: all controls passed' : `selftest: ${bad} control(s) FAILED`);
    return bad === 0 ? 0 : 1;
  }

  if (selftest() !== 0) {
    console.error('x the rule itself is broken, so no verdict it produces means anything.');
    return 1;
  }

  const pkg = JSON.parse(readFileSync(path.join(REPO_ROOT, 'package.json'), 'utf8'));
  const manifestSource = readFileSync(
    path.join(REPO_ROOT, 'scripts/ci-runner/manifest.ts'),
    'utf8'
  );

  const results = findUnwired(pkg.scripts ?? {}, manifestSource);
  if (results.length === 0) {
    console.error('x found zero check:test* keys -- the scope pattern is broken, not the tree clean.');
    return 1;
  }

  const broken = results.filter((r) => !r.inManifest || !r.wiredToCiQuality);
  if (broken.length > 0) {
    console.error(`x ${broken.length} of ${results.length} check:test* key(s) not fully wired:`);
    for (const r of broken) {
      if (!r.inManifest) {
        console.error(`    ${r.key}: NOT REGISTERED in scripts/ci-runner/manifest.ts`);
      } else {
        console.error(`    ${r.key}: registered, but not wired to ci-quality.yml`);
      }
    }
    return 1;
  }

  console.log(`✓ ${results.length} check:test* key(s), all registered and wired to ci-quality.yml`);
  return 0;
}

process.exit(main());
