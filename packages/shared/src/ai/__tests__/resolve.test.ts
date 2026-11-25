import { describe, expect, it } from 'vitest';
import { WK_ACCOUNT_EGRESS_HOST, WK_OPENAI_API_BASE } from '../../config/well-known.generated.js';
import { omitKey } from '../../utils/omit-key.js';
import type { AiConfig, Profile } from '../profile.js';
import { resolveProfile } from '../resolve.js';

function profile(model: string, overrides: Partial<Profile> = {}): Profile {
  return {
    format: 'openai-chat',
    baseURL: WK_OPENAI_API_BASE,
    key: 'k',
    authScheme: 'bearer',
    model,
    capabilities: { tools: true, streaming: true, parallelToolCalls: true, vision: false },
    ...overrides,
  };
}

const team: AiConfig = {
  providers: { fast: profile('team-fast'), shared: profile('team-over-shared') },
  default: 'fast',
};
const shared: AiConfig = {
  providers: { big: profile('org-big'), shared: profile('org-shared') },
  default: 'big',
};

describe('resolveProfile', () => {
  it('the team default wins over the shared default', () => {
    expect(resolveProfile({ team, shared })).toMatchObject({
      ok: true,
      name: 'fast',
      source: 'team',
      profile: { model: 'team-fast' },
    });
  });

  it('falls to the shared default when the team config has none', () => {
    expect(resolveProfile({ team: { providers: team.providers }, shared })).toMatchObject({
      ok: true,
      name: 'big',
      source: 'shared',
    });
    expect(resolveProfile({ shared })).toMatchObject({ ok: true, source: 'shared' });
  });

  it('uses the team default when there is no shared config', () => {
    expect(resolveProfile({ team })).toMatchObject({ ok: true, source: 'team', name: 'fast' });
  });

  it('a requested name resolves from the team config before the shared one', () => {
    expect(resolveProfile({ team, shared }, 'shared')).toMatchObject({
      ok: true,
      source: 'team',
      profile: { model: 'team-over-shared' },
    });
    expect(resolveProfile({ team, shared }, 'big')).toMatchObject({ ok: true, source: 'shared' });
  });

  it('control: without a team entry of that name the shared one answers', () => {
    expect(resolveProfile({ team: { providers: {} }, shared }, 'shared')).toMatchObject({
      ok: true,
      source: 'shared',
      profile: { model: 'org-shared' },
    });
  });

  it('refuses an unknown requested name, and a name that is only an Object prototype key', () => {
    expect(resolveProfile({ team, shared }, 'nope')).toMatchObject({
      ok: false,
      reason: 'unknown-profile',
    });
    expect(resolveProfile({ team, shared }, 'constructor')).toMatchObject({
      ok: false,
      reason: 'unknown-profile',
    });
  });

  it('a default that names a missing profile is an error, not a fall-through', () => {
    const dangling: AiConfig = { providers: {}, default: 'gone' };
    expect(resolveProfile({ team: dangling, shared })).toMatchObject({
      ok: false,
      reason: 'unknown-profile',
      source: 'team',
    });
    expect(resolveProfile({ shared: dangling })).toMatchObject({
      ok: false,
      reason: 'unknown-profile',
      source: 'shared',
    });
  });

  it('reports none-configured when neither config has a default', () => {
    expect(resolveProfile({})).toMatchObject({ ok: false, reason: 'none-configured' });
    expect(resolveProfile({ team: { providers: team.providers } })).toMatchObject({
      ok: false,
      reason: 'none-configured',
    });
  });

  it('never returns a profile whose base URL the guard refuses', () => {
    const bad: AiConfig = {
      providers: { main: profile('m', { baseURL: `https://${WK_ACCOUNT_EGRESS_HOST}/v1` }) },
      default: 'main',
    };
    const result = resolveProfile({ team: bad, shared });
    expect(result).toMatchObject({
      ok: false,
      reason: 'invalid-profile',
      source: 'team',
      name: 'main',
    });
    expect(!result.ok && result.message).toContain('/baseURL');
    expect(resolveProfile({ team: bad, shared }, 'main')).toMatchObject({
      ok: false,
      reason: 'invalid-profile',
    });
  });

  it('never returns a profile that fails the shape check (a key-less profile without byokOnly)', () => {
    const noKey = omitKey(profile('m'), 'key');
    const cfg = { providers: { main: noKey as Profile }, default: 'main' };
    expect(resolveProfile({ shared: cfg })).toMatchObject({ ok: false, reason: 'invalid-profile' });
  });
});
