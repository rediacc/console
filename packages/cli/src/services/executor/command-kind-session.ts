/**
 * The session of a command-kind job (`ExecuteOptions.commandKind`, PLAN-detached-jobs section 14): the renet binary is
 * brought to the machine, then one `job start --command` runs. A command kind carries no vault, so none of the
 * function-session work applies: no machine-setup verify (`setup` runs on a machine that has none yet), no license
 * pre-flight, no runtime converge pass.
 */

import type { SFTPClient } from '../../remote/sftp/index.js';
import { acquireRemoteRenet, type RenetAccess } from '../renet/renet-execution.js';
import { runJobExecution } from './detached-execution.js';
import type { ExecuteOptions, ExecuteResult } from './types.js';

/**
 * Which renet each kind needs. The kinds that change the machine provision the binary (a stale one would refuse the
 * allow-list entry); the reads run whatever renet is there.
 */
const COMMAND_KIND_ACCESS: Readonly<Record<string, RenetAccess>> = {
  setup: 'provision',
  'backup-unit': 'provision',
  'daemons-restart': 'provision',
  'list-all': 'read-only',
  'backup-cancel': 'read-only',
  'backup-status': 'read-only',
};

/** The access of a kind; an unknown kind reads, and renet refuses it against its own allow-list. */
export function commandKindAccess(name: string): RenetAccess {
  return COMMAND_KIND_ACCESS[name] ?? 'read-only';
}

type Machine = Parameters<typeof acquireRemoteRenet>[2];

export async function runCommandKindSession(
  sftp: SFTPClient,
  config: { renetPath: string },
  machine: Machine,
  sshPrivateKey: string,
  options: ExecuteOptions,
  startTime: number
): Promise<ExecuteResult> {
  const kind = options.commandKind?.name ?? options.functionName;
  const { remotePath } = await acquireRemoteRenet(
    commandKindAccess(kind),
    config,
    machine,
    sshPrivateKey,
    {
      debug: options.debug,
      skipRouterRestart: options.skipRouterRestart,
      machineName: options.machineName,
    },
    sftp
  );
  // No vault: the kind's argv comes from `--args`, and renet reads nothing from stdin but the secret prefix.
  const result = await runJobExecution(remotePath, '', options, machine, sshPrivateKey);
  return { ...result, durationMs: Date.now() - startTime };
}
