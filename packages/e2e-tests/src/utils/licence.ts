import { randomUUID } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { DEFAULT_DATASTORE_PATH } from '../constants';
import type { CliResult, CliRunner } from './CliRunner';
import type { ExecResult } from './renet-functions/types';

/**
 * Repository licences for the e2e harness.
 *
 * renet has one build, and it enforces licensing (renet aa872edb): `renet
 * repository create`, `fork` and `commit` refuse with exit 10 LICENSE_REQUIRED
 * unless a licence for the new repository's GUID, signed by the key baked into
 * that renet, sits in the machine's licence store. `renet functions once
 * --test-mode` enforces licensing like every other path (renet 23c0c03b removed
 * its executor tier-check bypass), so every tiered repository function it runs
 * needs the repo licensed, not only create. So a
 * suite that creates a repository through raw renet needs a licence installed
 * first, exactly as `rdc repo create` does it: ask the account server's
 * `/licenses/activate-repo` for a blob, then file it where renet reads it.
 *
 * Three consequences a suite has to live with:
 *   - The repository name IS its GUID to renet (the harness's vault maps the
 *     name to itself), and the account server signs only a UUID. A friendly
 *     name such as `test-repo-123` cannot be licensed at all, so repo names in
 *     raw-renet suites come from {@link e2eRepoGuid}.
 *   - The account server is REDIACC_ACCOUNT_SERVER and the API token is
 *     E2E_ACCOUNT_API_TOKEN (CI: `rediacc_ci.testrun.start_account`; locally the
 *     global setup mints one on the dev gateway, {@link ensureAccountToken}).
 *   - The server must sign with the key the deployed renet bakes. A mismatch
 *     installs a blob renet never looks up; {@link installRepoLicence} reports
 *     the fingerprint it installed under so the log names the mismatch.
 */

/** renet's licence store root (pkg/license/store.go LicenseDir). */
const LICENSE_DIR = '/var/lib/rediacc/license';
/** renet's datastore descriptor, relative to the datastore mount (pkg/datastore DescriptorRelPath). */
const DESCRIPTOR_REL_PATH = '.rediacc/datastore.json';
/** pkg/license/store.go datastoreIDPattern: an identity outside it reads as unscoped. */
const DATASTORE_ID_PATTERN = /^[0-9a-fA-F-]{8,64}$/;
const PUBLIC_KEY_ID_PATTERN = /^[0-9a-f]{16}$/;
const MACHINE_ID_PATTERN = /^[a-f0-9]{64}$/i;
const GUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
/** The plan a locally minted token's subscription carries; CI's start_account seeds the same. */
const LOCAL_PLAN = 'PROFESSIONAL';
const LOCAL_EMAIL = 'e2e-bridge-licence@rediacc.io';
const LOCAL_LOGIN_PHRASE = 'E2eBridgeLicence123!';
const LOCAL_TOKEN_SCOPES = [
  'license:read',
  'license:activate',
  'subscription:read',
  'backup:read',
] as const;

/** The runner's bridge executor (RenetFunctionsTestRunner.executeViaBridge). */
export type BridgeExec = (
  command: string,
  timeout?: number,
  options?: { stdin?: string; redactOutput?: boolean }
) => Promise<ExecResult>;

/** A fresh repository GUID: the only name renet can be licensed for. */
export const e2eRepoGuid = (): string => randomUUID();

/** Whether a repository name can carry a licence (the account server signs UUIDs only). */
const isRepoGuid = (name: string): boolean => GUID_PATTERN.test(name);

/** The account server licences come from, read at call time (global setup may set it). */
const accountServer = (): string =>
  (process.env.REDIACC_ACCOUNT_SERVER ?? '').trim().replace(/\/+$/, '');

/** The API token licences are issued under, read at call time. */
const accountToken = (): string => (process.env.E2E_ACCOUNT_API_TOKEN ?? '').trim();

export interface RepoLicenceRequest {
  /** The repository's renet name, which must be a GUID. */
  readonly repositoryGuid: string;
  readonly kind: 'grand' | 'fork';
  /** The lineage's grand, for a fork or a commit. */
  readonly grandGuid?: string;
  /** The create size (`1G`, `500M`); the request rounds it up to whole GB, minimum 1. */
  readonly size?: string;
  /** The datastore mount the repository lands in; default the machine's base pool. */
  readonly datastorePath?: string;
}

const failure = (message: string): ExecResult => ({
  stdout: '',
  stderr: `[licence] ${message}\n`,
  code: 10,
});

function sizeToGb(size: string | undefined): number {
  const match = /^(\d+(?:\.\d+)?)([MGT])?$/i.exec((size ?? '').trim());
  if (!match) return 1;
  const value = Number(match[1]);
  const unit = (match[2] ?? 'G').toUpperCase();
  if (unit === 'T') return Math.ceil(value * 1024);
  if (unit === 'M') return Math.max(1, Math.ceil(value / 1024));
  return Math.max(1, Math.ceil(value));
}

/** The host's machine id, the `clientMachineId` the server records beside the target's. */
function clientMachineId(): string {
  const id = existsSync('/etc/machine-id') ? readFileSync('/etc/machine-id', 'utf8').trim() : '';
  return id || 'e2e-harness';
}

/** The datastore identity renet scopes the licence store by, or '' for the unscoped base pool. */
function datastoreIdFrom(descriptor: string): string {
  try {
    const parsed = JSON.parse(descriptor) as { datastoreId?: unknown };
    const id = typeof parsed.datastoreId === 'string' ? parsed.datastoreId : '';
    return DATASTORE_ID_PATTERN.test(id) ? id : '';
  } catch {
    return '';
  }
}

/** A refusal on the licence path, turned into the code-10 result by installRepoLicence. */
class LicenceRefusal extends Error {}

/** Why a request cannot be licensed at all, before anything touches the machine or the server. */
function requestProblem(request: RepoLicenceRequest): string | undefined {
  const { repositoryGuid, grandGuid } = request;
  if (!isRepoGuid(repositoryGuid)) {
    return (
      `repository "${repositoryGuid}" is not a GUID. renet licenses a repository by its name, ` +
      'and the account server signs UUIDs only, so a raw-renet suite must name its repositories ' +
      'with e2eRepoGuid() (src/utils/licence.ts).'
    );
  }
  if (grandGuid !== undefined && !isRepoGuid(grandGuid)) {
    return `grand "${grandGuid}" of ${repositoryGuid} is not a GUID.`;
  }
  if (!accountServer() || !accountToken()) {
    return (
      'REDIACC_ACCOUNT_SERVER and E2E_ACCOUNT_API_TOKEN must both be set to license a repository. ' +
      'CI exports them from rediacc_ci.testrun.start_account; locally run `./run.sh account dev` ' +
      'and the global setup finds the gateway and mints the token.'
    );
  }
  return undefined;
}

/** The target's licence identity, read as root exactly as renet computes it. */
async function targetMachineId(exec: BridgeExec): Promise<string> {
  const machine = await exec('sudo -n renet machine-id');
  const machineId = machine.stdout.trim().split('\n').pop()?.trim() ?? '';
  if (machine.code !== 0 || !MACHINE_ID_PATTERN.test(machineId)) {
    throw new LicenceRefusal(
      `could not read the target's machine id (exit ${machine.code}): ${(machine.stdout + machine.stderr).slice(-400)}`
    );
  }
  return machineId;
}

/** The signed blob for one repository, from the account server's activate-repo. */
async function activateRepo(body: Record<string, unknown>): Promise<{ publicKeyId: string }> {
  const guid = String(body.repositoryGuid);
  let license: { publicKeyId?: unknown } | undefined;
  try {
    const response = await fetch(`${accountServer()}/account/api/v1/licenses/activate-repo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accountToken()}` },
      body: JSON.stringify(body),
    });
    const text = await response.text();
    if (!response.ok) {
      throw new LicenceRefusal(
        `activate-repo for ${guid} answered HTTP ${response.status}: ${text.slice(0, 400)}`
      );
    }
    license = (JSON.parse(text) as { license?: { publicKeyId?: unknown } }).license;
  } catch (error) {
    if (error instanceof LicenceRefusal) throw error;
    throw new LicenceRefusal(
      `activate-repo for ${guid} failed: ${error instanceof Error ? error.message : String(error)}`
    );
  }
  const publicKeyId = license?.publicKeyId;
  if (typeof publicKeyId !== 'string' || !PUBLIC_KEY_ID_PATTERN.test(publicKeyId)) {
    throw new LicenceRefusal(
      `activate-repo for ${guid} returned no signed blob with a publicKeyId: ${JSON.stringify(license).slice(0, 200)}`
    );
  }
  return { ...license, publicKeyId };
}

/**
 * File the blob where renet reads it, and answer the path. The scope rule of renet's
 * RepoLicenseBaseDir: an identity puts it under datastores/<id>/repos, no identity under
 * the unscoped repos/. The file is named by the signer's fingerprint, which must be the
 * baked key's for renet to read it.
 */
async function writeLicence(
  exec: BridgeExec,
  repositoryGuid: string,
  datastoreId: string,
  license: { publicKeyId: string }
): Promise<string> {
  const dir = datastoreId
    ? `${LICENSE_DIR}/datastores/${datastoreId}/repos/${repositoryGuid}`
    : `${LICENSE_DIR}/repos/${repositoryGuid}`;
  const file = `${dir}/${license.publicKeyId}.json`;
  const write = await exec(
    `sudo mkdir -p ${dir} && sudo tee ${file} > /dev/null && sudo chmod 640 ${file}`,
    undefined,
    { stdin: JSON.stringify(license, null, 2) }
  );
  if (write.code !== 0) {
    throw new LicenceRefusal(
      `could not write ${file} (exit ${write.code}): ${(write.stdout + write.stderr).slice(-400)}`
    );
  }
  return file;
}

/**
 * Issue a licence for one repository on the runner's target machine and install it there.
 *
 * Returns an ExecResult so a caller hands a refusal back the way it hands back a
 * renet failure: code 0 when the blob is in place, code 10 (LICENSE_REQUIRED, the
 * code renet itself would have exited with) and a `[licence]` reason otherwise.
 */
export async function installRepoLicence(
  exec: BridgeExec,
  request: RepoLicenceRequest
): Promise<ExecResult> {
  const problem = requestProblem(request);
  if (problem) return failure(problem);
  try {
    const machineId = await targetMachineId(exec);
    const datastorePath = request.datastorePath ?? DEFAULT_DATASTORE_PATH;
    const descriptor = await exec(
      `sudo cat ${datastorePath}/${DESCRIPTOR_REL_PATH} 2>/dev/null || true`
    );
    const datastoreId = datastoreIdFrom(descriptor.stdout);
    const license = await activateRepo({
      machineId,
      clientMachineId: clientMachineId(),
      repositoryGuid: request.repositoryGuid,
      grandGuid: request.grandGuid,
      kind: request.kind,
      requestedSizeGb: sizeToGb(request.size),
      ...(datastoreId ? { datastoreId } : {}),
    });
    const file = await writeLicence(exec, request.repositoryGuid, datastoreId, license);
    return { stdout: `[licence] installed ${request.kind} licence ${file}\n`, stderr: '', code: 0 };
  } catch (error) {
    if (error instanceof LicenceRefusal) return failure(error.message);
    throw error;
  }
}

/** One `/account/api/v1` call with a cookie session, for the local token mint. */
class AccountSession {
  private readonly jar = new Map<string, string>();

  constructor(private readonly base: string) {}

  async call(
    method: string,
    route: string,
    body?: unknown
  ): Promise<{ status: number; json: unknown }> {
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
    try {
      return { status: response.status, json: JSON.parse(text) as unknown };
    } catch {
      return { status: response.status, json: text };
    }
  }

  /** A call that must answer 2xx. */
  async must(method: string, route: string, body?: unknown): Promise<unknown> {
    const { status, json } = await this.call(method, route, body);
    if (status < 200 || status >= 300) {
      throw new Error(`${this.base} ${route} answered HTTP ${status} (is TEST_MODE on?)`);
    }
    return json;
  }
}

/** The `.account-state` file of this checkout, searched upward from the working directory. */
function findAccountState(): string | undefined {
  let dir = process.cwd();
  for (let i = 0; i < 8; i++) {
    const state = path.join(dir, '.account-state');
    if (existsSync(state)) return state;
    const parent = path.dirname(dir);
    if (parent === dir) return undefined;
    dir = parent;
  }
  return undefined;
}

/** The local dev gateway (`./run.sh account dev`), when this checkout runs one that answers. */
async function localGateway(): Promise<string> {
  const state = findAccountState();
  const port = state ? /^gateway_port=(\d+)$/m.exec(readFileSync(state, 'utf8'))?.[1] : undefined;
  if (!port) return '';
  const url = `http://127.0.0.1:${port}`;
  try {
    const health = await fetch(`${url}/health`, { signal: AbortSignal.timeout(5000) });
    return health.ok ? url : '';
  } catch {
    return '';
  }
}

/** Seed a subscribed user through the TEST_MODE seams and mint its token, as start_account does. */
async function mintLocalToken(server: string): Promise<string> {
  const session = new AccountSession(server);
  const credentials = { email: LOCAL_EMAIL, password: LOCAL_LOGIN_PHRASE };
  await session.must('POST', '/test/ensure-login', credentials);
  await session.must('POST', '/test/ensure-subscription', {
    email: LOCAL_EMAIL,
    planCode: LOCAL_PLAN,
  });
  await session.must('POST', '/auth/login', credentials);
  const subscriptionId = ((await session.must('GET', '/portal/subscription')) as { id?: string })
    .id;
  if (!subscriptionId) throw new Error(`${server} returned no subscription for ${LOCAL_EMAIL}`);
  const minted = (await session.must('POST', '/api-tokens', {
    subscriptionId,
    name: `e2e-bridge-${Date.now()}`,
    scopes: LOCAL_TOKEN_SCOPES,
  })) as { token?: string };
  if (!minted.token) throw new Error(`${server} minted no API token for ${LOCAL_EMAIL}`);
  process.env.E2E_ACCOUNT_API_TOKEN = minted.token;
  return subscriptionId;
}

/**
 * Make REDIACC_ACCOUNT_SERVER and E2E_ACCOUNT_API_TOKEN available to every worker.
 *
 * CI exports both (start_account) and this returns at once. A local run outside
 * GitHub Actions with no server named uses the checkout's dev gateway when one
 * answers; with a server but no token it mints one (mintLocalToken). Playwright
 * workers start after the global setup, so the values set here reach them.
 * Returns a one-line description, never the token.
 */
export async function ensureAccountToken(): Promise<string> {
  if (!accountServer() && process.env.GITHUB_ACTIONS !== 'true') {
    const gateway = await localGateway();
    if (gateway) process.env.REDIACC_ACCOUNT_SERVER = gateway;
  }
  const server = accountServer();
  if (!server) {
    return 'no account server: REDIACC_ACCOUNT_SERVER is unset and no local dev gateway answers; every repository create will refuse with LICENSE_REQUIRED';
  }
  if (accountToken()) return `account server ${server}, token from E2E_ACCOUNT_API_TOKEN`;
  const subscriptionId = await mintLocalToken(server);
  return `account server ${server}, token minted for ${LOCAL_EMAIL} (subscription ${subscriptionId})`;
}

/**
 * Log a CLI config in to the account server, so `rdc repo create` / `fork` can
 * issue the licence renet demands. Run after `initConfig`.
 */
export function loginCliToAccount(cli: CliRunner): Promise<CliResult> {
  const server = accountServer();
  const token = accountToken();
  if (!server || !token) {
    return Promise.resolve({
      code: 10,
      stdout: '',
      stderr:
        '[licence] REDIACC_ACCOUNT_SERVER and E2E_ACCOUNT_API_TOKEN must both be set for the CLI to license a repository.\n',
    });
  }
  return cli.run(['subscription', 'login', '--server', server, '--token', token]);
}
