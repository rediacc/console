/**
 * The CLI policy-record read path (PLAN-rmcp-policy-record.md C1): wire parsing, the rollback guard,
 * the org/team merge and the local-file ceiling.
 */

import {
  encryptPolicyRecord,
  generateCek,
  type PolicyRecord,
  PolicyRecordIntegrityError,
} from '@rediacc/shared/config-crypto';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import type { PolicyDocument } from '@rediacc/shared/policy';
import { describe, expect, it } from 'vitest';
import {
  bindEffectivePolicy,
  boundEffectivePolicy,
  loadEffectivePolicy,
  localPolicyCeiling,
  memoryPolicyHighWater,
  openPolicyRecord,
  type PolicyPointer,
  PolicyRecordInvalidError,
  PolicyRollbackError,
  parsePolicyRecordField,
  policyPointerKey,
} from '../policy-record.js';

const STORE = 'store-1';
const ORG_CONFIG: PolicyPointer = { storeId: STORE, configId: 'cfg-org', teamId: null };
const TEAM_CONFIG: PolicyPointer = { storeId: STORE, configId: 'cfg-team', teamId: 'team-a' };

const ORG_POLICY: PolicyDocument = {
  version: 1,
  defaults: { commands: { allow: ['repo *', 'machine *'] } },
  locked: ['allowGrandRepos'],
};
const TEAM_POLICY: PolicyDocument = {
  version: 1,
  defaults: { commands: { allow: ['repo *'] }, allowGrandRepos: true },
};

function seal(
  document: unknown,
  cek: CryptoKey,
  pointer: PolicyPointer,
  version: number
): Promise<PolicyRecord> {
  return encryptPolicyRecord(document, cek, { ...pointer, version, cekGeneration: 1 });
}

describe('parsePolicyRecordField', () => {
  it('reads null as no record and a well-formed record as itself', () => {
    expect(parsePolicyRecordField(null)).toBeNull();
    expect(parsePolicyRecordField({ version: 2, cekGeneration: 0, blob: 'abc' })).toEqual({
      version: 2,
      cekGeneration: 0,
      blob: 'abc',
    });
  });

  it.each([
    ['an absent field', undefined],
    ['a version of 0', { version: 0, cekGeneration: 1, blob: 'abc' }],
    ['a missing blob', { version: 1, cekGeneration: 1 }],
    ['an empty blob', { version: 1, cekGeneration: 1, blob: '' }],
    ['a string', 'policy'],
  ])('refuses %s instead of reading it as no policy', (_label, raw) => {
    expect(() => parsePolicyRecordField(raw)).toThrow(/malformed policy record/);
  });
});

describe('openPolicyRecord', () => {
  it('opens a record sealed for its pointer and raises the high-water mark', async () => {
    const cek = await generateCek();
    const marks = memoryPolicyHighWater();
    const record = await seal(ORG_POLICY, cek, ORG_CONFIG, 3);
    await expect(openPolicyRecord(record, cek, ORG_CONFIG, marks)).resolves.toEqual(ORG_POLICY);
    expect(marks.get(policyPointerKey(ORG_CONFIG))).toBe(3);
  });

  it('refuses a version below the mark, and accepts the same version again (control)', async () => {
    const cek = await generateCek();
    const marks = memoryPolicyHighWater();
    await openPolicyRecord(await seal(ORG_POLICY, cek, ORG_CONFIG, 5), cek, ORG_CONFIG, marks);

    const replay = await seal(ORG_POLICY, cek, ORG_CONFIG, 4);
    await expect(openPolicyRecord(replay, cek, ORG_CONFIG, marks)).rejects.toBeInstanceOf(
      PolicyRollbackError
    );
    const same = await seal(ORG_POLICY, cek, ORG_CONFIG, 5);
    await expect(openPolicyRecord(same, cek, ORG_CONFIG, marks)).resolves.toEqual(ORG_POLICY);
  });

  it('refuses a record served for another config or team', async () => {
    const cek = await generateCek();
    const teamRecord = await seal(TEAM_POLICY, cek, TEAM_CONFIG, 1);
    await expect(
      openPolicyRecord(teamRecord, cek, ORG_CONFIG, memoryPolicyHighWater())
    ).rejects.toBeInstanceOf(PolicyRecordIntegrityError);
    await expect(
      openPolicyRecord(
        teamRecord,
        cek,
        { ...TEAM_CONFIG, teamId: 'team-b' },
        memoryPolicyHighWater()
      )
    ).rejects.toBeInstanceOf(PolicyRecordIntegrityError);
  });

  it('refuses a record that opens but holds no policy document, and leaves the mark alone', async () => {
    const cek = await generateCek();
    const marks = memoryPolicyHighWater();
    const record = await seal({ version: 2, defaults: {} }, cek, ORG_CONFIG, 1);
    await expect(openPolicyRecord(record, cek, ORG_CONFIG, marks)).rejects.toBeInstanceOf(
      PolicyRecordInvalidError
    );
    expect(marks.get(policyPointerKey(ORG_CONFIG))).toBeUndefined();
  });
});

describe('loadEffectivePolicy', () => {
  it("an org-level config's own record is the org policy", async () => {
    const cek = await generateCek();
    const effective = await loadEffectivePolicy({
      storeId: STORE,
      config: ORG_CONFIG,
      pulled: await seal(ORG_POLICY, cek, ORG_CONFIG, 1),
      orgConfigId: ORG_CONFIG.configId,
      fetchRecord: () => Promise.reject(new Error('no fetch expected')),
      cek,
      highWater: memoryPolicyHighWater(),
    });
    expect(effective.org).toEqual(ORG_POLICY);
    expect(effective.team).toBeUndefined();
  });

  it('a team config merges the fetched org record over its pulled team record', async () => {
    const cek = await generateCek();
    const orgRecord = await seal(ORG_POLICY, cek, ORG_CONFIG, 2);
    const fetched: string[] = [];
    const effective = await loadEffectivePolicy({
      storeId: STORE,
      config: TEAM_CONFIG,
      pulled: await seal(TEAM_POLICY, cek, TEAM_CONFIG, 1),
      orgConfigId: ORG_CONFIG.configId,
      fetchRecord: (configId, teamId) => {
        fetched.push(`${configId}/${teamId ?? ''}`);
        return Promise.resolve(orgRecord);
      },
      cek,
      highWater: memoryPolicyHighWater(),
    });
    expect(fetched).toEqual(['cfg-org/']);
    expect(effective.org).toEqual(ORG_POLICY);
    expect(effective.team).toEqual(TEAM_POLICY);
    expect(effective.ignoredLocked).toEqual(['defaults.allowGrandRepos']);
  });

  it('fetches the own record when the pull did not carry one, and reads no record as none', async () => {
    const cek = await generateCek();
    const fetched: string[] = [];
    const effective = await loadEffectivePolicy({
      storeId: STORE,
      config: TEAM_CONFIG,
      orgConfigId: null,
      fetchRecord: (configId) => {
        fetched.push(configId);
        return Promise.resolve(null);
      },
      cek,
      highWater: memoryPolicyHighWater(),
    });
    expect(fetched).toEqual(['cfg-team']);
    expect(effective).toEqual({ locked: [], ignoredLocked: [] });
  });
});

describe('localPolicyCeiling', () => {
  const local = (extra: Partial<RdcConfig>): RdcConfig =>
    ({ schemaVersion: 3, id: 'local', version: 1, ...extra }) as unknown as RdcConfig;

  it("a local-file config's policy field is its ceiling", () => {
    expect(localPolicyCeiling(local({ policy: ORG_POLICY })).org).toEqual(ORG_POLICY);
    expect(localPolicyCeiling(local({})).org).toBeUndefined();
  });

  it('a remote config is refused, so a forged policy field is never read', () => {
    const forged = local({ policy: ORG_POLICY, remote: {} as RdcConfig['remote'] });
    expect(() => localPolicyCeiling(forged)).toThrow(/policy record/);
  });

  it('an invalid local policy is an error, not an empty ceiling', () => {
    const broken = local({ policy: { version: 9 } as unknown as PolicyDocument });
    expect(() => localPolicyCeiling(broken)).toThrow(/not valid/);
  });
});

describe('bindEffectivePolicy', () => {
  it('binds an effective policy to one config document only', () => {
    const config = { id: 'a' } as unknown as RdcConfig;
    const other = { id: 'a' } as unknown as RdcConfig;
    bindEffectivePolicy(config, { org: ORG_POLICY, locked: [], ignoredLocked: [] });
    expect(boundEffectivePolicy(config)?.org).toEqual(ORG_POLICY);
    expect(boundEffectivePolicy(other)).toBeUndefined();
  });
});
