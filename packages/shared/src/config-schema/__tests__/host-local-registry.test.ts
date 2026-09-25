/**
 * Every top-level key of the config is either carried to the server or host-local, never both and
 * never neither.
 *
 * A key `toFullConfig` does not project and HOST_LOCAL_POINTERS does not name is dropped by every
 * pull: the cache merge starts from the pulled document, and the pulled document is rebuilt without
 * it. That is how `renetPath` (fixed in bd0278084), `state.repos[*].networkId` (F3) and
 * `credentials.masterPasswordVerifier` (F4) were lost. A key in both lists would be pushed and then
 * overwritten by the local copy on every pull, so another device's edit never lands.
 *
 * "Projected" is measured, not declared: `toFullConfig` runs over a recording proxy, and the keys it
 * reads are the keys it carries. Roots it reads INTO (resources, credentials) are checked one level
 * down the same way.
 */

import { describe, expect, it } from 'vitest';
import type { z } from 'zod';
import { toFullConfig } from '../payload.js';
import type { RdcConfig } from '../schemas.js';
import { RdcConfigSchema } from '../schemas.js';
import { HOST_LOCAL_POINTERS, SENSITIVITY_REGISTRY } from '../sensitivity.js';

/** Widened for membership tests against computed pointers. */
const HOST_LOCAL: readonly string[] = HOST_LOCAL_POINTERS;

/** Every top-level section populated, so any read toFullConfig makes is observable. */
function everySectionPopulated(): RdcConfig {
  return {
    schemaVersion: 3,
    id: '7c8d1e9f-2a3b-4c5d-8e6f-1a2b3c4d5e6f',
    version: 5,
    account: { userEmail: 'admin@example.com' },
    defaults: { universalUser: 'rediacc' },
    credentials: { ssh: { privateKey: 'P' }, cfDnsApiToken: 'cf', masterPasswordVerifier: 'mpv' },
    resources: {
      machines: {},
      datastores: {},
      storages: {},
      repositories: {},
      deletedRepositories: [],
      backupStrategies: {},
      cloudProviders: {},
      clusters: {},
    },
    infra: { certEmail: 'ops@example.com' },
    encryption: { mode: 'plaintext' },
    remote: {
      apiUrl: 'https://eu.rediacc.com',
      storeId: '3f2a1b0c-9d8e-4f7a-8b6c-5d4e3f2a1b0c',
      configId: '4a3b2c1d-0e9f-4a8b-9c7d-6e5f4a3b2c1d',
    },
    renetPath: '/opt/bin/renet',
    state: { networkIds: { next: 3000 } },
    policy: { version: 1 },
  } as unknown as RdcConfig;
}

/** Run toFullConfig over a proxy and return every pointer it read (top level and one level down). */
function pointersReadByToFullConfig(): Set<string> {
  const read = new Set<string>();
  let recording = true;
  const wrap = (target: Record<string, unknown>, prefix: string, depth: number): unknown =>
    new Proxy(target, {
      get(obj, key, receiver) {
        const value: unknown = Reflect.get(obj, key, receiver);
        if (!recording || typeof key !== 'string') return value;
        const pointer = `${prefix}/${key}`;
        read.add(pointer);
        const isPlainObject = value !== null && typeof value === 'object' && !Array.isArray(value);
        return depth === 0 && isPlainObject
          ? wrap(value as Record<string, unknown>, pointer, depth + 1)
          : value;
      },
    });
  toFullConfig(wrap(everySectionPopulated(), '', 0) as RdcConfig, {
    version: 6,
    sdkEpoch: 1,
  });
  recording = false;
  return read;
}

function segments(pointer: string): string[] {
  return pointer.split('/').slice(1);
}

/** The object shape under a top-level key, unwrapping `.optional()`; undefined for non-objects. */
function childKeys(root: string): string[] | undefined {
  let schema = (RdcConfigSchema.shape as Record<string, z.ZodType>)[root] as unknown as {
    unwrap?: () => unknown;
    shape?: Record<string, unknown>;
  };
  while (schema.unwrap && !schema.shape) schema = schema.unwrap() as typeof schema;
  return schema.shape ? Object.keys(schema.shape) : undefined;
}

/**
 * For a root toFullConfig reads INTO, the children that are not exactly one of {read, host-local}.
 * A root read whole (no child reads) is carried whole and has nothing to check.
 */
function misclassifiedChildren(root: string, read: Set<string>): string[] {
  const children = childKeys(root);
  const readsInto = [...read].some((p) => p.startsWith(`/${root}/`));
  if (!children || !readsInto) return [];
  return children
    .map((child) => `/${root}/${child}`)
    .filter((pointer) => read.has(pointer) === HOST_LOCAL.includes(pointer));
}

describe('host-local registry: every config key is projected or host-local', () => {
  const read = pointersReadByToFullConfig();
  const topKeys = Object.keys(RdcConfigSchema.shape);
  const hostLocalRoots = new Set(
    HOST_LOCAL_POINTERS.filter((p) => segments(p).length === 1).map((p) => segments(p)[0])
  );
  const projectedRoots = new Set(
    [...read].filter((p) => segments(p).length === 1).map((p) => segments(p)[0])
  );

  it('the measurement sees toFullConfig read (control: the recorder is not blind)', () => {
    expect(projectedRoots.has('resources')).toBe(true);
    expect(read.has('/credentials/ssh')).toBe(true);
  });

  it('classifies every top-level key of RdcConfigSchema exactly once', () => {
    const unclassified = topKeys.filter((k) => !projectedRoots.has(k) && !hostLocalRoots.has(k));
    const both = topKeys.filter((k) => projectedRoots.has(k) && hostLocalRoots.has(k));
    expect(
      unclassified,
      `neither projected by toFullConfig nor in HOST_LOCAL_POINTERS (a pull drops them): ${unclassified.join(', ')}`
    ).toEqual([]);
    expect(both, `both projected and host-local: ${both.join(', ')}`).toEqual([]);
  });

  it('names only real schema keys (no stale entry)', () => {
    const stale = HOST_LOCAL_POINTERS.filter((p) => {
      const [root, ...rest] = segments(p);
      if (!topKeys.includes(root)) return true;
      return rest.length > 0 && !(childKeys(root) ?? []).includes(rest[0]);
    });
    expect(stale).toEqual([]);
  });

  it('classifies every child of a root toFullConfig reads into exactly once', () => {
    const problems = [...projectedRoots].flatMap((root) => misclassifiedChildren(root, read));
    expect(problems).toEqual([]);
  });

  it('puts every nested host-local pointer under a projected root, one level deep', () => {
    const bad = HOST_LOCAL_POINTERS.filter((p) => {
      const parts = segments(p);
      return parts.length > 2 || (parts.length === 2 && !projectedRoots.has(parts[0]));
    });
    expect(bad).toEqual([]);
  });

  it('commits nothing under a host-local pointer (committed means carried)', () => {
    const committed = [...SENSITIVITY_REGISTRY.entries()]
      .filter(([, meta]) => meta.commit)
      .map(([template]) => template)
      .filter((template) =>
        HOST_LOCAL_POINTERS.some((p) => template === p || template.startsWith(`${p}/`))
      );
    expect(committed).toEqual([]);
  });
});
