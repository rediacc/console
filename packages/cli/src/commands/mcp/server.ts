import type { Transport } from '@modelcontextprotocol/server';
import { McpServer } from '@modelcontextprotocol/server';
import { type StdioServerHandle, serveStdio } from '@modelcontextprotocol/server/stdio';
import { writeStderr } from '../../services/core/request-context.js';
import { VERSION } from '../../version.js';
import { registerAllTools } from './tools.js';

export interface McpServerOptions {
  configName?: string;
  defaultTimeoutMs: number;
}

/** One server instance with every tool registered; `serveStdio` pins one per connection. */
function createMcpServer(options: McpServerOptions): McpServer {
  const server = new McpServer({ name: 'rdc', version: VERSION }, { capabilities: { tools: {} } });
  registerAllTools(server, options);
  return server;
}

/**
 * Serve MCP over stdio (SDK v2). `serveStdio` answers `server/discover` for a 2026-07-28 client and
 * serves a 2025-era `initialize` opening from the same factory. The process runs until the client
 * closes stdin. `transport` replaces the process stdio (tests pass an in-memory pair).
 */
export function startMcpServer(
  options: McpServerOptions,
  transport?: Transport
): StdioServerHandle {
  return serveStdio(() => createMcpServer(options), {
    ...(transport ? { transport } : {}),
    onerror: (error) => writeStderr(`rdc mcp: ${error.message}\n`),
  });
}
