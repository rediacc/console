/**
 * The one repo resolver of the decision step (services/policy/target.ts) against the REAL config
 * resolver.
 *
 * command-policy.test.ts mocks configService.getRepository wholesale, which is exactly the seam
 * this file exercises: the decision asks the resolver whether a ref is a grand repo. The config
 * here is real, held request-scoped, and read by the real configService.
 *
 * Finding (c), PLAN-cloudflare-proxy.md "Writer B status": a bare ref names the family's GRAND
 * POINTER (resolve-machine.ts resolveStoredTag), but getRepository's bare fallback tries only
 * `<name>:latest`. A grand stored under any other tag was therefore invisible to the guard, and an
 * agent could `repo up` / `repo down` / `repo exec` it by its bare name.
 */

import type { RdcConfig } from '@rediacc/shared/config-schema';
import { describe, expect, it, vi } from 'vitest';

await vi.hoisted(async () => {
  const { mkdtempSync } = await import('node:fs');
  const os = await import('node:os');
  const scratch = mkdtempSync(`${os.tmpdir()}/rdc-policy-grand-ref-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
});

import {
  createOutputState,
  createRequestConfigScope,
  runInRequestContext,
} from '../../services/core/request-context.js';
import { resolveTarget } from '../../services/policy/target.js';

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
    },
    encryption: { mode: 'plaintext' },
  };
}

function stateOf(grandTag: string, ref: string): Promise<string | undefined> {
  return runInRequestContext(
    {
      output: createOutputState(),
      stdout: [],
      stderr: [],
      config: createRequestConfigScope(config(grandTag)),
    },
    async () => (await resolveTarget({ ref })).repo?.state
  );
}

describe('the decision target, real resolver', () => {
  it('resolves a bare ref whose grand line is `latest` to the grand', async () => {
    expect(await stateOf('latest', 'shop')).toBe('grand');
  });

  it('resolves a bare ref whose grand line is NOT `latest` to the grand (finding c)', async () => {
    expect(await stateOf('prod', 'shop')).toBe('grand');
  });

  it('never resolves the reserved `:base` spelling to a fork', async () => {
    // parseRef refuses `:base`, so it is unresolved, which decide counts as grand.
    expect(await stateOf('prod', 'shop:base')).not.toBe('fork');
    expect(await stateOf('latest', 'shop:base')).not.toBe('fork');
  });

  it('resolves the grand addressed by its explicit tag', async () => {
    expect(await stateOf('prod', 'shop:prod')).toBe('grand');
  });

  it('resolves a fork', async () => {
    expect(await stateOf('prod', 'shop:trial')).toBe('fork');
  });

  it('reports an unknown repo as unresolved, which decide counts as grand (fail closed)', async () => {
    expect(await stateOf('prod', 'nothere')).toBe('unresolved');
  });
});
