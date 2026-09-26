/**
 * The local agent guard against the REAL config resolver.
 *
 * command-policy.test.ts mocks configService.getRepository wholesale, which is
 * exactly the seam this file exercises: the guard asks the resolver whether a
 * ref is a grand repo, and a resolver miss makes the guard return early (it
 * fails open). The config here is real, held request-scoped, and read by the
 * real configService.
 *
 * Finding (c), PLAN-cloudflare-proxy.md "Writer B status": a bare ref names the
 * family's GRAND POINTER (resolve-machine.ts resolveStoredTag), but
 * getRepository's bare fallback tries only `<name>:latest`. A grand stored under
 * any other tag was therefore invisible to the guard, and an agent could
 * `repo up` / `repo down` / `repo exec` it by its bare name.
 */

import type { RdcConfig } from '@rediacc/shared/config-schema';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

await vi.hoisted(async () => {
  const { mkdtempSync } = await import('node:fs');
  const os = await import('node:os');
  const scratch = mkdtempSync(`${os.tmpdir()}/rdc-policy-grand-ref-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
});

vi.mock('../agent-guard.js', () => ({ isAgentEnvironment: vi.fn(() => true) }));

import {
  createOutputState,
  createRequestConfigScope,
  runInRequestContext,
} from '../../services/core/request-context.js';
import { assertCommandPolicy, CMD } from '../command-policy.js';

const GRAND_GUID = '11111111-1111-4111-8111-111111111111';
const FORK_GUID = '22222222-2222-4222-8222-222222222222';

/** `shop`'s grand line is tag `prod`, not `latest`; `shop:trial` is its fork. */
function config(grandTag: string): RdcConfig {
  return {
    schemaVersion: 3,
    id: '00000000-0000-4000-8000-0000000000cc',
    version: 1,
    credentials: { ssh: { privateKey: 'KEY' } },
    resources: {
      machines: { m1: { ip: '10.1.1.1', user: 'root', port: 22 } },
      repositories: {
        shop: {
          grand: grandTag,
          placement: { machine: 'm1' },
          tags: {
            [grandTag]: { repositoryGuid: GRAND_GUID },
            trial: { repositoryGuid: FORK_GUID, grandGuid: GRAND_GUID, parentGuid: GRAND_GUID },
          },
        },
      },
      storages: {},
    },
    encryption: { mode: 'plaintext' },
  };
}

function guard(grandTag: string, ref: string): Promise<void> {
  return runInRequestContext(
    {
      output: createOutputState(),
      stdout: [],
      stderr: [],
      config: createRequestConfigScope(config(grandTag)),
    },
    () => assertCommandPolicy(CMD.REPO_UP, ref)
  );
}

describe('agent grand guard, real resolver', () => {
  beforeEach(() => {
    delete process.env.REDIACC_ALLOW_GRAND_REPO;
  });
  afterEach(() => {
    delete process.env.REDIACC_ALLOW_GRAND_REPO;
  });

  it('refuses a bare ref whose grand line is `latest`', async () => {
    await expect(guard('latest', 'shop')).rejects.toThrow(/shop/);
  });

  it('refuses a bare ref whose grand line is NOT `latest` (finding c)', async () => {
    await expect(guard('prod', 'shop')).rejects.toThrow(/shop/);
  });

  it('refuses the reserved `:base` spelling of the grand', async () => {
    // parseRef refuses `:base` before any verb gets here; the guard must not depend on that.
    await expect(guard('prod', 'shop:base')).rejects.toThrow(/shop/);
    await expect(guard('latest', 'shop:base')).rejects.toThrow(/shop/);
  });

  it('refuses the grand addressed by its explicit tag', async () => {
    await expect(guard('prod', 'shop:prod')).rejects.toThrow(/shop/);
  });

  it('lets a fork through', async () => {
    await expect(guard('prod', 'shop:trial')).resolves.toBeUndefined();
  });

  it('lets an unknown repo through (the command itself reports not-found)', async () => {
    await expect(guard('prod', 'nothere')).resolves.toBeUndefined();
  });
});
