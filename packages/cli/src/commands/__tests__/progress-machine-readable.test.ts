/**
 * Status and progress lines that follow a command's result (sync summary, delete/create total) go to
 * stderr under -o json/yaml/csv, so stdout stays one parseable document.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setCurrentOutputFormat } from '../../services/core/output-format.js';

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));
vi.mock('../../services/core/output.js', () => ({
  outputService: { setTimelineRendered: vi.fn() },
}));

const out = vi.hoisted(() => ({ stdout: [] as string[], stderr: [] as string[] }));
vi.mock('../../services/core/request-context.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/core/request-context.js')>()),
  writeStdout: (s: string) => out.stdout.push(s),
  writeStderr: (s: string) => out.stderr.push(s),
}));

import { renderTimelineTotal } from '../repo-create-delete-teardown.js';
import { displaySyncResult } from '../repo-sync-display.js';

const spinner = { succeed: vi.fn(), fail: vi.fn() } as never;

function runSync(): void {
  displaySyncResult(
    {
      success: true,
      filesTransferred: 2,
      bytesTransferred: 2048,
      duration: 1500,
      errors: [],
      deleted: 1,
    },
    spinner,
    'upload'
  );
}

describe('status lines after a result', () => {
  beforeEach(() => {
    out.stdout.length = 0;
    out.stderr.length = 0;
  });
  afterEach(() => setCurrentOutputFormat('table'));

  it('table format writes the sync summary to stdout (control)', () => {
    runSync();
    expect(out.stdout.join('')).toContain('commands.sync.duration');
    expect(out.stdout.join('')).toContain('commands.sync.totalSize');
    expect(out.stdout.join('')).toContain('commands.sync.deleted');
    expect(out.stderr).toEqual([]);
  });

  it('table format writes the delete/create total to stdout (control)', () => {
    renderTimelineTotal([{ duration_ms: 1200 }]);
    expect(out.stdout.join('')).toContain('Total:');
    expect(out.stderr).toEqual([]);
  });

  it.each(['json', 'yaml', 'csv'] as const)('-o %s moves the sync summary to stderr', (format) => {
    setCurrentOutputFormat(format);
    runSync();
    expect(out.stdout).toEqual([]);
    expect(out.stderr.join('')).toContain('commands.sync.duration');
  });

  it.each(['json', 'yaml', 'csv'] as const)('-o %s moves the total line to stderr', (format) => {
    setCurrentOutputFormat(format);
    renderTimelineTotal([{ duration_ms: 1200 }]);
    expect(out.stdout).toEqual([]);
    expect(out.stderr.join('')).toContain('Total:');
  });
});
