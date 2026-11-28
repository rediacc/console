/**
 * The generated MCP registry (packages/shared/src/mcp/tools.generated.json) against the tools `rdc mcp serve` registers (PLAN-rmcp-local-mcp LM1).
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { CLI_CONTRACT } from '@rediacc/shared/cli-contract';
import { describe, expect, it } from 'vitest';
import {
  buildMcpRegistry,
  compareCodeUnits,
  isRegistryCurrent,
  serializeMcpRegistry,
  surfaceDisagreement,
} from '../../../../scripts/lib/mcp-registry-build.js';
import { buildAllTools } from '../tools.js';

const REGISTRY_PATH = fileURLToPath(
  new URL('../../../../../shared/src/mcp/tools.generated.json', import.meta.url)
);

describe('MCP registry', () => {
  it('the committed tools.generated.json is current against metadata and the contract', () => {
    const committed = readFileSync(REGISTRY_PATH, 'utf-8');
    expect(
      isRegistryCurrent(committed, buildMcpRegistry(CLI_CONTRACT)),
      'tools.generated.json is stale; run: npm run generate:mcp-registry -w @rediacc/cli'
    ).toBe(true);
  });

  it('carries one entry per registered tool, the hand-declared machine_* views included', () => {
    const registry = buildMcpRegistry(CLI_CONTRACT);
    expect(registry.tools.map((t) => t.name)).toEqual(
      buildAllTools()
        .map((t) => t.name)
        .sort(compareCodeUnits)
    );
    const view = registry.tools.find((t) => t.name === 'machine_containers');
    expect(view?.command).toBe('machine status');
    expect(view?.surface).toBe('proxy');
  });

  it('isRegistryCurrent ignores line folding and sees a changed value', () => {
    const registry = buildMcpRegistry(CLI_CONTRACT);
    const text = serializeMcpRegistry(registry);
    expect(isRegistryCurrent(text, registry)).toBe(true);
    expect(isRegistryCurrent(JSON.stringify(registry), registry)).toBe(true);
    const changed = text.replace('"repo_up"', '"repo_upp"');
    expect(changed).not.toBe(text);
    expect(isRegistryCurrent(changed, registry)).toBe(false);
    expect(isRegistryCurrent('not json', registry)).toBe(false);
  });
});

describe('surfaceDisagreement', () => {
  const proxyCmd = CLI_CONTRACT.commands.find((c) => c.proxyCapable);
  const localCmd = CLI_CONTRACT.commands.find((c) => !c.proxyCapable);
  if (!proxyCmd || !localCmd) throw new Error('the contract needs a proxy and a non-proxy command');

  it('admits a marker that agrees with the contract (the silent control)', () => {
    expect(
      surfaceDisagreement(
        { name: 'a', commandPath: proxyCmd.pathKey, surface: { kind: 'proxy' } },
        CLI_CONTRACT
      )
    ).toBeNull();
    expect(
      surfaceDisagreement(
        {
          name: 'b',
          commandPath: localCmd.pathKey,
          surface: { kind: 'executor', reason: 'LM10' },
        },
        CLI_CONTRACT
      )
    ).toBeNull();
  });

  it('refuses proxy on a command that is not proxyCapable', () => {
    expect(
      surfaceDisagreement(
        { name: 'b', commandPath: localCmd.pathKey, surface: { kind: 'proxy' } },
        CLI_CONTRACT
      )
    ).toMatch(/mcpSurface is proxy but .* is not proxyCapable/);
  });

  it('names the proxy block reason in parentheses when the contract holds one, and omits the parentheses when it is absent or empty', () => {
    const tool = { name: 'b', commandPath: localCmd.pathKey, surface: { kind: 'proxy' } } as const;
    const withCmd = (reason: string | undefined) => ({
      commands: [{ ...localCmd, proxyBlockedReason: reason }],
    });
    expect(surfaceDisagreement(tool, withCmd('needs a terminal'))).toMatch(
      /is not proxyCapable \(needs a terminal\)$/
    );
    // CONTROL: absent and empty reasons leave the sentence bare, never "()" or "(undefined)".
    for (const reason of [undefined, '']) {
      const msg = surfaceDisagreement(tool, withCmd(reason));
      expect(msg).toMatch(/is not proxyCapable$/);
      expect(msg).not.toMatch(/\(|undefined/);
    }
  });

  it('refuses a non-proxy marker on a proxyCapable command', () => {
    expect(
      surfaceDisagreement(
        {
          name: 'a',
          commandPath: proxyCmd.pathKey,
          surface: { kind: 'local', basis: 'terminal', reason: 'x' },
        },
        CLI_CONTRACT
      )
    ).toMatch(/mcpSurface is local but .* is proxyCapable/);
  });

  it('refuses a command the contract does not hold', () => {
    expect(
      surfaceDisagreement(
        { name: 'z', commandPath: 'no such command', surface: { kind: 'proxy' } },
        CLI_CONTRACT
      )
    ).toMatch(/is not in the CLI contract/);
  });

  it('buildMcpRegistry throws on a disagreeing tool instead of writing it', () => {
    const all = buildAllTools();
    const target = all.find((t) => t.surface.kind !== 'proxy');
    expect(target, 'the tool set needs a non-proxy tool').toBeDefined();
    const tools = all.map((t) =>
      t === target ? { ...t, surface: { kind: 'proxy' as const } } : t
    );
    expect(() => buildMcpRegistry(CLI_CONTRACT, tools)).toThrow(/MCP registry refused/);
  });
});
