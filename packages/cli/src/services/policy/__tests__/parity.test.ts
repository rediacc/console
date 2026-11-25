/**
 * Parity harness (agent/plans/PLAN-rmcp-decide.md box D6): rows of the shared decision table
 * (packages/shared/src/policy/__fixtures__/decision-table.json), chosen by fixtures/parity-cases.json,
 * driven through every local surface that reaches the one `decide`, each asserting the verdict and
 * code the row expects:
 *
 *   (a) decide      the function itself, on the row's own context
 *   (b) cli         the real CLI entry as a subprocess against a temporary config (the root
 *                   preAction hook, enforceRootCommand), the agent principal chosen by REDIACC_AGENT
 *   (c) mcp         `rdc mcp serve` over stdio through the SDK client; its child `rdc` is an agent
 *   (d) executor    `createServeApp` in-process with the real authorize and the real HTTP route; the
 *                   agent rows reach it as a remote-MCP grant principal, the only way an agent
 *                   arrives there
 *
 * Expectations come from the table rows, written by hand, never from any surface. A control case
 * (a row whose expectation is flipped) must be reported as a mismatch by every surface, so a
 * harness that stopped comparing fails here. The expectation of the one deliberate executor
 * deviation lives in the case file (`executorDeviation`).
 */

import { spawn } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import type { AddressInfo } from 'node:net';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { serve } from '@hono/node-server';
import { Client } from '@modelcontextprotocol/client';
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio';
import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import {
  DECISION_CODES,
  type DecisionContext,
  decide,
  mergePolicies,
  type PolicyDocument,
  PolicyDocumentSchema,
} from '@rediacc/shared/policy';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { isAgentByAncestry } from '../../../utils/process-ancestry.js';
import type { ExecuteOptions } from '../../executor/types.js';
import { AuthVerifier } from '../../serve/auth.js';
import { serveCrypto } from '../../serve/crypto.js';
import type { ServeDeps } from '../../serve/deps.js';
import { type AgentGrantOverrides, authorize } from '../../serve/policy.js';
import { createServeApp } from '../../serve/server.js';
import { SessionStore } from '../../serve/sessions.js';

interface Expectation {
  verdict: string;
  code: string;
}

interface FixtureRow {
  id: string;
  principal: DecisionContext['principal'];
  command: DecisionContext['command'];
  target: DecisionContext['target'];
  policy: { org?: unknown; team?: unknown } | null;
  overrides: DecisionContext['overrides'];
  confirmation: DecisionContext['confirmation'];
  expect: Expectation;
}

type Surface = 'decide' | 'cli' | 'mcp' | 'executor';

interface ParityCase {
  row: string;
  surfaces: Surface[];
  executorDeviation?: Expectation & { why: string };
}

const CLI_ROOT = path.resolve(import.meta.dirname, '..', '..', '..', '..');
const TABLE = JSON.parse(
  readFileSync(
    path.resolve(CLI_ROOT, '..', 'shared', 'src', 'policy', '__fixtures__', 'decision-table.json'),
    'utf8'
  )
) as { rows: FixtureRow[]; controls: FixtureRow[] };
const CASES = (
  JSON.parse(
    readFileSync(path.resolve(import.meta.dirname, 'fixtures', 'parity-cases.json'), 'utf8')
  ) as { cases: ParityCase[] }
).cases;

function rowOf(id: string): FixtureRow {
  const row = TABLE.rows.find((r) => r.id === id);
  if (!row) throw new Error(`parity-cases.json names the row "${id}", which the table lacks.`);
  return row;
}

const GRAND_GUID = '11111111-1111-4111-8111-111111111111';
const FORK_GUID = '22222222-2222-4222-8222-222222222222';

/** The verdict a stable code stands for (the HTTP and CLI surfaces report the code only). */
function verdictOfCode(code: string): string {
  if (code === 'ALLOWED') return 'allow';
  return code === 'CONFIRMATION_REQUIRED' ? 'needs_confirmation' : 'deny';
}

const parseDoc = (raw: unknown): PolicyDocument | undefined =>
  raw === undefined ? undefined : PolicyDocumentSchema.parse(raw);

/** The org-tier policy document of a row, which is what a local-file config carries. */
function localPolicyOf(row: FixtureRow): PolicyDocument | undefined {
  if (row.policy?.team !== undefined) {
    throw new Error(`Row ${row.id} has a team tier, which a local-file config cannot carry.`);
  }
  return parseDoc(row.policy?.org);
}

/**
 * The config a row's target stands for: the repo a grand with its fork tag when the name carries
 * one, nothing for an unresolved name, one machine at a refused port (an allowed command fails
 * fast at the connection, never at policy).
 */
function configFor(row: FixtureRow): Record<string, unknown> {
  const name = row.target.repo?.name;
  const state = row.target.repo?.state;
  const repositories: Record<string, unknown> = {};
  if (name && state !== 'unresolved') {
    const [base = name, tag] = name.split(':');
    const tags: Record<string, unknown> = {
      latest: { repositoryGuid: GRAND_GUID, credential: 'set' },
    };
    if (state === 'fork' && tag) {
      tags[tag] = { repositoryGuid: FORK_GUID, grandGuid: GRAND_GUID };
    }
    repositories[base] = { grand: 'latest', placement: { machine: 'm1' }, tags };
  }
  const policy = localPolicyOf(row);
  return {
    schemaVersion: 3,
    id: '00000000-0000-4000-8000-0000000007d6',
    version: 1,
    credentials: { ssh: { privateKey: 'KEY' } },
    resources: { machines: { m1: { ip: '127.0.0.1', user: 'root', port: 1 } }, repositories },
    encryption: { mode: 'plaintext' },
    ...(policy ? { policy } : {}),
  };
}

// ---------------------------------------------------------------------------------------------
// (a) decide
// ---------------------------------------------------------------------------------------------

function viaDecide(row: FixtureRow): Expectation {
  const got = decide({
    principal: row.principal,
    command: row.command,
    target: row.target,
    policy: row.policy ? mergePolicies(parseDoc(row.policy.org), parseDoc(row.policy.team)) : null,
    overrides: row.overrides,
    confirmation: row.confirmation,
  });
  return { verdict: got.verdict, code: got.code };
}

// ---------------------------------------------------------------------------------------------
// the temporary config home shared by the cli and mcp legs
// ---------------------------------------------------------------------------------------------

let home: string;

function childEnv(agent: boolean): Record<string, string> {
  const env: Record<string, string> = {};
  for (const [k, v] of Object.entries(process.env)) {
    if (v === undefined || k.startsWith('REDIACC_') || k === 'RDC_DEV' || k === 'CI') continue;
    if (k === 'CLAUDECODE' || k === 'GEMINI_CLI' || k === 'COPILOT_CLI') continue;
    env[k] = v;
  }
  env.XDG_CONFIG_HOME = path.join(home, 'config');
  env.XDG_STATE_HOME = path.join(home, 'state');
  env.XDG_CACHE_HOME = path.join(home, 'cache');
  env.NO_COLOR = '1';
  if (agent) env.REDIACC_AGENT = '1';
  return env;
}

interface Envelope {
  success: boolean;
  errors: { code?: string; details?: string[] }[] | null;
}

/** The code a run answered: the decision code leading a refusal's details, else ALLOWED (it got past policy). */
function codeOfEnvelope(envelope: Envelope): string {
  const lead = envelope.errors?.[0]?.details?.[0];
  return lead !== undefined && (DECISION_CODES as readonly string[]).includes(lead)
    ? lead
    : 'ALLOWED';
}

const EXTRA_ARGS: Record<string, { argv: string[]; tool: Record<string, unknown> }> = {
  'repo resize': { argv: ['--size', '10G'], tool: { size: '10G' } },
};

// ---------------------------------------------------------------------------------------------
// (b) the CLI as a subprocess
// ---------------------------------------------------------------------------------------------

function runCli(row: FixtureRow): Promise<Expectation> {
  const { pathKey } = row.command;
  const ref = row.target.repo?.name ?? '';
  const argv = [
    'tsx',
    'src/index.ts',
    '--config',
    row.id,
    ...pathKey.split(' '),
    ref,
    ...(EXTRA_ARGS[pathKey]?.argv ?? []),
    '--output',
    'json',
  ];
  return new Promise((resolve, reject) => {
    const child = spawn('npx', argv, {
      cwd: CLI_ROOT,
      env: childEnv(row.principal.kind === 'agent'),
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk: Buffer) => (stdout += chunk.toString()));
    child.stderr.on('data', (chunk: Buffer) => (stderr += chunk.toString()));
    child.on('error', reject);
    child.on('close', () => {
      try {
        const code = codeOfEnvelope(JSON.parse(stdout) as Envelope);
        resolve({ verdict: verdictOfCode(code), code });
      } catch {
        reject(new Error(`rdc printed no JSON envelope.\nstdout: ${stdout}\nstderr: ${stderr}`));
      }
    });
  });
}

// ---------------------------------------------------------------------------------------------
// (c) the local MCP server over stdio (its child rdc runs with REDIACC_AGENT=1)
// ---------------------------------------------------------------------------------------------

const mcpClients = new Map<string, Client>();

async function mcpClientFor(configName: string): Promise<Client> {
  const existing = mcpClients.get(configName);
  if (existing) return existing;
  const transport = new StdioClientTransport({
    command: 'npx',
    args: ['tsx', 'src/index.ts', 'mcp', 'serve', '--config', configName],
    cwd: CLI_ROOT,
    env: childEnv(false),
    stderr: 'pipe',
  });
  const client = new Client(
    { name: 'parity', version: '0.0.0' },
    { versionNegotiation: { mode: { pin: '2026-07-28' } } }
  );
  await client.connect(transport);
  mcpClients.set(configName, client);
  return client;
}

async function viaMcp(row: FixtureRow): Promise<Expectation> {
  const { pathKey } = row.command;
  const client = await mcpClientFor(row.id);
  const result = await client.callTool({
    name: pathKey.replaceAll(' ', '_'),
    arguments: { ref: row.target.repo?.name ?? '', ...EXTRA_ARGS[pathKey]?.tool },
  });
  const text = (result.content as { type: string; text: string }[])[0]?.text ?? '';
  const code = codeOfEnvelope(JSON.parse(text) as Envelope);
  return { verdict: verdictOfCode(code), code };
}

// ---------------------------------------------------------------------------------------------
// (d) the executor, in process
// ---------------------------------------------------------------------------------------------

let executor: ReturnType<typeof serve> | undefined;
let executorUrl = '';
let activeConfig: RdcConfig;
let activeGrant: AgentGrantOverrides | undefined;

function grandReposOf(row: FixtureRow): AgentGrantOverrides['allowGrandRepos'] {
  const { grandRepos } = row.overrides;
  if (grandRepos === '*') return true;
  return grandRepos ?? false;
}

function bootExecutor(): void {
  const deps: ServeDeps = {
    mode: 'container',
    auth: new AuthVerifier({
      accountUrl: 'https://account.test',
      executorToken: 'rdt_executor',
      fetchImpl: ((_url: string, init?: RequestInit) => {
        const { token } = JSON.parse(String(init?.body)) as { token: string };
        const [, orgRole = 'member', teamSlug] = token.split(':');
        return Promise.resolve(
          Response.json({
            active: true,
            scopes: ['proxy:exec', 'audit:write'],
            orgId: 'org-1',
            teamId: teamSlug ? `${teamSlug}-id` : null,
            ...(teamSlug ? { teamSlug } : {}),
            createdByUserId: 'user-1',
            userEmail: 'person@example.com',
            orgRole,
          })
        );
      }) as unknown as typeof fetch,
    }),
    sessions: new SessionStore(),
    crypto: serveCrypto,
    executor: {
      execute(_call: ExecuteOptions) {
        return Promise.resolve({ success: true, exitCode: 0, durationMs: 1, stdout: 'ok' });
      },
    },
    loadConfig: () => Promise.resolve(activeConfig),
    // The grant principal is the one way an agent reaches the executor (the HTTP route carries no agent claim of its own), so the case's grant is added here.
    authorize: (args) =>
      authorize({ ...args, ...(activeGrant ? { agentGrant: activeGrant } : {}) }),
    audit: () => Promise.resolve(),
    detach: () => false,
  };
  executor = serve({ fetch: createServeApp(deps).fetch, port: 0 });
  executorUrl = `http://127.0.0.1:${(executor.address() as AddressInfo).port}`;
}

async function viaExecutor(row: FixtureRow): Promise<Expectation> {
  activeConfig = configFor(row) as unknown as RdcConfig;
  activeGrant =
    row.principal.kind === 'agent'
      ? { allowGrandRepos: grandReposOf(row), allowClusterOps: false }
      : undefined;
  const { orgRole, teamSlug } = row.principal;
  const response = await fetch(`${executorUrl}${PROXY_ROUTES.command}`, {
    method: 'POST',
    headers: {
      authorization: `Bearer rdt:${orgRole}:${teamSlug ?? ''}`,
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      contractVersion: CLI_CONTRACT_VERSION,
      pathKey: row.command.pathKey,
      positionals: { ref: row.target.repo?.name ?? '' },
      params: EXTRA_ARGS[row.command.pathKey] ? { size: '10G' } : {},
    }),
  });
  const body = await response.text();
  if (response.status === 200) return { verdict: 'allow', code: 'ALLOWED' };
  const parsed = JSON.parse(body) as { error: string; code?: string };
  if (parsed.code === undefined) {
    throw new Error(`The executor refused without a decision code (${response.status}): ${body}`);
  }
  return { verdict: verdictOfCode(parsed.code), code: parsed.code };
}

// ---------------------------------------------------------------------------------------------
// the harness
// ---------------------------------------------------------------------------------------------

const RUNNERS: Record<Surface, (row: FixtureRow) => Expectation | Promise<Expectation>> = {
  decide: viaDecide,
  cli: runCli,
  mcp: viaMcp,
  executor: viaExecutor,
};

/** What a surface must answer for a case: the row's expectation, or the case's pinned deviation. */
function expectedOn(surface: Surface, c: ParityCase): Expectation {
  const row = rowOf(c.row);
  if (surface === 'executor' && c.executorDeviation) {
    const { verdict, code } = c.executorDeviation;
    return { verdict, code };
  }
  return row.expect;
}

/** The mismatch one surface reports for one case, or null when it answers as expected. */
async function mismatch(surface: Surface, c: ParityCase, flip = false): Promise<string | null> {
  const want = expectedOn(surface, c);
  const expected = flip
    ? { verdict: want.verdict === 'allow' ? 'deny' : 'allow', code: want.code }
    : want;
  const got = await RUNNERS[surface](rowOf(c.row));
  if (got.verdict === expected.verdict && got.code === expected.code) return null;
  return `${surface} ${c.row}: expected ${expected.verdict}/${expected.code}, got ${got.verdict}/${got.code}`;
}

beforeAll(() => {
  home = mkdtempSync(path.join(tmpdir(), 'rdc-parity-'));
  const configDir = path.join(home, 'config', 'rediacc');
  mkdirSync(configDir, { recursive: true });
  // One config per case, named by its row id, so each surface reads the policy and repo the row stands for.
  for (const c of CASES) {
    writeFileSync(path.join(configDir, `${c.row}.json`), JSON.stringify(configFor(rowOf(c.row))));
  }
  bootExecutor();
}, 60_000);

afterAll(async () => {
  for (const client of mcpClients.values()) await client.close();
  const running = executor;
  if (running) await new Promise<void>((resolve) => running.close(() => resolve()));
  if (home) rmSync(home, { recursive: true, force: true });
});

const SLOW = 120_000;
const AGENT_ANCESTRY = isAgentByAncestry();

describe('case file', () => {
  it('names rows that exist, once each, each reaching at least decide and executor', () => {
    expect(new Set(CASES.map((c) => c.row)).size).toBe(CASES.length);
    for (const c of CASES) {
      rowOf(c.row);
      expect(c.surfaces).toEqual(expect.arrayContaining(['decide', 'executor']));
    }
  });

  it('covers every verdict the local surfaces can answer, and every surface', () => {
    const local = CASES.filter((c) => c.surfaces.includes('cli'));
    expect(new Set(local.map((c) => rowOf(c.row).expect.verdict))).toEqual(
      new Set(['allow', 'deny'])
    );
    for (const surface of ['decide', 'cli', 'mcp', 'executor'] as const) {
      expect(CASES.some((c) => c.surfaces.includes(surface))).toBe(true);
    }
  });

  it('keeps the deviation to a row an agent-free owner reaches with no policy', () => {
    const deviating = CASES.filter((c) => c.executorDeviation);
    expect(deviating.map((c) => c.row)).toEqual(['null-human-owner-grand']);
  });
});

for (const surface of ['decide', 'cli', 'mcp', 'executor'] as const) {
  describe(`surface ${surface}`, () => {
    const cases = CASES.filter((c) => c.surfaces.includes(surface));

    // A human principal on the CLI is a process with no agent among its ancestors (the child walks the same /proc chain as this process), so under an agent session those rows cannot be reached and are skipped by name; CI has no agent ancestor and runs them.
    const unreachable = (c: ParityCase) =>
      surface === 'cli' && rowOf(c.row).principal.kind === 'human' && AGENT_ANCESTRY;

    it.each(cases.map((c) => [c.row, c] as const))(
      '%s answers as the table expects',
      async (_id, c) => {
        if (unreachable(c)) return;
        expect(await mismatch(surface, c)).toBeNull();
      },
      SLOW
    );

    // The control flips the verdict; if the surface stopped comparing, or always answered the same, this would pass silently, so here it must report a mismatch.
    it(
      'control: a flipped expectation is reported as a mismatch',
      async () => {
        const [first] = cases;
        expect(first).toBeDefined();
        expect(await mismatch(surface, first as ParityCase, true)).not.toBeNull();
      },
      SLOW
    );
  });
}

describe('the table controls', () => {
  it.each(TABLE.controls.map((r) => [r.id, r] as const))(
    '%s is reported as a mismatch by decide',
    (_id, row) => {
      const got = viaDecide(row);
      expect(got.verdict === row.expect.verdict && got.code === row.expect.code).toBe(false);
    }
  );
});
