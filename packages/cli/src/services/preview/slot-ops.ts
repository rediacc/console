/**
 * The two remote operations the renet provisioner runs for a preview (PLAN-preview-signer.md D9): pinning and
 * recording the slot a first replacement is about to leave, and pointing `current` back at a pinned slot.
 * The provisioner owns the install paths and the host lock; they arrive here as arguments.
 */
import { TELEMETRY_DEFAULTS } from '@rediacc/shared/config';
import type { SFTPClient } from '../../remote/sftp/index.js';
import { shellQuote } from '../../utils/shell-quote.js';
import {
  buildPinCommand,
  buildSwitchBackBody,
  isPreviewVersion,
  parsePinOutput,
  parseSwitchBackOutput,
  type SwitchBackOutcome,
} from './slot.js';
import { recordPreviewTouch } from './state.js';

/**
 * Pin the slot of the renet the machine runs, then record its slot, version and hash under
 * `preview.touched`, both before anything is uploaded, so a failure leaves the machine as it was. A machine
 * already running a preview renet, and one the local binary already matches, record nothing: a server never
 * touched never enters the list.
 */
export async function pinAndRecordTouch(
  sftp: Pick<SFTPClient, 'exec'>,
  machine: string,
  replacement: {
    running: { hash: string | null; version: string | null };
    localHash: string;
    /** The binary whose slot is pinned: `current/renet`, or the install slot on a machine with no `current`. */
    binaryPath: string;
  }
): Promise<void> {
  const { running } = replacement;
  if (
    !running.hash ||
    running.hash === replacement.localHash ||
    isPreviewVersion(running.version)
  ) {
    return;
  }
  const slotDir = parsePinOutput(await sftp.exec(buildPinCommand(replacement.binaryPath, 'sudo')));
  await recordPreviewTouch(machine, {
    slot: slotDir,
    version: running.version ?? TELEMETRY_DEFAULTS.UNKNOWN,
    sha256: running.hash,
    touchedAt: new Date().toISOString(),
  });
}

/**
 * Repoint `current` to the pinned slot under the host install lock. `slot_missing` and `hash_mismatch` change
 * nothing: the caller then re-provisions with the CLI that embeds the pre-preview renet.
 */
export async function runSwitchBack(
  sftp: Pick<SFTPClient, 'exec'>,
  pinned: { slotDir: string; sha256: string },
  host: { currentDir: string; currentPath: string; lockPath: string; flockTimeoutExit: number }
): Promise<SwitchBackOutcome> {
  const body = buildSwitchBackBody({
    slotDir: pinned.slotDir,
    expectedHash: pinned.sha256,
    currentDir: host.currentDir,
    currentPath: host.currentPath,
    binLink: '/usr/bin/renet',
    sudo: 'sudo',
  });
  const output = await sftp.exec(
    `command -v flock >/dev/null 2>&1 || { echo FLOCK_MISSING >&2; exit 127; }; flock -w 120 -E ${host.flockTimeoutExit} ${shellQuote(host.lockPath)} sh -c ${shellQuote(body)}`
  );
  return parseSwitchBackOutput(output);
}
