/**
 * The executor's enforcement point asks the one decision function (PLAN-rmcp-decide.md D3):
 * authorize() builds `decide`'s context from the verified principal, the contract entry, the
 * resolved target, the effective policy and, for a remote-MCP grant, the grant row's opt-ins.
 *
 * Covered here, below the HTTP route: the grant principal (opt-in AND ceiling, D22/D20), the
 * `needs_confirmation` answer and its retry (`repo delete` is destructive, `repo expand` is not), the cluster-ops refusal that is new on this path
 * (a datastore verb, which the old path-prefix test never classed as a cluster op), the grant row
 * mapping, and the target resolver's `repo promote` and fail-closed cases.
 */

import { getCommand } from '@rediacc/shared/cli-contract';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import type { Decision, DecisionTarget, PolicyDocument } from '@rediacc/shared/policy';
import { describe, expect, it } from 'vitest';
import {
  type AgentGrantOverrides,
  type AuthorizeArgs,
  authorize,
  clusterSubjectOf,
  grantOverrides,
  PolicyDenied,
  resolveExecutorTarget,
} from '../policy.js';
import type { SessionPrincipal } from '../sessions.js';

const OWNER: SessionPrincipal = {
  orgId: 'org-1',
  teamId: null,
  userId: 'user-owner',
  userEmail: 'owner@example.com',
  orgRole: 'owner',
};

const GRAND: DecisionTarget = {
  machine: 'm1',
  repo: { name: 'shop', state: 'grand' },
  isOpsVm: false,
};

function configWith(policy?: PolicyDocument): RdcConfig {
  return {
    schemaVersion: 3,
    id: '00000000-0000-4000-8000-0000000000cc',
    version: 1,
    resources: {
      machines: { m1: { ip: '10.1.1.1', user: 'root', port: 22 } },
      repositories: {
        shop: {
          grand: 'latest',
          placement: { machine: 'm1' },
          tags: {
            latest: { repositoryGuid: '11111111-1111-4111-8111-111111111111' },
            trial: {
              repositoryGuid: '22222222-2222-4222-8222-222222222222',
              grandGuid: '11111111-1111-4111-8111-111111111111',
            },
          },
        },
      },
    },
    encryption: { mode: 'plaintext' },
    ...(policy ? { policy } : {}),
  } as RdcConfig;
}

const GRAND_OK: PolicyDocument = {
  version: 1,
  defaults: { commands: { allow: ['*'] }, allowGrandRepos: true },
};

/** The decision authorize() refused with, or 'allow' when it let the command through. */
function outcome(args: AuthorizeArgs): Decision | 'allow' {
  try {
    authorize(args);
    return 'allow';
  } catch (error) {
    if (error instanceof PolicyDenied) return error.decision;
    throw error;
  }
}

const grantOf = (overrides: Partial<AgentGrantOverrides> = {}): AgentGrantOverrides => ({
  allowGrandRepos: false,
  allowClusterOps: false,
  ...overrides,
});

describe('authorize: a remote-MCP grant principal', () => {
  const base = { principal: OWNER, commandPath: 'repo up', target: GRAND } as const;

  it('allows a human on a grand repo the policy admits (control)', () => {
    expect(outcome({ ...base, config: configWith(GRAND_OK) })).toBe('allow');
  });

  it('refuses an agent whose grant names no grand repo', () => {
    const result = outcome({ ...base, config: configWith(GRAND_OK), agentGrant: grantOf() });
    expect(result).toMatchObject({ verdict: 'deny', code: 'AGENT_OPT_IN_MISSING' });
  });

  it('allows an agent whose grant names the repo for a non-destructive grand change', () => {
    const agentGrant = grantOf({ allowGrandRepos: ['shop'] });
    const args = { ...base, commandPath: 'repo expand', config: configWith(GRAND_OK), agentGrant };
    expect(outcome(args)).toBe('allow');
  });

  it('refuses an agent whose grant names another repo', () => {
    const agentGrant = grantOf({ allowGrandRepos: ['mail'] });
    const result = outcome({ ...base, config: configWith(GRAND_OK), agentGrant });
    expect(result).toMatchObject({ code: 'AGENT_OPT_IN_MISSING' });
  });

  it('keeps the policy ceiling above the grant (D20)', () => {
    const config = configWith({ version: 1, defaults: { commands: { allow: ['repo *'] } } });
    const agentGrant = grantOf({ allowGrandRepos: true });
    expect(outcome({ ...base, config, agentGrant })).toMatchObject({ code: 'GRAND_REPO_DENIED' });
  });

  it('asks a granted agent to confirm a destructive grand change, and allows the confirmed retry', () => {
    const args: AuthorizeArgs = {
      ...base,
      commandPath: 'repo delete',
      config: configWith(GRAND_OK),
      agentGrant: grantOf({ allowGrandRepos: true }),
    };
    expect(outcome(args)).toMatchObject({
      verdict: 'needs_confirmation',
      code: 'CONFIRMATION_REQUIRED',
      next: { confirm: { argument: 'confirm', value: 'shop' } },
    });
    expect(outcome({ ...args, confirmation: { granted: true } })).toBe('allow');
  });
});

describe('authorize: cluster operations on the executor path', () => {
  const datastoreDelete = {
    principal: OWNER,
    commandPath: 'datastore delete',
    target: { subject: 'ds-data', isOpsVm: false },
  } as const;

  it('refuses a datastore lifecycle verb under a policy without allowClusterOps', () => {
    const config = configWith({ version: 1, defaults: { commands: { allow: ['*'] } } });
    expect(outcome({ ...datastoreDelete, config })).toMatchObject({ code: 'CLUSTER_OPS_DENIED' });
  });

  it('allows it for a human once the policy sets allowClusterOps (control)', () => {
    const config = configWith({
      version: 1,
      defaults: { commands: { allow: ['*'] }, allowClusterOps: true },
    });
    expect(outcome({ ...datastoreDelete, config })).toBe('allow');
  });

  it('refuses a granted agent without the cluster switch, allows it with the switch', () => {
    const config = configWith({
      version: 1,
      defaults: { commands: { allow: ['*'] }, allowClusterOps: true },
    });
    expect(outcome({ ...datastoreDelete, config, agentGrant: grantOf() })).toMatchObject({
      code: 'AGENT_OPT_IN_MISSING',
    });
    expect(
      outcome({ ...datastoreDelete, config, agentGrant: grantOf({ allowClusterOps: true }) })
    ).toBe('allow');
  });

  it('reads the subject from the cluster or datastore positional', () => {
    const entry = getCommand('datastore delete');
    const join = getCommand('cluster join');
    if (!entry || !join) throw new Error('contract entries missing');
    expect(clusterSubjectOf(entry, { datastore: 'ds-data' })).toBe('ds-data');
    expect(clusterSubjectOf(join, { machine: 'm1' })).toBeUndefined();
  });
});

describe('authorize: inputs', () => {
  it('treats a grand-guarded command with no resolved target as grand (fail closed)', () => {
    const config = configWith({ version: 1, defaults: { commands: { allow: ['*'] } } });
    const result = outcome({ principal: OWNER, commandPath: 'repo up', config, machineName: 'm1' });
    expect(result).toMatchObject({ code: 'GRAND_REPO_DENIED' });
  });

  it('refuses to authorize a command the contract does not have', () => {
    expect(() =>
      authorize({ principal: OWNER, commandPath: 'repo nosuchverb', config: configWith() })
    ).toThrow(/There is no "rdc repo nosuchverb" command/);
  });
});

describe('grantOverrides', () => {
  it('maps the grant row switches onto the decide overrides', () => {
    expect(grantOverrides(grantOf({ allowGrandRepos: true, allowClusterOps: true }))).toEqual({
      grandRepos: '*',
      clusterOps: '*',
      source: 'grant',
    });
    expect(grantOverrides(grantOf({ allowGrandRepos: ['shop'] }))).toEqual({
      grandRepos: ['shop'],
      clusterOps: null,
      source: 'grant',
    });
  });

  it('grants nothing for false switches or an empty list', () => {
    const none = { grandRepos: null, clusterOps: null, source: 'none' };
    expect(grantOverrides(grantOf())).toEqual(none);
    expect(grantOverrides(grantOf({ allowGrandRepos: [] }))).toEqual(none);
  });
});

describe('resolveExecutorTarget', () => {
  const config = configWith();

  it('resolves a fork and a grand from the request config', async () => {
    const up = getCommand('repo up');
    if (!up) throw new Error('contract entry missing');
    await expect(resolveExecutorTarget(up, { ref: 'shop:trial' }, config)).resolves.toMatchObject({
      repo: { name: 'shop:trial', state: 'fork' },
    });
    await expect(resolveExecutorTarget(up, { ref: 'shop' }, config)).resolves.toMatchObject({
      repo: { name: 'shop', state: 'grand' },
    });
  });

  it('returns a ref the config does not name as unresolved', async () => {
    const up = getCommand('repo up');
    if (!up) throw new Error('contract entry missing');
    await expect(resolveExecutorTarget(up, { ref: 'nosuchrepo' }, config)).resolves.toMatchObject({
      repo: { name: 'nosuchrepo', state: 'unresolved' },
    });
  });

  it('names the grand a promoted fork replaces', async () => {
    const promote = getCommand('repo promote');
    if (!promote) throw new Error('contract entry missing');
    await expect(
      resolveExecutorTarget(promote, { ref: 'shop:trial' }, config)
    ).resolves.toMatchObject({ repo: { name: 'shop', state: 'grand' } });
  });
});
