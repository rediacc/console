/**
 * CI guardrail: verify the `dkim-notify` rotation is reachable via public DNS.
 *
 * Resolves the `<selector>._domainkey.<domain>` TXT record for every active
 * version in `private/account/rotation-manifest.json` and confirms it contains
 * a well-formed DKIM1 policy with a non-empty public key. Also re-hashes the
 * public key and compares against the fingerprint stored in the manifest at
 * rotate time — catching Cloudflare-side edits or parallel rotations on other
 * machines the moment they happen.
 *
 * This specifically covers the failure mode that caused the incident this
 * migration addresses: AWS Easy DKIM advertised three selectors on
 * `notify.rediacc.com`, only one of which returned a real public key — two
 * were empty strings at `*.dkim.amazonses.com`. DMARC `p=reject; adkim=s`
 * rejected ~67% of mail silently. The BYODKIM rotation tool records the
 * selector + fingerprint; this check is the daily proof that the selector
 * it published still resolves to the key it expects.
 *
 * Additional sanity: resolves the `bounce-<region>.notify.rediacc.com` MX
 * records for every region declared active in the rotation config and
 * confirms each points at the matching `feedback-smtp.<region>.amazonses.com`.
 * A missing or drifted MAIL FROM record collapses SPF alignment (one of
 * DMARC's two halves) so catching this alongside the DKIM side keeps the
 * whole authentication stack visible.
 *
 * Run: npx tsx scripts/gates/check-dkim-notify.ts
 * Exits 0 on success, 1 on any failure.
 *
 * FAILS CLOSED ON EVERY CADENCE (operator ruling 2026-10-14, "Extend to all
 * seven"). Each query asks 1.1.1.1 and then 8.8.8.8 (5 s each) and is retried
 * under the shared rule in scripts/lib/upstream.ts: three attempts, 2 s then
 * 4 s between them. A resolver that answers NXDOMAIN or NODATA has answered, and
 * the missing record is a finding about DNS. A query neither resolver answered
 * (a timeout, a refused connection, SERVFAIL) was NOT checked, and is a red
 * finding with the sentence `UPSTREAM REACHABILITY FAILURE`. The step runs the
 * gate with no run_external_gate wrapper, so it is red on the nightly too; the
 * `no-external-quality` label on a pull request is the one hold, and its job's
 * announcer names this gate.
 *
 * TEST SEAMS: `DKIM_MANIFEST_FILE` reads another rotation manifest, and
 * `DKIM_RESOLVERS` (comma-separated `host:port`) asks other resolvers, a stub
 * DNS server in the gate test.
 *
 * ---- gate ----
 * step: DKIM notify DNS
 * needs: node, submodules
 * lane: quality-content
 * when: inputs.external_quality != 'skip'
 * ---- end gate ----
 */

import { createHash } from 'node:crypto';
import { Resolver } from 'node:dns/promises';
import { readFileSync } from 'node:fs';
import * as path from 'node:path';
import { type Failure, NotCompared, reportUnreachable, retryUpstream } from '../lib/upstream.js';

interface ManifestVersion {
  id: string;
  name?: string | null;
  state?: string;
}
interface ManifestDkimNotify {
  platform: 'dkim-notify';
  domain: string;
  region_identities?: Record<string, string>;
  versions: ManifestVersion[];
}
interface Manifest {
  credentials: Record<
    string,
    { platform: string; versions?: ManifestVersion[] } & Partial<ManifestDkimNotify>
  >;
}

const MANIFEST_PATH = 'private/account/rotation-manifest.json';
// Per resolver, inside one attempt: both resolvers fit in one attempt of the shared 15 s budget.
const TIMEOUT_MS = 5_000;

// Active-region → AWS region mapping (matches `private/account/scripts/rotation/lib/config.ts:ROTATION_CONFIG.awsSes`). Kept in lockstep manually because this script also runs on `ubuntu-slim` CI runners that don't install the account package.
const REGION_MAPPING: Record<string, string> = {
  eu: 'eu-central-1',
  us: 'us-east-1',
  asia: 'ap-northeast-1',
};

// Regions to check MAIL FROM MX records for. `bench` shares `eu` so we skip it. `asia` is kept in the set even though its SES identity isn't production- approved: the MAIL FROM DNS is already published and will stay published, and checking it catches drift before asia gets flipped on.
const MAIL_FROM_REGIONS: Array<{ alias: string; mxTarget: string }> = [
  { alias: 'eu', mxTarget: `feedback-smtp.${REGION_MAPPING.eu}.amazonses.com` },
  { alias: 'us', mxTarget: `feedback-smtp.${REGION_MAPPING.us}.amazonses.com` },
  { alias: 'asia', mxTarget: `feedback-smtp.${REGION_MAPPING.asia}.amazonses.com` },
];

// Use public resolvers in CI — the runner's default resolver sometimes has shorter TTL caches for recently-changed records. 1.1.1.1 and 8.8.8.8 are independent networks so we get a cross-check on divergent answers.
const PUBLIC_RESOLVERS = (process.env.DKIM_RESOLVERS || '1.1.1.1,8.8.8.8')
  .split(',')
  .map((server) => server.trim())
  .filter(Boolean);

// A resolver that answers these has answered: the name or the record does not exist. Every other error code (ETIMEOUT, ECONNREFUSED, ESERVFAIL, EREFUSED, ...) means no answer was obtained.
const ANSWERED_ABSENT = new Set(['ENOTFOUND', 'ENODATA']);

async function withTimeout<T>(promise: Promise<T>, ms: number, label: string): Promise<T> {
  let timeout: NodeJS.Timeout | undefined;
  const timer = new Promise<never>((_, reject) => {
    timeout = setTimeout(
      () =>
        reject(Object.assign(new Error(`${label} timed out after ${ms}ms`), { code: 'ETIMEOUT' })),
      ms
    );
  });
  try {
    return await Promise.race([promise, timer]);
  } finally {
    if (timeout) clearTimeout(timeout);
  }
}

/**
 * One DNS question, asked of each resolver in turn, under the shared retry budget. Returns the records, an EMPTY list
 * when a resolver answered that none exist, or throws NotCompared when no resolver answered.
 */
async function askDns<T>(
  rrtype: 'TXT' | 'MX',
  name: string,
  query: (resolver: Resolver) => Promise<T[]>
): Promise<T[]> {
  const once = async (): Promise<{ value: T[] } | Failure> => {
    let lastCode = 'no resolver';
    for (const server of PUBLIC_RESOLVERS) {
      const resolver = new Resolver({ timeout: TIMEOUT_MS, tries: 1 });
      resolver.setServers([server]);
      try {
        return {
          value: await withTimeout(query(resolver), TIMEOUT_MS, `${rrtype} ${name}@${server}`),
        };
      } catch (err) {
        const code = (err as { code?: unknown }).code;
        if (typeof code === 'string' && ANSWERED_ABSENT.has(code)) return { value: [] };
        lastCode = `${server} ${typeof code === 'string' ? code : 'error'}`;
      }
    }
    return {
      what: `DNS ${lastCode}`,
      retry: true,
      status: null,
      retryAfterS: null,
      unreachable: true,
    };
  };
  return retryUpstream(
    { asked: `${rrtype} ${name}`, host: PUBLIC_RESOLVERS.join(', '), who: name },
    once
  );
}

async function main(): Promise<number> {
  // ANCHORED ON THIS FILE, not on cwd. process.cwd() is the workspace root under `npm run` and something else under any other caller, so the same gate would read a different manifest depending on where it was started.
  const manifestPath =
    process.env.DKIM_MANIFEST_FILE || path.resolve(import.meta.dirname, '..', '..', MANIFEST_PATH);
  let manifest: Manifest;
  try {
    const raw = readFileSync(manifestPath, 'utf-8');
    manifest = JSON.parse(raw) as Manifest;
  } catch (err) {
    process.stderr.write(
      `error: could not read ${MANIFEST_PATH}: ${err instanceof Error ? err.message : String(err)}\n`
    );
    return 1;
  }

  const dkim = Object.entries(manifest.credentials).find(
    ([, cred]) => cred.platform === 'dkim-notify'
  );

  if (!dkim) {
    // No dkim-notify entry yet — the rotation tool hasn't been run at least once. Phase 1 of the SES BYODKIM migration should seed this; until it does, the check is a no-op (otherwise CI fails before the migration even starts).
    process.stdout.write('SKIP: no dkim-notify credential in manifest yet (pre-migration state)\n');
    return 0;
  }

  const [slug, cred] = dkim;
  const domain = cred.domain;
  const versions = cred.versions ?? [];
  const active = versions.find((v) => v.state === 'active');

  if (!active) {
    process.stdout.write(`SKIP: ${slug} has no active version (pre-first-rotate)\n`);
    return 0;
  }

  if (!domain) {
    process.stderr.write(`FAIL: ${slug} has no domain field\n`);
    return 1;
  }

  const errors: string[] = [];
  const unanswered: Array<{ who: string; err: NotCompared }> = [];
  // FAIL CLOSED: a query no resolver answered is its own finding, never folded into "healthy" and never mistaken for a missing record.
  const record = (name: string, err: unknown): void => {
    if (err instanceof NotCompared) unanswered.push({ who: name, err });
    else errors.push(`${name}: ${err instanceof Error ? err.message : String(err)}`);
  };

  // Every query is in flight at once, so the retry budget is spent once for the run; the answers are read back in order, so the findings print in a stable order.
  const recordName = `${active.id}._domainkey.${domain}`;
  const settle = <T>(pending: Promise<T>) =>
    pending.then(
      (value) => ({ value }),
      (err: unknown) => ({ err })
    );
  const txtAsked = settle(askDns('TXT', recordName, (resolver) => resolver.resolveTxt(recordName)));
  const mxAsked = MAIL_FROM_REGIONS.map((r) => {
    const mxName = `bounce-${r.alias}.${domain}`;
    return settle(askDns('MX', mxName, (resolver) => resolver.resolveMx(mxName)));
  });

  // 1. DKIM TXT record check
  try {
    const txtAnswer = await txtAsked;
    if ('err' in txtAnswer) throw txtAnswer.err;
    const txt = txtAnswer.value;
    // Cloudflare returns multi-string TXTs as nested arrays; concatenate chunks.
    const joined = txt.map((chunks) => chunks.join('')).join('\n');
    if (txt.length === 0) {
      errors.push(`${recordName}: no TXT record (the resolver answered that none exists)`);
    } else if (!/^v=DKIM1\b/.test(joined)) {
      errors.push(
        `${recordName}: TXT does not start with v=DKIM1 (got: ${joined.slice(0, 80)}...)`
      );
    } else {
      const pMatch = /p=([A-Za-z0-9+/]+=*)/.exec(joined);
      if (!pMatch?.[1]) {
        errors.push(`${recordName}: TXT has no non-empty p= (DKIM cannot verify)`);
      } else if (active.name) {
        // Re-hash the public key and compare to the manifest's fingerprint
        const fp = createHash('sha256').update(Buffer.from(pMatch[1], 'base64')).digest('hex');
        if (fp !== active.name) {
          errors.push(
            `${recordName}: public-key fingerprint ${fp} does not match manifest fingerprint ${active.name}`
          );
        }
      }
    }
  } catch (err) {
    record(recordName, err);
  }

  // 2. MAIL FROM MX record check (one per region we declare)
  for (const [index, r] of MAIL_FROM_REGIONS.entries()) {
    const mxName = `bounce-${r.alias}.${domain}`;
    try {
      const mxAnswer = await mxAsked[index];
      if ('err' in mxAnswer) throw mxAnswer.err;
      const mx = mxAnswer.value;
      if (mx.length === 0) {
        errors.push(`${mxName}: no MX records (MAIL FROM misconfigured)`);
        continue;
      }
      const hit = mx.find((m) => m.exchange.replace(/\.$/, '') === r.mxTarget);
      if (!hit) {
        errors.push(
          `${mxName}: MX does not target ${r.mxTarget} (got: ${mx.map((m) => m.exchange).join(',')})`
        );
      }
    } catch (err) {
      record(mxName, err);
    }
  }

  reportUnreachable('DKIM notify DNS record(s)', unanswered, {
    notA: 'a DNS misconfiguration',
    hint: [
      `  (resolvers ${PUBLIC_RESOLVERS.join(', ')}), and re-run the failed job when this is a nightly.`,
    ],
  });
  if (errors.length > 0) {
    process.stderr.write(
      `FAIL: dkim-notify DNS check (${errors.length} issue${errors.length > 1 ? 's' : ''}):\n`
    );
    for (const e of errors) {
      process.stderr.write(`  ${e}\n`);
    }
  }
  if (errors.length > 0 || unanswered.length > 0) return 1;

  process.stdout.write(
    `OK: dkim-notify selector ${active.id} healthy in DNS (${domain}); MAIL FROM MX records aligned for ${MAIL_FROM_REGIONS.map((r) => r.alias).join(', ')}\n`
  );
  return 0;
}

main()
  .then((code) => process.exit(code))
  .catch((err) => {
    process.stderr.write(`FATAL: ${err instanceof Error ? err.stack : String(err)}\n`);
    process.exit(1);
  });
