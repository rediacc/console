/**
 * Custom MCP tool definitions that cannot be auto-derived from the Commander tree.
 *
 * These are tools that either:
 * - Map one CLI command to multiple MCP tools (virtual tools for machine query views)
 * - Have completely custom schema/builder logic (term_exec)
 */
import { z } from 'zod';
import { READ_TIMEOUT, WRITE_TIMEOUT } from '../../config/command-metadata.js';
import type { ToolDef } from './tool-factory.js';

/**
 * Virtual tools for `machine query` — each exposes a specific flag as a dedicated MCP tool.
 * The underlying CLI command is `machine query <name> --<flag>`.
 */
const MACHINE_QUERY_VIEWS: ToolDef[] = [
  {
    name: 'machine_containers',
    description:
      'List Docker containers on a machine. JSON includes full container details (labels, port_mappings, image), repository resolved to name (original in repository_guid), domain, and autoRoute ({service}.{repo}.{machine}.{baseDomain})',
    schema: { name: z.string().describe('Machine name') },
    command: (args) => ['machine', 'query', args.name as string, '--containers'],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'machine_services',
    description:
      'List rediacc-managed systemd services on a machine (name, state, sub-state, restart count, memory, repository resolved to name with original in repository_guid)',
    schema: { name: z.string().describe('Machine name') },
    command: (args) => ['machine', 'query', args.name as string, '--services'],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'machine_repos',
    description:
      "List deployed repositories on a machine. JSON includes name (resolved from GUID, original in guid field), nests each repo's containers (with domain, autoRoute, repository resolved) and services for hierarchical view",
    schema: { name: z.string().describe('Machine name') },
    command: (args) => ['machine', 'query', args.name as string, '--repositories'],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
  },
  {
    name: 'machine_health',
    description: 'Run health check on a machine (system, containers, services, storage)',
    schema: { name: z.string().describe('Machine name') },
    command: (args) => ['machine', 'query', args.name as string, '--system'],
    isDestructive: false,
    isIdempotent: true,
    timeoutMs: READ_TIMEOUT,
  },
];

/** Build argv for term_exec: term <machine> [repository] -c <command> */
function buildTermExecArgv(args: Record<string, unknown>): string[] {
  const argv = ['term', args.machine as string];
  if (args.repository) argv.push(args.repository as string);
  argv.push('-c', args.command as string);
  return argv;
}

/**
 * term_exec — custom tool for executing commands via SSH.
 * Cannot be auto-derived because it combines positional args + specific option
 * into a curated schema with different semantics than the full `term` command.
 */
const TERM_EXEC: ToolDef = {
  name: 'term_exec',
  description: 'Execute a command on a remote machine or repository via SSH',
  schema: {
    machine: z.string().describe('Machine name'),
    repository: z
      .string()
      .optional()
      .describe('Repository name (required for docker/repo commands)'),
    command: z.string().describe('Command to execute'),
  },
  command: buildTermExecArgv,
  isDestructive: true,
  isIdempotent: false,
  timeoutMs: WRITE_TIMEOUT,
  repoArgField: 'repository',
};

/** All custom MCP tools that are not auto-derived from Commander. */
export const CUSTOM_TOOLS: ToolDef[] = [...MACHINE_QUERY_VIEWS, TERM_EXEC];
