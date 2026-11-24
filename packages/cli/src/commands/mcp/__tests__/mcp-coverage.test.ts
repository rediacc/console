/**
 * MCP Tool Coverage Test
 *
 * Ensures every CLI command group in the command registry
 * has at least one corresponding MCP tool or an explicit exclusion reason
 * in COMMAND_METADATA. Fails CI when a command is added to the registry
 * but not covered.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { CLI_CONTRACT } from '@rediacc/shared/cli-contract';
import { describe, expect, it } from 'vitest';
import { cli } from '../../../cli.js';
import {
  COMMAND_METADATA,
  type CommandMeta,
  getCommandMeta,
  getMcpExclusions,
  type McpSurface,
} from '../../../config/command-metadata.js';
import { buildToolsFromContract } from '../tool-factory.js';
import { buildAllTools } from '../tools.js';

const TOOLS = buildAllTools();
const MCP_EXCLUDED = getMcpExclusions();

/**
 * Extract the CLI command path each MCP tool maps to.
 * e.g., repo_up → "repo up", machine_query → "machine query"
 */
function getMcpCommandPaths(): Set<string> {
  const paths = new Set<string>();
  for (const tool of TOOLS) {
    const argv = tool.command({
      name: 'x',
      machine: 'x',
      size: '1G',
      command: 'x',
      parent: 'x',
      tag: 'x',
      repo: 'x',
      storage: 'x',
      storageName: 'x',
    });
    // Take command words before the first argument value 'x'
    const cmdParts: string[] = [];
    for (const part of argv) {
      if (part === 'x' || part.startsWith('-')) break;
      cmdParts.push(part);
    }
    paths.add(cmdParts.join(' '));
  }
  return paths;
}

/** Get just the top-level prefixes (first word of each path). */
function getMcpPrefixes(paths: Set<string>): Set<string> {
  const prefixes = new Set<string>();
  for (const path of paths) {
    prefixes.add(path.split(' ')[0]);
  }
  return prefixes;
}

/**
 * Walk the REAL Commander tree to leaf command paths (same skip rules as
 * tool-factory: no help, no hidden). The registry is NOT the ground truth for
 * coverage, it only declares top-level domains, so registry-keyed checks let
 * unregistered leaves drift out of MCP silently.
 */
function walkLeafPaths(): string[] {
  const leaves: string[] = [];
  function walk(cmd: (typeof cli.commands)[number], prefix: string): void {
    const path = prefix ? `${prefix} ${cmd.name()}` : cmd.name();
    const visible = cmd.commands.filter(
      (sub) =>
        sub.name() !== 'help' &&
        !(sub as (typeof cli.commands)[number] & { _hidden?: boolean })._hidden
    );
    // ★ An ACTIONABLE PARENT is runnable and therefore must be classified too. `repo replicate <ref>` has subcommands AND its own action (spec/03 §5.4 keeps its bare create form). A leaves-only walk cannot see it, which is how it carried an `mcp` block that produced no tool at all: the gate was satisfied by a declaration that did nothing.
    const runnable =
      visible.length === 0 ||
      typeof (cmd as (typeof cli.commands)[number] & { _actionHandler?: unknown })
        ._actionHandler === 'function';
    if (runnable) leaves.push(path);
    for (const sub of visible) walk(sub, path);
  }
  for (const cmd of cli.commands) {
    if (cmd.name() === 'help') continue;
    if ((cmd as (typeof cli.commands)[number] & { _hidden?: boolean })._hidden) continue;
    walk(cmd, '');
  }
  return leaves;
}

/** A path is excluded if it or ANY ancestor prefix carries mcpExcludeReason. */
function isExcluded(path: string): boolean {
  const parts = path.split(' ');
  for (let i = parts.length; i >= 1; i--) {
    if (parts.slice(0, i).join(' ') in MCP_EXCLUDED) return true;
  }
  return false;
}

describe('MCP tool coverage', () => {
  const mcpPaths = getMcpCommandPaths();
  const mcpPrefixes = getMcpPrefixes(mcpPaths);

  it('every visible leaf command has MCP metadata or an explicit exclusion (tree-walk)', () => {
    const missing = walkLeafPaths().filter((path) => {
      if (isExcluded(path)) return false;
      // A path with no metadata entry at all is exactly what this test hunts for.
      if (!Object.hasOwn(COMMAND_METADATA, path)) return true;
      return !COMMAND_METADATA[path].mcp;
    });

    if (missing.length > 0) {
      const hint = missing
        .map(
          (path) => `  - "${path}": add MCP metadata in command-metadata.ts OR add mcpExcludeReason`
        )
        .join('\n');
      expect.fail(
        `${missing.length} visible leaf command(s) missing from MCP (drift — new commands must opt in or out):\n${hint}`
      );
    }
  });

  it('exclusion list has no stale entries', () => {
    // Validate against the real Commander tree (the registry only declares top-level domains, not every subcommand).
    const actualPaths = new Set<string>();
    function walk(cmd: (typeof cli.commands)[number], prefix: string): void {
      const path = prefix ? `${prefix} ${cmd.name()}` : cmd.name();
      actualPaths.add(path);
      for (const sub of cmd.commands) {
        if (sub.name() === 'help') continue;
        walk(sub, path);
      }
    }
    for (const cmd of cli.commands) {
      if (cmd.name() === 'help') continue;
      walk(cmd, '');
    }

    const stale = Object.keys(MCP_EXCLUDED).filter((name) => !actualPaths.has(name));

    if (stale.length > 0) {
      expect.fail(`MCP exclusions have entries not in the CLI command tree: ${stale.join(', ')}`);
    }
  });

  it('exclusion list has no entries that already have MCP tools', () => {
    const redundant = Object.keys(MCP_EXCLUDED).filter(
      (name) => mcpPrefixes.has(name) || mcpPaths.has(name)
    );

    if (redundant.length > 0) {
      expect.fail(
        `MCP exclusions overlap with MCP tools (remove mcpExcludeReason): ${redundant.join(', ')}`
      );
    }
  });

  it('all exclusions have non-empty reasons', () => {
    for (const [name, reason] of Object.entries(MCP_EXCLUDED)) {
      expect(reason.length, `${name} exclusion has empty reason`).toBeGreaterThan(0);
    }
  });

  it('no COMMAND_METADATA entry has both mcp and mcpExcludeReason', () => {
    const conflicts: string[] = [];
    for (const [path, meta] of Object.entries(COMMAND_METADATA)) {
      if (meta.mcp && meta.mcpExcludeReason) {
        conflicts.push(path);
      }
    }
    if (conflicts.length > 0) {
      expect.fail(`Entries with both mcp and mcpExcludeReason: ${conflicts.join(', ')}`);
    }
  });
});

/**
 * The re-sourcing contract itself: buildToolsFromContract must derive exactly one
 * tool for every mcp-annotated contract command, none for an excluded one, and
 * nothing that does not trace back to such a command. This is the assertion that
 * would catch the derivation drifting away from the contract it now reads from
 * (an exclusion being ignored,
 * a stray tool with no backing command).
 */
describe('contract-sourced tool derivation', () => {
  const autoTools = buildToolsFromContract();
  const autoNames = new Set(autoTools.map((t) => t.name));
  const toolName = (pathKey: string): string => pathKey.replaceAll(' ', '_');

  it('every mcp-annotated contract command produces exactly one tool', () => {
    for (const cmd of CLI_CONTRACT.commands) {
      if (!getCommandMeta(cmd.pathKey)?.mcp) continue;
      const name = toolName(cmd.pathKey);
      const matches = autoTools.filter((t) => t.name === name);
      expect(matches.length, `${cmd.pathKey} should derive exactly one tool "${name}"`).toBe(1);
    }
  });

  it('no mcp-excluded command produces an auto-derived tool', () => {
    for (const cmd of CLI_CONTRACT.commands) {
      if (!getCommandMeta(cmd.pathKey)?.mcpExcludeReason) continue;
      const name = toolName(cmd.pathKey);
      expect(autoNames.has(name), `${cmd.pathKey} is excluded but produced tool "${name}"`).toBe(
        false
      );
    }
  });

  it('every auto-derived tool traces back to an mcp-annotated command', () => {
    for (const tool of autoTools) {
      const cmd = CLI_CONTRACT.commands.find((c) => toolName(c.pathKey) === tool.name);
      expect(cmd, `tool "${tool.name}" has no backing contract command`).toBeDefined();
      expect(
        getCommandMeta(cmd!.pathKey)?.mcp,
        `tool "${tool.name}" backs a command with no mcp metadata`
      ).toBeTruthy();
    }
  });
});

/**
 * The surface table (PLAN-rmcp-local-mcp LM2, decision D57). Every MCP entry names where it is served; a tool whose command is not proxyCapable carries an `executor` or `in-memory` verdict, or `local` on one of the two bases D57 admits, and .ci/config/mcp-surface.json records the same verdict for exactly those tools.
 */
const SURFACE_TABLE_PATH = fileURLToPath(
  new URL('../../../../../../.ci/config/mcp-surface.json', import.meta.url)
);
const LOCAL_BASES = new Set(['caller-disk', 'terminal']);

interface SurfaceRow {
  plane?: string;
  verdict?: string;
  basis?: string;
  reason?: string;
  commandChange?: string;
}

/** Problems of one entry's marker: a missing or stray marker, a verdict without a reason, a local basis D57 does not admit. */
function entryMarkerProblems(path: string, meta: CommandMeta): string[] {
  const surface = meta.mcpSurface;
  if (!meta.mcp) return surface ? [`${path}: mcpSurface without mcp`] : [];
  if (!surface) return [`${path}: mcp without mcpSurface`];
  if (surface.kind === 'proxy') return [];
  const problems: string[] = [];
  if (!surface.reason.trim()) problems.push(`${path}: ${surface.kind} without a reason`);
  if (surface.kind === 'local' && !LOCAL_BASES.has(surface.basis)) {
    problems.push(
      `${path}: local on basis "${String(surface.basis)}", not caller-disk or terminal`
    );
  }
  return problems;
}

function markerProblems(metadata: Record<string, CommandMeta>): string[] {
  return Object.entries(metadata).flatMap(([path, meta]) => entryMarkerProblems(path, meta));
}

/** Problems of one non-proxy tool's table row against its marker. */
function rowProblems(path: string, surface: McpSurface, row: SurfaceRow | undefined): string[] {
  if (!row) return [`${path}: not proxyCapable and missing from mcp-surface.json`];
  if (surface.kind === 'proxy') return [];
  const problems: string[] = [];
  if (row.verdict !== surface.kind) {
    problems.push(`${path}: table verdict ${String(row.verdict)} != mcpSurface ${surface.kind}`);
  }
  if (row.reason !== surface.reason) {
    problems.push(`${path}: table reason differs from mcpSurface reason`);
  }
  const basis = surface.kind === 'local' ? surface.basis : undefined;
  if (row.basis !== basis) {
    problems.push(`${path}: table basis ${String(row.basis)} != ${String(basis)}`);
  }
  if (surface.kind !== 'local' && !row.commandChange?.trim()) {
    problems.push(`${path}: ${surface.kind} without the LM10 commandChange`);
  }
  return problems;
}

/** Problems of one MCP tool: its marker against the contract, then its table row when it is not proxyCapable. */
function toolTableProblems(
  path: string,
  surface: McpSurface,
  capable: boolean,
  row: SurfaceRow | undefined
): string[] {
  const problems: string[] = [];
  if (capable !== (surface.kind === 'proxy')) {
    problems.push(`${path}: mcpSurface ${surface.kind} but proxyCapable ${String(capable)}`);
  }
  if (!capable) problems.push(...rowProblems(path, surface, row));
  return problems;
}

/** Problems between the markers, the contract and the recorded table. */
function tableProblems(
  metadata: Record<string, CommandMeta>,
  table: Record<string, SurfaceRow>,
  proxyCapable: Map<string, boolean>
): string[] {
  const problems: string[] = [];
  const expected = new Set<string>();
  for (const [path, meta] of Object.entries(metadata)) {
    const surface = meta.mcp ? meta.mcpSurface : undefined;
    const capable = proxyCapable.get(path);
    if (!surface || capable === undefined) continue;
    if (!capable) expected.add(path);
    problems.push(...toolTableProblems(path, surface, capable, table[path]));
  }
  const strays = Object.keys(table).filter((path) => !expected.has(path));
  problems.push(
    ...strays.map((path) => `${path}: in mcp-surface.json but not a non-proxy MCP tool`)
  );
  return problems;
}

describe('MCP surface table (D57)', () => {
  const table = (
    JSON.parse(readFileSync(SURFACE_TABLE_PATH, 'utf-8')) as { tools: Record<string, SurfaceRow> }
  ).tools;
  const proxyCapable = new Map(CLI_CONTRACT.commands.map((c) => [c.pathKey, c.proxyCapable]));

  it('every MCP entry carries mcpSurface, and every verdict its reason', () => {
    expect(markerProblems(COMMAND_METADATA)).toEqual([]);
  });

  it('mcp-surface.json holds exactly the non-proxy MCP tools, each with the marker verdict', () => {
    expect(tableProblems(COMMAND_METADATA, table, proxyCapable)).toEqual([]);
  });

  it('refuses an MCP entry without mcpSurface and a local entry off the two bases', () => {
    const bad: Record<string, CommandMeta> = {
      'a b': { mcp: { destructive: false, idempotent: true, timeout: 'read' } },
      'c d': {
        mcp: { destructive: false, idempotent: true, timeout: 'read' },
        mcpSurface: {
          kind: 'local',
          basis: 'meaningless-remotely' as 'terminal',
          reason: 'not useful',
        },
      },
      'e f': { mcpSurface: { kind: 'proxy' } },
      'g h': {
        mcp: { destructive: false, idempotent: true, timeout: 'read' },
        mcpSurface: { kind: 'in-memory', reason: ' ' },
      },
    };
    expect(markerProblems(bad)).toEqual([
      'a b: mcp without mcpSurface',
      'c d: local on basis "meaningless-remotely", not caller-disk or terminal',
      'e f: mcpSurface without mcp',
      'g h: in-memory without a reason',
    ]);
  });

  it('refuses a table that drifts from the markers or the contract', () => {
    const mcp = { destructive: false, idempotent: true, timeout: 'read' } as const;
    const meta: Record<string, CommandMeta> = {
      'x one': { mcp, mcpSurface: { kind: 'executor', reason: 'r1' } },
      'x two': { mcp, mcpSurface: { kind: 'proxy' } },
      'x three': { mcp, mcpSurface: { kind: 'local', basis: 'terminal', reason: 'r3' } },
    };
    const capable = new Map([
      ['x one', false],
      ['x two', false],
      ['x three', false],
    ]);
    const drifted: Record<string, SurfaceRow> = {
      'x one': { verdict: 'in-memory', reason: 'other' },
      'x three': { verdict: 'local', basis: 'terminal', reason: 'r3' },
      'x stray': { verdict: 'executor', reason: 'r', commandChange: 'c' },
    };
    expect(tableProblems(meta, drifted, capable)).toEqual([
      'x one: table verdict in-memory != mcpSurface executor',
      'x one: table reason differs from mcpSurface reason',
      'x one: executor without the LM10 commandChange',
      'x two: mcpSurface proxy but proxyCapable false',
      'x two: not proxyCapable and missing from mcp-surface.json',
      'x stray: in mcp-surface.json but not a non-proxy MCP tool',
    ]);
  });
});
