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

import { MACHINE_JOB_PLANS } from './plans-machine.js';
import { REPO_JOB_PLANS } from './plans-repo.js';
import type { JobPlan } from './plans-types.js';

export {
  type ConversionBox,
  type JobForm,
  type JobPlan,
  LOCK_CLASSES,
  type LockClass,
  TIMEOUT_CLASSES,
  type TimeoutClass,
} from './plans-types.js';

export const JOB_PLANS: Readonly<Record<string, JobPlan>> = {
  ...REPO_JOB_PLANS,
  ...MACHINE_JOB_PLANS,
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
  // J16: repo create is one job; its rollback, identity refresh and schedule re-render are steps.
  'repo create',
  'repo down',
  'repo fork',
  'repo migrate',
  'repo pull',
  'repo push',
  'repo up',
]);
