/**
 * Result paging for MCP tool results (agent/plans/PLAN-rmcp-local-mcp.md Design 6), shared by the local stdio server (commands/mcp/tools.ts) and the executor's hosted call route (mcp-call-route.ts), so a call answers the same pages whichever way it arrived (D18).
 */
import type { CallToolResult } from '@modelcontextprotocol/server';

/**
 * The largest text one tool result carries (Design 6). It stays under the 150,000-character cap claude.ai puts
 * on a tool result; a longer result is cut into pages of this size.
 */
export const RESULT_PAGE_CHARS = 100_000;

/**
 * Cut a result's text to one page. A text within one page passes through untouched; a longer one returns the
 * requested page plus a second block naming the page count and the next page's cursor. A tool without a `page`
 * argument returns its first page marked `truncated`, with no cursor to follow.
 */
export function pageOf(
  text: string,
  page: number,
  pageable: boolean,
  isError: boolean
): CallToolResult {
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
