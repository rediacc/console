/**
 * The `docker` driver of `npm run pins`: container base-image tags, a SERIES MOVE taken only
 * on purpose (PLAN-pins-command T8, survey item 10).
 *
 * A base-image tag is a judgment call (the language runtime, the distro release, the CUDA
 * generation), so the driver reports and refuses by default: every candidate is labelled
 * `<image>:<tag>`, which the core can only read as a major move, and a major is taken solely
 * by `npm run pins -- bump <id> --major --reason "<why>"`. The candidates are the tags of the
 * same SHAPE as the pin (the same suffix, the same number of version components) with a
 * greater version, newest first, from Docker Hub's tag list with each tag's `last_updated`.
 * A tag of another shape (an `-alpine` sibling, `latest`) is never a candidate.
 *
 * THE BASELINE DRAIN. scripts/data/docker-image-freshness-baseline.json is the shrink-only
 * list of known-stale pins; one that is bumped must leave it or check:ci-docker-image-
 * freshness is red ("no longer stale"). When the old `image:tag` is listed there, the plan
 * adds the drain step (`check-docker-image-freshness.ts --write-baseline`) and declares the
 * baseline as its one write; an unlisted pin plans no step.
 *
 * The `docker` family entry (the FROM scan itself) answers "nothing to bump": its members are
 * the leaves, and a floating tag frozen in the baseline moves through its own leaf.
 *
 * THE AGE OF A MAJOR LINE. check:ci-pin-freshness turns a newer major red once the line's
 * first release is MAJOR_GRACE_DAYS old (scripts/lib/pins/status.ts), and Docker Hub carries
 * no release date: `last_updated` is a tag's LAST push, and official images re-push every
 * supported tag on a schedule (`ubuntu:26.04` measured 2026-10-14: last pushed 2026-10-04, half
 * a year after 26.04 shipped). Dated by its own stamp, a floating tag never ages. So each
 * candidate carries `lineFirstMs`, an instant the line had already begun by: Docker Hub's tag
 * `id` grows with creation, and a tag's last push is never earlier than its creation, so the
 * earliest `last_updated` among ALL the listed tags created no earlier than the line's oldest
 * listed tag (the smallest `id` on the line: any component count, the pin's suffix) bounds the
 * line's start from above; a dated tag that is never re-pushed (`resolute-20260106.1`) is the
 * evidence a re-pushed `26.04` cannot give. The age it gives is never more than the truth; a line whose oldest
 * tag fell past the listed pages only reads younger, and a line with no dated tag reads null
 * (undatable, which the gate fails closed on).
 */
import type { Inspection, PinDriver, PinPlan, PlanStep } from '../driver.js';
import { leafCurrent, PlanRefused, planLeafSites } from '../driver.js';
import type { LineDatedRelease } from '../status.js';
import {
  cmpVersion,
  type Deps,
  leafKey,
  realDeps,
  requireSource,
  type T8Mutant,
} from './shared.js';

const BASELINE = { repo: '.', file: 'scripts/data/docker-image-freshness-baseline.json' };
const SHAPE = /^(\d+(?:\.\d+){0,2})(.*)$/;
const PAGES = 5;

interface HubPage {
  results?: Array<{ name?: unknown; last_updated?: unknown; id?: unknown }>;
  next?: unknown;
}

/** One listed tag; `major` only for a tag of the pin's suffix (any component count), else null. */
export interface Listed {
  major: number | null;
  id: number | null;
  at: number | null;
}

/**
 * The instant a major line had begun by (see THE AGE OF A MAJOR LINE above): the earliest
 * push among the line's own tags and every tag created no earlier than the line's oldest
 * listed tag (by `id`); with no `id` on the line, the line's own tags alone. Null when nothing
 * in that pool is dated. Pure.
 */
export function lineFirstMs(major: number, listed: Listed[]): number | null {
  const line = listed.filter((t) => t.major === major);
  const ids = line.flatMap((t) => (t.id === null ? [] : [t.id]));
  const floor = ids.length > 0 ? Math.min(...ids) : null;
  const pool = listed.filter(
    (t) => t.major === major || (floor !== null && t.id !== null && t.id >= floor)
  );
  const ats = pool.flatMap((t) => (t.at === null ? [] : [t.at]));
  return ats.length > 0 ? Math.min(...ats) : null;
}

export function dockerDriver(
  depsFor: (root: string) => Deps = realDeps,
  mutant?: T8Mutant
): PinDriver {
  return {
    name: 'docker',
    async inspect(entry, ctx): Promise<Inspection> {
      if (entry.kind === 'family') return { current: null, releases: [] };
      requireSource(entry);
      const image = entry.source.image;
      if (entry.source.type !== 'dockerhub' || !image)
        throw new Error('the docker driver reads dockerhub sources');
      const value = leafCurrent(entry, ctx);
      if (value === null) throw new Error(`${entry.id}: no site holds the tag`);
      const tag = value.includes(':') ? value.slice(value.indexOf(':') + 1) : value;
      const cur = SHAPE.exec(tag);
      if (!cur)
        throw new Error(
          `the pinned tag ${tag} has no leading version, so a newer one cannot be named`
        );
      const parts = cur[1].split('.').length;
      const deps = depsFor(ctx.root);
      const repo = image.includes('/') ? image : `library/${image}`;
      let url: string | null =
        `https://hub.docker.com/v2/repositories/${repo}/tags?page_size=100&name=${encodeURIComponent(cur[2].replace(/^-/, ''))}`;
      const found = new Map<string, LineDatedRelease>();
      const listed: Listed[] = [];
      for (let page = 0; page < PAGES && url !== null; page++) {
        const j = (await deps.json(url, image)) as HubPage;
        if (!Array.isArray(j.results))
          throw new Error(`Docker Hub answered no tag list for ${repo}`);
        for (const r of j.results) {
          const name = typeof r.name === 'string' ? r.name : '';
          const m = SHAPE.exec(name);
          const at = typeof r.last_updated === 'string' ? Date.parse(r.last_updated) : Number.NaN;
          listed.push({
            major: m && m[2] === cur[2] ? Number(m[1].split('.')[0]) : null,
            id: typeof r.id === 'number' && Number.isFinite(r.id) ? r.id : null,
            at: Number.isNaN(at) ? null : at,
          });
          if (!m || m[2] !== cur[2] || m[1].split('.').length !== parts) continue;
          if (cmpVersion(m[1], cur[1]) <= 0) continue;
          found.set(name, {
            version: `${image}:${name}`,
            publishedMs: Number.isNaN(at) ? null : at,
            verdict: {
              eligible: true,
              why: `a series move to ${image}:${name}: a judgment call, taken only with --major --reason`,
            },
          });
        }
        url = typeof j.next === 'string' ? j.next : null;
      }
      const releases = [...found.entries()]
        .sort(([a], [b]) => cmpVersion(SHAPE.exec(b)?.[1] ?? '0', SHAPE.exec(a)?.[1] ?? '0'))
        .map(([name, r]) => ({
          ...r,
          lineFirstMs: lineFirstMs(Number((SHAPE.exec(name)?.[1] ?? '0').split('.')[0]), listed),
        }))
        .slice(0, 10);
      return { current: `${image}:${tag}`, releases };
    },
    plan(entry, to, ctx): Promise<PinPlan> {
      const image = entry.source.image as string;
      const tag = to.version.slice(image.length + 1);
      const old = leafCurrent(entry, ctx) as string;
      const oldTag = old.includes(':') ? old.slice(old.indexOf(':') + 1) : old;
      try {
        const { writes, changes } = planLeafSites(
          entry,
          { version: old.includes(':') ? `${image}:${tag}` : tag },
          ctx
        );
        const steps: PlanStep[] = [];
        let listed = false;
        try {
          listed = ((JSON.parse(ctx.read(BASELINE) ?? '[]') as string[] | null) ?? []).includes(
            `${image}:${oldTag}`
          );
        } catch {
          return Promise.reject(new PlanRefused(`${BASELINE.file} is not a JSON list`));
        }
        if (listed && mutant !== 'docker-no-drain')
          steps.push({
            label: 'drain the docker freshness baseline',
            run: 'npx tsx scripts/gates/check-docker-image-freshness.ts --write-baseline',
            cwd: '.',
            writes: [BASELINE],
          });
        return Promise.resolve({ entry, from: `${image}:${oldTag}`, to, writes, steps, changes });
      } catch (err) {
        return Promise.reject(err);
      }
    },
    holdKey: leafKey,
  };
}
