import { randomUUID } from 'node:crypto';
import type { RepositoryConfig } from '../schema/schemas.js';
import { configService } from '../services/config-resources.js';
import { localExecutorService } from '../services/local-executor.js';

/**
 * Resolve a hands-free delta base for pushing `repoConfig` to `machine`.
 * Prefers this repo's own previously-retained base (covers same-repo re-push),
 * then the closest immutable ancestor (headCommit -> parent -> grand) that was
 * itself pushed to this machine (covers fork/commit workflows). Returns
 * undefined when no base is known, so the push falls back to a full transfer.
 * The renet delta path independently re-verifies the base exists byte-identical
 * on both ends, so a stale hint here can only cost a fallback, never correctness.
 */
export async function resolveAutoDeltaBase(
  repoConfig: RepositoryConfig,
  machine: string
): Promise<string | undefined> {
  const own = repoConfig.pushState?.[machine]?.verifiedBase;
  if (own) return own;

  const ancestorGuids = [repoConfig.headCommit, repoConfig.parentGuid, repoConfig.grandGuid].filter(
    (g): g is string => !!g
  );
  for (const guid of ancestorGuids) {
    const ancestor = await configService.getRepository(guid).catch(() => undefined);
    const base = ancestor?.pushState?.[machine]?.verifiedBase;
    if (base) return base;
  }
  return undefined;
}

/**
 * Wire deterministic CoW-delta params onto a machine-target push. An explicit
 * `--delta-base` wins; otherwise a hands-free base is resolved. Either way a
 * fresh immutable base GUID is retained on both ends for next time, and the
 * repo's prior base is queued for pruning. Returns the retained base GUID so the
 * caller can record it after a successful push.
 */
export async function applyPushDeltaParams(
  params: Record<string, unknown>,
  options: Record<string, unknown>,
  repoConfig: RepositoryConfig,
  machine: string
): Promise<string> {
  if (options.strategy) params.strategy = options.strategy;
  const deltaBase =
    (options.deltaBase as string | undefined) ?? (await resolveAutoDeltaBase(repoConfig, machine));
  if (deltaBase) params.deltaBase = deltaBase;
  const retainBase = randomUUID();
  params.retainBase = retainBase;
  const priorBase = repoConfig.pushState?.[machine]?.verifiedBase;
  if (priorBase) params.retainBasePrune = priorBase;
  return retainBase;
}

/** Wire deterministic CoW-delta params onto a machine-source pull (explicit only). */
export function applyPullDeltaParams(
  params: Record<string, unknown>,
  options: Record<string, unknown>
): void {
  if (options.deltaBase) params.deltaBase = options.deltaBase;
  if (options.strategy) params.strategy = options.strategy;
}

/**
 * Post-push bookkeeping for a successful machine push: record the retained delta
 * base and, when the pushed object is an immutable commit, reconstruct its state
 * mirror on the target so cross-machine `rdc repo log` works post-push (commit
 * metadata travels in the image but the out-of-volume mirror does not). All
 * best-effort: the push already succeeded, so failures here are non-fatal.
 */
export async function finalizePush(
  repo: string,
  repoConfig: RepositoryConfig,
  machine: string,
  params: Record<string, unknown>,
  retainBase: string | undefined,
  debug?: boolean
): Promise<void> {
  if (retainBase) {
    const method = params.deltaBase ? 'delta' : 'rsync';
    await recordPushBase(repo, machine, method, retainBase, new Date().toISOString());
  }
  if (repoConfig.immutable) {
    await syncCommitMetaToTarget(repoConfig, machine, debug);
  }
}

/** Reconstruct an immutable commit's mirror on the target (best-effort). */
async function syncCommitMetaToTarget(
  repoConfig: RepositoryConfig,
  machine: string,
  debug?: boolean
): Promise<void> {
  try {
    await localExecutorService.execute({
      functionName: 'repository_commit_meta',
      machineName: machine,
      params: {
        repository: repoConfig.repositoryGuid,
        ...(repoConfig.commitMessage ? { message: repoConfig.commitMessage } : {}),
        ...(repoConfig.commitAuthor ? { author: repoConfig.commitAuthor } : {}),
        ...(repoConfig.commitParent ? { commitParent: repoConfig.commitParent } : {}),
        ...(repoConfig.grandGuid ? { grandGuid: repoConfig.grandGuid } : {}),
      },
      debug,
    });
  } catch {
    /* best-effort: `repo log` on the target falls back to the GUID-only walk */
  }
}

/**
 * Record the immutable base retained on `machine` after a successful push, so
 * the next push of this repo (or a descendant) auto-deltas with no operator
 * flag. Best-effort: a config write failure must not fail the completed push.
 */
export async function recordPushBase(
  repo: string,
  machine: string,
  method: 'rsync' | 'delta',
  verifiedBase: string,
  now: string
): Promise<void> {
  try {
    const cfg = await configService.getRepository(repo);
    if (!cfg) return;
    const pushState = { ...(cfg.pushState ?? {}) };
    pushState[machine] = { verifiedBase, lastPushAt: now, method };
    const key = (await configService.getRepositoryKey(repo)) ?? repo;
    await configService.addRepository(key, { ...cfg, pushState });
  } catch {
    /* best-effort: retention already happened on the machine */
  }
}
