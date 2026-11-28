import { describe, expect, it } from 'vitest';
import { WK_ACCOUNT_EGRESS_HOST, WK_OPENAI_API_BASE } from '../../config/well-known.generated.js';
import { omitKey } from '../../utils/omit-key.js';
import { buildProfile, getPreset, PRESETS } from '../presets.js';
import {
  AiConfigSchema,
  MAX_OUTPUT_TOKENS_CEILING,
  type Profile,
  ProfileSchema,
  validateProfile,
} from '../profile.js';

const base: Profile = {
  format: 'openai-chat',
  baseURL: WK_OPENAI_API_BASE,
  key: 'sk-test',
  authScheme: 'bearer',
  model: 'gpt-4.1',
  capabilities: { tools: true, streaming: true, parallelToolCalls: true, vision: false },
};

describe('ProfileSchema', () => {
  it('accepts a complete profile', () => {
    expect(ProfileSchema.safeParse(base).success).toBe(true);
  });

  it('refuses a missing key without byokOnly, accepts it with byokOnly', () => {
    const noKey = omitKey(base, 'key');
    expect(ProfileSchema.safeParse(noKey).success).toBe(false);
    expect(ProfileSchema.safeParse({ ...noKey, byokOnly: false }).success).toBe(false);
    expect(
      ProfileSchema.safeParse({
        ...noKey,
        byokOnly: true,
        headers: { 'cf-aig-authorization': 'Bearer t' },
      }).success
    ).toBe(true);
  });

  it('refuses an empty key', () => {
    expect(ProfileSchema.safeParse({ ...base, key: '' }).success).toBe(false);
  });

  it('refuses an unknown format, auth scheme and extra field', () => {
    expect(ProfileSchema.safeParse({ ...base, format: 'gemini-native' }).success).toBe(false);
    expect(ProfileSchema.safeParse({ ...base, authScheme: 'basic' }).success).toBe(false);
    expect(ProfileSchema.safeParse({ ...base, apiKey: 'x' }).success).toBe(false);
  });

  it('requires every capability flag and the model', () => {
    expect(
      ProfileSchema.safeParse({ ...base, capabilities: { tools: true, streaming: true } }).success
    ).toBe(false);
    expect(ProfileSchema.safeParse({ ...base, model: '' }).success).toBe(false);
  });

  it('takes an optional whole, positive output token cap up to the ceiling', () => {
    expect(ProfileSchema.safeParse({ ...base, maxOutputTokens: 2048 }).success).toBe(true);
    expect(
      ProfileSchema.safeParse({ ...base, maxOutputTokens: MAX_OUTPUT_TOKENS_CEILING }).success
    ).toBe(true);
    for (const bad of [0, -1, 1.5, MAX_OUTPUT_TOKENS_CEILING + 1, '2048']) {
      expect(ProfileSchema.safeParse({ ...base, maxOutputTokens: bad }).success).toBe(false);
    }
  });
});

describe('AiConfigSchema', () => {
  it('accepts named providers with an optional default', () => {
    expect(AiConfigSchema.safeParse({ providers: { main: base }, default: 'main' }).success).toBe(
      true
    );
    expect(AiConfigSchema.safeParse({ providers: {} }).success).toBe(true);
  });

  it('refuses an invalid profile inside providers', () => {
    expect(AiConfigSchema.safeParse({ providers: { main: { ...base, model: '' } } }).success).toBe(
      false
    );
  });
});

describe('validateProfile', () => {
  it('control: a good profile passes', () => {
    const r = validateProfile(base);
    expect(r.ok && r.profile.model).toBe('gpt-4.1');
  });

  it('adds the base URL guard on top of the shape check', () => {
    const r = validateProfile({ ...base, baseURL: `https://${WK_ACCOUNT_EGRESS_HOST}/v1` });
    expect(r).toMatchObject({
      ok: false,
      issues: [{ path: '/baseURL', refusal: 'internal-host' }],
    });
  });

  it('reports shape problems with their path and never reaches the guard', () => {
    const r = validateProfile({ ...base, model: '', baseURL: 'http://10.0.0.1' });
    expect(r.ok).toBe(false);
    expect(!r.ok && r.issues.map((i) => i.path)).toEqual(['/model']);
  });

  it('reports the key rule at /key', () => {
    const noKey = omitKey(base, 'key');
    const r = validateProfile(noKey);
    expect(!r.ok && r.issues.map((i) => i.path)).toEqual(['/key']);
  });
});

describe('presets', () => {
  const params: Record<string, Record<string, string>> = {
    'cloudflare-ai-gateway': { accountId: 'acc123', gatewayId: 'my-gw' },
    litellm: { host: 'llm.example.com' },
    portkey: { host: 'api.portkey.ai' },
  };

  it('ships the ten presets of D4', () => {
    expect(PRESETS.map((p) => p.id)).toEqual([
      'anthropic',
      'openai',
      'gemini',
      'mistral',
      'deepseek',
      'cloudflare-ai-gateway',
      'openrouter',
      'vercel-ai-gateway',
      'litellm',
      'portkey',
    ]);
  });

  it.each(PRESETS.map((p) => p.id))(
    'preset %s builds a valid profile that passes the guard',
    (id) => {
      const preset = getPreset(id);
      const built = buildProfile(id, {
        params: params[id],
        ...(preset?.byokOnly ? { headers: { 'cf-aig-authorization': 'Bearer t' } } : { key: 'k' }),
      });
      expect(built.ok).toBe(true);
      if (!built.ok || !preset) return;
      expect(built.profile).toMatchObject({
        format: preset.format,
        authScheme: preset.authScheme,
        model: preset.suggestedModel,
        preset: id,
      });
      expect(built.profile.baseURL.startsWith('https://')).toBe(true);
      expect(built.profile.baseURL).not.toContain('{');
    }
  );

  it('only anthropic presents its key as x-api-key over the messages format', () => {
    for (const preset of PRESETS) {
      const anthropic = preset.id === 'anthropic';
      expect(preset.format === 'anthropic-messages').toBe(anthropic);
      expect(preset.authScheme === 'x-api-key').toBe(anthropic);
    }
  });

  it('marks only Cloudflare AI Gateway byokOnly, and builds it without a key', () => {
    expect(PRESETS.filter((p) => p.byokOnly).map((p) => p.id)).toEqual(['cloudflare-ai-gateway']);
    const built = buildProfile('cloudflare-ai-gateway', {
      params: params['cloudflare-ai-gateway'],
      headers: { 'cf-aig-authorization': 'Bearer t' },
    });
    expect(built.ok && built.profile.key).toBeUndefined();
    expect(built.ok && built.profile.byokOnly).toBe(true);
    expect(built.ok && built.profile.baseURL).toBe(
      'https://gateway.ai.cloudflare.com/v1/acc123/my-gw/compat'
    );
  });

  it('a preset that is not byokOnly refuses a build without a key', () => {
    const built = buildProfile('openai');
    expect(!built.ok && built.issues.map((i) => i.path)).toEqual(['/key']);
  });

  it('takes the operator model over the suggestion', () => {
    const built = buildProfile('openai', { key: 'k', model: 'gpt-4o' });
    expect(built.ok && built.profile.model).toBe('gpt-4o');
  });

  it('requires every placeholder', () => {
    const built = buildProfile('cloudflare-ai-gateway', { params: { accountId: 'a' } });
    expect(!built.ok && built.issues.map((i) => i.path)).toEqual(['/params/gatewayId']);
  });

  it.each([
    ['litellm', { host: 'evil.com/path?x=' }],
    ['litellm', { host: 'user@evil.com' }],
    ['litellm', { host: 'a b.com' }],
    ['cloudflare-ai-gateway', { accountId: 'a/../b', gatewayId: 'g' }],
  ])('a %s placeholder value that adds path or credential text is refused', (id, p) => {
    const built = buildProfile(id, { key: 'k', params: p });
    expect(built.ok).toBe(false);
    expect(!built.ok && built.issues[0].path.startsWith('/params/')).toBe(true);
  });

  it('a self-hosted host that resolves to a private literal is refused by the guard', () => {
    for (const host of ['127.0.0.1', '10.0.0.5', 'localhost', 'litellm.internal']) {
      const built = buildProfile('litellm', { key: 'k', params: { host } });
      expect(built.ok).toBe(false);
      expect(!built.ok && built.issues[0].path).toBe('/baseURL');
    }
  });

  it('refuses an unknown preset', () => {
    expect(buildProfile('nope')).toMatchObject({ ok: false, issues: [{ path: '/preset' }] });
    expect(getPreset('nope')).toBeUndefined();
  });
});
