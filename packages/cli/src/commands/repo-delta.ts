import { randomUUID } from 'node:crypto';
import type { RepositoryConfig } from '@rediacc/shared/config-schema';
import { configService } from '../services/config/config-resources.js';
import { getExecutor } from '../services/executor/executor-factory.js';
import { bindStepHandler } from '../services/jobs/steps.js';

/**
 * Resolve a hands-free delta base for pushing `repoConfig` to `machine`.
 * Prefers this repo's own previously-retained base (covers same-repo re-push),
 * then the closest immutable ancestor (headCommit -> parent -> grand) that was
 * itself pushed to this machine (covers fork/commit workflows). Returns
 * undefined when no base is known, so the push falls back to a full transfer.
 * The renet delta path independently re-verifies the base exists byte-identical
 * on both ends, so a stale hint here can only cost a fallback, never correctness.
 */
async function resolveAutoDeltaBase(
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

/** Reconstruct an immutable commit's mirror on the push target (best-effort): the successor job of an immutable push. */
async function syncCommitMetaToTarget(
  machine: string,
  meta: { commit: string; message?: string; author?: string; parent?: string; grand?: string }
): Promise<void> {
  try {
    await getExecutor().execute({
      functionName: 'repository_commit_meta',
      machineName: machine,
      // NO datastore on purpose (#74): `machine` here is the PUSH TARGET, and the image landed wherever that machine's own vault record points. The source repo's named mount is a path on a different host.
      params: {
        repository: meta.commit,
        ...(meta.message ? { message: meta.message } : {}),
        ...(meta.author ? { author: meta.author } : {}),
        ...(meta.parent ? { commitParent: meta.parent } : {}),
        ...(meta.grand ? { grandGuid: meta.grand } : {}),
      },
    });
  } catch {
    /* best-effort: `repo log` on the target falls back to the GUID-only walk */
  }
}

bindStepHandler('syncCommitMeta', async ({ params }) => {
  const opt = (key: string) =>
    typeof params[key] === 'string' && params[key] !== '' ? String(params[key]) : undefined;
  const target = opt('target');
  const commit = opt('commit');
  if (!target || !commit) throw new Error('step param "target" or "commit" is missing');
  await syncCommitMetaToTarget(target, {
    commit,
    message: opt('message'),
    author: opt('author'),
    parent: opt('parent'),
    grand: opt('grand'),
  });
});

/**
 * Record the immutable base retained on `machine` after a successful push, so
 * the next push of this repo (or a descendant) auto-deltas with no operator
 * flag. Best-effort: a config write failure must not fail the completed push.
 */
async function recordPushBase(
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

bindStepHandler('recordPushBase', async ({ params, finishedAt }) => {
  // A plan without a verified base has nothing to record; String() would store the text "undefined" as a delta base.
  for (const key of ['repo', 'machine', 'verifiedBase'] as const) {
    if (typeof params[key] !== 'string' || params[key] === '') {
      throw new Error(`step param "${key}" is missing`);
    }
  }
  const method = params.method === 'delta' ? 'delta' : 'rsync';
  await recordPushBase(
    String(params.repo),
    String(params.machine),
    method,
    String(params.verifiedBase),
    finishedAt ?? new Date().toISOString()
  );
});
