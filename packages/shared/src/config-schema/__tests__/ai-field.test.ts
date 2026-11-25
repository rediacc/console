/**
 * `ai` in the config (PLAN-console-ai-providers.md D2, box AP2).
 *
 * AI provider profiles live under a top-level `ai` key: named profiles and the
 * default one. A profile's `key` and every `headers` value are `secret` leaves,
 * so they are encrypted at rest, sealed in the blob on a push, and each carries
 * its own commitment: a push that rewrites one is accepted only from a device
 * that knows the current value. Every other leaf is public and commits nothing.
 */

import { describe, expect, it } from 'vitest';
import {
  blindPointer,
  deriveFieldCommitmentKey,
  derivePointerBlindingKey,
  generateCek,
  generateSdkMaster,
  sdkDerive,
  unwrapEnvelopeConfigKey,
  verifyCommitment,
} from '../../config-crypto/index.js';
import { computeSchemaCoverage } from '../coverage.js';
import { buildConfigPushPayload, decryptConfigPullPayload, fromFullConfig } from '../payload.js';
import { parseConfig, type RdcConfig, RdcConfigSchema } from '../schemas.js';
import { listSensitivityTemplates, SENSITIVITY_REGISTRY } from '../sensitivity.js';
import { pathsToCommit } from '../walker.js';

const STORE_ID = 'store-ai';
const KEY = 'sk-ant-test-0123456789abcdef';
const GATEWAY_TOKEN = 'cf-aig-token-fedcba9876543210';

const AI = {
  providers: {
    anthropic: {
      format: 'anthropic-messages' as const,
      baseURL: 'https://api.anthropic.com',
      key: KEY,
      authScheme: 'x-api-key' as const,
      model: 'claude-sonnet-4-5',
      capabilities: { tools: true, streaming: true, parallelToolCalls: true, vision: true },
      preset: 'anthropic',
    },
    gateway: {
      format: 'openai-chat' as const,
      baseURL: 'https://gateway.ai.cloudflare.com/v1/acct/gw/compat',
      authScheme: 'bearer' as const,
      model: 'openai/gpt-4.1',
      headers: { 'cf-aig-authorization': `Bearer ${GATEWAY_TOKEN}` },
      capabilities: { tools: true, streaming: true, parallelToolCalls: false, vision: false },
      preset: 'cloudflare-ai-gateway',
      byokOnly: true,
    },
  },
  default: 'anthropic',
};

function configWith(ai: unknown): RdcConfig {
  return {
    schemaVersion: 3,
    id: '7c8d1e9f-2a3b-4c5d-8e6f-1a2b3c4d5e6f',
    version: 1,
    encryption: { mode: 'plaintext' },
    resources: { machines: {}, repositories: {} },
    ai,
  } as RdcConfig;
}

async function push(config: RdcConfig) {
  const cek = await generateCek();
  const sdkDerived = await sdkDerive(generateSdkMaster(), 1);
  const payload = await buildConfigPushPayload(config, {
    storeId: STORE_ID,
    version: config.version + 1,
    sdkEpoch: 1,
    sdkDerived,
    cek,
    cekGeneration: 1,
  });
  const binding = { storeId: STORE_ID, configId: config.id, teamId: null };
  return { cek, sdkDerived, payload, binding };
}

describe('ai in the config', () => {
  it('parses the profiles and the default unchanged', () => {
    const parsed = parseConfig(RdcConfigSchema, configWith(structuredClone(AI)), 'test config');
    expect(parsed.ai).toEqual(AI);
  });

  it('refuses a profile without a key unless it is byokOnly', () => {
    const noKey = structuredClone(AI) as { providers: Record<string, Record<string, unknown>> };
    delete noKey.providers.anthropic.key;
    expect(RdcConfigSchema.safeParse(configWith(noKey)).success).toBe(false);
    // control: the byokOnly gateway profile carries no key and parses
    expect(
      RdcConfigSchema.safeParse(configWith({ providers: { g: AI.providers.gateway } })).success
    ).toBe(true);
  });

  it('refuses an unknown profile field and an unknown format', () => {
    const extra = structuredClone(AI) as { providers: Record<string, Record<string, unknown>> };
    extra.providers.anthropic.apiKey = KEY;
    expect(RdcConfigSchema.safeParse(configWith(extra)).success).toBe(false);
    const format = structuredClone(AI) as { providers: Record<string, Record<string, unknown>> };
    format.providers.anthropic.format = 'gemini-native';
    expect(RdcConfigSchema.safeParse(configWith(format)).success).toBe(false);
  });

  it('control: a config without ai still parses', () => {
    const rest: Record<string, unknown> = { ...configWith(AI) };
    delete rest.ai;
    expect(RdcConfigSchema.safeParse(rest).success).toBe(true);
  });

  it('registers key and header values as encrypted, committed secrets, and the rest as public', () => {
    for (const pointer of ['/ai/providers/*/key', '/ai/providers/*/headers/*']) {
      const meta = SENSITIVITY_REGISTRY.get(pointer);
      expect(meta, pointer).toMatchObject({ kind: 'secret', commit: true, encryptAtRest: true });
    }
    for (const pointer of ['/ai/providers/*/baseURL', '/ai/providers/*/model', '/ai/default']) {
      expect(SENSITIVITY_REGISTRY.get(pointer), pointer).toMatchObject({
        kind: 'public',
        commit: false,
      });
    }
  });

  it('commits exactly the key and each header value', () => {
    expect(pathsToCommit(configWith(AI)).filter((p) => p.startsWith('/ai'))).toEqual([
      '/ai/providers/anthropic/key',
      '/ai/providers/gateway/headers/cf-aig-authorization',
    ]);
  });

  it('every ai leaf is covered by the registry and no ai entry is stale', () => {
    const report = computeSchemaCoverage(RdcConfigSchema, listSensitivityTemplates());
    expect(report.uncovered.filter((p) => p.startsWith('/ai'))).toEqual([]);
    expect(report.stale.filter((p) => p.startsWith('/ai'))).toEqual([]);
  });

  it('survives a push and pull with the key sealed in the blob, never in the envelope', async () => {
    const config = configWith(structuredClone(AI));
    const { cek, sdkDerived, payload, binding } = await push(config);

    const wire = JSON.stringify(payload);
    expect(wire).not.toContain(KEY);
    expect(wire).not.toContain(GATEWAY_TOKEN);
    expect(JSON.stringify(payload.envelope)).not.toContain('/ai/');

    const pulled = fromFullConfig(
      await decryptConfigPullPayload(payload, { cek, sdkDerived, binding })
    );
    expect(pulled.ai).toEqual(AI);
    expect(pathsToCommit(pulled)).toEqual(pathsToCommit(config));
  });

  it('gates a rewrite of the key on knowing its current value', async () => {
    const config = configWith(structuredClone(AI));
    const { cek, payload, binding } = await push(config);
    const { fckSalt, fields } = payload.envelope.commitments;
    const contentKey = await unwrapEnvelopeConfigKey(payload.envelope, cek, binding);
    const fck = await deriveFieldCommitmentKey(contentKey, fckSalt);
    const blinding = await derivePointerBlindingKey(contentKey, config.id);

    const keyPointer = '/ai/providers/anthropic/key';
    const committed = fields[await blindPointer(blinding, keyPointer)];
    expect(committed).toBeDefined();
    expect(await verifyCommitment(fck, keyPointer, KEY, committed)).toBe(true);
    expect(await verifyCommitment(fck, keyPointer, 'sk-ant-guess', committed)).toBe(false);

    const headerPointer = '/ai/providers/gateway/headers/cf-aig-authorization';
    const header = fields[await blindPointer(blinding, headerPointer)];
    expect(await verifyCommitment(fck, headerPointer, `Bearer ${GATEWAY_TOKEN}`, header)).toBe(
      true
    );
    expect(await verifyCommitment(fck, headerPointer, 'Bearer other', header)).toBe(false);

    // A public leaf carries no commitment: changing the model needs no knowledge.
    expect(fields[await blindPointer(blinding, '/ai/providers/anthropic/model')]).toBeUndefined();
  });
});
