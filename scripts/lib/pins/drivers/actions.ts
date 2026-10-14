/**
 * The `actions` driver of `npm run pins`: every `uses: owner/repo@<sha> # vX.Y.Z` pin of the
 * console, bumped from the repository's latest release (agent/plans/PLAN-pins-command.md
 * T8, Design 3).
 *
 * WHAT ONE BUMP WRITES, which `check:actions`' old sed recipe did not:
 *   1. every `uses:` of the action under the entry's `scope` (workflows, composite actions,
 *      the breakpoint workflow), sub-path actions included (`actions/cache/restore@` moves
 *      with `actions/cache`), the SHA from the release tag and the version comment kept in
 *      its own style (`# v7.0.2` stays a full version, `# v4` stays a major);
 *   2. the registry's `sha:` sites: the UPLOAD_ARTIFACT_PIN constant in scripts/gate-bind.ts
 *      (the receipt step the binder emits, so a sed bump was reverted by the next
 *      `gate-bind --write`) and the `owner/repo@<sha>` pattern in
 *      .ci/config/actions-allowlist.json, each refused whole when it does not match the
 *      registry's `expect` count;
 *   3. a derive step, `gate-bind --write`, whenever the constant moved, so the generated
 *      workflow regions carry the new pin in the same run.
 *
 * THE SHA IS RESOLVED FROM THE TAG through `repos/<repo>/commits/<tag>`, which dereferences a
 * lightweight and an annotated tag alike (`git/ref/tags` returns the tag object for an
 * annotated one). A response that is not 40 hex digits refuses the pin.
 *
 * WHAT IT REFUSES, naming the action: a pin with no version comment (nothing to compare), an
 * upstream that did not answer or publishes no release (the gate's own fail-closed rule),
 * and a SHA the tag does not resolve to. A blocklisted action (.ci/policy/.actions-upgrade-
 * blocklist) is left out of the plan, as the gate leaves it out of its verdict. The
 * allowlist file is the repository's committed copy of a GitHub SETTING: after a bump of a
 * pattern pinned there the setting itself must be refreshed by the operator
 * (`npm run check:ci-actions-allowlist -- --refresh` reads it), and the plan says so.
 */

import { isWithinFreshnessWindow } from '../../release-age.js';
import type {
  DriverContext,
  FileWrite,
  Inspection,
  PinDriver,
  PinPlan,
  PlanStep,
} from '../driver.js';
import { keyOf, PlanRefused, planLeafSites } from '../driver.js';
import type { PinEntry, PinSite, RepoPath } from '../registry.js';
import {
  type Deps,
  FAMILY_CURRENT,
  familyReleases,
  listFiles,
  realDeps,
  type T8Mutant,
} from './shared.js';

const USES =
  /^(\s*-?\s*uses:\s*["']?)([A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+)((?:\/[A-Za-z0-9_./-]+)?)@([0-9a-f]{40})\b(.*)$/;
const VERSION_TOKEN = /v?\d+(?:\.\d+)*/;
const BLOCKLIST = { repo: '.', file: '.ci/policy/.actions-upgrade-blocklist' };

interface Use {
  file: RepoPath;
  repo: string;
  sha: string;
  /** The version token inside the trailing comment, or null when the pin carries none. */
  token: string | null;
}

export interface Latest {
  tag: string;
  publishedMs: number | null;
}

interface Member {
  repo: string;
  uses: Use[];
  /** The oldest version token among the pins: the one the comparison starts from. */
  current: string;
  latest: Latest;
  major: boolean;
}

/** `v4` and `4` are floating majors: they track the latest release of that major. */
const isMajorOnly = (tok: string): boolean => /^v?\d+$/.test(tok);
const majorNum = (v: string): number => Number.parseInt(v.replace(/^v/, ''), 10) || 0;

/** check-actions' comparison: -1 when `a` is older than `b`, a floating major equal while the majors agree. */
function compare(a: string, b: string): number {
  const num = (v: string): number[] =>
    v
      .replace(/^v/, '')
      .split('.')
      .map((x) => Number.parseInt(x, 10) || 0);
  const x = num(a);
  const y = num(b);
  if (x[0] !== y[0]) return x[0] < y[0] ? -1 : 1;
  if (isMajorOnly(a)) return 0;
  for (let i = 1; i < 3; i++) {
    const d = (x[i] ?? 0) - (y[i] ?? 0);
    if (d !== 0) return d < 0 ? -1 : 1;
  }
  return 0;
}

/** The new token in the style of the old one: `v` kept or dropped, a floating major kept a major. */
function styled(old: string, tag: string): string {
  const bare = tag.replace(/^v/, '');
  const body = isMajorOnly(old) ? String(majorNum(tag)) : bare;
  return old.startsWith('v') ? `v${body}` : body;
}

function scanUses(entry: PinEntry, ctx: DriverContext): Use[] {
  const out: Use[] = [];
  for (const sc of entry.scope ?? []) {
    if (sc.scanner !== 'action-uses') continue;
    for (const file of listFiles(ctx.root, sc.repo, sc.files)) {
      if (!/\.ya?ml$/.test(file)) continue;
      const rp = { repo: sc.repo, file };
      const text = ctx.read(rp);
      if (text === null) continue;
      for (const line of text.split('\n')) {
        const m = USES.exec(line);
        if (!m || m[2].startsWith('rediacc/')) continue;
        const comment = /^\s*#\s*(.*)$/.exec(m[5])?.[1] ?? null;
        out.push({
          file: rp,
          repo: m[2],
          sha: m[4],
          token: comment === null ? null : (VERSION_TOKEN.exec(comment)?.[0] ?? null),
        });
      }
    }
  }
  return out;
}

function blocked(ctx: DriverContext): Set<string> {
  const text = ctx.read(BLOCKLIST) ?? '';
  const out = new Set<string>();
  for (const raw of text.split('\n')) {
    const t = raw.trim();
    if (t === '' || t.startsWith('#')) continue;
    out.add(t.split(/\s+/)[0]);
  }
  return out;
}

export function actionsDriver(
  depsFor: (root: string) => Deps = realDeps,
  mutant?: T8Mutant
): PinDriver {
  // Network facts, once per run context: inspect asks, plan reuses the answers.
  const memo = new WeakMap<DriverContext, Map<string, Promise<Latest>>>();
  const shaMemo = new WeakMap<DriverContext, Map<string, Promise<string>>>();
  const depsMemo = new WeakMap<DriverContext, Deps>();
  const deps = (ctx: DriverContext): Deps => {
    let d = depsMemo.get(ctx);
    if (!d) depsMemo.set(ctx, (d = depsFor(ctx.root)));
    return d;
  };
  const cached = <T>(
    m: WeakMap<DriverContext, Map<string, Promise<T>>>,
    ctx: DriverContext,
    key: string,
    make: () => Promise<T>
  ): Promise<T> => {
    let per = m.get(ctx);
    if (!per) m.set(ctx, (per = new Map()));
    let p = per.get(key);
    if (!p) per.set(key, (p = make()));
    return p;
  };

  const latestOf = (ctx: DriverContext, repo: string): Promise<Latest> =>
    cached(memo, ctx, repo, async () => {
      const j = (await deps(ctx).github(`/repos/${repo}/releases/latest`, repo)) as {
        tag_name?: unknown;
        published_at?: unknown;
      } | null;
      if (typeof j?.tag_name !== 'string' || j.tag_name === '')
        throw new Error(`${repo}: the latest release carries no tag_name`);
      const at = typeof j.published_at === 'string' ? Date.parse(j.published_at) : Number.NaN;
      return { tag: j.tag_name, publishedMs: Number.isNaN(at) ? null : at };
    });

  const shaOf = (ctx: DriverContext, repo: string, tag: string): Promise<string> =>
    cached(shaMemo, ctx, `${repo}@${tag}`, async () => {
      const j = (await deps(ctx).github(`/repos/${repo}/commits/${tag}`, repo)) as {
        sha?: unknown;
      } | null;
      if (typeof j?.sha !== 'string' || !/^[0-9a-f]{40}$/.test(j.sha))
        throw new PlanRefused(`${repo}: tag ${tag} did not resolve to a 40-digit commit SHA`);
      return j.sha;
    });

  async function members(entry: PinEntry, ctx: DriverContext): Promise<Member[]> {
    const uses = scanUses(entry, ctx);
    if (uses.length === 0)
      throw new Error('no `uses:` pin found under the scope: the scan lost the tree');
    const byRepo = new Map<string, Use[]>();
    for (const u of uses) byRepo.set(u.repo, [...(byRepo.get(u.repo) ?? []), u]);
    const bare = [...byRepo].filter(([, us]) => us.some((u) => u.token === null));
    if (bare.length > 0)
      throw new Error(
        `${bare.map(([r]) => r).join(', ')}: the pin carries no version comment, so there is nothing to compare with the latest release (pin it as \`owner/repo@<sha> # vX.Y.Z\`)`
      );
    const skip = blocked(ctx);
    const names = [...byRepo.keys()].filter((r) => !skip.has(r));
    const latest = await Promise.all(names.map((r) => latestOf(ctx, r)));
    const out: Member[] = [];
    for (const [i, repo] of names.entries()) {
      const us = byRepo.get(repo) as Use[];
      const current = us
        .map((u) => u.token as string)
        .reduce((lo, t) => (compare(t, lo) < 0 ? t : lo));
      if (compare(current, latest[i].tag) >= 0) continue;
      out.push({
        repo,
        uses: us,
        current,
        latest: latest[i],
        major: majorNum(latest[i].tag) > majorNum(current),
      });
    }
    return out;
  }

  /** Which members each synthetic version stands for, recomputed from the same facts. */
  async function groups(entry: PinEntry, ctx: DriverContext) {
    const now = deps(ctx).nowMs();
    const window = deps(ctx).windowMs();
    const all = await members(entry, ctx);
    const settled = (m: Member): boolean =>
      mutant === 'actions-no-defer' ||
      (m.latest.publishedMs !== null &&
        !isWithinFreshnessWindow(m.latest.publishedMs, now, window));
    const newest = (ms: Member[]): number | null =>
      ms.some((m) => m.latest.publishedMs === null)
        ? null
        : Math.max(...ms.map((m) => m.latest.publishedMs as number));
    const minor = all.filter((m) => !m.major);
    const eligible = minor.filter(settled);
    const deferred = minor.filter((m) => !settled(m));
    const major = all.filter((m) => m.major);
    const rel = familyReleases(
      { members: eligible, publishedMs: newest(eligible) },
      { members: deferred, publishedMs: newest(deferred) },
      { members: major, publishedMs: newest(major) }
    );
    return { eligible, deferred, major, ...rel };
  }

  return {
    name: 'actions',
    async inspect(entry, ctx): Promise<Inspection> {
      const g = await groups(entry, ctx);
      return { current: FAMILY_CURRENT, releases: g.releases };
    },
    async plan(entry, to, ctx): Promise<PinPlan> {
      const g = await groups(entry, ctx);
      const moving =
        to.version === g.versions.major
          ? g.major
          : to.version === g.versions.deferred && g.deferred.length > 0
            ? [...g.eligible, ...g.deferred]
            : g.eligible;
      if (
        moving.length === 0 ||
        ![g.versions.eligible, g.versions.deferred, g.versions.major].includes(to.version)
      )
        throw new PlanRefused(`actions: ${to.version} stands for no member the source answered`);

      const shas = new Map<string, string>();
      for (const m of moving) shas.set(m.repo, await shaOf(ctx, m.repo, m.latest.tag));

      // 1. every `uses:` of a moving action.
      const texts = new Map<string, { p: RepoPath; text: string }>();
      const changes: string[] = [];
      const counts = new Map<string, number>();
      for (const m of moving) {
        const newSha = shas.get(m.repo) as string;
        for (const u of m.uses) {
          const k = keyOf(u.file);
          const cur = texts.get(k)?.text ?? (ctx.read(u.file) as string);
          const next = cur
            .split('\n')
            .map((line) => {
              const mm = USES.exec(line);
              if (!mm || mm[2] !== m.repo || mm[4] !== u.sha) return line;
              counts.set(m.repo, (counts.get(m.repo) ?? 0) + 1);
              const after = mm[5].replace(
                /^(\s*#\s*)(.*)$/,
                (_s, lead: string, rest: string) =>
                  `${lead}${rest.replace(VERSION_TOKEN, styled(u.token as string, m.latest.tag))}`
              );
              return `${mm[1]}${mm[2]}${mm[3]}@${newSha}${after}`;
            })
            .join('\n');
          texts.set(k, { p: u.file, text: next });
        }
      }
      for (const m of moving) {
        const wanted = m.uses.length;
        const done = counts.get(m.repo) ?? 0;
        if (done !== wanted)
          throw new PlanRefused(
            `${m.repo}: rewrote ${done} of ${wanted} \`uses:\` pin(s); nothing is written for actions`
          );
        changes.push(
          `.github: ${m.repo} ${m.current} -> ${styled(m.current, m.latest.tag)} (${wanted} pin${wanted === 1 ? '' : 's'}, sha ${(shas.get(m.repo) as string).slice(0, 12)})`
        );
      }
      const writes: FileWrite[] = [...texts.values()].map(({ p, text }) => ({
        ...p,
        after: text,
      }));

      // 2. the registry's sha sites of the moving actions.
      const roleOf = (repo: string): string[] => {
        const [owner, name] = repo.split('/');
        return [`sha:${name}`, `sha:${owner}-${name}`];
      };
      const siteMembers = moving.filter(
        (m) =>
          mutant !== 'actions-skip-sites' &&
          entry.sites.some((s) => roleOf(m.repo).includes(s.role))
      );
      if (siteMembers.length > 0) {
        const values: Record<string, string> = {};
        const sites: PinSite[] = [];
        for (const m of siteMembers)
          for (const s of entry.sites)
            if (roleOf(m.repo).includes(s.role)) {
              values[s.role] = shas.get(m.repo) as string;
              sites.push(s);
            }
        const planned = planLeafSites({ ...entry, sites }, values, ctx);
        for (const w of planned.writes) {
          // A site that also carries the version comment (UPLOAD_ARTIFACT_PIN) moves with it.
          let text = w.after;
          for (const m of siteMembers) {
            const sha = shas.get(m.repo) as string;
            text = text.replace(
              new RegExp(`(@${sha}\\s*#\\s*)(${VERSION_TOKEN.source})`, 'g'),
              (_s, lead: string, tok: string) => `${lead}${styled(tok, m.latest.tag)}`
            );
          }
          writes.push({ ...w, after: text });
        }
        changes.push(...planned.changes);
        for (const s of sites)
          if (s.file.endsWith('actions-allowlist.json'))
            changes.push(
              `${s.file}: REFRESH the repository's actions allowlist setting by hand after this merges (\`npm run check:ci-actions-allowlist -- --refresh\` reads it); the committed copy only mirrors it`
            );
      }

      // 3. the generated workflow regions follow the constant.
      const steps: PlanStep[] = [];
      if (
        mutant !== 'actions-skip-gate-bind' &&
        writes.some((w) => w.file === 'scripts/gate-bind.ts')
      ) {
        steps.push({
          label: 'gate-bind --write',
          run: 'npx tsx scripts/gate-bind.ts --write',
          cwd: '.',
          writes: [
            ...listFiles(ctx.root, '.', [
              '.github/workflows/*.yml',
              '.github/workflows/*.yaml',
            ]).map((file) => ({ repo: '.', file })),
            ...listFiles(ctx.root, '.', ['.ci/config/shards/*.json']).map((file) => ({
              repo: '.',
              file,
            })),
          ],
        });
      }
      return { entry, from: FAMILY_CURRENT, to, writes, steps, changes };
    },
    holdKey: () => null,
  };
}
