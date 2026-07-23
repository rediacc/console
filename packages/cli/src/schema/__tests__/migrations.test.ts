import {
  CURRENT_SCHEMA_VERSION,
  type MigrationContext,
  migrateV1ToV2,
  migrateV2ToV3,
  RdcConfigSchema,
  runMigrations,
} from '@rediacc/shared/config-schema';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { nodeCryptoProvider } from '../../adapters/crypto.js';

/**
 * These tests probe dynamic and removed fields on migrated documents, so they
 * walk the result structurally rather than through the schema types. A migrated
 * doc is modeled as a recursive index type: every access yields another node.
 */
type MigratedDoc = { readonly [key: string]: MigratedDoc };

/** The v2 input shape these tests mutate before feeding the migration. */
type V2Input = Record<string, unknown> & {
  resources: { repositories: Record<string, unknown> };
};

/**
 * The schema package is runtime-portable and holds no crypto provider, so the
 * host injects one (see ConfigFileStorage.migrationContext). These tests inject
 * the same Node provider the CLI uses in production.
 */
const decryptLegacyBlob = (data: string, password: string): Promise<string> =>
  nodeCryptoProvider.decrypt(data, password);

const throwingCtx: MigrationContext = {
  getMasterPassword: () => Promise.reject(new Error('no password')),
  decryptLegacyBlob,
};

function makeV1Sample(): Record<string, unknown> {
  return {
    id: '7c8d1e9f-2a3b-4c5d-8e6f-1a2b3c4d5e6f',
    version: 1,
    defaults: { language: 'en', datastoreSize: '95%' },
    encryption: { mode: 'plaintext' },
  };
}

function makeV2Sample(): Record<string, unknown> {
  return {
    schemaVersion: 2,
    id: '7c8d1e9f-2a3b-4c5d-8e6f-1a2b3c4d5e6f',
    version: 5,
    account: { userEmail: 'op@example.com', team: 'acme', region: 'eu' },
    defaults: { language: 'en', machine: 'web-1', nextNetworkId: 3008 },
    resources: {
      machines: {
        'web-1': { ip: '10.0.0.1', user: 'deploy', ceph: { pool: 'rbd', image: 'img' } },
      },
      repositories: {
        erpnext: { repositoryGuid: '11111111-1111-4111-8111-111111111111', networkId: 2816 },
        'shop:latest': {
          repositoryGuid: '22222222-2222-4222-8222-222222222222',
          tag: 'latest',
          networkId: 2880,
          headCommit: 'c0ffee',
        },
        'shop:test': {
          repositoryGuid: '33333333-3333-4333-8333-333333333333',
          tag: 'test',
          grandGuid: '22222222-2222-4222-8222-222222222222',
          networkId: 2944,
        },
      },
      clusters: {
        c1: {
          provider: 'kvm',
          pools: [{ name: 'server', role: 'k8s-server', count: 1 }],
          kvm: { netName: 'n', netBase: '192.168.90', controlId: 1, memberIds: { server: [11] } },
        },
      },
      deletedRepositories: [
        { repositoryGuid: '55555555-5555-4555-8555-555555555555', name: 'old:v1', deletedAt: 'x' },
      ],
    },
    infra: {
      acmeCertCache: {
        'example.com': {
          baseDomain: 'example.com',
          updatedAt: 'x',
          sourceMachine: 'web-1',
          certCount: 0,
          certs: {},
          data: 'AAAA',
          rawSize: 1,
        },
      },
    },
    encryption: { mode: 'plaintext' },
    unknownFutureKey: { kept: true },
  };
}

describe('runMigrations', () => {
  it('treats missing schemaVersion as version 1 and upgrades to current', async () => {
    const result = await runMigrations(makeV1Sample(), throwingCtx);
    expect(result.migrated).toBe(true);
    expect(result.fromVersion).toBe(1);
    expect(result.toVersion).toBe(CURRENT_SCHEMA_VERSION);
    expect(result.config.schemaVersion).toBe(3);
  });

  it('is a no-op when input is already at current version', async () => {
    const v3 = { ...makeV1Sample(), schemaVersion: 3 };
    const result = await runMigrations(v3, throwingCtx);
    expect(result.migrated).toBe(false);
    expect(result.fromVersion).toBe(CURRENT_SCHEMA_VERSION);
    expect(result.config).toBe(v3);
  });

  it('refuses to downgrade configs from a newer CLI', async () => {
    const future = { ...makeV1Sample(), schemaVersion: 99 };
    await expect(runMigrations(future, throwingCtx)).rejects.toThrow(
      /newer than this CLI supports/
    );
  });

  it('rejects non-object roots', async () => {
    await expect(runMigrations(null, throwingCtx)).rejects.toThrow(/must be an object/);
    await expect(runMigrations([], throwingCtx)).rejects.toThrow(/must be an object/);
  });

  it('rejects invalid schemaVersion values', async () => {
    await expect(runMigrations({ schemaVersion: -1 }, throwingCtx)).rejects.toThrow(
      /Invalid schemaVersion/
    );
    await expect(runMigrations({ schemaVersion: 1.5 }, throwingCtx)).rejects.toThrow(
      /Invalid schemaVersion/
    );
  });

  it('produces v3 output that passes RdcConfigSchema', async () => {
    const result = await runMigrations(makeV2Sample(), throwingCtx);
    expect(RdcConfigSchema.safeParse(result.config).success).toBe(true);
  });

  it('preserves the full account universe (server/e2e/channel/releases) round-tripping a v3 fixture', async () => {
    const raw = JSON.parse(
      readFileSync(
        join(
          fileURLToPath(new URL('.', import.meta.url)),
          '..',
          '..',
          '__tests__',
          'fixtures',
          'config',
          'v3-account-universe.json'
        ),
        'utf-8'
      )
    );

    // v3 in, v3 out — a no-op migration that must not touch the account fields.
    const result = await runMigrations(raw, throwingCtx);
    expect(result.migrated).toBe(false);

    const parsed = RdcConfigSchema.safeParse(result.config);
    expect(parsed.success).toBe(true);

    const account = (parsed.success ? parsed.data : {}).account;
    expect(account).toEqual({
      userEmail: 'op@example.com',
      accountServer: 'https://on-prem.example.com',
      e2ePublicKey: 'MCowBQYDK2VuAyEALY64atDar/bIwKoYEJPoYphKKZ6KUIkPzIHdfH6nKg8=',
      updateChannel: 'edge',
      releasesUrl: 'https://releases.on-prem.example.com',
    });
  });
});

describe('migrateV2ToV3 transforms', () => {
  it('T1 stamps schemaVersion 3', async () => {
    const out = await migrateV2ToV3(makeV2Sample(), throwingCtx);
    expect(out.schemaVersion).toBe(3);
  });

  it('T2 keys repositories by name into families of structural tags', async () => {
    const out = (await migrateV2ToV3(makeV2Sample(), throwingCtx)) as MigratedDoc;
    const repos = out.resources.repositories;
    expect(repos.erpnext.grand).toBe('latest');
    expect(repos.erpnext.tags.latest.repositoryGuid).toBe('11111111-1111-4111-8111-111111111111');
    expect(repos.shop.grand).toBe('latest');
    expect(Object.keys(repos.shop.tags).sort()).toEqual(['latest', 'test']);
    expect(repos.shop.tags.latest.tag).toBeUndefined();
    expect(repos.shop.tags.latest.networkId).toBeUndefined();
    expect(repos.shop.tags.latest.headCommit).toBeUndefined();
  });

  it('T4 extracts status into the state bucket', async () => {
    const out = (await migrateV2ToV3(makeV2Sample(), throwingCtx)) as MigratedDoc;
    expect(out.state.repos.shop.latest.networkId).toBe(2880);
    expect(out.state.repos.shop.latest.headCommit).toBe('c0ffee');
    expect(out.state.repos.shop.test.networkId).toBe(2944);
    expect(out.state.networkIds.next).toBe(3008);
    expect(out.state.certCache['example.com'].baseDomain).toBe('example.com');
    expect(out.state.clusters.c1.memberIds.server).toEqual([11]);
    expect(out.resources.clusters.c1.kvm.memberIds).toBeUndefined();
    expect(out.infra.acmeCertCache).toBeUndefined();
  });

  it('T6 residue-sweeps team/region/defaults.machine/nextNetworkId', async () => {
    const out = (await migrateV2ToV3(makeV2Sample(), throwingCtx)) as MigratedDoc;
    expect(out.account.team).toBeUndefined();
    expect(out.account.region).toBeUndefined();
    expect(out.defaults.machine).toBeUndefined();
    expect(out.defaults.nextNetworkId).toBeUndefined();
  });

  it('T7 drops machines[*].ceph', async () => {
    const out = (await migrateV2ToV3(makeV2Sample(), throwingCtx)) as MigratedDoc;
    expect(out.resources.machines['web-1'].ceph).toBeUndefined();
    expect(out.resources.machines['web-1'].ip).toBe('10.0.0.1');
  });

  it('T9 splits archived-repo composite name into {name, tag}', async () => {
    const out = (await migrateV2ToV3(makeV2Sample(), throwingCtx)) as MigratedDoc;
    const archived = out.resources.deletedRepositories[0];
    expect(archived.name).toBe('old');
    expect(archived.tag).toBe('v1');
  });

  it('T10 preserves unknown top-level keys', async () => {
    const out = (await migrateV2ToV3(makeV2Sample(), throwingCtx)) as MigratedDoc;
    expect(out.unknownFutureKey).toEqual({ kept: true });
  });

  it('refuses a shop + shop:latest ambiguity, naming both keys', async () => {
    const v2 = makeV2Sample() as V2Input;
    v2.resources.repositories = {
      shop: { repositoryGuid: '66666666-6666-4666-8666-666666666666' },
      'shop:latest': { repositoryGuid: '77777777-7777-4777-8777-777777777777' },
    };
    await expect(migrateV2ToV3(v2, throwingCtx)).rejects.toThrow(/shop/);
  });

  it('fails when a secret exceeds its mode cap, naming the key', async () => {
    const v2 = makeV2Sample() as V2Input;
    v2.resources.repositories = {
      shop: {
        repositoryGuid: '66666666-6666-4666-8666-666666666666',
        secrets: { BIG: { mode: 'env', value: 'x'.repeat(40 * 1024) } },
      },
    };
    await expect(migrateV2ToV3(v2, throwingCtx)).rejects.toThrow(/BIG/);
  });

  it('is idempotent: migrating a v3 doc through runMigrations is a no-op', async () => {
    const v3 = await runMigrations(makeV2Sample(), throwingCtx);
    const again = await runMigrations(v3.config, throwingCtx);
    expect(again.migrated).toBe(false);
  });

  it('unpacks a v2 master-password /resources blob into per-field plaintext', async () => {
    const password = 'test-pw';
    const inner = {
      machines: { 'web-1': { ip: '10.0.0.9', user: 'deploy' } },
      repositories: {
        secret: {
          repositoryGuid: '88888888-8888-4888-8888-888888888888',
          credential: 'luks-secret',
          networkId: 4032,
        },
      },
    };
    const combined = await nodeCryptoProvider.encrypt(JSON.stringify(inner), password);
    const v2: Record<string, unknown> = {
      schemaVersion: 2,
      id: '7c8d1e9f-2a3b-4c5d-8e6f-1a2b3c4d5e6f',
      version: 2,
      encryption: {
        mode: 'master-password',
        encryptedFields: { '/resources': { data: combined } },
      },
    };

    const ctx: MigrationContext = {
      getMasterPassword: () => Promise.resolve(password),
      decryptLegacyBlob,
    };
    const out = (await migrateV2ToV3(v2, ctx)) as MigratedDoc;
    expect(out.resources.repositories.secret.grand).toBe('latest');
    expect(out.resources.repositories.secret.tags.latest.credential).toBe('luks-secret');
    expect(out.state.repos.secret.latest.networkId).toBe(4032);
    expect(out.encryption.encryptedFields['/resources']).toBeUndefined();
  });

  it('aborts (rejects) when the master password is wrong', async () => {
    const combined = await nodeCryptoProvider.encrypt('{"machines":{}}', 'right-pw');
    const v2: Record<string, unknown> = {
      schemaVersion: 2,
      id: '7c8d1e9f-2a3b-4c5d-8e6f-1a2b3c4d5e6f',
      version: 2,
      encryption: {
        mode: 'master-password',
        encryptedFields: { '/resources': { data: combined } },
      },
    };
    const ctx: MigrationContext = {
      getMasterPassword: () => Promise.resolve('wrong-pw'),
      decryptLegacyBlob,
    };
    await expect(migrateV2ToV3(v2, ctx)).rejects.toThrow();
  });
});

describe('migrateV1ToV2', () => {
  it('stamps schemaVersion: 2', () => {
    const out = migrateV1ToV2({ id: 'x', version: 1 });
    expect(out.schemaVersion).toBe(2);
    expect(out.id).toBe('x');
  });
});
