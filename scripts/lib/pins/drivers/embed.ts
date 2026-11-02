/**
 * The embed driver: the `embed:<base>` pins of private/renet (criu, rsync, zot, k3s and the
 * CSI sidecars), planned as one transaction (agent/plans/PLAN-pins-command.md T7).
 *
 * WHAT A BUMP MOVES, in one plan. scripts/lib/embed-pin-upgrade.ts `upgradeComponent` moves the
 * Dockerfile ARGs (VERSION, COMMIT, SHA256), embed-assets.lock.json and the Go constants and unit
 * goldens the entry's sites place in private/renet, and REFUSES when a tied commit or digest
 * cannot be resolved. This driver adds what that function never did:
 *   - the sites outside private/renet (the spec 09 unit table);
 *   - the sibling that shares a clone. snapshotter and snapshot-controller build from ONE
 *     external-snapshotter clone guarded by ONE commit ARG, so a plan for either moves both and
 *     refuses when the other is held or the two already differ;
 *   - the CRD CLAIM. pkg/kube/csidriver/crds.go and the lock's `notes` state which external-snapshotter
 *     release the vendored VolumeSnapshot CRDs come from. A bump that renames the claim without
 *     touching the CRDs makes the claim false (survey item 4 of the plan). The driver fetches the
 *     three CRDs at the new tag and either RE-VENDORS them (the bytes differ) or RECORDS a byte-identity
 *     proof (the bytes are the same), and in both cases moves the claim. When the tag's CRDs cannot be
 *     read, or are not the vendored set, there is neither a re-vendor nor a proof and the plan is
 *     refused;
 *   - a step that proves the unit goldens and the vendored CRDs agree with the new constants
 *     (`go test ./pkg/kube/csidriver`).
 * The credits generator is the registry's `derive` step and runs in the core.
 *
 * A driver never writes: the plan is file contents in memory plus the proving step.
 */
import crypto from 'node:crypto';
import {
  CONST_FILES,
  type Fetchers,
  sharedCloneDrift,
  type UpgradeFiles,
  upgradeComponent,
} from '../../embed-pin-upgrade.js';
import { NotCompared, UnreadableListing } from '../../upstream.js';
import {
  type DriverContext,
  type FileWrite,
  type Inspection,
  keyOf,
  leafCurrent,
  type PinDriver,
  type PinPlan,
  PlanRefused,
  type PlanStep,
  planLeafSites,
  type Release,
} from '../driver.js';
import { entriesFor, idName, type PinEntry, type RepoPath } from '../registry.js';
import { checkSites, isHeld, versionValues } from './toolchain-plan.js';
import {
  compareVersions,
  gh,
  githubReleases,
  rsyncVersions,
  type Upstream,
} from './toolchain-upstream.js';

/** Selftest mutants of this driver. Each disables one refusal, and the selftest proves its case goes red. */
export const EMBED_MUTANTS = [
  'blind-commit',
  'skip-crd',
  'claim-without-proof',
  'lone-sibling',
] as const;
export type EmbedMutant = (typeof EMBED_MUTANTS)[number];

const RENET = 'private/renet';

/** Components that build from one clone and must never differ. */
const SHARED_CLONE: Record<string, string> = {
  csisnapshotter: 'snapshotcontroller',
  snapshotcontroller: 'csisnapshotter',
};

/** The vendored CRD set and the claims that name its source release. */
const CRD_VENDOR = {
  repo: 'kubernetes-csi/external-snapshotter',
  upstreamDir: 'client/config/crd',
  dir: 'pkg/kube/csidriver/crds',
  names: [
    'snapshot.storage.k8s.io_volumesnapshotclasses.yaml',
    'snapshot.storage.k8s.io_volumesnapshotcontents.yaml',
    'snapshot.storage.k8s.io_volumesnapshots.yaml',
  ],
  /** The Go comment that names the release the CRDs were vendored from. */
  claimFile: 'pkg/kube/csidriver/crds.go',
  claimRe: /(external-snapshotter v)(\d+\.\d+\.\d+)( client\/config\/crd)/g,
  /** The lock component whose `notes` repeat the claim ("vendored verbatim from the same vX.Y.Z tag"). */
  lockComponent: 'csisnapshotter',
};

const sha256 = (s: string): string => crypto.createHash('sha256').update(s).digest('hex');

function refusal(err: unknown): PlanRefused {
  if (err instanceof PlanRefused) return err;
  if (err instanceof NotCompared || err instanceof UnreadableListing)
    return new PlanRefused(err.message);
  throw err;
}

export function createEmbedDriver(up: Upstream, mutant: EmbedMutant | null = null): PinDriver {
  async function inspect(entry: PinEntry, ctx: DriverContext): Promise<Inspection> {
    const current = leafCurrent(entry, ctx);
    const who = entry.name;
    const dated =
      entry.source.type === 'rsync-index'
        ? await rsyncVersions(up, who, current)
        : entry.source.type === 'github-release' && entry.source.repo
          ? await githubReleases(up, entry.source.repo, entry.source.tagPrefix ?? 'v', who, current)
          : null;
    if (dated === null)
      throw new Error(
        `the embed driver reads a github-release or rsync-index source, not ${entry.source.type}`
      );
    const newer = dated
      .filter((r) => current === null || compareVersions(r.version, current) > 0)
      .map((r): Release => ({ version: r.version, publishedMs: r.publishedMs }));
    return { current, releases: newer };
  }

  function fetchers(): Fetchers {
    return {
      async commitOf(repo, tag) {
        try {
          const c = (await up.json(
            gh(`/repos/${repo}/commits/${encodeURIComponent(tag)}`),
            `${repo}@${tag}`
          )) as { sha?: string } | null;
          if (!c?.sha) throw new UnreadableListing('no sha in the commit response');
          return c.sha;
        } catch (err) {
          // blind-commit: a tag nobody can resolve keeps a made-up commit, the half-moved pin upgradeComponent exists to refuse.
          if (mutant === 'blind-commit') return 'a'.repeat(40);
          throw err;
        }
      },
      text: (url) => up.text(url, url),
    };
  }

  async function plan(entry: PinEntry, to: Release, ctx: DriverContext): Promise<PinPlan> {
    try {
      return await planInner(entry, to, ctx);
    } catch (err) {
      throw refusal(err);
    }
  }

  async function planInner(entry: PinEntry, to: Release, ctx: DriverContext): Promise<PinPlan> {
    const base = idName(entry);
    const latest = to.version;
    const pinned = leafCurrent(entry, ctx);
    if (pinned === null) throw new PlanRefused(`${entry.id}: no pinned version is readable`);

    // The members of this plan: the entry, plus the component that shares its clone.
    const members: PinEntry[] = [entry];
    const sibling = SHARED_CLONE[base];
    if (sibling !== undefined && mutant !== 'lone-sibling') {
      const se = entriesFor(ctx.reg, 'embed').find((e) => idName(e) === sibling);
      if (!se)
        throw new PlanRefused(
          `${entry.id}: the shared-clone sibling embed:${sibling} is not in the registry`
        );
      if (isHeld(ctx, se, sibling, Date.now()))
        throw new PlanRefused(
          `${entry.id}: ${se.id} shares its clone and is held in ${se.holds[0]}; the two bump together, so lift that hold first`
        );
      members.push(se);
    }
    for (const m of members) {
      checkSites(m, m.sites, ctx.read);
      const now = versionValues(m.sites, ctx.read);
      if (m !== entry && now.some((v) => v !== pinned))
        throw new PlanRefused(
          `${entry.id}: ${m.id} is at ${[...new Set(now)].join(', ')} while ${entry.id} is at ${pinned}; they share one clone and must agree before either moves`
        );
    }

    const renetRead = (file: string): string | null => ctx.read({ repo: RENET, file });
    const dockerfile = renetRead('Dockerfile');
    if (dockerfile === null) throw new PlanRefused(`${RENET}/Dockerfile does not exist`);
    const before: UpgradeFiles = {
      dockerfile,
      lock: renetRead('embed-assets.lock.json'),
      consts: Object.fromEntries(
        CONST_FILES.flatMap((f) => {
          const t = renetRead(f);
          return t === null ? [] : [[f, t] as const];
        })
      ),
    };

    let files = before;
    const changes: string[] = [];
    for (const m of members) {
      const b = idName(m);
      const res = await upgradeComponent(
        files,
        {
          base: b,
          display: m.name,
          pinned,
          latest,
          repo: m.source.repo,
        },
        fetchers()
      );
      if (!res.ok) throw new PlanRefused(res.reason);
      files = res.files;
      changes.push(...res.changes.map((c) => `${m.id}: ${c}`));
    }
    const drift = sharedCloneDrift(files.dockerfile);
    if (drift && mutant !== 'lone-sibling') throw new PlanRefused(drift);

    // Everything outside private/renet that upgradeComponent does not reach, as one pseudo-entry so two members that share a file (the spec table holds both rows) compose.
    const outside: PinEntry = {
      ...entry,
      sites: members.flatMap((m) =>
        m.sites.filter((s) => s.repo !== RENET && s.role === 'version')
      ),
    };
    const extra =
      outside.sites.length > 0 ? planLeafSites(outside, { version: latest }, ctx) : null;

    const out = new Map<string, FileWrite>();
    const put = (p: RepoPath, after: string): void => {
      out.set(keyOf(p), { repo: p.repo, file: p.file, after });
    };
    for (const w of extra?.writes ?? []) put(w, w.after);
    changes.push(...(extra?.changes ?? []));

    // The CRD claim, for the component that vendors the CRDs.
    let lock = files.lock;
    const vendors = members.some((m) => idName(m) === CRD_VENDOR.lockComponent);
    if (vendors && mutant !== 'skip-crd') {
      const crd = await planCrds(up, ctx, pinned, latest, lock, mutant === 'claim-without-proof');
      for (const w of crd.writes) put(w, w.after);
      lock = crd.lock;
      changes.push(...crd.changes);
    }

    for (const [file, text] of Object.entries(files.consts))
      if (text !== before.consts[file]) put({ repo: RENET, file }, text);
    if (files.dockerfile !== before.dockerfile)
      put({ repo: RENET, file: 'Dockerfile' }, files.dockerfile);
    if (lock !== null && lock !== before.lock)
      put({ repo: RENET, file: 'embed-assets.lock.json' }, lock);

    // Re-count every site on the planned contents: a plan that leaves a site at the wrong count, or a version site at another value, is refused whole.
    const after = (p: RepoPath): string | null => out.get(keyOf(p))?.after ?? ctx.read(p);
    for (const m of members) {
      checkSites(m, m.sites, after);
      const wrong = versionValues(m.sites, after).filter((v) => v !== latest);
      if (wrong.length > 0)
        throw new PlanRefused(
          `${m.id}: after the plan a version site still holds ${[...new Set(wrong)].join(', ')}, not ${latest}`
        );
    }

    const steps: PlanStep[] = [];
    if (members.some((m) => m.sites.some((s) => s.file.startsWith('pkg/kube/csidriver/'))))
      steps.push({
        label: 'the unit goldens and vendored CRDs agree with the new constants',
        run: 'go test ./pkg/kube/csidriver',
        cwd: RENET,
        writes: [],
      });
    return { entry, from: pinned, to, writes: [...out.values()], steps, changes };
  }

  return { name: 'embed', inspect, plan, holdKey: (e) => idName(e) };
}

interface CrdPlan {
  writes: FileWrite[];
  lock: string | null;
  changes: string[];
}

/**
 * The vendored CRDs against the new tag. Identical bytes: the claim moves and the proof is
 * recorded in the change lines (and so in the message draft). Different bytes: the three files
 * are re-vendored verbatim. No readable set at the tag, or a set that is not the three vendored
 * files: refused, since the claim would then name a release the CRDs do not come from.
 */
async function planCrds(
  up: Upstream,
  ctx: DriverContext,
  pinned: string,
  latest: string,
  lock: string | null,
  claimWithoutProof: boolean
): Promise<CrdPlan> {
  const v = CRD_VENDOR;
  const tag = `v${latest}`;
  const who = `${v.repo}@${tag} ${v.upstreamDir}`;
  const none = (why: string): PlanRefused =>
    new PlanRefused(
      `the CRD claim in ${v.claimFile} cannot move to ${tag}: ${why}, so there is neither a re-vendor from the new tag nor a byte-identity proof. Re-vendor ${v.dir} from ${v.repo} ${tag} ${v.upstreamDir} first`
    );
  const fetched = new Map<string, string>();
  if (!claimWithoutProof) {
    let listing: unknown;
    try {
      listing = await up.json(gh(`/repos/${v.repo}/contents/${v.upstreamDir}?ref=${tag}`), who);
    } catch (err) {
      throw none(err instanceof Error ? err.message : String(err));
    }
    const upstreamNames = Array.isArray(listing)
      ? (listing as Array<{ name?: string }>)
          .map((x) => x.name ?? '')
          .filter((n) => n.startsWith('snapshot.storage.k8s.io_') && n.endsWith('.yaml'))
          .sort((a, b) => Number(a > b) - Number(a < b))
      : [];
    if (
      upstreamNames.join(',') !==
      [...v.names].sort((a, b) => Number(a > b) - Number(a < b)).join(',')
    )
      throw none(
        `${tag} ships [${upstreamNames.join(', ')}], not the vendored set [${v.names.join(', ')}]`
      );
    for (const name of v.names) {
      try {
        fetched.set(
          name,
          await up.text(
            `https://raw.githubusercontent.com/${v.repo}/${tag}/${v.upstreamDir}/${name}`,
            who
          )
        );
      } catch (err) {
        throw none(err instanceof Error ? err.message : String(err));
      }
    }
  }

  const writes: FileWrite[] = [];
  const changes: string[] = [];
  const drifted: string[] = [];
  for (const name of v.names) {
    const file = `${v.dir}/${name}`;
    const have = ctx.read({ repo: RENET, file });
    if (have === null) throw new PlanRefused(`${RENET}/${file} does not exist`);
    const next = fetched.get(name);
    if (next === undefined) continue;
    if (next !== have) {
      drifted.push(name);
      writes.push({ repo: RENET, file, after: next });
    }
  }
  if (!claimWithoutProof) {
    changes.push(
      drifted.length === 0
        ? `CRDs: byte-identical to ${v.repo} ${tag} ${v.upstreamDir} (proof: ${v.names
            .map(
              (n) =>
                `${n.slice('snapshot.storage.k8s.io_'.length, -'.yaml'.length)} sha256 ${sha256(fetched.get(n) as string).slice(0, 12)}`
            )
            .join(', ')}); the claim moves from v${pinned} to ${tag}`
        : `CRDs: re-vendored verbatim from ${v.repo} ${tag} ${v.upstreamDir} (${drifted.join(', ')} changed)`
    );
  } else {
    changes.push(`CRDs: claim moved to ${tag} WITHOUT a proof (MUTANT claim-without-proof)`);
  }

  // The claims.
  const goText = ctx.read({ repo: RENET, file: v.claimFile });
  if (goText === null) throw new PlanRefused(`${RENET}/${v.claimFile} does not exist`);
  const hits = [...goText.matchAll(v.claimRe)];
  if (hits.length !== 1)
    throw new PlanRefused(
      `${RENET}/${v.claimFile}: the CRD claim "external-snapshotter vX.Y.Z client/config/crd" matches ${hits.length} time(s), expected 1; the comment moved, so update CRD_VENDOR`
    );
  writes.push({
    repo: RENET,
    file: v.claimFile,
    after: goText.replace(v.claimRe, `$1${latest}$3`),
  });
  changes.push(`${v.claimFile}: CRD claim v${hits[0][2]} -> v${latest}`);

  let nextLock = lock;
  if (lock !== null) {
    const doc = JSON.parse(lock) as { components?: Record<string, { notes?: string }> };
    const comp = doc.components?.[v.lockComponent];
    if (comp?.notes?.includes(`v${pinned}`)) {
      comp.notes = comp.notes.replaceAll(`v${pinned}`, tag);
      nextLock = `${JSON.stringify(doc, null, 2)}\n`;
      changes.push(
        `embed-assets.lock.json components.${v.lockComponent}.notes: CRD claim v${pinned} -> ${tag}`
      );
    }
  }
  return { writes, lock: nextLock, changes };
}
