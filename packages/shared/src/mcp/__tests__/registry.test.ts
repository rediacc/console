import { describe, expect, it } from 'vitest';
import { CLI_CONTRACT } from '../../cli-contract/data/contract.generated.js';
import { isMcpLayerErrorCode, MCP_LAYER_ERROR_CODES } from '../errors.js';
import {
  getMcpTool,
  isMcpErrorCode,
  listMcpTools,
  listProxyTools,
  MCP_REGISTRY,
  mcpRegistryProblems,
  parseMcpRegistry,
} from '../registry.js';
import { compareCodeUnits, type McpToolEntry } from '../schema.js';

function entry(overrides: Partial<McpToolEntry> = {}): McpToolEntry {
  return {
    name: 'repo_up',
    command: 'repo up',
    description: 'Deploy a repository',
    inputSchema: { type: 'object', properties: {} },
    annotations: {
      destructiveHint: false,
      readOnlyHint: false,
      idempotentHint: true,
      openWorldHint: true,
    },
    surface: 'proxy',
    localBasis: null,
    localReason: null,
    timeoutClass: 'write',
    attachWindow: true,
    ...overrides,
  };
}

function doc(tools: McpToolEntry[], contractErrorCodes = ['SSH_ERROR']) {
  return { schema: 1, tools, contractErrorCodes };
}

describe('mcpRegistryProblems', () => {
  it('finds nothing in a well-formed document (the silent control)', () => {
    const local = entry({
      name: 'version',
      command: 'version',
      surface: 'local',
      localBasis: 'caller-disk',
      localReason: 'Reports the installed binary.',
    });
    const executor = entry({
      name: 'x_executor',
      command: 'x executor',
      surface: 'executor',
      localReason: 'Runs on the executor once LM10 lands.',
    });
    expect(mcpRegistryProblems(doc([entry(), local, executor]))).toEqual([]);
  });

  it('refuses a proxy tool that carries a localReason', () => {
    expect(mcpRegistryProblems(doc([entry({ localReason: 'why' })]))).toEqual([
      'tools[0] is proxy but carries a localReason',
    ]);
  });

  it('refuses a non-proxy tool without a reason', () => {
    const problems = mcpRegistryProblems(doc([entry({ surface: 'in-memory' })]));
    expect(problems).toEqual(['tools[0] is in-memory but has no localReason']);
  });

  it('refuses a local tool whose basis is not one of the two D57 admits', () => {
    const bad = entry({ surface: 'local', localReason: 'meaningless remotely' });
    expect(mcpRegistryProblems(doc([bad]))).toEqual([
      'tools[0].localBasis null does not fit surface local',
    ]);
    const wrongBasis = { ...bad, localBasis: 'meaningless' } as unknown as McpToolEntry;
    expect(mcpRegistryProblems(doc([wrongBasis]))).toEqual([
      'tools[0].localBasis "meaningless" does not fit surface local',
    ]);
  });

  it('refuses a basis on a tool that is not local', () => {
    const bad = entry({ localBasis: 'terminal' });
    expect(mcpRegistryProblems(doc([bad]))).toEqual([
      'tools[0].localBasis "terminal" does not fit surface proxy',
    ]);
  });

  it('refuses duplicate and unsorted names', () => {
    const a = entry({ name: 'b_tool' });
    const b = entry({ name: 'a_tool' });
    expect(mcpRegistryProblems(doc([a, b]))).toEqual([
      'tools[1].name a_tool breaks the sort order',
    ]);
    expect(mcpRegistryProblems(doc([b, b]))).toEqual([
      'tools[1].name a_tool is a duplicate',
      'tools[1].name a_tool breaks the sort order',
    ]);
  });

  it('refuses a contract code list that repeats an MCP-layer code', () => {
    expect(mcpRegistryProblems(doc([entry()], ['POLICY_DENIED']))).toEqual([
      'contractErrorCodes repeats an MCP-layer code',
    ]);
  });

  it('refuses a non-object input schema and missing annotations', () => {
    const bad = {
      ...entry(),
      inputSchema: { type: 'string' },
      annotations: { destructiveHint: true },
    };
    expect(mcpRegistryProblems(doc([bad as unknown as McpToolEntry]))).toEqual([
      'tools[0].inputSchema is not an object schema',
      'tools[0].annotations lacks one of destructiveHint, readOnlyHint, idempotentHint, openWorldHint',
    ]);
  });

  it('parseMcpRegistry throws naming every problem', () => {
    expect(() => parseMcpRegistry(doc([]))).toThrow(/tools is not a non-empty array/);
  });
});

describe('the committed registry', () => {
  it('is well-formed', () => {
    expect(mcpRegistryProblems(MCP_REGISTRY)).toEqual([]);
  });

  it('holds exactly the contract error codes', () => {
    expect(MCP_REGISTRY.contractErrorCodes).toEqual(
      CLI_CONTRACT.errorCodes.map((e) => e.code).sort(compareCodeUnits)
    );
  });

  it('names a contract command for every tool', () => {
    const paths = new Set(CLI_CONTRACT.commands.map((c) => c.pathKey));
    const orphans = listMcpTools().filter((t) => !paths.has(t.command));
    expect(orphans.map((t) => t.name)).toEqual([]);
  });

  it('serves on the proxy surface exactly the tools whose command is proxyCapable', () => {
    const proxyCapable = new Set(
      CLI_CONTRACT.commands.filter((c) => c.proxyCapable).map((c) => c.pathKey)
    );
    const proxy = listProxyTools();
    expect(proxy.length).toBeGreaterThan(0);
    expect(proxy.every((t) => t.surface === 'proxy' && proxyCapable.has(t.command))).toBe(true);
    const hidden = listMcpTools().filter(
      (t) => t.surface !== 'proxy' && proxyCapable.has(t.command)
    );
    expect(hidden.map((t) => t.name)).toEqual([]);
  });

  it('looks a tool up by name', () => {
    expect(getMcpTool('repo_up')?.command).toBe('repo up');
    expect(getMcpTool('machine_containers')?.command).toBe('machine status');
    expect(getMcpTool('no_such_tool')).toBeUndefined();
  });
});

describe('error codes', () => {
  it('admits an MCP-layer code and a contract code, and refuses an unknown one', () => {
    expect(isMcpErrorCode('POLICY_DENIED')).toBe(true);
    expect(isMcpErrorCode('BUSY')).toBe(true);
    expect(isMcpErrorCode('NOT_A_CODE')).toBe(false);
  });

  it('keeps the layer codes apart from the contract codes', () => {
    const contract = new Set(CLI_CONTRACT.errorCodes.map((e) => e.code));
    expect(MCP_LAYER_ERROR_CODES.filter((c) => contract.has(c))).toEqual([]);
    expect(isMcpLayerErrorCode('BUSY')).toBe(false);
  });
});
