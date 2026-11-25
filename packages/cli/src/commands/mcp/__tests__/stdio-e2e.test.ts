/**
 * `rdc mcp serve` end to end over stdio (PLAN-rmcp-local-mcp LM7, Design 8). The SDK v2 client spawns the real
 * CLI entry, negotiates spec 2026-07-28 through `server/discover`, and:
 *   - lists the tools; the proxy-surface slice must equal the parity snapshot
 *     packages/shared/src/mcp/__tests__/tools-list.snapshot.json, which the hosted Worker is held to as well;
 *   - calls one read tool (machine_list), answered by the child `rdc` from the fixture config;
 *   - calls one grand-repo write (repo_up on a grand) and reads the structured refusal code the child's
 *     command-policy decision returns before any machine is contacted.
 *
 * Nothing is mocked: the server, its child `rdc` processes and the policy decision are the shipped code. The
 * config is a temporary XDG_CONFIG_HOME fixture whose machine address is unroutable (TEST-NET-1).
 * The snapshot is compared parsed, so biome's JSON formatting of the committed file never decides the result.
 * After an intended tools/list change, rewrite it with `UPDATE_MCP_PARITY_SNAPSHOT=1 npx vitest run <this file>`
 * (packages/cli); the test writes the file, formats it with biome and still asserts against what it wrote.
 */
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { Client } from '@modelcontextprotocol/client';
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { buildAllTools } from '../tools.js';

const SPEC = '2026-07-28';
const CLI_ROOT = path.resolve(import.meta.dirname, '..', '..', '..', '..');
const SNAPSHOT = path.resolve(
  CLI_ROOT,
  '..',
  'shared',
  'src',
  'mcp',
  '__tests__',
  'tools-list.snapshot.json'
);
const CONFIG_NAME = 'lm7-e2e';
const GRAND_GUID = '11111111-1111-4111-8111-111111111111';

const FIXTURE = {
  schemaVersion: 3,
  id: '00000000-0000-4000-8000-0000000007e2',
  version: 1,
  credentials: { ssh: { privateKey: 'KEY' } },
  resources: {
    machines: { m1: { ip: '192.0.2.10', user: 'root', port: 22 } },
    repositories: {
      shop: {
        grand: 'latest',
        placement: { machine: 'm1' },
        tags: { latest: { repositoryGuid: GRAND_GUID, credential: 'set' } },
      },
    },
  },
  state: { repos: { shop: { latest: { networkId: 2816 } } } },
  encryption: { mode: 'plaintext' },
};

/** Order by UTF-16 code units, the order the registry and its validator use. */
function byCodeUnits(a: string, b: string): number {
  if (a < b) return -1;
  return a > b ? 1 : 0;
}

/** Rewrite the parity snapshot (UPDATE_MCP_PARITY_SNAPSHOT=1) in the form biome's JSON check accepts. */
function writeSnapshot(surface: unknown): void {
  writeFileSync(SNAPSHOT, `${JSON.stringify(surface, null, 2)}\n`);
  const biome = path.resolve(CLI_ROOT, '..', '..', 'node_modules', '.bin', 'biome');
  const formatted = spawnSync(biome, ['format', '--write', SNAPSHOT], { encoding: 'utf-8' });
  if (formatted.status !== 0)
    throw new Error(`biome format failed on ${SNAPSHOT}: ${formatted.stderr}`);
}

let home: string;
let client: Client;
let stderr = '';

/** The env the server starts with: the fixture's config home, and none of the opt-ins an operator could set. */
function serverEnv(): Record<string, string> {
  const env: Record<string, string> = {};
  for (const [k, v] of Object.entries(process.env)) {
    if (v === undefined || k.startsWith('REDIACC_') || k === 'RDC_DEV' || k === 'CI') continue;
    env[k] = v;
  }
  env.XDG_CONFIG_HOME = path.join(home, 'config');
  env.XDG_STATE_HOME = path.join(home, 'state');
  env.XDG_CACHE_HOME = path.join(home, 'cache');
  env.NO_COLOR = '1';
  return env;
}

interface Envelope {
  success: boolean;
  data: unknown;
  errors: { code?: string; details?: string[]; message?: string }[] | null;
}

async function callTool(name: string, args: Record<string, unknown>) {
  const result = await client.callTool({ name, arguments: args });
  const text = (result.content as { type: string; text: string }[])[0].text;
  return { isError: result.isError === true, envelope: JSON.parse(text) as Envelope };
}

beforeAll(async () => {
  home = mkdtempSync(path.join(tmpdir(), 'rdc-mcp-e2e-'));
  const configDir = path.join(home, 'config', 'rediacc');
  mkdirSync(configDir, { recursive: true });
  writeFileSync(path.join(configDir, `${CONFIG_NAME}.json`), JSON.stringify(FIXTURE));

  const transport = new StdioClientTransport({
    command: 'npx',
    args: ['tsx', 'src/index.ts', 'mcp', 'serve', '--config', CONFIG_NAME],
    cwd: CLI_ROOT,
    env: serverEnv(),
    stderr: 'pipe',
  });
  transport.stderr?.on('data', (chunk: Buffer) => {
    stderr += chunk.toString();
  });
  client = new Client(
    { name: 'lm7-e2e', version: '0.0.0' },
    { versionNegotiation: { mode: { pin: SPEC } } }
  );
  await client.connect(transport);
}, 120_000);

afterAll(async () => {
  await client?.close();
  if (home) rmSync(home, { recursive: true, force: true });
});

describe('rdc mcp serve over stdio (SDK v2 client)', () => {
  it('negotiates spec 2026-07-28 through server/discover', () => {
    expect(client.getProtocolEra(), stderr).toBe('modern');
    expect(client.getNegotiatedProtocolVersion()).toBe(SPEC);
    expect(client.getServerVersion()?.name).toBe('rdc');
  });

  it('lists every tool, and the proxy surface equals the parity snapshot', async () => {
    const { tools } = await client.listTools();
    const all = buildAllTools();
    expect(tools.map((t) => t.name).sort((a, b) => a.localeCompare(b))).toEqual(
      all.map((t) => t.name).sort((a, b) => a.localeCompare(b))
    );
    const proxy = new Set(all.filter((t) => t.surface.kind === 'proxy').map((t) => t.name));
    const surface = tools
      .filter((t) => proxy.has(t.name))
      .map((t) => ({
        name: t.name,
        description: t.description,
        inputSchema: t.inputSchema,
        annotations: t.annotations,
      }))
      .sort((a, b) => byCodeUnits(a.name, b.name));
    // Control: the slice is a real subset (the local-only tools drop out) and not empty.
    expect(surface.length).toBeGreaterThan(20);
    expect(surface.length).toBeLessThan(tools.length);
    if (process.env.UPDATE_MCP_PARITY_SNAPSHOT === '1') writeSnapshot(surface);
    expect(surface).toEqual(JSON.parse(readFileSync(SNAPSHOT, 'utf-8')));
  });

  it('a read tool (machine_list) answers from the config through the child rdc', async () => {
    const { isError, envelope } = await callTool('machine_list', {});
    expect(isError, JSON.stringify(envelope)).toBe(false);
    expect(envelope.success).toBe(true);
    expect(JSON.stringify(envelope.data)).toContain('192.0.2.10');
  }, 120_000);

  it('a grand-repo write (repo_up) is refused by the child decision with a structured code', async () => {
    const { isError, envelope } = await callTool('repo_up', { ref: 'shop' });
    expect(isError).toBe(true);
    const first = envelope.errors?.[0];
    expect(first?.code, JSON.stringify(envelope)).toBe('VALIDATION_ERROR');
    // The decision's own code leads the details (utils/command-policy.ts refusalError).
    expect(first?.details?.[0], JSON.stringify(envelope)).toBe('AGENT_OPT_IN_MISSING');
  }, 120_000);
});
