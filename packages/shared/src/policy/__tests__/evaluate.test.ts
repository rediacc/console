import { describe, expect, it } from 'vitest';
import {
  evaluatePolicy,
  MISSING_POLICY_DEFAULT,
  matchesGlob,
  type PolicyContext,
} from '../evaluate.js';
import { type PolicyDocument, PolicyDocumentSchema } from '../schema.js';

/** A context with the required fields filled in; override what a case cares about. */
const ctx = (overrides: Partial<PolicyContext> = {}): PolicyContext => ({
  userEmail: 'dev@example.com',
  orgRole: 'member',
  commandPath: 'repo up',
  ...overrides,
});

const doc = (d: Omit<PolicyDocument, 'version'>): PolicyDocument => ({ version: 1, ...d });

describe('matchesGlob', () => {
  it('matches an exact path literally', () => {
    expect(matchesGlob('repo fork', 'repo fork')).toBe(true);
    expect(matchesGlob('repo fork', 'repo up')).toBe(false);
  });

  it('does not let a literal space act as a wildcard', () => {
    // Regression: an escaping scheme that reuses the space as the wildcard
    // sentinel turns "repo fork" into /^repo.*fork$/ and matches this.
    expect(matchesGlob('repo fork', 'repoXXXfork')).toBe(false);
  });

  it('spans segments with *', () => {
    expect(matchesGlob('repo *', 'repo fork')).toBe(true);
    expect(matchesGlob('repo *', 'repo secret set')).toBe(true);
    expect(matchesGlob('repo *', 'machine query')).toBe(false);
  });

  it('does not match the bare prefix when the pattern requires a subcommand', () => {
    expect(matchesGlob('repo *', 'repo')).toBe(false);
  });

  it('matches everything with a lone *', () => {
    expect(matchesGlob('*', 'repo up')).toBe(true);
    expect(matchesGlob('*', 'cluster destroy')).toBe(true);
  });

  it('supports a trailing wildcard on names', () => {
    expect(matchesGlob('prod-*', 'prod-1')).toBe(true);
    expect(matchesGlob('prod-*', 'staging-1')).toBe(false);
  });

  it('supports a leading wildcard', () => {
    expect(matchesGlob('* list', 'repo list')).toBe(true);
    expect(matchesGlob('* list', 'machine list')).toBe(true);
    expect(matchesGlob('* list', 'repo up')).toBe(false);
  });

  it('treats regex metacharacters in a pattern as literals', () => {
    expect(matchesGlob('repo.fork', 'repo.fork')).toBe(true);
    expect(matchesGlob('repo.fork', 'repoXfork')).toBe(false);
  });
});

describe('evaluatePolicy — missing document', () => {
  it('allows owners and admins', () => {
    expect(evaluatePolicy(undefined, ctx({ orgRole: 'owner' })).allowed).toBe(true);
    expect(evaluatePolicy(undefined, ctx({ orgRole: 'admin' })).allowed).toBe(true);
  });

  it('denies members', () => {
    const decision = evaluatePolicy(undefined, ctx({ orgRole: 'member' }));
    expect(decision.allowed).toBe(false);
    expect(decision.reason).toMatch(/No policy is configured/);
  });

  it('matches the exported constant the UI reads', () => {
    expect(MISSING_POLICY_DEFAULT).toEqual({ owner: true, admin: true, member: false });
    for (const role of ['owner', 'admin', 'member'] as const) {
      expect(evaluatePolicy(undefined, ctx({ orgRole: role })).allowed).toBe(
        MISSING_POLICY_DEFAULT[role]
      );
    }
  });
});

describe('evaluatePolicy — commands', () => {
  it('allows a command matching the defaults allow-list', () => {
    const d = doc({ defaults: { commands: { allow: ['repo *'] } } });
    expect(evaluatePolicy(d, ctx({ commandPath: 'repo up' })).allowed).toBe(true);
  });

  it('denies a command outside the allow-list', () => {
    const d = doc({ defaults: { commands: { allow: ['repo *'] } } });
    const decision = evaluatePolicy(d, ctx({ commandPath: 'machine deprovision' }));
    expect(decision.allowed).toBe(false);
    expect(decision.reason).toMatch(/does not allow/);
  });

  it('fails CLOSED when a document defines no commands rule (the footgun)', () => {
    // A present document that allow-lists no commands must grant nothing, not
    // everything. A reviewer flagged the old allow-all behavior: an admin who
    // scopes machines but forgets commands would otherwise hand out every verb.
    const d = doc({ defaults: {} });
    const decision = evaluatePolicy(d, ctx({ commandPath: 'machine deprovision' }));
    expect(decision.allowed).toBe(false);
    expect(decision.reason).toMatch(/allow-lists no commands/);
  });

  it('denies even an owner when a document allow-lists no commands', () => {
    // Under a document, the allow-list binds everyone (deny already outranks all
    // tiers, including owners). An empty allow-list is an empty grant for all.
    const d = doc({ defaults: { machines: ['*'] } });
    expect(evaluatePolicy(d, ctx({ commandPath: 'repo delete', orgRole: 'owner' })).allowed).toBe(
      false
    );
  });

  it('an author who wants everything must say so explicitly with ["*"]', () => {
    const d = doc({ defaults: { commands: { allow: ['*'] }, machines: ['prod-*'] } });
    expect(
      evaluatePolicy(d, ctx({ commandPath: 'machine deprovision', machineName: 'prod-1' })).allowed
    ).toBe(true);
  });

  it('lets deny outrank a matching allow in the same tier', () => {
    const d = doc({ defaults: { commands: { allow: ['repo *'], deny: ['repo delete'] } } });
    expect(evaluatePolicy(d, ctx({ commandPath: 'repo up' })).allowed).toBe(true);
    const decision = evaluatePolicy(d, ctx({ commandPath: 'repo delete' }));
    expect(decision.allowed).toBe(false);
    expect(decision.reason).toMatch(/explicitly denies/);
  });
});

describe('evaluatePolicy — precedence', () => {
  const base = {
    defaults: { commands: { allow: ['repo list'] } },
    teams: { platform: { commands: { allow: ['repo *'] } } },
    users: { 'dev@example.com': { commands: { allow: ['*'] } } },
  };

  it('prefers the user rule over team and defaults', () => {
    const d = doc(base);
    expect(
      evaluatePolicy(d, ctx({ commandPath: 'cluster scale', teamSlug: 'platform' })).allowed
    ).toBe(false); // cluster ops still need allowClusterOps
    expect(
      evaluatePolicy(d, ctx({ commandPath: 'machine query', teamSlug: 'platform' })).allowed
    ).toBe(true); // '*' from the user rule
  });

  it('prefers the team rule over defaults when no user rule exists', () => {
    const d = doc(base);
    const other = ctx({ userEmail: 'other@example.com', teamSlug: 'platform' });
    // 'repo up' is allowed by the team's 'repo *', not by the defaults' 'repo list'.
    expect(evaluatePolicy(d, { ...other, commandPath: 'repo up' }).allowed).toBe(true);
    expect(evaluatePolicy(d, { ...other, commandPath: 'machine query' }).allowed).toBe(false);
  });

  it('falls back to defaults when neither team nor user matches', () => {
    const d = doc(base);
    const stranger = ctx({ userEmail: 'stranger@example.com' });
    expect(evaluatePolicy(d, { ...stranger, commandPath: 'repo list' }).allowed).toBe(true);
    expect(evaluatePolicy(d, { ...stranger, commandPath: 'repo up' }).allowed).toBe(false);
  });

  it('ignores a team rule the caller does not belong to', () => {
    const d = doc(base);
    const noTeam = ctx({ userEmail: 'other@example.com' });
    expect(evaluatePolicy(d, { ...noTeam, commandPath: 'repo up' }).allowed).toBe(false);
  });

  it('lets a deny in defaults survive a permissive user rule', () => {
    const d = doc({
      defaults: { commands: { allow: ['*'], deny: ['cluster destroy'] } },
      users: { 'dev@example.com': { commands: { allow: ['*'] } } },
    });
    // A blanket ban stays a ban: deny wins at any tier.
    expect(evaluatePolicy(d, ctx({ commandPath: 'cluster destroy' })).allowed).toBe(false);
  });

  it('refines one dimension in a user rule without restating the others', () => {
    const d = doc({
      defaults: { commands: { allow: ['*'] }, machines: ['prod-*'] },
      users: { 'dev@example.com': { machines: ['staging-*'] } },
    });
    // The user rule overrides machines only; commands still come from defaults.
    expect(
      evaluatePolicy(d, ctx({ commandPath: 'repo up', machineName: 'staging-1' })).allowed
    ).toBe(true);
    expect(evaluatePolicy(d, ctx({ commandPath: 'repo up', machineName: 'prod-1' })).allowed).toBe(
      false
    );
  });
});

describe('evaluatePolicy — machine and repo scoping', () => {
  const d = doc({
    defaults: { commands: { allow: ['*'] }, machines: ['prod-*'], repos: ['app-*'] },
  });

  it('allows a machine inside the scope', () => {
    expect(evaluatePolicy(d, ctx({ machineName: 'prod-1' })).allowed).toBe(true);
  });

  it('denies a machine outside the scope', () => {
    const decision = evaluatePolicy(d, ctx({ machineName: 'staging-1' }));
    expect(decision.allowed).toBe(false);
    expect(decision.reason).toMatch(/machine "staging-1"/);
  });

  it('denies a repo outside the scope', () => {
    const decision = evaluatePolicy(d, ctx({ machineName: 'prod-1', repoName: 'db-1' }));
    expect(decision.allowed).toBe(false);
    expect(decision.reason).toMatch(/repo "db-1"/);
  });

  it('does not apply machine scoping to a command with no machine', () => {
    expect(evaluatePolicy(d, ctx({ commandPath: 'config show' })).allowed).toBe(true);
  });
});

describe('evaluatePolicy — capability flags', () => {
  it('denies grand-repo operations unless allowGrandRepos is set', () => {
    const d = doc({ defaults: { commands: { allow: ['*'] } } });
    expect(evaluatePolicy(d, ctx({ repoName: 'mail', isGrandRepo: true })).allowed).toBe(false);

    const permissive = doc({ defaults: { commands: { allow: ['*'] }, allowGrandRepos: true } });
    expect(evaluatePolicy(permissive, ctx({ repoName: 'mail', isGrandRepo: true })).allowed).toBe(
      true
    );
  });

  it('denies cluster ops unless allowClusterOps is set, deriving the signal from the path', () => {
    const d = doc({ defaults: { commands: { allow: ['*'] } } });
    const decision = evaluatePolicy(d, ctx({ commandPath: 'cluster destroy' }));
    expect(decision.allowed).toBe(false);
    expect(decision.reason).toMatch(/cluster operations/);

    const permissive = doc({ defaults: { commands: { allow: ['*'] }, allowClusterOps: true } });
    expect(evaluatePolicy(permissive, ctx({ commandPath: 'cluster destroy' })).allowed).toBe(true);
  });

  it('honours an explicit isClusterOp over the path heuristic', () => {
    const d = doc({ defaults: { commands: { allow: ['*'] } } });
    // A command that looks like a cluster op but is declared not to be.
    expect(
      evaluatePolicy(d, ctx({ commandPath: 'cluster list', isClusterOp: false })).allowed
    ).toBe(true);
  });

  it('restricts mutation scopes when the rule lists them', () => {
    const d = doc({ defaults: { commands: { allow: ['*'] }, mutationScopes: ['backup'] } });
    expect(evaluatePolicy(d, ctx({ mutationScope: 'backup' })).allowed).toBe(true);
    const decision = evaluatePolicy(d, ctx({ mutationScope: 'infra' }));
    expect(decision.allowed).toBe(false);
    expect(decision.reason).toMatch(/"infra" mutations/);
  });

  it('leaves mutations unrestricted when no tier lists scopes', () => {
    const d = doc({ defaults: { commands: { allow: ['*'] } } });
    expect(evaluatePolicy(d, ctx({ mutationScope: 'infra' })).allowed).toBe(true);
  });
});

describe('evaluatePolicy — destructive commands', () => {
  it('names the command as destructive in the reason', () => {
    const d = doc({ defaults: { commands: { allow: ['*'], deny: ['repo delete'] } } });
    const decision = evaluatePolicy(d, ctx({ commandPath: 'repo delete', destructive: true }));
    expect(decision.allowed).toBe(false);
    expect(decision.reason).toMatch(/destructive command "repo delete"/);
  });

  it('does not deny a destructive command that policy permits', () => {
    const d = doc({ defaults: { commands: { allow: ['*'] } } });
    expect(evaluatePolicy(d, ctx({ commandPath: 'repo delete', destructive: true })).allowed).toBe(
      true
    );
  });
});

describe('PolicyDocumentSchema', () => {
  it('accepts a full document', () => {
    const parsed = PolicyDocumentSchema.safeParse({
      version: 1,
      defaults: { commands: { allow: ['repo *'], deny: ['repo delete'] } },
      teams: { platform: { machines: ['prod-*'], allowClusterOps: true } },
      users: { 'dev@example.com': { mutationScopes: ['config', 'backup'] } },
    });
    expect(parsed.success).toBe(true);
  });

  it('requires version 1', () => {
    expect(PolicyDocumentSchema.safeParse({ version: 2, defaults: {} }).success).toBe(false);
  });

  it('requires defaults', () => {
    expect(PolicyDocumentSchema.safeParse({ version: 1 }).success).toBe(false);
  });

  it('rejects an unknown mutation scope', () => {
    const parsed = PolicyDocumentSchema.safeParse({
      version: 1,
      defaults: { mutationScopes: ['root'] },
    });
    expect(parsed.success).toBe(false);
  });
});
