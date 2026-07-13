/**
 * MCP Tool Coverage Test
 *
 * Ensures every non-experimental CLI command group in the command registry
 * has at least one corresponding MCP tool or an explicit exclusion reason
 * in COMMAND_METADATA. Fails CI when a command is added to the registry
 * but not covered.
 */
import { describe, expect, it } from 'vitest';
import { cli } from '../../../cli.js';
import { COMMAND_METADATA, getMcpExclusions } from '../../../config/command-metadata.js';
import { COMMAND_REGISTRY } from '../../../config/command-registry.js';
import { buildAllTools } from '../tools.js';

const TOOLS = buildAllTools(cli);
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
 * coverage — it only declares top-level domains, so registry-keyed checks let
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
    // ★ An ACTIONABLE PARENT is runnable and therefore must be classified too. `repo replicate
    // <ref>` has subcommands AND its own action (spec/03 §5.4 keeps its bare create form). A
    // leaves-only walk cannot see it, which is how it carried an `mcp` block that produced no
    // tool at all: the gate was satisfied by a declaration that did nothing.
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
  const experimentalPrefixes = new Set(
    COMMAND_REGISTRY.filter((c) => c.experimental).map((c) => c.name)
  );

  it('every visible leaf command has MCP metadata or an explicit exclusion (tree-walk)', () => {
    const missing = walkLeafPaths().filter((path) => {
      if (experimentalPrefixes.has(path.split(' ')[0])) return false;
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
    // Validate against the real Commander tree (the registry only declares
    // top-level domains + experimental overrides, not every subcommand).
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
