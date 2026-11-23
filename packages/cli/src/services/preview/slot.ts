/**
 * The remote half of switching a server's renet for a preview and back (PLAN-preview-signer.md D9):
 * the pin marker that keeps the pre-preview slot through later installs, and the locked switch-back
 * that repoints `current` to it. Both are POSIX sh fragments built here and run by the renet provisioner
 * under its install flock, so a test drives them in a real shell against a temp tree.
 */
import { shellQuote } from '../../utils/shell-quote.js';

/** The file written into a slot to keep it; the slot prune of the CLI and of renet (`daemons upgrade`) both skip a slot holding it. */
export const PREVIEW_PIN_MARKER = '.preview-pin';

/** A preview build's version carries `-preview.<sha7>` (D7); a machine running one may be replaced by any release. */
export function isPreviewVersion(version: string | null | undefined): boolean {
  return typeof version === 'string' && /-preview\./.test(version);
}

const PIN_TAG = 'PREVIEW_PIN';

/**
 * Pin the slot the renet at `binaryPath` (a symlink such as `current/renet`, or the slot's own binary) resolves
 * to, and print `PREVIEW_PIN <slot dir>`. A binary that does not resolve prints nothing and fails the pin.
 */
export function buildPinCommand(binaryPath: string, sudo: string): string {
  const prefix = sudo ? `${sudo} ` : '';
  const target = shellQuote(binaryPath);
  return (
    `slot=$(dirname "$(readlink -f ${target})") && [ -f "$slot/renet" ] ` +
    `&& ${prefix}touch "$slot/${PREVIEW_PIN_MARKER}" && echo "${PIN_TAG} $slot"`
  );
}

/** The pinned slot directory out of {@link buildPinCommand}'s output, or a refusal: a server whose way back cannot be pinned is not replaced. */
export function parsePinOutput(output: string): string {
  const line = output.split('\n').find((l) => l.startsWith(`${PIN_TAG} `));
  const slot = line?.slice(PIN_TAG.length + 1).trim();
  if (!slot) {
    throw new Error('the running renet slot could not be pinned, so the machine is left unchanged');
  }
  return slot;
}

/** What the switch-back body found. */
export type SwitchBackOutcome = 'switched' | 'slot_missing' | 'hash_mismatch';

/**
 * The switch-back, a POSIX sh body for the install flock: repoint `current` to the pinned slot when its
 * binary still hashes to `expectedHash`, link `/usr/bin/renet` to `current`, and drop the pin. A missing
 * or changed slot changes nothing and prints why, so the caller re-provisions instead.
 */
export function buildSwitchBackBody(opts: {
  slotDir: string;
  expectedHash: string;
  currentDir: string;
  currentPath: string;
  binLink: string;
  sudo: string;
}): string {
  const prefix = opts.sudo ? `${opts.sudo} ` : '';
  const slotBin = shellQuote(`${opts.slotDir}/renet`);
  const pin = shellQuote(`${opts.slotDir}/${PREVIEW_PIN_MARKER}`);
  const currentDir = shellQuote(opts.currentDir);
  const currentPath = shellQuote(opts.currentPath);
  const tmp = shellQuote(`${opts.currentPath}.tmp`);
  const binLink = shellQuote(opts.binLink);
  return [
    'set -eu',
    `if [ ! -f ${slotBin} ]; then echo SLOT_MISSING; exit 0; fi`,
    `h=$( (${slotBin} hash 2>/dev/null || sha256sum ${slotBin} | cut -d' ' -f1) 2>/dev/null || true)`,
    `if [ "$h" != ${shellQuote(opts.expectedHash)} ]; then echo HASH_MISMATCH; exit 0; fi`,
    `${prefix}mkdir -p ${currentDir}`,
    `${prefix}ln -sfn ${slotBin} ${tmp}`,
    `${prefix}mv -Tf ${tmp} ${currentPath}`,
    `${prefix}ln -sf ${currentPath} ${binLink}`,
    `${prefix}rm -f ${pin}`,
    'echo SWITCHED',
  ].join('; ');
}

/** The outcome in a switch-back's output; an output naming none of them is an error, never a success. */
export function parseSwitchBackOutput(output: string): SwitchBackOutcome {
  const tokens = new Set(output.trim().split(/\s+/));
  if (tokens.has('SWITCHED')) return 'switched';
  if (tokens.has('SLOT_MISSING')) return 'slot_missing';
  if (tokens.has('HASH_MISMATCH')) return 'hash_mismatch';
  throw new Error(`unexpected switch-back result: ${output.trim() || '(empty output)'}`);
}
