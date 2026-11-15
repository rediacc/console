/**
 * The live halves of the `ServerDeps` the air-gapped flow adds: local programs with captured
 * output, file hashing, the CLI's own renet binary, and a file copy to the machine.
 */

import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';
import { createReadStream } from 'node:fs';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, isAbsolute, join } from 'node:path';
import { t } from '../../i18n/index.js';
import { configService } from '../config/config-resources.js';
import {
  computeSha256,
  getEmbeddedMetadata,
  getEmbeddedRenetBinary,
  isSEA,
} from '../core/embedded-assets.js';
import { machineConnections } from '../machine/machine-connection.js';
import { ServerError } from './box.js';
import type { ProcResult, ServerDeps } from './types.js';

type OfflineDeps = Pick<
  ServerDeps,
  'localOut' | 'sha256File' | 'makeDir' | 'renetAsset' | 'uploadFile'
>;

function localOut(command: string, args: string[]): Promise<ProcResult> {
  return new Promise((resolve) => {
    const child = spawn(command, args, { stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (chunk: Buffer) => {
      stdout += chunk.toString('utf-8');
    });
    child.stderr.on('data', (chunk: Buffer) => {
      stderr += chunk.toString('utf-8');
    });
    child.on('error', (error) => resolve({ code: 127, stdout, stderr: error.message }));
    child.on('close', (code) => resolve({ code: code ?? 1, stdout, stderr }));
  });
}

function sha256File(path: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const hash = createHash('sha256');
    const stream = createReadStream(path);
    stream.on('data', (chunk) => hash.update(chunk));
    stream.on('error', reject);
    stream.on('end', () => resolve(hash.digest('hex')));
  });
}

/** This CLI's linux renet: the SEA's embedded asset, or `renet-linux-<arch>` beside the configured renet in a dev tree. */
async function renetBytes(arch: 'amd64' | 'arm64'): Promise<{ data: Buffer; version: string }> {
  if (isSEA()) {
    return { data: getEmbeddedRenetBinary('linux', arch), version: getEmbeddedMetadata().version };
  }
  const configured = (await configService.getLocalConfig()).renetPath;
  const beside =
    configured && isAbsolute(configured) ? join(dirname(configured), `renet-linux-${arch}`) : '';
  try {
    return { data: await readFile(beside), version: 'dev' };
  } catch {
    throw new ServerError(t('commands.server.bundle.errors.noRenetAsset', { arch }));
  }
}

async function renetAsset(
  arch: 'amd64' | 'arm64',
  dest?: string
): Promise<{ sha256: string; version: string }> {
  const { data, version } = await renetBytes(arch);
  if (dest) await writeFile(dest, data, { mode: 0o755 });
  return { sha256: computeSha256(data), version };
}

async function uploadFile(machine: string, local: string, remote: string): Promise<void> {
  const lease = await machineConnections.acquire(machine);
  try {
    await lease.sftp.writeFile(remote, await readFile(local));
  } finally {
    lease.release();
  }
}

export const offlineDeps: OfflineDeps = {
  localOut,
  sha256File,
  makeDir: async (path) => {
    await mkdir(path, { recursive: true });
  },
  renetAsset,
  uploadFile,
};
