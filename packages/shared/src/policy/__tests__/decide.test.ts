import { describe, expect, it } from 'vitest';
import table from '../__fixtures__/decision-table.json' with { type: 'json' };
import { type DecisionContext, decide, isClusterLifecycleCommand } from '../decide.js';
import { DECISION_CODES, DECISION_VERDICTS } from '../decision-codes.js';
import { mergePolicies } from '../merge.js';
import { type PolicyDocument, PolicyDocumentSchema } from '../schema.js';

interface FixtureRow {
  id: string;
  note: string;
  principal: DecisionContext['principal'];
  command: DecisionContext['command'];
  target: DecisionContext['target'];
  policy: { org?: unknown; team?: unknown } | null;
  overrides: DecisionContext['overrides'];
  confirmation: DecisionContext['confirmation'];
  expect: { verdict: string; code: string };
}

const rows = table.rows as unknown as FixtureRow[];
const controls = table.controls as unknown as FixtureRow[];

/** Every policy document in the table must be one the schema accepts, or the row tests nothing real. */
function parseDoc(raw: unknown): PolicyDocument | undefined {
  return raw === undefined ? undefined : PolicyDocumentSchema.parse(raw);
}

function toContext(row: FixtureRow): DecisionContext {
  return {
    principal: row.principal,
    command: row.command,
    target: row.target,
    policy: row.policy ? mergePolicies(parseDoc(row.policy.org), parseDoc(row.policy.team)) : null,
    overrides: row.overrides,
    confirmation: row.confirmation,
  };
}

/** The mismatch the harness reports for one row, or null when decide reproduces it. */
function mismatch(row: FixtureRow): string | null {
  const got = decide(toContext(row));
  if (got.verdict === row.expect.verdict && got.code === row.expect.code) return null;
  return `${row.id}: expected ${row.expect.verdict}/${row.expect.code}, got ${got.verdict}/${got.code} (${got.reason})`;
}

describe('decision table', () => {
  it('holds at least 60 rows with unique ids', () => {
    expect(rows.length).toBeGreaterThanOrEqual(60);
    expect(new Set(rows.map((r) => r.id)).size).toBe(rows.length);
  });

  it('exercises every verdict and every code', () => {
    expect(new Set(rows.map((r) => r.expect.verdict))).toEqual(new Set(DECISION_VERDICTS));
    expect(new Set(rows.map((r) => r.expect.code))).toEqual(new Set(DECISION_CODES));
  });

  it.each(rows.map((r) => [r.id, r] as const))('%s', (_id, row) => {
    expect(mismatch(row)).toBeNull();
  });
});

describe('controls', () => {
  it('carries at least one control', () => {
    expect(controls.length).toBeGreaterThan(0);
  });

  // A control's expectation is deliberately wrong. If the harness stopped comparing (or decide stopped deciding), these would pass silently; here they must report a mismatch.
  it.each(controls.map((r) => [r.id, r] as const))('%s is reported as a mismatch', (_id, row) => {
    expect(mismatch(row)).not.toBeNull();
  });
});

describe('decide', () => {
  const ctx = (patch: Partial<DecisionContext> = {}): DecisionContext => ({
    principal: { kind: 'agent', userEmail: 'owner@example.com', orgRole: 'owner' },
    command: { pathKey: 'repo delete', grandGuard: true, destructive: true },
    target: { repo: { name: 'mail', state: 'grand' }, isOpsVm: false },
    policy: null,
    overrides: { grandRepos: ['mail'], clusterOps: null, source: 'env' },
    confirmation: { granted: false },
    ...patch,
  });

  it('names the confirm argument and value on needs_confirmation', () => {
    expect(decide(ctx()).next).toEqual({ confirm: { argument: 'confirm', value: 'mail' } });
  });

  it('names the fork command on a grand-repo refusal', () => {
    const got = decide(ctx({ overrides: { grandRepos: null, clusterOps: null, source: 'none' } }));
    expect(got.code).toBe('AGENT_OPT_IN_MISSING');
    expect(got.next).toEqual({ run: 'rdc repo fork mail --tag <tag>' });
  });

  it('carries no next step on an allow', () => {
    expect(decide(ctx({ confirmation: { granted: true } })).next).toBeUndefined();
  });

  it('is pure: the same context yields the same decision', () => {
    const c = ctx();
    expect(decide(c)).toEqual(decide(c));
  });

  it('treats only agent-withheld verbs of the cluster families as lifecycle ops', () => {
    expect(isClusterLifecycleCommand({ pathKey: 'cluster destroy', agentBlocked: true })).toBe(
      true
    );
    expect(isClusterLifecycleCommand({ pathKey: 'datastore delete', agentBlocked: true })).toBe(
      true
    );
    expect(isClusterLifecycleCommand({ pathKey: 'cluster status' })).toBe(false);
    expect(isClusterLifecycleCommand({ pathKey: 'run', agentBlocked: true })).toBe(false);
  });
});
