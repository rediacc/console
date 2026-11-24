/**
 * Builds the MCP tool registry document (packages/shared/src/mcp/tools.generated.json) from the tools the stdio server registers (`buildAllTools`: the contract-derived tools plus the hand-declared machine_* views) and the CLI contract.
 *
 * The generator (scripts/generate-mcp-registry.ts) writes or checks the result, and the freshness test (src/commands/mcp/__tests__/mcp-registry.test.ts) compares it to the committed file, so the registry and the server cannot drift apart.
 */
import type { CliContract } from '@rediacc/shared/cli-contract';
import { z } from 'zod';
import { type ToolDef, toolAnnotations } from '../../src/commands/mcp/tool-factory.js';
import { buildAllTools } from '../../src/commands/mcp/tools.js';

/**
 * One registry entry as this builder emits it. The shape is declared in packages/shared/src/mcp/schema.ts (McpToolEntry); this side cannot import it, because the CLI test project reaches this file and its rootDir stops at packages/cli. The generator runs the shared validator (mcpRegistryProblems) on every build, and packages/shared/src/mcp/__tests__/registry.test.ts validates the committed file, so the two shapes cannot drift silently.
 */
export interface RegistryEntry {
  name: string;
  command: string;
  description: string;
  inputSchema: Record<string, unknown>;
  annotations: ReturnType<typeof toolAnnotations>;
  surface: ToolDef['surface']['kind'];
  localBasis: 'caller-disk' | 'terminal' | null;
  localReason: string | null;
  timeoutClass: ToolDef['timeoutClass'];
  attachWindow: boolean;
}

export interface RegistryDocument {
  schema: 1;
  tools: RegistryEntry[];
  contractErrorCodes: string[];
}

/** Order two strings by UTF-16 code units; the shared validator checks the same order (compareCodeUnits in schema.ts). */
export function compareCodeUnits(a: string, b: string): number {
  if (a < b) return -1;
  return a > b ? 1 : 0;
}

/** The committed registry, relative to packages/cli. */
export const REGISTRY_REL_PATH = '../shared/src/mcp/tools.generated.json';

/**
 * Why a tool's surface marker disagrees with its contract command, or null when it agrees.
 *
 * `proxy` is exactly `proxyCapable`: a `proxy` marker on a command the executor refuses would advertise a tool the Worker cannot run, and a non-proxy marker on a proxy-capable command would hide a tool the Worker can run.
 */
export function surfaceDisagreement(
  tool: Pick<ToolDef, 'name' | 'commandPath' | 'surface'>,
  contract: Pick<CliContract, 'commands'>
): string | null {
  const cmd = contract.commands.find((c) => c.pathKey === tool.commandPath);
  if (!cmd) return `${tool.name}: command "${tool.commandPath}" is not in the CLI contract`;
  if (tool.surface.kind === 'proxy' && !cmd.proxyCapable) {
    return `${tool.name}: mcpSurface is proxy but "${tool.commandPath}" is not proxyCapable (${cmd.proxyBlockedReason ?? 'no reason'})`;
  }
  if (tool.surface.kind !== 'proxy' && cmd.proxyCapable) {
    return `${tool.name}: mcpSurface is ${tool.surface.kind} but "${tool.commandPath}" is proxyCapable; mark it proxy`;
  }
  return null;
}

function inputSchemaOf(tool: ToolDef): Record<string, unknown> {
  const { $schema: _drop, ...schema } = z.toJSONSchema(z.object(tool.schema as z.ZodRawShape));
  return schema;
}

function entryOf(tool: ToolDef): RegistryEntry {
  const { surface } = tool;
  return {
    name: tool.name,
    command: tool.commandPath,
    description: tool.description,
    inputSchema: inputSchemaOf(tool),
    annotations: toolAnnotations(tool),
    surface: surface.kind,
    localBasis: surface.kind === 'local' ? surface.basis : null,
    localReason: surface.kind === 'proxy' ? null : surface.reason,
    timeoutClass: tool.timeoutClass,
    attachWindow: tool.attachWindowMs !== undefined,
  };
}

/** Build the registry document, throwing with every problem when a tool's surface disagrees with the contract. */
export function buildMcpRegistry(
  contract: Pick<CliContract, 'commands' | 'errorCodes'>,
  tools: ToolDef[] = buildAllTools()
): RegistryDocument {
  const problems = tools
    .map((tool) => surfaceDisagreement(tool, contract))
    .filter((p): p is string => p !== null);
  const registry: RegistryDocument = {
    schema: 1,
    tools: tools.map(entryOf).sort((a, b) => compareCodeUnits(a.name, b.name)),
    contractErrorCodes: contract.errorCodes.map((e) => e.code).sort(compareCodeUnits),
  };
  if (problems.length > 0) {
    throw new Error(`MCP registry refused:\n  ${problems.join('\n  ')}`);
  }
  return registry;
}

/** The registry as JSON text, before the generator's biome pass reformats it. */
export function serializeMcpRegistry(registry: RegistryDocument): string {
  return `${JSON.stringify(registry, null, 2)}\n`;
}

/**
 * Does the committed file hold exactly this registry? Compared through a canonical re-serialization of the parsed text, so biome's line folding is irrelevant while key order, values and tool order all count. Text that is not JSON is stale.
 */
export function isRegistryCurrent(committedText: string, registry: RegistryDocument): boolean {
  let parsed: unknown;
  try {
    parsed = JSON.parse(committedText);
  } catch {
    return false;
  }
  return JSON.stringify(parsed) === JSON.stringify(registry);
}
