/**
 * Agent grants (PLAN-rmcp-agent-grants.md Design 1): known answers from fixed inputs (computed with an
 * independent RFC 5869 / RFC 2104 implementation), RFC 5869 test case 1 as the control that the HKDF helper
 * is the standard one, a round trip, and the refusals. Every refusal sits beside a control that opens with
 * the same fixture, so a refusal cannot pass because nothing opens at all.
 */

import { beforeAll, describe, expect, it } from 'vitest';
import {
  AGENT_BEARER_PREFIX,
  type AgentGrantBinding,
  type AgentGrantPolicyKeyBinding,
  aesDecryptFromString,
  aesEncryptToString,
  agentGrantHkdf,
  ConfigIntegrityError,
  decryptPolicyRecord,
  deriveAgentGrantKey,
  deriveAgentGrantSlotKeyRaw,
  deriveAuthTag,
  derivePolicyKey,
  encryptPolicyRecord,
  formatAgentBearer,
  fromBase64,
  generateCek,
  generateConfigKey,
  hashAuthTag,
  newAgentGrantSecret,
  parseAgentBearer,
  toBase64,
  unwrapConfigKeyForAgentGrant,
  unwrapPolicyKeyForAgentGrant,
  wrapConfigKeyForAgentGrant,
  wrapPolicyKeyForAgentGrant,
} from '../index.js';

const hex = (data: Uint8Array): string =>
  Array.from(data, (b) => b.toString(16).padStart(2, '0')).join('');
const seq = (start: number, length: number): Uint8Array =>
  new Uint8Array(Array.from({ length }, (_, i) => (start + i) & 0xff));

// Fixed inputs of the known-answer vectors.
const S = seq(0x00, 32);
const SERVER_SECRET = seq(0x80, 32);
const BINDING: AgentGrantBinding = {
  grantId: 'eu_grant-0001',
  storeId: 'store-1',
  configId: 'cfg-a',
  teamId: 'team-1',
  configKeyVersion: 1,
  cekGeneration: 3,
};

describe('agentGrantHkdf', () => {
  it('is RFC 5869 HKDF-SHA256 (test case 1)', async () => {
    const okm = await agentGrantHkdf(
      new Uint8Array(22).fill(0x0b),
      seq(0x00, 13),
      seq(0xf0, 10),
      42
    );
    expect(hex(okm)).toBe(
      '3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865'
    );
  });
});

describe('known answers', () => {
  it('authTag and its stored hash', async () => {
    const tag = await deriveAuthTag(S);
    expect(tag).toBe('B6OKnPsmoR5YVlTc2F8EU2EieCqUq9TDiKR9vtjqHKc');
    expect(await hashAuthTag(tag)).toBe('VWS78iov0uaMni_ch8DT04AOnaFSeiXodRy_hlN66J0');
  });

  it('K', async () => {
    expect(hex(await deriveAgentGrantKey(S, BINDING.grantId))).toBe(
      '209b97f6884068cfb681b67c82054f6e27c50108c8f39db3c46a3108b0feb648'
    );
  });

  it('the slot key', async () => {
    const k = await deriveAgentGrantKey(S, BINDING.grantId);
    expect(hex(await deriveAgentGrantSlotKeyRaw(k, SERVER_SECRET, BINDING))).toBe(
      '02c35b581d2e94cdcdd4905f632098996341ccabd78022ee0f64b6f6cf65f5d1'
    );
  });

  it('the bearer form', () => {
    expect(formatAgentBearer(BINDING.grantId, S)).toBe(
      'rmcp_eu_grant-0001.AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8'
    );
  });
});

describe('wrap and unwrap', () => {
  let configKey: CryptoKey;
  let wrapped: string;
  let sealed: string;
  const plaintext = new TextEncoder().encode('config body');

  /** True when `candidate` opens under (secret, serverSecret, binding) and decrypts the sealed sample. */
  async function opens(
    candidate: string,
    secret: Uint8Array,
    serverSecret: Uint8Array,
    binding: AgentGrantBinding
  ): Promise<boolean> {
    try {
      const key = await unwrapConfigKeyForAgentGrant(candidate, secret, serverSecret, binding);
      const out = await aesDecryptFromString(key, sealed);
      return new TextDecoder().decode(out) === 'config body';
    } catch {
      return false;
    }
  }

  beforeAll(async () => {
    configKey = await generateConfigKey();
    wrapped = await wrapConfigKeyForAgentGrant(configKey, S, SERVER_SECRET, BINDING);
    sealed = await aesEncryptToString(configKey, plaintext);
  });

  it('round trips into a non-extractable key that opens the config', async () => {
    const key = await unwrapConfigKeyForAgentGrant(wrapped, S, SERVER_SECRET, BINDING);
    expect(key.extractable).toBe(false);
    expect(new TextDecoder().decode(await aesDecryptFromString(key, sealed))).toBe('config body');
    expect(await opens(wrapped, S, SERVER_SECRET, BINDING)).toBe(true);
  });

  it('refuses a tampered wrap (control: the untouched wrap opens)', async () => {
    expect(await opens(wrapped, S, SERVER_SECRET, BINDING)).toBe(true);
    const bytes = fromBase64(wrapped);
    bytes[bytes.length - 1] ^= 0x01;
    const tampered = toBase64(bytes);
    await expect(
      unwrapConfigKeyForAgentGrant(tampered, S, SERVER_SECRET, BINDING)
    ).rejects.toBeInstanceOf(ConfigIntegrityError);
  });

  it('refuses a wrong key: another S, another serverSecret (control: the right pair opens)', async () => {
    expect(await opens(wrapped, S, SERVER_SECRET, BINDING)).toBe(true);
    await expect(
      unwrapConfigKeyForAgentGrant(wrapped, newAgentGrantSecret(), SERVER_SECRET, BINDING)
    ).rejects.toBeInstanceOf(ConfigIntegrityError);
    await expect(
      unwrapConfigKeyForAgentGrant(wrapped, S, newAgentGrantSecret(), BINDING)
    ).rejects.toBeInstanceOf(ConfigIntegrityError);
  });

  it('refuses a wrapped_config_key from another grant (control: that grant opens its own)', async () => {
    const otherS = newAgentGrantSecret();
    const other = { ...BINDING, grantId: 'eu_grant-0002' };
    const otherWrap = await wrapConfigKeyForAgentGrant(configKey, otherS, SERVER_SECRET, other);
    expect(await opens(otherWrap, otherS, SERVER_SECRET, other)).toBe(true);
    expect(await opens(otherWrap, S, SERVER_SECRET, BINDING)).toBe(false);
  });

  it('refuses a wrong grantId (control: the right one opens)', async () => {
    expect(await opens(wrapped, S, SERVER_SECRET, BINDING)).toBe(true);
    expect(await opens(wrapped, S, SERVER_SECRET, { ...BINDING, grantId: 'eu_grant-0009' })).toBe(
      false
    );
  });

  describe('scope mismatch', () => {
    it('refuses a wrap moved to another configId (control: its own config opens)', async () => {
      expect(await opens(wrapped, S, SERVER_SECRET, BINDING)).toBe(true);
      expect(await opens(wrapped, S, SERVER_SECRET, { ...BINDING, configId: 'cfg-b' })).toBe(false);
    });

    it('refuses another store, team or content-key version (control: the bound ones open)', async () => {
      expect(await opens(wrapped, S, SERVER_SECRET, BINDING)).toBe(true);
      expect(await opens(wrapped, S, SERVER_SECRET, { ...BINDING, storeId: 'store-2' })).toBe(
        false
      );
      expect(await opens(wrapped, S, SERVER_SECRET, { ...BINDING, teamId: 'team-2' })).toBe(false);
      expect(await opens(wrapped, S, SERVER_SECRET, { ...BINDING, teamId: null })).toBe(false);
      expect(await opens(wrapped, S, SERVER_SECRET, { ...BINDING, configKeyVersion: 2 })).toBe(
        false
      );
    });
  });

  it('expiry by CEK rotation: refuses an older or newer cekGeneration (control: the bound one opens)', async () => {
    expect(await opens(wrapped, S, SERVER_SECRET, BINDING)).toBe(true);
    expect(await opens(wrapped, S, SERVER_SECRET, { ...BINDING, cekGeneration: 2 })).toBe(false);
    expect(await opens(wrapped, S, SERVER_SECRET, { ...BINDING, cekGeneration: 4 })).toBe(false);
  });

  it('refuses serverSecret without S, and S without serverSecret (control: both open)', async () => {
    expect(await opens(wrapped, S, SERVER_SECRET, BINDING)).toBe(true);
    const none = new Uint8Array(0);
    await expect(
      unwrapConfigKeyForAgentGrant(wrapped, none, SERVER_SECRET, BINDING)
    ).rejects.toThrow(/secret must be 32 bytes/);
    await expect(unwrapConfigKeyForAgentGrant(wrapped, S, none, BINDING)).rejects.toThrow(
      /serverSecret must be 32 bytes/
    );
    // Either half standing in for the missing one does not open either.
    expect(await opens(wrapped, SERVER_SECRET, SERVER_SECRET, BINDING)).toBe(false);
    expect(await opens(wrapped, S, S, BINDING)).toBe(false);
  });
});

describe('policy-key wrap and unwrap (AG-P1)', () => {
  const policy = { version: 1, defaults: { commands: { allow: ['repo *'] } } };
  const teamPointer = { storeId: 'store-1', configId: 'cfg-a', teamId: 'team-1' };
  const orgPointer = { storeId: 'store-1', configId: 'cfg-org', teamId: null };
  const TEAM: AgentGrantPolicyKeyBinding = {
    grantId: BINDING.grantId,
    storeId: 'store-1',
    configId: 'cfg-a',
    cekGeneration: 3,
    policyConfigId: 'cfg-a',
    policyTeamId: 'team-1',
  };
  const ORG: AgentGrantPolicyKeyBinding = {
    ...TEAM,
    policyConfigId: 'cfg-org',
    policyTeamId: null,
  };
  let teamRecord: Awaited<ReturnType<typeof encryptPolicyRecord>>;
  let orgRecord: Awaited<ReturnType<typeof encryptPolicyRecord>>;
  let teamWrap: string;
  let orgWrap: string;
  let configWrap: string;
  let configKey: CryptoKey;

  /** True when `candidate` unwraps as a policy key under `binding` and opens `record` at `pointer`. */
  async function opensPolicy(
    candidate: string,
    binding: AgentGrantPolicyKeyBinding,
    record: typeof teamRecord,
    pointer: typeof teamPointer | typeof orgPointer
  ): Promise<boolean> {
    try {
      const key = await unwrapPolicyKeyForAgentGrant(candidate, S, SERVER_SECRET, binding);
      return (
        JSON.stringify(await decryptPolicyRecord(record, key, pointer)) === JSON.stringify(policy)
      );
    } catch {
      return false;
    }
  }

  beforeAll(async () => {
    const cek = await generateCek();
    teamRecord = await encryptPolicyRecord(policy, cek, {
      ...teamPointer,
      version: 1,
      cekGeneration: 3,
    });
    orgRecord = await encryptPolicyRecord(policy, cek, {
      ...orgPointer,
      version: 1,
      cekGeneration: 3,
    });
    const teamKey = await derivePolicyKey(cek, { ...teamPointer, cekGeneration: 3 });
    const orgKey = await derivePolicyKey(cek, { ...orgPointer, cekGeneration: 3 });
    teamWrap = await wrapPolicyKeyForAgentGrant(teamKey, S, SERVER_SECRET, TEAM);
    orgWrap = await wrapPolicyKeyForAgentGrant(orgKey, S, SERVER_SECRET, ORG);
    configKey = await generateConfigKey();
    configWrap = await wrapConfigKeyForAgentGrant(configKey, S, SERVER_SECRET, BINDING);
  });

  it('round trips the team and org keys into non-extractable keys that open their records', async () => {
    const key = await unwrapPolicyKeyForAgentGrant(teamWrap, S, SERVER_SECRET, TEAM);
    expect(key.kind).toBe('policy-key');
    expect(key.key.extractable).toBe(false);
    expect(await opensPolicy(teamWrap, TEAM, teamRecord, teamPointer)).toBe(true);
    expect(await opensPolicy(orgWrap, ORG, orgRecord, orgPointer)).toBe(true);
  });

  it('refuses a content-key wrap presented as a policy-key wrap, and the reverse (control: each opens as itself)', async () => {
    expect(await opensPolicy(teamWrap, TEAM, teamRecord, teamPointer)).toBe(true);
    const ck = await unwrapConfigKeyForAgentGrant(configWrap, S, SERVER_SECRET, BINDING);
    expect(ck.algorithm.name).toBe('AES-GCM');
    // The two wraps share the slot key (same grant, store, config and generation); only the AAD label differs.
    await expect(
      unwrapPolicyKeyForAgentGrant(configWrap, S, SERVER_SECRET, TEAM)
    ).rejects.toBeInstanceOf(ConfigIntegrityError);
    await expect(
      unwrapConfigKeyForAgentGrant(teamWrap, S, SERVER_SECRET, BINDING)
    ).rejects.toBeInstanceOf(ConfigIntegrityError);
  });

  it('refuses the org wrap presented for the team pointer, and the reverse (control: each opens its own)', async () => {
    expect(await opensPolicy(teamWrap, TEAM, teamRecord, teamPointer)).toBe(true);
    expect(await opensPolicy(orgWrap, ORG, orgRecord, orgPointer)).toBe(true);
    expect(await opensPolicy(orgWrap, TEAM, teamRecord, teamPointer)).toBe(false);
    expect(await opensPolicy(teamWrap, ORG, orgRecord, orgPointer)).toBe(false);
  });

  it("a policy key does not open another pointer's record (control: it opens its own)", async () => {
    const teamKey = await unwrapPolicyKeyForAgentGrant(teamWrap, S, SERVER_SECRET, TEAM);
    await expect(decryptPolicyRecord(teamRecord, teamKey, teamPointer)).resolves.toEqual(policy);
    await expect(decryptPolicyRecord(orgRecord, teamKey, orgPointer)).rejects.toThrow(
      /Policy record integrity check failed/
    );
  });

  it('refuses another grant, store, config or generation (control: the bound one opens)', async () => {
    expect(await opensPolicy(teamWrap, TEAM, teamRecord, teamPointer)).toBe(true);
    for (const change of [
      { grantId: 'eu_grant-0009' },
      { storeId: 'store-2' },
      { configId: 'cfg-b' },
      { cekGeneration: 4 },
      { policyTeamId: 'team-2' },
    ]) {
      expect(await opensPolicy(teamWrap, { ...TEAM, ...change }, teamRecord, teamPointer)).toBe(
        false
      );
    }
  });

  it('refuses a wrong S or serverSecret (control: the right pair opens)', async () => {
    expect(await opensPolicy(teamWrap, TEAM, teamRecord, teamPointer)).toBe(true);
    await expect(
      unwrapPolicyKeyForAgentGrant(teamWrap, newAgentGrantSecret(), SERVER_SECRET, TEAM)
    ).rejects.toBeInstanceOf(ConfigIntegrityError);
    await expect(
      unwrapPolicyKeyForAgentGrant(teamWrap, S, newAgentGrantSecret(), TEAM)
    ).rejects.toBeInstanceOf(ConfigIntegrityError);
  });
});

describe('parseAgentBearer', () => {
  const good = formatAgentBearer(BINDING.grantId, S);

  it('parses the bearer it formats (control)', () => {
    const parsed = parseAgentBearer(good);
    expect(parsed?.grantId).toBe(BINDING.grantId);
    expect(hex(parsed?.secret ?? new Uint8Array())).toBe(hex(S));
  });

  it('rejects a wrong prefix', () => {
    expect(good.startsWith(AGENT_BEARER_PREFIX)).toBe(true);
    expect(parseAgentBearer(good.replace(/^rmcp_/, 'rmcx_'))).toBeNull();
    expect(parseAgentBearer(good.replace(/^rmcp_/, ''))).toBeNull();
    expect(parseAgentBearer(`Bearer ${good}`)).toBeNull();
  });

  it('rejects an empty secret or grant id', () => {
    expect(parseAgentBearer(`rmcp_${BINDING.grantId}.`)).toBeNull();
    expect(parseAgentBearer(`rmcp_${BINDING.grantId}`)).toBeNull();
    expect(parseAgentBearer(`rmcp_.${good.split('.')[1]}`)).toBeNull();
  });

  it('rejects a non-base64url body and a wrong-length secret', () => {
    const body = good.split('.')[1];
    expect(parseAgentBearer(`rmcp_${BINDING.grantId}.${body.slice(0, -1)}+`)).toBeNull();
    expect(parseAgentBearer(`rmcp_${BINDING.grantId}.${body.slice(0, -1)}/`)).toBeNull();
    expect(parseAgentBearer(`rmcp_${BINDING.grantId}.${body}=`)).toBeNull();
    expect(parseAgentBearer(`rmcp_${BINDING.grantId}.${body}.x`)).toBeNull();
    // Non-canonical trailing bits: the same 32 bytes under a different text.
    expect(parseAgentBearer(`rmcp_${BINDING.grantId}.${body.slice(0, -1)}9`)).toBeNull();
    expect(parseAgentBearer(`rmcp_${BINDING.grantId}.${body.slice(0, -4)}`)).toBeNull();
  });
});

describe('hashAuthTag', () => {
  it('rejects a tag that is not base64url of 32 bytes (control: a derived tag hashes)', async () => {
    const tag = await deriveAuthTag(S);
    await expect(hashAuthTag(tag)).resolves.toHaveLength(43);
    await expect(hashAuthTag('')).rejects.toThrow();
    await expect(hashAuthTag(tag.slice(0, -2))).rejects.toThrow();
    await expect(hashAuthTag(`${tag}=`)).rejects.toThrow();
    // The failure is a rejected promise, so a caller's try/catch around an awaited call sees it and a bare call throws nothing.
    expect(() => hashAuthTag('').catch(() => undefined)).not.toThrow();
  });
});
