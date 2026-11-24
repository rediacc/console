/**
 * The one MCP tool registry (PLAN-rmcp-local-mcp Design 1).
 *
 * `tools.generated.json` is written by packages/cli/scripts/generate-mcp-registry.ts from the CLI contract, COMMAND_METADATA and the hand-declared machine_* views, and `--check` fails on drift. The local stdio server (`rdc mcp serve`) and the hosted MCP Worker both build `tools/list` from it; the Worker serves only `surface === 'proxy'` (see {@link listProxyTools}).
 *
 * The JSON is parsed once at module load through {@link parseMcpRegistry}, so a malformed file throws here rather than reaching a client as a broken tool.
 */

import { isMcpLayerErrorCode } from './errors.js';
import {
  type McpErrorCode,
  type McpRegistry,
  type McpToolEntry,
  parseMcpRegistry,
} from './schema.js';
import data from './tools.generated.json' with { type: 'json' };

export type { McpErrorCode, McpRegistry, McpToolEntry } from './schema.js';
export { mcpRegistryProblems, parseMcpRegistry } from './schema.js';

export const MCP_REGISTRY: McpRegistry = parseMcpRegistry(data);

const BY_NAME = new Map(MCP_REGISTRY.tools.map((tool) => [tool.name, tool]));
const CONTRACT_CODES: ReadonlySet<string> = new Set(MCP_REGISTRY.contractErrorCodes);

/** Every tool, sorted by name. */
export function listMcpTools(): readonly McpToolEntry[] {
  return MCP_REGISTRY.tools;
}

/** The tools the hosted Worker serves. */
export function listProxyTools(): readonly McpToolEntry[] {
  return MCP_REGISTRY.tools.filter((tool) => tool.surface === 'proxy');
}

/** One tool by name, or undefined. */
export function getMcpTool(name: string): McpToolEntry | undefined {
  return BY_NAME.get(name);
}

/** Is `code` a code a tool result may carry (an MCP-layer code or a contract code)? */
export function isMcpErrorCode(code: string): code is McpErrorCode {
  return isMcpLayerErrorCode(code) || CONTRACT_CODES.has(code);
}
