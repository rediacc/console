/** The bounds of one `job_wait` call, shared by the local MCP tool (commands/mcp/custom-tools.ts) and the served call route (mcp-call-route.ts), so the service layer does not import a command module. */

/** One job_wait call blocks at most this long (Design 5), well inside a client's 60 s tool budget. */
export const JOB_WAIT_CEILING_MS = 50_000;
/** The pause between two `job status` reads, and the `nextPollSeconds` a call that hits the ceiling returns. */
export const JOB_WAIT_INTERVAL_MS = 5_000;
