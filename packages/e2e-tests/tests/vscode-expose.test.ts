import { expect, test } from '@playwright/test';
import { repoDockerHost } from '@rediacc/shared/config/runtime-paths';
import { DEFAULT_DATASTORE_PATH, DEFAULT_NETWORK_ID, TEST_PASSWORD } from '../src/constants';
import { assertLandlockSelected } from '../src/utils/landlock';
import { e2eRepoGuid } from '../src/utils/licence';
import { RenetFunctionsTestRunner } from '../src/utils/renet-functions/RenetFunctionsTestRunner';
import type { ExecResult } from '../src/utils/renet-functions/types';

/**
 * Browser VS Code behind the route server's portal-token gate, on a worker VM
 * (agent/plans/PLAN-vscode-browser-exposure.md box V5).
 *
 * `repository_vscode_expose` starts the pinned code-server container on the
 * repository's own daemon with Traefik labels whose forwardAuth middleware
 * points at the route server's gate (`/vscode-gate/<guid>`, renet
 * pkg/router/gate.go); `repository_vscode_unexpose` removes it. The gate admits
 * a browser once per token the account server mints at
 * `POST /console/repos/:guid/vscode-token`, verified offline against the account
 * key the deployed renet bakes, and the route server's reaper removes an editor
 * 15 minutes after its last sign of life.
 *
 * The gate is asked directly on the route server's loopback address with the
 * X-Forwarded-* headers Traefik's forwardAuth sends, so neither DNS nor a
 * certificate is needed on the worker: the subject is the gate's decision.
 *
 * Identity: the suite seeds its own user per run through the account server's
 * TEST_MODE seams (a PROFESSIONAL subscription, whose plan carries the web
 * console, and a server-recoverable config store, which the console entitlement
 * requires), and licenses the repository under that user's own API token. The
 * gate compares the token's `sub` with the subscription of the licence
 * installed for the repository, so the token and the licence must come from the
 * same subscription; the harness-wide E2E_ACCOUNT_API_TOKEN may belong to
 * another user.
 *
 * Route server: a machine where `rdc machine infra push` ran has the
 * rediacc-router unit and it is used as it stands. A fresh worker has none, so
 * the suite writes /etc/rediacc/router.env (MACHINE_NAME, BASE_DOMAIN, PORT,
 * which expose reads) and starts `renet router` as a transient unit with the
 * production unit's data dir; both are removed afterwards.
 *
 * The reaper test waits out the real 15 minute idle window: the idle clock is
 * the latest of the container's creation, its exposed_at label and its last
 * heartbeat, so it cannot be shortened from outside without a renet change.
 *
 * Run (one worker, an account server with TEST_MODE seams):
 *   PYTHONPATH=.ci python3 -m rediacc_ci.testrun.e2e --test tests/vscode-expose.test.ts --fail-on-skip
 */

const RUN_ID = Date.now();
const REPO = e2eRepoGuid();
const NETWORK_ID = DEFAULT_NETWORK_ID;
const DATASTORE = DEFAULT_DATASTORE_PATH;
const DOCKER = `sudo docker -H ${repoDockerHost(NETWORK_ID)}`;
const CONTAINER = 'rediacc-vscode';
const ROUTER_ENV = '/etc/rediacc/router.env';
const ROUTER_UNIT = 'rediacc-router';
const TRANSIENT_UNIT = 'rediacc-e2e-vscode-router';
const ROUTER_DATA_DIR = '/var/lib/rediacc/router';
const DEFAULT_ROUTER_PORT = 7111;
const SUITE_MACHINE = 'e2e-vscode';
const SUITE_BASE_DOMAIN = 'renet.local';
const IDLE_TIMEOUT_S = 15 * 60;
/** The reaper ticks once a minute; two ticks plus a sweep is the slack after the idle window. */
const REAPER_SLACK_S = 150;
const SESSION_COOKIE = 'rdc_vscode_session';
const EMAIL = `e2e-vscode-${RUN_ID}@rediacc.io`;
const LOGIN_PHRASE = `E2eVscode${RUN_ID}!`;
const API_TOKEN_SCOPES = ['license:read', 'license:activate', 'subscription:read'] as const;

/** One cookie session against `/account/api/v1`, as the portal holds one. */
class PortalSession {
  private readonly jar = new Map<string, string>();

  constructor(private readonly base: string) {}

  async call(
    method: string,
    route: string,
    body?: unknown
  ): Promise<{ status: number; json: unknown; text: string }> {
    const headers: Record<string, string> = {};
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (this.jar.size > 0) headers.Cookie = [...this.jar.values()].join('; ');
    const response = await fetch(`${this.base}/account/api/v1${route}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    for (const header of response.headers.getSetCookie()) {
      const pair = header.split(';')[0];
      this.jar.set(pair.split('=')[0], pair);
    }
    const text = await response.text();
    let json: unknown = text;
    try {
      json = JSON.parse(text) as unknown;
    } catch {
      // A non-JSON answer stays as text.
    }
    return { status: response.status, json, text };
  }

  /** A call that must answer 2xx; the route and status name the failure, never a body with secrets. */
  async must(method: string, route: string, body?: unknown): Promise<unknown> {
    const { status, json, text } = await this.call(method, route, body);
    if (status < 200 || status >= 300) {
      const detail = route.startsWith('/api-tokens') ? '' : `: ${text.slice(0, 300)}`;
      throw new Error(`${this.base} ${method} ${route} answered HTTP ${status}${detail}`);
    }
    return json;
  }
}

/** The forwardAuth answer the gate gave: status, headers and the session cookie it set. */
interface GateAnswer {
  status: number;
  location: string;
  cookie: string;
  setCookie: string;
  raw: string;
}

function parseGateAnswer(result: ExecResult): GateAnswer {
  const raw = result.stdout;
  const status = Number(/^HTTP (\d{3})\s*$/m.exec(raw)?.[1] ?? 0);
  const header = (name: string) => new RegExp(`^${name}:\\s*(.*?)\\s*$`, 'im').exec(raw)?.[1] ?? '';
  const setCookie = header('set-cookie');
  const cookie = new RegExp(`^${SESSION_COOKIE}=([^;]*)`).exec(setCookie)?.[1] ?? '';
  return { status, location: header('location'), cookie, setCookie, raw };
}

test.describe
  .serial('VS Code browser exposure @bridge @landlock', () => {
    let runner: RenetFunctionsTestRunner;
    let portal: PortalSession;
    let machine = SUITE_MACHINE;
    let routerPort = DEFAULT_ROUTER_PORT;
    let routerUnit = ROUTER_UNIT;
    let ownRouter = false;
    let hostname = '';
    /** The admission token the fresh-token test spent, which the stale-token test presents again. */
    let usedToken = '';

    function must(step: string, result: ExecResult): void {
      if (!runner.isSuccess(result)) {
        throw new Error(`${step} failed: ${runner.getCombinedOutput(result)}`);
      }
    }

    async function onWorker(command: string, timeout?: number): Promise<string> {
      const result = await runner.executeViaBridge(command, timeout);
      must(command, result);
      return result.stdout.trim();
    }

    /** The editor container's state on the repository daemon, '' when it does not exist. */
    function editorState(): Promise<string> {
      return onWorker(`${DOCKER} ps -a --filter name=^${CONTAINER}$ --format {{.State}}`);
    }

    async function workerNow(): Promise<number> {
      return Number(await onWorker('date +%s'));
    }

    /** Mint a token through the console route, exactly as the portal's button does. */
    async function mintToken(purpose: 'open' | 'heartbeat'): Promise<string> {
      const minted = (await portal.must('POST', `/console/repos/${REPO}/vscode-token`, {
        machine,
        purpose,
      })) as { token?: string; kind?: string };
      expect(minted.kind).toBe(purpose === 'open' ? 'vscode' : 'vscode-heartbeat');
      expect(typeof minted.token).toBe('string');
      return minted.token ?? '';
    }

    /**
     * Ask the gate as Traefik's forwardAuth does. The token and cookie ride a curl config on
     * stdin, never the command line.
     */
    async function askGate(opts: { token?: string; cookie?: string }): Promise<GateAnswer> {
      const query = opts.token
        ? `?folder=/data/work&rdc_vscode=${opts.token}`
        : '?folder=/data/work';
      const lines = [
        `header = "X-Forwarded-Host: ${hostname}"`,
        `header = "X-Forwarded-Uri: /${query}"`,
        'header = "X-Forwarded-Method: GET"',
        'header = "X-Forwarded-Proto: https"',
      ];
      if (opts.cookie) lines.push(`header = "Cookie: ${SESSION_COOKIE}=${opts.cookie}"`);
      const result = await runner.executeViaBridge(
        `curl -sS -o /dev/null -D - -w 'HTTP %{http_code}\\n' -K - http://127.0.0.1:${routerPort}/vscode-gate/${REPO}`,
        undefined,
        { stdin: `${lines.join('\n')}\n`, redactOutput: true }
      );
      must('asking the gate', result);
      return parseGateAnswer(result);
    }

    function expose(): Promise<ExecResult> {
      return runner.testFunction({
        function: 'repository_vscode_expose',
        repository: REPO,
        datastorePath: DATASTORE,
        networkId: NETWORK_ID,
        timeout: 900_000,
      });
    }

    function unexpose(): Promise<ExecResult> {
      return runner.testFunction({
        function: 'repository_vscode_unexpose',
        repository: REPO,
        datastorePath: DATASTORE,
        networkId: NETWORK_ID,
      });
    }

    /** Seed the suite's own subscribed user with a config store, and answer its API token. */
    async function seedPortalUser(server: string): Promise<string> {
      portal = new PortalSession(server);
      const credentials = { email: EMAIL, password: LOGIN_PHRASE };
      await portal.must('POST', '/test/ensure-login', credentials);
      await portal.must('POST', '/test/ensure-subscription', {
        email: EMAIL,
        planCode: 'PROFESSIONAL',
      });
      await portal.must('POST', '/auth/login', credentials);
      const terms = (await portal.must('GET', '/portal/terms')) as {
        satisfied?: boolean;
        current?: { version?: string; sha256?: string };
      };
      if (terms.satisfied === false) {
        await portal.must('POST', '/portal/terms/accept', {
          version: terms.current?.version,
          sha256: terms.current?.sha256,
          locale: 'en',
          method: 'web-checkbox',
        });
      }
      const subscriptionId = ((await portal.must('GET', '/portal/subscription')) as { id?: string })
        .id;
      if (!subscriptionId) throw new Error(`${server} returned no subscription for ${EMAIL}`);
      // Before the store: seeding it turns on TOTP for the user.
      const minted = (await portal.must('POST', '/api-tokens', {
        subscriptionId,
        name: `e2e-vscode-${RUN_ID}`,
        scopes: API_TOKEN_SCOPES,
      })) as { token?: string };
      if (!minted.token) throw new Error(`${server} minted no API token for ${EMAIL}`);
      await portal.must('POST', '/test/seed-config-store', { email: EMAIL, emptyStore: true });
      return minted.token;
    }

    /** Use the machine's rediacc-router when it runs, else start one as a transient unit. */
    async function ensureRouter(): Promise<void> {
      const active = await runner.executeViaBridge(`systemctl is-active ${ROUTER_UNIT}`);
      if (active.stdout.trim() === 'active') {
        const env = await onWorker(`sudo cat ${ROUTER_ENV}`);
        const value = (key: string) =>
          new RegExp(`^${key}="?([^"\\n]*)"?$`, 'm').exec(env)?.[1]?.trim() ?? '';
        machine = value('MACHINE_NAME');
        routerPort = Number(value('PORT')) || DEFAULT_ROUTER_PORT;
        expect(machine, `${ROUTER_ENV} names no MACHINE_NAME`).not.toBe('');
        return;
      }
      ownRouter = true;
      routerUnit = TRANSIENT_UNIT;
      const env = [
        '# Written by e2e vscode-expose',
        `BASE_DOMAIN="${SUITE_BASE_DOMAIN}"`,
        `MACHINE_NAME="${SUITE_MACHINE}"`,
        `PORT="${DEFAULT_ROUTER_PORT}"`,
        '',
      ].join('\n');
      must(
        `writing ${ROUTER_ENV}`,
        await runner.executeViaBridge(
          `sudo mkdir -p /etc/rediacc ${ROUTER_DATA_DIR} && sudo tee ${ROUTER_ENV} >/dev/null`,
          undefined,
          { stdin: env }
        )
      );
      const renet = await onWorker('command -v renet');
      must(
        'starting the route server',
        await runner.executeViaBridge(
          `sudo systemd-run --unit=${TRANSIENT_UNIT} --collect ${renet} router --port=${DEFAULT_ROUTER_PORT} --base-domain=${SUITE_BASE_DOMAIN} --machine-name=${SUITE_MACHINE} --data-dir=${ROUTER_DATA_DIR} --refresh-interval=3 --watchdog=false`
        )
      );
      const health = await runner.executeViaBridge(
        `for i in $(seq 1 30); do curl -sf -o /dev/null http://127.0.0.1:${DEFAULT_ROUTER_PORT}/health && exit 0; sleep 1; done; exit 1`,
        60_000
      );
      must('waiting for the route server /health', health);
    }

    test.beforeAll(async () => {
      test.setTimeout(900_000);
      const server = (process.env.REDIACC_ACCOUNT_SERVER ?? '').trim().replace(/\/+$/, '');
      if (!server) {
        throw new Error(
          'REDIACC_ACCOUNT_SERVER must name an account server with TEST_MODE seams: CI exports it from rediacc_ci.testrun.start_account; locally run `./run.sh account dev`'
        );
      }
      runner = RenetFunctionsTestRunner.forWorker();
      await assertLandlockSelected(runner);
      await runner.resetWorkerState();
      must('datastore init', await runner.datastoreInitPool('10G', DATASTORE, true));

      const apiToken = await seedPortalUser(server);
      // The licence must carry the suite user's subscription (see the header), so this create
      // licenses under the suite's token; the harness token is restored at once.
      const harnessToken = process.env.E2E_ACCOUNT_API_TOKEN;
      process.env.E2E_ACCOUNT_API_TOKEN = apiToken;
      try {
        must('repository_new', await runner.repositoryNew(REPO, '4G', TEST_PASSWORD, DATASTORE));
      } finally {
        if (harnessToken === undefined) delete process.env.E2E_ACCOUNT_API_TOKEN;
        else process.env.E2E_ACCOUNT_API_TOKEN = harnessToken;
      }
      // A mount starts the repository's daemon and socket; no Rediaccfile runs.
      must(
        'repository_mount',
        await runner.repositoryMount(REPO, TEST_PASSWORD, DATASTORE, NETWORK_ID)
      );
      await ensureRouter();
    });

    test.afterAll(async () => {
      if (!runner) return;
      await unexpose().catch(() => undefined);
      await runner.repositoryUnmount(REPO, DATASTORE, NETWORK_ID);
      await runner.repositoryRm(REPO, DATASTORE, NETWORK_ID);
      await runner.daemonTeardown(NETWORK_ID);
      if (ownRouter) {
        await runner.executeViaBridge(
          `sudo systemctl stop ${TRANSIENT_UNIT}; sudo rm -f ${ROUTER_ENV} ${ROUTER_DATA_DIR}/vscode-gate.key ${ROUTER_DATA_DIR}/vscode-gate.nonces ${ROUTER_DATA_DIR}/vscode-heartbeats/${REPO}`
        );
      }
    });

    test('repository_vscode_expose starts the editor behind the gate', async () => {
      test.setTimeout(900_000);
      const result = await expose();
      must('repository_vscode_expose', result);
      const url = /https:\/\/(vscode\.[a-z0-9.-]+)\/\?folder=\/data\/work/.exec(
        `${result.stdout}\n${result.stderr}`.toLowerCase()
      );
      expect(
        url,
        `expose printed no editor URL\n${runner.getCombinedOutput(result)}`
      ).not.toBeNull();
      hostname = url?.[1] ?? '';
      expect(hostname).toContain(`.${machine}.`);
      expect(await editorState()).toBe('running');

      // The forwardAuth middleware points at this machine's gate for this repository.
      const labels = JSON.parse(
        await onWorker(`${DOCKER} inspect -f '{{json .Config.Labels}}' ${CONTAINER}`)
      ) as Record<string, string>;
      expect(labels[`traefik.http.middlewares.rdc-vscode-gate-${REPO}.forwardauth.address`]).toBe(
        `http://127.0.0.1:${routerPort}/vscode-gate/${REPO}`
      );
      expect(labels['rediacc.vscode.repo']).toBe(REPO);

      // code-server answers on its service IP, so the gate fronts a live editor.
      const ip = labels['rediacc.service_ip'];
      expect(ip, 'the editor holds no service IP').toMatch(/^127\.\d+\.\d+\.\d+$/);
      const alive = await runner.executeViaBridge(
        `for i in $(seq 1 60); do curl -sf http://${ip}:8080/healthz && exit 0; sleep 2; done; exit 1`,
        180_000
      );
      must('code-server /healthz', alive);
    });

    test('the gate refuses a request with neither token nor session', async () => {
      const answer = await askGate({});
      expect(answer.status, answer.raw).toBe(401);
      expect(answer.cookie).toBe('');
    });

    test('a fresh token is admitted once and the session cookie it sets opens the editor', async () => {
      const token = await mintToken('open');
      const answer = await askGate({ token });
      expect(answer.status, answer.raw).toBe(302);
      expect(answer.cookie, 'the admission set no session cookie').not.toBe('');
      expect(answer.setCookie.toLowerCase()).toContain('httponly');
      expect(answer.setCookie.toLowerCase()).toContain('secure');
      expect(answer.setCookie.toLowerCase()).not.toContain('domain=');
      expect(answer.location).not.toContain('rdc_vscode=');
      usedToken = token;

      const withCookie = await askGate({ cookie: answer.cookie });
      expect(withCookie.status, withCookie.raw).toBe(200);
    });

    test('a stale token, already spent, is refused', async () => {
      expect(usedToken, 'the admission test minted no token').not.toBe('');
      const answer = await askGate({ token: usedToken });
      expect(answer.status, answer.raw).toBe(401);
      expect(answer.cookie).toBe('');
    });

    test('a heartbeat token admits nothing', async () => {
      const heartbeat = await mintToken('heartbeat');
      const answer = await askGate({ token: heartbeat });
      expect(answer.status, answer.raw).toBe(401);
      expect(answer.cookie).toBe('');
    });

    test('repository_vscode_unexpose removes the editor at once', async () => {
      must('repository_vscode_unexpose', await unexpose());
      expect(await editorState()).toBe('');
    });

    test('the idle reaper removes an editor 15 minutes after it was exposed', async () => {
      test.setTimeout((IDLE_TIMEOUT_S + REAPER_SLACK_S) * 1000 + 900_000);
      must('repository_vscode_expose (again)', await expose());
      expect(await editorState()).toBe('running');
      const exposedAt = Number(
        await onWorker(
          `${DOCKER} inspect -f '{{index .Config.Labels "rediacc.vscode.exposed_at"}}' ${CONTAINER}`
        )
      );
      expect(exposedAt, 'the editor carries no exposed_at label').toBeGreaterThan(0);

      // No heartbeat comes, so the editor is idle from exposed_at on. It must still run inside the
      // window and be gone within the reaper's slack after it.
      let goneAt = 0;
      for (;;) {
        const now = await workerNow();
        const state = await editorState();
        if (state === '') {
          goneAt = now;
          break;
        }
        expect(
          now - exposedAt,
          `the editor still runs ${now - exposedAt}s after exposure`
        ).toBeLessThan(IDLE_TIMEOUT_S + REAPER_SLACK_S);
        await new Promise((resolve) => setTimeout(resolve, 20_000));
      }
      expect(
        goneAt - exposedAt,
        'the editor was removed inside the idle window, so something other than the reaper removed it'
      ).toBeGreaterThanOrEqual(IDLE_TIMEOUT_S);

      // The route server's own log names the removal.
      const log = await runner.executeViaBridge(
        `sudo journalctl -u ${routerUnit} --no-pager -o cat --since @${exposedAt}`
      );
      expect(runner.getCombinedOutput(log)).toContain(
        `vscode reaper: removed idle editor ${CONTAINER} (repo ${REPO})`
      );
    });
  });
