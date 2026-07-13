/**
 * The commit set and the encrypt set must agree.
 *
 * The server enforces two things the client must keep consistent:
 *   - pathsToCommit(config) — the sensitive pointers whose HMACs go in the
 *     envelope. Anti-downgrade rejects a push that commits FEWER than before.
 *   - SENSITIVE_FIELDS — the top-level sections that actually travel inside the
 *     ciphertext, and so survive a push -> pull round trip.
 *
 * If a pointer is COMMITTED but its data is not CARRIED, a round trip (a CEK
 * rotation, a container config load, or an ordinary `config remote` pull) drops
 * it: the secret is lost, and the re-push commits fewer pointers than the server
 * was told to expect, which bricks config push for the whole org.
 *
 * That exact gap shipped twice — the policy document, then four org secrets
 * (cfDnsApiToken, masterPasswordVerifier, cloudProviders apiToken/sshUser). This
 * test is the invariant that fails HERE the next time a committed field is added
 * without being carried, instead of failing in production on the first rotation.
 */

import { describe, expect, it } from 'vitest';
import { fullConfigToRdcConfig } from '../../config-crypto/rotation.js';
import { toFullConfig } from '../payload.js';
import type { RdcConfig } from '../schemas.js';
import { pathsToCommit } from '../walker.js';

/** A config with every sensitive section populated. */
function fullyPopulated(): RdcConfig {
  return {
    schemaVersion: 3,
    id: '7c8d1e9f-2a3b-4c5d-8e6f-1a2b3c4d5e6f',
    version: 5,
    encryption: { mode: 'plaintext' },
    credentials: {
      ssh: { privateKey: 'PRIV', publicKey: 'PUB', knownHosts: 'kh' },
      cfDnsApiToken: 'cf-secret',
      // Host-local to master-password mode: committed:false, so it must appear in
      // NEITHER the commit set nor the blob. Present here to prove it is dropped.
      masterPasswordVerifier: 'mpv',
    },
    policy: { version: 1, defaults: { commands: { allow: ['repo *'] } } },
    resources: {
      machines: { m1: { ip: '10.0.0.1', user: 'root' } },
      repositories: {},
      storages: {},
      cloudProviders: { cp1: { apiToken: 'provider-secret', sshUser: 'u' } },
      datastores: { ds1: { size: '10G', backend: { kind: 'local', machine: 'm1', path: '/x' } } },
    },
  };
}

/** Project to the encrypted shape and rebuild, exactly as a rotation/pull does. */
function roundTrip(config: RdcConfig): RdcConfig {
  const full = toFullConfig(config, { version: config.version + 1, sdkEpoch: 1 });
  return fullConfigToRdcConfig(full);
}

describe('commit set / encrypt set parity', () => {
  it('drops no committed pointer across a push/pull round trip', () => {
    const original = fullyPopulated();
    const rebuilt = roundTrip(original);

    const before = pathsToCommit(original);
    const after = pathsToCommit(rebuilt);

    const dropped = before.filter((p) => !after.includes(p));
    expect(
      dropped,
      `these committed pointers were lost on round trip: ${dropped.join(', ')}`
    ).toEqual([]);
  });

  it('commits exactly the same pointer set before and after (no drift either way)', () => {
    const original = fullyPopulated();
    expect(pathsToCommit(roundTrip(original))).toEqual(pathsToCommit(original));
  });

  it('carries the org secrets back out intact', () => {
    const rebuilt = roundTrip(fullyPopulated());
    expect(rebuilt.credentials?.cfDnsApiToken).toBe('cf-secret');
    expect(
      (rebuilt.resources?.cloudProviders as Record<string, { apiToken: string; sshUser: string }>)
        .cp1
    ).toEqual({ apiToken: 'provider-secret', sshUser: 'u' });
  });

  it('does NOT commit the host-local master-password verifier', () => {
    // commit:false, so it is out of the commit set entirely; there is therefore
    // nothing for the round trip to drop, and it never enters the remote envelope.
    expect(pathsToCommit(fullyPopulated())).not.toContain('/credentials/masterPasswordVerifier');
  });

  it('does not resurrect the verifier through the round trip', () => {
    // It is not carried in the blob, so the rebuilt config simply lacks it.
    const rebuilt = roundTrip(fullyPopulated());
    expect(rebuilt.credentials?.masterPasswordVerifier).toBeUndefined();
  });
});
