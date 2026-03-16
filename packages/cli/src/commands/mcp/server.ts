import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import type { Command } from 'commander';
import { VERSION } from '../../version.js';
import { registerAllTools } from './tools.js';

export interface McpServerOptions {
  configName?: string;
  defaultTimeoutMs: number;
  allowGrand?: boolean;
  /** Commander program instance for auto-deriving MCP tools from the command tree. */
  program: Command;
}

export async function startMcpServer(options: McpServerOptions): Promise<void> {
  const server = new McpServer({
    name: 'rdc',
    version: VERSION,
  });

  registerAllTools(server, options.program, options);

  const transport = new StdioServerTransport();
  await server.connect(transport);

  // Server runs until the transport is closed (parent process exits)
}
