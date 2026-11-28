/**
 * The policy document's place in the config (PLAN-rmcp-policy-record.md Design 2).
 *
 * A remote config's policy is its own encrypted record, written only by the
 * roles D29 names through `PUT /configs/:id/policy`. A `policy` field inside a
 * pushed blob is the hole that record closes: any member with config write
 * access could rewrite it, and the server cannot see it change. So the schema
 * refuses `policy` beside a `remote` block, and only a local-file config (no
 * `remote`) keeps the field, as a ceiling (D24).
 *
 * The local field is never pushed, so it is not field-committed and carries no
 * sensitivity entry; coverage.ts lists it in LOCAL_ONLY_EXCLUSIONS instead.
 */

import { describe, expect, it } from 'vitest';
import { WK_SITE_ORIGIN } from '../../config/well-known.generated.js';
import { generateAesKey } from '../../config-crypto/aes.js';
import { decryptPolicyRecord, encryptPolicyRecord } from '../../config-crypto/policy-record.js';
import { evaluatePolicy, PolicyDocumentSchema } from '../../policy/index.js';
import { omitKey } from '../../utils/omit-key.js';
import { LOCAL_ONLY_EXCLUSIONS } from '../coverage.js';
import { parseConfig, type RdcConfig, RdcConfigSchema } from '../schemas.js';
import { listSensitivityTemplates } from '../sensitivity.js';
import { pathsToCommit } from '../walker.js';

const POLICY = {
  version: 1 as const,
  defaults: { commands: { allow: ['repo *'], deny: ['repo delete'] } },
  teams: { platform: { commands: { allow: ['*'] }, allowClusterOps: true } },
};

const REMOTE = {
  apiUrl: WK_SITE_ORIGIN,
  storeId: '3f2a1b0c-9d8e-4f7a-8b6c-5d4e3f2a1b0c',
  configId: '4a3b2c1d-0e9f-4a8b-9c7d-6e5f4a3b2c1d',
  storageKeyId: 'key-1',
};

function localConfig(): RdcConfig {
  return {
    schemaVersion: 3,
    id: '7c8d1e9f-2a3b-4c5d-8e6f-1a2b3c4d5e6f',
    version: 1,
    defaults: { language: 'en', datastoreSize: '95%' },
    encryption: { mode: 'plaintext' },
    policy: structuredClone(POLICY),
  };
}

describe('policy document in the config', () => {
  it('a local-file config keeps its policy as a typed section', () => {
    const parsed = parseConfig(RdcConfigSchema, localConfig(), 'test config');
    expect(parsed.policy).toEqual(POLICY);
  });

  it('a remote config carrying policy fails the parse', () => {
    const remote = { ...localConfig(), remote: structuredClone(REMOTE) };
    const result = RdcConfigSchema.safeParse(remote);
    expect(result.success).toBe(false);
    expect(result.error?.issues.map((i) => i.path.join('.'))).toEqual(['policy']);
  });

  it('control: the same remote config without policy parses', () => {
    const rest = omitKey(localConfig(), 'policy');
    const result = RdcConfigSchema.safeParse({ ...rest, remote: structuredClone(REMOTE) });
    expect(result.success).toBe(true);
  });

  it('rejects a malformed rule set at parse time', () => {
    const bad = { ...localConfig(), policy: { version: 99, defaults: 'not-an-object' } };
    expect(() => parseConfig(RdcConfigSchema, bad, 'test config')).toThrow();
  });

  it('carries no sensitivity entry and commits nothing: it never leaves the device', () => {
    expect(listSensitivityTemplates()).not.toContain('/policy');
    expect(LOCAL_ONLY_EXCLUSIONS).toContain('/policy');
    expect(pathsToCommit(localConfig()).filter((p) => p.startsWith('/policy'))).toEqual([]);
  });

  it('a remote config reads its policy back from the separate record, and the decision survives the round trip', async () => {
    const cek = await generateAesKey();
    const pointer = { storeId: REMOTE.storeId, configId: REMOTE.configId, teamId: 'platform' };
    const record = await encryptPolicyRecord(POLICY, cek, {
      ...pointer,
      version: 1,
      cekGeneration: 0,
    });
    const pulled = PolicyDocumentSchema.parse(await decryptPolicyRecord(record, cek, pointer));
    expect(pulled).toEqual(POLICY);
    const ctx = { userEmail: 'dev@example.com', orgRole: 'member', teamSlug: 'platform' } as const;
    for (const commandPath of ['repo up', 'repo delete', 'machine query']) {
      expect(evaluatePolicy(pulled, { ...ctx, commandPath })).toEqual(
        evaluatePolicy(POLICY, { ...ctx, commandPath })
      );
    }
    expect(evaluatePolicy(pulled, { ...ctx, commandPath: 'repo up' }).allowed).toBe(true);
    expect(evaluatePolicy(pulled, { ...ctx, commandPath: 'repo delete' }).allowed).toBe(false);
    // The team-allowed case: only the team's `*` admits it, so a pulled document that lost the team rule denies it (review 395c5213.1).
    expect(evaluatePolicy(pulled, { ...ctx, commandPath: 'machine query' }).allowed).toBe(true);
  });

  it('the schema accepts exactly what the policy engine validates', () => {
    // One definition, two consumers: if these ever diverged, the executor could honor a document the config would not store, or vice versa.
    expect(PolicyDocumentSchema.safeParse(POLICY).success).toBe(true);
  });
});
