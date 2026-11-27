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
 * The listing is put through biome's JSON formatter before the file-snapshot comparison, so the committed file is
 * exactly what biome's check accepts. After an intended tools/list change, refresh it with
 * `npx vitest run -u <this file>` (packages/cli).
 */
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
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

/** The listing as biome formats a JSON file of the snapshot's name, so the committed snapshot passes its check. */
function biomeJson(value: unknown): string {
  const biome = path.resolve(CLI_ROOT, '..', '..', 'node_modules', '.bin', 'biome');
  const formatted = spawnSync(biome, ['format', `--stdin-file-path=${SNAPSHOT}`], {
    input: `${JSON.stringify(value, null, 2)}\n`,
    encoding: 'utf-8',
  });
  if (formatted.status !== 0) throw new Error(`biome format failed: ${formatted.stderr}`);
  return formatted.stdout;
}

// BLOCKER: spawns `npx` and `node_modules/.bin/biome` as bare executables (no .cmd shim resolution without a shell) and steers the child with XDG_*, which win32 ignores; the child would read the runner's real %APPDATA%.
const SKIP_WIN32 = process.platform === 'win32';

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
  if (SKIP_WIN32) return;
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

describe.skipIf(SKIP_WIN32)('the mcp serve stdio server, driven by the SDK v2 client', () => {
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
    await expect(biomeJson(surface)).toMatchFileSnapshot(SNAPSHOT);
  });

  it('a read tool (machine_list) answers from the config through the child rdc', async () => {
    const { isError, envelope } = await callTool('machine_list', {});
    expect(isError, JSON.stringify(envelope)).toBe(false);
    expect(envelope.success).toBe(true);
    expect(JSON.stringify(envelope.data)).toContain('192.0.2.10');
  }, 120_000);

  it('a grand-repo write (repo_up) is refused by the child decision with a structured code', async () => {
    const result = await client.callTool({ name: 'repo_up', arguments: { ref: 'shop' } });
    expect(result.isError).toBe(true);
    // The child's refusal is lifted to structuredContent (executor.ts runUnderPolicy).
    const structured = result.structuredContent as { code?: string } | undefined;
    expect(structured?.code, JSON.stringify(result)).toBe('AGENT_OPT_IN_MISSING');
  }, 120_000);
});
