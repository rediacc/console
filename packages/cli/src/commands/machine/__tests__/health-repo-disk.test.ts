/**
 * The shared parser now judges per-repo disk usage and Restarting containers (exit 1, 2 and 3). The CLI folds the
 * staleness findings on top of that verdict: it must keep the parser's issues and never lower its exit code.
 */

import { describe, expect, it, vi } from 'vitest';

vi.mock('../../../services/core/output.js', () => ({ outputService: { info: vi.fn() } }));
vi.mock('../../../services/config/config-resources.js', () => ({ configService: {} }));
vi.mock('../../../i18n/index.js', () => ({ t: (k: string) => k }));

const { applyStaleness } = await import('../health.js');

const fromParser = (exitCode: number, issues: string[]) => ({
  healthy: false,
  exitCode,
  message: 'System has errors',
  details: {} as never,
  issues,
  findings: [],
});

const staleBackups = [{ name: 'mail', ageDays: 12 }] as never;

describe('applyStaleness over the per-repo parser verdicts', () => {
  it('keeps a critical repo disk issue and its exit code beside a staleness warning', () => {
    const verdict = applyStaleness(
      fromParser(2, ['Repository demo-stackoverflow disk usage critical: 99%']),
      { staleBinary: [], staleBackups, failedVerifies: [] }
    );
    expect(verdict.exitCode).toBe(2);
    expect(verdict.issues.join('\n')).toContain('demo-stackoverflow');
  });

  it('never lowers a restart-loop verdict (exit 3)', () => {
    const verdict = applyStaleness(fromParser(3, ['1 container(s) in restart loop']), {
      staleBinary: [],
      staleBackups,
      failedVerifies: [],
    });
    expect(verdict.exitCode).toBe(3);
    expect(verdict.issues.join('\n')).toContain('restart loop');
  });
});
