/**
 * MCP Tool Coverage Test
 *
 * Ensures every non-experimental CLI command group in the command registry
 * has at least one corresponding MCP tool. Also verifies that non-experimental
 * subcommands are covered. Fails CI when a command is added to the registry
 * but not exposed via MCP.
 */
import { describe, expect, it } from 'vitest';
import { COMMAND_REGISTRY } from '../../../config/command-registry.js';
import { TOOLS } from '../tools.js';

/**
 * Commands intentionally excluded from MCP with documented reasons.
 * To add a new exclusion, add an entry here — the test enforces this is the
 * only place exclusions live.
 *
 * Format: "command" for top-level, "command subcommand" for subcommands.
 */
const MCP_EXCLUDED: Record<string, string> = {
  // ── Interactive / GUI ─────────────────────────────────────────────
  vscode: 'Opens VS Code GUI — not useful for MCP agents',
  protocol: 'URL protocol handler registration — local desktop concern',

  // ── Local-only tooling ────────────────────────────────────────────
  ops: 'Local VM provisioning — requires host KVM/QEMU, not remote-operable',
  doctor: 'Diagnoses local CLI installation — not a remote operation',
  update: 'CLI self-update — not a remote operation',
  store: 'Config file sync backends — local credential management',
  subscription: 'License management — local concern',
  mcp: 'The MCP server itself — cannot recurse',

  // ── Sync requires local filesystem ────────────────────────────────
  sync: 'Requires local filesystem paths — MCP agents have no local FS',

  // ── Covered by sub-operations ─────────────────────────────────────
  run: 'Escape hatch for raw renet functions — agents should use typed tools',
  snapshot: 'Snapshot operations — future MCP tools planned',
  storage: 'Storage management — future MCP tools planned',

  // ── Subcommands ───────────────────────────────────────────────────
  'storage browse': 'Interactive file browser — requires TTY',
  'storage pull': 'Downloads to local filesystem — MCP agents have no local FS',
  'backup sync': 'Bidirectional sync — complex orchestration, agents use push/pull',
  'backup schedule': 'Cron scheduling — local config concern, not a remote operation',
};

/**
 * Extract the CLI command path each MCP tool maps to.
 * e.g., repo_up → "repo up", machine_info → "machine info"
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
          (name) =>
            `  - "${name}": add an MCP tool in tools.ts OR add to MCP_EXCLUDED with a reason`
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
          (name) =>
            `  - "${name}": add an MCP tool in tools.ts OR add to MCP_EXCLUDED with a reason`
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
      expect.fail(`MCP_EXCLUDED has entries not in the registry: ${stale.join(', ')}`);
    }
  });

  it('exclusion list has no entries that already have MCP tools', () => {
    const redundant = Object.keys(MCP_EXCLUDED).filter(
      (name) => mcpPrefixes.has(name) || mcpPaths.has(name)
    );

    if (redundant.length > 0) {
      expect.fail(
        `MCP_EXCLUDED has entries that already have MCP tools (remove): ${redundant.join(', ')}`
      );
    }
  });

  it('all exclusions have non-empty reasons', () => {
    for (const [name, reason] of Object.entries(MCP_EXCLUDED)) {
      expect(reason.length, `${name} exclusion has empty reason`).toBeGreaterThan(0);
    }
  });
});
