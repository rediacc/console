/**
 * Connect helpers for the SFTP client: the IPv6 retry lookup and the host-key mismatch message.
 */

import { lookup } from 'node:dns/promises';
import { fingerprint, keyBlobAlgorithm, parseKnownHosts } from '../../utils/host-keys.js';
import type { Ipv6Resolver } from './types.js';

/** A hostname's IPv6 (AAAA) address, or undefined when it has none. */
export const resolveAaaa: Ipv6Resolver = async (hostname) => {
  try {
    return (await lookup(hostname, { family: 6 })).address;
  } catch {
    return undefined;
  }
};

/** How long the AAAA lookup of the IPv6 retry may take before the original failure surfaces. */
export const AAAA_LOOKUP_TIMEOUT_MS = 5_000;

/** `resolve`, answering undefined once `ms` pass: a hung resolver must not delay the connect failure. */
export function resolveWithin(
  resolve: Ipv6Resolver,
  hostname: string,
  ms: number
): Promise<string | undefined> {
  return new Promise((done) => {
    const timer = setTimeout(() => done(undefined), ms);
    timer.unref?.();
    resolve(hostname).then(
      (address) => {
        clearTimeout(timer);
        done(address);
      },
      () => {
        clearTimeout(timer);
        done(undefined);
      }
    );
  });
}

/**
 * Explain a host-key mismatch in terms the operator can act on.
 *
 * Deliberately not a "tip: run scan-keys" hint. Pinning exists to make exactly
 * this failure loud, and an unconditional remedy trains the reflex of re-pinning
 * on every mismatch, which defeats the point. The remedy is stated
 * conditionally, after the causes and the fingerprints needed to tell them
 * apart.
 *
 * A stale local config is listed as a cause because it is a real and easily
 * missed one: several divergent copies of the config file will present an old
 * pin against an unchanged host, which looks identical to key rotation.
 */
export function buildHostKeyMismatchMessage(params: {
  machineName: string;
  host: string;
  knownHosts: string;
  offeredKey: string;
}): string {
  const { machineName, host, knownHosts, offeredKey } = params;

  const offeredType = keyBlobAlgorithm(offeredKey);
  const pinned = parseKnownHosts(knownHosts);

  // Compare like with like: a host offers one key per algorithm, so the meaningful comparison is against the pin of the same algorithm. Falling back to listing every pin keeps the message useful when the offered blob cannot be decoded.
  const sameAlgorithm = offeredType ? pinned.filter((e) => e.type === offeredType) : [];
  const toShow = sameAlgorithm.length ? sameAlgorithm : pinned;

  const pinnedSummary = toShow.length
    ? toShow.map((e) => `  pinned:   ${e.type} ${fingerprint(e.key)}`).join('\n')
    : '  pinned:   (none recorded)';

  return [
    `Host key mismatch for "${machineName}" (${host})`,
    '',
    pinnedSummary,
    `  offered:  ${offeredType || '(unknown algorithm)'} ${fingerprint(offeredKey)}`,
    '',
    'A rebuilt, reinstalled, or migrated machine will do this. So will a stale',
    'local config, and so will a man-in-the-middle. Confirm the fingerprint out',
    'of band before trusting it.',
    '',
    `If the change is expected: rdc machine scan-keys ${machineName}`,
  ].join('\n');
}
