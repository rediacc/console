import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { VERSION } from '../../version.js';
import { registerAllTools } from './tools.js';

export interface McpServerOptions {
  configName?: string;
  defaultTimeoutMs: number;
  allowGrand?: boolean;
}

export async function startMcpServer(options: McpServerOptions): Promise<void> {
  const server = new McpServer({
    name: 'rdc',
    version: VERSION,
  });

  registerAllTools(server, options);

  const transport = new StdioServerTransport();
  await server.connect(transport);

  // Server runs until the transport is closed (parent process exits)
}
