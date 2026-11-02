/**
 * The `os-ceph-host` driver of `npm run pins`: the exact ceph-common build each host OS pins
 * (agent/plans/PLAN-pins-command.md T8, survey item 5).
 *
 * ONLY THE LEAP PIN HAS A SOURCE. openSUSE Leap 16.0 installs from OBS, which keeps just its
 * latest build, so the truth is mechanical: `obs_mirror upstream` reads the signed repomd
 * (gpgv-verified against the key renet embeds) and answers the EVR OBS serves now. The other
 * three hosts (Ubuntu noble, Fedora 43, EL10) follow `host-version`, the Ceph image pin's
 * decision, and their entries carry `source: none` with a BLOCKER reason; this driver throws
 * that reason, so they read "not compared" and are never bumped from here.
 *
 * SAFETY IS `mirror-tag`, not a soak (the old build is already gone, so waiting changes
 * nothing). A newer EVR is taken only when BOTH hold, and the release's own verdict says
 * which does not:
 *   - its upstream version (epoch and release stripped) equals `host-version`, since a Ceph
 *     client and cluster that disagree on the patch level cannot read each other's keyring
 *     (.ceph-image-pin explains), so a move of the series is the operator's decision, recorded as a
 *     `host-version.opensuse-16.0` override with its `host-version-reason` line (hostVersionFor);
 *   - the obs-mirror tag for the EVR exists in ghcr.io/rediacc/ci-vm-bake
 *     (`obs_mirror mirror-tag`), because CI installs the pin from the captured tree and the
 *     Leap legs go red without one. An absent tag is "dispatch ci-obs-mirror while OBS still
 *     serves it", never a bump. A probe that fails for any other reason is not "absent":
 *     the pin reads "not compared".
 * The three sites (cephpkg.go hostPins, .ceph-image-pin host.opensuse-16.0, the install
 * profile test) move together through the shared leaf planner, which refuses the whole pin
 * when one of them does not match its registry `expect`.
 */
import type { Inspection, PinDriver, PinPlan } from '../driver.js';
import { leafCurrent, PlanRefused, planLeafSites } from '../driver.js';
import {
  type Deps,
  hostVersionFor,
  leafKey,
  realDeps,
  requireSource,
  type T8Mutant,
} from './shared.js';

const OBS = 'PYTHONPATH=.ci python3 -m rediacc_ci.infra.obs_mirror';

/** The upstream version of an EVR: the epoch and the release dropped (`2:19.2.3-1.el10s` -> `19.2.3`). */
export const upstreamVersion = (evr: string): string => evr.replace(/^\d+:/, '').split('-')[0];

export function osCephHostDriver(
  depsFor: (root: string) => Deps = realDeps,
  mutant?: T8Mutant
): PinDriver {
  return {
    name: 'os-ceph-host',
    async inspect(entry, ctx): Promise<Inspection> {
      requireSource(entry);
      if (entry.source.type !== 'obs-repomd')
        throw new Error(`the os-ceph-host driver has no reader for source ${entry.source.type}`);
      const deps = depsFor(ctx.root);
      const current = leafCurrent(entry, ctx);
      const up = deps.run(`${OBS} upstream`, ctx.root);
      const evr = /^obs_evr=(\S+)$/m.exec(up.stdout)?.[1];
      if (up.rc !== 0 || !evr)
        throw new Error(
          `obs_mirror upstream could not read the OBS origin: ${up.out.trim().slice(-300)}`
        );
      if (evr === current) return { current, releases: [] };

      const host = hostVersionFor((p) => ctx.read(p), 'opensuse-16.0');
      if (mutant !== 'os-ignore-series' && upstreamVersion(evr) !== host)
        return {
          current,
          releases: [
            {
              version: evr,
              publishedMs: null,
              verdict: {
                eligible: false,
                why: `OBS serves ceph-common ${upstreamVersion(evr)} while host-version is ${host}: moving the Ceph series is the operator's decision (.ceph-image-pin)`,
              },
            },
          ],
        };
      const tag = deps.run(`${OBS} mirror-tag --evr ${evr}`, ctx.root);
      const state = /^mirror_tag=(present|absent)$/m.exec(tag.stdout)?.[1];
      if (tag.rc !== 0 || !state)
        throw new Error(
          `obs_mirror mirror-tag could not probe the mirror for ${evr}: ${tag.out.trim().slice(-300)}`
        );
      return {
        current,
        releases: [
          {
            version: evr,
            publishedMs: null,
            verdict:
              state === 'present' || mutant === 'os-ignore-tag'
                ? {
                    eligible: true,
                    why: `OBS serves ${evr}, host-version ${host} unchanged, mirror tag present`,
                  }
                : {
                    eligible: false,
                    why: `no obs-mirror tag for ${evr}: dispatch ci-obs-mirror (evr=${evr}) while OBS still serves it, then bump`,
                  },
          },
        ],
      };
    },
    plan(entry, to, ctx): Promise<PinPlan> {
      if (!to.verdict?.eligible)
        return Promise.reject(
          new PlanRefused(
            `${entry.id}: ${to.verdict?.why ?? 'the release carries no safety verdict'}`
          )
        );
      try {
        const { writes, changes } = planLeafSites(entry, { version: to.version }, ctx);
        return Promise.resolve({
          entry,
          from: leafCurrent(entry, ctx),
          to,
          writes,
          steps: [],
          changes,
        });
      } catch (err) {
        return Promise.reject(err);
      }
    },
    holdKey: leafKey,
  };
}
