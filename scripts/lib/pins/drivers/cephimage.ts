/**
 * The `ceph-image` driver of `npm run pins`: the dated quay tag of the Ceph container image
 * (private/renet/.ceph-image-pin `image=`, provisioner.go CephImagePin; PLAN-pins-command T8,
 * survey item 6).
 *
 * THE RULE of the pin file: take the DATED tag whose version equals `host-version` exactly
 * (`v19.2.3-20250717`), never a floating one (`v19`, `v19.2` and `v19.2.3` are rebuilt in
 * place), and never another patch level, because a cluster of one patch cannot be read by a
 * client of another (measured live 2026-08-20). So the candidates are the tags
 * `v<host-version>-<YYYYMMDD>` dated after the pin; a move of host-version is the
 * operator's decision and this driver cannot make it.
 *
 * SAFETY is the same-host-version rule above plus the shared release-age window on the tag's
 * push time: a rebuild published today waits for the next UTC day after the window like
 * every other pin. A bump rewrites `image=` and CephImagePin, leaves `host-version=` as it
 * is, and sets `review=` ninety days out (the pin file's cadence).
 */
import { isWithinFreshnessWindow } from '../../release-age.js';
import type { Inspection, PinDriver, PinPlan, Release } from '../driver.js';
import { leafCurrent, PlanRefused, planLeafSites } from '../driver.js';
import {
  type Deps,
  dateAfter,
  hostVersionOf,
  leafKey,
  realDeps,
  requireSource,
  type T8Mutant,
} from './shared.js';

const DATED = /^v(\d+\.\d+\.\d+)-(\d{8})$/;
const REVIEW_DAYS = 90;
const MAX_PAGES = 10;

interface QuayPage {
  tags?: Array<{ name?: unknown; start_ts?: unknown }>;
  has_additional?: unknown;
}

export function cephImageDriver(
  depsFor: (root: string) => Deps = realDeps,
  mutant?: T8Mutant
): PinDriver {
  return {
    name: 'ceph-image',
    async inspect(entry, ctx): Promise<Inspection> {
      requireSource(entry);
      const image = entry.source.image;
      if (entry.source.type !== 'quay-tags' || !image?.startsWith('quay.io/'))
        throw new Error('the ceph-image driver reads quay-tags sources of quay.io images');
      const deps = depsFor(ctx.root);
      const ref = leafCurrent(entry, ctx);
      const curTag = ref?.slice(ref.lastIndexOf(':') + 1) ?? '';
      const cur = DATED.exec(curTag);
      if (!cur)
        throw new Error(
          `the pinned tag ${curTag || '(none)'} is not a dated tag v<x.y.z>-<YYYYMMDD>`
        );
      const host = hostVersionOf((p) => ctx.read(p));
      if (cur[1] !== host)
        throw new Error(
          `the pinned image is Ceph ${cur[1]} but host-version is ${host}: the pin file disagrees with itself`
        );

      const repo = image.slice('quay.io/'.length);
      const found: Array<{ name: string; date: string; pushedMs: number | null }> = [];
      for (let page = 1; page <= MAX_PAGES; page++) {
        const url = `https://quay.io/api/v1/repository/${repo}/tag/?onlyActiveTags=true&limit=100&page=${page}&filter_tag_name=like:${encodeURIComponent(`v${host}-`)}`;
        const j = (await deps.json(url, image)) as QuayPage;
        if (!Array.isArray(j.tags)) throw new Error(`quay answered no tag list for ${repo}`);
        for (const t of j.tags) {
          const m = typeof t.name === 'string' ? DATED.exec(t.name) : null;
          if (!m || (m[1] !== host && mutant !== 'ceph-ignore-host')) continue;
          found.push({
            name: t.name as string,
            date: m[2],
            pushedMs: typeof t.start_ts === 'number' ? t.start_ts * 1000 : null,
          });
        }
        if (j.has_additional !== true) break;
      }
      const now = deps.nowMs();
      const win = deps.windowMs();
      const releases: Release[] = found
        .filter((t) => t.date > cur[2])
        .sort((a, b) => (a.date < b.date ? 1 : -1))
        .map((t) => {
          const fresh = t.pushedMs === null || isWithinFreshnessWindow(t.pushedMs, now, win);
          return {
            version: t.name,
            publishedMs: t.pushedMs,
            verdict: fresh
              ? {
                  eligible: false,
                  why:
                    t.pushedMs === null
                      ? 'the tag carries no push time, so its age is unknown'
                      : 'pushed inside the release-age window',
                }
              : { eligible: true, why: `dated tag of host-version ${host}, past the window` },
          };
        });
      return { current: curTag, releases };
    },
    plan(entry, to, ctx): Promise<PinPlan> {
      if (!to.verdict?.eligible)
        return Promise.reject(
          new PlanRefused(
            `${entry.id}: ${to.verdict?.why ?? 'the release carries no safety verdict'}`
          )
        );
      try {
        const image = entry.source.image as string;
        const deps = depsFor(ctx.root);
        const { writes, changes } = planLeafSites(
          entry,
          {
            image: `${image}:${to.version}`,
            'host-version': hostVersionOf((p) => ctx.read(p)),
            review: dateAfter(deps.nowMs(), REVIEW_DAYS),
          },
          ctx
        );
        const ref = leafCurrent(entry, ctx);
        return Promise.resolve({
          entry,
          from: ref?.slice(ref.lastIndexOf(':') + 1) ?? null,
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
