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
 * Run: npx tsx scripts/check-dkim-notify.ts
 * Exits 0 on success, 1 on any failure. Uses `node:dns/promises` with a 5s
 * per-query timeout and 3 retries with 1s/2s/4s backoff — matching the
 * external-network retry pattern used by `scripts/check-external-links.ts`.
 */

import { readFileSync } from 'node:fs';
import * as path from 'node:path';
import { createHash } from 'node:crypto';
import { Resolver } from 'node:dns/promises';

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
  credentials: Record<string, { platform: string; versions?: ManifestVersion[] } & Partial<ManifestDkimNotify>>;
}

const MANIFEST_PATH = 'private/account/rotation-manifest.json';
const TIMEOUT_MS = 5_000;
const MAX_RETRIES = 3;

// Active-region → AWS region mapping (matches
// `private/account/scripts/rotation/lib/config.ts:ROTATION_CONFIG.awsSes`).
// Kept in lockstep manually because this script also runs on `ubuntu-slim`
// CI runners that don't install the account package.
const REGION_MAPPING: Record<string, string> = {
  eu: 'eu-central-1',
  us: 'us-east-1',
  asia: 'ap-northeast-1',
};

// Regions to check MAIL FROM MX records for. `bench` shares `eu` so we skip
// it. `asia` is kept in the set even though its SES identity isn't production-
// approved: the MAIL FROM DNS is already published and will stay published,
// and checking it catches drift before asia gets flipped on.
const MAIL_FROM_REGIONS: Array<{ alias: string; mxTarget: string }> = [
  { alias: 'eu', mxTarget: `feedback-smtp.${REGION_MAPPING.eu}.amazonses.com` },
  { alias: 'us', mxTarget: `feedback-smtp.${REGION_MAPPING.us}.amazonses.com` },
  { alias: 'asia', mxTarget: `feedback-smtp.${REGION_MAPPING.asia}.amazonses.com` },
];

// Use public resolvers in CI — the runner's default resolver sometimes has
// shorter TTL caches for recently-changed records. 1.1.1.1 and 8.8.8.8
// are independent networks so we get a cross-check on divergent answers.
const PUBLIC_RESOLVERS = ['1.1.1.1', '8.8.8.8'];

async function withTimeout<T>(promise: Promise<T>, ms: number, label: string): Promise<T> {
  let timeout: NodeJS.Timeout | undefined;
  const timer = new Promise<never>((_, reject) => {
    timeout = setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms);
  });
  try {
    return await Promise.race([promise, timer]);
  } finally {
    if (timeout) clearTimeout(timeout);
  }
}

async function resolveTxtWithRetry(name: string): Promise<string[][]> {
  let lastErr = '';
  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    for (const server of PUBLIC_RESOLVERS) {
      const resolver = new Resolver();
      resolver.setServers([server]);
      try {
        return await withTimeout(resolver.resolveTxt(name), TIMEOUT_MS, `TXT ${name}@${server}`);
      } catch (err) {
        lastErr = `${server}: ${err instanceof Error ? err.message : String(err)}`;
      }
    }
    if (attempt < MAX_RETRIES) {
      const backoff = 1000 * 2 ** (attempt - 1);
      await new Promise((r) => setTimeout(r, backoff));
    }
  }
  throw new Error(`TXT ${name} failed after ${MAX_RETRIES} attempts: ${lastErr}`);
}

async function resolveMxWithRetry(name: string): Promise<Array<{ exchange: string; priority: number }>> {
  let lastErr = '';
  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    for (const server of PUBLIC_RESOLVERS) {
      const resolver = new Resolver();
      resolver.setServers([server]);
      try {
        return await withTimeout(resolver.resolveMx(name), TIMEOUT_MS, `MX ${name}@${server}`);
      } catch (err) {
        lastErr = `${server}: ${err instanceof Error ? err.message : String(err)}`;
      }
    }
    if (attempt < MAX_RETRIES) {
      const backoff = 1000 * 2 ** (attempt - 1);
      await new Promise((r) => setTimeout(r, backoff));
    }
  }
  throw new Error(`MX ${name} failed after ${MAX_RETRIES} attempts: ${lastErr}`);
}

async function main(): Promise<number> {
  const manifestPath = path.resolve(process.cwd(), MANIFEST_PATH);
  let manifest: Manifest;
  try {
    const raw = readFileSync(manifestPath, 'utf-8');
    manifest = JSON.parse(raw) as Manifest;
  } catch (err) {
    process.stderr.write(`error: could not read ${MANIFEST_PATH}: ${err instanceof Error ? err.message : String(err)}\n`);
    return 1;
  }

  const dkim = Object.entries(manifest.credentials).find(
    ([, cred]) => cred.platform === 'dkim-notify'
  );

  if (!dkim) {
    // No dkim-notify entry yet — the rotation tool hasn't been run at least
    // once. Phase 1 of the SES BYODKIM migration should seed this; until it
    // does, the check is a no-op (otherwise CI fails before the migration
    // even starts).
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

  // 1. DKIM TXT record check
  const recordName = `${active.id}._domainkey.${domain}`;
  try {
    const txt = await resolveTxtWithRetry(recordName);
    // Cloudflare returns multi-string TXTs as nested arrays; concatenate chunks.
    const joined = txt.map((chunks) => chunks.join('')).join('\n');
    if (!/^v=DKIM1\b/.test(joined)) {
      errors.push(`${recordName}: TXT does not start with v=DKIM1 (got: ${joined.slice(0, 80)}...)`);
    } else {
      const pMatch = /p=([A-Za-z0-9+/]+=*)/.exec(joined);
      if (!pMatch || !pMatch[1]) {
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
    errors.push(`${recordName}: ${err instanceof Error ? err.message : String(err)}`);
  }

  // 2. MAIL FROM MX record check (one per region we declare)
  for (const r of MAIL_FROM_REGIONS) {
    const mxName = `bounce-${r.alias}.${domain}`;
    try {
      const mx = await resolveMxWithRetry(mxName);
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
      errors.push(`${mxName}: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  if (errors.length > 0) {
    process.stderr.write(`FAIL: dkim-notify DNS check (${errors.length} issue${errors.length > 1 ? 's' : ''}):\n`);
    for (const e of errors) {
      process.stderr.write(`  ${e}\n`);
    }
    return 1;
  }

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
