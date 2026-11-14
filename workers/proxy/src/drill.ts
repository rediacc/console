/**
 * The bench-only reachability drill seam (agent/plans/PLAN-org-executor-connect-timeout-relocate.md box E15, operator ruling 2026-11-06T13:44Z).
 *
 * The E9 drill makes an executor report a machine it cannot reach, and the reachability gate (src/reachability.ts) counts that report only when the Worker itself reads an SSH banner at the reported address. A blackholed drill address (192.0.2.10, TEST-NET-1) never greets anyone, so on bench `EGRESS_DRILL_PROBE = "<from>=<to>"` sends the Worker's probe of `from` to `to`, a machine that does greet (hostinger's SSH port). Only the probe moves: the executor's report, its count and the relocation path stay the real ones.
 *
 * Three locks keep it on bench. `ENVIRONMENT` must be `bench`; `.ci/rediacc_ci/deploy/proxy_configs.py` refuses the var in every other target's config; and both sides must pass `probeTarget`, so the redirect can never aim the probe at a private, loopback or CGNAT address, or at port 25.
 *
 * A malformed var leaves the reported target as it is rather than throwing: the seam only ever widens what the Worker probes on bench, so a typo must fall back to the real gate, never break report handling or skip the probe.
 */

import { type ProbeTarget, probeTarget } from './reachability';

/** The env slice the drill reads. */
export interface DrillEnv {
  ENVIRONMENT?: string;
  EGRESS_DRILL_PROBE?: string;
}

/** `host:port` with the host bare or an IPv6 literal in brackets, and a decimal port. */
const SIDE_RE = /^(\[[0-9a-fA-F:.]+\]|[^\s:[\]=]+):(\d{1,5})$/;

/** One side of the var as an admitted probe target, else undefined. */
function side(text: string): ProbeTarget | undefined {
  const match = SIDE_RE.exec(text);
  if (!match) return undefined;
  const admitted = probeTarget({ host: match[1], port: Number(match[2]) });
  return 'refused' in admitted ? undefined : admitted;
}

/** The `{ from, to }` pair of a strict `<host:port>=<host:port>` value, else undefined. */
function drillPair(raw: string | undefined): { from: ProbeTarget; to: ProbeTarget } | undefined {
  const parts = (raw ?? '').split('=');
  if (parts.length !== 2) return undefined;
  const from = side(parts[0]);
  const to = side(parts[1]);
  return from && to ? { from, to } : undefined;
}

/** The address the reachability gate probes for `reported`: `reported` itself, except on bench when it is the drill's `from`. */
export function drillProbeTarget(
  env: DrillEnv,
  reported: ProbeTarget | undefined,
  placement: number
): ProbeTarget | undefined {
  if (env.ENVIRONMENT !== 'bench' || reported === undefined) return reported;
  const pair = drillPair(env.EGRESS_DRILL_PROBE);
  if (!pair || pair.from.host !== reported.host || pair.from.port !== reported.port) {
    return reported;
  }
  console.warn(`proxy: org executor reachability drill redirect at p${placement}`);
  return pair.to;
}
