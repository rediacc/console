/**
 * The remote MCP Worker, one per region at `mcp.<region>.rediacc.cloud` (agent/plans/PLAN-rmcp-remote-worker.md).
 *
 * The handler lives in `packages/shared/src/mcp-host/handler.ts`, where the Node host shares it (RW-OP1); this entry only binds it to Cloudflare: the default export serves requests and `GrantRateObject` is the Durable Object class `wrangler` binds as `RATE`.
 */
export {
  default,
  type Env,
  GrantRateObject,
} from '../../../packages/shared/src/mcp-host/handler.js';
