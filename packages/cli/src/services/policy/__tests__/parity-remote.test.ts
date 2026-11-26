/**
 * Parity harness, hosted-remote leg (agent/plans/PLAN-rmcp-remote-worker.md box RW-PAR, and box D8 of
 * agent/plans/PLAN-rmcp-decide.md): the agent rows of the shared decision table, chosen by
 * fixtures/parity-cases.json (`remote` in a case's surfaces), driven through the hosted MCP path end
 * to end the way a claude.ai client reaches it:
 *
 *   SDK client -> workers/mcp `createMcpTransport` (the real Worker: bearer, grant lookup, scope, `tools/call`)
 *     -> `EXECUTOR` binding -> workers/proxy `callMcp` (the McpExecutor body and the container request)
 *     -> the container's `POST /v1/mcp/call` on the real serve app: a real grant session over a fake
 *        account that seals real ciphertext, `runAiTool`, the real `authorize` and `decide`
 *
 * Only the bindings and the machine are faked: the account server (agent-grant-harness.ts), the
 * Worker's grant lookup, the proxy's Durable Object forward (a direct call of the container app) and
 * the executor seam that would have run the command on a machine. The row's policy rides in the
 * grant's sealed org policy record (none for a row with no policy), its opt-ins in the grant's
 * `overrides`, and its org role in the account's agent-session answer.
 *
 * Expectations come from the table rows, written by hand, never from the hosted path. ALLOWED is
 * reported only on positive evidence: the executor seam ran.
 * A control case with a flipped expectation must be reported as a mismatch.
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { Client, StreamableHTTPClientTransport } from '@modelcontextprotocol/client';
import {
  WK_ACCOUNT_DEFAULT_ORIGIN,
  WK_MCP_EU_HOST,
} from '@rediacc/shared/config/well-known.generated';
import { deriveAuthTag, formatAgentBearer } from '@rediacc/shared/config-crypto';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { getMcpTool } from '@rediacc/shared/mcp/registry';
import { DECISION_CODES, type DecisionContext, PolicyDocumentSchema } from '@rediacc/shared/policy';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ExecuteOptions } from '../../executor/types.js';
import {
  EXECUTOR_TOKEN,
  type FakeGrant,
  fakeAccount,
  makeGrant,
  ORG_ID,
} from '../../serve/__tests__/agent-grant-harness.js';
import { AgentGrantSessions } from '../../serve/agent-grant-session.js';
import { routeAgentPrincipals } from '../../serve/container-config.js';
import { serveCrypto } from '../../serve/crypto.js';
import type { ServeDeps } from '../../serve/deps.js';
import { authorize } from '../../serve/policy.js';
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
  expect: Expectation;
}

interface ParityCase {
  row: string;
  surfaces: string[];
}

const CLI_ROOT = path.resolve(import.meta.dirname, '..', '..', '..', '..');
const TABLE = JSON.parse(
  readFileSync(
    path.resolve(CLI_ROOT, '..', 'shared', 'src', 'policy', '__fixtures__', 'decision-table.json'),
    'utf8'
  )
) as { rows: FixtureRow[] };
const CASES = (
  JSON.parse(
    readFileSync(path.resolve(import.meta.dirname, 'fixtures', 'parity-cases.json'), 'utf8')
  ) as { cases: ParityCase[] }
).cases.filter((c) => c.surfaces.includes('remote'));

function rowOf(id: string): FixtureRow {
  const row = TABLE.rows.find((r) => r.id === id);
  if (!row) throw new Error(`parity-cases.json names the row "${id}", which the table lacks.`);
  return row;
}

const GRAND_GUID = '11111111-1111-4111-8111-111111111111';
const FORK_GUID = '22222222-2222-4222-8222-222222222222';
const HOST = WK_MCP_EU_HOST;
const ACCOUNT_ORIGIN = WK_ACCOUNT_DEFAULT_ORIGIN;
const SLOW = 60_000;

// The two Workers build apart from this package, so their modules are read where the test needs them, which also keeps this package's test typecheck (tsconfig.test.json, rootDir packages/cli) from claiming files outside it.
const WORKERS = path.resolve(CLI_ROOT, '..', '..', 'workers');
const loadWorkers = async () => {
  const mcp = (await import(path.join(WORKERS, 'mcp', 'src', 'transport.ts'))) as {
    createMcpTransport: (options: Record<string, unknown>) => {
      fetch: (request: Request) => Promise<Response>;
    };
  };
  const proxy = (await import(path.join(WORKERS, 'proxy', 'src', 'org-executor-mcp.ts'))) as {
    callMcp: (
      forward: Record<string, unknown>,
      send: (request: Request) => Promise<Response>
    ) => Promise<unknown>;
  };
  return { createMcpTransport: mcp.createMcpTransport, callMcp: proxy.callMcp };
};

function verdictOfCode(code: string): string {
  if (code === 'ALLOWED') return 'allow';
  if (code.startsWith('UNEXPECTED_FAILURE')) return 'error';
  return code === 'CONFIRMATION_REQUIRED' ? 'needs_confirmation' : 'deny';
}

/** The config the grant opens for a row: its repo (a grand, or a fork with its tag) and one machine. A remote config carries no policy field, so the row's policy is bound in `hostFor`. */
function configFor(row: FixtureRow, configId: string): RdcConfig {
  if (row.policy?.team !== undefined) {
    throw new Error(
      `Row ${row.id} has a team tier, which a grant's local-file config cannot carry.`
    );
  }
  const name = row.target.repo?.name;
  const state = row.target.repo?.state;
  const repositories: Record<string, unknown> = {};
  const repoState: Record<string, unknown> = {};
  if (name && state !== 'unresolved') {
    const [base = name, tag] = name.split(':');
    const tags: Record<string, unknown> = {
      latest: { repositoryGuid: GRAND_GUID, credential: 'set' },
    };
    repoState[base] = { latest: { networkId: 2816 } };
    if (state === 'fork' && tag) {
      tags[tag] = { repositoryGuid: FORK_GUID, grandGuid: GRAND_GUID };
      repoState[base] = { ...(repoState[base] as object), [tag]: { networkId: 2832 } };
    }
    repositories[base] = { grand: 'latest', placement: { machine: 'm1' }, tags };
  }
  return {
    schemaVersion: 3,
    id: configId,
    version: 1,
    credentials: { ssh: { privateKey: `KEY-${configId}` } },
    resources: { machines: { m1: { ip: '10.9.9.9', user: 'deploy', port: 22 } }, repositories },
    state: { repos: repoState },
    encryption: { mode: 'plaintext' },
  } as unknown as RdcConfig;
}

interface Hosted {
  client: Client;
  executed: ExecuteOptions[];
  close: () => Promise<void>;
}

/** The hosted path for one row's grant, from an SDK client down to the container's executor seam. */
async function hostFor(row: FixtureRow): Promise<Hosted> {
  const grantId = `g_${row.id.replaceAll(/[^A-Za-z0-9]/g, '_')}`.slice(0, 60);
  const org = row.policy?.org;
  const made = await makeGrant({
    grantId,
    teamId: null,
    configId: `cfg-${grantId}`.slice(0, 60),
    machine: 'm1',
    orgRole: row.principal.orgRole as FakeGrant['orgRole'],
    overrides: {
      grandRepos: (row.overrides.grandRepos ?? null) as FakeGrant['overrides']['grandRepos'],
      clusterOps: (row.overrides.clusterOps ?? null) as FakeGrant['overrides']['clusterOps'],
    },
    ...(org === undefined ? {} : { policies: { org: PolicyDocumentSchema.parse(org) } }),
  });
  // The harness seals an allow-all org record unless a case names one; a row with no policy has no
  // record at all, so the session loads no policy and `decide` sees the missing-policy default.
  if (org === undefined) made.policyRecords.clear();
  const account = fakeAccount([made]);
  await account.bump(grantId, configFor(row, made.configId));
  const sessions = new AgentGrantSessions({
    accountUrl: 'https://account.test',
    executorToken: EXECUTOR_TOKEN,
    orgId: ORG_ID,
    fetchImpl: account.fetch,
  });
  const executed: ExecuteOptions[] = [];
  const grantLoader = routeAgentPrincipals(
    () => Promise.reject(new Error('a grant call never reaches the user loader')),
    sessions
  );
  const deps: ServeDeps = {
    mode: 'container',
    auth: {
      verify: () => Promise.reject(new Error('the call route takes no bearer')),
      canWriteAudit: () => Promise.resolve({ ok: true }),
    } as unknown as ServeDeps['auth'],
    sessions: new SessionStore(),
    crypto: serveCrypto,
    executor: {
      execute: (options: ExecuteOptions) => {
        executed.push(options);
        return Promise.resolve({ success: true, exitCode: 0, durationMs: 1, stdout: 'ok' });
      },
    },
    loadConfig: grantLoader,
    agentGrants: sessions,
    authorize,
    audit: () => Promise.resolve(),
  };
  const app = createServeApp(deps);

  // The proxy's McpExecutor entrypoint: the forward becomes the request the container's route reads.
  const { createMcpTransport, callMcp } = await loadWorkers();
  const executor = {
    call: (_routing: unknown, forward: Record<string, unknown>) =>
      callMcp(forward, (request) => Promise.resolve(app.fetch(request))),
  };
  const authTag = await deriveAuthTag(made.secretBytes);
  const worker = createMcpTransport({
    host: HOST,
    serverVersion: '0.0.0-test',
    accountUrl: ACCOUNT_ORIGIN,
    resolveGrant: (id: string, tag: string) =>
      Promise.resolve(
        id === grantId && tag === authTag
          ? {
              grantId,
              state: 'active' as const,
              expiresAt: '2099-01-01T00:00:00.000Z',
              scope: { readOnly: false, tools: null, machines: null, repos: null },
              orgId: ORG_ID,
              placement: 0,
            }
          : null
      ),
    executor,
  });
  const bearer = formatAgentBearer(grantId, made.secretBytes);
  const fetchViaWorker = (input: string | URL | Request, init?: RequestInit) => {
    const request = new Request(input, init);
    request.headers.set('authorization', `Bearer ${bearer}`);
    return worker.fetch(request);
  };
  const client = new Client(
    { name: 'parity-remote', version: '0.0.0' },
    { versionNegotiation: { mode: { pin: '2026-07-28' } } }
  );
  await client.connect(
    new StreamableHTTPClientTransport(new URL(`https://${HOST}/g/${grantId}`), {
      fetch: fetchViaWorker,
    })
  );
  return { client, executed, close: () => client.close() };
}

/** The code one hosted `tools/call` answered: the decision code of a refusal, ALLOWED only when the executor seam ran and the tool did not fail, anything else an UNEXPECTED_FAILURE that matches no row. */
async function viaRemote(row: FixtureRow): Promise<Expectation> {
  const hosted = await hostFor(row);
  try {
    const result = await hosted.client.callTool({
      name: row.command.pathKey.replaceAll(' ', '_'),
      arguments: { ref: row.target.repo?.name ?? '' },
    });
    const structured = (result.structuredContent ?? {}) as {
      code?: string;
      message?: string;
      decisionCode?: string;
    };
    const decision = structured.decisionCode;
    if (decision !== undefined && (DECISION_CODES as readonly string[]).includes(decision)) {
      return { verdict: verdictOfCode(decision), code: decision };
    }
    // The executor seam ran: policy let the command through, whatever the command then did on the machine (a delete's config write-back is refused by the executor, which is not policy).
    if (hosted.executed.length > 0) return { verdict: 'allow', code: 'ALLOWED' };
    const message = structured.message ?? JSON.stringify(result.content).slice(0, 1200);
    return { verdict: 'error', code: `UNEXPECTED_FAILURE: ${message}` };
  } finally {
    await hosted.close();
  }
}

async function mismatch(c: ParityCase, flip = false): Promise<string | null> {
  const row = rowOf(c.row);
  const want = row.expect;
  const expected = flip
    ? { verdict: want.verdict === 'allow' ? 'deny' : 'allow', code: want.code }
    : want;
  const got = await viaRemote(row);
  if (got.verdict === expected.verdict && got.code === expected.code) return null;
  return `remote ${c.row}: expected ${expected.verdict}/${expected.code}, got ${got.verdict}/${got.code}`;
}

beforeEach(() => {
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe('hosted-remote case file', () => {
  it('names agent rows only, each a row the table has, each a tool the hosted surface serves', () => {
    expect(CASES.length).toBeGreaterThan(0);
    for (const c of CASES) {
      const row = rowOf(c.row);
      expect(row.principal.kind).toBe('agent');
      expect(getMcpTool(row.command.pathKey.replaceAll(' ', '_'))?.surface).toBe('proxy');
      expect(row.policy?.team).toBeUndefined();
    }
  });

  it('covers an allow and a deny', () => {
    expect(new Set(CASES.map((c) => rowOf(c.row).expect.verdict))).toEqual(
      new Set(['allow', 'deny'])
    );
  });
});

describe('surface remote (workers/mcp -> McpExecutor -> /v1/mcp/call)', () => {
  it.each(CASES.map((c) => [c.row, c] as const))(
    '%s answers as the table expects',
    async (_id, c) => {
      expect(await mismatch(c)).toBeNull();
    },
    SLOW
  );

  // The control flips the verdict; a leg that stopped comparing, or always answered the same, would pass here, so it must report a mismatch.
  it(
    'control: a flipped expectation is reported as a mismatch',
    async () => {
      const [first] = CASES;
      expect(first).toBeDefined();
      expect(await mismatch(first as ParityCase, true)).not.toBeNull();
    },
    SLOW
  );
});
