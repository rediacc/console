/**
 * PLAN-rmcp-local-mcp LM10 (decision D57): every MCP tool of the LM2 surface table that is not `local` runs on the hosted executor.
 *
 * The serve app is real (`createServeApp`), the config store is the fake account of the grant harness with real ciphertext, and the
 * machine is the executor seam that records what would have run. Each case is a `POST /v1/mcp/call` as the MCP Worker posts it. The
 * table test replaces only the final command dispatch, to keep the account-server and SSH commands off the network, and records
 * which command each tool reached: a refusal (`proxyCapable: false`, an unknown tool, a policy denial) would stop the call before it.
 * The cases after it run the real command against the grant config.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { CLI_CONTRACT } from '@rediacc/shared/cli-contract';
import { listMcpTools, type McpToolEntry } from '@rediacc/shared/mcp/registry';
import type { Hono } from 'hono';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { COMMAND_METADATA } from '../../../config/command-metadata.js';
import type { ExecuteOptions, ExecuteResult } from '../../../services/executor/types.js';
import {
  EXECUTOR_TOKEN,
  fakeAccount,
  makeGrant,
  ORG_ID,
} from '../../../services/serve/__tests__/agent-grant-harness.js';
import { AgentGrantSessions } from '../../../services/serve/agent-grant-session.js';
import type { DispatchOutcome } from '../../../services/serve/command-dispatch.js';
import { routeAgentPrincipals } from '../../../services/serve/container-config.js';
import { serveCrypto } from '../../../services/serve/crypto.js';
import type { ServeDeps } from '../../../services/serve/deps.js';
import { authorize } from '../../../services/serve/policy.js';
import { createServeApp } from '../../../services/serve/server.js';
import { SessionStore } from '../../../services/serve/sessions.js';

// The dispatched command reads its config through the real configService, which must serve the config the grant session decrypted; the config dir is an empty scratch directory, so a dispatch that fell through to the disk finds nothing.
await vi.hoisted(async () => {
  const { mkdtempSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const scratch = mkdtempSync(`${tmpdir()}/rdc-surface-executor-`);
  process.env.XDG_CONFIG_HOME = scratch;
  process.env.XDG_STATE_HOME = scratch;
  process.env.XDG_CACHE_HOME = scratch;
});
process.env.REDIACC_TELEMETRY_DISABLED = '1';

const { dispatchStub } = vi.hoisted(() => ({
  dispatchStub: {
    reached: [] as string[],
    stubbed: false,
  },
}));
vi.mock('../../../services/serve/command-dispatch.js', async (original) => {
  const real = await original<typeof import('../../../services/serve/command-dispatch.js')>();
  return {
    ...real,
    dispatchCommand: (args: Parameters<typeof real.dispatchCommand>[0]) => {
      dispatchStub.reached.push(args.prepared.entry.pathKey);
      if (!dispatchStub.stubbed) return real.dispatchCommand(args);
      const stdout = JSON.stringify({
        success: true,
        command: args.prepared.entry.pathKey,
        data: {},
        errors: null,
        warnings: [],
      });
      const result: ExecuteResult = { success: true, exitCode: 0, durationMs: 1, stdout };
      return Promise.resolve<DispatchOutcome>({ result, stdout, stderr: '' });
    },
  };
});

const getMcpToolByCommand = (path: string): McpToolEntry | undefined =>
  listMcpTools().find((tool) => tool.command === path);

type Grant = Awaited<ReturnType<typeof makeGrant>>;

const asOwner: ServeDeps['authorize'] = (args) =>
  authorize({ ...args, principal: { ...args.principal, orgRole: 'owner' } });

interface Booted {
  app: Hono;
  grant: Grant;
}

async function boot(): Promise<Booted> {
  const grant = await makeGrant({
    grantId: 'g_a',
    teamId: 'team-a',
    configId: 'cfg-a',
    machine: 'machine-a',
    // Config-plane writes and the grand-repo reads are the point of the cases; the grant admits both.
    overrides: { grandRepos: '*', clusterOps: '*' },
  });
  const account = fakeAccount([grant]);
  const sessions = new AgentGrantSessions({
    accountUrl: 'https://account.test',
    executorToken: EXECUTOR_TOKEN,
    orgId: ORG_ID,
    fetchImpl: account.fetch,
  });
  const deps: ServeDeps = {
    mode: 'container',
    auth: {
      verify: () => Promise.reject(new Error('the call route takes no bearer')),
      canWriteAudit: () => Promise.resolve({ ok: true }),
    } as unknown as ServeDeps['auth'],
    sessions: new SessionStore(),
    crypto: serveCrypto,
    executor: {
      execute: (_options: ExecuteOptions) =>
        Promise.resolve({ success: true, exitCode: 0, durationMs: 1, stdout: 'ok' }),
    },
    loadConfig: routeAgentPrincipals(
      () => Promise.reject(new Error('a grant call never reaches the user loader')),
      sessions
    ),
    agentGrants: sessions,
    authorize: asOwner,
    audit: () => Promise.resolve(),
  };
  return { app: createServeApp(deps), grant };
}

interface Answer {
  result?: {
    isError?: boolean;
    content: { text: string }[];
    structuredContent?: { code?: string; message?: string };
  };
}

async function callTool(world: Booted, tool: string, args: Record<string, unknown>) {
  const response = await world.app.request('/v1/mcp/call', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      grantId: world.grant.grantId,
      secret: world.grant.secret,
      tool,
      args,
      requestId: `req-${Math.random().toString(16).slice(2)}`,
      attachMs: 45_000,
    }),
  });
  expect(response.status).toBe(200);
  return (await response.json()) as Answer;
}

/** The tools of the LM2 table that LM10 moved onto the executor: every `executor` and `in-memory` verdict, recorded by the surface table before LM10 and held as the proxy marker now. */
const EXECUTOR_TOOLS = [
  'backup check',
  'backup immutability show',
  'backup manifests',
  'backup reconcile',
  'backup repair',
  'backup retention',
  'backup retention preview',
  'backup strategy list',
  'backup strategy show',
  'backup toc-key sync',
  'backup undelete',
  'backup usage',
  'cluster status',
  'config access list',
  'config prune',
  'config reconcile',
  'config show',
  'credits',
  'feedback list',
  'feedback report',
  'feedback show',
  'legal',
  'machine access show',
  'machine add',
  'machine converge',
  'machine infra show',
  'machine list',
  'machine provider add',
  'machine provider list',
  'machine provider remove',
  'machine prune',
  'machine remove',
  'machine scan-keys',
  'repo replicate status',
  'repo secret get',
  'repo secret list',
] as const;

const LOCAL_TABLE = JSON.parse(
  readFileSync(
    fileURLToPath(new URL('../../../../../../.ci/config/mcp-surface.json', import.meta.url)),
    'utf-8'
  )
) as { tools: Record<string, { verdict: string; reason: string }> };

function registryEntry(commandPath: string): McpToolEntry {
  const entry = getMcpToolByCommand(commandPath);
  if (!entry) throw new Error(`no registry tool for "${commandPath}"`);
  return entry;
}

interface SchemaProp {
  type?: string;
  enum?: unknown[];
}

/** A dummy value for one required input field, by its JSON-schema type; the named fields take the grant config's repo and machine. */
function dummyValue(key: string, prop: SchemaProp): unknown {
  const named: Record<string, string> = { repo: 'demo', ref: 'demo', machine: 'machine-a' };
  if (prop.enum?.length) return prop.enum[0];
  if (prop.type === 'number' || prop.type === 'integer') return 1;
  if (prop.type === 'boolean') return true;
  return named[key] ?? 'x';
}

/** Dummy values for the input fields a tool requires. */
function minimalArgs(entry: McpToolEntry): Record<string, unknown> {
  const schema = entry.inputSchema as {
    properties?: Record<string, SchemaProp>;
    required?: string[];
  };
  return Object.fromEntries(
    (schema.required ?? []).map((key) => [key, dummyValue(key, schema.properties?.[key] ?? {})])
  );
}

beforeEach(() => {
  dispatchStub.reached.length = 0;
  dispatchStub.stubbed = false;
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe('the executor and in-memory tools of the surface table run on the executor (D57)', () => {
  it('lists every one of them as a proxy tool and proxyCapable in the contract, with no local row left for it', () => {
    for (const path of EXECUTOR_TOOLS) {
      const tool = registryEntry(path);
      expect(tool.surface, path).toBe('proxy');
      expect(COMMAND_METADATA[path]?.mcpSurface, path).toEqual({ kind: 'proxy' });
      expect(CLI_CONTRACT.commands.find((c) => c.pathKey === path)?.proxyCapable, path).toBe(true);
      expect(LOCAL_TABLE.tools[path], path).toBeUndefined();
    }
  });

  it('dispatches each of them through createServeApp and answers a result, never a proxyCapable refusal', async () => {
    dispatchStub.stubbed = true;
    const world = await boot();
    for (const path of EXECUTOR_TOOLS) {
      const entry = registryEntry(path);
      dispatchStub.reached.length = 0;
      const answer = await callTool(world, entry.name, minimalArgs(entry));
      const code = answer.result?.structuredContent?.code;
      expect(answer.result, path).toBeDefined();
      expect(code, `${path}: ${answer.result?.structuredContent?.message ?? ''}`).toBeUndefined();
      expect(answer.result?.isError, `${path}: ${JSON.stringify(answer.result)}`).toBe(false);
      expect(dispatchStub.reached, path).toEqual([path]);
    }
  }, 120_000);

  it('answers machine list from the grant config, not the executor disk', async () => {
    const world = await boot();
    const answer = await callTool(world, 'machine_list', {});
    expect(answer.result?.isError).toBe(false);
    expect(answer.result?.content[0]?.text).toContain('machine-a');
    expect(dispatchStub.reached).toEqual(['machine list']);
  });

  it('answers config show redacted, never carrying the grant ssh key', async () => {
    const world = await boot();
    const answer = await callTool(world, 'config_show', {});
    expect(answer.result?.isError).toBe(false);
    const text = answer.result?.content[0]?.text ?? '';
    // The grant config's own id and one machine, not the empty executor disk; the inline ssh key is redacted.
    expect(text).toContain('cfg-a');
    expect(text).toContain('"machines": 1');
    expect(text).not.toContain('KEY-cfg-a');
  });
});

describe('a local tool is still refused remotely, with its reason', () => {
  const locals = Object.entries(LOCAL_TABLE.tools).filter(([, row]) => row.verdict === 'local');

  it('holds the local rows of the table, all in the registry as local', () => {
    expect(locals.length).toBeGreaterThan(0);
    for (const [path] of locals) expect(registryEntry(path).surface, path).toBe('local');
  });

  it.each(locals)(
    'refuses %s with the written reason and dispatches nothing',
    async (path, row) => {
      const world = await boot();
      const answer = await callTool(world, registryEntry(path).name, {});
      expect(answer.result?.isError).toBe(true);
      expect(answer.result?.structuredContent?.code).toBe('INVALID_REQUEST');
      expect(answer.result?.structuredContent?.message).toContain(row.reason);
      expect(dispatchStub.reached).toEqual([]);
    }
  );
});
