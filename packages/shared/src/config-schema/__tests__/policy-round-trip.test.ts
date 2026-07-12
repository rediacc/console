/**
 * The policy document must survive the encrypted round trip.
 *
 * This is the regression test for the worst bug found in the proxy campaign.
 * `selectiveEncrypt` builds the ciphertext by copying SENSITIVE_FIELDS, and
 * `policy` was not in that list, while `toFullConfig` did not copy it either.
 * So the rules were dropped twice over: a push discarded them, and a pull could
 * not have returned them anyway.
 *
 * The consequence was silent and total. The executor is the ONLY thing that
 * enforces authorization, and it can only see what the blob carries. So every
 * store-backed deployment fell through to MISSING_POLICY_DEFAULT — owners and
 * admins allowed, members denied — no matter what rules the org had written.
 * No error, no warning: the rules simply were not there.
 *
 * Asserting that a `policy` key survives is NOT enough, and this file does not
 * settle for it. The thing that has to survive is the DECISION: evaluatePolicy
 * on the recovered document must rule exactly as it did on the original. A
 * document that round-trips with one glob mangled would pass a key-presence
 * check and still hand an org's machines to the wrong person.
 */

import { describe, expect, it } from 'vitest';
import { generateCek, generateSdkMaster, sdkDerive } from '../../config-crypto/index.js';
import { fullConfigToRdcConfig } from '../../config-crypto/rotation.js';
import { evaluatePolicy, type PolicyContext, type PolicyDocument } from '../../policy/index.js';
import { buildConfigPushPayload, decryptConfigPullPayload } from '../payload.js';
import type { RdcConfig } from '../schemas.js';
import { pathsToCommit } from '../walker.js';

/** Rules with teeth: an explicit deny, a team grant, and a user override. */
const POLICY: PolicyDocument = {
  version: 1,
  defaults: { commands: { allow: ['repo *'], deny: ['repo delete'] } },
  teams: { platform: { commands: { allow: ['*'] }, allowClusterOps: true } },
  users: { 'dev@example.com': { machines: ['staging-*'] } },
};

function configWith(policy?: PolicyDocument): RdcConfig {
  return {
    schemaVersion: 3,
    id: '7c8d1e9f-2a3b-4c5d-8e6f-1a2b3c4d5e6f',
    version: 3,
    credentials: { ssh: { privateKey: 'PRIVATE' } },
    resources: {
      machines: { 'web-1': { ip: '10.0.0.1', user: 'deploy' } },
      repositories: {},
      storages: {},
    },
    encryption: { mode: 'plaintext' },
    ...(policy === undefined ? {} : { policy: structuredClone(policy) }),
  } as RdcConfig;
}

async function keys() {
  return { cek: await generateCek(), sdkDerived: await sdkDerive(generateSdkMaster(), 9) };
}

/** Push, then pull, then rebuild the config exactly as a real client does. */
async function roundTrip(config: RdcConfig): Promise<RdcConfig> {
  const { cek, sdkDerived } = await keys();
  const payload = await buildConfigPushPayload(config, {
    version: config.version + 1,
    sdkEpoch: 9,
    sdkDerived,
    cek,
  });
  const decrypted = await decryptConfigPullPayload(payload, { cek, sdkDerived });
  return fullConfigToRdcConfig(decrypted);
}

const ctx = (overrides: Partial<PolicyContext> = {}): PolicyContext => ({
  userEmail: 'dev@example.com',
  orgRole: 'member',
  commandPath: 'repo up',
  ...overrides,
});

describe('policy survives the encrypted round trip', () => {
  it('comes back byte-identical', async () => {
    const recovered = await roundTrip(configWith(POLICY));
    expect(recovered.policy).toEqual(POLICY);
  });

  it('is actually carried INSIDE the ciphertext, not the plaintext envelope', async () => {
    const { cek, sdkDerived } = await keys();
    const payload = await buildConfigPushPayload(configWith(POLICY), {
      version: 4,
      sdkEpoch: 9,
      sdkDerived,
      cek,
    });

    // The envelope is what the server can read. The rules must not be in it.
    const envelopeJson = JSON.stringify(payload.envelope);
    expect(envelopeJson).not.toContain('repo delete');
    expect(envelopeJson).not.toContain('dev@example.com');

    // But the ciphertext must yield them back.
    const decrypted = await decryptConfigPullPayload(payload, { cek, sdkDerived });
    expect((decrypted as { policy?: PolicyDocument }).policy).toEqual(POLICY);
  });

  // ── The rules must still BIND, not merely exist ──────────────────────

  it('rules the same way after the round trip as before it', async () => {
    const original = configWith(POLICY);
    const recovered = await roundTrip(original);

    const cases: PolicyContext[] = [
      ctx({ commandPath: 'repo up' }),
      ctx({ commandPath: 'repo delete' }), // denied by the explicit deny
      ctx({ commandPath: 'machine query' }), // outside the defaults allow-list
      ctx({ commandPath: 'cluster scale', teamSlug: 'platform' }),
      ctx({ commandPath: 'repo up', teamSlug: 'platform' }),
      ctx({ commandPath: 'repo up', machineName: 'staging-1' }),
      ctx({ commandPath: 'repo up', machineName: 'prod-1' }), // user rule scopes machines
      ctx({ commandPath: 'repo up', orgRole: 'owner' }),
    ];

    for (const c of cases) {
      const before = evaluatePolicy(original.policy, c);
      const after = evaluatePolicy(recovered.policy, c);
      expect(after, `decision drifted for ${c.commandPath} / ${c.machineName ?? '-'}`).toEqual(
        before
      );
    }
  });

  it('a deny rule still denies after the round trip', async () => {
    const recovered = await roundTrip(configWith(POLICY));

    // This is the assertion that would have failed before the fix: with the
    // policy dropped, evaluatePolicy(undefined, ...) fell through to the
    // missing-document default and this command was ALLOWED for an owner.
    const decision = evaluatePolicy(recovered.policy, ctx({ commandPath: 'repo delete' }));
    expect(decision.allowed).toBe(false);
    expect(decision.reason).toMatch(/explicitly denies/);

    // And it denies an owner too — a deny outranks every tier.
    expect(
      evaluatePolicy(recovered.policy, ctx({ commandPath: 'repo delete', orgRole: 'owner' }))
        .allowed
    ).toBe(false);
  });

  // ── The explicit-undefined trap, for this field ──────────────────────

  it('a config with no policy round-trips with no policy KEY at all', async () => {
    const recovered = await roundTrip(configWith(undefined));

    // Not `policy: undefined` — absent. A present-but-undefined key would commit
    // '/policy' and make the next ordinary push look like a downgrade.
    expect('policy' in recovered).toBe(false);
    expect(pathsToCommit(recovered)).not.toContain('/policy');
  });

  it('the rebuilt config commits exactly the pointers the original did', async () => {
    const original = configWith(POLICY);
    const recovered = await roundTrip(original);

    // Anti-downgrade compares these sets. A pointer that appears or vanishes
    // across a round trip bricks the next push for the whole org.
    expect(pathsToCommit(recovered)).toContain('/policy');
    expect(pathsToCommit(recovered)).toEqual(pathsToCommit(original));
  });
});
