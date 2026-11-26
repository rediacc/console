import type { ServerContext } from '@modelcontextprotocol/server';

/** The request context of a first call with no elicitation reply, for tests that call a registered handler directly. */
export const FIRST_CALL_CTX = {
  mcpReq: {
    inputResponses: undefined,
    envelope: undefined,
    requestState: () => undefined,
  },
} as unknown as ServerContext;
