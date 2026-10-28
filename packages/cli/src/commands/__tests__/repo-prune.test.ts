import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

const mockExecute = vi.hoisted(() => vi.fn());
vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute: mockExecute }),
}));

const mockGetRepository = vi.hoisted(() => vi.fn());
vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getRepository: mockGetRepository },
}));

const out = vi.hoisted(() => ({
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
  success: vi.fn(),
  print: vi.fn(),
}));
vi.mock('../../services/core/output.js', () => ({ outputService: out }));

const mockIsAgent = vi.hoisted(() => vi.fn());
vi.mock('../../utils/agent-guard.js', () => ({ isAgentEnvironment: mockIsAgent }));

const mockAssertPolicy = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock('../../utils/command-policy.js', () => ({
  assertCommandPolicy: mockAssertPolicy,
  CMD: { REPO_PRUNE: 'repo prune' },
}));

const outputFormat = vi.hoisted(() => ({ value: 'table' }));
vi.mock('../../utils/errors.js', () => {
  class ValidationError extends Error {}
  return {
    ValidationError,
    getOutputFormat: () => outputFormat.value,
    handleError: (error: unknown) => {
      throw error;
    },
  };
});

vi.mock('../../utils/guid-resolver.js', () => ({
  loadGuidMap: vi.fn().mockResolvedValue({}),
  createRepoNameResolver: () => (guid: string) => ({ name: `repo-${guid}`, source: 'config' }),
}));

const mockRenderFailure = vi.hoisted(() => vi.fn());
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: mockRenderFailure,
}));

const mockAskConfirm = vi.hoisted(() => vi.fn());
vi.mock('../../utils/prompt.js', () => ({ askConfirm: mockAskConfirm }));

vi.mock('../../utils/repo-executor.js', () => ({
  recordedDatastoreMount: vi.fn().mockResolvedValue(undefined),
}));

const mockResolveRef = vi.hoisted(() => vi.fn());
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: mockResolveRef,
  resolveRepoTarget: vi.fn().mockResolvedValue({ machineName: 'm1' }),
}));

vi.mock('../_validate.js', () => ({ assertMachineExists: vi.fn().mockResolvedValue(undefined) }));

import { registerRepoPruneCommand } from '../repo-prune.js';

const CLASS_KEYS = ['A', 'B', 'C', 'D', 'G', 'E', 'F1', 'F2', 'L', 'Q'] as const;

function record(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const classes: Record<string, unknown> = {};
  CLASS_KEYS.forEach((key, i) => {
    classes[key] = { count: i + 1, bytes: (i + 1) * 1024 * 1024, paths: [] };
  });
  return {
    guid: 'g1',
    mode: 'dry-run',
    classes,
    estimate: 5 * 1024 ** 3,
    estimate_online: 2 * 1024 ** 2,
    errors: [],
    ...overrides,
  };
}

async function run(...args: string[]): Promise<void> {
  const repo = new Command('repo').exitOverride();
  registerRepoPruneCommand(repo);
  await repo.parseAsync(['prune', ...args], { from: 'user' });
}

beforeEach(() => {
  vi.clearAllMocks();
  outputFormat.value = 'table';
  mockIsAgent.mockReturnValue(false);
  mockResolveRef.mockResolvedValue({ repoKey: 'shop', name: 'shop', machineName: 'm1' });
  mockGetRepository.mockResolvedValue({ repositoryGuid: 'g1' });
  mockExecute.mockResolvedValue({ success: true, stdout: JSON.stringify(record()) });
});

describe('repo prune refusals (before any execution)', () => {
  it('refuses --offline without --apply', async () => {
    await expect(run('shop', '--offline')).rejects.toThrow('commands.repo.prune.offlineNeedsApply');
    expect(mockExecute).not.toHaveBeenCalled();
    expect(mockResolveRef).not.toHaveBeenCalled();
  });

  it('refuses --apply with -m and no ref', async () => {
    await expect(run('-m', 'm1', '--apply')).rejects.toThrow('commands.repo.prune.applyNeedsRef');
    expect(mockExecute).not.toHaveBeenCalled();
  });

  it('refuses --offline in an agent environment without -y', async () => {
    mockIsAgent.mockReturnValue(true);
    await expect(run('shop', '--apply', '--offline')).rejects.toThrow(
      'commands.repo.prune.offlineNeedsYes'
    );
    expect(mockExecute).not.toHaveBeenCalled();
  });

  it('lets --offline -y through in an agent environment', async () => {
    mockIsAgent.mockReturnValue(true);
    await run('shop', '--apply', '--offline', '-y');
    expect(mockExecute).toHaveBeenCalledTimes(1);
    expect(mockAskConfirm).not.toHaveBeenCalled();
  });

  // The root program owns -y/--yes and consumes it anywhere on the line (cli.ts), so the subcommand never sees options.yes; the flag arrives as REDIACC_YES=1.
  it('lets --offline through in an agent environment when the root -y set REDIACC_YES', async () => {
    mockIsAgent.mockReturnValue(true);
    process.env.REDIACC_YES = '1';
    try {
      await run('shop', '--apply', '--offline');
    } finally {
      delete process.env.REDIACC_YES;
    }
    expect(mockExecute).toHaveBeenCalledTimes(1);
    expect(mockAskConfirm).not.toHaveBeenCalled();
  });

  it('prints the downtime notice and asks for --offline without -y outside an agent', async () => {
    mockAskConfirm.mockResolvedValue(false);
    await run('shop', '--apply', '--offline');
    expect(out.warn).toHaveBeenCalledWith(expect.stringContaining('downtimeNotice'));
    expect(mockAskConfirm).toHaveBeenCalledTimes(1);
    expect(mockExecute).not.toHaveBeenCalled();
  });
});

describe('repo prune execution', () => {
  it('runs repository_docker_prune as a dry run with the repo guid', async () => {
    await run('shop');
    expect(mockAssertPolicy).toHaveBeenCalledWith('repo prune', 'shop');
    const call = mockExecute.mock.calls[0][0];
    expect(call.functionName).toBe('repository_docker_prune');
    expect(call.captureOutput).toBe(true);
    expect(call.params).toEqual({ name: 'g1' });
  });

  it('maps the flags onto the function params', async () => {
    await run('shop', '--apply', '--all-images', '--no-trim');
    expect(mockExecute.mock.calls[0][0].params).toEqual({
      name: 'g1',
      apply: true,
      all_images: true,
      no_trim: true,
    });
  });

  it('renders every class and the estimate footer', async () => {
    await run('shop');
    const rows = out.print.mock.calls[0][0] as { class: string; count: number; bytes: string }[];
    expect(rows.map((r) => r.class)).toEqual(CLASS_KEYS);
    expect(rows[0]).toMatchObject({ count: 1, bytes: '1.0 MB' });
    expect(out.info).toHaveBeenCalledWith(
      expect.stringContaining('"offline":"5.0 GB","online":"2.0 MB"')
    );
  });

  it('passes the record through unchanged for JSON output', async () => {
    outputFormat.value = 'json';
    const rec = record({ extra_field: 'kept' });
    mockExecute.mockResolvedValue({ success: true, stdout: JSON.stringify(rec) });
    await run('shop');
    expect(out.print).toHaveBeenCalledWith(rec, 'json');
  });

  it('exits non-zero when the scan refuses the run', async () => {
    const saved = process.exitCode;
    process.exitCode = undefined;
    try {
      mockExecute.mockResolvedValue({
        success: true,
        stdout: JSON.stringify(record({ refused: 'daemon busy' })),
      });
      await run('shop', '--apply', '--offline', '-y');
      expect(process.exitCode).toBe(1);
    } finally {
      process.exitCode = saved;
    }
  });

  it('surveys every mounted repository on -m as a dry run', async () => {
    mockExecute
      .mockResolvedValueOnce({
        success: true,
        stdout: JSON.stringify([
          { name: 'g1', mounted: true },
          { name: 'g2', mounted: false },
          { name: 'g3', mounted: true },
        ]),
      })
      .mockResolvedValue({ success: true, stdout: JSON.stringify(record()) });
    await run('-m', 'm1');
    const names = mockExecute.mock.calls.map((c) => c[0].functionName);
    expect(names).toEqual([
      'repository_list',
      'repository_docker_prune',
      'repository_docker_prune',
    ]);
    expect(mockExecute.mock.calls[1][0].params).toEqual({ name: 'g1' });
    expect(mockExecute.mock.calls[2][0].params).toEqual({ name: 'g3' });
  });
});
