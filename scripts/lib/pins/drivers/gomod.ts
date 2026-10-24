/**
 * The `go-mod` driver of `npm run pins`: the direct Go dependencies of private/renet, bumped
 * from `go_deps --json` (agent/plans/PLAN-pins-command.md T8).
 *
 * THE PLAN COMES FROM THE GATE'S OWN PROBE. `check:ci-go-deps --json` (rediacc_ci.quality.
 * go_deps.plan_json) classifies every outdated direct module with the gate's code: `minor`
 * (taken), `toofresh` (inside the release-age window), `major` (refused), `blocked` (the
 * blocklist .ci/policy/.go-deps-upgrade-blocklist), `vulnerable` (the newer version is in
 * OSV, so it is not demanded). The driver adds no second opinion: a module the gate would not
 * demand is not bumped, and one it would demand is.
 *
 * WHAT ONE BUMP RUNS, in order, from the console root:
 *   1. `go get <module>@<latest> ...` in the module's directory (private/renet), one command
 *      for the whole group so the module graph resolves once;
 *   2. `go mod tidy` there;
 *   3. `go mod tidy` in every other go.mod the registry scopes (license-mint, which
 *      `replace`s the renet worktree and is red under check:ci-go-module-sync until it is
 *      tidy against renet's new graph), the mirror of step 2.
 * Each step declares the go.mod and go.sum it may write. The check:ci-go-deps and
 * check:ci-go-module-sync gates run after, as the entry's `gates` say.
 *
 * MAJORS ARE REFUSED, whatever `--major` says: a move of the major component can change the
 * import path (every importer is code) or the API, so it is a reviewed code change and never
 * a pin bump. The refusal is the release's own verdict and the plan's PlanRefused.
 *
 * A probe that could not run, or an upstream that did not answer, is not "nothing to bump":
 * inspect throws with the gate's own record line, so the pin reads "not compared".
 */
import path from 'node:path';
import type { DriverContext, Inspection, PinDriver, PinPlan, PlanStep } from '../driver.js';
import { PlanRefused } from '../driver.js';
import type { PinEntry, RepoPath } from '../registry.js';
import {
  type Deps,
  FAMILY_CURRENT,
  familyReleases,
  realDeps,
  shq,
  type T8Mutant,
} from './shared.js';

export interface GoRecord {
  module: string;
  current: string;
  latest: string;
  kind: string;
  published: number | null;
}

interface GoDoc {
  dirs: Array<{ dir: string; records: GoRecord[] }>;
  unanswered: string[];
  probeFailures: string[];
}

const GO_MAJOR_WHY =
  'a Go major move is refused: the import path changes at v2 and above and the API can break, so it is a reviewed code change in every importer, never a pin bump';

const majorOf = (v: string): number => Number.parseInt(/^v?(\d+)/.exec(v)?.[1] ?? '0', 10);

export function gomodDriver(
  depsFor: (root: string) => Deps = realDeps,
  mutant?: T8Mutant
): PinDriver {
  const deps = new WeakMap<DriverContext, Deps>();
  const depsOf = (ctx: DriverContext): Deps => {
    let d = deps.get(ctx);
    if (!d) deps.set(ctx, (d = depsFor(ctx.root)));
    return d;
  };
  const probes = new WeakMap<DriverContext, GoDoc>();

  /** Which go.mod directories the registry scopes: the probed ones (private/*) and the mirrors. */
  function scopeDirs(entry: PinEntry): Array<{ repo: string; dir: string; cwd: string }> {
    return (entry.scope ?? []).flatMap((sc) =>
      sc.files.map((f) => {
        const dir = path.posix.dirname(f);
        const rel = dir === '.' ? '' : dir;
        return { repo: sc.repo, dir: rel, cwd: path.posix.join(sc.repo, rel) };
      })
    );
  }

  function probe(entry: PinEntry, ctx: DriverContext): GoDoc {
    const have = probes.get(ctx);
    if (have) return have;
    const r = depsOf(ctx).run('python3 .ci/scripts/quality/check_go_deps.py --json', ctx.root);
    if (r.rc !== 0) throw new Error(`go_deps --json exited ${r.rc}: ${r.out.trim().slice(0, 300)}`);
    let doc: GoDoc;
    try {
      doc = JSON.parse(r.stdout) as GoDoc;
    } catch {
      throw new Error('go_deps --json printed no JSON document');
    }
    if (doc.probeFailures.length > 0)
      throw new Error(`the Go probe failed, so nothing was compared: ${doc.probeFailures[0]}`);
    if (doc.unanswered.length > 0)
      throw new Error(`an upstream did not answer (UPSTREAM REACHABILITY): ${doc.unanswered[0]}`);
    if (doc.dirs.length === 0)
      throw new Error('go_deps --json probed no Go directory: the scan lost private/');
    const scoped = new Set(scopeDirs(entry).map((s) => s.cwd));
    for (const d of doc.dirs)
      if (!scoped.has(d.dir))
        throw new Error(
          `go_deps probed ${d.dir}, which the go-mod scope of .ci/config/pins.json does not list`
        );
    probes.set(ctx, doc);
    return doc;
  }

  function groups(entry: PinEntry, ctx: DriverContext) {
    const doc = probe(entry, ctx);
    const pick = (kind: string) =>
      doc.dirs.flatMap((d) =>
        d.records.filter((r) => r.kind === kind).map((r) => ({ ...r, dir: d.dir }))
      );
    const eligible = pick('minor');
    const deferred = pick('toofresh');
    const major = pick('major');
    const newest = (rs: GoRecord[]): number | null =>
      rs.some((r) => r.published === null)
        ? null
        : Math.max(...rs.map((r) => (r.published as number) * 1000));
    const rel = familyReleases(
      { members: eligible, publishedMs: newest(eligible) },
      { members: deferred, publishedMs: newest(deferred) },
      {
        members: major,
        publishedMs: newest(major),
        verdict: { eligible: false, why: GO_MAJOR_WHY },
      }
    );
    return { eligible, deferred, major, ...rel };
  }

  return {
    name: 'go-mod',
    inspect(entry, ctx): Promise<Inspection> {
      try {
        return Promise.resolve({ current: FAMILY_CURRENT, releases: groups(entry, ctx).releases });
      } catch (err) {
        return Promise.reject(err);
      }
    },
    plan(entry, to, ctx): Promise<PinPlan> {
      const g = groups(entry, ctx);
      if (mutant !== 'go-allow-major' && to.version === g.versions.major && g.major.length > 0)
        return Promise.reject(
          new PlanRefused(
            `go-mod: ${GO_MAJOR_WHY} (${g.major.map((m) => `${m.module} ${m.current} -> ${m.latest}`).join(', ')})`
          )
        );
      const moving =
        mutant === 'go-allow-major' && to.version === g.versions.major
          ? g.major
          : to.version === g.versions.deferred && g.deferred.length > 0
            ? [...g.eligible, ...g.deferred]
            : g.eligible;
      if (moving.length === 0)
        return Promise.reject(new PlanRefused(`go-mod: ${to.version} stands for no module`));
      const bad =
        mutant === 'go-allow-major'
          ? undefined
          : moving.find((m) => majorOf(m.latest) > majorOf(m.current));
      if (bad)
        return Promise.reject(
          new PlanRefused(`go-mod: ${GO_MAJOR_WHY} (${bad.module} ${bad.current} -> ${bad.latest})`)
        );

      const dirs = scopeDirs(entry);
      const steps: PlanStep[] = [];
      const writesOf = (d: { repo: string; dir: string }): RepoPath[] => [
        { repo: d.repo, file: path.posix.join(d.dir, 'go.mod') || 'go.mod' },
        { repo: d.repo, file: path.posix.join(d.dir, 'go.sum') || 'go.sum' },
      ];
      const changes: string[] = [];
      const probed = new Set(moving.map((m) => m.dir));
      for (const dir of [...probed].sort((a, b) => Number(a > b) - Number(a < b))) {
        const d = dirs.find((x) => x.cwd === dir) as (typeof dirs)[number];
        const mods = moving.filter((m) => m.dir === dir);
        steps.push({
          label: `go get (${dir})`,
          run: `go get ${mods.map((m) => shq(`${m.module}@${m.latest}`)).join(' ')}`,
          cwd: d.cwd,
          writes: writesOf(d),
        });
        steps.push({
          label: `go mod tidy (${dir})`,
          run: 'go mod tidy',
          cwd: d.cwd,
          writes: writesOf(d),
        });
        for (const m of mods)
          changes.push(`${dir}/go.mod: ${m.module} ${m.current} -> ${m.latest}`);
      }
      // The mirrors: modules that replace the bumped worktree and must be tidy against it.
      const probedCwds = new Set(probe(entry, ctx).dirs.map((x) => x.dir));
      for (const d of dirs.filter((x) => mutant !== 'go-no-mirror' && !probedCwds.has(x.cwd))) {
        steps.push({
          label: `go mod tidy (${d.cwd}, mirrors ${[...probed].join(', ')})`,
          run: 'go mod tidy',
          cwd: d.cwd,
          writes: writesOf(d),
        });
        changes.push(`${d.cwd}/go.mod: tidied against ${[...probed].join(', ')}`);
      }
      return Promise.resolve({ entry, from: FAMILY_CURRENT, to, writes: [], steps, changes });
    },
    holdKey: () => null,
  };
}
