import { fromFullConfig, toFullConfig } from '@rediacc/shared/config-schema';
import { describe, expect, it } from 'vitest';
import type { RdcConfig } from '../../../types/index.js';
import { isNoopPush } from '../push-visibility.js';

function cfg(extra: Record<string, unknown>): RdcConfig {
  return {
    schemaVersion: 3,
    id: 'c0ffee00-0000-4000-8000-000000000000',
    resources: { machines: { hostinger: { ip: '10.0.0.1', user: 'root' } } },
    ...extra,
  } as unknown as RdcConfig;
}

/** The document as a pull rebuilds it from the wire (no crypto: the blob is the JSON of this). */
function overTheWire(config: RdcConfig): RdcConfig {
  const full = toFullConfig(JSON.parse(JSON.stringify(config)) as RdcConfig, {
    version: 2,
    sdkEpoch: 1,
  });
  return fromFullConfig(JSON.parse(JSON.stringify(full)));
}

describe('isNoopPush: empty objects (#d00f4c1e)', () => {
  // `/access` is the whole-stored subtree these cases use; `/policy` left the pushed document (a
  // remote config refuses it, PLAN-rmcp-policy-record Design 2), so it is no longer one.
  it('the wire carries an empty object inside a whole-stored subtree', () => {
    const access = { keys: { probe: { publicKey: 'ssh-ed25519 AAAA', machines: {} } } };
    expect(
      (overTheWire(cfg({ access })) as unknown as Record<string, unknown>).access
    ).toStrictEqual(access);
  });

  it('an edit that only adds {} inside /access is a push (the binding 08acee9bb routed around)', () => {
    const base = cfg({
      access: { keys: { probe: { publicKey: 'ssh-ed25519 AAAA', machines: {} } } },
    });
    const merged = cfg({
      access: { keys: { probe: { publicKey: 'ssh-ed25519 AAAA', machines: { hostinger: {} } } } },
    });
    expect(isNoopPush(merged, base)).toBe(false);
  });

  it('a whole-stored subtree that becomes {} where it was absent is a push', () => {
    expect(isNoopPush(cfg({ access: {} }), cfg({}))).toBe(false);
  });

  it('the same whole-stored value on both sides is still a no-op', () => {
    const access = { keys: { probe: { publicKey: 'ssh-ed25519 AAAA', machines: {} } } };
    expect(isNoopPush(cfg({ access }), cfg({ access: structuredClone(access) }))).toBe(true);
  });

  it('an empty object outside any whole-stored subtree is still dropped', () => {
    const base = cfg({});
    expect(isNoopPush(cfg({ infra: {} }), base)).toBe(true);
    expect(isNoopPush(cfg({ infra: { dns: {} } }), base)).toBe(true);
  });

  it('/resources/storages is whole-stored too, so an empty storages object is a push', () => {
    const merged = cfg({
      resources: { machines: { hostinger: { ip: '10.0.0.1', user: 'root' } }, storages: {} },
    });
    expect(isNoopPush(merged, cfg({}))).toBe(false);
  });

  it('a pulled copy, with the empty families a pull rebuilds, is a no-op against the local one', () => {
    const local = cfg({ policy: { rules: [] } });
    expect(isNoopPush(overTheWire(local), local)).toBe(true);
  });
});
