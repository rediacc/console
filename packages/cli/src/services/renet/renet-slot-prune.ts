import { shellQuote } from '../../utils/shell-quote.js';

/**
 * The slot-pruning step of the locked install, a POSIX sh fragment run under the install flock.
 * Keeps the slot `current` resolves to plus the newest other slots (newest by the slot binary's mtime) up to `keep` in total, and removes the rest. A slot a systemd unit file or a live process names is kept regardless, so a daemon still running an older binary never loses it. Only directories holding a regular `renet` file are slots; the `current` directory and anything else under the root is left alone. The step never fails the install.
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
    // Unit files and the executables of live processes; a slot named in either stays.
    `refs=$(cat ${unitDir}/*.service 2>/dev/null || true; ${sudo}sh -c 'for p in /proc/[0-9]*/exe; do readlink "$p" 2>/dev/null || true; done' 2>/dev/null || true)`,
    'kept=0',
    `if [ -f "$curdir/renet" ]; then kept=1; fi`,
    // ls -t lists newest first; current/renet is a symlink and its directory is skipped by name.
    `for bin in $(ls -1t ${root}/*/renet 2>/dev/null); do dir=$(dirname "$bin"); [ "$(basename "$dir")" = current ] && continue; [ -f "$bin" ] && [ ! -L "$bin" ] || continue; [ "$dir" = "$curdir" ] && continue; if [ "$kept" -lt ${keep} ] || printf '%s' "$refs" | grep -qF "$dir/"; then kept=$((kept+1)); else ${sudo}rm -rf "$dir" || true; fi; done`,
  ].join('; ');
}
