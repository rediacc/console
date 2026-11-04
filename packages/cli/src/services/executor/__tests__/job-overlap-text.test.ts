import { describe, expect, it } from 'vitest';
import en from '../../../i18n/locales/en/cli.json' with { type: 'json' };
import { overlapWarningLines } from '../job-client.js';

describe('overlap warning text comes from the en catalog', () => {
  it('renders a refusal with its subject, origin and attach line', () => {
    const lines = overlapWarningLines({
      action: 'refuse',
      jobId: 'j1-abcdef01',
      function: 'repository_up',
      repo: 'mail',
      state: 'running',
      startedAt: '2026-11-04T10:00:00Z',
      origin: { sshUser: 'ops', client: 'rdc', config: { name: 'eu' } },
      attach: 'rdc job wait j1-abcdef01',
    } as never);
    expect(lines).toEqual([
      'Refused: job j1-abcdef01 (repository_up on mail) is running, started 2026-11-04T10:00:00Z, started by ops via rdc (config eu).',
      '  See it: rdc job wait j1-abcdef01',
    ]);
  });

  it('falls back to the older-renet origin text', () => {
    const [head] = overlapWarningLines({ action: 'warn', jobId: 'j2-00000000' } as never);
    expect(head).toBe(
      'Warning: job j2-00000000 (work) is running, started by: unknown (older renet).'
    );
  });

  it('control: the refusal key carries its holder placeholder', () => {
    expect(en.errors.jobs.refused).toContain('{{holder}}');
  });
});
