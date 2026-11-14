/**
 * The two operator-only seams of `rdc server install`: the Bitwarden Secrets Manager backup
 * (`--bws-project`) and the DNS write for zones Rediacc owns. A customer install uses neither.
 *
 * bws reads go through the `bws` CLI (`secret list` carries no value on argv). bws 2.1 takes a
 * value only on argv, so writes go through the console checkout's
 * private/account/scripts/rotation/bws-write.ts, which reads the request on stdin and encrypts
 * client-side; without a checkout the backup is refused rather than putting a value in the
 * process table.
 */

import { spawn } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { getConfigDir } from '@rediacc/shared/paths';
import { t } from '../../i18n/index.js';
import { CloudflareDnsClient } from '../provision/cloudflare-dns.js';
import { ServerError } from './box.js';
import type { BwsRow, BwsWriteRequest } from './types.js';

const BWS_TIMEOUT_MS = 120_000;
const WRITER_REL = join('private', 'account', 'scripts', 'rotation', 'bws-write.ts');

/** BWS_ACCESS_TOKEN, else the token file every repo tool reads (`<config dir>/bws-access-token`). */
function bwsEnv(): NodeJS.ProcessEnv {
  if (process.env.BWS_ACCESS_TOKEN) return process.env;
  const file = process.env.BWS_ACCESS_TOKEN_FILE ?? join(getConfigDir(), 'bws-access-token');
  try {
    const token = readFileSync(file, 'utf-8').trim();
    if (token) return { ...process.env, BWS_ACCESS_TOKEN: token };
  } catch {
    // Reported below as a missing token.
  }
  throw new ServerError(t('commands.server.bws.noToken'));
}

function run(
  command: string,
  args: string[],
  opts: { env: NodeJS.ProcessEnv; cwd?: string; stdin?: string }
): Promise<{ code: number; stdout: string }> {
  return new Promise((resolve) => {
    const child = spawn(command, args, {
      env: opts.env,
      ...(opts.cwd ? { cwd: opts.cwd } : {}),
      stdio: ['pipe', 'pipe', 'ignore'],
      detached: true,
    });
    let stdout = '';
    const timer = setTimeout(() => {
      try {
        if (child.pid) process.kill(-child.pid, 'SIGKILL');
      } catch {
        // Already gone.
      }
    }, BWS_TIMEOUT_MS);
    child.stdout.on('data', (chunk: Buffer) => {
      stdout += chunk.toString('utf-8');
    });
    child.on('error', () => {
      clearTimeout(timer);
      resolve({ code: 127, stdout: '' });
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      resolve({ code: code ?? 1, stdout });
    });
    child.stdin.end(opts.stdin ?? '');
  });
}

export async function bwsList(): Promise<BwsRow[]> {
  const result = await run('bws', ['secret', 'list', '--output', 'json', '--color', 'no'], {
    env: bwsEnv(),
  });
  if (result.code !== 0) throw new ServerError(t('commands.server.bws.listFailed'));
  try {
    const rows = JSON.parse(result.stdout) as unknown;
    return Array.isArray(rows) ? (rows as BwsRow[]) : [];
  } catch {
    throw new ServerError(t('commands.server.bws.listFailed'));
  }
}

/** The console checkout holding bws-write.ts, searched upward from the working directory. */
function findWriter(): string | undefined {
  let dir = process.cwd();
  for (;;) {
    if (existsSync(join(dir, WRITER_REL))) return join(dir, 'private', 'account');
    const parent = dirname(dir);
    if (parent === dir) return undefined;
    dir = parent;
  }
}

export async function bwsWrite(request: BwsWriteRequest): Promise<void> {
  const account = findWriter();
  if (!account) throw new ServerError(t('commands.server.bws.noWriter'));
  const result = await run('npx', ['--no', 'tsx', join('scripts', 'rotation', 'bws-write.ts')], {
    env: bwsEnv(),
    cwd: account,
    stdin: JSON.stringify(request),
  });
  if (result.code !== 0) {
    throw new ServerError(t('commands.server.bws.writeFailed', { key: request.key }));
  }
}

export function ownedZoneToken(): string | undefined {
  return process.env.CLOUDFLARE_API_TOKEN?.trim() || undefined;
}

export async function writeDns(
  token: string,
  zone: string,
  type: 'A' | 'AAAA',
  name: string,
  value: string
): Promise<void> {
  const client = new CloudflareDnsClient(token);
  const zoneId = await client.getZoneId(zone);
  await client.ensureRecord(zoneId, type, name, value);
}
