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
 * THE DIGEST MOVES WITH THE TAG. A line that pins `<image>:<tag>@sha256:<digest>` carries two
 * values, and a bump that rewrote only the tag left `node:26.13.0-slim` pulling the 26.12.0
 * index (#d4b2a051). So such a leaf has a second site on the same line with role `digest`, and
 * the plan resolves the target tag's index digest from Docker Hub (scripts/lib/docker-hub.ts)
 * and writes both in one pass. No digest for the target is a refusal, never a write of the tag
 * alone; and a version site whose line carries `@sha256:` in an entry with no `digest` site is
 * refused too, so a registry gap cannot bring the same drift back.
 *
 * THE RE-DIGEST. Docker Official Images re-push a tag when its parent image is rebuilt, so the
 * digest beside an unchanged tag goes stale with no newer tag to move to (node 22.12.0-slim was
 * released 2024-12-03 and last pushed 2024-12-25). When a leaf has a `digest` site and Docker
 * Hub serves another index digest for the PINNED tag, inspect offers that tag again, labelled
 * `<image>:<tag>@<first 12 hex of the served digest>`. The label carries no second colon on
 * purpose: status.ts `majorLineOf` reads the text after the last colon, and a hex prefix that
 * starts with digits would read as a phantom newer major line. Like every docker candidate the
 * core reads it as a major, so it is taken only with `--major --reason`; it is dated by the
 * tag's last push and waits out the shared release-age window like any new image. The plan
 * rewrites the digest alone, and refuses when Hub has moved the tag again since the label
 * was printed. A pinned tag whose digest matches offers nothing.
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
import { HUB_DEFAULT_BASE, hubRepo, hubTagUrl, parseTagDigest } from '../../docker-hub.js';
import { isWithinFreshnessWindow } from '../../release-age.js';
import type { DriverContext, Inspection, PinDriver, PinPlan, PlanStep } from '../driver.js';
import { leafCurrent, PlanRefused, planLeafSites } from '../driver.js';
import { type PinEntry, siteMatches } from '../registry.js';
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
/** Hex characters of the served digest a re-digest label carries. */
const REDIGEST_HEX = 12;
const REDIGEST_LABEL = /^(.*)@([0-9a-f]{12})$/;
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

/**
 * The first line a `version` site of `entry` matches that also carries `@sha256:`, as
 * `<file>:<line>`, or null. Such a line pins a digest beside the tag, and an entry with no
 * `digest` site would move the tag and keep the digest of the old one (the 26.13.0 tag over a
 * 26.12.0 digest of #d4b2a051), so the plan refuses rather than write it.
 */
export function digestedVersionLine(entry: PinEntry, ctx: DriverContext): string | null {
  for (const site of entry.sites) {
    if (site.role !== 'version' || site.json !== undefined) continue;
    const text = ctx.read(site);
    if (text === null) continue;
    const lines = text.split('\n');
    for (const m of siteMatches(site, text))
      for (let l = m.line; l <= m.lastLine; l++)
        if ((lines[l - 1] ?? '').includes('@sha256:'))
          return `${site.repo === '.' ? '' : `${site.repo}/`}${site.file}:${l}`;
  }
  return null;
}

/**
 * The re-digest candidate of a leaf (see THE RE-DIGEST above), or null when the leaf has no
 * `digest` site or its digest matches what Docker Hub serves for the pinned tag. A lookup that
 * cannot answer throws, so the pin reads `not compared` rather than current.
 */
async function redigestRelease(
  entry: PinEntry,
  ctx: DriverContext,
  deps: Deps,
  repo: string,
  image: string,
  tag: string
): Promise<LineDatedRelease | null> {
  const site = entry.sites.find((s) => s.role === 'digest');
  if (!site) return null;
  const text = ctx.read(site);
  const pinned = text === null ? undefined : siteMatches(site, text)[0]?.value;
  if (pinned === undefined) throw new Error(`${entry.id}: its digest site matches nothing`);
  const answer = (await deps.json(hubTagUrl(HUB_DEFAULT_BASE, repo, tag), image)) as {
    tag_last_pushed?: unknown;
    last_updated?: unknown;
  };
  const served = parseTagDigest(answer);
  if (served === null)
    throw new Error(`Docker Hub gives no index digest for the pinned ${image}:${tag}`);
  if (served === pinned) return null;
  const pushed = answer.tag_last_pushed ?? answer.last_updated;
  const at = typeof pushed === 'string' ? Date.parse(pushed) : Number.NaN;
  const publishedMs = Number.isNaN(at) ? null : at;
  const fresh =
    publishedMs === null || isWithinFreshnessWindow(publishedMs, deps.nowMs(), deps.windowMs());
  return {
    version: `${image}:${tag}@${served.slice('sha256:'.length, 'sha256:'.length + REDIGEST_HEX)}`,
    publishedMs,
    verdict: fresh
      ? {
          eligible: false,
          why: `a re-digest of ${image}:${tag} to ${served}: ${publishedMs === null ? 'the re-push has no date' : `re-pushed ${new Date(publishedMs).toISOString()}, inside the release-age window`}`,
        }
      : {
          eligible: true,
          why: `a re-digest of ${image}:${tag}: Docker Hub serves ${served}, the file pins ${pinned}; taken only with --major --reason`,
        },
  };
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
      const repo = hubRepo(image);
      if (repo === null) throw new Error(`${image} is not a Docker Hub image`);
      let url: string | null =
        `${HUB_DEFAULT_BASE}/v2/repositories/${repo}/tags?page_size=100&name=${encodeURIComponent(cur[2].replace(/^-/, ''))}`;
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
      const redigest =
        mutant === 'docker-skip-redigest'
          ? null
          : await redigestRelease(entry, ctx, deps, repo, image, tag);
      return {
        current: `${image}:${tag}`,
        releases: redigest ? [...releases, redigest] : releases,
      };
    },
    async plan(entry, to, ctx): Promise<PinPlan> {
      const image = entry.source.image as string;
      const label = REDIGEST_LABEL.exec(to.version.slice(image.length + 1));
      const tag = label ? label[1] : to.version.slice(image.length + 1);
      const old = leafCurrent(entry, ctx) as string;
      const oldTag = old.includes(':') ? old.slice(old.indexOf(':') + 1) : old;
      const values: Record<string, string> = {
        version: old.includes(':') ? `${image}:${tag}` : tag,
      };
      const digestSites = entry.sites.filter((s) => s.role === 'digest');
      if (digestSites.length === 0) {
        if (label)
          throw new PlanRefused(
            `${entry.id}: ${to.version} is a re-digest, and the entry has no \`digest\` site to write it to`
          );
        const pinned = digestedVersionLine(entry, ctx);
        if (pinned !== null)
          throw new PlanRefused(
            `${entry.id}: ${pinned} pins a digest beside the tag, and the entry has no \`digest\` site, so a bump would move the tag and leave the old digest behind; add a site with role digest whose value group is the \`sha256:<hex>\` on that line`
          );
      } else {
        const refusal = `${entry.id}: Docker Hub gives no digest for ${image}:${tag}; refusing to move the tag without it`;
        const repo = hubRepo(image);
        if (repo === null) throw new PlanRefused(`${refusal} (${image} is not a Docker Hub image)`);
        let answer: unknown;
        try {
          answer = await depsFor(ctx.root).json(hubTagUrl(HUB_DEFAULT_BASE, repo, tag), image);
        } catch (err) {
          throw new PlanRefused(`${refusal} (${(err as Error).message})`);
        }
        const digest = parseTagDigest(answer);
        if (digest === null) throw new PlanRefused(refusal);
        if (label && !digest.startsWith(`sha256:${label[2]}`))
          throw new PlanRefused(
            `${entry.id}: ${to.version} names a digest starting ${label[2]}, and Docker Hub now serves ${digest} for ${image}:${tag}; the tag was re-pushed again, so re-run \`npm run pins -- status ${entry.id}\` for the current label`
          );
        values.digest = digest;
        if (mutant === 'docker-keep-digest') {
          const text = ctx.read(digestSites[0]);
          values.digest =
            (text === null ? null : siteMatches(digestSites[0], text)[0]?.value) ?? digest;
        }
      }
      const planned = planLeafSites(entry, values, ctx);
      const { writes } = planned;
      // A re-digest writes the tag back unchanged; only the digest line is a change worth naming.
      const changes = label
        ? planned.changes.filter((c) => !/: version (\S+) -> \1$/.test(c))
        : planned.changes;
      const steps: PlanStep[] = [];
      let listed = false;
      try {
        listed = ((JSON.parse(ctx.read(BASELINE) ?? '[]') as string[] | null) ?? []).includes(
          `${image}:${oldTag}`
        );
      } catch {
        throw new PlanRefused(`${BASELINE.file} is not a JSON list`);
      }
      // A re-digest keeps the tag, so a baselined stale tag stays stale and stays listed.
      if (listed && !label && mutant !== 'docker-no-drain')
        steps.push({
          label: 'drain the docker freshness baseline',
          run: 'npx tsx scripts/gates/check-docker-image-freshness.ts --write-baseline',
          cwd: '.',
          writes: [BASELINE],
        });
      return { entry, from: `${image}:${oldTag}`, to, writes, steps, changes };
    },
    holdKey: leafKey,
  };
}
