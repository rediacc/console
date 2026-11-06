/**
 * `machine health` folds every mounted repo's Rediaccfile health() (G4, D-repohealth): renet
 * `repository health --all --strict`, the worst level joining the exit code with one finding per repo. A repo with no
 * check adds nothing, an older renet is one warning (`renet.repo-health.unsupported`), and a failed read is exit 2.
 */

import { describe, expect, it, vi } from 'vitest';

vi.mock('../../../services/core/output.js', () => ({ outputService: { info: vi.fn() } }));
vi.mock('../../../services/config/config-resources.js', () => ({ configService: {} }));
vi.mock('../../../i18n/index.js', () => ({ t: (k: string) => k }));

const { applyRepoHealth, fetchRepoHealth, foldRepoHealthResult } = await import('../health.js');

const clean = {
  healthy: true,
  exitCode: 0,
  message: 'All systems healthy',
  details: {} as never,
  issues: [] as string[],
  findings: [],
};

const answer = (repositories: unknown[]) => ({
  success: true,
  stdout: `${JSON.stringify({ repositories })}\n`,
});

const repo = (name: string, level: string, files: unknown[] = []) => ({
  guid: `${name}-guid`,
  name,
  network_id: 2816,
  state: 'healthy',
  level,
  files,
});

describe('applyRepoHealth', () => {
  it('one repo warning turns a clean machine to exit 1 with one finding', () => {
    const h = applyRepoHealth(
      clean,
      foldRepoHealthResult(
        answer([
          repo('mail', 'warning', [
            { file: 'Rediaccfile', exit: 1, level: 'warning', detail: 'queue 812' },
          ]),
          repo('wiki', 'ok'),
        ])
      ),
      'm1'
    );
    expect(h.exitCode).toBe(1);
    expect(h.healthy).toBe(false);
    expect(h.findings).toEqual([
      expect.objectContaining({
        code: 'repo.health.warning',
        severity: 'warning',
        subject: 'mail',
      }),
    ]);
    expect(h.issues.join('\n')).toMatch(/mail/);
  });

  it('one repo error gives exit 2', () => {
    const h = applyRepoHealth(
      clean,
      foldRepoHealthResult(answer([repo('mail', 'error'), repo('wiki', 'warning')])),
      'm1'
    );
    expect(h.exitCode).toBe(2);
    expect(h.findings.map((f) => f.code).sort()).toEqual([
      'repo.health.error',
      'repo.health.warning',
    ]);
  });

  it('all repos without a check stay exit 0 and raise no finding', () => {
    const h = applyRepoHealth(
      clean,
      foldRepoHealthResult(answer([repo('mail', 'none'), repo('wiki', 'none')])),
      'm1'
    );
    expect(h.exitCode).toBe(0);
    expect(h.findings).toEqual([]);
    expect(h.issues).toEqual([]);
  });

  it('an "unknown flag" answer (older renet) gives exit 1 with renet.repo-health.unsupported', () => {
    const fold = foldRepoHealthResult({
      success: false,
      error: 'renet exited with code 1',
      stderr: 'Error: unknown flag: --all',
    });
    expect(fold.status).toBe('unsupported');
    const h = applyRepoHealth(clean, fold, 'm1');
    expect(h.exitCode).toBe(1);
    expect(h.findings).toEqual([
      expect.objectContaining({ code: 'renet.repo-health.unsupported', subject: 'm1' }),
    ]);
  });

  it('an older renet that ignores the all param and asks for a repository is unsupported too', () => {
    expect(
      foldRepoHealthResult({ success: false, stderr: 'Error: Repository name is required' }).status
    ).toBe('unsupported');
    // A single report (no list) is an older renet that ran without --all.
    expect(foldRepoHealthResult({ success: true, stdout: '{"state":"healthy"}' }).status).toBe(
      'unsupported'
    );
  });

  it('a failed repo-health read gives exit 2', () => {
    const fold = foldRepoHealthResult({ success: false, error: 'ssh: connection reset' });
    expect(fold.status).toBe('failed');
    const h = applyRepoHealth(clean, fold, 'm1');
    expect(h.exitCode).toBe(2);
    expect(h.findings[0]).toMatchObject({ code: 'repo.health.failed', severity: 'error' });
  });

  it('a repo whose evaluation failed on the machine counts as an error, not as healthy', () => {
    const h = applyRepoHealth(
      clean,
      foldRepoHealthResult(
        answer([{ guid: 'g1', level: 'error', error: 'find Rediaccfiles: broken' }])
      ),
      'm1'
    );
    expect(h.exitCode).toBe(2);
    expect(h.findings[0]).toMatchObject({ subject: 'g1', detail: 'find Rediaccfiles: broken' });
  });

  it('never lowers a worse machine verdict (control)', () => {
    const h = applyRepoHealth(
      { ...clean, healthy: false, exitCode: 2, message: 'System has errors' },
      foldRepoHealthResult(answer([repo('mail', 'warning')])),
      'm1'
    );
    expect(h.exitCode).toBe(2);
  });
});

describe('fetchRepoHealth', () => {
  it('folds an unreadable local config into repo.health.failed instead of rejecting', async () => {
    // The mocked configService has no getLocalConfig, so the read throws before any renet call.
    const fold = await fetchRepoHealth('m1');
    expect(fold.status).toBe('failed');
    expect(applyRepoHealth(clean, fold, 'm1').exitCode).toBe(2);
  });
});
