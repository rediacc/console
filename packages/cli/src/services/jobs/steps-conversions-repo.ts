/** Client-side steps of the conversion boxes J16 and J17: repo and backup verbs (see steps.ts). */

import {
  type ConfigServiceType,
  jsonParam,
  optStr,
  privateStep,
  type ReplicaSetRecord,
  type StepDefinition,
  str,
} from './steps-support.js';

type RepoRecord = NonNullable<Awaited<ReturnType<ConfigServiceType['getRepository']>>>;

export const REPO_CONVERSION_STEPS: StepDefinition[] = [
  // J16: repo verbs.
  {
    // The working fork's tip after `repo merge` (the source commit) or `repo checkout` (the checked-out commit).
    name: 'advanceHeadCommit',
    on: 'success',
    params: ['repo', 'commit'],
    load: async () => {
      const { configService } = await import('../config/config-resources.js');
      return async (ctx) => {
        const repo = str(ctx.params, 'repo');
        const cfg = await configService.getRepository(repo);
        if (!cfg) throw new Error(`Repository "${repo}" is not in the config`);
        const key = (await configService.getRepositoryKey(repo)) ?? repo;
        await configService.addRepository(key, { ...cfg, headCommit: str(ctx.params, 'commit') });
      };
    },
  },
  {
    // `repo commit`: register the immutable commit object, then advance the working fork's tip to it.
    name: 'recordRepoCommit',
    on: 'success',
    params: ['repo', 'commit', 'message', 'author', 'parent'],
    load: async () => {
      const { configService } = await import('../config/config-resources.js');
      return async (ctx) => {
        const repo = str(ctx.params, 'repo');
        const commit = str(ctx.params, 'commit');
        const cfg: RepoRecord | undefined = await configService.getRepository(repo);
        if (!cfg) throw new Error(`Repository "${repo}" is not in the config`);
        await configService.addRepository(commit, {
          repositoryGuid: commit,
          networkId: cfg.networkId,
          credential: cfg.credential,
          grandGuid: cfg.grandGuid ?? cfg.repositoryGuid,
          parentGuid: cfg.repositoryGuid,
          immutable: true,
          commitMessage: optStr(ctx.params, 'message'),
          commitAuthor: optStr(ctx.params, 'author'),
          commitParent: optStr(ctx.params, 'parent'),
        });
        const key = (await configService.getRepositoryKey(repo)) ?? repo;
        await configService.addRepository(key, { ...cfg, headCommit: commit });
      };
    },
  },
  {
    // `repo delete`: SSH-config cleanup, config-entry settlement, schedule reconcile, cloud backups and license (handleDeleteSuccess).
    name: 'settleRepoDelete',
    on: 'success',
    params: ['repo', 'machine', 'originalRef', 'archiveConfig', 'purgeBackups'],
    load: async () => {
      const [{ handleDeleteSuccess }, { configService }] = await Promise.all([
        import('../../commands/repo-create-delete.js'),
        import('../config/config-resources.js'),
      ]);
      return async (ctx) => {
        const repo = str(ctx.params, 'repo');
        const cfg = await configService.getRepository(repo);
        if (!cfg) throw new Error(`Repository "${repo}" is not in the config`);
        await handleDeleteSuccess(
          repo,
          optStr(ctx.params, 'machine') ?? ctx.machine,
          cfg,
          ctx.params.archiveConfig === true,
          { success: true, stdout: '', stderr: '', exitCode: 0, durationMs: 0 },
          optStr(ctx.params, 'originalRef'),
          ctx.params.purgeBackups === true
        );
      };
    },
  },
  {
    name: 'recordReplicaSet',
    on: 'success',
    params: ['set', 'replicaSet'],
    load: async () => {
      const { recordReplicaSet } = await import('../cluster/repo-replicate.js');
      return (ctx) =>
        recordReplicaSet(
          str(ctx.params, 'set'),
          jsonParam<ReplicaSetRecord>(ctx.params, 'replicaSet')
        );
    },
  },
  {
    name: 'forgetReplicaSet',
    on: 'success',
    params: ['set'],
    load: async () => {
      const { forgetReplicaSet } = await import('../cluster/repo-replicate.js');
      return (ctx) => forgetReplicaSet(str(ctx.params, 'set'));
    },
  },
  privateStep(
    'renderAutostartList',
    'success',
    ['machine'],
    () => import('../../commands/repo-extended.js'),
    true
  ),
  privateStep(
    'reportRepoFsck',
    'success',
    ['machine'],
    () => import('../../commands/repo-maintenance.js'),
    true
  ),
  privateStep(
    'reportRepoGc',
    'success',
    ['machine'],
    () => import('../../commands/repo-maintenance.js'),
    true
  ),
  privateStep(
    'recordCanary',
    'success',
    ['set', 'canary'],
    () => import('../cluster/repo-release.js')
  ),
  privateStep('forgetCanary', 'success', ['set'], () => import('../cluster/repo-release.js')),
  privateStep('printRepoCat', 'success', [], () => import('../../commands/repo-cat.js'), true),
  privateStep(
    'renderRepoDiff',
    'success',
    ['mode', 'json'],
    () => import('../../commands/repo-diff.js'),
    true
  ),
  privateStep(
    'mirrorGpuGrants',
    'success',
    ['repo', 'verb', 'device'],
    () => import('../../commands/repo-gpu.js'),
    true
  ),
  privateStep(
    'renderRepoList',
    'success',
    ['machine'],
    () => import('../../commands/repo-batch-utils.js'),
    true
  ),
  privateStep(
    'renderRepoLog',
    'success',
    [],
    () => import('../../commands/repo-branching.js'),
    true
  ),
  privateStep(
    'renderPolicyResult',
    'success',
    [],
    () => import('../../commands/repo-policy.js'),
    true
  ),
  privateStep(
    'renderRepoPrune',
    'success',
    ['survey'],
    () => import('../../commands/repo-prune.js'),
    true
  ),
  privateStep('printRepoStatus', 'success', [], () => import('../../commands/repo.js'), true),
  privateStep(
    'renderRepoTrim',
    'success',
    ['reportOnly'],
    () => import('../../commands/repo-trim.js'),
    true
  ),

  // J17: backup verbs.
  {
    name: 'warnIfConfigStorageUnenrolled',
    on: 'success',
    params: [],
    load: async () => {
      const { warnIfConfigStorageUnenrolled } = await import('../backup/dr-nudge.js');
      return () => warnIfConfigStorageUnenrolled();
    },
  },
  privateStep(
    'renderBackupBrowse',
    'success',
    ['repo'],
    () => import('../../commands/backup-storage.js'),
    true
  ),
  privateStep(
    'renderBackupList',
    'success',
    ['machine'],
    () => import('../../commands/repo-backup-list.js'),
    true
  ),
  privateStep(
    'seedStrategyRetention',
    'success',
    ['strategies', 'machine'],
    () => import('../../commands/backup-ops.js')
  ),
  privateStep(
    'renderBackupStatus',
    'success',
    ['machine', 'strategy'],
    () => import('../../commands/backup-ops.js'),
    true
  ),
];
