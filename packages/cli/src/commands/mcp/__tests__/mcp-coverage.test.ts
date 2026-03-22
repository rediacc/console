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

describe('MCP tool coverage', () => {
  const mcpPaths = getMcpCommandPaths();
  const mcpPrefixes = getMcpPrefixes(mcpPaths);
  const nonExperimental = COMMAND_REGISTRY.filter((c) => !c.experimental);

  it('every non-experimental command is either in MCP tools or explicitly excluded', () => {
    const missing: string[] = [];

    for (const cmd of nonExperimental) {
      const hasMcpTool = mcpPrefixes.has(cmd.name);
      const isExcluded = cmd.name in MCP_EXCLUDED;

      if (!hasMcpTool && !isExcluded) {
        missing.push(cmd.name);
      }
    }

    if (missing.length > 0) {
      const hint = missing
        .map(
          (name) => `  - "${name}": add MCP metadata in command-metadata.ts OR add mcpExcludeReason`
        )
        .join('\n');
      expect.fail(`${missing.length} non-experimental command(s) missing from MCP tools:\n${hint}`);
    }
  });

  it('every non-experimental subcommand is covered by MCP or explicitly excluded', () => {
    const missing = nonExperimental.flatMap((cmd) => {
      if (!cmd.subcommands || cmd.name in MCP_EXCLUDED) return [];
      return Object.entries(cmd.subcommands)
        .filter(([, subDef]) => !subDef.experimental)
        .map(([subName]) => `${cmd.name} ${subName}`)
        .filter((fullPath) => !mcpPaths.has(fullPath) && !(fullPath in MCP_EXCLUDED));
    });

    if (missing.length > 0) {
      const hint = missing
        .map(
          (name) => `  - "${name}": add MCP metadata in command-metadata.ts OR add mcpExcludeReason`
        )
        .join('\n');
      expect.fail(
        `${missing.length} non-experimental subcommand(s) missing from MCP tools:\n${hint}`
      );
    }
  });

  it('exclusion list has no stale entries', () => {
    const registryNames = new Set(COMMAND_REGISTRY.map((c) => c.name));
    const registrySubPaths = new Set<string>();
    for (const cmd of COMMAND_REGISTRY) {
      if (cmd.subcommands) {
        for (const sub of Object.keys(cmd.subcommands)) {
          registrySubPaths.add(`${cmd.name} ${sub}`);
        }
      }
    }

    const stale = Object.keys(MCP_EXCLUDED).filter(
      (name) => !registryNames.has(name) && !registrySubPaths.has(name)
    );

    if (stale.length > 0) {
      expect.fail(`MCP exclusions have entries not in the registry: ${stale.join(', ')}`);
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
