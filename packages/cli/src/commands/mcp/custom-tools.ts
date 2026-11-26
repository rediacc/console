/**
 * Custom MCP tool definitions that cannot be auto-derived from the Commander tree.
 *
 * These are tools that either:
 * - Map one CLI command to multiple MCP tools (virtual tools for machine query views)
 * - Have completely custom schema/builder logic
 */
import { z } from 'zod';
import { type McpSurface, READ_TIMEOUT } from '../../config/command-metadata.js';
import { isTerminalState, type JobStatus } from '../../services/executor/job-client.js';
import { JOB_WAIT_CEILING_MS, JOB_WAIT_INTERVAL_MS } from '../../services/serve/job-wait-limits.js';
import type { ToolDef } from './tool-factory.js';

/** The views run `machine status` and job_wait runs `job status`, both proxy-capable; the registry generator checks this against the contract like any other tool. */
const STATUS_SURFACE: McpSurface = { kind: 'proxy' };

/**
 * Virtual tools for `machine status`, each exposes a specific section flag as a
 * dedicated MCP tool. The underlying CLI command is `machine status <name> --<flag>`.
 */
const MACHINE_STATUS_VIEWS: ToolDef[] = [
  {
    name: 'machine_containers',
    description:
      'List Docker containers on a machine. JSON includes full container details (labels, port_mappings, image), repository resolved to name (original in repository_guid), domain, and autoRoute ({service}.{repo}.{machine}.{baseDomain})',
    schema: { name: z.string().describe('Machine name') },
    commandPath: 'machine status',
    command: (args) => ['machine', 'status', args.name as string, '--containers'],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
    timeoutClass: 'read',
    surface: STATUS_SURFACE,
  },
  {
    name: 'machine_services',
    description:
      'List rediacc-managed systemd services on a machine (name, state, sub-state, restart count, memory, repository resolved to name with original in repository_guid)',
    schema: { name: z.string().describe('Machine name') },
    commandPath: 'machine status',
    command: (args) => ['machine', 'status', args.name as string, '--services'],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
    timeoutClass: 'read',
    surface: STATUS_SURFACE,
  },
  {
    name: 'machine_repos',
    description:
      "List deployed repositories on a machine. JSON includes name (resolved from GUID, original in guid field), nests each repo's containers (with domain, autoRoute, repository resolved) and services for hierarchical view",
    schema: { name: z.string().describe('Machine name') },
    commandPath: 'machine status',
    command: (args) => ['machine', 'status', args.name as string, '--repositories'],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
    timeoutClass: 'read',
    surface: STATUS_SURFACE,
  },
];

export { JOB_WAIT_CEILING_MS, JOB_WAIT_INTERVAL_MS };

/** Whether a `job status` envelope's data names a finished job. */
function jobFinished(data: unknown): boolean {
  const state = (data as { state?: unknown } | null)?.state;
  return typeof state === 'string' && isTerminalState(state as JobStatus['state']);
}

/**
 * `job_wait` (PLAN-rmcp-local-mcp LM6): repeat `rdc job status` until the job is terminal or the call nears
 * JOB_WAIT_CEILING_MS. Each read is a full child `rdc` call, so it meets the same command-policy decision as
 * `job_status`. `rdc job wait` itself stays off MCP: it follows the log stream until the job ends and
 * acknowledges the ticket, which no bounded tool call can promise.
 */
const JOB_WAIT: ToolDef = {
  name: 'job_wait',
  description: `Wait up to ${JOB_WAIT_CEILING_MS / 1000} s for a job to finish. Returns the terminal job status, or the latest status with nextPollSeconds while the job still runs; call job_wait again with the same id to keep waiting.`,
  schema: {
    'job-id': z.string().describe('Job ID'),
    machine: z
      .string()
      .optional()
      .describe('Target machine name (optional when this config holds a ticket for the job)'),
  },
  commandPath: 'job status',
  command: (args) => [
    'job',
    'status',
    ...(args['job-id'] === undefined ? [] : [String(args['job-id'])]),
    ...(args.machine === undefined ? [] : ['--machine', String(args.machine)]),
  ],
  isDestructive: false,
  isIdempotent: true,
  timeoutMs: READ_TIMEOUT,
  timeoutClass: 'read',
  surface: STATUS_SURFACE,
  poll: { ceilingMs: JOB_WAIT_CEILING_MS, intervalMs: JOB_WAIT_INTERVAL_MS, done: jobFinished },
};

// ★ machine_health is GONE. It claimed to "run health check on a machine" but its argv was `machine status <name> --system`, a raw system-stats dump that never called the health checker, so an agent asking for health got facts to interpret rather than the aggregated issues[] and exit code. `machine health` is no longer experimental, so the contract-derived tool of the same name
// now runs the real command.

/** All custom MCP tools that are not auto-derived from Commander. */
// ★ TERM_EXEC is GONE (w2b). It built `term connect -m <machine> [-r <repo>] -c <cmd>`, and `-m`/`-r` no longer exist: the tool's argv became invalid the moment `term connect` took a positional target, and nothing caught it, because the MCP tests assert the argv a tool BUILDS, never that the CLI ACCEPTS it. Its repo case is now `repo exec` (a real, auto-derived leaf). Its
// bare-MACHINE case is removed on purpose (spec §5.8): an arbitrary command on a machine with no repo is the escape hatch `run` already is, and `run` is an absolute agent block.
export const CUSTOM_TOOLS: ToolDef[] = [...MACHINE_STATUS_VIEWS, JOB_WAIT];
