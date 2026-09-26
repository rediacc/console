/**
 * Best-effort state records (the renet provision cache, licence-refresh timestamps, backup-run
 * notes) never fail the command they annotate. A remote config refuses every write while its
 * server is unreachable (operator ruling 2026-09-25: offline state writes on a remote config fail
 * closed), and such a refusal used to vanish into the writer's catch-all. This says it instead:
 * the fail-closed error names the config and the server, and is printed once per process.
 *
 * Any other failure keeps its writer's contract (a missing config, a local IO error), which is
 * silence.
 */

import { RemoteWriteFailedClosedError } from '../../adapters/remote-config-adapter.js';
import { outputService } from '../core/output.js';

const reported = new Set<string>();

/**
 * Warn when `error` is a remote config's fail-closed refusal. Returns true when it was one (and
 * so was reported), false for anything else, which the caller handles as before.
 */
export function reportStateWriteRefused(error: unknown): boolean {
  if (!(error instanceof RemoteWriteFailedClosedError)) return false;
  if (!reported.has(error.message)) {
    reported.add(error.message);
    outputService.warn(error.message);
  }
  return true;
}
