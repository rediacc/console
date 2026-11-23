/**
 * The explicit-undefined trap.
 *
 * The sensitivity walker keys off property EXISTENCE, because Object.entries()
 * yields a key whose value is undefined exactly like any other key. So this:
 *
 *     ssh: { privateKey: 'k', knownHosts: undefined }
 *
 * is NOT the same document as this:
 *
 *     ssh: { privateKey: 'k' }
 *
 * The first commits a pointer for /credentials/ssh/knownHosts; the second does
 * not. That difference is invisible when you read the code and fatal when you
 * run it: a config rebuilt the first way (a remote pull, a CEK rotation) commits
 * a pointer that an ordinary local config does not have, so the very next push
 * looks like it DROPPED a sensitive path and the server's anti-downgrade check
 * rejects it. One such round trip can brick config push for an entire org.
 *
 * Two real bugs of exactly this shape were caught in review, one in the CEK
 * rotation and one in the CLI's remote pull. These tests exist so a third one
 * fails here instead of in production.
 */

import { describe, expect, it } from 'vitest';
import { buildCommitEntries } from '../payload.js';
import type { RdcConfig } from '../schemas.js';
import { pathsToCommit } from '../walker.js';

function configWithSsh(ssh: Record<string, unknown>): RdcConfig {
  const config = {
    schemaVersion: 3,
    id: '7c8d1e9f-2a3b-4c5d-8e6f-1a2b3c4d5e6f',
    version: 1,
    defaults: { language: 'en', datastoreSize: '95%' },
    credentials: { ssh },
    encryption: { mode: 'plaintext' },
  };
  return config as RdcConfig;
}

describe('explicit undefined keys', () => {
  it('an undefined-valued key IS a committed pointer, an absent key is not', () => {
    const explicit = pathsToCommit(configWithSsh({ privateKey: 'k', knownHosts: undefined }));
    const absent = pathsToCommit(configWithSsh({ privateKey: 'k' }));

    expect(explicit).toContain('/credentials/ssh/knownHosts');
    expect(absent).not.toContain('/credentials/ssh/knownHosts');

    // This inequality is the whole bug: two configs that look identical to a reader commit different pointer sets.
    expect(explicit).not.toEqual(absent);
  });

  it('the asymmetry is what makes the next push look like a downgrade', () => {
    // A config rebuilt from a remote pull, written the careless way.
    const pulled = buildCommitEntries(configWithSsh({ privateKey: 'k', knownHosts: undefined }));
    // The same org's ordinary local config, which simply has no knownHosts.
    const local = buildCommitEntries(configWithSsh({ privateKey: 'k' }));

    const pulledPointers = new Set(pulled.map((e) => e.pointer));
    const localPointers = new Set(local.map((e) => e.pointer));

    // The local config is missing a pointer the server was told to expect, which is precisely what the anti-downgrade check rejects.
    const dropped = [...pulledPointers].filter((p) => !localPointers.has(p));
    expect(dropped).toEqual(['/credentials/ssh/knownHosts']);
  });

  it('spread-if-present rebuilds a config that stays pushable', () => {
    // The correct reconstruction: omit the key entirely when the source lacks it.
    const source: { privateKey: string; publicKey?: string; knownHosts?: string } = {
      privateKey: 'k',
    };
    const rebuilt = configWithSsh({
      privateKey: source.privateKey,
      ...(source.publicKey === undefined ? {} : { publicKey: source.publicKey }),
      ...(source.knownHosts === undefined ? {} : { knownHosts: source.knownHosts }),
    });

    expect(pathsToCommit(rebuilt)).toEqual(pathsToCommit(configWithSsh({ privateKey: 'k' })));
  });
});
