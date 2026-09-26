/**
 * A bare ref resolves to the family's GRAND, whatever tag the grand is stored under.
 *
 * getRepository, getRepositoryKey and resolveDestructiveTarget used to try only
 * `<name>:latest` for a bare ref, while resolve-machine.ts resolveStoredTag
 * dispatches a bare ref through the family's recorded grand pointer. A grand
 * stored as `shop:prod` was therefore found by machine dispatch and missed by
 * every config lookup, which is how the agent grand-repo guard failed open
 * (PLAN-cloudflare-proxy.md finding (c)).
 *
 * The config is real and request-scoped, read by the real configService.
 */

import type { RdcConfig } from '@rediacc/shared/config-schema';
import { describe, expect, it, vi } from 'vitest';

await vi.hoisted(async () => {
  const { mkdtempSync } = await import('node:fs');
  const os = await import('node:os');
  const scratch = mkdtempSync(`${os.tmpdir()}/rdc-grand-tag-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
});

import type { RepositoryConfig } from '../../../types/index.js';
import {
  createOutputState,
  createRequestConfigScope,
  runInRequestContext,
} from '../../core/request-context.js';
import { AmbiguousRepoTargetError, configService } from '../config-resources.js';
import { resolveRepoKey } from '../config-resources-resolve.js';

const GRAND_GUID = '11111111-1111-4111-8111-111111111111';
const FORK_GUID = '22222222-2222-4222-8222-222222222222';

function config(tags: Record<string, { repositoryGuid: string; grandGuid?: string }>): RdcConfig {
  const built: RdcConfig = {
    schemaVersion: 3,
    id: '00000000-0000-4000-8000-0000000000dd',
    version: 1,
    credentials: { ssh: { privateKey: 'KEY' } },
    resources: {
      machines: { m1: { ip: '10.1.1.1', user: 'root', port: 22 } },
      repositories: { shop: { grand: 'prod', placement: { machine: 'm1' }, tags } },
      storages: {},
    },
    encryption: { mode: 'plaintext' },
  };
  return built;
}

function scoped<T>(cfg: RdcConfig, fn: () => Promise<T>): Promise<T> {
  return runInRequestContext(
    {
      output: createOutputState(),
      stdout: [],
      stderr: [],
      config: createRequestConfigScope(cfg),
    },
    fn
  );
}

const GRAND_ONLY = config({ prod: { repositoryGuid: GRAND_GUID } });
const GRAND_AND_FORK = config({
  prod: { repositoryGuid: GRAND_GUID },
  trial: { repositoryGuid: FORK_GUID, grandGuid: GRAND_GUID },
});

describe('a bare ref on a family whose grand tag is not latest', () => {
  it('getRepository returns the grand', async () => {
    const repo = await scoped(GRAND_AND_FORK, () => configService.getRepository('shop'));
    expect(repo?.repositoryGuid).toBe(GRAND_GUID);
  });

  it('getRepositoryKey returns the grand key, for a bare ref and for :base', async () => {
    await scoped(GRAND_AND_FORK, async () => {
      expect(await configService.getRepositoryKey('shop')).toBe('shop:prod');
      expect(await configService.getRepositoryKey('shop:base')).toBe('shop:prod');
      expect(await configService.getRepositoryKey('shop:trial')).toBe('shop:trial');
      expect(await configService.getRepositoryKey('shop:latest')).toBeUndefined();
    });
  });

  it('resolveDestructiveTarget resolves a lone grand by its bare name', async () => {
    const target = await scoped(GRAND_ONLY, () => configService.resolveDestructiveTarget('shop'));
    expect(target.key).toBe('shop:prod');
  });

  it('resolveDestructiveTarget still refuses a bare ref shared by a grand and a fork', async () => {
    await expect(
      scoped(GRAND_AND_FORK, () => configService.resolveDestructiveTarget('shop'))
    ).rejects.toBeInstanceOf(AmbiguousRepoTargetError);
  });
});

describe('resolveRepoKey', () => {
  const repos: Record<string, RepositoryConfig> = {
    'shop:prod': { repositoryGuid: GRAND_GUID },
    'shop:trial': { repositoryGuid: FORK_GUID, grandGuid: GRAND_GUID },
  };

  it('follows the recorded grand pointer', () => {
    expect(resolveRepoKey(repos, 'shop', { shop: 'prod' })).toBe('shop:prod');
  });

  it('derives the grand when no pointer is recorded (a record not yet persisted)', () => {
    expect(resolveRepoKey(repos, 'shop')).toBe('shop:prod');
  });

  it('prefers latest among several grand-shaped tags, as persist does', () => {
    const two: Record<string, RepositoryConfig> = {
      ...repos,
      'shop:latest': { repositoryGuid: 'g3' },
    };
    expect(resolveRepoKey(two, 'shop')).toBe('shop:latest');
  });

  it('never resolves an unknown tag or an unknown family', () => {
    expect(resolveRepoKey(repos, 'shop:nope', { shop: 'prod' })).toBeUndefined();
    expect(resolveRepoKey(repos, 'cart', { shop: 'prod' })).toBeUndefined();
  });
});
