import { describe, expect, it } from 'vitest';
import { evaluatePolicy, type PolicyContext } from '../evaluate.js';
import { evaluateEffectivePolicy, mergePolicies } from '../merge.js';
import {
  POLICY_RULE_KEYS,
  type PolicyDocument,
  PolicyDocumentSchema,
  type PolicyRule,
  PolicyRuleSchema,
} from '../schema.js';

const ctx = (overrides: Partial<PolicyContext> = {}): PolicyContext => ({
  userEmail: 'dev@example.com',
  orgRole: 'member',
  commandPath: 'repo up',
  ...overrides,
});

const doc = (d: Omit<PolicyDocument, 'version'>): PolicyDocument => ({ version: 1, ...d });
const allowAll: PolicyRule = { commands: { allow: ['*'] } };

const decide = (org: PolicyDocument | undefined, team: PolicyDocument | undefined, c = ctx()) =>
  evaluateEffectivePolicy(mergePolicies(org, team), c).allowed;

describe('allowGrandRepos glob list', () => {
  const grand = (allowGrandRepos: PolicyRule['allowGrandRepos'], repoName: string) =>
    evaluatePolicy(
      doc({ defaults: { ...allowAll, allowGrandRepos } }),
      ctx({ isGrandRepo: true, repoName })
    ).allowed;

  it('true admits every grand repo, like ["*"]', () => {
    expect(grand(true, 'mail')).toBe(true);
    expect(grand(['*'], 'mail')).toBe(true);
  });

  it('a list admits only the repos a glob matches', () => {
    expect(grand(['web-*', 'mail'], 'web-eu')).toBe(true);
    expect(grand(['web-*', 'mail'], 'mail')).toBe(true);
    expect(grand(['web-*', 'mail'], 'gitlab')).toBe(false);
  });

  it('false, an empty list and omission admit none', () => {
    expect(grand(false, 'mail')).toBe(false);
    expect(grand([], 'mail')).toBe(false);
    expect(grand(undefined, 'mail')).toBe(false);
  });

  it('the schema accepts a boolean or a list of non-empty globs, nothing else', () => {
    expect(PolicyRuleSchema.safeParse({ allowGrandRepos: ['web-*'] }).success).toBe(true);
    expect(PolicyRuleSchema.safeParse({ allowGrandRepos: true }).success).toBe(true);
    expect(PolicyRuleSchema.safeParse({ allowGrandRepos: [''] }).success).toBe(false);
    expect(PolicyRuleSchema.safeParse({ allowGrandRepos: 'web-*' }).success).toBe(false);
  });
});

describe('locked keys in the schema', () => {
  it('names every rule key and only rule keys', () => {
    const byName = (a: string, b: string) => a.localeCompare(b);
    const ruleKeys = Object.keys(PolicyRuleSchema.shape).sort(byName);
    expect([...POLICY_RULE_KEYS].sort(byName)).toEqual(ruleKeys);
    expect(
      PolicyDocumentSchema.safeParse({ version: 1, defaults: {}, locked: ['allowGrandRepos'] })
        .success
    ).toBe(true);
    expect(
      PolicyDocumentSchema.safeParse({ version: 1, defaults: {}, locked: ['teams'] }).success
    ).toBe(false);
  });
});

describe('mergePolicies: the team policy narrows within the org ceiling', () => {
  // Each row: what the org allows, what the team allows, the request, the effective answer.
  const rows: [
    string,
    PolicyDocument | undefined,
    PolicyDocument | undefined,
    PolicyContext,
    boolean,
  ][] = [
    // Allow lists intersect.
    [
      'both allow the command',
      doc({ defaults: allowAll }),
      doc({ defaults: { commands: { allow: ['repo *'] } } }),
      ctx(),
      true,
    ],
    [
      'team allow list excludes it',
      doc({ defaults: allowAll }),
      doc({ defaults: { commands: { allow: ['machine *'] } } }),
      ctx(),
      false,
    ],
    [
      'org allow list excludes it, team allows all',
      doc({ defaults: { commands: { allow: ['machine *'] } } }),
      doc({ defaults: allowAll }),
      ctx(),
      false,
    ],
    // Deny lists union.
    [
      'team denies it',
      doc({ defaults: allowAll }),
      doc({ defaults: { commands: { allow: ['*'], deny: ['repo up'] } } }),
      ctx(),
      false,
    ],
    [
      'org denies it, team allows it',
      doc({ defaults: { commands: { allow: ['*'], deny: ['repo up'] } } }),
      doc({ defaults: allowAll }),
      ctx(),
      false,
    ],
    // Machines and repos intersect.
    [
      'machine in both',
      doc({ defaults: { ...allowAll, machines: ['prod-*'] } }),
      doc({ defaults: { machines: ['*-eu'] } }),
      ctx({ machineName: 'prod-eu' }),
      true,
    ],
    [
      'machine only in org',
      doc({ defaults: { ...allowAll, machines: ['prod-*'] } }),
      doc({ defaults: { machines: ['*-eu'] } }),
      ctx({ machineName: 'prod-us' }),
      false,
    ],
    [
      'machine only in team',
      doc({ defaults: { ...allowAll, machines: ['prod-*'] } }),
      doc({ defaults: { machines: ['*'] } }),
      ctx({ machineName: 'dev-eu' }),
      false,
    ],
    [
      'repo outside team list',
      doc({ defaults: allowAll }),
      doc({ defaults: { repos: ['web'] } }),
      ctx({ repoName: 'mail' }),
      false,
    ],
    // Booleans AND.
    [
      'cluster ops: org yes, team no',
      doc({ defaults: { ...allowAll, allowClusterOps: true } }),
      doc({ defaults: { allowClusterOps: false } }),
      ctx({ commandPath: 'cluster destroy' }),
      false,
    ],
    [
      'cluster ops: org no, team yes',
      doc({ defaults: allowAll }),
      doc({ defaults: { allowClusterOps: true } }),
      ctx({ commandPath: 'cluster destroy' }),
      false,
    ],
    [
      'cluster ops: org yes, team silent',
      doc({ defaults: { ...allowAll, allowClusterOps: true } }),
      doc({ defaults: allowAll }),
      ctx({ commandPath: 'cluster destroy' }),
      true,
    ],
    // Grand-repo globs combine as "org allows AND team allows".
    [
      'grand: org list and team list both match',
      doc({ defaults: { ...allowAll, allowGrandRepos: ['web-*'] } }),
      doc({ defaults: { allowGrandRepos: ['*-eu'] } }),
      ctx({ isGrandRepo: true, repoName: 'web-eu' }),
      true,
    ],
    [
      'grand: only org glob matches',
      doc({ defaults: { ...allowAll, allowGrandRepos: ['web-*'] } }),
      doc({ defaults: { allowGrandRepos: ['*-eu'] } }),
      ctx({ isGrandRepo: true, repoName: 'web-us' }),
      false,
    ],
    [
      'grand: team true cannot widen org list',
      doc({ defaults: { ...allowAll, allowGrandRepos: ['web-*'] } }),
      doc({ defaults: { allowGrandRepos: true } }),
      ctx({ isGrandRepo: true, repoName: 'mail' }),
      false,
    ],
    [
      'grand: team list narrows org true',
      doc({ defaults: { ...allowAll, allowGrandRepos: true } }),
      doc({ defaults: { allowGrandRepos: ['web-*'] } }),
      ctx({ isGrandRepo: true, repoName: 'mail' }),
      false,
    ],
    [
      'grand: org true, team silent',
      doc({ defaults: { ...allowAll, allowGrandRepos: true } }),
      doc({ defaults: allowAll }),
      ctx({ isGrandRepo: true, repoName: 'mail' }),
      true,
    ],
    // Mutation scopes intersect.
    [
      'mutation scope outside team list',
      doc({ defaults: allowAll }),
      doc({ defaults: { mutationScopes: ['backup'] } }),
      ctx({ mutationScope: 'infra' }),
      false,
    ],
    // The team policy's own tiers narrow too.
    [
      'team users tier narrows one user',
      doc({ defaults: allowAll }),
      doc({
        defaults: allowAll,
        users: { 'dev@example.com': { commands: { allow: ['machine *'] } } },
      }),
      ctx(),
      false,
    ],
    // No org policy: the missing-policy default is the ceiling, and a team cannot grant past it.
    [
      'no org policy, member, team allows all',
      undefined,
      doc({ defaults: allowAll }),
      ctx(),
      false,
    ],
    [
      'no org policy, admin, team allows all',
      undefined,
      doc({ defaults: allowAll }),
      ctx({ orgRole: 'admin' }),
      true,
    ],
    [
      'no org policy, admin, team denies',
      undefined,
      doc({ defaults: { commands: { allow: ['machine *'] } } }),
      ctx({ orgRole: 'admin' }),
      false,
    ],
    // The org-level config: no team policy, the org policy alone.
    ['org-level config', doc({ defaults: allowAll }), undefined, ctx(), true],
  ];

  it.each(rows)('%s', (_label, org, team, c, allowed) => {
    expect(decide(org, team, c)).toBe(allowed);
  });

  it('never allows what the org policy alone denies (ceiling property over the table)', () => {
    for (const [label, org, team, c] of rows) {
      if (!evaluatePolicy(org, c).allowed) {
        expect(decide(org, team, c), label).toBe(false);
      }
    }
  });
});

describe('mergePolicies: locked keys', () => {
  const org = doc({
    defaults: { ...allowAll, allowGrandRepos: ['web-*'], machines: ['prod-*'] },
    locked: ['allowGrandRepos', 'machines'],
  });

  it('ignores a locked key the team sets, at every tier, and reports each row', () => {
    const team = doc({
      defaults: { allowGrandRepos: false, commands: { allow: ['*'] } },
      teams: { ops: { machines: ['dev-*'] } },
      users: { 'dev@example.com': { allowGrandRepos: [] } },
    });
    const effective = mergePolicies(org, team);
    expect(effective.ignoredLocked).toEqual([
      'defaults.allowGrandRepos',
      'teams.ops.machines',
      'users.dev@example.com.allowGrandRepos',
    ]);
    // The team's `allowGrandRepos: false` is ignored: the org's glob list decides.
    expect(
      evaluateEffectivePolicy(effective, ctx({ isGrandRepo: true, repoName: 'web-eu' })).allowed
    ).toBe(true);
    // The team's machines list is ignored too: prod-eu stays allowed for a member of team "ops".
    expect(
      evaluateEffectivePolicy(effective, ctx({ teamSlug: 'ops', machineName: 'prod-eu' })).allowed
    ).toBe(true);
    // The team policy as stored is kept whole for the editor.
    expect(effective.team).toBe(team);
  });

  it('control: the same team keys narrow when the org does not lock them', () => {
    const unlocked = doc({ defaults: org.defaults });
    const team = doc({ defaults: { allowGrandRepos: false } });
    const effective = mergePolicies(unlocked, team);
    expect(effective.ignoredLocked).toEqual([]);
    expect(
      evaluateEffectivePolicy(effective, ctx({ isGrandRepo: true, repoName: 'web-eu' })).allowed
    ).toBe(false);
  });

  it('a locked key still cannot widen: the org ceiling holds regardless', () => {
    const team = doc({ defaults: { allowGrandRepos: true } });
    expect(
      evaluateEffectivePolicy(
        mergePolicies(org, team),
        ctx({ isGrandRepo: true, repoName: 'mail' })
      ).allowed
    ).toBe(false);
  });

  it('reports a lock list inside the team policy and gives it no effect', () => {
    const team = doc({ defaults: {}, locked: ['commands'] });
    const effective = mergePolicies(doc({ defaults: allowAll }), team);
    expect(effective.ignoredLocked).toEqual(['locked']);
    expect(effective.locked).toEqual([]);
  });
});
