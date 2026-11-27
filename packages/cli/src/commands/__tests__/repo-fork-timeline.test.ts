import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setCurrentOutputFormat } from '../../services/core/output-format.js';
import type { TimelineStep } from '../../utils/timeline.js';
import { createForkEventHandler } from '../repo-fork-timeline.js';

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));
vi.mock('../../services/core/output.js', () => ({
  outputService: { setTimelineRendered: vi.fn() },
}));

const out = vi.hoisted(() => ({
  stdout: [] as string[],
  stderr: [] as string[],
}));
vi.mock('../../services/core/request-context.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/core/request-context.js')>()),
  writeStdout: (s: string) => out.stdout.push(s),
  writeStderr: (s: string) => out.stderr.push(s),
}));

function runLegs(): void {
  const steps: TimelineStep[] = [];
  const handle = createForkEventHandler(steps);
  handle({ type: 'step_start', name: 'clone' });
  handle({ type: 'step_done', name: 'clone', duration_ms: 12 });
}

describe('fork timeline progress stream', () => {
  beforeEach(() => {
    out.stdout.length = 0;
    out.stderr.length = 0;
  });
  afterEach(() => setCurrentOutputFormat('table'));

  it('table format writes the timeline to stdout (control)', () => {
    setCurrentOutputFormat('table');
    runLegs();
    expect(out.stdout.join('')).toContain('✔');
    expect(out.stderr).toEqual([]);
  });

  it.each(['json', 'yaml', 'csv'] as const)(
    '-o %s keeps stdout empty and sends progress to stderr',
    (format) => {
      setCurrentOutputFormat(format);
      runLegs();
      expect(out.stdout).toEqual([]);
      expect(out.stderr.join('')).toContain('✔');
    }
  );
});
