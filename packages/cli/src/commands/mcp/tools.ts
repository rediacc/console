import type { McpServer } from '@modelcontextprotocol/server';
import { z } from 'zod';
import { CUSTOM_TOOLS } from './custom-tools.js';
import { executeRdcCommand } from './executor.js';
import type { McpServerOptions } from './server.js';
import { buildToolsFromContract, type ToolDef, toolAnnotations } from './tool-factory.js';

export type { ToolDef } from './tool-factory.js';

type ToolResult = { content: [{ type: 'text'; text: string }]; isError: boolean };

/** Build the complete list of MCP tools (contract-derived + custom). */
export function buildAllTools(): ToolDef[] {
  return [...buildToolsFromContract(), ...CUSTOM_TOOLS];
}

/**
 * Execute a tool call via the rdc child process and format the MCP response.
 *
 * No repo guard runs here (agent/plans/PLAN-rmcp-decide.md Design 3): the child runs with
 * `REDIACC_AGENT=1` (executor.ts) and meets the CLI's own command-policy check, so an MCP call and
 * the same command typed by an agent get one check and one answer.
 */
async function executeTool(
  tool: ToolDef,
  args: Record<string, unknown>,
  options: McpServerOptions
): Promise<ToolResult> {
  const argv = tool.command(args);
  const result = await executeRdcCommand(argv, {
    ...options,
    timeoutMs: tool.timeoutMs ?? options.defaultTimeoutMs,
    ...(tool.attachWindowMs !== undefined && args.background === true ? { background: true } : {}),
  });
  return {
    content: [{ type: 'text' as const, text: JSON.stringify(result, null, 2) }],
    isError: !result.success,
  };
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
