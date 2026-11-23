import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { flows, overlayState, out } = vi.hoisted(() => ({
  flows: {
    switchToPreview: vi.fn((): Promise<unknown> => Promise.resolve({})),
    leavePreviewFlow: vi.fn(
      (): Promise<unknown> => Promise.resolve({ left: true, switched: [], remaining: [] })
    ),
  },
  overlayState: { current: undefined as unknown },
  out: { info: vi.fn(), report: vi.fn(), warn: vi.fn(), success: vi.fn(), error: vi.fn() },
}));

vi.mock('../../services/preview/switch.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/preview/switch.js')>()),
  switchToPreview: flows.switchToPreview,
  leavePreviewFlow: flows.leavePreviewFlow,
}));
vi.mock('../../services/preview/deps.js', () => ({
  realPreviewUseDeps: () => ({ marker: 'use-deps' }),
  realPreviewLeaveDeps: () => ({ marker: 'leave-deps' }),
}));
vi.mock('../../services/preview/state.js', () => ({
  readPreviewOverlay: () => overlayState.current,
  readRealAccountServer: () => 'https://real.example',
}));
vi.mock('../../services/core/output.js', () => ({ outputService: out }));
vi.mock('../../utils/errors.js', () => ({
  handleError: (error: unknown) => {
    throw error;
  },
}));

const { printPreviewBanner, registerPreviewCommand } = await import('../preview.js');

function program(): Command {
  const cli = new Command().exitOverride();
  registerPreviewCommand(cli);
  return cli;
}

beforeEach(() => {
  vi.clearAllMocks();
  overlayState.current = undefined;
});

describe('rdc preview', () => {
  it('registers use, leave and status under one preview command', () => {
    const preview = program().commands.find((c) => c.name() === 'preview');
    expect(preview?.commands.map((c) => c.name()).sort()).toEqual(['leave', 'status', 'use']);
  });

  it('passes the name and --accept-format-change to use', async () => {
    await program().parseAsync(
      ['preview', 'use', 'pv-amber-river-stone', '--accept-format-change'],
      { from: 'user' }
    );
    expect(flows.switchToPreview).toHaveBeenCalledWith(
      'pv-amber-river-stone',
      { acceptFormatChange: true },
      { marker: 'use-deps' }
    );
  });

  it('refuses use without a name', async () => {
    await expect(program().parseAsync(['preview', 'use'], { from: 'user' })).rejects.toThrow();
    expect(flows.switchToPreview).not.toHaveBeenCalled();
  });

  it('passes --machine to leave and exits non-zero while servers remain', async () => {
    flows.leavePreviewFlow.mockResolvedValueOnce({
      left: false,
      switched: [],
      remaining: ['vm2'],
    });
    const before = process.exitCode;
    await program().parseAsync(['preview', 'leave', '--machine', 'vm2'], { from: 'user' });
    expect(flows.leavePreviewFlow).toHaveBeenCalledWith(
      { machine: 'vm2' },
      { marker: 'leave-deps' }
    );
    expect(process.exitCode).toBe(1);
    process.exitCode = before;
  });

  it('status prints nothing but a notice outside a preview, and the block inside one', async () => {
    await program().parseAsync(['preview', 'status'], { from: 'user' });
    expect(out.info).toHaveBeenCalledWith(expect.stringContaining('not on a preview'));
    expect(out.report).not.toHaveBeenCalled();

    overlayState.current = {
      name: 'pv-amber-river-stone',
      host: 'https://pv-amber-river-stone.rediacc.workers.dev',
      enteredAt: '2026-11-23T10:00:00.000Z',
      channel: 'pv-amber-river-stone',
      previous: { cliVersion: '1.3.9', cliSha256: 'a'.repeat(64) },
    };
    await program().parseAsync(['preview', 'status'], { from: 'user' });
    expect(String(out.report.mock.calls[0][0])).toContain('pv-amber-river-stone');
  });
});

describe('the banner before every command', () => {
  it('prints once while a preview is active, and nothing otherwise', () => {
    printPreviewBanner();
    expect(out.info).not.toHaveBeenCalled();

    overlayState.current = {
      name: 'pv-amber-river-stone',
      host: 'https://pv-amber-river-stone.rediacc.workers.dev',
      enteredAt: '2026-11-23T10:00:00.000Z',
      channel: 'pv-amber-river-stone',
      licenceEndsAt: '2099-01-01T00:00:00.000Z',
      previous: { cliVersion: '1.3.9', cliSha256: 'a'.repeat(64) },
    };
    printPreviewBanner();
    expect(out.info).toHaveBeenCalledTimes(1);
    expect(String(out.info.mock.calls[0][0])).toContain('rdc preview leave');
  });
});
