/**
 * Parity harness, on-premise leg (agent/plans/PLAN-rmcp-decide.md box D8): the human rows of the
 * shared decision table, chosen by fixtures/parity-cases.json (`onprem` in a case's surfaces),
 * driven through the on-premise executor the way a customer's host runs it: the real
 * `rdc serve --mode daemon` as a subprocess, reading its config (and the policy in it) off disk,
 * answering `POST /v1/command` to a bearer token the account resolved to a principal. Each row
 * asserts the verdict and code the table expects, the same as the in-process legs of parity.test.ts.
 *
 * The account server is a loopback stand-in that answers token introspection and takes audit and
 * run-index events. The Node account entry of PLAN-rmcp-executor-hardening.md EHOP1 is not started
 * here, because a vitest file cannot bring up its RustFS and seeded store; the stack's own daemon
 * suite (.ci/rediacc_ci/testrun/onprem_suites/daemon.py) covers that wiring. What this leg proves is
 * the daemon process: its config loader, its authorize and its route, in one real process each.
 *
 * Agent rows are absent by construction: a daemon is not pinned to an org, so it has no grant
 * sessions and an agent principal never reaches it (the hosted leg, parity-remote.test.ts, carries
 * those). Expectations come from the table rows, written by hand, never from the daemon, and a
 * control case with a flipped expectation must be reported as a mismatch.
 */

import { type ChildProcess, spawn } from 'node:child_process';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http';
import type { AddressInfo } from 'node:net';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { CLI_CONTRACT_VERSION } from '@rediacc/shared/cli-contract';
import { PROXY_ROUTES } from '@rediacc/shared/cli-contract/wire';
import {
  DECISION_CODES,
  type DecisionContext,
  type PolicyDocument,
  PolicyDocumentSchema,
} from '@rediacc/shared/policy';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

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
  expect: Expectation;
}

interface ParityCase {
  row: string;
  surfaces: string[];
  executorDeviation?: Expectation & { why: string };
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
).cases.filter((c) => c.surfaces.includes('onprem'));

function rowOf(id: string): FixtureRow {
  const row = TABLE.rows.find((r) => r.id === id);
  if (!row) throw new Error(`parity-cases.json names the row "${id}", which the table lacks.`);
  return row;
}

const GRAND_GUID = '11111111-1111-4111-8111-111111111111';
const FORK_GUID = '22222222-2222-4222-8222-222222222222';
const EXECUTOR_TOKEN = 'rdt_executor';
const SLOW = 120_000;

function verdictOfCode(code: string): string {
  if (code === 'ALLOWED') return 'allow';
  return code === 'CONFIRMATION_REQUIRED' ? 'needs_confirmation' : 'deny';
}

/** The daemon process is itself an `rdc` command judged by the policy of the config it starts under, so a row's allow list also names `serve`; the rows' own commands are unchanged. */
function withServeAllowed(policy: PolicyDocument): PolicyDocument {
  const allow = policy.defaults?.commands?.allow;
  if (allow === undefined || allow.includes('*')) return policy;
  return {
    ...policy,
    defaults: {
      ...policy.defaults,
      commands: { ...policy.defaults?.commands, allow: [...allow, 'serve'] },
    },
  };
}

/** The config a daemon's disk holds for a row: its repo (a grand, or a fork with its tag), its org-tier policy, one machine at a refused port. */
function configFor(row: FixtureRow): Record<string, unknown> {
  if (row.policy?.team !== undefined) {
    throw new Error(`Row ${row.id} has a team tier, which a local-file config cannot carry.`);
  }
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
  const org = row.policy?.org;
  const policy: PolicyDocument | undefined =
    org === undefined ? undefined : withServeAllowed(PolicyDocumentSchema.parse(org));
  return {
    schemaVersion: 3,
    id: '00000000-0000-4000-8000-0000000007d8',
    version: 1,
    credentials: { ssh: { privateKey: 'KEY' } },
    resources: { machines: { m1: { ip: '127.0.0.1', user: 'root', port: 1 } }, repositories },
    encryption: { mode: 'plaintext' },
    ...(policy ? { policy } : {}),
  };
}

// ---------------------------------------------------------------------------------------------
// the account server stand-in
// ---------------------------------------------------------------------------------------------

let account: Server;
let accountUrl = '';
/** Every request the daemon made of the account, as `METHOD path`, so a leg that never reached it is visible. */
const accountCalls: string[] = [];

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve) => {
    let raw = '';
    req.on('data', (chunk: Buffer) => (raw += chunk.toString()));
    req.on('end', () => resolve(raw));
  });
}

/** A bearer token is `rdt:<orgRole>:<teamSlug>`; the executor's own token reports its scopes. */
function introspection(token: string): Record<string, unknown> {
  if (token === EXECUTOR_TOKEN) {
    return { active: true, scopes: ['proxy:exec', 'audit:write'], orgId: 'org-1' };
  }
  const [, orgRole = 'member', teamSlug] = token.split(':');
  return {
    active: true,
    scopes: ['proxy:exec'],
    orgId: 'org-1',
    teamId: teamSlug ? `${teamSlug}-id` : null,
    ...(teamSlug ? { teamSlug } : {}),
    createdByUserId: 'user-1',
    userEmail: 'person@example.com',
    orgRole,
  };
}

async function accountAnswer(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const url = new URL(req.url ?? '/', 'http://account');
  accountCalls.push(`${req.method} ${url.pathname}`);
  const body = await readBody(req);
  res.setHeader('content-type', 'application/json');
  if (url.pathname.endsWith('/proxy/introspect')) {
    const { token } = JSON.parse(body) as { token: string };
    res.end(JSON.stringify(introspection(token)));
    return;
  }
  res.end('{}');
}

// ---------------------------------------------------------------------------------------------
// the daemon
// ---------------------------------------------------------------------------------------------

let home: string;

function daemonEnv(): Record<string, string> {
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
  env.REDIACC_TOKEN = EXECUTOR_TOKEN;
  env.REDIACC_ACCOUNT_SERVER = accountUrl;
  env.REDIACC_TELEMETRY_DISABLED = '1';
  return env;
}

async function freePort(): Promise<number> {
  const probe = createServer();
  await new Promise<void>((resolve) => probe.listen(0, '127.0.0.1', resolve));
  const { port } = probe.address() as AddressInfo;
  await new Promise<void>((resolve) => probe.close(() => resolve()));
  return port;
}

interface Daemon {
  child: ChildProcess;
  url: string;
}

const daemons: Daemon[] = [];

/** `rdc serve --mode daemon` on a free loopback port for the row's config, once it answers server-info as a daemon. */
async function startDaemon(configName: string): Promise<Daemon> {
  const port = await freePort();
  const args = ['tsx', 'src/index.ts', '--config', configName];
  args.push('serve', '--mode', 'daemon', '--port', String(port));
  const child = spawn('npx', args, {
    cwd: CLI_ROOT,
    env: daemonEnv(),
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: true,
  });
  let output = '';
  child.stdout?.on('data', (chunk: Buffer) => (output += chunk.toString()));
  child.stderr?.on('data', (chunk: Buffer) => (output += chunk.toString()));
  const daemon: Daemon = { child, url: `http://127.0.0.1:${port}` };
  daemons.push(daemon);
  for (let attempt = 0; attempt < 120 && child.exitCode === null; attempt++) {
    try {
      const response = await fetch(`${daemon.url}${PROXY_ROUTES.serverInfo}`);
      const info = (await response.json()) as { mode?: string };
      if (info.mode === 'daemon') return daemon;
    } catch {
      // not listening yet
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`The daemon for ${configName} never answered as a daemon.\n${output}`);
}

function stopDaemon(daemon: Daemon): void {
  const pid = daemon.child.pid;
  if (pid === undefined) return;
  try {
    process.kill(-pid, 'SIGTERM');
  } catch {
    // already gone
  }
}

async function viaDaemon(row: FixtureRow): Promise<Expectation> {
  const daemon = await startDaemon(row.id);
  try {
    const { orgRole, teamSlug } = row.principal;
    const response = await fetch(`${daemon.url}${PROXY_ROUTES.command}`, {
      method: 'POST',
      headers: {
        authorization: `Bearer rdt:${orgRole}:${teamSlug ?? ''}`,
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        contractVersion: CLI_CONTRACT_VERSION,
        pathKey: row.command.pathKey,
        positionals: { ref: row.target.repo?.name ?? '' },
        params: {},
      }),
    });
    const body = await response.text();
    // A 200 opens the command stream, which the route does only after authorize and the audit gate passed: the positive evidence of an allow. What the command then does at its refused port is not policy.
    if (response.status === 200) return { verdict: 'allow', code: 'ALLOWED' };
    const parsed = JSON.parse(body) as { error: string; code?: string };
    if (parsed.code === undefined || !(DECISION_CODES as readonly string[]).includes(parsed.code)) {
      throw new Error(`The daemon refused without a decision code (${response.status}): ${body}`);
    }
    return { verdict: verdictOfCode(parsed.code), code: parsed.code };
  } finally {
    stopDaemon(daemon);
  }
}

/** What the daemon must answer for a case: the row's expectation, or the case's pinned deviation (the executor's own, which a daemon shares). */
function expectedOf(c: ParityCase): Expectation {
  if (c.executorDeviation) {
    return { verdict: c.executorDeviation.verdict, code: c.executorDeviation.code };
  }
  return rowOf(c.row).expect;
}

async function mismatch(c: ParityCase, flip = false): Promise<string | null> {
  const want = expectedOf(c);
  const expected = flip
    ? { verdict: want.verdict === 'allow' ? 'deny' : 'allow', code: want.code }
    : want;
  const got = await viaDaemon(rowOf(c.row));
  if (got.verdict === expected.verdict && got.code === expected.code) return null;
  return `onprem ${c.row}: expected ${expected.verdict}/${expected.code}, got ${got.verdict}/${got.code}`;
}

beforeAll(async () => {
  home = mkdtempSync(path.join(tmpdir(), 'rdc-parity-onprem-'));
  const configDir = path.join(home, 'config', 'rediacc');
  mkdirSync(configDir, { recursive: true });
  for (const c of CASES) {
    writeFileSync(path.join(configDir, `${c.row}.json`), JSON.stringify(configFor(rowOf(c.row))));
  }
  account = createServer((req, res) => void accountAnswer(req, res));
  await new Promise<void>((resolve) => account.listen(0, '127.0.0.1', resolve));
  accountUrl = `http://127.0.0.1:${(account.address() as AddressInfo).port}`;
}, 60_000);

afterAll(async () => {
  for (const daemon of daemons) stopDaemon(daemon);
  await new Promise<void>((resolve) => account.close(() => resolve()));
  if (home) rmSync(home, { recursive: true, force: true });
});

describe('on-premise case file', () => {
  it('names human rows only, each a row the table has, with no team tier in its policy', () => {
    expect(CASES.length).toBeGreaterThan(0);
    for (const c of CASES) {
      const row = rowOf(c.row);
      expect(row.principal.kind).toBe('human');
      expect(row.policy?.team).toBeUndefined();
    }
  });

  it('covers an allow and a deny', () => {
    expect(new Set(CASES.map((c) => expectedOf(c).verdict))).toEqual(new Set(['allow', 'deny']));
  });
});

describe('surface onprem (rdc serve --mode daemon)', () => {
  it.each(CASES.map((c) => [c.row, c] as const))(
    '%s answers as the table expects',
    async (_id, c) => {
      expect(await mismatch(c)).toBeNull();
    },
    SLOW
  );

  it('asked the account server to identify the callers, so the daemon is what answered', () => {
    expect(accountCalls.some((call) => call.endsWith('/proxy/introspect'))).toBe(true);
  });

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
