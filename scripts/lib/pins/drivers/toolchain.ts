/**
 * The toolchain driver: the `toolchain:<tool>` pins of .devcontainer/toolchain.env,
 * .ci/config/constants.sh and the Dockerfiles that repeat them (agent/plans/PLAN-pins-command.md T7).
 *
 *   toolchain:go    go.dev/dl for the version and both archive sha256 values, the Go module proxy
 *                   for the publish instant (go.dev carries none), then toolchain.env, the
 *                   Dockerfile ARG and its two hashes, both go.mod `go` lines, and `go mod tidy`
 *                   in each module. A release of ANOTHER minor line (1.26 -> 1.27) changes the
 *                   language version every go.mod declares, so it is marked BREAKING
 *                   (Release.breaking): a plain bump, `bump --all` and `apply-soaked` leave it,
 *                   `bump toolchain:go --major --reason "<why>"` takes it, and status ages the
 *                   line as a newer major.
 *   toolchain:npm   the npm registry, the three NPM_VERSION sites, then the canonical lockfile pass
 *                   over EVERY lockfile of the npm family scope under the NEW npm, since a lockfile
 *                   written by any other npm is refused by check:ci-lockfile.
 *   python tools    PyPI (ruff, mypy, pytest, pytest-xdist, PyYAML) for the version, GitHub
 *                   releases (uv, shfmt, shellcheck, actionlint, nfpm) for the version and every
 *                   per-platform sha256 by the asset filename the registry names.
 *   toolchain:awscli  the aws/aws-cli tags for the version (no release is cut, so the tags are
 *                   read and dated by commit), and each versioned installer named by a full URL
 *                   in the site's `asset`, downloaded from awscli.amazonaws.com and hashed, since
 *                   AWS publishes no sha256 beside them.
 *   wrangler        the npm registry for the version in constants.sh.
 *
 * `toolchain:node` has a `none` source (the Node major is the operator's), and answers "not compared".
 */
import fs from 'node:fs';
import path from 'node:path';
import { WK_GO_DL_BASE } from '../../../../packages/shared/src/config/well-known.generated.js';
import { NotCompared, UnreadableListing } from '../../upstream.js';
import {
  type DriverContext,
  type Inspection,
  leafCurrent,
  type PinDriver,
  type PinPlan,
  PlanRefused,
  type PlanStep,
  planLeafSites,
  type Release,
} from '../driver.js';
import { idName, type PinEntry, type PinScope } from '../registry.js';
import { pinnedNpm } from './npm.js';
import { checkSites, digestFor, hashSites } from './toolchain-plan.js';
import {
  byNewest,
  type Dated,
  githubReleases,
  newerThan,
  npmVersions,
  pypiVersions,
  type Upstream,
} from './toolchain-upstream.js';

/** Selftest mutants: `half-hash` keeps an old hash when a digest is missing; `ambient-npm` runs the lockfile pass with the npm on PATH; `line-not-breaking` offers another Go minor line as a plain release. */
export const TOOLCHAIN_MUTANTS = ['half-hash', 'ambient-npm', 'line-not-breaking'] as const;
export type ToolchainMutant = (typeof TOOLCHAIN_MUTANTS)[number];

const GO_DL = `${WK_GO_DL_BASE}/?mode=json`;
const GO_ARCHIVE = 'linux-amd64.tar.gz';

interface GoFile {
  filename?: string;
  sha256?: string;
}
interface GoRelease {
  version?: string;
  stable?: boolean;
  files?: GoFile[];
}

/** The minor line of a Go version (the first two segments): the line a Go patch stays inside. */
const goLine = (v: string): string => v.split('.').slice(0, 2).join('.');

function refusal(err: unknown): PlanRefused {
  if (err instanceof PlanRefused) return err;
  if (err instanceof NotCompared || err instanceof UnreadableListing)
    return new PlanRefused(err.message);
  throw err;
}

interface Found extends Dated {
  digests: Map<string, string>;
  breaking?: { line: string; why: string };
}

/** The go.mod files whose `go` directive the toolchain:go entry rewrites, as repo-relative paths. */
const goModSites = (entry: PinEntry): string[] =>
  entry.sites
    .filter((x) => x.file === 'go.mod' || x.file.endsWith('/go.mod'))
    .map((x) => (x.repo === '.' ? x.file : `${x.repo}/${x.file}`));

/** Expand a registry scope glob made of literal segments and single-segment `*` against the tree. */
function expandScope(root: string, scope: PinScope): Array<{ repo: string; file: string }> {
  const out: Array<{ repo: string; file: string }> = [];
  for (const pattern of scope.files) {
    if (pattern.includes('**')) throw new Error(`scope glob ${pattern}: ** is not supported here`);
    let paths = [''];
    for (const seg of pattern.split('/')) {
      const next: string[] = [];
      for (const p of paths) {
        if (!seg.includes('*')) {
          next.push(p === '' ? seg : `${p}/${seg}`);
          continue;
        }
        const dir = path.join(root, scope.repo, p);
        if (!fs.existsSync(dir)) continue;
        const re = new RegExp(
          `^${seg.replace(/[.+?^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '[^/]*')}$`
        );
        for (const name of fs.readdirSync(dir).sort())
          if (re.test(name)) next.push(p === '' ? name : `${p}/${name}`);
      }
      paths = next;
    }
    for (const file of paths)
      if (fs.existsSync(path.join(root, scope.repo, file))) out.push({ repo: scope.repo, file });
  }
  return out;
}

export function createToolchainDriver(
  up: Upstream,
  mutant: ToolchainMutant | null = null
): PinDriver {
  async function goReleases(entry: PinEntry, current: string | null): Promise<Found[]> {
    const who = entry.name;
    const raw = await up.json(GO_DL, who);
    if (!Array.isArray(raw)) throw new UnreadableListing('go.dev/dl is not a release list');
    const found: Found[] = [];
    for (const r of raw as GoRelease[]) {
      if (!r.stable || !r.version?.startsWith('go')) continue;
      const version = r.version.slice(2);
      if (!/^\d+\.\d+(?:\.\d+)?$/.test(version)) continue;
      const digests = new Map<string, string>();
      for (const f of r.files ?? []) if (f.filename && f.sha256) digests.set(f.filename, f.sha256);
      found.push({ version, publishedMs: null, digests });
    }
    if (found.length === 0) throw new UnreadableListing('go.dev/dl lists no stable release');
    const newer = newerThan(byNewest(found), current);
    // go.dev publishes no date; the module proxy's toolchain record of the same release does.
    for (const f of newer) {
      const info = (await up.json(
        `https://proxy.golang.org/golang.org/toolchain/@v/v0.0.1-go${f.version}.${GO_ARCHIVE.replace('.tar.gz', '')}.info`,
        who
      )) as { Time?: string } | null;
      f.publishedMs = info?.Time ? Date.parse(info.Time) : null;
      if (
        current !== null &&
        goLine(f.version) !== goLine(current) &&
        mutant !== 'line-not-breaking'
      )
        f.breaking = {
          line: goLine(f.version),
          why: `Go ${goLine(f.version)} is another minor line than the pinned ${goLine(current)}; it changes the go directive of every go.mod (${goModSites(entry).join(', ') || 'none named'}), so it is a breaking move`,
        };
    }
    return newer;
  }

  async function foundFor(entry: PinEntry, current: string | null): Promise<Found[]> {
    const s = entry.source;
    const who = entry.name;
    const bare = (l: Dated[]): Found[] => l.map((d) => ({ ...d, digests: new Map() }));
    if (s.type === 'go-dl') return goReleases(entry, current);
    if (s.type === 'npm-registry' && s.package) return bare(await npmVersions(up, s.package, who));
    if (s.type === 'pypi' && s.package) return bare(await pypiVersions(up, s.package, who));
    if (s.type === 'github-release' && s.repo)
      return githubReleases(up, s.repo, s.tagPrefix ?? '', who, current);
    if (s.type === 'none') throw new Error(s.reason ?? 'the registry names no source');
    throw new Error(`the toolchain driver cannot read a ${s.type} source`);
  }

  async function inspect(entry: PinEntry, ctx: DriverContext): Promise<Inspection> {
    const current = leafCurrent(entry, ctx);
    const all = await foundFor(entry, current);
    return {
      current,
      releases: newerThan(byNewest(all), current).map(
        (r): Release => ({
          version: r.version,
          publishedMs: r.publishedMs,
          ...((r as Found).breaking ? { breaking: (r as Found).breaking } : {}),
        })
      ),
    };
  }

  /** The commands that follow the site rewrites. */
  function stepsFor(entry: PinEntry, to: Release, ctx: DriverContext): PlanStep[] {
    const steps: PlanStep[] = [];
    if (entry.id === 'toolchain:go') {
      for (const s of entry.sites.filter(
        (x) => x.file === 'go.mod' || x.file.endsWith('/go.mod')
      )) {
        const dir = path.posix.dirname(s.file);
        const cwd = path.posix.join(s.repo, dir === '.' ? '' : dir);
        steps.push({
          label: `go mod tidy in ${cwd}`,
          run: 'go mod tidy',
          cwd,
          writes: [
            { repo: s.repo, file: path.posix.join(dir, 'go.mod') },
            { repo: s.repo, file: path.posix.join(dir, 'go.sum') },
          ],
        });
      }
    }
    // A package.json site (toolchain:wrangler's workers/account/package.json) leaves its lockfile naming the old
    // version unless the lockfile pass runs in that directory, so npm ci refuses the pair and the old tool stays installed.
    if (entry.id !== 'toolchain:npm') {
      for (const s of entry.sites.filter(
        (x) => x.file === 'package.json' || x.file.endsWith('/package.json')
      )) {
        const dir = path.posix.dirname(s.file);
        const lock = path.posix.join(dir, 'package-lock.json');
        steps.push({
          label: `canonical lockfile pass for ${s.repo === '.' ? '' : `${s.repo}/`}${lock} after the ${s.file} rewrite`,
          run: `npx -y npm@${pinnedNpm(ctx.root)} install --package-lock-only --ignore-scripts`,
          cwd: path.posix.join(s.repo, dir === '.' ? '' : dir),
          writes: [{ repo: s.repo, file: lock }],
        });
      }
    }
    if (entry.id === 'toolchain:npm') {
      const family = ctx.reg.entries.filter((e) => e.driver === 'npm');
      const locks = family.flatMap((e) =>
        (e.scope ?? []).flatMap((sc) => expandScope(ctx.root, sc))
      );
      if (locks.length === 0)
        throw new PlanRefused(
          'toolchain:npm: VACUOUS scope, the npm family scope names no lockfile on disk'
        );
      const npm = mutant === 'ambient-npm' ? 'npm' : `npx -y npm@${to.version}`;
      for (const l of locks) {
        const dir = path.posix.dirname(l.file);
        steps.push({
          label: `canonical lockfile pass for ${l.repo === '.' ? '' : `${l.repo}/`}${l.file} under npm ${to.version}`,
          run: `${npm} install --package-lock-only --ignore-scripts`,
          cwd: path.posix.join(l.repo, dir === '.' ? '' : dir),
          writes: [{ repo: l.repo, file: l.file }],
        });
      }
    }
    return steps;
  }

  async function plan(entry: PinEntry, to: Release, ctx: DriverContext): Promise<PinPlan> {
    try {
      checkSites(entry, entry.sites, ctx.read);
      const current = leafCurrent(entry, ctx);
      const values: Record<string, string> = { version: to.version };
      const hashed = hashSites(entry);
      if (hashed.length > 0) {
        const hit = (await foundFor(entry, current)).find((r) => r.version === to.version);
        const digests = new Map(hit?.digests ?? []);
        // An asset named by a full URL (AWS's versioned aws CLI installers) has no published
        // digest anywhere, so it is downloaded and hashed; a release asset keeps the API digest.
        for (const site of hashed) {
          const url = site.asset?.replaceAll('{version}', to.version);
          if (url?.startsWith('https://') && !digests.has(url)) {
            if (!up.sha256) throw new PlanRefused(`${entry.id}: this upstream cannot hash ${url}`);
            digests.set(url, await up.sha256(url, entry.name));
          }
        }
        for (const site of hashed) {
          try {
            values[site.role] = digestFor(site, to.version, digests);
          } catch (err) {
            if (mutant !== 'half-hash' || !(err instanceof PlanRefused)) throw err;
            values[site.role] = 'keep-old-hash';
          }
        }
      }
      const { writes, changes } = planLeafSites(entry, values, ctx);
      return { entry, from: current, to, writes, steps: stepsFor(entry, to, ctx), changes };
    } catch (err) {
      throw refusal(err);
    }
  }

  return { name: 'toolchain', inspect, plan, holdKey: (e) => idName(e) };
}
