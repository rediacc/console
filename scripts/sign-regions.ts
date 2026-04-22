/**
 * Sign regions.json for CLI verification.
 *
 * Reads regions.json, extracts the public region info (id, label, domain, default),
 * signs the payload with the Ed25519 private key, and outputs a SignedSubscriptionBlob.
 *
 * Usage:
 *   ED25519_PRIVATE_KEY=... npx tsx scripts/sign-regions.ts > workers/www/dist/regions.json
 *
 * The output is served as /regions.json on the marketing site. The CLI fetches it,
 * verifies the Ed25519 signature with the hardcoded public key, and presents the
 * region list to the user.
 */

import { importPrivateKey, signSubscriptionPayload } from '@rediacc/shared/subscription';
import { CURRENT_SIGNING_KEY } from '@rediacc/shared/subscription';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const privateKeyBase64 = process.env.ED25519_PRIVATE_KEY;
if (!privateKeyBase64) {
  console.error('ED25519_PRIVATE_KEY environment variable is required');
  process.exit(1);
}

const regionsPath = join(import.meta.dirname, '..', 'regions.json');
const regionsData = JSON.parse(readFileSync(regionsPath, 'utf-8'));

const payload = JSON.stringify(
  regionsData.regions.map((r: { id: string; label: string; domain: string; default: boolean }) => ({
    id: r.id,
    label: r.label,
    domain: r.domain,
    default: r.default,
  }))
);

const privateKey = await importPrivateKey(privateKeyBase64);
const signed = await signSubscriptionPayload(payload, privateKey, CURRENT_SIGNING_KEY.keyId);

console.log(JSON.stringify(signed));
