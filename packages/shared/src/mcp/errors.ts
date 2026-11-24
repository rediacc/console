/**
 * The error codes an MCP tool result can carry in `structuredContent.code` (PLAN-rmcp-local-mcp Design 1).
 *
 * Two families: the MCP-layer codes below, which the stdio server and the hosted Worker raise themselves, and the CLI contract's error codes, which a tool result passes through from the `rdc` run. The generated registry carries the contract family (`contractErrorCodes`), so a consumer needs no second copy of the contract.
 */

/** Codes the MCP layer raises itself, never the `rdc` child. `BUSY` is not here: it is already a contract code (the serve dispatcher's refusal while another command runs), so it arrives through the contract family. */
export const MCP_LAYER_ERROR_CODES = [
  'REDIACC_GRANT_EXPIRED',
  'REDIACC_GRANT_REVOKED',
  'REDIACC_KEY_ROTATED',
  'POLICY_DENIED',
  'NEEDS_CONFIRMATION',
] as const;

export type McpLayerErrorCode = (typeof MCP_LAYER_ERROR_CODES)[number];

const LAYER_SET: ReadonlySet<string> = new Set(MCP_LAYER_ERROR_CODES);

/** Is `code` one of the MCP-layer codes? */
export function isMcpLayerErrorCode(code: string): code is McpLayerErrorCode {
  return LAYER_SET.has(code);
}
