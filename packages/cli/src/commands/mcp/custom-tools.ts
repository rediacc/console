/**
 * Custom MCP tool definitions that cannot be auto-derived from the Commander tree.
 *
 * These are tools that either:
 * - Map one CLI command to multiple MCP tools (virtual tools for machine query views)
 * - Have completely custom schema/builder logic
 */
import { z } from 'zod';
import { READ_TIMEOUT, WRITE_TIMEOUT } from '../../config/command-metadata.js';
import type { ToolDef } from './tool-factory.js';

/**
 * Virtual tools for `machine status` — each exposes a specific section flag as a
 * dedicated MCP tool. The underlying CLI command is `machine status <name> --<flag>`.
 */
const MACHINE_STATUS_VIEWS: ToolDef[] = [
  {
    name: 'machine_containers',
    description:
      'List Docker containers on a machine. JSON includes full container details (labels, port_mappings, image), repository resolved to name (original in repository_guid), domain, and autoRoute ({service}.{repo}.{machine}.{baseDomain})',
    schema: { name: z.string().describe('Machine name') },
    command: (args) => ['machine', 'status', args.name as string, '--containers'],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'machine_services',
    description:
      'List rediacc-managed systemd services on a machine (name, state, sub-state, restart count, memory, repository resolved to name with original in repository_guid)',
    schema: { name: z.string().describe('Machine name') },
    command: (args) => ['machine', 'status', args.name as string, '--services'],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'machine_repos',
    description:
      "List deployed repositories on a machine. JSON includes name (resolved from GUID, original in guid field), nests each repo's containers (with domain, autoRoute, repository resolved) and services for hierarchical view",
    schema: { name: z.string().describe('Machine name') },
    command: (args) => ['machine', 'status', args.name as string, '--repositories'],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'machine_health',
    description: 'Run health check on a machine (system, containers, services, storage)',
    schema: { name: z.string().describe('Machine name') },
    command: (args) => ['machine', 'status', args.name as string, '--system'],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
  },
];

/** All custom MCP tools that are not auto-derived from Commander. */
// ★ TERM_EXEC is GONE (w2b). It built `term connect -m <machine> [-r <repo>] -c
// <cmd>`, and `-m`/`-r` no longer exist: the tool's argv became invalid the moment
// `term connect` took a positional target, and nothing caught it, because the MCP
// tests assert the argv a tool BUILDS, never that the CLI ACCEPTS it. Its repo case
// is now `repo exec` (a real, auto-derived leaf). Its bare-MACHINE case is removed
// on purpose (spec §5.8): an arbitrary command on a machine with no repo is the
// escape hatch `run` already is, and `run` is an absolute agent block.
export const CUSTOM_TOOLS: ToolDef[] = [...MACHINE_STATUS_VIEWS];
