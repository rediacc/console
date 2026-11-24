/**
 * WB0 (agent/plans/PLAN-rmcp-writeback.md Design 1): a dispatched command whose
 * config change the executor cannot save fails before any host job.
 *
 * The container tier runs a command against the config it decrypted for the
 * session (a request-scoped config). Before this stop-gap a version-bumping write
 * stayed in request memory and the command reported success with a stderr
 * warning: a proxied `repo create` built the encrypted volume on the host and the
 * only copy of its key died with the request. Now the spec write throws
 * ConfigWriteUnavailableError, and because `repo create` registers the repo before
 * it starts the create job, the machine is never called.
 *
 * The real Commander tree, the real configService and configFileStorage run; the
 * executor (the fake renet) and the config are the only seams.
 */

import type { RdcConfig } from '@rediacc/shared/config-schema';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../../utils/agent-guard.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/agent-guard.js')>()),
  isAgentEnvironment: () => false,
}));

await vi.hoisted(async () => {
  const { mkdtempSync } = await import('node:fs');
  const os = await import('node:os');
  const scratch = mkdtempSync(`${os.tmpdir()}/rdc-writeback-stopgap-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
  process.env.REDIACC_TELEMETRY_DISABLED = '1';
});

import { configFileStorage } from '../../../adapters/config-file-storage.js';
import {
  CONFIG_WRITE_UNAVAILABLE,
  ConfigWriteUnavailableError,
} from '../../core/config-write-errors.js';
import {
  createOutputState,
  createRequestConfigScope,
  runInRequestContext,
} from '../../core/request-context.js';
import type { ExecuteOptions, ExecuteResult, Executor } from '../../executor/types.js';
import { dispatchCommand, prepareCommand, withUnsavedWrite } from '../command-dispatch.js';

function sessionConfig(): RdcConfig {
  return {
    schemaVersion: 3,
    id: '00000000-0000-4000-8000-0000000000b0',
    version: 3,
    credentials: { ssh: { privateKey: 'KEY' } },
    resources: {
      machines: { m1: { ip: '10.1.1.1', user: 'root', port: 22 } },
      repositories: {},
    },
    state: {},
    encryption: { mode: 'plaintext' },
  } as unknown as RdcConfig;
}

/** A fake renet that records every call and would succeed. */
function fakeRenet(): { executor: Executor; calls: ExecuteOptions[] } {
  const calls: ExecuteOptions[] = [];
  return {
    calls,
    executor: {
      execute(options): Promise<ExecuteResult> {
        calls.push(options);
        return Promise.resolve({ success: true, exitCode: 0, durationMs: 1, stdout: '' });
      },
    },
  };
}

describe('WB0: a config write the executor cannot save fails before the host job', () => {
  it('a dispatched repo create ends with CONFIG_WRITE_UNAVAILABLE and never calls the machine', async () => {
    const renet = fakeRenet();
    const config = sessionConfig();

    const outcome = await dispatchCommand({
      prepared: prepareCommand('repo create', { machine: 'm1', size: '1G' }, { name: 'shop' }),
      executor: renet.executor,
      onEvent: () => {},
      config,
    });

    expect(renet.calls).toEqual([]);
    expect(outcome.result.success).toBe(false);
    expect(outcome.result.errorCode).toBe(CONFIG_WRITE_UNAVAILABLE);
    // The JSON envelope (a dispatch is not a TTY) carries the code, and the message names the command and the way out.
    const envelope = JSON.parse(outcome.stdout) as {
      errors: { code: string; message: string }[];
    };
    expect(envelope.errors[0]?.code).toBe(CONFIG_WRITE_UNAVAILABLE);
    expect(envelope.errors[0]?.message).toContain('rdc repo create');
    expect(envelope.errors[0]?.message).toContain('Run it locally until write-back ships');
    // The removed warning is gone: a refusal replaces "success, but not saved".
    expect(outcome.stderr).not.toContain('did not save the change');
    // The session's config is untouched: no half-registered repo.
    expect(config.resources?.repositories).toEqual({});
  });

  it('a success whose config write was refused fails with the write code (review 87c7ff68.1)', () => {
    const ok = { success: true, exitCode: 0, durationMs: 1 } satisfies ExecuteResult;
    expect(withUnsavedWrite(ok, CONFIG_WRITE_UNAVAILABLE)).toMatchObject({
      success: false,
      exitCode: 1,
      errorCode: CONFIG_WRITE_UNAVAILABLE,
    });
    expect(withUnsavedWrite(ok, undefined)).toBe(ok);
  });

  it('control: a state-only write under a request scope still applies in memory', async () => {
    const scope = createRequestConfigScope(sessionConfig());
    const context = { output: createOutputState(), stdout: [], stderr: [], config: scope };

    const updated = await runInRequestContext(context, () =>
      configFileStorage.updateState('rediacc', (cfg) => ({
        ...cfg,
        state: { ...cfg.state, repos: { shop: { latest: { networkId: 2816 } } } },
      }))
    );

    expect(updated.state?.repos?.shop?.latest?.networkId).toBe(2816);
    expect(scope.config.state?.repos?.shop?.latest?.networkId).toBe(2816);
    // A state write bumps no version and records no refusal.
    expect(scope.config.version).toBe(3);
    expect(scope.writeFailure).toBeUndefined();
  });

  it('a spec write under a request scope is refused before its updater runs', async () => {
    const scope = createRequestConfigScope(sessionConfig());
    const context = { output: createOutputState(), stdout: [], stderr: [], config: scope };
    const updater = vi.fn((cfg: RdcConfig) => cfg);

    await expect(
      runInRequestContext(context, () => configFileStorage.update('rediacc', updater))
    ).rejects.toBeInstanceOf(ConfigWriteUnavailableError);

    expect(updater).not.toHaveBeenCalled();
    expect(scope.writeFailure).toBe(CONFIG_WRITE_UNAVAILABLE);
    expect(scope.config.version).toBe(3);
  });
});
