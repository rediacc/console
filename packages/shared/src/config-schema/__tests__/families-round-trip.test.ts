/**
 * Every resource family must survive a push → pull round trip byte-faithfully.
 *
 * This is the test class that was missing when the v3 families shipped:
 * `toFullConfig` projected a hand-listed subset of `resources` into the
 * encrypted blob, so datastores, clusters, backupStrategies, and
 * deletedRepositories silently vanished on every config sync — real data loss,
 * discovered by e2e, invisible to every unit test because none carried a
 * fully-populated `resources`.
 *
 * The same class hit TOP-LEVEL sections: /account/userEmail is a COMMITTED
 * pointer (the CLI pushes its on-disk document with only `state` stripped),
 * but `account` was never projected — so a browser pull + editor re-push
 * committed fewer pointers than the server stored and anti-downgrade rejected
 * it as a spurious conflict. The commitment-set-equality test below is the
 * regression guard for that exact property.
 *
 * Both the family list and the top-level section list are enumerated
 * DYNAMICALLY from RdcConfigSchema, and the fixture is required to populate
 * every key: adding a new family or top-level section fails this test until
 * it is either carried or explicitly classified host-local, so a future
 * addition cannot silently vanish.
 */

import { describe, expect, it } from 'vitest';
import type { z } from 'zod';
import { generateAesKey, generateCek } from '../../config-crypto/index.js';
import { fullConfigToRdcConfig } from '../../config-crypto/rotation.js';
import {
  buildConfigPushPayload,
  decryptConfigPullPayload,
  pathsToCommit,
  type RdcConfig,
  RdcConfigSchema,
} from '../index.js';

/** The authoritative family list, straight from the schema. */
function resourceFamilyKeys(): string[] {
  const resources = RdcConfigSchema.shape.resources as z.ZodOptional<z.ZodObject<z.ZodRawShape>>;
  return Object.keys(resources.unwrap().shape);
}

/**
 * Every top-level RdcConfig section, classified. A section is either part of
 * the plaintext envelope, carried inside the encrypted blob, or host-local by
 * design (never synced, and therefore never committed — see the `remote` and
 * `masterPasswordVerifier` entries in sensitivity.ts for the doctrine).
 * A new top-level section fails the classification test until it is added to
 * exactly one of these lists AND (if carried) to SENSITIVE_FIELDS +
 * toFullConfig + fullConfigToRdcConfig.
 */
const ENVELOPE_SECTIONS = ['schemaVersion', 'id', 'version'] as const;
const CARRIED_SECTIONS = [
  'account',
  'defaults',
  'credentials',
  'resources',
  'infra',
  'policy',
] as const;
const HOST_LOCAL_SECTIONS = ['encryption', 'remote', 'renetPath', 'state'] as const;

/**
 * A config populating EVERY resource family (schema-validated below, so a
 * schema change that invalidates it fails loudly rather than testing garbage).
 */
function allFamiliesConfig(): RdcConfig {
  return {
    schemaVersion: 3,
    id: '7c8d1e9f-2a3b-4c5d-8e6f-1a2b3c4d5e6f',
    version: 3,
    encryption: { mode: 'plaintext' },
    account: { userEmail: 'admin@example.com', accountServer: 'https://eu.rediacc.com' },
    defaults: { language: 'en', universalUser: 'rediacc', datastoreSize: '95%' },
    infra: { certEmail: 'ops@example.com', cfDnsZoneId: 'zone-1234' },
    // Host-local sections, present to PROVE they neither travel nor commit.
    remote: {
      apiUrl: 'https://eu.rediacc.com',
      storeId: '3f2a1b0c-9d8e-4f7a-8b6c-5d4e3f2a1b0c',
      configId: '4a3b2c1d-0e9f-4a8b-9c7d-6e5f4a3b2c1d',
      teamId: '5b4c3d2e-1f0a-4b9c-8d7e-7f6a5b4c3d2e',
      storageKeyId: 'key-1',
    },
    renetPath: '/opt/bin/renet',
    state: { datastores: { ds1: { mounted: true } } },
    policy: { version: 1, defaults: { commands: { allow: ['repo *'] } } },
    credentials: { ssh: { privateKey: 'PRIV' } },
    resources: {
      machines: { m1: { ip: '10.0.0.1', user: 'root' } },
      datastores: {
        ds1: { backend: { kind: 'local', machine: 'm1', path: '/mnt/pool' }, size: '50G' },
        ds2: {
          backend: { kind: 'rbd', pool: 'rbd-pool', image: 'img-1' },
          cluster: 'c1',
          parent: { datastore: 'ds1', snapshot: 'snap-1' },
        },
      },
      storages: { s1: { provider: 's3', vaultContent: { accessKey: 'AKID', secret: 'SEC' } } },
      repositories: {
        shop: {
          grand: 'base',
          placement: { machine: 'm1' },
          tags: {
            base: {
              repositoryGuid: '9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d',
              credential: 'repo-cred',
              sshPrivateKey: 'repo-ssh-priv',
              secrets: {},
            },
          },
        },
      },
      deletedRepositories: [
        {
          name: 'retired',
          tag: 'base',
          deletedAt: '2026-07-01T00:00:00Z',
          repositoryGuid: '1a2b3c4d-5e6f-4a8b-9c0d-e1f2a3b4c5d6',
          credential: 'archived-cred',
          sshPrivateKey: 'archived-ssh-priv',
          sshPublicKey: 'archived-ssh-pub',
          immutable: true,
        },
      ],
      backupStrategies: {
        nightly: {
          destinations: [{ name: 'offsite', storage: 's1', folder: 'backups/shop', enabled: true }],
          schedule: '0 3 * * *',
          mode: 'cold',
          enabled: true,
          bandwidthLimit: '10M',
          include: ['shop'],
          exclude: ['shop:scratch'],
        },
      },
      cloudProviders: { cp1: { apiToken: 'provider-secret', sshUser: 'ubuntu' } },
      clusters: {
        c1: {
          provider: 'kvm',
          network: { primitive: 'vlan', cidr: '10.42.0.0/16', mtu: 1400 },
          pools: [
            {
              name: 'workers',
              role: 'hyperconverged',
              count: 3,
              size: '8G',
              disks: [{ purpose: 'osd', size: '100G', count: 2 }],
              labels: { tier: 'std' },
            },
          ],
          kubernetes: { distro: 'k3s', version: 'v1.30' },
          registry: { enabled: true, upstreams: ['docker.io'] },
          ceph: { pool: 'rbd-pool' },
          controlNode: 'm1',
          kvm: { netName: 'rdnet', netBase: '10.77.0.0', controlId: 1, dockerRegistry: 'reg:5000' },
        },
      },
    },
  };
}

async function pushPullRoundTrip(config: RdcConfig): Promise<RdcConfig> {
  const cek = await generateCek();
  const sdkDerived = await generateAesKey();
  const payload = await buildConfigPushPayload(config, {
    version: config.version + 1,
    sdkEpoch: 42,
    sdkDerived,
    cek,
  });
  // Real crypto both ways — the wire shape is exactly what a pull hands back.
  const decrypted = await decryptConfigPullPayload(payload, { cek, sdkDerived });
  return fullConfigToRdcConfig(decrypted);
}

describe('resource families round trip', () => {
  it('fixture is schema-valid and populates every family and top-level section', () => {
    const config = allFamiliesConfig();
    expect(() => RdcConfigSchema.parse(config)).not.toThrow();

    // If this fails, a NEW family was added to ResourcesSchema: populate it in
    // this fixture AND carry it in toFullConfig / fullConfigToRdcConfig /
    // SENSITIVE_FIELDS, or it will be silently dropped by config sync.
    const missing = resourceFamilyKeys().filter(
      (key) => (config.resources as Record<string, unknown>)[key] === undefined
    );
    expect(
      missing,
      `fixture must populate every schema family; missing: ${missing.join(', ')}`
    ).toEqual([]);

    const missingSections = Object.keys(RdcConfigSchema.shape).filter(
      (key) => (config as Record<string, unknown>)[key] === undefined
    );
    expect(
      missingSections,
      `fixture must populate every top-level section; missing: ${missingSections.join(', ')}`
    ).toEqual([]);
  });

  it('every top-level section is classified envelope, carried, or host-local', () => {
    const classified = [...ENVELOPE_SECTIONS, ...CARRIED_SECTIONS, ...HOST_LOCAL_SECTIONS];
    // If this fails, a NEW top-level section was added to RdcConfigSchema:
    // decide whether it syncs (add to CARRIED_SECTIONS + SENSITIVE_FIELDS +
    // both projections) or stays host-local (add to HOST_LOCAL_SECTIONS and
    // make sure none of its leaves are committed in sensitivity.ts).
    expect([...Object.keys(RdcConfigSchema.shape)].sort()).toEqual([...classified].sort());
  });

  it('every family survives push → pull field-by-field', async () => {
    const original = allFamiliesConfig();
    const rebuilt = await pushPullRoundTrip(original);

    for (const key of resourceFamilyKeys()) {
      expect(
        (rebuilt.resources as Record<string, unknown>)[key],
        `resources.${key} was dropped or mutated by the push/pull round trip`
      ).toEqual((original.resources as Record<string, unknown>)[key]);
    }
  });

  it('carried top-level sections survive; host-local sections stay home', async () => {
    const original = allFamiliesConfig();
    const rebuilt = await pushPullRoundTrip(original);

    expect(rebuilt.account).toEqual(original.account);
    expect(rebuilt.defaults).toEqual(original.defaults);
    expect(rebuilt.infra).toEqual(original.infra);
    expect(rebuilt.policy).toEqual(original.policy);

    // Host-local sections must NOT be resurrected from the blob: a pulled
    // config must never overwrite this host's store pointer, runtime state, or
    // at-rest settings with another host's.
    expect(rebuilt.remote).toBeUndefined();
    expect(rebuilt.state).toBeUndefined();
    expect(rebuilt.renetPath).toBeUndefined();
    expect(rebuilt.encryption).toEqual({ mode: 'plaintext' });
  });

  it('a re-push after pull commits exactly the pointer set the server stored', async () => {
    // THE anti-downgrade property that broke: the editor re-pushes the rebuilt
    // config, so pathsToCommit(rebuilt) is what the next push commits. Any
    // committed-but-not-carried section makes this set smaller than the
    // original's and the server rejects the push as a conflict.
    const original = allFamiliesConfig();
    const before = pathsToCommit(original);
    const after = pathsToCommit(await pushPullRoundTrip(original));
    expect(after).toEqual(before);

    // The addendum case, pinned explicitly.
    expect(before).toContain('/account/userEmail');
    expect(before).toContain('/defaults/universalUser');
    expect(before).toContain('/infra/certEmail');
    // Host-local sections contribute NO committed pointers even when present.
    const hostLocal = before.filter(
      (p) => p.startsWith('/remote/') || p.startsWith('/state/') || p === '/renetPath'
    );
    expect(hostLocal).toEqual([]);
  });
});

describe('datastore fork keys', () => {
  // `datastore fork` records the fork as a FLAT `name:tag` entry with a
  // `parent` backref (mirroring renet's machine-side registry key), so the
  // datastores record key must admit the colon that repository family keys
  // deliberately forbid. Regression: the drill's `drill-ds:remeter` entry
  // made every subsequent config load fail with "Invalid key in record".
  it('accepts a name:tag datastores key in resources and state', () => {
    const config = allFamiliesConfig();
    const resources = config.resources as { datastores: Record<string, unknown> };
    resources.datastores['ds1:exp'] = {
      backend: { kind: 'rbd', pool: 'rbd-pool', image: 'img-1' },
      parent: { datastore: 'ds1', snapshot: 'snap-1' },
    };
    (config.state as { datastores: Record<string, unknown> }).datastores['ds1:exp'] = {
      attachedTo: 'm1',
      writes: 'local',
    };
    expect(() => RdcConfigSchema.parse(config)).not.toThrow();
  });

  it('still rejects malformed datastore keys', () => {
    for (const bad of ['ds1:', ':exp', 'ds1:exp:more', 'Ds1:exp', 'ds1:Exp']) {
      const config = allFamiliesConfig();
      (config.resources as { datastores: Record<string, unknown> }).datastores[bad] = {
        backend: { kind: 'local', machine: 'm1', path: '/mnt/pool' },
      };
      expect(RdcConfigSchema.safeParse(config).success, `key ${JSON.stringify(bad)}`).toBe(false);
    }
  });
});
