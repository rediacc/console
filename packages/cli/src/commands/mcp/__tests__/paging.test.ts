/**
 * Result paging (PLAN-rmcp-local-mcp LM6, Design 6): a result above RESULT_PAGE_CHARS returns one page plus a
 * cursor, and the `page` argument of job_logs, repo_logs and config_audit_log reads the rest.
 */
import { describe, expect, it, vi } from 'vitest';
import { buildAllTools, RESULT_PAGE_CHARS, registerAllTools } from '../tools.js';

vi.mock('../executor.js', () => ({
  executeRdcCommand: vi.fn(),
  resolveRdcBinary: () => ({ command: 'node', prefixArgs: ['index.js'] }),
  runUnderPolicy: async (_call: unknown, run: (confirm: undefined) => Promise<unknown>) => ({
    result: await run(undefined),
  }),
}));

type Handler = (args: Record<string, unknown>) => Promise<{
  content: { type: string; text: string }[];
  isError: boolean;
}>;

function handlerFor(name: string): Handler {
  let found: Handler | undefined;
  registerAllTools(
    {
      registerTool: (toolName: string, _config: unknown, handler: Handler) => {
        if (toolName === name) found = handler;
      },
    } as never,
    { defaultTimeoutMs: 120_000 }
  );
  if (!found) throw new Error(`no MCP tool ${name}`);
  return found;
}

/** Make the executor return a log of `chars` characters; returns the full text one call would carry. */
async function logOf(chars: number): Promise<{ full: string; argvs: string[][] }> {
  const { executeRdcCommand } = await import('../executor.js');
  const envelope = {
    success: true,
    command: 'job logs j-1',
    data: 'x'.repeat(chars),
    errors: null,
    warnings: [],
    duration_ms: 1,
  };
  const argvs: string[][] = [];
  vi.mocked(executeRdcCommand).mockReset();
  vi.mocked(executeRdcCommand).mockImplementation((argv) => {
    argvs.push(argv);
    return Promise.resolve(envelope);
  });
  return { full: JSON.stringify(envelope, null, 2), argvs };
}

function pagingOf(result: Awaited<ReturnType<Handler>>) {
  return JSON.parse(result.content[1].text).paging;
}

describe('MCP result paging', () => {
  it('a 300,000-character log pages in three calls that rebuild the whole text', async () => {
    const { full, argvs } = await logOf(300_000 - 200);
    expect(full.length).toBeGreaterThan(2 * RESULT_PAGE_CHARS);
    expect(full.length).toBeLessThanOrEqual(3 * RESULT_PAGE_CHARS);
    const logs = handlerFor('job_logs');

    const first = await logs({ 'job-id': 'j-1' });
    expect(pagingOf(first)).toEqual({ page: 1, pages: 3, totalChars: full.length, cursor: 2 });
    const second = await logs({ 'job-id': 'j-1', page: 2 });
    expect(pagingOf(second).cursor).toBe(3);
    const third = await logs({ 'job-id': 'j-1', page: 3 });
    expect(pagingOf(third).cursor).toBeNull();

    for (const r of [first, second, third]) {
      expect(r.isError).toBe(false);
      expect(r.content[0].text.length).toBeLessThanOrEqual(RESULT_PAGE_CHARS);
    }
    expect(first.content[0].text + second.content[0].text + third.content[0].text).toBe(full);
    // `page` is the MCP layer's own argument; it never reaches the rdc argv.
    for (const argv of argvs) expect(argv).toEqual(['job', 'logs', 'j-1']);
  });

  it('a page past the last is refused', async () => {
    await logOf(300_000 - 200);
    const result = await handlerFor('job_logs')({ 'job-id': 'j-1', page: 4 });
    expect(result.isError).toBe(true);
    expect(JSON.parse(result.content[0].text).errors[0].message).toContain(
      'past the last page (3)'
    );
  });

  it('control: a result within one page passes through as one untouched block', async () => {
    const { full } = await logOf(500);
    const result = await handlerFor('job_logs')({ 'job-id': 'j-1' });
    expect(result.content).toEqual([{ type: 'text', text: full }]);
  });

  it('a tool without a page argument returns its first page marked truncated, with no cursor', async () => {
    const { full } = await logOf(250_000);
    const result = await handlerFor('repo_status')({ ref: 'app' });
    expect(result.content[0].text).toBe(full.slice(0, RESULT_PAGE_CHARS));
    expect(pagingOf(result)).toEqual({
      page: 1,
      pages: 3,
      totalChars: full.length,
      truncated: true,
      cursor: null,
    });
  });

  it('exactly job_logs, repo_logs and config_audit_log take a page argument', () => {
    const paged = buildAllTools()
      .filter((t) => 'page' in t.schema)
      .map((t) => t.name)
      .sort((a, b) => a.localeCompare(b));
    expect(paged).toEqual(['config_audit_log', 'job_logs', 'repo_logs']);
  });

  it('the page argument tells a client that each page re-runs the command', () => {
    const pageable = buildAllTools().filter((t) => 'page' in t.schema);
    expect(pageable).toHaveLength(3);
    for (const tool of pageable) {
      const field = tool.schema.page as { description?: string } | undefined;
      expect(field?.description, tool.name).toContain('re-runs the command');
    }
  });
});
