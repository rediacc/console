import { describe, expect, it, vi } from 'vitest';
import { registerAllTools, TOOLS } from '../tools.js';

// Mock executor so no child processes are spawned
vi.mock('../executor.js', () => ({
  executeRdcCommand: vi.fn().mockResolvedValue({
    success: true,
    command: 'test',
    data: { mock: true },
    errors: null,
    warnings: [],
    duration_ms: 50,
  }),
  resolveRdcBinary: () => ({ command: 'node', prefixArgs: ['index.js'] }),
}));

describe('MCP server', () => {
  it('registers all tools on the McpServer', () => {
    const registeredTools: string[] = [];
    const mockServer = {
      registerTool: (name: string, _config: unknown, _handler: unknown) => {
        registeredTools.push(name);
      },
    };

    registerAllTools(mockServer as never, { defaultTimeoutMs: 120_000 });

    expect(registeredTools.length).toBe(TOOLS.length);
    for (const tool of TOOLS) {
      expect(registeredTools, `missing tool: ${tool.name}`).toContain(tool.name);
    }
  });

  it('tool handler calls executor and returns result', async () => {
    let capturedHandler: ((args: Record<string, unknown>) => Promise<unknown>) | null = null;
    const mockServer = {
      registerTool: (_name: string, _config: unknown, handler: unknown) => {
        // Capture the first tool's handler
        capturedHandler ??= handler as typeof capturedHandler;
      },
    };

    registerAllTools(mockServer as never, { defaultTimeoutMs: 120_000 });

    const result = (await capturedHandler!({ name: 'prod' })) as {
      content: { type: string; text: string }[];
      isError: boolean;
    };

    expect(result.isError).toBe(false);
    expect(result.content).toHaveLength(1);
    expect(result.content[0].type).toBe('text');

    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.success).toBe(true);
    expect(parsed.data).toEqual({ mock: true });
  });

  it('tool handler passes correct argv to executor', async () => {
    const { executeRdcCommand } = await import('../executor.js');
    vi.mocked(executeRdcCommand).mockClear();

    // Capture the handler for 'machine_containers' specifically
    let containerHandler: ((args: Record<string, unknown>) => Promise<unknown>) | null = null;
    const mockServer = {
      registerTool: (name: string, _config: unknown, handler: unknown) => {
        if (name === 'machine_containers') {
          containerHandler = handler as typeof containerHandler;
        }
      },
    };

    registerAllTools(mockServer as never, { defaultTimeoutMs: 120_000 });
    await containerHandler!({ name: 'staging' });

    expect(executeRdcCommand).toHaveBeenCalledWith(
      ['machine', 'containers', 'staging'],
      expect.objectContaining({ defaultTimeoutMs: 120_000 })
    );
  });

  it('passes configName from options to executor', async () => {
    const { executeRdcCommand } = await import('../executor.js');
    vi.mocked(executeRdcCommand).mockClear();

    let capturedHandler: ((args: Record<string, unknown>) => Promise<unknown>) | null = null;
    const mockServer = {
      registerTool: (_name: string, _config: unknown, handler: unknown) => {
        capturedHandler ??= handler as typeof capturedHandler;
      },
    };

    registerAllTools(mockServer as never, {
      defaultTimeoutMs: 120_000,
      configName: 'production',
    });
    await capturedHandler!({ name: 'prod' });

    expect(executeRdcCommand).toHaveBeenCalledWith(
      expect.any(Array),
      expect.objectContaining({ configName: 'production' })
    );
  });

  it('passes tool-specific timeoutMs to executor', async () => {
    const { executeRdcCommand } = await import('../executor.js');
    vi.mocked(executeRdcCommand).mockClear();

    // Capture the handler for 'repo_up' which has 300s timeout
    let repoUpHandler: ((args: Record<string, unknown>) => Promise<unknown>) | null = null;
    const mockServer = {
      registerTool: (name: string, _config: unknown, handler: unknown) => {
        if (name === 'repo_up') {
          repoUpHandler = handler as typeof repoUpHandler;
        }
      },
    };

    registerAllTools(mockServer as never, { defaultTimeoutMs: 120_000 });
    await repoUpHandler!({ name: 'app', machine: 'prod' });

    expect(executeRdcCommand).toHaveBeenCalledWith(
      expect.any(Array),
      expect.objectContaining({ timeoutMs: 300_000 })
    );
  });

  it('tool handler returns isError=true when executor reports failure', async () => {
    // Override the mock for this test
    const { executeRdcCommand } = await import('../executor.js');
    vi.mocked(executeRdcCommand).mockResolvedValueOnce({
      success: false,
      command: 'machine info bad',
      data: null,
      errors: [{ code: 'NOT_FOUND', message: 'Machine not found' }],
      warnings: [],
      duration_ms: 100,
    });

    let capturedHandler: ((args: Record<string, unknown>) => Promise<unknown>) | null = null;
    const mockServer = {
      registerTool: (_name: string, _config: unknown, handler: unknown) => {
        capturedHandler ??= handler as typeof capturedHandler;
      },
    };

    registerAllTools(mockServer as never, { defaultTimeoutMs: 120_000 });

    const result = (await capturedHandler!({ name: 'bad' })) as {
      content: { type: string; text: string }[];
      isError: boolean;
    };

    expect(result.isError).toBe(true);

    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.success).toBe(false);
    expect(parsed.errors[0].code).toBe('NOT_FOUND');
  });
});
