const HELP_FLAGS = new Set(['--help', '-h']);

/**
 * True when argv asks for the stdio MCP server fast path in index.ts. A help flag
 * leaves the fast path so Commander prints the `mcp serve` help instead of the
 * server starting (and blocking on stdin).
 */
export function isMcpServeFastPath(argv: readonly string[]): boolean {
  if (!argv.includes('mcp') || !argv.includes('serve')) return false;
  return !argv.some((arg) => HELP_FLAGS.has(arg));
}
