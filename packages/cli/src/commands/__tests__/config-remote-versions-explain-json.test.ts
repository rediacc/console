import { beforeEach, describe, expect, it, vi } from 'vitest';

// R2 review: `config remote versions --explain -o json` keeps `changes` null and the raw
// `unreadable` reason; the localized placeholders belong to the table only.

const { printed, mockService } = vi.hoisted(() => ({
  printed: [] as { rows: unknown; format: string }[],
  mockService: {
    getEffectiveConfigName: () => 'ro',
    getActiveRemoteAdapter: vi.fn(),
  },
}));

vi.mock('../../services/config/config-resources.js', () => ({ configService: mockService }));
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    print: (rows: unknown, format: string) => {
      printed.push({ rows, format });
    },
    info: vi.fn(),
    error: vi.fn(),
    warn: vi.fn(),
    success: vi.fn(),
  },
}));

const { Command } = await import('commander');
const { registerConfigCommands } = await import('../config.js');

const docs: Record<number, unknown> = {
  1: { schemaVersion: 3, resources: { machines: { a: { ip: '1' } } } },
  3: { schemaVersion: 3, resources: { machines: { a: { ip: '9' } } } },
};

async function run(...argv: string[]) {
  const program = new Command();
  program.option('-o, --output <format>', 'format', 'table');
  registerConfigCommands(program);
  await program.parseAsync(argv, { from: 'user' });
}

describe('config remote versions --explain output', () => {
  beforeEach(() => {
    printed.length = 0;
    mockService.getActiveRemoteAdapter.mockResolvedValue({
      listVersions: vi.fn().mockResolvedValue([
        { version: 3, archivedAt: 't3', sdkEpoch: 1 },
        { version: 2, archivedAt: 't2', sdkEpoch: 1 },
        { version: 1, archivedAt: 't1', sdkEpoch: 1 },
      ]),
      pullVersion: vi.fn((v: number) =>
        v === 2
          ? Promise.reject(new Error('key slot rotated'))
          : Promise.resolve({ config: docs[v], version: v })
      ),
    });
  });

  it('json keeps changes null and the raw unreadable reason', async () => {
    await run('-o', 'json', 'config', 'remote', 'versions', '--explain');
    expect(printed).toHaveLength(1);
    expect(printed[0].rows).toMatchObject([
      { version: 3, changes: '/resources/machines/a/ip' },
      { version: 2, changes: null, unreadable: 'key slot rotated' },
      { version: 1, changes: null },
    ]);
  });

  it('table swaps in a sentence and drops the raw field', async () => {
    await run('config', 'remote', 'versions', '--explain');
    const rows = printed[0].rows as Record<string, unknown>[];
    expect(rows[1]).not.toHaveProperty('unreadable');
    expect(typeof rows[1].changes).toBe('string');
  });
});
