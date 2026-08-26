#!/usr/bin/env tsx
/**
 * check:env-credential-drift -- the production .env must not hold a credential
 * the rotation manifest has never recorded.
 *
 * DELIBERATELY NOT A check:ci-* KEY. private/account/.env is gitignored, so it is
 * never present in CI; a CI-wired entry would skip on every run, which is a gate
 * that is defined, reachable, and structurally incapable of checking anything.
 * The credential lives on developer machines, so this runs where bench's
 * equivalent already does: a blocking preflight in ./run.sh setup, with
 * SKIP_ENV_DRIFT_CHECK=1 as the documented escape.
 *
 * THE DEFECT THIS CLOSES, found 2026-08-26. The stop hook's operator email had
 * been failing with `SES HTTP 403: The security token included in the request is
 * invalid`. That consumer (`wl_email.py`) has since been REMOVED, but the stale
 * credential it exposed is still live and still shipped: the
 * AWS_SES_ACCESS_KEY_ID in `private/account/.env` appears in no version of any
 * `ses-*` slug in `rotation-manifest.json`, while `./run.sh rotation check`
 * passes every `ses-*` slug. Manifest-vs-AWS was healthy; only `.env` was
 * stale, left behind by a rotation.
 *
 * SO THE GATE OUTLIVES ITS FIRST SYMPTOM, deliberately. run.sh pushes this exact
 * quartet into the Cloudflare account worker's secrets, and
 * .ci/scripts/deploy/set-account-worker-secrets.sh reads the same file, so a
 * stale value here still ships to production email. Losing the hook that
 * happened to notice first is a reason to keep the check, not to drop it.
 *
 * WHY NOTHING CAUGHT IT. There is exactly one rotation preflight in the repo:
 * `rotation check --for=bench` at scripts/dev/deploy-bench.sh:131, which covers
 * `.env.bench`. A stale BENCH key is blocked from shipping; a stale PRODUCTION
 * key just silently stops mail, and the failure surfaces somewhere unrelated
 * days later. This gate closes that asymmetry.
 *
 * WHAT IT COMPARES, and what it deliberately does not. It checks IDENTIFIERS
 * only -- an AWS access key id, a Cloudflare token id -- against the ids the
 * manifest records. It never reads, prints or transmits a secret, and it never
 * contacts AWS or Cloudflare: liveness is `rotation check`'s job and needs
 * admin credentials CI does not have. This is the cheap, offline, always-runnable
 * half: does the file agree with the record.
 *
 * SKIPS, LOUDLY, when the private submodule is absent, which is the normal state
 * for a checkout without submodule access. A skip prints its reason; it is never
 * silent, because a gate that quietly does nothing is the failure this repo
 * names most often.
 */

import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const ENV_FILE = 'private/account/.env';
export const MANIFEST = 'private/account/rotation-manifest.json';

/** env var -> the manifest slugs whose versions may legitimately supply it. */
export const TRACKED: ReadonlyArray<{ key: string; slugs: string[] }> = [
  { key: 'AWS_SES_ACCESS_KEY_ID', slugs: ['ses-eu', 'ses-us', 'ses-asia'] },
  { key: 'SES_AK_ID', slugs: ['ses-eu', 'ses-us', 'ses-asia'] },
];

export const parseEnv = (source: string): Record<string, string> => {
  const out: Record<string, string> = {};
  for (const raw of source.split('\n')) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq <= 0) continue;
    const key = line.slice(0, eq);
    if (!/^[A-Z0-9_]+$/.test(key)) continue;
    out[key] = line
      .slice(eq + 1)
      .trim()
      .replace(/^["']|["']$/g, '');
  }
  return out;
};

/** Every version id the manifest knows, per slug. */
export const manifestIds = (json: unknown): Map<string, Set<string>> => {
  const out = new Map<string, Set<string>>();
  const root = json as Record<string, unknown>;
  const creds = (root.credentials ?? root) as Record<string, { versions?: { id?: string }[] }>;
  for (const [slug, v] of Object.entries(creds ?? {})) {
    if (!v || typeof v !== 'object') continue;
    const ids = new Set<string>();
    for (const ver of v.versions ?? []) if (ver?.id) ids.add(String(ver.id));
    out.set(slug, ids);
  }
  return out;
};

export interface Drift {
  key: string;
  idPrefix: string;
  slugs: string[];
}

export const findDrift = (env: Record<string, string>, ids: Map<string, Set<string>>): Drift[] => {
  const out: Drift[] = [];
  for (const { key, slugs } of TRACKED) {
    const value = env[key];
    if (!value) continue;
    const known = slugs.some((s) => ids.get(s)?.has(value));
    if (!known) out.push({ key, idPrefix: `${value.slice(0, 8)}...`, slugs });
  }
  return out;
};

const selftest = (): number => {
  let fail = 0;
  const check = (name: string, ok: boolean): void => {
    if (!ok) fail += 1;
    console.log(`  ${ok ? 'PASS' : 'FAIL'}  ${name}`);
  };

  const env = parseEnv('A=1\n# c=2\nB="q"\nBAD LINE\nlower=3\n');
  check('parses plain values', env.A === '1');
  check('strips quotes', env.B === 'q');
  check('skips comments', env['# c'] === undefined && env.c === undefined);
  check('skips non-uppercase keys', env.lower === undefined);

  const ids = manifestIds({ credentials: { 'ses-eu': { versions: [{ id: 'AKIA_GOOD' }] } } });
  check('reads version ids per slug', ids.get('ses-eu')?.has('AKIA_GOOD') === true);

  check(
    'a key present in the manifest is clean',
    findDrift({ AWS_SES_ACCESS_KEY_ID: 'AKIA_GOOD' }, ids).length === 0
  );
  // THE DEFECT: the exact shape that broke operator email.
  check(
    'a key absent from the manifest is drift',
    findDrift({ AWS_SES_ACCESS_KEY_ID: 'AKIA_STALE' }, ids).length === 1
  );
  // CONTROLS: without these a gate that flags everything would still pass above.
  check('an unset key is not drift', findDrift({}, ids).length === 0);
  check('an empty value is not drift', findDrift({ AWS_SES_ACCESS_KEY_ID: '' }, ids).length === 0);
  check(
    'a match under ANY listed slug counts',
    findDrift(
      { AWS_SES_ACCESS_KEY_ID: 'AKIA_ASIA' },
      manifestIds({ credentials: { 'ses-asia': { versions: [{ id: 'AKIA_ASIA' }] } } })
    ).length === 0
  );
  check(
    'the drift report carries no secret, only a prefix',
    findDrift({ AWS_SES_ACCESS_KEY_ID: 'AKIA_SECRET_VALUE' }, ids)[0].idPrefix === 'AKIA_SEC...'
  );
  return fail === 0 ? 0 : 1;
};

const main = (): number => {
  if (process.argv.slice(2).includes('--selftest')) return selftest();

  const envPath = path.join(REPO, ENV_FILE);
  const manPath = path.join(REPO, MANIFEST);
  if (!fs.existsSync(envPath) || !fs.existsSync(manPath)) {
    console.log(`- skipped: ${ENV_FILE} or ${MANIFEST} absent (private submodule not checked out)`);
    return 0;
  }

  let ids: Map<string, Set<string>>;
  try {
    ids = manifestIds(JSON.parse(fs.readFileSync(manPath, 'utf8')));
  } catch (err) {
    console.error(`✗ ${MANIFEST} is unreadable: ${(err as Error).message}`);
    return 1;
  }
  if (ids.size === 0) {
    console.error(`✗ ${MANIFEST} yielded no credentials; the scan has lost its subject.`);
    return 1;
  }

  const env = parseEnv(fs.readFileSync(envPath, 'utf8'));
  const tracked = TRACKED.filter((t) => env[t.key]);
  if (tracked.length === 0) {
    console.log(`- skipped: none of the tracked keys are set in ${ENV_FILE}`);
    return 0;
  }

  const drifts = findDrift(env, ids);
  if (drifts.length > 0) {
    console.error(
      `✗ ${drifts.length} credential(s) in ${ENV_FILE} are not in the rotation manifest:`
    );
    for (const d of drifts) {
      console.error(
        `    ${d.key} = ${d.idPrefix}  (no version of ${d.slugs.join(', ')} records it)`
      );
    }
    console.error('');
    console.error('  The file is stale relative to the record, which is how a rotated-out key');
    console.error('  keeps being used until something unrelated stops working. Re-run the');
    console.error('  rotation for that slug, or paste the current credential into the file.');
    return 1;
  }

  console.log(
    `✓ ${tracked.length} tracked credential(s) in ${ENV_FILE} match the rotation manifest`
  );
  return 0;
};

process.exit(main());
