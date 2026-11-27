/**
 * `rdc mcp serve` over stdio against a real config (PLAN-rmcp-local-mcp LM9). Skipped unless RDC_MCP_LIVE names
 * the config to serve (for the bench run: `RDC_MCP_LIVE=eu-bench`). The SDK v2 client spawns the real CLI entry
 * through the repo's own `./rdc.sh` entry (it prepares the CLI bundle and puts renet on PATH, as every live run does) and drives the four results the box names:
 *   1. `repo_list`, a read on the machine REDIACC_LIVE_MACHINE names (a config with two machines refuses a machineless list);
 *   2. `repo_up` on a fork (RDC_MCP_LIVE_FORK, a `name:tag` ref);
 *   3. `repo_up` on the grand (RDC_MCP_LIVE_GRAND, a repo name) without the env opt-in, refused with a structured code;
 *   4. the same write with REDIACC_ALLOW_GRAND_REPO set before the server starts, admitted by the policy.
 * Run it from packages/cli as `RDC_MCP_LIVE=<config> REDIACC_LIVE_MACHINE=<machine> RDC_MCP_LIVE_FORK=<name:tag> RDC_MCP_LIVE_GRAND=<repo> npx vitest run src/commands/mcp/__tests__/stdio-live.test.ts`.
 * Each result is printed with its structured code. Nothing is mocked.
 */
import path from 'node:path';
import { Client } from '@modelcontextprotocol/client';
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio';
import { afterAll, describe, expect, it } from 'vitest';

const SPEC = '2026-07-28';
const CLI_ROOT = path.resolve(import.meta.dirname, '..', '..', '..', '..');
// The wrapper the repo uses for every live run: it builds the bundle and sets PATH (renet) before the CLI starts.
const RDC_SH = path.resolve(CLI_ROOT, '..', '..', 'rdc.sh');
const LIVE = process.env.RDC_MCP_LIVE;
const FORK = process.env.RDC_MCP_LIVE_FORK;
const GRAND = process.env.RDC_MCP_LIVE_GRAND;
const MACHINE = process.env.REDIACC_LIVE_MACHINE;

interface Outcome {
  isError: boolean;
  code?: string;
  text: string;
}

/** The server's environment: the caller's, minus every opt-in, plus the ones this scenario sets. */
function serverEnv(extra: Record<string, string>): Record<string, string> {
  const env: Record<string, string> = {};
  for (const [k, v] of Object.entries(process.env)) {
    if (v === undefined || k === 'REDIACC_ALLOW_GRAND_REPO' || k === 'REDIACC_ALLOW_CLUSTER_OPS')
      continue;
    env[k] = v;
  }
  return { ...env, ...extra };
}

const clients: Client[] = [];

async function connect(config: string, extra: Record<string, string> = {}): Promise<Client> {
  const transport = new StdioClientTransport({
    command: RDC_SH,
    args: ['--config', config, 'mcp', 'serve'],
    cwd: CLI_ROOT,
    env: serverEnv(extra),
    stderr: 'pipe',
  });
  const client = new Client(
    { name: 'lm9-live', version: '0.0.0' },
    { versionNegotiation: { mode: { pin: SPEC } } }
  );
  await client.connect(transport);
  clients.push(client);
  return client;
}

async function call(client: Client, name: string, args: Record<string, unknown>): Promise<Outcome> {
  const result = await client.callTool({ name, arguments: args });
  const text = (result.content as { type: string; text: string }[])[0]?.text ?? '';
  const structured = result.structuredContent as { code?: string } | undefined;
  return { isError: result.isError === true, code: structured?.code, text };
}

function show(label: string, outcome: Outcome): void {
  process.stdout.write(
    `LM9 ${label}: isError=${outcome.isError} code=${outcome.code ?? '-'} ${outcome.text.slice(0, 200)}\n`
  );
}

afterAll(async () => {
  await Promise.all(clients.map((c) => c.close()));
});

describe.skipIf(!LIVE)('the mcp serve stdio server against a live config', () => {
  it('names the fork and the grand it drives', () => {
    expect(FORK, 'set RDC_MCP_LIVE_FORK to a name:tag fork ref').toBeTruthy();
    expect(GRAND, 'set RDC_MCP_LIVE_GRAND to a grand repository name').toBeTruthy();
    expect(MACHINE, 'set REDIACC_LIVE_MACHINE to the machine the scenario targets').toBeTruthy();
  });

  it('reads, writes a fork, is refused on a grand, and is admitted with the env opt-in', async () => {
    // The scenario refuses to run without its targets: a machineless repo_list would proceed and only fail on the list call.
    expect(MACHINE, 'set REDIACC_LIVE_MACHINE to the machine the scenario targets').toBeTruthy();
    expect(FORK, 'set RDC_MCP_LIVE_FORK to a name:tag fork ref').toBeTruthy();
    expect(GRAND, 'set RDC_MCP_LIVE_GRAND to a grand repository name').toBeTruthy();
    const live = LIVE as string;
    const plain = await connect(live);

    const list = await call(plain, 'repo_list', { machine: MACHINE });
    show('repo_list', list);
    expect(list.isError, list.text).toBe(false);

    const fork = await call(plain, 'repo_up', { ref: FORK });
    show('repo_up fork', fork);
    expect(fork.isError, fork.text).toBe(false);

    const refused = await call(plain, 'repo_up', { ref: GRAND });
    show('repo_up grand without opt-in', refused);
    expect(refused.isError).toBe(true);
    expect(refused.code, refused.text).toBe('AGENT_OPT_IN_MISSING');

    const opted = await connect(live, { REDIACC_ALLOW_GRAND_REPO: GRAND as string });
    const admitted = await call(opted, 'repo_up', { ref: GRAND, confirm: GRAND });
    show('repo_up grand with opt-in', admitted);
    // Proves only that the call came back without an error or any refusal code (not just the missing opt-in); it does not read back the write's effect.
    expect(admitted.isError, `${admitted.code ?? '-'}: ${admitted.text}`).toBe(false);
    expect(admitted.code, admitted.text).toBeUndefined();
  }, 600_000);
});
