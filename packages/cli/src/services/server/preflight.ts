/**
 * Before anything is installed: the box answers SSH, `sudo -n` works, the architecture is one the
 * image ships for, ports 80 and 443 are free (or held by renet's own proxy), the datastore has
 * room, and the clocks agree.
 */

import { t } from '../../i18n/index.js';
import { RENET_PATH, ServerError } from './box.js';
import { PREFLIGHT, parseEnvLines, shCommand } from './box-scripts.js';
import type { ServerDeps } from './types.js';

export const SUPPORTED_ARCH = ['x86_64', 'amd64', 'aarch64', 'arm64'] as const;
/** Largest clock difference tolerated, in seconds: certificates, licences and 2FA codes all carry times. */
export const MAX_CLOCK_SKEW_S = 120;
/** Room kept beside the repo for images and the stack's own data, in GiB. */
export const DISK_HEADROOM_GIB = 2;
/** Port holders that are renet's own proxy, which routes the new repo instead of colliding with it. */
const PROXY_HOLDERS = ['traefik', 'docker-proxy'];

export interface PreflightFacts {
  sudo: boolean;
  arch: string;
  epoch: number;
  renet: boolean;
  freeKb: number;
  ports: Record<'80' | '443', string>;
}

export function parsePreflight(stdout: string): PreflightFacts {
  const v = parseEnvLines(stdout);
  return {
    sudo: v.sudo === '1',
    arch: v.arch ?? '',
    epoch: Number.parseInt(v.epoch ?? '0', 10),
    renet: v.renet === '1',
    freeKb: Number.parseInt(v.free_kb ?? '0', 10),
    ports: { '80': (v.port80 ?? '').trim(), '443': (v.port443 ?? '').trim() },
  };
}

/** `10G`, `512M`, `1T` (or a bare number of GiB) in GiB; 0 when unreadable. */
export function sizeGib(size: string): number {
  const match = /^(\d+(?:\.\d+)?)\s*([KMGT]?)i?B?$/i.exec(size.trim());
  if (!match) return 0;
  const n = Number.parseFloat(match[1]);
  const unit = match[2].toUpperCase();
  const scale: Record<string, number> = { K: 1 / 1024 ** 2, M: 1 / 1024, G: 1, T: 1024, '': 1 };
  return n * (scale[unit] ?? 1);
}

/** The process names an `ss -p` line names. */
function holders(line: string): string[] {
  return [...line.matchAll(/\("([^"]+)"/g)].map((m) => m[1]);
}

/** Ports 80 and 443 must be free, or held only by renet's own proxy. */
function portProblems(facts: PreflightFacts): string[] {
  const problems: string[] = [];
  for (const port of ['80', '443'] as const) {
    const line = facts.ports[port];
    if (!line) continue;
    const names = holders(line);
    const proxy = facts.renet && names.length > 0 && names.every((n) => PROXY_HOLDERS.includes(n));
    if (!proxy) {
      problems.push(
        t('commands.server.preflight.portBusy', { port, holder: names.join(', ') || line })
      );
    }
  }
  return problems;
}

/** Every refusal the facts carry, as messages; empty when the box is ready. */
export function preflightProblems(
  facts: PreflightFacts,
  opts: { machine: string; size: string; now: number }
): string[] {
  const problems: string[] = [];
  if (!facts.sudo) problems.push(t('commands.server.preflight.noSudo', { machine: opts.machine }));
  if (!SUPPORTED_ARCH.includes(facts.arch as (typeof SUPPORTED_ARCH)[number])) {
    problems.push(t('commands.server.preflight.arch', { arch: facts.arch || '?' }));
  }
  problems.push(...portProblems(facts));
  const needGib = sizeGib(opts.size) + DISK_HEADROOM_GIB;
  const freeGib = facts.freeKb / 1024 ** 2;
  if (freeGib < needGib) {
    problems.push(
      t('commands.server.preflight.disk', { free: freeGib.toFixed(1), need: needGib.toFixed(1) })
    );
  }
  const skew = Math.abs(facts.epoch - Math.floor(opts.now / 1000));
  if (!facts.epoch || skew > MAX_CLOCK_SKEW_S) {
    problems.push(t('commands.server.preflight.clock', { skew, max: MAX_CLOCK_SKEW_S }));
  }
  return problems;
}

export async function runPreflight(
  deps: ServerDeps,
  opts: { machine: string; datastore: string; size: string }
): Promise<PreflightFacts> {
  const result = await deps.ssh(
    opts.machine,
    shCommand(PREFLIGHT, [opts.datastore, RENET_PATH], false)
  );
  if (result.code !== 0) {
    throw new ServerError(t('commands.server.preflight.noAnswer', { machine: opts.machine }));
  }
  const facts = parsePreflight(result.stdout);
  const problems = preflightProblems(facts, { ...opts, now: deps.now() });
  if (problems.length > 0) {
    throw new ServerError(
      [t('commands.server.preflight.refused', { machine: opts.machine }), ...problems].join('\n  ')
    );
  }
  return facts;
}
