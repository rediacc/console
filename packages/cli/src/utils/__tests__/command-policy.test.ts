/**
 * The CLI's decision step (command-policy.ts): a local run judged by `decide` through `enforce`,
 * with the local principal, the local-file policy (D24), the ancestry-verified env opt-ins and the
 * `--confirm-grand` retry. Driven here through `enforceResolvedTarget`, which shares every step
 * with the root hook (`enforceRootCommand`, command-policy-root.test.ts) but the target reading.
 */

import type { Command } from 'commander';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({
  config: undefined as unknown,
  fileExists: true,
  adapter: null as null | { policyContext: () => Promise<unknown> },
}));

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getRepository: vi.fn(),
    getCurrentName: vi.fn(() => 'rediacc'),
    // The ops-VM test reads machines and datastores from the current config.
    getCurrent: vi.fn(() => Promise.resolve(state.config ?? null)),
    // A remote config's principal and policy come from its adapter's session (D2).
    getActiveRemoteAdapter: vi.fn(() => Promise.resolve(state.adapter)),
  },
}));

vi.mock('../../adapters/config-file-storage.js', () => ({
  configFileStorage: {
    exists: vi.fn(() => Promise.resolve(state.fileExists)),
    load: vi.fn(() => Promise.resolve(state.config ?? {})),
  },
}));

vi.mock('../agent-guard.js', () => ({
  isAgentEnvironment: vi.fn(),
}));

vi.mock('../process-ancestry.js', () => ({
  isOverrideLegitimate: vi.fn(() => true),
  isAncestryVerificationAvailable: vi.fn(() => true),
  OVERRIDE_VAR_CLUSTER: 'REDIACC_ALLOW_CLUSTER_OPS',
  OVERRIDE_VAR_GRAND: 'REDIACC_ALLOW_GRAND_REPO',
}));

vi.mock('../../services/core/audit-log.js', () => ({
  auditLog: vi.fn(),
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) => {
    if (params) return `${key}:${JSON.stringify(params)}`;
    return key;
  },
}));

import { configService } from '../../services/config/config-resources.js';
import { auditLog } from '../../services/core/audit-log.js';
import {
  createOutputState,
  createRequestConfigScope,
  runInRequestContext,
} from '../../services/core/request-context.js';
import type { RepositoryConfig } from '../../types/index.js';
import { isAgentEnvironment } from '../agent-guard.js';
import { CliExitError } from '../cli-exit-error.js';
import {
  ACTION_RESOLVED_TARGETS,
  CMD,
  COMMAND_POLICIES,
  enforceResolvedTarget,
  enforceRootCommand,
  setConfirmGrand,
  validateRemotePath,
} from '../command-policy.js';
import { isAncestryVerificationAvailable, isOverrideLegitimate } from '../process-ancestry.js';

const mockIsAgent = vi.mocked(isAgentEnvironment);
const mockGetRepo = vi.mocked(configService.getRepository);
const mockIsOverrideLegitimate = vi.mocked(isOverrideLegitimate);
const mockIsAncestryAvailable = vi.mocked(isAncestryVerificationAvailable);
const mockAuditLog = vi.mocked(auditLog);

const GRAND: RepositoryConfig = { repositoryGuid: 'abc-123' };
const FORK: RepositoryConfig = { repositoryGuid: 'def-456', grandGuid: 'abc-123' };

/** term connect: grand-guarded, not destructive, so an opt-in alone clears it. */
const connect = (ref: string) => enforceResolvedTarget(CMD.TERM_CONNECT, { ref });
/** backup restore: grand-guarded and destructive, so an agent is asked to confirm. */
const restore = (ref: string) => enforceResolvedTarget(CMD.BACKUP_RESTORE, { ref });

/** The decision code a refusal carries first in its details. */
async function refusalCode(run: Promise<void>): Promise<unknown> {
  const error = await run.catch((e: unknown) => e);
  expect(error).toBeInstanceOf(CliExitError);
  return (error as CliExitError).details?.[0];
}

beforeEach(() => {
  vi.clearAllMocks();
  state.config = undefined;
  state.fileExists = true;
  state.adapter = null;
  mockIsOverrideLegitimate.mockReturnValue(true);
  mockIsAncestryAvailable.mockReturnValue(true);
  setConfirmGrand(undefined);
  delete process.env.REDIACC_ALLOW_GRAND_REPO;
  delete process.env.REDIACC_ALLOW_CLUSTER_OPS;
});

afterEach(() => {
  setConfirmGrand(undefined);
  delete process.env.REDIACC_ALLOW_GRAND_REPO;
  delete process.env.REDIACC_ALLOW_CLUSTER_OPS;
});

describe('a human', () => {
  beforeEach(() => mockIsAgent.mockReturnValue(false));

  it('with no policy is allowed without resolving the target (an owner may run anything)', async () => {
    await expect(connect('mail')).resolves.toBeUndefined();
    expect(mockGetRepo).not.toHaveBeenCalled();
  });

  it('with no config file yet is judged with no policy', async () => {
    state.fileExists = false;
    await expect(connect('mail')).resolves.toBeUndefined();
  });

  it('is refused by a local-file policy that denies the command (D19, D24)', async () => {
    state.config = {
      policy: { version: 1, defaults: { commands: { allow: ['*'], deny: ['term connect'] } } },
    };
    mockGetRepo.mockResolvedValue(FORK);
    const error = await connect('mail').catch((e: unknown) => e);
    expect((error as CliExitError).details?.[0]).toBe('POLICY_DENIED');
    expect((error as Error).message).toContain('errors.agent.policyDenied');
  });

  it('is refused a grand by a local-file policy that leaves allowGrandRepos unset', async () => {
    state.config = { policy: { version: 1, defaults: { commands: { allow: ['*'] } } } };
    mockGetRepo.mockResolvedValue(GRAND);
    expect(await refusalCode(connect('mail'))).toBe('GRAND_REPO_DENIED');
  });

  it('control: a local-file policy that allows grand repos lets the human through, no opt-in asked', async () => {
    state.config = {
      policy: { version: 1, defaults: { commands: { allow: ['*'] }, allowGrandRepos: true } },
    };
    mockGetRepo.mockResolvedValue(GRAND);
    await expect(restore('mail')).resolves.toBeUndefined();
  });

  it('refuses a local-file policy whose deny rule names no live command', async () => {
    state.config = {
      policy: { version: 1, defaults: { commands: { allow: ['*'], deny: ['repo vanished'] } } },
    };
    await expect(connect('mail')).rejects.toThrow('repo vanished');
  });
});

describe('a remote config, judged as the session names its member (D2)', () => {
  const REMOTE = { remote: { storeId: 's', configId: 'c' } };
  /** An org with no policy document: the missing-policy default decides by role. */
  const NO_ORG_POLICY = { locked: [], ignoredLocked: [] };

  /** A fresh adapter whose session answers `principal` and `policy` (one per test: the session is memoized per adapter). */
  function session(principal: { orgRole: string; userEmail: string }, policy: unknown) {
    const policyContext = vi.fn(() => Promise.resolve({ principal, policy }));
    state.adapter = { policyContext };
    return policyContext;
  }

  beforeEach(() => {
    state.config = REMOTE;
    mockGetRepo.mockResolvedValue(FORK);
  });

  it('refuses a human member what the missing-policy default withholds from members', async () => {
    mockIsAgent.mockReturnValue(false);
    session({ orgRole: 'member', userEmail: 'm@example.com' }, NO_ORG_POLICY);
    expect(await refusalCode(connect('mail:t'))).toBe('POLICY_DENIED');
  });

  it('control: the same command from an owner session is allowed', async () => {
    mockIsAgent.mockReturnValue(false);
    session({ orgRole: 'owner', userEmail: 'o@example.com' }, NO_ORG_POLICY);
    await expect(connect('mail:t')).resolves.toBeUndefined();
  });

  it('refuses an agent acting for a member, even with a grand-repo opt-in', async () => {
    mockIsAgent.mockReturnValue(true);
    process.env.REDIACC_ALLOW_GRAND_REPO = '*';
    session({ orgRole: 'member', userEmail: 'm@example.com' }, NO_ORG_POLICY);
    expect(await refusalCode(connect('mail:t'))).toBe('POLICY_DENIED');
  });

  it("reads the policy's user tier by the session's email", async () => {
    mockIsAgent.mockReturnValue(false);
    const policy = {
      org: {
        version: 1,
        defaults: { commands: { allow: ['*'] } },
        users: { 'm@example.com': { commands: { allow: ['*'], deny: ['term connect'] } } },
      },
      locked: [],
      ignoredLocked: [],
    };
    session({ orgRole: 'member', userEmail: 'm@example.com' }, policy);
    expect(await refusalCode(connect('mail:t'))).toBe('POLICY_DENIED');
    session({ orgRole: 'member', userEmail: 'other@example.com' }, policy);
    await expect(connect('mail:t')).resolves.toBeUndefined();
  });

  it('opens the session once per adapter for a command judged twice', async () => {
    mockIsAgent.mockReturnValue(false);
    const asked = session({ orgRole: 'owner', userEmail: 'o@example.com' }, NO_ORG_POLICY);
    await connect('mail:t');
    await connect('mail:t');
    expect(asked).toHaveBeenCalledTimes(1);
  });

  it('refuses the run when the session cannot be opened (fail closed)', async () => {
    mockIsAgent.mockReturnValue(false);
    state.adapter = { policyContext: () => Promise.reject(new Error('server unreachable')) };
    await expect(connect('mail:t')).rejects.toThrow('server unreachable');
  });

  it('leaves an enrollment command unjudged when the session cannot be opened', async () => {
    mockIsAgent.mockReturnValue(true);
    state.adapter = { policyContext: () => Promise.reject(new Error('token expired')) };
    await expect(
      enforceRootCommand('config remote reenroll', undefined, {} as Command)
    ).resolves.toBeUndefined();
  });
});

describe('an agent on a grand-guarded command', () => {
  beforeEach(() => mockIsAgent.mockReturnValue(true));

  it('is refused a grand with no opt-in, with the fork-first message', async () => {
    mockGetRepo.mockResolvedValue(GRAND);
    const error = await connect('mail').catch((e: unknown) => e);
    expect((error as CliExitError).details?.[0]).toBe('AGENT_OPT_IN_MISSING');
    expect((error as Error).message).toBe('errors.agent.grandGuard:{"name":"mail"}');
  });

  it('is let through on a fork', async () => {
    mockGetRepo.mockResolvedValue(FORK);
    await expect(connect('mail:t')).resolves.toBeUndefined();
  });

  it('is refused a repo the config does not name: unresolved counts as grand (fail closed)', async () => {
    mockGetRepo.mockResolvedValue(undefined);
    expect(await refusalCode(connect('nothere'))).toBe('AGENT_OPT_IN_MISSING');
  });

  it.each([
    ['*', 'mail'],
    ['mail', 'mail'],
    ['web,mail,db', 'mail'],
    [' web , mail ', 'mail'],
    ['web,*', 'mail'],
  ])('honours REDIACC_ALLOW_GRAND_REPO=%j for %s', async (value, ref) => {
    process.env.REDIACC_ALLOW_GRAND_REPO = value;
    mockGetRepo.mockResolvedValue(GRAND);
    await expect(connect(ref)).resolves.toBeUndefined();
  });

  it.each([
    ['web', 'mail'],
    ['web,db', 'mail'],
    ['Mail', 'mail'],
  ])('refuses with REDIACC_ALLOW_GRAND_REPO=%j for %s', async (value, ref) => {
    process.env.REDIACC_ALLOW_GRAND_REPO = value;
    mockGetRepo.mockResolvedValue(GRAND);
    expect(await refusalCode(connect(ref))).toBe('AGENT_OPT_IN_MISSING');
  });

  it('names an opt-in the agent set itself', async () => {
    process.env.REDIACC_ALLOW_GRAND_REPO = 'mail';
    mockIsOverrideLegitimate.mockReturnValue(false);
    mockGetRepo.mockResolvedValue(GRAND);
    await expect(connect('mail')).rejects.toThrow('errors.agent.grandGuardOverride:');
  });

  it('names an opt-in whose origin cannot be verified on this platform', async () => {
    process.env.REDIACC_ALLOW_GRAND_REPO = 'mail';
    mockIsOverrideLegitimate.mockReturnValue(false);
    mockIsAncestryAvailable.mockReturnValue(false);
    mockGetRepo.mockResolvedValue(GRAND);
    await expect(connect('mail')).rejects.toThrow('errors.agent.grandGuardOverrideNonLinux:');
  });

  it('is asked to confirm a destructive command on a grand even with the opt-in (D21)', async () => {
    process.env.REDIACC_ALLOW_GRAND_REPO = 'mail';
    mockGetRepo.mockResolvedValue(GRAND);
    const error = await restore('mail').catch((e: unknown) => e);
    expect((error as CliExitError).details?.[0]).toBe('CONFIRMATION_REQUIRED');
    expect((error as Error).message).toContain('errors.agent.confirmationRequired:');
    expect((error as Error).message).toContain('"value":"mail"');
  });

  it('control: --confirm-grand naming the repo confirms it', async () => {
    process.env.REDIACC_ALLOW_GRAND_REPO = 'mail';
    mockGetRepo.mockResolvedValue(GRAND);
    setConfirmGrand('mail');
    await expect(restore('mail')).resolves.toBeUndefined();
  });

  it('a --confirm-grand naming another repo confirms nothing', async () => {
    process.env.REDIACC_ALLOW_GRAND_REPO = 'mail';
    mockGetRepo.mockResolvedValue(GRAND);
    setConfirmGrand('web');
    expect(await refusalCode(restore('mail'))).toBe('CONFIRMATION_REQUIRED');
  });

  it('a --confirm-grand does not stand in for the opt-in', async () => {
    mockGetRepo.mockResolvedValue(GRAND);
    setConfirmGrand('mail');
    expect(await refusalCode(restore('mail'))).toBe('AGENT_OPT_IN_MISSING');
  });
});

describe('ops VM exemption (operator ruling 2026-10-15)', () => {
  const config = {
    resources: {
      machines: {
        'ops-worker': { ip: '192.168.111.11', user: 'muhammed' },
        'ops-worker-prod': { ip: '203.0.113.7', user: 'root' },
        'edge-112': { ip: '192.168.112.11', user: 'muhammed' },
      },
      datastores: { 'ops-pool': {} },
    },
    state: { datastores: { 'ops-pool': { attachedTo: 'ops-worker' } } },
  };
  const grandOn = (placement: RepositoryConfig['placement']): RepositoryConfig => ({
    repositoryGuid: 'abc-123',
    placement,
  });

  beforeEach(() => {
    mockIsAgent.mockReturnValue(true);
    state.config = config;
  });

  it('allows a grand-guarded change to a grand placed on an ops VM', async () => {
    mockGetRepo.mockResolvedValue(grandOn({ machine: 'ops-worker' }));
    await expect(connect('vmcheck-base')).resolves.toBeUndefined();
    await expect(restore('vmcheck-base')).resolves.toBeUndefined();
  });

  it('allows a grand on a datastore attached to an ops VM', async () => {
    mockGetRepo.mockResolvedValue(grandOn({ datastore: 'ops-pool' }));
    await expect(connect('vmcheck-base')).resolves.toBeUndefined();
  });

  it('still refuses an ops-looking machine name on a production address', async () => {
    mockGetRepo.mockResolvedValue(grandOn({ machine: 'ops-worker-prod' }));
    expect(await refusalCode(connect('mail'))).toBe('AGENT_OPT_IN_MISSING');
  });

  it('still refuses an address just outside the ops range', async () => {
    mockGetRepo.mockResolvedValue(grandOn({ machine: 'edge-112' }));
    expect(await refusalCode(connect('mail'))).toBe('AGENT_OPT_IN_MISSING');
  });

  it('still refuses a grand with no recorded placement', async () => {
    mockGetRepo.mockResolvedValue(grandOn(undefined));
    expect(await refusalCode(connect('mail'))).toBe('AGENT_OPT_IN_MISSING');
  });
});

describe('repo admin orphan delete: the machine marker decides grand or fork', () => {
  const GUID = '260f0a05-1111-4222-8333-444455556666';
  const orphan = (machine: string, isFork: boolean) =>
    enforceResolvedTarget(CMD.REPO_ADMIN_ORPHAN_DELETE, {
      machine,
      identified: { name: GUID, state: isFork ? 'fork' : 'grand' },
    });
  const machines = (ip: string) => {
    state.config = { resources: { machines: { box: { ip } } } };
  };

  beforeEach(() => mockIsAgent.mockReturnValue(true));

  it('lets an agent delete an orphan the machine marks as a fork', async () => {
    machines('203.0.113.7');
    await expect(orphan('box', true)).resolves.toBeUndefined();
    expect(mockGetRepo).not.toHaveBeenCalled();
  });

  it('lets an agent delete a non-fork orphan on a machine inside the ops fleet network', async () => {
    machines('192.168.111.11');
    await expect(orphan('box', false)).resolves.toBeUndefined();
  });

  it('refuses the same delete on a machine outside the ops fleet network', async () => {
    machines('203.0.113.7');
    await expect(orphan('box', false)).rejects.toThrow('errors.agent.grandGuard');
  });

  it('control: the opt-in naming the GUID lets it through', async () => {
    machines('203.0.113.7');
    process.env.REDIACC_ALLOW_GRAND_REPO = GUID;
    await expect(orphan('box', false)).resolves.toBeUndefined();
  });
});

describe('cluster operations (REDIACC_ALLOW_CLUSTER_OPS)', () => {
  const join = (cluster: string | undefined) =>
    enforceResolvedTarget(CMD.CLUSTER_JOIN, cluster ? { subject: cluster } : {});

  beforeEach(() => mockIsAgent.mockReturnValue(true));

  it('refuses an agent with no cluster opt-in', async () => {
    await expect(join('prod')).rejects.toThrow('errors.agent.clusterOpBlocked');
  });

  it('allows a named cluster and audits the honoured opt-in', async () => {
    process.env.REDIACC_ALLOW_CLUSTER_OPS = 'prod';
    await expect(join('prod')).resolves.toBeUndefined();
    expect(mockAuditLog).toHaveBeenCalledOnce();
    expect(mockAuditLog.mock.calls[0]?.[1]).toMatchObject({
      command: 'cluster join',
      paths: ['prod'],
      outcome: 'ok',
    });
  });

  it('a name-list opt-in does not unlock a different cluster', async () => {
    process.env.REDIACC_ALLOW_CLUSTER_OPS = 'staging';
    await expect(join('prod')).rejects.toThrow('errors.agent.clusterOpBlocked');
    expect(mockAuditLog).not.toHaveBeenCalled();
  });

  it('a named opt-in does not cover a command that names no cluster; `*` does', async () => {
    process.env.REDIACC_ALLOW_CLUSTER_OPS = 'prod';
    await expect(join(undefined)).rejects.toThrow('errors.agent.clusterOpBlocked');
    process.env.REDIACC_ALLOW_CLUSTER_OPS = '*';
    await expect(join(undefined)).resolves.toBeUndefined();
  });

  it('refuses an opt-in the agent set itself', async () => {
    process.env.REDIACC_ALLOW_CLUSTER_OPS = '*';
    mockIsOverrideLegitimate.mockReturnValue(false);
    await expect(join('prod')).rejects.toThrow('errors.agent.clusterOpBlocked');
  });

  it('judges cluster rehearse as cluster fork', async () => {
    const rehearse = () => enforceResolvedTarget('cluster rehearse', { subject: 'prod' });
    await expect(rehearse()).rejects.toThrow(
      'errors.agent.clusterOpBlocked:{"command":"cluster fork"}'
    );
    process.env.REDIACC_ALLOW_CLUSTER_OPS = 'prod';
    await expect(rehearse()).resolves.toBeUndefined();
  });

  it('control: a human runs a cluster operation with no opt-in', async () => {
    mockIsAgent.mockReturnValue(false);
    await expect(join('prod')).resolves.toBeUndefined();
  });
});

describe('enforceResolvedTarget boundaries', () => {
  it('refuses a command the root hook judges (not on ACTION_RESOLVED_TARGETS)', async () => {
    mockIsAgent.mockReturnValue(false);
    await expect(enforceResolvedTarget(CMD.REPO_UP, { ref: 'mail' })).rejects.toThrow(
      'judged by the root hook'
    );
  });

  it('judges nothing inside an executor request (the executor already did)', async () => {
    mockIsAgent.mockReturnValue(true);
    mockGetRepo.mockResolvedValue(GRAND);
    const inRequest = runInRequestContext(
      {
        output: createOutputState(),
        stdout: [],
        stderr: [],
        config: createRequestConfigScope({} as never),
      },
      () => connect('mail')
    );
    await expect(inRequest).resolves.toBeUndefined();
    expect(mockGetRepo).not.toHaveBeenCalled();
  });

  it('every listed command carries a reason, and every judgedAs names a guarded command', () => {
    for (const [path, { reason, judgedAs }] of ACTION_RESOLVED_TARGETS) {
      expect(reason.length, path).toBeGreaterThan(10);
      if (judgedAs) expect(COMMAND_POLICIES.has(judgedAs as never), path).toBe(true);
    }
  });
});

describe('validateRemotePath', () => {
  it('accepts valid relative paths', () => {
    expect(() => validateRemotePath('data')).not.toThrow();
    expect(() => validateRemotePath('data/sub')).not.toThrow();
    expect(() => validateRemotePath('./data')).not.toThrow();
  });

  it('rejects ../ traversal', () => {
    expect(() => validateRemotePath('../etc')).toThrow('errors.sync.pathTraversalBlocked');
    expect(() => validateRemotePath('data/../../etc')).toThrow('errors.sync.pathTraversalBlocked');
  });

  it('rejects absolute paths', () => {
    expect(() => validateRemotePath('/etc/passwd')).toThrow('errors.sync.absolutePathBlocked');
  });
});

describe('policy consistency', () => {
  it('every forkBlocked entry also has grandGuard', () => {
    for (const [cmd, policy] of COMMAND_POLICIES) {
      if (policy.forkBlocked) {
        expect(policy.grandGuard, `${cmd} is forkBlocked but not grandGuard`).toBe(true);
      }
    }
  });

  it('all CMD values are unique', () => {
    const values = Object.values(CMD);
    expect(new Set(values).size).toBe(values.length);
  });

  it('every CMD value has a policy entry', () => {
    for (const [key, value] of Object.entries(CMD)) {
      expect(COMMAND_POLICIES.has(value), `${key} (${value}) missing from COMMAND_POLICIES`).toBe(
        true
      );
    }
  });
});
