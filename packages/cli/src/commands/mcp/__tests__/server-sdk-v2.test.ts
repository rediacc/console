/**
 * `rdc mcp serve` on MCP SDK v2 (PLAN-rmcp-local-mcp LM3): the server `startMcpServer` builds answers
 * `server/discover` with spec 2026-07-28, lists every tool and runs a call through the executor. The
 * transport is an in-memory pair in place of the process stdio; the stdio process itself is LM7.
 */
import { Client, InMemoryTransport } from '@modelcontextprotocol/client';
import type { StdioServerHandle } from '@modelcontextprotocol/server/stdio';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { startMcpServer } from '../server.js';
import { buildAllTools } from '../tools.js';

vi.mock('../executor.js', () => ({
  executeRdcCommand: vi.fn().mockResolvedValue({
    success: true,
    command: 'machine status staging --containers',
    data: { mock: true },
    errors: null,
    warnings: [],
    duration_ms: 5,
  }),
  resolveRdcBinary: () => ({ command: 'node', prefixArgs: ['index.js'] }),
}));

const SPEC = '2026-07-28';
const handles: StdioServerHandle[] = [];
const clients: Client[] = [];

async function connect(mode: 'auto' | 'legacy'): Promise<Client> {
  const [clientSide, serverSide] = InMemoryTransport.createLinkedPair();
  handles.push(startMcpServer({ defaultTimeoutMs: 1000 }, serverSide));
  const client = new Client(
    { name: 'lm3-test', version: '0.0.0' },
    { versionNegotiation: { mode } }
  );
  clients.push(client);
  await client.connect(clientSide);
  return client;
}

afterEach(async () => {
  for (const c of clients.splice(0)) await c.close();
  for (const h of handles.splice(0)) await h.close();
});

describe('rdc mcp serve on SDK v2', () => {
  it('answers server/discover with spec 2026-07-28 and negotiates the modern era', async () => {
    const client = await connect('auto');
    expect(client.getProtocolEra()).toBe('modern');
    expect(client.getNegotiatedProtocolVersion()).toBe(SPEC);
    const discovered = await client.discover();
    expect(discovered.supportedVersions).toContain(SPEC);
    expect(client.getServerVersion()?.name).toBe('rdc');
  });

  it('control: a 2025-era client still connects through initialize, not discover', async () => {
    const client = await connect('legacy');
    expect(client.getProtocolEra()).toBe('legacy');
    expect(client.getDiscoverResult()).toBeUndefined();
  });

  it('lists every tool with an object input schema', async () => {
    const client = await connect('auto');
    const listed = await client.listTools();
    const names = listed.tools.map((t) => t.name).sort((a, b) => a.localeCompare(b));
    expect(names).toEqual(
      buildAllTools()
        .map((t) => t.name)
        .sort((a, b) => a.localeCompare(b))
    );
    const containers = listed.tools.find((t) => t.name === 'machine_containers');
    expect(containers?.inputSchema.type).toBe('object');
    expect(containers?.inputSchema.required).toEqual(['name']);
  });

  it('runs a tool call through the executor and returns its envelope', async () => {
    const { executeRdcCommand } = await import('../executor.js');
    vi.mocked(executeRdcCommand).mockClear();
    const client = await connect('auto');
    const result = await client.callTool({
      name: 'machine_containers',
      arguments: { name: 'staging' },
    });
    expect(executeRdcCommand).toHaveBeenCalledWith(
      ['machine', 'status', 'staging', '--containers'],
      expect.objectContaining({ defaultTimeoutMs: 1000 })
    );
    expect(result.isError).toBe(false);
    const content = result.content as { type: string; text: string }[];
    expect(JSON.parse(content[0].text).data).toEqual({ mock: true });
  });

  it('control: a call missing a required field is refused before the executor runs', async () => {
    const { executeRdcCommand } = await import('../executor.js');
    vi.mocked(executeRdcCommand).mockClear();
    const client = await connect('auto');
    const outcome = await client
      .callTool({ name: 'machine_containers', arguments: {} })
      .then((r) => ({ isError: r.isError === true }))
      .catch(() => ({ isError: true }));
    expect(outcome.isError).toBe(true);
    expect(executeRdcCommand).not.toHaveBeenCalled();
  });
});
