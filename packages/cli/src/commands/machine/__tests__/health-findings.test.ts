/**
 * X1 (PLAN-health-checks-local): every issue the CLI adds to the machine verdict (staleness, repo health(),
 * certificates) carries a coded finding from the findings table, with its fix, next to the unchanged issue text.
 */

import { isKnownFindingCode } from '@rediacc/shared/services/machine/findings';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../../services/core/output.js', () => ({ outputService: { info: vi.fn() } }));
vi.mock('../../../services/config/config-resources.js', () => ({ configService: {} }));
vi.mock('../../../i18n/index.js', () => ({ t: (k: string) => k }));

const { applyStaleness } = await import('../health.js');
const { applyRepoHealth, applyCertificates } = await import('../health-folds.js');

const NOW = new Date('2026-11-06T00:00:00Z');
const clean = {
  healthy: true,
  exitCode: 0,
  message: 'All systems healthy',
  details: {} as never,
  issues: [] as string[],
  findings: [],
};

/** Every CLI producer triggered once. */
function everything() {
  const stale = applyStaleness(clean, {
    staleBinary: [{ unit: 'rediacc-docker-5', pid: 42 }] as never,
    staleBackups: [
      { guid: 'g1', name: 'mail', ageSeconds: 900_000 },
      { guid: 'g2', name: 'wiki', ageSeconds: 900_000, targetSeconds: 3600 },
    ] as never,
    missedTargets: [{ guid: 'g3', name: 'git', targetSeconds: 3600 }] as never,
    failedVerifies: [{ guid: 'g4', name: 'erp', status: 'mismatch' }] as never,
  });
  const repos = applyRepoHealth(
    stale,
    {
      status: 'ok',
      repositories: [
        { guid: 'g5', name: 'shop', network_id: 7, level: 'warning', files: [] },
        { guid: 'g6', name: 'blog', network_id: 8, level: 'error', files: [] },
      ],
    },
    'm1'
  );
  return applyCertificates(
    repos,
    {
      status: 'ok',
      certificates: [
        {
          main: 'a.example.com',
          not_after: new Date(NOW.getTime() + 10 * 86_400_000).toISOString(),
          challenges: [
            { name: 'a.example.com', cname: 'www.example.com' },
            { name: 'b.example.com', cname: 'www.example.com' },
          ],
        },
      ],
    },
    NOW
  );
}

const EXPECTED = [
  'renet.binary.replaced',
  'backup.schedule.behind',
  'backup.target.missed',
  'backup.target.missed-latest',
  'backup.verify.failed',
  'repo.health.warning',
  'repo.health.error',
  'cert.expiry.near',
  'acme.challenge.cname-shared',
] as const;

describe('machine health findings from the CLI producers (X1)', () => {
  it('codes every issue it adds, from the table', () => {
    const health = everything();
    expect(health.findings.map((f) => f.code)).toEqual([...EXPECTED]);
    for (const f of health.findings) expect(isKnownFindingCode(f.code), f.code).toBe(true);
    // One issue string per finding, unchanged in wording.
    expect(health.issues).toHaveLength(EXPECTED.length);
    expect(health.issues[0]).toBe(
      '1 renet process(es) run a replaced binary: rediacc-docker-5 (pid 42)'
    );
  });

  it('attaches each fix from the table', () => {
    const byCode = new Map(everything().findings.map((f) => [f.code, f]));
    expect(byCode.get('renet.binary.replaced')?.fix).toEqual({
      action: 'restart-repo-supervisors',
      class: 'auto-safe',
      window_only: true,
    });
    expect(byCode.get('repo.health.error')).toMatchObject({
      fix: { action: 'repo-repair' },
      target: { repository: 'g6', networkId: 8 },
    });
    expect(byCode.get('cert.expiry.near')?.fix?.action).toBe('restart-traefik');
    expect(byCode.get('acme.challenge.cname-shared')?.fix?.action).toBe('acme-anchor');
    expect(byCode.get('backup.verify.failed')?.fix).toBeUndefined();
  });

  it('keeps the shared parser findings it was handed', () => {
    const fromParser = {
      ...clean,
      exitCode: 1,
      issues: ['Datastore usage high: 86%'],
      findings: [
        {
          code: 'datastore.usage.high',
          severity: 'warning' as const,
          subject: 'datastore',
          detail: 'x',
        },
      ],
    };
    const folded = applyStaleness(fromParser, { staleBinary: [], staleBackups: [] });
    expect(folded.findings.map((f) => f.code)).toEqual(['datastore.usage.high']);
  });
});
