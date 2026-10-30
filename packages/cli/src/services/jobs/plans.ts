/**
 * The job plan of every machine-plane command (PLAN-detached-jobs J0b, C3).
 *
 * One entry per command whose contract `plane` is `machine`
 * (packages/shared/src/cli-contract/data/contract.generated.ts), transcribed from the J0b audit table: the single-job
 * form, the renet function or command kind the job runs, its lock class, its timeout class, the client-side steps that
 * follow it (column 4, each a registered step in steps.ts) and the conversion box that converts it. A command that
 * does not become a job is in JOB_EXCEPTIONS with its section 24 reason. The coverage test fails for a machine-plane
 * command in neither table.
 *
 * Lock classes are renet's (private/renet/pkg/jobs/overlap.go). Where a plan names `fn`, its `lock` is the class
 * overlap.go gives that function, and `lockWithoutRepo` is the class it takes when the job names no repository
 * (overlap.go ClassForJob). A plan without `fn` runs a command kind renet does not list yet, or a chain of functions
 * with no compound function; its `note` says which.
 *
 * Keyed on `plane`, not on `detachable`: J2 changes `detachable`.
 */

/** renet's lock classes (overlap.go LockClass). */
export const LOCK_CLASSES = [
  'repo-exclusive',
  'repo-shared',
  'machine-exclusive',
  'machine-shared',
  'control',
  'read',
] as const;
export type LockClass = (typeof LOCK_CLASSES)[number];

/** Section 20's two timeout classes. */
export const TIMEOUT_CLASSES = ['10m', '24h'] as const;
export type TimeoutClass = (typeof TIMEOUT_CLASSES)[number];

/**
 * The single-job form (J0b column 3).
 *
 * - `single`: one renet call.
 * - `precondition`: the probes fold into the job as preconditions.
 * - `command-kind`: a raw renet subcommand on the section 14 allow-list.
 * - `compound`: several calls, as one compound function or a chain under one ticket.
 * - `successor`: one job, then a successor job recorded on the ticket.
 */
export type JobForm = 'single' | 'precondition' | 'command-kind' | 'compound' | 'successor';

export type ConversionBox = 'J4' | 'J16' | 'J17' | 'J18' | 'J19' | 'J20';

export interface JobPlan {
  form: JobForm;
  /** The renet function or command kind the job runs, as overlap.go names it. */
  fn?: string;
  lock: LockClass;
  /** The class when the job names no repository (`-m`, the survey forms). */
  lockWithoutRepo?: LockClass;
  timeout: TimeoutClass;
  box: ConversionBox;
  /** Client-side steps after the job, by registered step name (steps.ts). */
  steps?: readonly string[];
  /** A section 24 exception for one form of the command (an interactive or a local leg). */
  exception?: string;
  /** Why the plan names no `fn`, or what else the conversion box must know. */
  note?: string;
  /** For a plan with no `fn`: the overlap.go name (a command kind) its `lock` is read from. */
  lockFrom?: string;
  /**
   * For a plan with no `fn`: the renet function or kind it runs that overlap.go either does not
   * list (its fallback rules classify it) or classifies differently from `lock`. `overlap` is what
   * overlap.go gives it today, so a change in overlap.go fails the coverage test. A listed name
   * whose class agrees with `lock` is a `lockFrom`, not a gap.
   */
  lockGap?: { runs: string; overlap: LockClass };
}

const NEW_KIND =
  'runs as a command kind that is not on the section 14 allow-list yet (J0b finding 4)';
const CHAIN =
  'a chain across calls or machines with no compound renet function yet (J0b finding 9)';

export const JOB_PLANS: Readonly<Record<string, JobPlan>> = {
  // J4: the nine J0 verbs.
  'repo up': {
    form: 'single',
    fn: 'repository_up',
    lock: 'repo-exclusive',
    timeout: '24h',
    box: 'J4',
    steps: ['postRepoUpTasks'],
  },
  'repo down': {
    form: 'single',
    fn: 'repository_down',
    lock: 'repo-exclusive',
    timeout: '10m',
    box: 'J4',
  },
  'repo fork': {
    form: 'precondition',
    fn: 'repository_fork',
    lock: 'repo-shared',
    timeout: '24h',
    box: 'J4',
    steps: [
      'identityRefresh',
      'reconcileBackupSchedules',
      'rollbackFork',
      'forkUp',
      'postRepoUpTasks',
    ],
  },
  'repo push': {
    form: 'single',
    fn: 'backup_push',
    lock: 'repo-shared',
    timeout: '24h',
    box: 'J4',
    steps: ['reportPushStats', 'recordPushBase', 'syncCommitMeta'],
    note: 'repository_commit_meta on the target after an immutable push is the syncCommitMeta successor step (J0 Surprise 7)',
  },
  'repo pull': {
    form: 'successor',
    fn: 'backup_pull',
    lock: 'repo-exclusive',
    timeout: '24h',
    box: 'J4',
    steps: ['pullDeploy'],
    note: '--up runs repository_up {mount:true} as the pullDeploy successor step',
  },
  'repo migrate': {
    form: 'successor',
    fn: 'repository_migrate',
    lock: 'repo-exclusive',
    timeout: '24h',
    box: 'J4',
    steps: ['migratePlacement', 'migrateComplete'],
    note: 'the source job, then the migrateComplete step runs repository_up on the target and repository_delete on the source (J0b finding 1)',
  },
  'backup snapshot': {
    form: 'single',
    fn: 'backup_snapshot',
    lock: 'repo-shared',
    timeout: '24h',
    box: 'J4',
    steps: ['recordBackupRun', 'recordBackupRunFailed'],
  },
  'backup restore': {
    form: 'single',
    fn: 'backup_restore',
    lock: 'repo-exclusive',
    timeout: '24h',
    box: 'J4',
    steps: [
      'reconcileBackupSchedules',
      'recordBackupRun',
      'recordBackupRunFailed',
      'reportRestoreStats',
      'rollbackRestoreRegistration',
      'reportRestorePath',
      'restoreDeploy',
    ],
  },
  'backup verify': {
    form: 'single',
    fn: 'backup_verify',
    lock: 'repo-shared',
    timeout: '24h',
    box: 'J4',
    steps: ['reportVerifyVerdict', 'recordBackupRun', 'recordBackupRunFailed'],
  },

  // J16: repo verbs outside J4.
  'repo admin autostart disable': {
    form: 'precondition',
    fn: 'repository_autostart_disable',
    lock: 'repo-exclusive',
    timeout: '10m',
    box: 'J16',
    note: 'with -m it has no repository; overlap.go still classes it repo-exclusive, where the audit asks machine-exclusive',
  },
  'repo admin autostart enable': {
    form: 'precondition',
    fn: 'repository_autostart_enable',
    lock: 'repo-exclusive',
    timeout: '10m',
    box: 'J16',
    note: 'with -m it has no repository; overlap.go still classes it repo-exclusive, where the audit asks machine-exclusive',
  },
  'repo admin autostart list': {
    form: 'single',
    fn: 'repository_autostart_list',
    lock: 'read',
    timeout: '10m',
    box: 'J16',
    steps: ['renderAutostartList'],
  },
  'repo admin fsck': {
    form: 'compound',
    fn: 'repository_fsck',
    lock: 'machine-shared',
    timeout: '10m',
    box: 'J16',
    steps: ['reportRepoFsck'],
  },
  'repo admin ownership': {
    form: 'precondition',
    fn: 'repository_ownership',
    lock: 'repo-exclusive',
    timeout: '10m',
    box: 'J16',
  },
  'repo admin template apply': {
    form: 'precondition',
    fn: 'repository_template_apply',
    lock: 'repo-exclusive',
    timeout: '10m',
    box: 'J16',
  },
  'repo admin validate': {
    form: 'precondition',
    fn: 'repository_validate',
    lock: 'read',
    timeout: '10m',
    box: 'J16',
  },
  'repo canary create': {
    form: 'compound',
    fn: 'datastore_snapshot_create',
    lock: 'machine-exclusive',
    timeout: '24h',
    box: 'J16',
    steps: ['recordCanary'],
    note: 'then kube_apply on the control machine; overlap.go does not list kube_apply, so it falls to read',
  },
  'repo canary remove': {
    form: 'single',
    lock: 'repo-exclusive',
    lockGap: { runs: 'kube_delete', overlap: 'read' },
    timeout: '10m',
    box: 'J16',
    steps: ['forgetCanary'],
    note: 'runs kube_delete, which overlap.go does not list, so it falls to read; the audit asks repo-exclusive',
  },
  'repo canary weight': {
    form: 'compound',
    fn: 'datastore_snapshot_create',
    lock: 'machine-exclusive',
    timeout: '24h',
    box: 'J16',
    steps: ['recordCanary'],
    note: 'then kube_apply on the control machine',
  },
  'repo cat': {
    form: 'single',
    fn: 'repository_cat',
    lock: 'read',
    timeout: '10m',
    box: 'J16',
    steps: ['printRepoCat'],
  },
  'repo checkout': {
    form: 'precondition',
    fn: 'repository_fork',
    lock: 'repo-shared',
    timeout: '24h',
    box: 'J16',
    steps: ['identityRefresh', 'reconcileBackupSchedules', 'advanceHeadCommit', 'rollbackFork'],
  },
  'repo commit': {
    form: 'precondition',
    fn: 'repository_commit',
    lock: 'repo-exclusive',
    timeout: '10m',
    box: 'J16',
    steps: ['recordRepoCommit'],
  },
  'repo create': {
    form: 'precondition',
    fn: 'repository_create',
    lock: 'repo-exclusive',
    timeout: '24h',
    box: 'J16',
    steps: ['identityRefresh', 'reconcileBackupSchedules', 'rollbackCreate'],
    note: 'network_id "auto" removes the conflict-retry leg (J0b finding 8)',
  },
  'repo delete': {
    form: 'precondition',
    fn: 'repository_delete',
    lock: 'repo-exclusive',
    timeout: '10m',
    box: 'J16',
    steps: ['settleRepoDelete'],
  },
  'repo diff': {
    form: 'single',
    fn: 'repository_diff',
    lock: 'read',
    timeout: '10m',
    box: 'J16',
    steps: ['renderRepoDiff'],
  },
  'repo exec': {
    form: 'precondition',
    fn: 'container_exec',
    lock: 'repo-shared',
    timeout: '10m',
    box: 'J16',
    exception: 'the interactive form (-i, tty) needs the terminal (section 24)',
    note: 'the remote exit code is the result, so the ticket keeps the job exit code',
  },
  'repo expand': {
    form: 'precondition',
    fn: 'repository_expand',
    lock: 'repo-exclusive',
    timeout: '24h',
    box: 'J16',
  },
  'repo gc': {
    form: 'compound',
    fn: 'repository_gc',
    lock: 'machine-shared',
    timeout: '10m',
    box: 'J16',
    steps: ['reportRepoGc'],
  },
  'repo gpu grant': {
    form: 'precondition',
    fn: 'repository_gpu_grant',
    lock: 'repo-exclusive',
    timeout: '10m',
    box: 'J16',
    steps: ['mirrorGpuGrants'],
  },
  'repo gpu revoke': {
    form: 'precondition',
    fn: 'repository_gpu_revoke',
    lock: 'repo-exclusive',
    timeout: '10m',
    box: 'J16',
    steps: ['mirrorGpuGrants'],
  },
  'repo list': {
    form: 'single',
    fn: 'repository_list',
    lock: 'read',
    timeout: '10m',
    box: 'J16',
    steps: ['renderRepoList'],
  },
  'repo log': {
    form: 'single',
    fn: 'repository_log',
    lock: 'read',
    timeout: '10m',
    box: 'J16',
    steps: ['renderRepoLog'],
  },
  'repo logs': {
    form: 'single',
    fn: 'container_logs',
    lock: 'read',
    timeout: '10m',
    box: 'J16',
    exception: 'the -f form streams to the terminal (section 24)',
  },
  'repo merge': {
    form: 'precondition',
    fn: 'repository_merge',
    lock: 'repo-exclusive',
    timeout: '10m',
    box: 'J16',
    steps: ['advanceHeadCommit'],
  },
  'repo policy get': {
    form: 'single',
    fn: 'repository_policy_get',
    lock: 'read',
    timeout: '10m',
    box: 'J16',
    steps: ['renderPolicyResult'],
  },
  'repo policy set': {
    form: 'precondition',
    fn: 'repository_policy_set',
    lock: 'repo-exclusive',
    timeout: '10m',
    box: 'J16',
    steps: ['renderPolicyResult'],
  },
  'repo promote': {
    form: 'precondition',
    fn: 'repository_promote',
    lock: 'repo-exclusive',
    timeout: '10m',
    box: 'J16',
    steps: ['reconcileBackupSchedules'],
  },
  'repo prune': {
    form: 'compound',
    fn: 'repository_docker_prune',
    lock: 'repo-exclusive',
    lockWithoutRepo: 'machine-shared',
    timeout: '24h',
    box: 'J16',
    steps: ['renderRepoPrune'],
    note: 'single with a ref; the machine survey is a chain over repository_list',
  },
  'repo replicate': {
    form: 'compound',
    fn: 'datastore_fork',
    lock: 'machine-exclusive',
    timeout: '24h',
    box: 'J16',
    steps: ['recordReplicaSet'],
    note: 'per replica a datastore chain on several machines, then kube_apply',
  },
  'repo replicate refresh': {
    form: 'compound',
    fn: 'datastore_snapshot_create',
    lock: 'machine-exclusive',
    timeout: '24h',
    box: 'J16',
    steps: ['recordReplicaSet'],
  },
  'repo replicate remove': {
    form: 'compound',
    fn: 'datastore_snapshot_delete',
    lock: 'machine-exclusive',
    timeout: '24h',
    box: 'J16',
    steps: ['forgetReplicaSet'],
  },
  'repo resize': {
    form: 'precondition',
    fn: 'repository_resize',
    lock: 'repo-exclusive',
    timeout: '24h',
    box: 'J16',
  },
  'repo status': {
    form: 'single',
    fn: 'repository_status',
    lock: 'read',
    timeout: '10m',
    box: 'J16',
    steps: ['printRepoStatus'],
  },
  'repo trim': {
    form: 'single',
    fn: 'repository_trim',
    lock: 'repo-exclusive',
    lockWithoutRepo: 'machine-shared',
    timeout: '24h',
    box: 'J16',
    steps: ['renderRepoTrim'],
  },

  // J17: backup verbs outside J4.
  'backup browse': {
    form: 'precondition',
    fn: 'backup_browse',
    lock: 'read',
    timeout: '10m',
    box: 'J17',
    steps: ['renderBackupBrowse'],
    note: '--at runs backup_browse_at; exit 18 (no listing) is a code the ticket keeps',
  },
  'backup cancel': {
    form: 'command-kind',
    fn: 'backup-cancel',
    lock: 'control',
    timeout: '10m',
    box: 'J17',
  },
  'backup list': {
    form: 'single',
    fn: 'backup_list',
    lock: 'read',
    timeout: '10m',
    box: 'J17',
    steps: ['renderBackupList'],
  },
  'backup run': {
    form: 'command-kind',
    fn: 'backup-unit',
    lock: 'machine-shared',
    timeout: '24h',
    box: 'J17',
    note: 'seedStrategyRetention runs before the job; backup-unit takes a units list (J0b finding 7)',
  },
  'backup schedule': {
    form: 'command-kind',
    lock: 'machine-exclusive',
    lockGap: { runs: 'backup-unit', overlap: 'machine-shared' },
    timeout: '10m',
    box: 'J17',
    steps: ['seedStrategyRetention', 'warnIfConfigStorageUnenrolled'],
    note: `${NEW_KIND}; the license refresh inside it is HTTP between two machine phases (J0b finding 3)`,
  },
  'backup status': {
    form: 'command-kind',
    lock: 'read',
    lockFrom: 'backup-status',
    timeout: '10m',
    box: 'J17',
    steps: ['renderBackupStatus'],
    note: NEW_KIND,
  },

  // J18: machine verbs.
  'config reconcile': {
    form: 'command-kind',
    fn: 'list-all',
    lock: 'read',
    timeout: '10m',
    box: 'J18',
    steps: ['reconcileConfigState'],
    note: 'one list-all job per machine under one group; the command stays exempt from the proxy',
  },
  'machine converge': {
    form: 'single',
    fn: 'machine_converge_runtime',
    lock: 'machine-exclusive',
    timeout: '24h',
    box: 'J18',
    steps: ['settleConverge', 'settleConvergeFailed'],
  },
  'machine gpu list': {
    form: 'single',
    fn: 'machine_gpu_list',
    lock: 'read',
    timeout: '10m',
    box: 'J18',
    steps: ['renderGpuList'],
  },
  'machine health': {
    form: 'command-kind',
    fn: 'list-all',
    lock: 'read',
    timeout: '10m',
    box: 'J18',
    steps: ['renderMachineHealth'],
    note: 'the stale-process probe folds into the list-all payload',
  },
  'machine infra push': {
    form: 'compound',
    lock: 'machine-exclusive',
    lockGap: { runs: 'infra-push', overlap: 'read' },
    timeout: '10m',
    box: 'J18',
    steps: ['ensureMachineDns'],
    note: `${NEW_KIND}; the cert-cache upload runs before the job`,
  },
  'machine provision': {
    form: 'successor',
    fn: 'setup',
    lock: 'machine-exclusive',
    timeout: '24h',
    box: 'J18',
    steps: ['setMachineInfra'],
    exception: 'the tofu legs stay local (section 24)',
    note: 'infra push is the successor and carries no secret (J0b finding 2); addMachine and knownHosts precede the job, which needs the machine record to connect',
  },
  'machine prune': {
    form: 'compound',
    fn: 'network_prune',
    lock: 'machine-exclusive',
    timeout: '10m',
    box: 'J18',
    steps: ['cleanupSshArtifacts', 'purgeExpiredArchives', 'renderPruneOutcome'],
    note: 'repository_prune then network_prune; the orphaned and unknown forms need the config GUID set in the vault (J0b finding 9)',
  },
  'machine restart-services': {
    form: 'command-kind',
    lock: 'machine-exclusive',
    lockFrom: 'daemons-restart',
    timeout: '24h',
    box: 'J18',
    steps: ['renderRestartServices'],
    note: `${NEW_KIND} (daemons-restart)`,
  },
  'machine setup': {
    form: 'successor',
    fn: 'setup',
    lock: 'machine-exclusive',
    timeout: '24h',
    box: 'J18',
    steps: ['postSetupMachineTasks'],
    note: 'the bootstrap upload runs before the job; the converge pass is a recorded successor',
  },
  'machine status': {
    form: 'command-kind',
    fn: 'list-all',
    lock: 'read',
    timeout: '10m',
    box: 'J18',
    steps: ['renderMachineStatus'],
    note: 'license and stale-process reads fold into the list-all payload',
  },

  // J19: datastore and cluster verbs.
  'cluster create': {
    form: 'compound',
    fn: 'kube_install',
    lock: 'machine-exclusive',
    timeout: '24h',
    box: 'J19',
    steps: ['updateClusterRecord', 'materializeClusterMachines', 'recordClusterAudit'],
    exception: 'the tofu or KVM legs stay local (section 24)',
    note: CHAIN,
  },
  'cluster evict': {
    form: 'compound',
    fn: 'kube_node_remove',
    lock: 'machine-exclusive',
    timeout: '24h',
    box: 'J19',
    steps: ['updateMachineCluster', 'recordClusterAudit'],
  },
  'cluster fork': {
    form: 'compound',
    fn: 'datastore_fork',
    lock: 'machine-exclusive',
    timeout: '24h',
    box: 'J19',
    steps: ['recordClusterAudit'],
    note: `${CHAIN}; the discard of a partial fork makes machine calls, so it is not a client step`,
  },
  'cluster join': {
    form: 'compound',
    fn: 'kube_join',
    lock: 'machine-exclusive',
    timeout: '24h',
    box: 'J19',
    steps: ['updateMachineCluster', 'recordClusterAudit'],
    note: 'kube_join consumes the kube_join_token output',
  },
  'cluster migrate': {
    form: 'compound',
    fn: 'datastore_attach',
    lock: 'machine-exclusive',
    timeout: '24h',
    box: 'J19',
    steps: ['recordClusterAudit'],
    note: `${CHAIN}; rollbackMigrateToSource makes machine calls, so it is not a client step`,
  },
  'cluster rehearse': {
    form: 'compound',
    fn: 'datastore_fork',
    lock: 'machine-exclusive',
    timeout: '24h',
    box: 'J19',
    note: `${CHAIN}; the teardown on both outcomes makes machine calls, so it is not a client step`,
  },
  'cluster scale': {
    form: 'compound',
    fn: 'kube_join',
    lock: 'machine-exclusive',
    timeout: '24h',
    box: 'J19',
    steps: ['updateClusterRecord', 'removeClusterMembers', 'recordClusterAudit'],
    exception: 'the tofu or KVM legs stay local (section 24)',
    note: 'shrink runs kube_prep_fork and kube_node_remove',
  },
  'cluster snapshot create': {
    form: 'precondition',
    fn: 'datastore_snapshot_create',
    lock: 'machine-exclusive',
    timeout: '24h',
    box: 'J19',
    steps: ['reportClusterSnapshot'],
  },
  'cluster snapshot list': {
    form: 'single',
    fn: 'datastore_snapshot_list',
    lock: 'read',
    timeout: '10m',
    box: 'J19',
    steps: ['printCapturedJson'],
  },
  'datastore attach': {
    form: 'compound',
    fn: 'datastore_attach',
    lock: 'machine-exclusive',
    timeout: '24h',
    box: 'J19',
    steps: ['setDatastoreState'],
    note: 'the relocation form alternates machines and feeds the source record to datastore_adopt',
  },
  'datastore create': {
    form: 'single',
    fn: 'datastore_create',
    lock: 'machine-exclusive',
    timeout: '24h',
    box: 'J19',
    steps: ['recordDatastore'],
  },
  'datastore delete': {
    form: 'compound',
    fn: 'datastore_delete',
    lock: 'machine-exclusive',
    timeout: '24h',
    box: 'J19',
    steps: ['forgetDatastore'],
    note: 'datastore_detach then datastore_delete on one host',
  },
  'datastore detach': {
    form: 'single',
    fn: 'datastore_detach',
    lock: 'machine-exclusive',
    timeout: '24h',
    box: 'J19',
    steps: ['setDatastoreState', 'forgetDatastore'],
  },
  'datastore fork': {
    form: 'successor',
    fn: 'datastore_fork',
    lock: 'machine-exclusive',
    timeout: '24h',
    box: 'J19',
    steps: ['recordDatastore', 'setDatastoreState'],
    note: '--attach-to records datastore_attach on the second machine as the successor',
  },
  'datastore resize': {
    form: 'single',
    fn: 'datastore_resize',
    lock: 'machine-exclusive',
    timeout: '24h',
    box: 'J19',
    steps: ['recordDatastore'],
  },
  'datastore snapshot create': {
    form: 'single',
    fn: 'datastore_snapshot_create',
    lock: 'machine-exclusive',
    timeout: '24h',
    box: 'J19',
  },
  'datastore snapshot list': {
    form: 'single',
    fn: 'datastore_snapshot_list',
    lock: 'read',
    timeout: '10m',
    box: 'J19',
    steps: ['printCapturedJson'],
  },
  'datastore status': {
    form: 'single',
    fn: 'datastore_status',
    lock: 'read',
    timeout: '10m',
    box: 'J19',
    steps: ['renderDatastoreStatus'],
  },

  // J20: subscription verbs.
  'subscription refresh': {
    form: 'compound',
    lock: 'machine-exclusive',
    lockGap: { runs: 'license-refresh', overlap: 'read' },
    timeout: '10m',
    box: 'J20',
    steps: ['renderSubscriptionRefresh'],
    note: 'a machine read, an account HTTP issue, then a machine write: a job, a client step and a successor job (J0b finding 3); --repo is repo-exclusive',
  },
  'subscription status': {
    form: 'command-kind',
    lock: 'read',
    lockGap: { runs: 'license-status', overlap: 'read' },
    timeout: '10m',
    box: 'J20',
    steps: ['renderSubscriptionStatus'],
    note: `${NEW_KIND} (license-status)`,
  },
};

const SPOOL = 'drives the job spool itself (section 24)';
const INTERACTIVE = 'interactive: needs the local terminal (section 24)';
const LOCAL_SYNC = 'client rsync between the local filesystem and the machine (section 24)';
const NO_RENET =
  'makes no renet call, so there is nothing to run as a job (section 24 not-proxyable row)';

/** Machine-plane commands that do not become jobs, each with its section 24 reason. */
export const JOB_EXCEPTIONS: Readonly<Record<string, string>> = {
  'job cancel': SPOOL,
  'job gc': SPOOL,
  'job list': SPOOL,
  'job logs': SPOOL,
  'job status': SPOOL,
  'job wait': SPOOL,
  'backup download': LOCAL_SYNC,
  'backup upload': LOCAL_SYNC,
  'repo sync download': LOCAL_SYNC,
  'repo sync status': LOCAL_SYNC,
  'repo sync upload': LOCAL_SYNC,
  'repo tunnel': INTERACTIVE,
  'term connect': INTERACTIVE,
  'vscode connect': INTERACTIVE,
  serve: 'the executor daemon itself (section 24)',
  'vscode serve status':
    'runs a script as the repo user, not root, and a job runs as a root unit (J0b finding 9)',
  'vscode serve stop':
    'runs a script as the repo user, not root, and a job runs as a root unit (J0b finding 9)',
  'cluster destroy':
    'local tofu or KVM teardown and HTTP only, with no SSH leg (section 24 tofu row)',
  'cluster kubeconfig': NO_RENET,
  'machine access push': NO_RENET,
  'machine infra cert pull': NO_RENET,
  'machine infra cert push':
    'one raw write of a local file with no renet call (J0b, proposed; the alternative is a cert-write allow-list entry)',
  'machine deprovision': 'local tofu destroy and config removal, with no SSH leg (J0b finding 6)',
  'machine scan-keys':
    'local ssh-keyscan; the config write is the command (section 24 not-proxyable row)',
  'datastore list': 'reads config and state only, with no machine call',
};

/**
 * The verbs whose conversion box has landed. A verb joins this set in the change that converts it, and the same
 * change removes it from BACKGROUND_UNSAFE (packages/cli/src/services/executor/proxy-command.ts); the J22 invariant
 * test refuses a verb in both.
 */
export const CONVERTED: ReadonlySet<string> = new Set<string>([
  // J4: each runs its main call through runCommandJob, with its follow-up code as ticket steps.
  'backup restore',
  'backup snapshot',
  'backup verify',
  'repo checkout',
  'repo commit',
  'repo down',
  'repo fork',
  'repo migrate',
  'repo pull',
  'repo push',
  'repo up',
]);
