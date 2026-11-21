/**
 * The box side of every `rdc server` verb: where the repo lives on the machine, and the scripts run
 * there through the SSH channel.
 */

import { NETWORK_DEFAULTS } from '@rediacc/shared/config';
import { WK_RUNTIME_DIR } from '@rediacc/shared/config/well-known.generated';
import { t } from '../../i18n/index.js';
import { recordedDatastoreMount } from '../../utils/repo-executor.js';
import { configService } from '../config/config-resources.js';
import { REMOTE_RENET_PATH } from '../renet/renet-provisioner.js';
import {
  BUNDLE_KEYS,
  envStdin,
  KEYGEN,
  PUBLIC_KEYS,
  parseEnvLines,
  readKeysScript,
  SET_ENV,
  shCommand,
} from './box-scripts.js';
import type { ProcResult, ServerDeps } from './types.js';

export class ServerError extends Error {}

export const RENET_PATH = REMOTE_RENET_PATH;

/** Where the repo is mounted on its machine, and its Docker daemon's socket. */
export interface RepoOnBox {
  machine: string;
  repo: string;
  dir: string;
  dockerSocket?: string;
}

export async function locateRepo(repo: string, machine: string): Promise<RepoOnBox> {
  const config = await configService.getRepository(repo);
  if (!config?.repositoryGuid) {
    throw new ServerError(t('commands.server.errors.repoUnknown', { repo }));
  }
  const machineConfig = await configService.getLocalMachine(machine);
  const datastore =
    (await recordedDatastoreMount(repo)) ??
    machineConfig.datastore ??
    NETWORK_DEFAULTS.DATASTORE_PATH;
  return {
    machine,
    repo,
    dir: `${datastore}/mounts/${config.repositoryGuid}`,
    ...(config.networkId === undefined
      ? {}
      : { dockerSocket: `${WK_RUNTIME_DIR}/docker-${config.networkId}.sock` }),
  };
}

export async function runOnBox(
  deps: ServerDeps,
  where: RepoOnBox,
  script: string,
  stdin?: string
): Promise<ProcResult> {
  const result = await deps.ssh(where.machine, shCommand(script, [where.dir]), stdin);
  if (result.code !== 0) {
    throw new ServerError(
      t('commands.server.errors.boxScriptFailed', {
        machine: where.machine,
        code: result.code,
        detail: result.stderr.trim().split('\n').at(-1) ?? '',
      })
    );
  }
  return result;
}

/** Generate the stack's secrets on the box (a rerun keeps them) and return the Ed25519 public key. */
export async function generateKeys(deps: ServerDeps, where: RepoOnBox): Promise<string> {
  const result = await runOnBox(deps, where, KEYGEN);
  const key = parseEnvLines(result.stdout).ACCOUNT_ED25519_PUBLIC_KEY;
  if (!key) throw new ServerError(t('commands.server.errors.keygenNoKey'));
  return key;
}

/** Set these keys in the box's `secrets.env`; the values travel on stdin. */
export async function setBoxEnv(
  deps: ServerDeps,
  where: RepoOnBox,
  values: Record<string, string>
): Promise<void> {
  await runOnBox(deps, where, SET_ENV, envStdin(values));
}

export interface PublicFacts {
  values: Partial<Record<string, string>>;
  /** The deployed template's `VERSION`; 0 when the file is absent. */
  templateVersion: number;
}

export async function readPublicFacts(deps: ServerDeps, where: RepoOnBox): Promise<PublicFacts> {
  const result = await runOnBox(deps, where, readKeysScript(PUBLIC_KEYS));
  const values = parseEnvLines(result.stdout);
  const version = Number.parseInt(values.VERSION ?? '', 10);
  delete values.VERSION;
  return { values, templateVersion: Number.isFinite(version) ? version : 0 };
}

/** The recovery bundle as `KEY=value` lines, read from the box on purpose (`backup`, the one-time print). */
export async function readBundle(
  deps: ServerDeps,
  where: RepoOnBox,
  domain: string
): Promise<string> {
  const result = await runOnBox(deps, where, readKeysScript(BUNDLE_KEYS));
  const values = parseEnvLines(result.stdout);
  const missing = BUNDLE_KEYS.filter((k) => !values[k]);
  if (missing.length > 0) {
    throw new ServerError(
      t('commands.server.errors.bundleIncomplete', { keys: missing.join(', ') })
    );
  }
  const lines = [
    `# ${t('commands.server.bundle.header', { domain })}`,
    ...BUNDLE_KEYS.map((k) => `${k}=${values[k]}`),
  ];
  return `${lines.join('\n')}\n`;
}

/** A child `rdc` that must succeed; its failure names the verb and the exit code. */
export async function rdcMust(deps: ServerDeps, argv: string[]): Promise<string> {
  const result = await deps.rdc(argv);
  if (result.code !== 0) {
    throw new ServerError(
      t('commands.server.errors.rdcFailed', {
        command: `rdc ${argv.slice(0, 4).join(' ')}`,
        code: result.code,
      })
    );
  }
  return result.stdout;
}
