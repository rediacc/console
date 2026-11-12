/**
 * The live `ServerDeps`: a child `rdc` for the repo and machine verbs, the pooled SSH channel,
 * HTTPS to the box with its own trust roots, DNS, and the account server under the stored token.
 */

import { spawn } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { promises as dns } from 'node:dns';
import { chmod, mkdtemp, open, readFile } from 'node:fs/promises';
import { request as httpsRequest } from 'node:https';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import type { TLSSocket } from 'node:tls';
import { type AccountFetchError, accountServerFetch } from '../account/account-client.js';
import { getSubscriptionTokenState } from '../account/subscription-auth.js';
import { getEffectiveConfigName } from '../config/config-name.js';
import { writeStdout } from '../core/request-context.js';
import { machineConnections } from '../machine/machine-connection.js';
import { certToBase64, parseSignedCert } from './cert.js';
import { bwsList, bwsWrite, ownedZoneToken, writeDns } from './ops-deps.js';
import type { BoxReply, BoxTarget, IssueOutcome, ProcResult, ServerDeps } from './types.js';

const BOX_TIMEOUT_MS = 15_000;
const CERT_VALID_DAYS = 365;

/** The rdc binary: the SEA itself, or node plus the script it runs. */
function rdcBinary(): { command: string; prefix: string[] } {
  if (!process.argv[1] || process.execPath === process.argv[1]) {
    return { command: process.execPath, prefix: [] };
  }
  return { command: process.execPath, prefix: [process.argv[1]] };
}

/** A child `rdc` under this run's config: stdout captured, stderr (its progress) passed through. */
function runRdc(argv: string[]): Promise<ProcResult> {
  const bin = rdcBinary();
  const args = [...bin.prefix, '--config', getEffectiveConfigName(), ...argv];
  return new Promise((resolve) => {
    const child = spawn(bin.command, args, { stdio: ['ignore', 'pipe', 'inherit'] });
    let stdout = '';
    child.stdout.on('data', (chunk: Buffer) => {
      stdout += chunk.toString('utf-8');
    });
    child.on('error', (error) => resolve({ code: 1, stdout, stderr: error.message }));
    child.on('close', (code) => resolve({ code: code ?? 1, stdout, stderr: '' }));
  });
}

async function runSsh(machine: string, command: string, stdin?: string): Promise<ProcResult> {
  const lease = await machineConnections.acquire(machine);
  let stdout = '';
  let stderr = '';
  try {
    const code = await lease.sftp.execStreaming(command, {
      ...(stdin === undefined ? {} : { stdin }),
      onStdout: (data) => {
        stdout += data.toString('utf-8');
      },
      onStderr: (data) => {
        stderr += data.toString('utf-8');
      },
    });
    return { code, stdout, stderr };
  } finally {
    lease.release();
  }
}

function sansOf(socket: TLSSocket | undefined): string[] {
  const alt = socket?.getPeerCertificate?.()?.subjectaltname ?? '';
  return alt
    .split(',')
    .map((s) => s.trim())
    .filter((s) => s.startsWith('DNS:'))
    .map((s) => s.slice(4));
}

function boxRequest(
  target: BoxTarget,
  method: string,
  path: string,
  body?: unknown,
  cookie?: string
): Promise<BoxReply> {
  const payload = body === undefined ? undefined : JSON.stringify(body);
  return new Promise((resolve) => {
    const req = httpsRequest(
      {
        host: target.address ?? target.domain,
        servername: target.domain,
        port: 443,
        method,
        path,
        timeout: BOX_TIMEOUT_MS,
        ...(target.ca ? { ca: target.ca } : {}),
        headers: {
          Host: target.domain,
          ...(payload === undefined
            ? {}
            : { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) }),
          ...(cookie ? { Cookie: cookie } : {}),
        },
      },
      (res) => {
        const sans = sansOf(res.socket as TLSSocket);
        const found = (res.headers['set-cookie'] ?? [])
          .map((c) => c.split(';')[0])
          .find((c) => c.startsWith('access_token='));
        let text = '';
        res.on('data', (chunk: Buffer) => {
          text += chunk.toString('utf-8');
        });
        res.on('end', () => {
          let parsed: unknown = text;
          try {
            parsed = text ? JSON.parse(text) : {};
          } catch {
            // Not JSON: the text itself is reported.
          }
          resolve({ status: res.statusCode ?? 0, body: parsed, cookie: found, sans });
        });
      }
    );
    req.on('timeout', () => req.destroy());
    req.on('error', () => resolve({ status: 0, body: {}, sans: [] }));
    if (payload !== undefined) req.write(payload);
    req.end();
  });
}

async function resolveHost(host: string): Promise<string[]> {
  const [v4, v6] = await Promise.all([
    dns.resolve4(host).catch(() => [] as string[]),
    dns.resolve6(host).catch(() => [] as string[]),
  ]);
  return [...v4, ...v6];
}

async function issueCert(delegatedPublicKey: string): Promise<IssueOutcome> {
  const state = getSubscriptionTokenState();
  if (state.kind !== 'ready' || !state.token.subscriptionId) return { kind: 'no-login' };
  try {
    const answer = await accountServerFetch<{
      cert: unknown;
      autoRenewToken?: string;
      upstreamUrl?: string;
    }>('/account/api/v1/delegation/issue', {
      method: 'POST',
      body: {
        subscriptionId: state.token.subscriptionId,
        delegatedPublicKey,
        validDays: CERT_VALID_DAYS,
      },
    });
    const signed = parseSignedCert(JSON.stringify({ cert: answer.cert }));
    return {
      kind: 'issued',
      cert: {
        certBase64: certToBase64(signed),
        subscriptionId: state.token.subscriptionId,
        autoRenewToken: answer.autoRenewToken,
        upstreamUrl: answer.upstreamUrl ?? state.serverUrl,
      },
    };
  } catch (error) {
    return issueRefusal(error as AccountFetchError);
  }
}

/** The refusals `install` and `licence` know how to answer; anything else is rethrown. */
function issueRefusal(error: AccountFetchError): IssueOutcome {
  if (error.status === 403 && /Missing required scope/i.test(error.message)) {
    return { kind: 'missing-scope' };
  }
  if (error.code === 'PLAN_DISALLOWS_DELEGATION_CERT') {
    return { kind: 'plan-disallows', message: error.message };
  }
  if (error.status === 409) {
    const certId = String(error.details?.existingCertId ?? '');
    return { kind: 'other-key', certId, message: error.message };
  }
  throw error;
}

async function writePrivate(path: string, text: string): Promise<void> {
  const handle = await open(path, 'w', 0o600);
  try {
    await handle.writeFile(text, 'utf-8');
  } finally {
    await handle.close();
  }
  await chmod(path, 0o600);
}

export function liveServerDeps(): ServerDeps {
  return {
    rdc: runRdc,
    ssh: runSsh,
    box: boxRequest,
    resolve: resolveHost,
    ownedZoneToken,
    writeDns,
    bwsList,
    bwsWrite,
    issueCert,
    local: (command, args) =>
      new Promise((resolve) => {
        const child = spawn(command, args, { stdio: ['ignore', 'inherit', 'inherit'] });
        child.on('error', () => resolve(127));
        child.on('close', (code) => resolve(code ?? 1));
      }),
    tempDir: () => mkdtemp(join(tmpdir(), 'rdc-server-')),
    readFile: (path) => readFile(path, 'utf-8'),
    writePrivate,
    stdout: (text) => writeStdout(text),
    isTTY: () => process.stdin.isTTY === true && process.stdout.isTTY === true,
    sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
    now: () => Date.now(),
    secret: () => `${randomBytes(24).toString('base64url')}A1!`,
  };
}
