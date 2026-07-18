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

/**
 * Resolve the peer machine referenced by `params`, if any.
 *
 * Returns undefined when the operation targets storage rather than a machine,
 * which is the common case.
 */
export async function resolveExtraMachines(
  params: Record<string, unknown>
): Promise<Record<string, ExtraMachine> | undefined> {
  const peer = peerMachineName(params);
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
 * what makes the last rule safe: it cannot swallow a storage name.
 */
function peerMachineName(params: Record<string, unknown>): string | undefined {
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
