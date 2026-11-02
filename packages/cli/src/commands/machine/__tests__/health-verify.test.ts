/**
 * A failed `backup verify` is a health input: renet records the last verify per repository in
 * backup_coverage, and `machine health` raises its exit code and names the repository.
 */

import { describe, expect, it, vi } from 'vitest';

vi.mock('../../../services/core/output.js', () => ({ outputService: { info: vi.fn() } }));
vi.mock('../../../services/config/config-resources.js', () => ({ configService: {} }));
vi.mock('../../../i18n/index.js', () => ({ t: (k: string) => k }));

const { applyStaleness } = await import('../health.js');
const { failedVerifyRepos } = await import('../../../services/backup/backup-schedule-coverage.js');
const { statusJsonDocument } = await import('../status.js');

const healthy = {
  healthy: true,
  exitCode: 0,
  message: 'All systems healthy',
  details: {} as never,
  issues: [] as string[],
};

const repo = (over: Record<string, unknown>) => ({
  guid: 'a0000000-0000-4000-8000-000000000001',
  name: 'mail',
  age_days: 0.5,
  last_verify_at: '2026-11-01T03:00:00Z',
  ...over,
});

describe('failedVerifyRepos', () => {
  it('lists the repos whose last verify mismatched or failed', () => {
    const failed = failedVerifyRepos({
      repos: [
        repo({ guid: 'g1', name: 'mail', last_verify_status: 'mismatch' }),
        repo({ guid: 'g2', name: 'wiki', last_verify_status: 'failed' }),
        repo({ guid: 'g3', name: 'git', last_verify_status: 'verified' }),
        repo({ guid: 'g4', name: 'new', last_verify_status: undefined, last_verify_at: undefined }),
      ],
    });
    expect(failed.map((f) => [f.guid, f.status])).toEqual([
      ['g1', 'mismatch'],
      ['g2', 'failed'],
    ]);
    expect(failed[0]).toMatchObject({ name: 'mail', verifiedAt: '2026-11-01T03:00:00Z' });
  });

  it('reports nothing for a clean or absent coverage (control)', () => {
    expect(failedVerifyRepos(undefined)).toEqual([]);
    expect(failedVerifyRepos({ repos: [repo({ last_verify_status: 'verified' })] })).toEqual([]);
  });
});

describe('applyStaleness with failed verifies', () => {
  const failedVerifies = [
    { guid: 'g1', name: 'mail', status: 'mismatch', verifiedAt: '2026-11-01T03:00:00Z' },
  ];

  it('raises exit 1 and names the repository and the verdict', () => {
    const h = applyStaleness(healthy, { staleBinary: [], staleBackups: [], failedVerifies });
    expect(h.exitCode).toBe(1);
    expect(h.healthy).toBe(false);
    expect(h.message).toBe('System has warnings');
    expect(h.issues.join('\n')).toMatch(/mail/);
    expect(h.issues.join('\n')).toMatch(/mismatch/);
  });

  it('never lowers a worse verdict', () => {
    const worse = applyStaleness(
      { ...healthy, healthy: false, exitCode: 2, message: 'System has errors' },
      { staleBinary: [], staleBackups: [], failedVerifies }
    );
    expect(worse.exitCode).toBe(2);
  });

  it('leaves a clean machine clean (control)', () => {
    expect(
      applyStaleness(healthy, { staleBinary: [], staleBackups: [], failedVerifies: [] })
    ).toEqual(healthy);
  });
});

describe('machine status json', () => {
  it('carries the failed verifies beside the staleness findings', () => {
    const doc = statusJsonDocument(
      {},
      undefined,
      (g) => g,
      null,
      [],
      [{ guid: 'g1', status: 'failed', verifiedAt: 'x' }]
    );
    expect(doc.verify_failures).toEqual([{ guid: 'g1', status: 'failed', verifiedAt: 'x' }]);
  });
});
