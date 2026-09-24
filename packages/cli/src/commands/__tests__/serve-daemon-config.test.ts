/**
 * Finding (a), PLAN-cloudflare-proxy.md "Writer B status": the daemon
 * executor's config loader returned getLocalConfig(), a machines-and-SSH
 * projection with no `policy` field, cast to RdcConfig. authorize() therefore
 * always saw "no policy document", and a daemon never enforced one.
 *
 * The config file is real (a scratch XDG dir) and so are the loader and
 * authorize(); nothing on the path is mocked.
 */

import { tmpdir } from 'node:os';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import type { PolicyDocument } from '@rediacc/shared/policy';
import { describe, expect, it, vi } from 'vitest';
import { configFileStorage } from '../../adapters/config-file-storage.js';
import { authorize, PolicyDenied } from '../../services/serve/policy.js';
import { loadDaemonConfig } from '../serve.js';

await vi.hoisted(async () => {
  const { mkdtempSync } = await import('node:fs');
  const os = await import('node:os');
  const scratch = mkdtempSync(`${os.tmpdir()}/rdc-serve-daemon-config-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
  delete process.env.REDIACC_CONFIG;
});

const POLICY: PolicyDocument = {
  version: 1,
  defaults: { commands: { allow: ['machine status'] } },
};

const CONFIG: RdcConfig = {
  schemaVersion: 3,
  id: '00000000-0000-4000-8000-0000000000dd',
  version: 1,
  credentials: { ssh: { privateKey: 'KEY' } },
  resources: {
    machines: { m1: { ip: '10.1.1.1', user: 'root', port: 22 } },
    repositories: {},
    storages: {},
  },
  encryption: { mode: 'plaintext' },
  policy: POLICY,
};

const OWNER = {
  userId: 'user-owner',
  userEmail: 'owner@example.com',
  orgId: 'org-1',
  teamId: null,
  orgRole: 'owner' as const,
};

describe('rdc serve --mode daemon config loader', () => {
  it('returns the enrolled config with its policy document', async () => {
    // Never write outside the scratch dir: this save would otherwise replace a real rediacc.json.
    expect(configFileStorage.getConfigDir().startsWith(tmpdir())).toBe(true);
    await configFileStorage.save(CONFIG, 'rediacc');

    const config = await loadDaemonConfig();

    expect(config.policy).toEqual(POLICY);
    expect(Object.keys(config.resources?.machines ?? {})).toEqual(['m1']);
  });

  it('lets authorize() enforce that document', async () => {
    const config = await loadDaemonConfig();
    const args = { principal: OWNER, config, machineName: 'm1' };

    expect(authorize({ ...args, commandPath: 'machine status' }).allowed).toBe(true);
    // An owner with no document is allowed everything; the document narrows it to one command.
    expect(() => authorize({ ...args, commandPath: 'machine prune' })).toThrow(PolicyDenied);
  });
});
