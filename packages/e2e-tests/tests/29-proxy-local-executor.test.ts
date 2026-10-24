import { type ChildProcess, spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { existsSync, readFileSync, rmSync } from 'node:fs';
import http from 'node:http';
import type { AddressInfo } from 'node:net';
import net from 'node:net';
import path from 'node:path';
import { expect, test } from '@playwright/test';
import { getSSHPrivateKeyPath } from '@rediacc/provisioning';
import { AuditEventsRequestSchema } from '@rediacc/shared';
import { DEFAULT_DATASTORE_PATH } from '../src/constants';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';
import { type CliResult, CliRunner } from '../src/utils/CliRunner';

/**
 * Suite 29: `rdc --proxy` against a LOCAL executor (`rdc serve --mode daemon`),
 * box B4 of agent/plans/PLAN-cloudflare-proxy.md (missing test 6).
 *
 * ## What runs for real, and what is stood in
 *
 * Real: the `rdc` client in proxy mode, the `rdc serve` executor (its HTTP
 * server, token check, policy, command dispatch and audit call), the worker VM
 * and the fork's Docker daemon on it.
 *
 * Stood in: the account server. The executor asks it two things, whose token a
 * caller presented (`POST /account/api/v1/proxy/introspect`) and where to record
 * what ran (`POST /account/api/v1/licenses/audit-events`). E2E Workers legs have
 * no account server, so this suite serves those two routes from a loopback stub
 * with two fixed tokens: the executor's own (`proxy:exec` and `audit:write`) and
 * one caller's (`proxy:exec`, org owner). Any other token introspects as
 * inactive, which is how the real server answers an unknown or foreign token.
 * The stub also answers introspection only when the executor authenticates with
 * its own token, so an executor that forgot its credential fails here too.
 *
 * ## What each case proves
 *
 *   1. CONTROL: `repo up` with a token the account server does not know exits
 *      non-zero with the executor's 401, records no audit event, and the
 *      machine shows that nothing started.
 *   2. `repo status` through the proxy exits 0 and returns the fork's own record
 *      from the machine (its GUID).
 *   3. `repo up` through the proxy exits 0, and the fork's Docker daemon on the
 *      worker runs the fork's service.
 *   4. `repo down` through the proxy exits 0, and that container is gone.
 *
 * Each of 2-4 also checks the audit event the executor sent: the command, the
 * machine, success, and the caller's token id as `onBehalfOfTokenId`.
 *
 * The fork, its parent, the executor and the stub are all this run's own, and
 * afterAll removes every one of them.
 */

const RUN_ID = Date.now();
const CONFIG_NAME = 'e2e-proxy';
const workers = (process.env.VM_WORKERS ?? '').trim().split(/\s+/).filter(Boolean);
const NET_BASE = process.env.VM_NET_BASE ?? '192.168.111';
const MACHINE = 'proxy-worker';
const MACHINE_IP = `${NET_BASE}.${workers[0] ?? '11'}`;
// The key and user the ops VMs authorize, resolved the way suite 23 resolves them.
const SSH_KEY = process.env.E2E_SSH_KEY ?? getSSHPrivateKeyPath();
const SSH_USER = process.env.E2E_SSH_USER ?? process.env.USER ?? 'root';

const GRAND = `proxy-${RUN_ID}`;
const TAG = 'px';
const FORK_REF = `${GRAND}:${TAG}`;
const CONTAINER = `proxy-idle-${RUN_ID}`;
const SERVICE_IMAGE = 'alpine:3.20';

// Fixed, run-scoped credentials of the stub account server. They grant nothing anywhere else.
const EXECUTOR_TOKEN = `e2e-executor-${RUN_ID}`;
const CALLER_TOKEN = `e2e-caller-${RUN_ID}`;
// UUIDs, as real token ids are: the stub's ingest schema refuses anything else in onBehalfOfTokenId.
const CALLER_TOKEN_ID = randomUUID();
const EXECUTOR_TOKEN_ID = randomUUID();
const WRONG_TOKEN = `e2e-unknown-${RUN_ID}`;

const REDIACCFILE = `#!/bin/bash
up() {
  renet compose -- up -d
}
down() {
  renet compose -- down -v
}
`;
const COMPOSE = `services:
  idle:
    image: ${SERVICE_IMAGE}
    container_name: ${CONTAINER}
    command: ["sleep", "infinity"]
`;

interface AuditEvent {
  type: string;
  onBehalfOfTokenId?: string;
  data: { commandPath?: string; machineName?: string; success: boolean };
}

interface StubAccountServer {
  url: string;
  audits: AuditEvent[];
  close: () => Promise<void>;
}

const IDENTITY_BASE = { active: true, orgId: 'org-e2e', orgRole: 'owner' };

/** What the account server reports for a presented token: the two known ones, and inactive for any other. */
function introspect(token: string | undefined): Record<string, unknown> {
  if (token === EXECUTOR_TOKEN) {
    return {
      ...IDENTITY_BASE,
      scopes: ['proxy:exec', 'audit:write'],
      createdByUserId: 'user-executor',
      userEmail: 'executor@e2e.invalid',
      tokenId: EXECUTOR_TOKEN_ID,
    };
  }
  if (token === CALLER_TOKEN) {
    return {
      ...IDENTITY_BASE,
      scopes: ['proxy:exec'],
      createdByUserId: 'user-caller',
      userEmail: 'caller@e2e.invalid',
      tokenId: CALLER_TOKEN_ID,
    };
  }
  return { active: false };
}

/** One request to the stub: the status and JSON body it answers with. */
function route(
  url: string | undefined,
  authorization: string | undefined,
  body: string,
  audits: AuditEvent[]
): [number, unknown] {
  const known =
    url === '/account/api/v1/proxy/introspect' || url === '/account/api/v1/licenses/audit-events';
  if (!known) return [404, { error: 'not served by the e2e stub' }];
  if (authorization !== `Bearer ${EXECUTOR_TOKEN}`) {
    return [401, { error: 'unknown executor credential' }];
  }
  if (url === '/account/api/v1/proxy/introspect') {
    return [200, introspect((JSON.parse(body) as { token?: string }).token)];
  }
  // The real ingest route parses with this schema and answers 400 otherwise; a stub that took any shape is how every executor event shipped invalid until 2026-10-24 while this suite stayed green.
  const parsed = AuditEventsRequestSchema.safeParse(JSON.parse(body));
  if (!parsed.success)
    return [400, { error: 'audit payload rejected', issues: parsed.error.issues }];
  audits.push(...(parsed.data.events as AuditEvent[]));
  return [200, { accepted: parsed.data.events.length }];
}

/** The two account-server routes the executor calls, with the tokens described above. */
async function startStubAccountServer(): Promise<StubAccountServer> {
  const audits: AuditEvent[] = [];
  const server = http.createServer((req, res) => {
    let body = '';
    req.on('data', (chunk: Buffer) => {
      body += chunk.toString('utf8');
    });
    req.on('end', () => {
      const [status, payload] =
        req.method === 'POST'
          ? route(req.url, req.headers.authorization, body, audits)
          : [404, { error: 'not served by the e2e stub' }];
      res.writeHead(status, { 'content-type': 'application/json' });
      res.end(JSON.stringify(payload));
    });
  });
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address() as AddressInfo;
  return {
    url: `http://127.0.0.1:${port}`,
    audits,
    close: () =>
      new Promise<void>((resolve) => {
        server.closeAllConnections();
        server.close(() => resolve());
      }),
  };
}

/** A loopback port nothing listens on right now. */
async function freePort(): Promise<number> {
  const probe = net.createServer();
  await new Promise<void>((resolve) => probe.listen(0, '127.0.0.1', resolve));
  const { port } = probe.address() as AddressInfo;
  await new Promise<void>((resolve) => probe.close(() => resolve()));
  return port;
}

/**
 * The argv prefix and environment of the CLI under test, resolved as CliRunner
 * resolves them: `E2E_CLI_BIN`, else the PATH `rdc` on GitHub Actions, else this
 * checkout's bundle. CliRunner only runs a command to completion, and the
 * executor has to keep running for the whole suite.
 */
function cliCommand(): { bin: string; prefix: string[] } {
  if (process.env.E2E_CLI_BIN) return { bin: process.env.E2E_CLI_BIN, prefix: [] };
  if (process.env.GITHUB_ACTIONS === 'true') return { bin: 'rdc', prefix: [] };
  return {
    bin: process.execPath,
    prefix: [path.resolve(__dirname, '../../cli/dist/cli-bundle.cjs')],
  };
}

function devRenetDir(): string | undefined {
  const candidate =
    process.env.RENET_BINARY_PATH ?? path.resolve(__dirname, '../../../private/renet/bin/renet');
  return existsSync(candidate) ? path.dirname(candidate) : undefined;
}

interface Executor {
  url: string;
  output: () => string;
  stop: () => Promise<void>;
}

/** The executor's environment: the CliRunner defaults, its own token, and the stub as its account server. */
function executorEnv(accountUrl: string): NodeJS.ProcessEnv {
  const renetDir = devRenetDir();
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    REDIACC_SKIP_MACHINE_ACTIVATION: '1',
    REDIACC_YES: '1',
    REDIACC_MASTER_PASSWORD: process.env.REDIACC_MASTER_PASSWORD ?? 'e2e-cli-master',
    REDIACC_TOKEN: EXECUTOR_TOKEN,
    REDIACC_ACCOUNT_SERVER: accountUrl,
  };
  if (renetDir) env.PATH = `${renetDir}${path.delimiter}${process.env.PATH ?? ''}`;
  delete env.REDIACC_PROXY_URL;
  return env;
}

/** Poll /v1/health until it answers, the process exits, or 60 s pass. */
async function waitForHealth(url: string, hasExited: () => boolean, output: () => string) {
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    if (hasExited())
      throw new Error(`rdc serve exited before it answered /v1/health:\n${output()}`);
    const healthy = await fetch(`${url}/v1/health`).then(
      (res) => res.ok,
      () => false
    );
    if (healthy) return;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`rdc serve did not answer /v1/health within 60s:\n${output()}`);
}

/** Start `rdc serve --mode daemon` on loopback and wait until it answers /v1/health. */
async function startExecutor(accountUrl: string): Promise<Executor> {
  const port = await freePort();
  const { bin, prefix } = cliCommand();
  const args = ['--config', CONFIG_NAME, 'serve', '--mode', 'daemon'];
  args.push('--host', '127.0.0.1', '--port', String(port));
  const child: ChildProcess = spawn(bin, [...prefix, ...args], {
    env: executorEnv(accountUrl),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let output = '';
  const collect = (chunk: Buffer) => {
    output += chunk.toString('utf8');
  };
  child.stdout?.on('data', collect);
  child.stderr?.on('data', collect);
  let exited = false;
  const exitedPromise = new Promise<void>((resolve) =>
    child.on('exit', () => {
      exited = true;
      resolve();
    })
  );

  const url = `http://127.0.0.1:${port}`;
  try {
    await waitForHealth(
      url,
      () => exited,
      () => output
    );
  } catch (error) {
    child.kill('SIGKILL');
    throw error;
  }

  return {
    url,
    output: () => output,
    stop: async () => {
      if (exited) return;
      child.kill('SIGTERM');
      const timer = setTimeout(() => child.kill('SIGKILL'), 20_000);
      await exitedPromise;
      clearTimeout(timer);
    },
  };
}

interface CliConfigFile {
  resources?: {
    repositories?: Record<string, { tags?: Record<string, { repositoryGuid?: string }> }>;
  };
  state?: { repos?: Record<string, Record<string, { networkId?: number }>> };
}

test.describe
  .serial('rdc --proxy through a local executor @cli @proxy', () => {
    test.setTimeout(600_000);

    let cli: CliRunner;
    let caller: CliRunner;
    let stranger: CliRunner;
    let runner: BridgeTestRunner;
    let stub: StubAccountServer | undefined;
    let executor: Executor | undefined;
    let forkGuid = '';
    let forkSocket = '';

    const combined = (result: CliResult) => `${result.stdout}\n${result.stderr}`;

    /** Run a command through the executor as the given client. */
    const viaProxy = (client: CliRunner, ...args: string[]): Promise<CliResult> => {
      if (!executor) throw new Error('the executor is not running');
      return client.run(['--proxy', executor.url, ...args]);
    };

    const must = (step: string, result: CliResult) => {
      if (result.code !== 0) {
        throw new Error(`${step} exited ${result.code}:\n${combined(result)}`);
      }
    };

    /** The fork's container as the fork's own Docker daemon reports it, '' when absent. */
    const forkContainerStatus = async (): Promise<string> => {
      const listed = await runner.executeViaBridge(
        `sudo test -S ${forkSocket} && sudo docker -H unix://${forkSocket} ps --filter name=${CONTAINER} --format '{{.Status}}' || true`
      );
      return listed.stdout.trim();
    };

    const auditFor = (command: string) =>
      (stub?.audits ?? []).filter((e) => e.data.commandPath === command);

    const expectAudited = (command: string) => {
      const events = auditFor(command);
      expect(events, `exactly one audit event for "${command}"`).toHaveLength(1);
      expect(events[0].data.success, `the "${command}" audit event records success`).toBe(true);
      expect(events[0].data.machineName).toBe(MACHINE);
      expect(events[0].onBehalfOfTokenId, 'attributed to the caller token').toBe(CALLER_TOKEN_ID);
    };

    const writeIntoRepo = async (guid: string, file: string, content: string) => {
      const target = `${DEFAULT_DATASTORE_PATH}/mounts/${guid}/${file}`;
      const b64 = Buffer.from(content, 'utf8').toString('base64');
      const written = await runner.executeViaBridge(
        `echo ${b64} | base64 -d | sudo tee ${target} >/dev/null && sudo chown rediacc:rediacc ${target}`
      );
      if (written.code !== 0) {
        throw new Error(`writing ${target} failed: ${written.stdout}\n${written.stderr}`);
      }
    };

    const readConfig = (): CliConfigFile =>
      JSON.parse(readFileSync(cli.configPath, 'utf8')) as CliConfigFile;

    // `repo create -m` places the repo on the machine's default datastore. A fleet reset leaves none, so it is created only when absent: forcing it would wipe repos other suites keep there.
    const ensureDatastore = async () => {
      const mounted = await runner.executeViaBridge(`mountpoint -q ${DEFAULT_DATASTORE_PATH}`);
      if (mounted.code === 0) return;
      const init = await runner.datastoreInitPool('5G', DEFAULT_DATASTORE_PATH, false);
      if (init.code !== 0) {
        throw new Error(`datastore init failed: ${init.stdout}\n${init.stderr}`);
      }
    };

    test.beforeAll(async () => {
      runner = BridgeTestRunner.forWorker();
      cli = CliRunner.create({ configName: CONFIG_NAME });
      caller = CliRunner.create({ configName: CONFIG_NAME, env: { REDIACC_TOKEN: CALLER_TOKEN } });
      stranger = CliRunner.create({ configName: CONFIG_NAME, env: { REDIACC_TOKEN: WRONG_TOKEN } });

      // The config records the fleet's host keys, so one that outlived a fleet reset is stale: recreated each run (see CliRunner.resetConfig).
      await CliRunner.resetConfig(CONFIG_NAME);
      must('config init', await cli.initConfig(SSH_KEY));
      must('machine add', await cli.addMachine(MACHINE, MACHINE_IP, SSH_USER));

      await ensureDatastore();

      // The fork's service is written into the parent before the fork, so the fork inherits it through the reflink.
      must('repo create', await cli.run(['repo', 'create', GRAND, '-m', MACHINE, '--size', '1G']));
      const grandGuid = readConfig().resources?.repositories?.[GRAND]?.tags?.latest?.repositoryGuid;
      if (!grandGuid) throw new Error(`repo create recorded no GUID for ${GRAND}`);
      await writeIntoRepo(grandGuid, 'Rediaccfile', REDIACCFILE);
      await writeIntoRepo(grandGuid, 'docker-compose.yaml', COMPOSE);
      must('repo fork', await cli.run(['repo', 'fork', GRAND, '--tag', TAG]));

      const config = readConfig();
      forkGuid = config.resources?.repositories?.[GRAND]?.tags?.[TAG]?.repositoryGuid ?? '';
      const networkId = config.state?.repos?.[GRAND]?.[TAG]?.networkId;
      if (!forkGuid || networkId === undefined) {
        throw new Error(`repo fork recorded no GUID or network id for ${FORK_REF}`);
      }
      forkSocket = `/var/run/rediacc/net-${networkId}/docker-${networkId}.sock`;

      stub = await startStubAccountServer();
      executor = await startExecutor(stub.url);
    });

    test.afterAll(async () => {
      const serveOutput = executor?.output() ?? '';
      await executor?.stop();
      await stub?.close();
      // The fork goes first: a parent with a live fork is not the thing to delete.
      const forkGone = await cli.run(['repo', 'delete', FORK_REF, '-y']);
      const grandGone = await cli.run(['repo', 'delete', GRAND, '-y']);
      await CliRunner.resetConfig(CONFIG_NAME);
      // The CLI keeps a backup beside the config, holding the deleted repos' credentials.
      rmSync(`${cli.configPath}.bak`, { force: true });
      if (forkGone.code !== 0 || grandGone.code !== 0) {
        throw new Error(
          `teardown left a repo behind:\n${combined(forkGone)}\n${combined(grandGone)}\n` +
            `executor output:\n${serveOutput}`
        );
      }
      const residue = await runner.executeViaBridge(
        `ls ${DEFAULT_DATASTORE_PATH}/repositories/ 2>/dev/null | grep -F ${forkGuid} || true`
      );
      expect(residue.stdout.trim(), `${FORK_REF} residue on the machine`).toBe('');
    });

    test('CONTROL: a token the account server does not know is refused, and nothing starts', async () => {
      const refused = await viaProxy(stranger, 'repo', 'up', FORK_REF);
      const output = combined(refused).toLowerCase();
      expect(refused.code, `a refused call exits non-zero\n${output}`).not.toBe(0);
      expect(output, 'the refusal is the executor 401').toContain(
        'proxy rejected this request (401)'
      );
      expect(output).toContain('this token is not valid for the executor');
      expect(stub?.audits, 'a refused call records no audit event').toHaveLength(0);
      expect(await forkContainerStatus(), 'nothing started on the machine').toBe('');
    });

    test("repo status through the proxy returns the fork's record from the machine", async () => {
      const status = await viaProxy(caller, 'repo', 'status', FORK_REF);
      expect(status.code, `repo status exits 0\n${combined(status)}`).toBe(0);
      expect(status.stdout, "the record is the fork's own").toContain(forkGuid);
      expectAudited('repo status');
    });

    test("repo up through the proxy starts the fork's service on the machine", async () => {
      const up = await viaProxy(caller, 'repo', 'up', FORK_REF);
      expect(up.code, `repo up exits 0\n${combined(up)}`).toBe(0);
      expect(await forkContainerStatus(), "the fork's daemon runs its service").toMatch(/^Up /);
      expectAudited('repo up');
    });

    test("repo down through the proxy stops the fork's service", async () => {
      const down = await viaProxy(caller, 'repo', 'down', FORK_REF);
      expect(down.code, `repo down exits 0\n${combined(down)}`).toBe(0);
      expect(await forkContainerStatus(), 'the service container is gone').toBe('');
      expectAudited('repo down');
    });
  });
