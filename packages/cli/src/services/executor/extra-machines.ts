/**
 * Peer-machine resolution for multi-machine operations.
 *
 * A backup push to another machine, or a pull from one, needs that peer's
 * connection details in the vault. Those details are CONFIG, so they are
 * resolved here, executor-side, from the params the caller already sent
 * (`to` / `from` plus their `destinationType` / `sourceType`).
 *
 * This used to run in the command layer, which meant the client resolved
 * machine IPs from its own config before calling the executor. That cannot work
 * through the proxy: a proxy client holds no config at all. Deriving here keeps
 * one code path for both executors and keeps config out of the wire.
 */

import { configService } from '../config/config-resources.js';
import type { ExtraMachine } from './types.js';

/** Functions whose `to` param is a directory on the machine, never a peer machine. */
const PATH_DESTINATION_FUNCTIONS: ReadonlySet<string> = new Set(['backup_restore_path']);

/**
 * Resolve the peer machine referenced by `params`, if any.
 *
 * Returns undefined when the operation targets storage rather than a machine,
 * which is the common case.
 */
export async function resolveExtraMachines(
  params: Record<string, unknown>,
  functionName?: string
): Promise<Record<string, ExtraMachine> | undefined> {
  const peer = peerMachineName(params, functionName);
  if (!peer) return undefined;

  const machine = await configService.getLocalMachine(peer);
  return {
    [peer]: {
      ip: machine.ip,
      port: machine.port,
      user: machine.user,
      datastore: machine.datastore,
    },
  };
}

/**
 * The machine-typed peer named by these params, if the operation has one.
 *
 * Three shapes exist, and the discriminator is what tells them apart:
 *   - backup push:  destinationType='machine' + to=<machine>   (or 'storage', no peer)
 *   - backup pull:  sourceType='machine' + from=<machine>      (or 'storage', no peer)
 *   - datastore:    to=<machine>, with NO type discriminator
 *
 * The backup family always sets its discriminator (repo-backup.ts sets
 * destinationType/sourceType on every path), so an undiscriminated `to` can
 * only be the datastore family, where `--to` always names a machine. That is
 * what makes the last rule safe: it cannot swallow a storage name. The one
 * exception is PATH_DESTINATION_FUNCTIONS, whose `to` is a directory and which
 * take no peer at all.
 */
function peerMachineName(
  params: Record<string, unknown>,
  functionName?: string
): string | undefined {
  // `to` names a DIRECTORY here, and with no discriminator it would be read as a datastore peer: `Machine "/tmp/x" not found`.
  if (functionName && PATH_DESTINATION_FUNCTIONS.has(functionName)) return undefined;
  if (params.destinationType === 'machine' && typeof params.to === 'string') {
    return params.to;
  }
  if (params.sourceType === 'machine' && typeof params.from === 'string') {
    return params.from;
  }
  if (params.destinationType === undefined && typeof params.to === 'string') {
    return params.to;
  }
  return undefined;
}
