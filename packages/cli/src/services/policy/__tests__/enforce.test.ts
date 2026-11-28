/**
 * The shared decision table (packages/shared/src/policy/__fixtures__/decision-table.json) driven
 * through the CLI enforcement step: a ref resolved by target.ts against a mocked config, then
 * `decide`. Every row must reproduce its expected verdict and code, and every control row (a
 * deliberately wrong expectation) must be reported as a mismatch.
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  type Decision,
  type DecisionContext,
  mergePolicies,
  type PolicyDocument,
  PolicyDocumentSchema,
} from '@rediacc/shared/policy';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const repoRecord = vi.hoisted(() => ({
  current: undefined as undefined | { repositoryGuid: string; grandGuid?: string },
  opsVm: false,
}));

vi.mock('../../config/config-resources.js', () => ({
  configService: { getRepository: vi.fn(async () => repoRecord.current) },
}));
vi.mock('../../../utils/ops-vm.js', () => ({
  isOpsVmMachine: vi.fn(async () => repoRecord.opsVm),
  isOpsVmPlacement: vi.fn(async () => repoRecord.opsVm),
}));

import { isOpsVmMachine } from '../../../utils/ops-vm.js';
import { configService } from '../../config/config-resources.js';
import { DecisionError, enforce } from '../enforce.js';
import { resolveTarget } from '../target.js';

interface FixtureRow {
  id: string;
  principal: DecisionContext['principal'];
  command: DecisionContext['command'];
  target: DecisionContext['target'];
  policy: { org?: unknown; team?: unknown } | null;
  overrides: DecisionContext['overrides'];
  confirmation: DecisionContext['confirmation'];
  expect: { verdict: string; code: string };
}

const HERE = dirname(fileURLToPath(import.meta.url));
const TABLE_PATH = join(
  HERE,
  '..',
  '..',
  '..',
  '..',
  '..',
  'shared',
  'src',
  'policy',
  '__fixtures__',
  'decision-table.json'
);
const table = JSON.parse(readFileSync(TABLE_PATH, 'utf8')) as {
  rows: FixtureRow[];
  controls: FixtureRow[];
};

const parseDoc = (raw: unknown): PolicyDocument | undefined =>
  raw === undefined ? undefined : PolicyDocumentSchema.parse(raw);

/** The config record a row's repo state stands for: a grand, a fork of one, or nothing. */
function recordFor(state: string | undefined) {
  if (state === 'grand') return { repositoryGuid: 'g-1' };
  if (state === 'fork') return { repositoryGuid: 'f-1', grandGuid: 'g-1' };
  return undefined;
}

async function run(row: FixtureRow): Promise<Decision> {
  repoRecord.current = recordFor(row.target.repo?.state);
  repoRecord.opsVm = row.target.isOpsVm;
  try {
    return await enforce({
      principal: row.principal,
      command: row.command,
      target: {
        ...(row.target.repo ? { ref: row.target.repo.name } : {}),
        ...(row.target.machine ? { machine: row.target.machine } : {}),
        ...(row.target.subject ? { subject: row.target.subject } : {}),
      },
      policy: row.policy
        ? mergePolicies(parseDoc(row.policy.org), parseDoc(row.policy.team))
        : null,
      overrides: row.overrides,
      confirmation: row.confirmation,
    });
  } catch (error) {
    if (error instanceof DecisionError) return error.decision;
    throw error;
  }
}

async function mismatch(row: FixtureRow): Promise<string | null> {
  const got = await run(row);
  if (got.verdict === row.expect.verdict && got.code === row.expect.code) return null;
  return `${row.id}: expected ${row.expect.verdict}/${row.expect.code}, got ${got.verdict}/${got.code} (${got.reason})`;
}

beforeEach(() => {
  vi.clearAllMocks();
  repoRecord.current = undefined;
  repoRecord.opsVm = false;
});

describe('decision table through enforce', () => {
  it('reads a table of at least 60 rows', () => {
    expect(table.rows.length).toBeGreaterThanOrEqual(60);
  });

  it.each(table.rows.map((r) => [r.id, r] as const))('%s', async (_id, row) => {
    expect(await mismatch(row)).toBeNull();
  });

  it.each(table.controls.map((r) => [r.id, r] as const))(
    '%s is reported as a mismatch',
    async (_id, row) => {
      expect(await mismatch(row)).not.toBeNull();
    }
  );
});

describe('enforce', () => {
  it('throws a DecisionError carrying the whole decision for a refusal', async () => {
    repoRecord.current = { repositoryGuid: 'g-1' };
    const attempt = enforce({
      principal: { kind: 'agent', userEmail: 'a@example.com', orgRole: 'owner' },
      command: { pathKey: 'repo up', grandGuard: true },
      target: { ref: 'mail' },
      policy: null,
      overrides: { grandRepos: null, clusterOps: null, source: 'none' },
    });
    await expect(attempt).rejects.toBeInstanceOf(DecisionError);
    await expect(attempt).rejects.toMatchObject({
      decision: { verdict: 'deny', code: 'AGENT_OPT_IN_MISSING' },
    });
  });

  it('returns the allow decision and throws nothing for an allowed command', async () => {
    repoRecord.current = { repositoryGuid: 'f-1', grandGuid: 'g-1' };
    const decision = await enforce({
      principal: { kind: 'agent', userEmail: 'a@example.com', orgRole: 'owner' },
      command: { pathKey: 'repo up', grandGuard: true },
      target: { ref: 'mail:t1' },
      policy: null,
      overrides: { grandRepos: null, clusterOps: null, source: 'none' },
    });
    expect(decision.code).toBe('ALLOWED');
  });
});

describe('resolveTarget', () => {
  it('reports a ref that breaks the grammar as unresolved without a config lookup', async () => {
    const target = await resolveTarget({ ref: 'Not A Ref!' });
    expect(target.repo).toEqual({ name: 'Not A Ref!', state: 'unresolved' });
    expect(configService.getRepository).not.toHaveBeenCalled();
  });

  it('looks a forked ref up by name:tag and strips the @place into the machine', async () => {
    repoRecord.current = { repositoryGuid: 'f-1', grandGuid: 'g-1' };
    const target = await resolveTarget({ ref: 'mail:t1@m2' });
    expect(configService.getRepository).toHaveBeenCalledWith('mail:t1');
    expect(target).toEqual({
      machine: 'm2',
      repo: { name: 'mail:t1', state: 'fork' },
      isOpsVm: false,
    });
  });

  it('judges an unresolved repo on the ops VM fleet by the machine the ref names', async () => {
    repoRecord.opsVm = true;
    const target = await resolveTarget({ ref: 'ghost@ops-1' });
    expect(isOpsVmMachine).toHaveBeenCalledWith('ops-1');
    expect(target).toMatchObject({ repo: { state: 'unresolved' }, isOpsVm: true });
  });

  it('treats a record whose grandGuid is its own guid as the grand', async () => {
    repoRecord.current = { repositoryGuid: 'g-1', grandGuid: 'g-1' };
    expect((await resolveTarget({ ref: 'mail' })).repo).toEqual({ name: 'mail', state: 'grand' });
  });
});
