import { shellQuote } from '../../utils/shell-quote.js';
import { PREVIEW_PIN_MARKER } from '../preview/slot.js';

/**
 * The slot-pruning step of the locked install, a POSIX sh fragment run under the install flock.
 * Keeps the slot `current` resolves to plus the newest other slots (newest by the slot binary's mtime) up to `keep` in total, and removes the rest. A slot a systemd unit file or a live process names is kept regardless, so a daemon still running an older binary never loses it. A slot holding the preview pin marker (`rdc preview use` writes it into the renet it replaces, PLAN-preview-signer.md D9) is kept and does not count against `keep`. Only directories holding a regular `renet` file are slots; the `current` directory and anything else under the root is left alone. The step never fails the install.
 * `sudo` is the privilege prefix ('sudo' on a machine, '' in a test that owns its directory tree).
 */
export function buildSlotPruneStep(opts: {
  root: string;
  currentPath: string;
  installPath: string;
  unitDir: string;
  keep: number;
  sudo: string;
}): string {
  const root = shellQuote(opts.root);
  const currentPath = shellQuote(opts.currentPath);
  const installPath = shellQuote(opts.installPath);
  const unitDir = shellQuote(opts.unitDir);
  const sudo = opts.sudo ? `${opts.sudo} ` : '';
  const keep = Math.max(1, Math.trunc(opts.keep));
  return [
    `curdir=$(dirname "$(readlink ${currentPath} 2>/dev/null || echo ${installPath})")`,
    // Unit files and the executables of live processes; a slot named in either stays. One `ls -l` prints every `exe -> <binary>` line: a readlink per process forked once per pid, 1.8 s for 670 processes on an idle host and past the 30 s test budget under load.
    `refs=$(cat ${unitDir}/*.service 2>/dev/null || true; ${sudo}sh -c 'ls -l /proc/[0-9]*/exe 2>/dev/null || true' 2>/dev/null || true)`,
    'kept=0',
    `if [ -f "$curdir/renet" ]; then kept=1; fi`,
    // ls -t lists newest first; current/renet is a symlink and its directory is skipped by name.
    `for bin in $(ls -1t ${root}/*/renet 2>/dev/null); do dir=$(dirname "$bin"); [ "$(basename "$dir")" = current ] && continue; [ -f "$bin" ] && [ ! -L "$bin" ] || continue; [ "$dir" = "$curdir" ] && continue; [ -e "$dir/${PREVIEW_PIN_MARKER}" ] && continue; if [ "$kept" -lt ${keep} ] || printf '%s' "$refs" | grep -qF "$dir/"; then kept=$((kept+1)); else ${sudo}rm -rf "$dir" || true; fi; done`,
  ].join('; ');
}
