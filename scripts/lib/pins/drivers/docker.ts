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
 */
import type { Inspection, PinDriver, PinPlan, PlanStep, Release } from '../driver.js';
import { leafCurrent, PlanRefused, planLeafSites } from '../driver.js';
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
  results?: Array<{ name?: unknown; last_updated?: unknown }>;
  next?: unknown;
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
      const found = new Map<string, Release>();
      for (let page = 0; page < PAGES && url !== null; page++) {
        const j = (await deps.json(url, image)) as HubPage;
        if (!Array.isArray(j.results))
          throw new Error(`Docker Hub answered no tag list for ${repo}`);
        for (const r of j.results) {
          const name = typeof r.name === 'string' ? r.name : '';
          const m = SHAPE.exec(name);
          if (!m || m[2] !== cur[2] || m[1].split('.').length !== parts) continue;
          if (cmpVersion(m[1], cur[1]) <= 0) continue;
          const at = typeof r.last_updated === 'string' ? Date.parse(r.last_updated) : Number.NaN;
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
        .map(([, r]) => r)
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
          listed = ((JSON.parse(ctx.read(BASELINE) ?? '[]') as string[]) ?? []).includes(
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
