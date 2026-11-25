import type { CallToolResult, McpServer } from '@modelcontextprotocol/server';
import { z } from 'zod';
import { CUSTOM_TOOLS } from './custom-tools.js';
import { type ExecutionResult, executeRdcCommand } from './executor.js';
import type { McpServerOptions } from './server.js';
import {
  buildToolsFromContract,
  type ToolDef,
  type ToolPoll,
  toolAnnotations,
} from './tool-factory.js';

export type { ToolDef } from './tool-factory.js';

/**
 * The largest text one tool result carries (Design 6). It stays under the 150,000-character cap claude.ai puts
 * on a tool result; a longer result is cut into pages of this size.
 */
export const RESULT_PAGE_CHARS = 100_000;

/** The tools whose long output an agent reads in full, page by page; each takes a `page` argument. */
const PAGEABLE_TOOLS = new Set(['job_logs', 'repo_logs', 'config_audit_log']);

/** The `page` field of a pageable tool: 1 (the default) is the first page, the cursor of a page names the next. */
const PAGE_FIELD = z
  .number()
  .int()
  .min(1)
  .optional()
  .describe(
    `Page of a result longer than ${RESULT_PAGE_CHARS} characters, from 1; pass the cursor a page returned to read the next one.`
  );

function withPaging(tool: ToolDef): ToolDef {
  if (!PAGEABLE_TOOLS.has(tool.name)) return tool;
  if ('page' in tool.schema) throw new Error(`MCP tool ${tool.name} already has a page field`);
  return { ...tool, schema: { ...tool.schema, page: PAGE_FIELD }, pageable: true };
}

/** Build the complete list of MCP tools (contract-derived + custom). */
export function buildAllTools(): ToolDef[] {
  return [...buildToolsFromContract(), ...CUSTOM_TOOLS].map(withPaging);
}

/** What a polling tool returns: the last run's result, how long the call waited, and the hint when it hit the ceiling. */
interface PolledResult extends Omit<ExecutionResult, 'next'> {
  next?: ExecutionResult['next'] | 'job_wait';
  waited_ms: number;
  nextPollSeconds?: number;
}

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/**
 * Repeat one tool's command until its data is final, it fails, or the next run would pass the ceiling. Each run
 * gets the time left before the ceiling, but never less than two intervals, so one slow read is not killed at once.
 */
async function runPolled(
  poll: ToolPoll,
  run: (timeoutMs: number) => Promise<ExecutionResult>
): Promise<PolledResult> {
  const started = Date.now();
  for (;;) {
    const remaining = poll.ceilingMs - (Date.now() - started);
    const result = await run(Math.max(remaining, poll.intervalMs * 2));
    const waited = Date.now() - started;
    if (!result.success || poll.done(result.data)) return { ...result, waited_ms: waited };
    if (waited + poll.intervalMs >= poll.ceilingMs) {
      return {
        ...result,
        waited_ms: waited,
        next: 'job_wait',
        nextPollSeconds: poll.intervalMs / 1000,
      };
    }
    await sleep(poll.intervalMs);
  }
}

/**
 * Cut a result's text to one page. A text within one page passes through untouched; a longer one returns the
 * requested page plus a second block naming the page count and the next page's cursor. A tool without a `page`
 * argument returns its first page marked `truncated`, with no cursor to follow.
 */
function pageOf(text: string, page: number, pageable: boolean, isError: boolean): CallToolResult {
  if (text.length <= RESULT_PAGE_CHARS && page === 1) {
    return { content: [{ type: 'text', text }], isError };
  }
  const pages = Math.max(1, Math.ceil(text.length / RESULT_PAGE_CHARS));
  if (page > pages) {
    const refusal = {
      success: false,
      errors: [
        { code: 'INVALID_REQUEST', message: `page ${page} is past the last page (${pages})` },
      ],
    };
    return { content: [{ type: 'text', text: JSON.stringify(refusal, null, 2) }], isError: true };
  }
  const slice = text.slice((page - 1) * RESULT_PAGE_CHARS, page * RESULT_PAGE_CHARS);
  const paging = pageable
    ? { page, pages, totalChars: text.length, cursor: page < pages ? page + 1 : null }
    : { page: 1, pages, totalChars: text.length, truncated: true, cursor: null };
  return {
    content: [
      { type: 'text', text: slice },
      { type: 'text', text: JSON.stringify({ paging }) },
    ],
    isError,
  };
}

/**
 * Execute a tool call via the rdc child process and format the MCP response.
 *
 * No repo guard runs here (agent/plans/PLAN-rmcp-decide.md Design 3): the child runs with
 * `REDIACC_AGENT=1` (executor.ts) and meets the CLI's own command-policy check, so an MCP call and
 * the same command typed by an agent get one check and one answer. A polling tool (job_wait) runs
 * the same child call each time.
 */
async function executeTool(
  tool: ToolDef,
  args: Record<string, unknown>,
  options: McpServerOptions
): Promise<CallToolResult> {
  const argv = tool.command(args);
  const run = (timeoutMs: number) =>
    executeRdcCommand(argv, {
      ...options,
      timeoutMs,
      ...(tool.attachWindowMs !== undefined && args.background === true
        ? { background: true }
        : {}),
    });
  const timeoutMs = tool.timeoutMs ?? options.defaultTimeoutMs;
  const result = tool.poll ? await runPolled(tool.poll, run) : await run(timeoutMs);
  const page = tool.pageable && typeof args.page === 'number' ? args.page : 1;
  return pageOf(JSON.stringify(result, null, 2), page, tool.pageable === true, !result.success);
}

export function registerAllTools(server: McpServer, options: McpServerOptions): void {
  const allTools = buildAllTools();

  for (const tool of allTools) {
    server.registerTool(
      tool.name,
      {
        description: tool.description,
        inputSchema: z.object(tool.schema),
        annotations: toolAnnotations(tool),
      },
      async (args: Record<string, unknown>) => executeTool(tool, args, options)
    );
  }
}
