import { afterEach, describe, expect, it, vi } from 'vitest';
import { isMcpServeFastPath } from '../fast-path.js';

const base = ['node', 'rdc'];

describe('isMcpServeFastPath', () => {
  it('takes the fast path for mcp serve', () => {
    expect(isMcpServeFastPath([...base, 'mcp', 'serve'])).toBe(true);
    expect(isMcpServeFastPath([...base, 'mcp', 'serve', '--config', 'x', '--timeout', '5'])).toBe(
      true
    );
  });

  it('leaves the fast path for --help and -h so Commander prints help', () => {
    expect(isMcpServeFastPath([...base, 'mcp', 'serve', '--help'])).toBe(false);
    expect(isMcpServeFastPath([...base, 'mcp', 'serve', '-h'])).toBe(false);
    expect(isMcpServeFastPath([...base, '--help', 'mcp', 'serve'])).toBe(false);
  });

  it('ignores other commands', () => {
    expect(isMcpServeFastPath([...base, 'mcp'])).toBe(false);
    expect(isMcpServeFastPath([...base, 'serve'])).toBe(false);
  });
});

// 698a0145.1: the helper is pinned above, but index.ts could stop calling it (or call it with another argv) and nothing failed.
describe('index.ts entry', () => {
  const origArgv = process.argv;
  const startMcpServer = vi.fn(() => Promise.resolve());
  const parseAsync = vi.fn(() => Promise.resolve());

  afterEach(() => {
    process.argv = origArgv;
    vi.resetModules();
    startMcpServer.mockClear();
    parseAsync.mockClear();
  });

  async function runEntry(args: string[]): Promise<void> {
    process.argv = [...base, ...args];
    vi.resetModules();
    vi.doMock('../server.js', () => ({ startMcpServer }));
    vi.doMock('../../../cli.js', () => ({ cli: { parseAsync } }));
    vi.doMock('../../../services/feedback/hint.js', () => ({ printFeedbackHint: vi.fn() }));
    vi.doMock('../../../services/feedback/ring.js', () => ({
      installStderrTap: vi.fn(),
      recordCommand: vi.fn(),
    }));
    vi.doMock('../../../services/telemetry/telemetry.js', () => ({
      telemetryService: {
        trackError: vi.fn(),
        shutdown: () => Promise.resolve(),
        stopProfiling: () => Promise.resolve(),
      },
    }));
    vi.doMock('../../../services/update/background-updater.js', () => ({
      applyPendingUpdate: () => Promise.resolve(),
      maybeSpawnBackgroundUpdate: () => Promise.resolve(),
      runBackgroundUpdateWorker: () => Promise.resolve(),
    }));
    vi.doMock('../../../warmup.js', () => ({ runWarmup: () => 0 }));
    await import('../../../index.js');
    await new Promise((resolve) => setTimeout(resolve, 20));
  }

  it('starts the MCP server, with its --config and --timeout, and never the CLI, for mcp serve', async () => {
    await runEntry(['mcp', 'serve', '--config', 'x', '--timeout', '5']);
    expect(startMcpServer).toHaveBeenCalledWith({ configName: 'x', defaultTimeoutMs: 5 });
    expect(parseAsync).not.toHaveBeenCalled();
  });

  it('hands mcp serve --help to Commander instead of starting the server', async () => {
    await runEntry(['mcp', 'serve', '--help']);
    expect(startMcpServer).not.toHaveBeenCalled();
    expect(parseAsync).toHaveBeenCalledTimes(1);
  });
});
