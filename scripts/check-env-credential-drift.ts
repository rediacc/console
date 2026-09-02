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
 * SO THE GATE OUTLIVES ITS FIRST SYMPTOM, deliberately. run.sh:1433-1437 sources
 * this file and run.sh:1526-1539 pushes the quartet into a Cloudflare Worker's
 * secrets, so a stale value here still ships. Losing the hook that happened to
 * notice first is a reason to keep the check, not to drop it.
 * (This block used to add "and .ci/scripts/deploy/set-account-worker-secrets.sh
 * reads the same file". It does not -- that script has zero .env references and
 * takes every secret from the process env CI supplies. Corrected 2026-09-02; the
 * argument survives through run.sh, the citation did not.)
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
  // R2. Added 2026-09-02 after the live check that this gate could not make:
  // `.env`'s CLOUDFLARE_R2_ACCESS_KEY_ID is the Cloudflare token `Github-R2`, which the
  // manifest records as **grace** for cf-r2. Local dev is therefore running on
  // a credential already scheduled for deactivation, and nothing said so --
  // this list only ever named the two SES keys.
  { key: 'CLOUDFLARE_R2_ACCESS_KEY_ID', slugs: ['cf-r2'] },
  // Found by SWEEPING the class rather than tripping over it: every value in
  // `.env` was compared against every version id in the manifest, and this was
  // the one other match that nothing tracked. It is `active` today, so it adds
  // no noise now -- it is here to catch the drift, not to report one.
  { key: 'CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID', slugs: ['cf-r2-media'] },
  //
  // DELIBERATELY ABSENT, and this list is the whole answer to "why not also
  // track X" -- do not add these back without reading why:
  //
  //   CLOUDFLARE_R2_SECRET_ACCESS_KEY, CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY, CLOUDFLARE_BREAKPOINT_TUNNEL_TOKEN
  //     NOT ID-MATCHABLE BY CONSTRUCTION. The manifest records a token ID; the
  //     `.env` value is the token's SECRET. For an R2 keypair the id half IS the
  //     token id (which is why the two above work) and the secret half is
  //     sha256(value), which appears in no manifest. Tracking these would report
  //     permanent false drift -- exactly the category error that had `AWS_IAM_ADMIN_ACCESS_KEY_ID`
  //     in this list until 2026-09-02.
  //
  //   CLOUDFLARE_TURNSTILE_SECRET_KEY (the .env key; the GitHub secret is still CLOUDFLARE_TURNSTILE_SECRET_KEY)
  //     `turnstile` and `turnstile-bench` have ZERO versions recorded in the
  //     manifest (verified 2026-09-02; every other slug has 1-4). There is
  //     nothing to compare against, so this cannot be a membership test today.
  //     That is a real gap in the RECORD, not in this gate: two live credentials
  //     sit outside rotation entirely, so nothing tracks their age and
  //     `deactivate`/`delete` have nothing to act on. Fixing it means seeding
  //     those versions, which is operator work.
  //
  //   AWS_IAM_ADMIN_ACCESS_KEY_ID / AWS_IAM_ADMIN_SECRET_ACCESS_KEY, CF_GLOBAL_API_KEY, CF_EMAIL
  //     Operator-held ADMIN credentials that mint the others. No slug records
  //     them and none can; see the note above the SES entry.
  // NOT `AWS_IAM_ADMIN_ACCESS_KEY_ID`. It was tracked against the ses-* slugs until 2026-09-02,
  // which is a category error: `AWS_IAM_ADMIN_ACCESS_KEY_ID`/`AWS_IAM_ADMIN_SECRET_ACCESS_KEY` are the AWS **IAM
  // admin** credential the rotation tool uses to CREATE and DELETE the SES
  // sending keys (`scripts/rotation/lib/credentials.ts:59-61`,
  // `resolveAwsAdmin`). It is not itself a rotated sending key, no manifest
  // slug records it, and none can -- there is no admin slug. So the check
  // could never pass for it, and a gate that is permanently red is worse than
  // one that cannot fail: it teaches you to skip the output.
  //
  // The real gap this leaves is honest and worth stating: the admin credential
  // is outside the rotation record entirely, so nothing tracks its age. Closing
  // that means adding an `aws-admin` slug to the manifest, which is the
  // operator's call, not this gate's.
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

/** Every version id the manifest knows, per slug, mapped to its state. */
export const manifestIds = (json: unknown): Map<string, Map<string, string>> => {
  const out = new Map<string, Map<string, string>>();
  const root = json as Record<string, unknown>;
  const creds = (root.credentials ?? root) as Record<
    string,
    { versions?: { id?: string; state?: string }[] }
  >;
  for (const [slug, v] of Object.entries(creds ?? {})) {
    if (!v || typeof v !== 'object') continue;
    const ids = new Map<string, string>();
    for (const ver of v.versions ?? []) {
      if (ver?.id) ids.set(String(ver.id), String(ver.state ?? 'unknown'));
    }
    out.set(slug, ids);
  }
  return out;
};

export interface Drift {
  key: string;
  idPrefix: string;
  slugs: string[];
  /**
   * 'absent'  the value is in NO listed slug -- the original defect.
   * 'retiring' the value IS recorded, but under a version whose state is
   *            `grace` or `inactive`: it works today and is scheduled to stop.
   *
   * Membership alone cannot see the second case, and the second case is the one
   * with a date attached. `Github-R2` is `grace` for cf-r2 right now while
   * `.env` still uses it; a `deactivate cf-r2` retires it and local dev breaks
   * with a credentials error naming none of this.
   */
  kind: 'absent' | 'retiring';
  state?: string;
}

export const findDrift = (
  env: Record<string, string>,
  ids: Map<string, Map<string, string>>
): Drift[] => {
  const out: Drift[] = [];
  for (const { key, slugs } of TRACKED) {
    const value = env[key];
    if (!value) continue;
    const prefix = `${value.slice(0, 8)}...`;
    let state: string | undefined;
    for (const s of slugs) {
      const found = ids.get(s)?.get(value);
      // Prefer an `active` match: a value may legitimately appear under one
      // slug as active and another as grace.
      if (found && (state === undefined || found === 'active')) state = found;
    }
    if (state === undefined) {
      out.push({ key, idPrefix: prefix, slugs, kind: 'absent' });
    } else if (state !== 'active') {
      out.push({ key, idPrefix: prefix, slugs, kind: 'retiring', state });
    }
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

  const ids = manifestIds({
    credentials: { 'ses-eu': { versions: [{ id: 'AKIA_GOOD', state: 'active' }] } },
  });
  check('reads version ids per slug', ids.get('ses-eu')?.get('AKIA_GOOD') === 'active');
  check('reads the version STATE, not just the id', ids.get('ses-eu')?.get('AKIA_GOOD') === 'active');

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
      manifestIds({
        credentials: { 'ses-asia': { versions: [{ id: 'AKIA_ASIA', state: 'active' }] } },
      })
    ).length === 0
  );
  // THE SECOND DEFECT, added 2026-09-02: membership is not enough. A value can
  // be recorded and still be on its way out, which is the live state of
  // `.env`'s CLOUDFLARE_R2_ACCESS_KEY_ID (the `Github-R2` token, `grace` under cf-r2).
  const graceIds = manifestIds({
    credentials: { 'cf-r2': { versions: [{ id: 'TOK_GRACE', state: 'grace' }] } },
  });
  const graceDrift = findDrift({ CLOUDFLARE_R2_ACCESS_KEY_ID: 'TOK_GRACE' }, graceIds);
  check('a recorded but RETIRING version is reported', graceDrift.length === 1);
  check('and it is classified as retiring, not absent', graceDrift[0]?.kind === 'retiring');
  check('and it carries the state that explains why', graceDrift[0]?.state === 'grace');
  check(
    'an ACTIVE version under the same slug is still clean',
    findDrift(
      { CLOUDFLARE_R2_ACCESS_KEY_ID: 'TOK_OK' },
      manifestIds({ credentials: { 'cf-r2': { versions: [{ id: 'TOK_OK', state: 'active' }] } } })
    ).length === 0
  );
  // CONTROL for the preference rule: active wins over grace across slugs.
  check(
    'a value active under one slug is clean even if grace under another',
    findDrift(
      { AWS_SES_ACCESS_KEY_ID: 'DUP' },
      manifestIds({
        credentials: {
          'ses-eu': { versions: [{ id: 'DUP', state: 'grace' }] },
          'ses-us': { versions: [{ id: 'DUP', state: 'active' }] },
        },
      })
    ).length === 0
  );
  check('an absent value is still classified absent', findDrift({ AWS_SES_ACCESS_KEY_ID: 'NOPE' }, ids)[0]?.kind === 'absent');
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

  let ids: Map<string, Map<string, string>>;
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
    const absent = drifts.filter((d) => d.kind === 'absent');
    const retiring = drifts.filter((d) => d.kind === 'retiring');
    console.error(`✗ ${drifts.length} credential(s) in ${ENV_FILE} disagree with the record:`);
    for (const d of absent) {
      console.error(
        `    ABSENT   ${d.key} = ${d.idPrefix}  (no version of ${d.slugs.join(', ')} records it)`
      );
    }
    for (const d of retiring) {
      console.error(
        `    RETIRING ${d.key} = ${d.idPrefix}  (recorded under ${d.slugs.join(', ')}, ` +
          `but state is "${d.state}", not active)`
      );
    }
    console.error('');
    if (absent.length > 0) {
      console.error('  ABSENT means the file is stale relative to the record, which is how a');
      console.error('  rotated-out key keeps being used until something unrelated stops');
      console.error('  working. Re-run the rotation for that slug, or paste the current');
      console.error('  credential into the file.');
    }
    if (retiring.length > 0) {
      console.error('  RETIRING is the more urgent one, because it has a DATE attached: the');
      console.error('  key works today and is scheduled to stop. `./run.sh rotation status`');
      console.error('  shows when. A `deactivate` for that slug will break local development');
      console.error('  with a credentials error that names none of this.');
    }
    return 1;
  }

  console.log(
    `✓ ${tracked.length} tracked credential(s) in ${ENV_FILE} match the rotation manifest`
  );
  return 0;
};

process.exit(main());
