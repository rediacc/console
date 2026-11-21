import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({ format: 'yaml' as string }));

vi.mock('../../services/core/output.js', () => ({
  outputService: {
    print: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    success: vi.fn(),
    format: vi.fn(),
  },
}));
vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    listClusters: vi.fn(async () => [
      {
        name: 'c1',
        config: { provider: 'aws', pools: [{ name: 'cp', role: 'control', count: 1 }] },
      },
    ]),
  },
}));
vi.mock('../../utils/errors.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/errors.js')>()),
  getOutputFormat: () => state.format,
}));

import { outputService } from '../../services/core/output.js';
import { registerClusterCommands } from '../cluster/index.js';
import { reportPushStats } from '../repo-push-stats.js';

const print = vi.mocked(outputService.print);

beforeEach(() => {
  vi.clearAllMocks();
});

describe('cluster status honours the global output format', () => {
  it.each(['json', 'yaml'])('prints the cluster list as %s, not one-line rows', async (format) => {
    state.format = format;
    const program = new Command();
    program.exitOverride();
    registerClusterCommands(program);
    await program.parseAsync(['node', 'rdc', 'cluster', 'status']);
    expect(print).toHaveBeenCalledTimes(1);
    const [data, fmt] = print.mock.calls[0];
    expect(fmt).toBe(format);
    expect(JSON.stringify(data)).toContain('c1');
  });
});

describe('repo push stats honour the global output format', () => {
  const stdout = `{"push_result":${JSON.stringify({
    repository: 'shop',
    destination: 'm2',
    destinationType: 'machine',
    size: 10,
    transferredAt: 'now',
    method: 'rsync',
    duration: '1s',
    transferMode: 'full',
    transferredBytes: 10,
    transferMs: 1000,
  })}}`;

  it.each(['json', 'yaml'])('prints the stats as %s for a storage target too', (format) => {
    reportPushStats(
      'shop',
      'bucket',
      'storage',
      { success: true, exitCode: 0, durationMs: 0, stdout },
      format as 'json'
    );
    expect(print).toHaveBeenCalledTimes(1);
    const [data, fmt] = print.mock.calls[0];
    expect(fmt).toBe(format);
    expect(JSON.stringify(data)).toContain('"repository":"shop"');
  });

  it('control: table prints no structured payload for a storage target', () => {
    reportPushStats(
      'shop',
      'bucket',
      'storage',
      { success: true, exitCode: 0, durationMs: 0, stdout },
      'table'
    );
    expect(print).not.toHaveBeenCalled();
  });
});
