/**
 * The curated tables the contract generator reads: which commands a remote executor or `--background`
 * refuses and why, the refusal texts shared by a class of commands, and how a positional's name maps
 * to a kind (split out of generate-cli-contract.ts to keep it within the file size budget).
 */

import type { PositionalKind } from '../../../shared/src/cli-contract/types.js';

/**
 * Machine-plane commands a remote executor must never run for the caller, and
 * why. Each reason is user-facing: the CLI prints it when `--proxy` refuses the
 * command, so it must say what the operator should do instead.
 *
 * Two distinct classes end up here.
 *
 * 1. Client-side transfer: the file paths exist only on the operator's own
 *    disk, so an executor could not see them. (This is NOT the same as building
 *    params from a local file: `repo template apply --file` reads the file and
 *    base64s the bytes INTO the renet params, which crosses the wire fine and
 *    stays proxyable.)
 *
 * 2. Local effect: the command reaches a machine, but its whole point is to
 *    write what it found back into the CALLER's config or filesystem. A remote
 *    executor would write it into its own, and the caller would be none the
 *    wiser. The wire carries params and events, not config mutations.
 */
export const PROXY_EXCLUSIONS: Record<string, string> = {
  // ── Client-side transfer ──────────────────────────────────────────────
  'repo sync upload':
    'Uploads from the local filesystem with rsync/SFTP; a remote executor cannot see the source paths. Run it without --proxy.',
  'repo sync download':
    'Downloads to the local filesystem with rsync/SFTP; a remote executor would write the files onto its own disk. Run it without --proxy.',
  // Registered as a dry-run download: it still shells out to a client-side rsync that diffs against the operator's local tree.
  'repo sync status':
    'Diffs the machine against the local filesystem with a client-side rsync; a remote executor has no copy of the local tree. Run it without --proxy.',
  'backup download':
    'Copies the repository image to a local directory with a client-side rsync; a remote executor would write the image onto its own disk. Run it without --proxy.',
  'backup upload':
    'Sends a local image file with a client-side rsync and registers the repository in the local config; a remote executor cannot see the file. Run it without --proxy.',

  // ── The operator's credential ─────────────────────────────────────────
  'backup churn':
    'a client-side loop of probes that can run for hours, and it must forget its base when it ends',

  // ── Local effect ──────────────────────────────────────────────────────
  'machine infra cert pull':
    "Its effect is writing the machine's acme.json into the caller's local config; a remote executor would write it into its own. Run it without --proxy.",
  'cluster kubeconfig':
    'Caches the kubeconfig to a local 0600 file and prints that path; a remote executor would write the file onto its own disk. Run it without --proxy.',
  'machine access push':
    "Rewrites who may log in to the machine from the CALLER's access keys; an executor never rewrites the access it connects with, and it would push its own config's keys. Run it without --proxy.",

  // ── The install record and child processes on the caller's machine ─────
  'server status':
    "Finds the server through the caller's local install record; a remote executor holds none. Run it without --proxy.",
  'server upgrade':
    "Drives child commands and the caller's local install record (and --local-image, the caller's Docker); a remote executor would act from its own. Run it without --proxy.",
  'server backup':
    "Writes the recovery bundle (the server's keys) to the caller's terminal or file; through an executor the keys would cross another machine. Run it without --proxy.",
  'server bundle':
    "Runs the caller's local docker (pull and save) and writes the bundle to the caller's disk; a remote executor would write it to its own. Run it without --proxy.",
  'server licence mint':
    "Mints the certificate with the caller's login and writes it to the caller's file; a remote executor holds neither. Run it without --proxy.",
  'server licence':
    "Mints the certificate with the caller's login and records it in the caller's local install record; a remote executor holds neither. Run it without --proxy.",

  // ── The caller's config set ───────────────────────────────────────────
  'repo admin orphan list':
    "Judges each image against every config the CALLER can read; a remote executor would judge against its own configs and report the caller's repositories as orphans. Run it without --proxy.",
  'repo admin orphan delete':
    "Refuses a GUID any config the CALLER can read still names; a remote executor would check its own configs and could delete an image the caller's config names. Run it without --proxy.",
};

/**
 * Config-plane and `other`-plane commands the executor serves against the session config (PLAN-rmcp-local-mcp LM10, decision D57): each reads or writes only the config the request scope holds, or calls the account server with the session token, and so needs no machine. Every other non-machine command stays refused. None of them reaches a machine, so none is a machine job and `--background` refuses them.
 */
export const EXECUTOR_SERVED: Record<string, string> = {
  'backup immutability show':
    'Calls the account server with the session token the executor holds for the grant.',
  'backup manifests':
    'Calls the account server with the session token the executor holds for the grant.',
  'backup reconcile':
    'Calls the account server with the session token the executor holds for the grant.',
  'backup retention':
    'Calls the account server with the session token the executor holds for the grant.',
  'backup retention preview':
    'Calls the account server with the session token the executor holds for the grant.',
  'backup strategy list':
    'Reads the session config held by the request scope, never another config on the executor.',
  'backup strategy show':
    'Reads the session config held by the request scope, never another config on the executor.',
  'backup undelete':
    'Calls the account server with the session token the executor holds for the grant.',
  'backup usage':
    'Calls the account server with the session token the executor holds for the grant.',
  'cluster status':
    'Reads the session config held by the request scope, never another config on the executor.',
  'config access list':
    'Reads the session config held by the request scope, never another config on the executor.',
  'config prune':
    'Writes the session config through the request-scoped remote state, which pushes the change back to the store.',
  'config show':
    'Reads the session config held by the request scope, never another config on the executor.',
  credits: "Prints the credits bundled with the CLI build; nothing of the caller's is read.",
  'feedback list':
    'Calls the account server with the session token the executor holds for the grant.',
  'feedback report':
    'Calls the account server with the session token the executor holds for the grant.',
  'feedback show':
    'Calls the account server with the session token the executor holds for the grant.',
  legal:
    'Prints the bundled legal documents and reads the accepted terms from the account server with the session token.',
  'machine access show':
    'Reads the session config held by the request scope, never another config on the executor.',
  'machine add':
    'Writes the session config through the request-scoped remote state, which pushes the change back to the store.',
  'machine infra show':
    'Reads the session config held by the request scope, never another config on the executor.',
  'machine list':
    'Reads the session config held by the request scope, never another config on the executor.',
  'machine provider add':
    'Writes the session config through the request-scoped remote state, which pushes the change back to the store.',
  'machine provider list':
    'Reads the session config held by the request scope, never another config on the executor.',
  'machine provider remove':
    'Writes the session config through the request-scoped remote state, which pushes the change back to the store.',
  'machine remove':
    'Writes the session config through the request-scoped remote state, which pushes the change back to the store.',
  'repo replicate status':
    'Reads the session config held by the request scope, never another config on the executor.',
  'repo secret get':
    'Reads the session config held by the request scope, never another config on the executor.',
  'repo secret list':
    'Reads the session config held by the request scope, never another config on the executor.',
};

/**
 * Proxyable machine-plane commands that do NOT run as a machine job, keyed by
 * command path, with the reason (agent/plans/PLAN-detached-jobs.md section 24
 * and the J0b audit). Every other proxyable, non-`job` command is `detachable`:
 * its renet calls run as one machine job (section 14), and `--background`
 * returns the ticket at once.
 *
 * Each reason is user-facing: `--background` prints it when it refuses the
 * command (`detachBlockedReason` in the contract), so it says why and what to
 * run instead.
 */
export const DETACH_EXCLUSIONS: Record<string, string> = {
  'backup check':
    'Drives several renet calls from the operator side with a credential the config holds, so there is no single machine job to detach. Run it without --background.',
  'backup repair':
    'Drives several renet calls from the operator side with a token and credential the config holds, so there is no single machine job to detach. Run it without --background.',
  'backup toc-key sync':
    'Drives several renet calls from the operator side with a credential the config holds, so there is no single machine job to detach. Run it without --background.',
  'machine scan-keys':
    'Runs ssh-keyscan locally and writes the config, with no renet call to run as a job. Run it without --background.',
  'cluster destroy':
    'Tears the cluster down with local OpenTofu or ops calls and never reaches a machine over SSH, so there is no machine job to detach. Run it without --background.',
  'datastore list':
    'Reads the local config and state only and makes no machine call, so there is no machine job to detach. Run it without --background.',
  'machine deprovision':
    'Destroys the machine with local OpenTofu and has no SSH leg, so there is no machine job to detach. Run it without --background.',
  'machine infra cert push':
    'Writes the local certificate cache to the machine in one raw file write, with no renet call to run as a job. Run it without --background.',
  'vscode serve status':
    'Runs a script as the repository user, not as root, so it cannot run as a root job unit. Run it without --background.',
  'vscode serve stop':
    'Runs a script as the repository user, not as root, so it cannot run as a root job unit. Run it without --background.',
};

/**
 * What a positional token names, keyed by its argument name.
 *
 * The addressing grammar (docs/design/spec/03-cli-contracts.md §2.2) names each
 * noun's positional so that the NAME already signals the kind: a repo verb's
 * `<repo-ref>`, a datastore verb's `<datastore-ref>`, a file argument's
 * `<file>`. So the classifier keys on the argument name, with a couple of
 * domain refinements where the same bare name means different things.
 */
const POSITIONAL_KIND_BY_NAME: Record<string, PositionalKind> = {
  ref: 'repo-ref',
  'repo-ref': 'repo-ref',
  // Repo-ref aliases: some repo verbs name their positional by role for clarity (`repo fork <parent-ref>`, `repo promote <fork-ref>`, `repo checkout <commit-or-branch-ref>`, `repo merge --from <source-ref>`). They all name a repo, so they bind the console's repo picker exactly like `<ref>`.
  'parent-ref': 'repo-ref',
  'fork-ref': 'repo-ref',
  'commit-or-branch-ref': 'repo-ref',
  'source-ref': 'repo-ref',
  machine: 'machine',
  datastore: 'datastore-ref',
  'datastore-ref': 'datastore-ref',
  cluster: 'cluster',
  strategy: 'strategy',
  artifact: 'artifact-ref',
  'artifact-ref': 'artifact-ref',
  file: 'file',
  target: 'target',
  'job-id': 'job-id',
};

/**
 * What an argument name the table does not classify falls back to: a plain
 * free-text token, binding no console picker.
 */
const DEFAULT_POSITIONAL_KIND: PositionalKind = 'plain';

/**
 * Machine-domain commands whose `<name>` positional names a machine (or
 * provider) that does NOT exist yet, so it must NOT bind the console's machine
 * picker. Everything else on the `machine` domain named `name` references an
 * existing machine (see `classifyPositional`).
 */
const MACHINE_NAME_CREATORS = new Set<string>([
  'machine add',
  'machine provision',
  'machine provider add',
]);

export function classifyPositional(pathKey: string, domain: string, name: string): PositionalKind {
  // `rdc job status <job-id>` and `rdc job logs <job-id>` name the job; an `id`
  // argument on the `job` domain is the same thing under an older spelling.
  if (domain === 'job' && (name === 'id' || name === 'job-id')) return 'job-id';
  // `machine provider remove <name>` names an EXISTING configured provider, so the console can bind its provider picker to it. Path-aware on purpose: `machine provider add <name>` and `machine provision <name>` name NEW resources, so there is nothing to pick and they stay plain.
  if (pathKey === 'machine provider remove' && name === 'name') return 'provider';
  // A machine verb's `<name>` positional names an EXISTING configured machine (`machine status`, `health`, `deprovision`, `prune`, `remove`, `setup`, `scan-keys`), so the console can bind its machine picker to it and its container discovery / context / policy layers can resolve the machine from the ref. Same path-aware carve-out as `machine provider remove` above: the commands
  // below name a machine (or provider) that does NOT exist yet, so there is nothing to pick and they stay plain: `machine add` registers a brand-new machine under this name, `machine provision` provisions a brand-new cloud machine under this name, `machine provider add` names a new cloud PROVIDER, not a machine.
  if (domain === 'machine' && name === 'name' && !MACHINE_NAME_CREATORS.has(pathKey)) {
    return 'machine';
  }
  return POSITIONAL_KIND_BY_NAME[name] ?? DEFAULT_POSITIONAL_KIND;
}

/**
 * The refusal texts shared by every command of a class, keyed by their i18n key
 * under `commands.proxyBlocked.*`. A PROXY_EXCLUSIONS entry carries its own text
 * and is keyed by its camel-cased path (`proxyBlockedKeyFor`).
 */
export const GENERIC_PROXY_BLOCKED = {
  interactive:
    'Needs a terminal or never returns on its own (interactive shell, editor, tunnel, stream, or daemon), so a headless executor cannot run it. Run it without --proxy.',
  localConfig:
    'Runs entirely against the local config and never reaches a machine, so there is nothing to proxy. Run it without --proxy.',
  localTooling:
    'Local tooling that never reaches a machine, so there is nothing to proxy. Run it without --proxy.',
} as const;

/** The `--background` refusal of a command the executor serves without a machine (EXECUTOR_SERVED): there is no machine job to detach. */
export const GENERIC_DETACH_BLOCKED = {
  executorServed:
    'Runs against the config alone and reaches no machine, so there is no machine job to detach. Run it without --background.',
} as const;
