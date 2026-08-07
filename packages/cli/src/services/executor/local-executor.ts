/* eslint-disable max-lines */
/**
 * LocalExecutorService - Direct task execution via renet.
 *
 * This service enables the CLI to work directly with renet
 * over SSH, without any intermediate API.
 *
 * Uses direct SSH to the target machine and runs `renet execute --executor local`
 * which builds and executes the command locally on the machine (no double SSH).
 *
 * Delegates to shared utilities in renet-execution.ts.
 */

import { spawn } from 'node:child_process';
import * as fs from 'node:fs/promises';
import * as os from 'node:os';
import * as path from 'node:path';
import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
import { t } from '../../i18n/index.js';
import type { SFTPClient } from '../../remote/sftp/index.js';
import type { RepositoryConfig } from '../../types/index.js';
import { isAgentEnvironment } from '../../utils/agent-guard.js';
import { isDevBuild } from '../../utils/platform.js';
import { ValidationError } from '../../utils/errors.js';
import { CliExitError } from '../../utils/cli-exit-error.js';
import { formatDuration } from '../../utils/format.js';
import { shellQuote } from '../../utils/shell-quote.js';
import { startSpinner, stopSpinner } from '../../utils/spinner.js';
import { formatStepDuration, getActiveLabel, getDoneLabel } from '../../utils/timeline.js';
import {
  isDatastoreScopedId,
  issueRepoLicense,
  type RepoBatchRecoveryFailureMode,
  refreshRepoLicenseIdentity,
  refreshRepoLicensesBatch,
} from '../account/license.js';
import {
  isMachineSlotLimitError,
  machineSlotLimitMessage,
  readMachineSlotStatus,
} from '../account/license-preflight.js';
import { clusterKubeconfigRemotePath, namedDatastoreMount } from '../cluster/cluster-target.js';
import { configService } from '../config/config-resources.js';
import { auditService } from '../core/audit.js';
import { outputService } from '../core/output.js';
import { writeStderr, writeStdout } from '../core/request-context.js';
import { machineConnections } from '../machine/machine-connection.js';
import {
  buildLocalVault,
  getLocalRenetPath,
  provisionRenetToRemote,
  readOptionalSSHKey,
  readSSHKey,
  verifyMachineSetup,
} from '../renet/renet-execution.js';
import {
  isRepoProvisioningFunction,
  parseRenetLicenseFailure,
  RENET_LICENSE_REQUIRED_EXIT_CODE,
  type RenetLicenseFailure,
  usesTagAsProvisioningTarget,
} from '../renet/renet-license-contract.js';
import { cleanRelayLine, isLogrusLine, stripRelayPrefix } from './output-lines.js';
import { fetchOtlpCredentials } from '../telemetry/otlp-credentials.js';
import { isTelemetryDisabled, telemetryService } from '../telemetry/telemetry.js';

/** Run a step with spinner + timing. Shows "Loading..." then "✓ Loaded (1.2s)" on the same line. */
async function timedStep<T>(
  spinnerText: string,
  successKey: string,
  fn: () => Promise<T>
): Promise<T> {
  const start = Date.now();
  const spinner = startSpinner(spinnerText);
  try {
    const result = await fn();
    const successText = t(successKey, { duration: formatDuration(Date.now() - start) });
    if (spinner) {
      stopSpinner(true, successText);
    } else {
      outputService.info(successText);
    }
    return result;
  } catch (error) {
    if (spinner) stopSpinner(false);
    throw error;
  }
}

import { isRefreshDue, markRefreshAttempted } from '../account/license-refresh-state.js';
import { getSubscriptionTokenState } from '../account/subscription-auth.js';
import { resolveExtraMachines } from './extra-machines.js';
import {
  backgroundStartedHint,
  buildJobStartCommand,
  createJobOutputCollector,
  isJobCommandUnsupported,
  JobLogCursor,
  type JobOutputCollector,
  JobStartFailedError,
  jobStatusToExecuteResult,
  parseJobHandle,
  resumeHint,
  versionSkewWarning,
} from './job-client.js';
import { followJobLogs, readJobStatus, renderJobEvent } from './job-remote.js';
import type { ExecuteOptions, ExecuteResult, RenetEvent } from './types.js';

// ExecuteResult only. The other seam types are consumed from executor-factory,
// which is the entry point to this layer; re-exporting them here as well just
// gave callers two doors to the same room.
export type { ExecuteResult } from './types.js';

import { authorizeSubscriptionViaDeviceCode } from '../account/subscription-device-auth.js';

interface RepoLicenseContext {
  repositoryGuid: string;
  grandGuid?: string;
  kind: 'grand' | 'fork';
  requestedSizeGb: number;
  /**
   * Identity of the NAMED datastore the repo is being provisioned into, absent
   * when it lands on the machine's implicit default datastore. It scopes both
   * the signed payload and the on-machine store path, and it has to be resolved
   * BEFORE issuance because a pre-provisioning mint has no repo to scan.
   */
  datastoreId?: string;
  /**
   * Mount of the datastore holding the repo's image, from its recorded
   * placement. Carried so the post-create identity refresh measures the same
   * place the pre-issuance probe did, instead of falling back to the machine
   * default inside `refreshRepoLicenseIdentity`.
   */
  datastoreMount: string;
}

async function resolveKnownHosts(machineKnownHosts: string | undefined): Promise<string> {
  const hosts = machineKnownHosts ?? '';
  if (hosts) return hosts;
  const knownHostsPath = path.join(os.homedir(), '.ssh', 'known_hosts');
  return fs.readFile(knownHostsPath, 'utf-8').catch(() => '');
}

async function loadContextStorages(): Promise<
  Record<string, { vaultContent: Record<string, unknown> }> | undefined
> {
  try {
    const storageList = await configService.listStorages();
    if (storageList.length === 0) return undefined;
    const storages: Record<string, { vaultContent: Record<string, unknown> }> = {};
    for (const s of storageList) {
      storages[s.name] = { vaultContent: s.config.vaultContent };
    }
    return storages;
  } catch {
    return undefined;
  }
}

interface LoadedRepoEntry {
  guid: string;
  name: string;
  networkId?: number;
  secretFiles?: { name: string; value: string }[];
}

/**
 * Build a single LoadedRepoEntry. Extracts file-mode secrets only;
 * env-mode rides the shell prefix (resolveEnvSecrets), not the vault.
 */
function buildLoadedRepoEntry(name: string, config: RepositoryConfig): LoadedRepoEntry {
  const secretFiles: { name: string; value: string }[] = [];
  for (const [secretName, entry] of Object.entries(config.secrets ?? {})) {
    if (entry.mode === 'file') secretFiles.push({ name: secretName, value: entry.value });
  }
  return {
    guid: config.repositoryGuid,
    name,
    networkId: config.networkId,
    ...(secretFiles.length > 0 ? { secretFiles } : {}),
  };
}

async function loadContextRepositories(): Promise<{
  credentials: Record<string, string> | undefined;
  configs: Record<string, LoadedRepoEntry> | undefined;
}> {
  try {
    const repoList = await configService.listRepositories();
    if (repoList.length === 0) return { credentials: undefined, configs: undefined };
    const credentials: Record<string, string> = {};
    const configs: Record<string, LoadedRepoEntry> = {};
    for (const r of repoList) {
      if (r.config.credential) {
        credentials[r.config.repositoryGuid] = r.config.credential;
      }
      const entry = buildLoadedRepoEntry(r.name, r.config);
      configs[r.name] = entry;
      // Also add bare name alias for :latest repos so lookups by bare name work.
      // NOTE: Only handles the default ":latest" tag. If custom tags for grand repos
      // are supported in the future, commands should pass explicit guid/network_id
      // in params (which buildSingleRepoEntry uses as fallback).
      if (r.name.endsWith(':latest')) {
        const bareName = r.name.slice(0, -7);
        if (!(bareName in configs)) {
          configs[bareName] = entry;
        }
      }
    }
    return { credentials, configs };
  } catch {
    return { credentials: undefined, configs: undefined };
  }
}

function parseSizeToGb(size: string): number {
  const trimmed = size.trim().toUpperCase();
  const match = /^(\d+(?:\.\d+)?)([MGT])$/.exec(trimmed);
  if (!match) throw new Error(`Unsupported repository size: ${size}`);
  const value = Number(match[1]);
  const unit = match[2];
  if (unit === 'T') return Math.ceil(value * 1024);
  if (unit === 'G') return Math.ceil(value);
  return Math.max(1, Math.ceil(value / 1024));
}

/** The two fields this file needs from one `renet datastore list --json` row. */
interface RemoteDatastoreRow {
  name?: unknown;
  datastoreId?: unknown;
}

interface DatastoreScopeOptions {
  remoteRenetPath?: string;
  /**
   * Whether an unresolvable identity is fatal.
   *
   * True on the PRE-ISSUANCE path, where the identity is the only thing that
   * decides where a license nobody has minted yet will land, and a wrong guess
   * spends an activation on an unreadable blob. False on the POST-CREATE
   * refresh, where renet's own scan is the authority and this resolution is
   * only a fallback for a scan that cannot answer — refusing there would fail
   * an operation that has already succeeded.
   */
  required: boolean;
}

/**
 * The datastore identity a PRE-PROVISIONING repo license must carry, or
 * undefined when the repo lands on the machine's implicit default datastore.
 *
 * This is the one thing the pre-issuance path cannot learn the way every later
 * touch does. `refreshRepoLicenseIdentity` reads the identity out of renet's
 * own license scan, which walks repos that exist; here the repo is about to be
 * created and the scan is empty by construction. The DATASTORE, however, does
 * exist, and it is the thing that carries the identity — so we ask the machine
 * registry for it.
 *
 * Getting this wrong is expensive and silent, and it happened live: `repo
 * create --datastore <d>` minted the license (slot claimed, meter moved) and
 * wrote it to the unscoped `repos/<guid>/` path, while renet's create-tier
 * check for a datastore-resident repo reads ONLY
 * `datastores/<id>/repos/<guid>/` — a clean break, no dual read. renet exited
 * 10 LICENSE_REQUIRED and the repo rolled back, having spent an issuance on a
 * blob nothing would ever read.
 *
 * So an unresolvable identity FAILS THE CREATE instead of issuing unscoped and
 * hoping. Every attached plain datastore has an identity (renet lazy-mints one
 * at read-write attach, pkg/datastore identity_attach_test.go), so an empty or
 * malformed answer means the datastore's own identity is broken, and that is
 * worth a refusal the operator can act on rather than a burned slot. The
 * refusal costs nothing: it runs before issuance.
 *
 * The registry mirrors the on-datastore descriptor, which is authoritative and
 * travels with the bytes; attach refuses to mount a datastore whose two copies
 * disagree, so for an attached datastore (and a repo cannot be created into a
 * detached one) reading the registry is reading the descriptor.
 */
async function resolveProvisioningDatastoreId(
  repo: RepositoryConfig | null | undefined,
  sftp: SFTPClient,
  scope: DatastoreScopeOptions
): Promise<string | undefined> {
  const placement = repo?.placement;
  // The `{machine}` arm is the machine's implicit default datastore, which
  // carries no descriptor and therefore no identity: unscoped is CORRECT there,
  // and it is what renet reads. Same for a config that predates placement.
  if (!placement || !('datastore' in placement)) return undefined;

  const name = placement.datastore;
  const renetPath = scope.remoteRenetPath ?? DEFAULTS.CONTEXT.RENET_BINARY;
  const refuse = (reason: string): undefined => {
    if (!scope.required) return undefined;
    throw new ValidationError(unresolvedDatastoreIdMessage(name, reason));
  };

  let rows: RemoteDatastoreRow[];
  try {
    const parsed: unknown = JSON.parse(await sftp.exec(`sudo ${renetPath} datastore list --json`));
    if (!Array.isArray(parsed)) throw new Error('expected a JSON array of datastore records');
    rows = parsed as RemoteDatastoreRow[];
  } catch (error) {
    return refuse(
      `"${renetPath} datastore list --json" did not return a readable datastore registry ` +
        `(${error instanceof Error ? error.message : String(error)}).`
    );
  }

  const row = rows.find((r) => r.name === name);
  if (!row) {
    return refuse(`the machine's datastore registry has no entry named "${name}".`);
  }
  const datastoreId = typeof row.datastoreId === 'string' ? row.datastoreId : undefined;
  if (!isDatastoreScopedId(datastoreId)) {
    return refuse(
      `datastore "${name}" reports no usable identity (${JSON.stringify(row.datastoreId)}).`
    );
  }
  return datastoreId;
}

/** The refusal above, with the reason varying and the remedy fixed. */
function unresolvedDatastoreIdMessage(datastore: string, reason: string): string {
  return (
    `Cannot license a repository on datastore "${datastore}": ${reason} ` +
    `A repository in a named datastore is licensed under that datastore's identity, and ` +
    `issuing without it would spend an activation on a license the machine cannot read. ` +
    `Nothing was provisioned. Re-attach the datastore to mint its identity ` +
    `("rdc datastore attach ${datastore} --to <machine>"), then retry.`
  );
}

async function resolveRepoLicenseContext(
  functionName: string,
  machineName: string,
  params: Record<string, unknown>,
  sftp: SFTPClient,
  scope: DatastoreScopeOptions
): Promise<RepoLicenseContext | null> {
  const resolved = await resolveRepoLicenseInputs(functionName, machineName, params);
  if (!resolved) return null;
  const { repo, machine } = resolved;

  const datastoreMount = repoImageDatastoreMount(repo, machine);
  const requestedSizeGb = await resolveRequestedSizeGb(
    functionName,
    params,
    repo?.repositoryGuid,
    datastoreMount,
    sftp
  );
  if (requestedSizeGb === null) return null;

  // No identity proofs here, by construction. This context is only ever built
  // for provisioning verbs, whose target repo does not exist on disk yet, so
  // there is nothing to fingerprint; the proofs arrive afterwards, when
  // refreshRepoLicenseIdentity reissues from renet's own licence scan.
  //
  // A `stat`-based fingerprint used to be computed on this path and it was
  // dead code that was ALSO wrong: `storageFingerprint` is a signed payload
  // field whose exact bytes renet re-derives (pkg/license/identity.go,
  // `kind:size:mtime:mode` over Go's FileMode), and no `stat -c` format string
  // produces them. One producer of those bytes now, and it is renet's scan.
  //
  // The datastore identity is the exception, and it is resolved here rather
  // than scanned: see resolveProvisioningDatastoreId. For a tag-targeted verb
  // (fork, commit) the placement read is the SOURCE repo's, which is the right
  // one — a fork lands in the datastore its parent lives in, and placement is a
  // property of the family, not of the tag.
  const built = buildRepoLicenseContext(functionName, params, repo, requestedSizeGb);
  if (!built) return null;
  const ctx: RepoLicenseContext = { ...built, datastoreMount };
  const datastoreId = await resolveProvisioningDatastoreId(repo, sftp, scope);
  return datastoreId === undefined ? ctx : { ...ctx, datastoreId };
}

async function resolveRepoLicenseInputs(
  functionName: string,
  machineName: string,
  params: Record<string, unknown>
): Promise<{
  machine: Awaited<ReturnType<typeof configService.getLocalMachine>>;
  repo: Awaited<ReturnType<typeof configService.getRepository>> | null;
} | null> {
  if (!functionName.startsWith('repository_')) return null;
  const repoName = typeof params.repository === 'string' ? params.repository : '';
  // For a tag-targeted verb `params.repository` names the SOURCE, and the
  // licence target is `params.tag`; a missing source is not fatal here because
  // buildRepoLicenseContext decides what it can build without one.
  if (!repoName && !usesTagAsProvisioningTarget(functionName)) return null;
  // Try bare name first, then composite key (e.g., "my-app" → "my-app:latest")
  let repo = await configService.getRepository(repoName);
  if (!repo && !repoName.includes(':')) {
    repo = await configService.getRepository(`${repoName}:latest`);
  }
  const machine = await configService.getLocalMachine(machineName);
  if (!repo && !usesTagAsProvisioningTarget(functionName)) return null;
  return { repo, machine };
}

function buildRepoLicenseContext(
  functionName: string,
  params: Record<string, unknown>,
  repo: Awaited<ReturnType<typeof configService.getRepository>> | null,
  requestedSizeGb: number
): Omit<RepoLicenseContext, 'datastoreMount'> | null {
  // fork and commit both mint against `params.tag`, and both are derived
  // snapshots of the source repo rather than new lineages, so both are kind
  // 'fork' rooted at the source's grand. `repo commit` registers the commit
  // object with exactly that lineage (repo-branching.ts handleCommit sets
  // grandGuid: cfg.grandGuid ?? cfg.repositoryGuid), so the batch refresh path
  // classifies it the same way on every later touch.
  if (usesTagAsProvisioningTarget(functionName)) {
    const targetGuid = typeof params.tag === 'string' ? params.tag : '';
    if (!repo || !targetGuid) return null;
    return {
      repositoryGuid: targetGuid,
      grandGuid: repo.grandGuid ?? repo.repositoryGuid,
      kind: 'fork',
      requestedSizeGb,
    };
  }
  if (!repo) return null;
  return {
    repositoryGuid: repo.repositoryGuid,
    grandGuid: repo.grandGuid,
    kind: repo.grandGuid && repo.grandGuid !== repo.repositoryGuid ? 'fork' : 'grand',
    requestedSizeGb,
  };
}

/**
 * The datastore mount the repo's image actually lives under.
 *
 * The machine's default datastore is the answer ONLY for a `{machine}`
 * placement. A repo created with `repo create --datastore <d>` lives at
 * `/mnt/rediacc-ds/<d>/repositories/<guid>`, and reading the machine default
 * for it is the same #74 mistake the dispatch path made: the config records one
 * place and the machine is asked about another. It was still live here, on the
 * size probe below, and it failed SILENTLY rather than loudly — the stat found
 * nothing, the old `|| echo ${REPO_SIZE_PROBE_UNKNOWN}` turned that into 0 bytes, and every fork or
 * commit of a named-datastore repo was pre-issued a licence for the 1 GB floor
 * regardless of the repo's real size. Neither verb exposes `--size`, so that
 * estimate was not a fallback for them; it was the only number they ever sent.
 *
 * Placement is a property of the FAMILY, and the flat per-tag records carry a
 * copy of it (resource-state.ts flattening), so `repo.placement` answers for a
 * fork's parent as well — which is the repo this probe measures.
 */
function repoImageDatastoreMount(
  repo: RepositoryConfig | null | undefined,
  machine: Awaited<ReturnType<typeof configService.getLocalMachine>>
): string {
  const placement = repo?.placement;
  if (placement && 'datastore' in placement) return namedDatastoreMount(placement.datastore);
  return machine.datastore ?? NETWORK_DEFAULTS.DATASTORE_PATH;
}

/**
 * Printed by the size probe when `stat` could not answer. Deliberately not a
 * number: a failed probe and a real measurement must not be the same bytes.
 */
const REPO_SIZE_PROBE_UNKNOWN = 'rediacc-size-unknown';

/**
 * Floor for a licence size request. renet compares `requested > contract limit`,
 * so the floor never over-claims against a contract.
 */
const MIN_REQUESTED_SIZE_GB = 1;

async function resolveRequestedSizeGb(
  functionName: string,
  params: Record<string, unknown>,
  repositoryGuid: string | undefined,
  datastore: string,
  sftp: SFTPClient
): Promise<number | null> {
  if (typeof params.size === 'string' && params.size.trim()) {
    return parseSizeToGb(params.size);
  }
  // Sized from the PARENT image in every case, fork included: a fork has no
  // image of its own yet, and it starts as a reflink of its parent.
  if (!repositoryGuid) return null;
  const imagePath = `${datastore}/repositories/${repositoryGuid}`;
  // A sentinel, not `|| echo 0`. Under the old probe a stat that failed for ANY
  // reason — wrong datastore, unreadable mount, missing image — produced the
  // same bytes as a genuinely tiny image, and the caller then reported the 1 GB
  // floor with the confidence of a measurement. The sentinel keeps "we did not
  // measure" expressible, which is the whole point of the distinction.
  const probe = (
    await sftp.exec(
      `stat -c %s ${shellQuote(imagePath)} 2>/dev/null || echo ${REPO_SIZE_PROBE_UNKNOWN}`
    )
  ).trim();
  if (!/^\d+$/.test(probe)) {
    warnUnmeasuredRepoSize(functionName, imagePath);
    return MIN_REQUESTED_SIZE_GB;
  }
  return Math.max(
    MIN_REQUESTED_SIZE_GB,
    Math.ceil(Number.parseInt(probe, 10) / (1024 * 1024 * 1024))
  );
}

/**
 * Say out loud that the licence size is a floor rather than a measurement —
 * but only where the image was supposed to be there to measure.
 *
 * For `repository_create` the probe targets a repo that does not exist yet by
 * construction (the config record is written before renet runs), so an
 * unanswerable stat is the NORMAL case and warning on it would train the
 * operator to ignore this line. `repository_fork` and `repository_commit` take
 * their size from the SOURCE repo, which must already exist; there, an
 * unanswerable stat means the CLI looked in the wrong place or the machine
 * cannot read its own datastore, and both are worth a line on stderr.
 *
 * Warn rather than throw, deliberately: this runs on `repo fork`, `repo commit`
 * and their post-create identity refresh, and refusing on a probe that is only
 * ever an ESTIMATE would turn a cosmetic under-report into a failed
 * provisioning run. renet re-checks the real size against the contract on the
 * machine, so the floor cannot smuggle an over-limit repo past enforcement.
 */
function warnUnmeasuredRepoSize(functionName: string, imagePath: string): void {
  if (!usesTagAsProvisioningTarget(functionName)) return;
  outputService.warn(
    `Could not measure the source repository image at ${imagePath}, so its license is being ` +
      `requested at the ${MIN_REQUESTED_SIZE_GB} GB minimum instead of its real size. ` +
      `If this repository lives on a named datastore, check that its recorded placement ` +
      `matches where the image actually is ("rdc config reconcile").`
  );
}

/**
 * Service for executing tasks directly via renet subprocess.
 * Runs against a single machine over direct SSH.
 *
 * Uses direct SSH to the target machine and runs `renet execute --executor local`
 * with vault JSON piped via stdin. This avoids double-SSH (CLI→renet→machine).
 */
type StepEntry = { name: string; duration_ms: number; detail?: string };

/** Try to extract steps from a single parsed JSON object. */
function collectStepsFromParsed(parsed: Record<string, unknown>, steps: StepEntry[]): void {
  if (parsed.step_done && typeof parsed.step_done === 'object') {
    const step = parsed.step_done as StepEntry;
    if (step.name && typeof step.duration_ms === 'number') {
      steps.push(step);
    }
  }
  if (Array.isArray(parsed.steps) && parsed.steps.length > 0) {
    steps.push(...(parsed.steps as StepEntry[]));
  }
}

/** Extract step timing from renet's combined stdout+stderr output. */
function extractStepsFromOutput(output: string): StepEntry[] | undefined {
  const steps: StepEntry[] = [];

  for (const rawLine of output.split('\n')) {
    const line = rawLine.trim();
    const jsonStart = line.indexOf('{');
    if (jsonStart < 0) continue;
    try {
      const parsed = JSON.parse(line.slice(jsonStart)) as Record<string, unknown>;
      collectStepsFromParsed(parsed, steps);
    } catch {
      // Not valid JSON, continue
    }
  }

  return steps.length > 0 ? steps : undefined;
}

const MAX_FAILURE_REASON_CHARS = 300;

// Parser patterns for renet output lines — not user-facing strings.
const COBRA_ERROR_PREFIX = 'Error: ';
const LOGRUS_LINE_PREFIX = 'time="';

/**
 * Build the non-zero-exit error message, including renet's actual failure
 * reason when one is available. Without this the operator only sees
 * "renet exited with code 1" while the real cause ("repository X is not
 * mounted") sits unprinted in the captured output. The bridge relays the
 * inner command's streams into stdout (with a `[function] ` prefix) while
 * its own logrus noise lands in stderr, so the cobra "Error: ..." line is
 * searched across BOTH streams before any last-line fallback.
 */
function buildRenetExitError(exitCode: number, stderr: string, stdout: string): string {
  const base = `renet exited with code ${exitCode}`;
  const reason =
    extractErrorLine(stderr) ??
    extractErrorLine(stdout) ??
    lastInformativeLine(stderr) ??
    lastInformativeLine(stdout);
  return reason ? `${base}: ${capReason(reason)}` : base;
}

/**
 * Echo renet's full output to stderr on a non-capture failure, so the operator
 * sees the real reason rather than a bare exit code. Returns whether it echoed,
 * so failure renderers downstream do not repeat what was already printed.
 */
function echoRenetFailure(exitCode: number, combined: string, options: ExecuteOptions): boolean {
  if (exitCode === 0 || options.debug || options.captureOutput) return false;
  const output = combined.trim();
  if (!output) return false;
  process.stderr.write(`\n--- renet output (exit code ${exitCode}) ---\n`);
  process.stderr.write(`${output}\n`);
  process.stderr.write('---\n\n');
  return true;
}

/**
 * Surface renet's WARNINGS on a SUCCESSFUL run.
 *
 * renet's output is otherwise echoed only on failure (above) or under --debug, so a
 * command that succeeded while warning that it had silently skipped half its job said
 * nothing at all to the operator — which is how a datastore could report "attached"
 * while its CSI enablement had been skipped and every future PVC would hang Pending
 * (#86). A warning nobody can see is not a warning.
 *
 * Warnings are rare by construction (a full `cluster create` emits one), so this is not
 * a noise channel: renet uses log.Warn for "I did the thing, but you need to know
 * something", which is exactly what an operator must read.
 */
function surfaceRenetWarnings(exitCode: number, combined: string, options: ExecuteOptions): void {
  if (exitCode !== 0 || options.debug) return; // failures echo everything; debug already shows it
  for (const line of combined.split('\n')) {
    if (!line.includes('level=warning')) continue;
    // logrus renders the payload as msg="..."; fall back to the raw line if it does not.
    const msg = /msg="((?:[^"\\]|\\.)*)"/
      .exec(line)?.[1]
      ?.replaceAll('\\"', '"')
      .replaceAll('\\\\', '\\');
    outputService.warn(msg ?? line.trim());
  }
}

/**
 * Parse a JSON payload out of a captured bridge stdout. A bridge function that
 * SHELLS OUT to a sub-`renet` command (e.g. datastore_list ->
 * `renet datastore list --json`, ceph_client_config_export ->
 * `renet ceph client config export --json`) has its sub-process stdout RELAYED
 * by `renet functions once` with a `[function] ` line prefix, so the captured
 * `result.stdout` is `[datastore_list] [ ... ]`, not raw JSON — a plain
 * `JSON.parse` dies with `Unexpected token '['/'{'`. Strip the relay prefix per
 * line, then extract the JSON object/array payload (first `{`/`[` to its matching
 * last `}`/`]`), tolerating interleaved logrus lines outside the payload.
 * `cleanOutputLines` cannot be reused here — it deliberately DROPS JSON lines.
 *
 * The prefix strip matches ONLY a bridge-function relay prefix — `[<name>] ` with
 * `<name>` a snake_case identifier — never a JSON array. An earlier `[^\]]+`
 * strip ate a whole single-line array payload `[{...},{...}]` (whose only `]` is
 * the closing bracket), turning a valid `datastore list --json` capture into "no
 * JSON payload"; anchoring to an identifier fixes that (a JSON array's first char
 * after `[` is never an identifier char).
 */
export function parseCapturedJson<T>(stdout: string | undefined): T {
  const stripped = (stdout ?? '')
    .split('\n')
    .map(stripRelayPrefix)
    // Drop renet logrus lines (`time="..." level=... msg="..."`) BEFORE the
    // payload scan: their messages carry stray brackets (e.g. a "[detached]"
    // fork message) that would otherwise be mistaken for the start of a JSON
    // array. The JSON payload itself never matches this shape.
    .filter((line) => !isLogrusLine(line))
    .join('\n');
  const start = stripped.search(/[[{]/);
  if (start === -1) {
    throw new Error(`no JSON payload in captured output: ${(stdout ?? '').slice(0, 160)}`);
  }
  const close = stripped[start] === '{' ? '}' : ']';
  const end = stripped.lastIndexOf(close);
  if (end < start) {
    throw new Error(`unterminated JSON payload in captured output: ${stripped.slice(start, 160)}`);
  }
  return JSON.parse(stripped.slice(start, end + 1)) as T;
}

/** Strip bridge `[function] ` prefixes and drop empty lines and JSON
 * fragments (multi-line JSON yields lines starting with braces, brackets, or
 * quoted keys). The JSON-fragment drop is specific to failure-message
 * extraction and is why `cleanRelayLine` cannot simply replace this. */
function cleanOutputLines(output: string): string[] {
  return output
    .split('\n')
    .map((line) => stripRelayPrefix(line).trim())
    .filter((line) => line.length > 0 && !/^[{}\][",]/.test(line));
}

/** The last cobra-style "Error: ..." line, without the prefix. */
function extractErrorLine(output: string): string | undefined {
  return cleanOutputLines(output)
    .filter((line) => line.startsWith(COBRA_ERROR_PREFIX))
    .at(-1)
    ?.slice(COBRA_ERROR_PREFIX.length)
    .trim();
}

/** The last line that isn't structured-log noise (`time="..." level=...`). */
function lastInformativeLine(output: string): string | undefined {
  return cleanOutputLines(output)
    .filter((line) => !line.startsWith(LOGRUS_LINE_PREFIX))
    .at(-1);
}

function capReason(reason: string): string {
  return reason.length > MAX_FAILURE_REASON_CHARS
    ? `${reason.slice(0, MAX_FAILURE_REASON_CHARS)}…`
    : reason;
}

/**
 * A stdout sink. `flush` exists because the line-buffered handlers hold a
 * trailing partial line: a stream that ends without a final newline (a killed
 * `--follow`, a command whose last line has no `\n`) would otherwise drop it.
 */
type StdoutHandler = ((data: Buffer) => void) & { flush?: () => void };

/** Handle NDJSON events from renet in events mode. */
function handleEventsStdout(onEvent: (event: RenetEvent) => void): StdoutHandler {
  let lineBuffer = '';
  return (data: Buffer) => {
    lineBuffer += data.toString();
    const lines = lineBuffer.split('\n');
    lineBuffer = lines.pop() ?? '';
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      try {
        const event = JSON.parse(trimmed) as RenetEvent;
        onEvent(event);
      } catch {
        process.stdout.write(`${line}\n`);
      }
    }
  };
}

/**
 * Render real-time step events from a single parsed JSON object.
 *
 * `write` exists so passthrough commands can send progress to STDERR: for
 * `repo exec`/`repo logs` stdout is the command's data, and a `✔ Provisioning
 * renet (2.0s)` line landing in `$(rdc repo exec …)` is corruption, not progress.
 */
function renderStepEvent(
  parsed: Record<string, unknown>,
  write: (text: string) => void = (text) => void process.stdout.write(text)
): void {
  if (parsed.step_start && typeof parsed.step_start === 'object') {
    const s = parsed.step_start as { name?: string };
    if (s.name) write(`⠋ ${getActiveLabel(s.name)}...`);
  } else if (parsed.step_done && typeof parsed.step_done === 'object') {
    const s = parsed.step_done as { name?: string; duration_ms?: number };
    if (s.name && s.duration_ms != null) {
      write(`\r✔ ${getDoneLabel(s.name)} (${formatStepDuration(s.duration_ms)})\n`);
    }
  }
}

/** Handle stdout in non-events, non-capture mode: detect step events and render them. */
function handleStepDetectionStdout(): StdoutHandler {
  let stepLineBuffer = '';
  return (data: Buffer) => {
    stepLineBuffer += data.toString();
    const stepLines = stepLineBuffer.split('\n');
    stepLineBuffer = stepLines.pop() ?? '';
    for (const sl of stepLines) {
      const trimmed = sl.trim();
      const jsonIdx = trimmed.indexOf('{');
      if (jsonIdx < 0) continue;
      try {
        const p = JSON.parse(trimmed.slice(jsonIdx)) as Record<string, unknown>;
        renderStepEvent(p);
      } catch {
        /* not JSON, ignore */
      }
    }
  };
}

/**
 * Stream the inner process's own output live, minus renet's relay scaffolding.
 *
 * This is what makes `repo exec`, `repo logs` and `run -f` print anything at
 * all: the default handler below detects step events and DROPS every other
 * line, which is right for `repo up`/`fork`/`push` (renet's chatter is noise
 * there) and exactly wrong for the three verbs whose output is the answer.
 *
 * Line-buffered rather than accumulate-then-print, because `repo logs --follow`
 * must emit each line as it completes. Step-event lines are swallowed, not
 * printed: leaking a `{"step_done":...}` line would poison `$(rdc repo exec …)`.
 */
function handlePassthroughStdout(renderSteps: boolean): StdoutHandler {
  let lineBuffer = '';

  const emit = (line: string): void => {
    const trimmed = line.trim();
    const jsonIdx = trimmed.indexOf('{');
    if (jsonIdx >= 0) {
      try {
        const parsed = JSON.parse(trimmed.slice(jsonIdx)) as Record<string, unknown>;
        if (parsed.step_start || parsed.step_done) {
          // Progress to stderr, never stdout: stdout belongs to the command.
          if (renderSteps) renderStepEvent(parsed, writeStderr);
          return;
        }
      } catch {
        /* not a step event, fall through and print it */
      }
    }
    // writeStdout, not process.stdout: inside the MCP/serve dispatch context
    // this output belongs to ONE request's envelope, and writing to the process
    // stream would interleave concurrent tenants' command output.
    const cleaned = cleanRelayLine(line);
    if (cleaned !== undefined) writeStdout(`${cleaned}\n`);
  };

  const handler: StdoutHandler = (data: Buffer) => {
    lineBuffer += data.toString();
    const lines = lineBuffer.split('\n');
    lineBuffer = lines.pop() ?? '';
    for (const line of lines) emit(line);
  };
  handler.flush = () => {
    if (!lineBuffer) return;
    const tail = lineBuffer;
    lineBuffer = '';
    emit(tail);
  };
  return handler;
}

/** Create the appropriate stdout handler based on execution options. */
function createStdoutHandler(
  options: ExecuteOptions,
  collector?: JobOutputCollector
): StdoutHandler {
  if (collector) {
    // Events mode: parse the NDJSON, feed the collector so result.stdout is the
    // reconstructed text (not raw events) that parseCapturedJson expects, and
    // still forward each event to the caller's renderer when it set one.
    const render = options.onEvent;
    return handleEventsStdout((event) => {
      collector.consume(event);
      render?.(event);
    });
  }
  if (options.captureOutput) {
    return () => {};
  }
  if (options.debug) {
    return (data: Buffer) => process.stdout.write(data);
  }
  // Opt-in, per command: only the verbs whose output IS the answer ask for it,
  // so every other command keeps the step-detection handler unchanged.
  if (options.passthroughOutput) {
    return handlePassthroughStdout(!options.quietSpinners);
  }
  return handleStepDetectionStdout();
}

/**
 * POSIX single-quote a string for safe use as an argument inside a remote
 * shell command. Wraps in `'...'` and escapes embedded single quotes. Used
 * by `buildRemoteCommand` to inject OTLP credentials as env vars.
 */
/**
 * Build the `env K=V K=V ` prefix that carries telemetry state into a
 * renet subprocess launched over SSH. Shared by the `renet execute`
 * path (buildRemoteRenetCommand) and the `renet list all` path
 * (machine-status.ts) so both invocations get the same telemetry
 * handling — emit spans/metrics/logs when OTLP creds were fetched, or
 * go default-deny when the user opted out via CI / REDIACC_TELEMETRY_DISABLED.
 *
 * Returns a trailing-space string ready to splice into the command, or
 * an empty string when nothing needs to be injected.
 */
export function buildRenetEnvPrefix(params: {
  isDevelopment: boolean;
  telemetryDisabled: boolean;
  otlpCreds?: { user: string; pass: string } | null;
  /**
   * Per-repo env-mode secrets, already prefixed `REDIACC_SECRET_<NAME>`.
   * Renet's `propagateDevEnvVars` forwards this prefix into the bash
   * preamble, and the `renet compose --` wrapper interpolates them into
   * `${REDIACC_SECRET_*}` references in the user's compose YAML.
   */
  envSecrets?: Record<string, string>;
  /**
   * Remote KUBECONFIG path when the target is a cluster — the k8s analog of
   * DOCKER_HOST. The `renet kube` wrapper reads it to talk to the cluster.
   */
  kubeconfig?: string;
}): string {
  const { isDevelopment, telemetryDisabled, otlpCreds, envSecrets, kubeconfig } = params;
  const envParts: string[] = [];
  if (isDevelopment) {
    // REMOTE plane: this REDIACC_ENVIRONMENT travels to the renet process on
    // the machine, a different plane from the local CLI's dev signal. Keep the
    // name; the env-tombstone test allowlists this one literal.
    envParts.push('REDIACC_ENVIRONMENT=development');
  }
  if (kubeconfig) {
    envParts.push(`KUBECONFIG=${shellQuote(kubeconfig)}`);
  }
  if (telemetryDisabled) {
    // Propagate the opt-out to renet. When set, renet skips its OTel SDK
    // setup entirely (see pkg/telemetry/telemetry.go:disabled). We
    // deliberately do NOT pass OTLP creds in this branch — even if the
    // caller passed `otlpCreds`, ignoring them here matches the user's
    // intent to send zero telemetry from any process.
    envParts.push('REDIACC_TELEMETRY_DISABLED=1');
  } else if (otlpCreds) {
    envParts.push(`REDIACC_OTLP_USER=${shellQuote(otlpCreds.user)}`);
    envParts.push(`REDIACC_OTLP_PASS=${shellQuote(otlpCreds.pass)}`);
  }
  if (envSecrets) {
    for (const [k, v] of Object.entries(envSecrets)) {
      envParts.push(`${k}=${shellQuote(v)}`);
    }
  }
  return envParts.length > 0 ? `env ${envParts.join(' ')} ` : '';
}

/**
 * Build the `sudo env ... renet execute ...` command string that the CLI
 * executes over SSH on the target machine.
 *
 * Exported as a pure function so unit tests can exercise all combinations
 * of (telemetry disabled, OTLP creds present, events mode, dev environment)
 * without constructing a full LocalExecutorService with SFTP mocks.
 *
 * When `telemetryDisabled` is true, `REDIACC_TELEMETRY_DISABLED=1` is
 * injected INSTEAD OF OTLP credentials — the user's opt-out takes
 * precedence over any credentials the caller may have pre-fetched.
 */
export function buildRemoteRenetCommand(params: {
  remoteRenetPath: string;
  eventsMode?: boolean;
  isDevelopment: boolean;
  telemetryDisabled: boolean;
  otlpCreds?: { user: string; pass: string } | null;
  envSecrets?: Record<string, string>;
  kubeconfig?: string;
}): string {
  const { remoteRenetPath, eventsMode, ...envParams } = params;
  const eventsFlag = eventsMode ? ' --events' : '';
  const envPrefix = buildRenetEnvPrefix(envParams);
  return `sudo ${envPrefix}${remoteRenetPath} execute --executor local${eventsFlag}`;
}

/** Exit code reported when the operator detaches from a running job with Ctrl-C. */
const EXIT_DETACHED = 130;

/**
 * Whether a failed run is the kind that license recovery can retry: renet
 * refused for want of a repo license, and the caller has not opted out of
 * machine activation.
 */
/*
 * Exit 10 is NO LONGER UNIQUE to the license path. renet now re-raises a child
 * process's own exit code verbatim (cmd/renet/execute_command.go), so a
 * `repo exec ... -- sh -c 'exit 10'` reports 10 too. That makes the structured
 * payload parse at the call site LOAD-BEARING rather than merely defensive:
 * this predicate answers "could this be a license refusal", and only a parsed
 * LICENSE_REQUIRED payload confirms it. Do not act on this function alone.
 */
export function needsLicenseRecovery(result: ExecuteResult): boolean {
  return (
    !result.success &&
    result.exitCode === RENET_LICENSE_REQUIRED_EXIT_CODE &&
    process.env.REDIACC_SKIP_MACHINE_ACTIVATION !== '1'
  );
}

type LicenseIssuanceOutcome =
  | { kind: 'success' }
  | { kind: 'failure'; failureMode: RepoBatchRecoveryFailureMode; serverErrorSample?: string };

class LocalExecutorService {
  private async resolveLicenseFailure(
    result: ExecuteResult,
    failure: RenetLicenseFailure,
    options: ExecuteOptions,
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string,
    remoteRenetPath: string,
    sftp: SFTPClient,
    startTime: number
  ): Promise<ExecuteResult | null> {
    const guidance = this.resolveLicenseRecoveryGuidance(failure, options.machineName);
    if (guidance.failFastMessage) {
      return this.buildRecoveryFailureResult(
        result,
        guidance,
        guidance.failFastMessage,
        failure.reason,
        startTime
      );
    }
    try {
      await this.maybeOnboardSubscription(failure.reason);
    } catch (error) {
      return this.buildRecoveryFailureResult(
        result,
        guidance,
        error instanceof Error ? error.message : String(error),
        failure.reason,
        startTime
      );
    }
    const outcome = await this.maybeIssueLicense(
      options,
      machine,
      sshPrivateKey,
      remoteRenetPath,
      sftp
    );
    if (outcome.kind === 'success') {
      return null;
    }
    telemetryService.trackEvent('license_recovery_failed', {
      licenseRecoveryFailureMode: String(outcome.failureMode),
    });
    const recoveryGuidance = this.resolveLicenseRecoveryGuidance(
      failure,
      options.machineName,
      outcome
    );
    const recoveryFailedMsg = recoveryGuidance.recoveryFailedMessage;
    if (!recoveryFailedMsg) {
      return result;
    }
    return this.buildRecoveryFailureResult(
      result,
      recoveryGuidance,
      recoveryFailedMsg,
      failure.reason,
      startTime
    );
  }

  private buildRecoveryFailureResult(
    result: ExecuteResult,
    guidance: ReturnType<LocalExecutorService['resolveLicenseRecoveryGuidance']>,
    error: string,
    failureReason: string,
    startTime: number
  ): ExecuteResult {
    return {
      ...result,
      errorCode: guidance.errorCode,
      error,
      errorGuidance: guidance.guidance,
      licenseFailureReason: failureReason,
      durationMs: Date.now() - startTime,
    };
  }

  private async executeWithConnectedSftp(
    sftp: SFTPClient,
    options: ExecuteOptions,
    remoteRenetPath: string,
    vault: string,
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string,
    startTime: number
  ): Promise<ExecuteResult> {
    let result = await this.runOperation(
      sftp,
      options,
      remoteRenetPath,
      vault,
      machine,
      sshPrivateKey
    );
    const failure: RenetLicenseFailure | null = needsLicenseRecovery(result)
      ? parseRenetLicenseFailure(result.stderr, result.stdout)
      : null;
    if (failure) {
      const recovered = await this.resolveLicenseFailure(
        result,
        failure,
        options,
        machine,
        sshPrivateKey,
        remoteRenetPath,
        sftp,
        startTime
      );
      if (recovered === null) {
        // Recovery issued a license. Re-run: exit 10 means renet refused BEFORE
        // doing any work, so a second run cannot double-execute even a detached
        // job (a strictly weaker claim than startJob's version-skew fallback).
        result = await this.runOperation(
          sftp,
          options,
          remoteRenetPath,
          vault,
          machine,
          sshPrivateKey
        );
      } else {
        return recovered;
      }
    }

    if (result.success && !options.deferIdentityRefresh) {
      await this.maybeRefreshRepoIdentity(options, machine, sshPrivateKey, remoteRenetPath, sftp);
    }

    const operationDurationMs = result.operationDurationMs ?? result.durationMs;
    return {
      ...result,
      durationMs: Date.now() - startTime,
      operationDurationMs,
    };
  }

  /**
   * Run the operation once, detached when the caller asked for it and the
   * machine supports it, else synchronously. Both variants flow back through the
   * shared recovery, identity-refresh, and duration tail in
   * executeWithConnectedSftp, so a detached run is no longer a second code path
   * that silently skips license recovery (finding #33).
   */
  private async runOperation(
    sftp: SFTPClient,
    options: ExecuteOptions,
    remoteRenetPath: string,
    vault: string,
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string
  ): Promise<ExecuteResult> {
    if (options.detached) {
      const detached = await this.runDetachedExecution(
        remoteRenetPath,
        vault,
        options,
        machine,
        sshPrivateKey
      );
      // null means the machine's renet has no `job` command: fall back to sync.
      if (detached !== null) return detached;
    }
    return this.runRemoteExecution(sftp, remoteRenetPath, vault, options);
  }

  private async maybeIssueLicense(
    options: ExecuteOptions,
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string,
    remoteRenetPath: string,
    sftp: SFTPClient
  ): Promise<LicenseIssuanceOutcome> {
    // NOTE: recovery is deliberately NOT gated on any "is this function
    // licensed" predicate. There used to be one (isLicensedRenetFunction, with
    // a repository_up/down/delete deny-list); it is deleted, because it was a
    // hand-maintained second source of truth that had already drifted from
    // renet's tier map, and nothing consumed it but this comment.
    //
    // The reasoning it encoded still holds and is why nothing like it belongs
    // here: such a deny-list governs PRE-FLIGHT issuance, since operate-tier
    // ops do not issue a license before running. But this
    // method runs during RECOVERY, after renet has already reported
    // LICENSE_REQUIRED (reason=missing) for the repo on the target machine.
    // The repo image exists on disk there, so refreshRepoLicensesBatch can
    // scan it and issue. Skipping recovery for deny-listed functions is the
    // root cause of rediacc/console#482: `repo push --up` to a fresh machine
    // fails because the license was issued for the source, not the destination,
    // and the destination's repository_up recovery never tried to issue.

    // For provisioning verbs (create-tier, per renet's tier map), re-issue the
    // pre-provisioning repo license
    if (isRepoProvisioningFunction(options.functionName)) {
      try {
        await this.ensureRepoLicenseForProvisioning(
          options,
          machine,
          sshPrivateKey,
          remoteRenetPath,
          sftp
        );
        return { kind: 'success' };
      } catch (err) {
        telemetryService.trackError(err, { operation: 'executor.repo_license_recovery' });
        return {
          kind: 'failure',
          failureMode: 'server_rejected_all',
          serverErrorSample: err instanceof Error ? err.message : String(err),
        };
      }
    }
    // For all other licensed operations, batch refresh existing repo licenses
    const batchResult = await refreshRepoLicensesBatch(
      machine,
      sshPrivateKey,
      remoteRenetPath,
      sftp
    ).catch((err: unknown) => {
      telemetryService.trackError(err, { operation: 'executor.batch_refresh' });
      return {
        kind: 'failure' as const,
        failureMode: 'server_rejected_all' as const,
        serverErrorSample: String(err),
      };
    });
    if ('kind' in batchResult) {
      return batchResult;
    }
    if (batchResult.recoveryFailureMode === null) return { kind: 'success' };
    return {
      kind: 'failure',
      failureMode: batchResult.recoveryFailureMode,
      serverErrorSample: batchResult.serverErrorSample,
    };
  }

  /**
   * Opportunistically refresh repo licences on a machine we are already talking
   * to.
   *
   * Gated on a per-machine cooldown, NOT on whether the renet binary happened to
   * change. It used to run only `if (renetUploaded)`, which coupled licence
   * maintenance to binary churn: on a stable machine renet does not change for
   * weeks, so a daily-active operator got no refresh at all and licences drifted
   * toward expiry unattended. Binary version and licence age are unrelated.
   *
   * Best-effort throughout. A machine can never refresh its own licences (renet
   * only verifies them; issuance is CLI-side), so this is the only proactive
   * path — but it can only run where the operator's subscription token lives,
   * and it stays silent when there is none.
   */
  private async maybeRefreshRepoLicenses(
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    machineName: string,
    sshPrivateKey: string,
    remoteRenetPath: string,
    sftp: SFTPClient
  ): Promise<void> {
    // The ENTIRE body is best-effort. This runs on every machine-touching
    // command as a side-effect of doing something else, so nothing in here —
    // token lookup, local state IO, the network call — may surface as a failure
    // of the command the operator actually asked for.
    try {
      if (getSubscriptionTokenState().kind !== 'ready') return;

      if (!(await isRefreshDue(machineName))) return;
      // Marked before the attempt, not after: a refresh that throws must still
      // consume its cooldown slot, or an unreachable machine would be retried
      // on every single command.
      await markRefreshAttempted(machineName);

      const result = await refreshRepoLicensesBatch(machine, sshPrivateKey, remoteRenetPath, sftp);
      if (result.invalidSignatureDetected > 0) {
        const refreshed = result.issued + result.refreshed;
        if (refreshed > 0) {
          outputService.info(t('warnings.licenseSignatureRefreshed', { count: refreshed }));
        } else {
          outputService.warn(
            t('warnings.licenseSignatureRefreshFailed', {
              count: result.invalidSignatureDetected,
            })
          );
        }
      }
    } catch {
      // Non-blocking: license check failure should not prevent command execution
    }
  }

  private async maybeOnboardSubscription(reason: string): Promise<boolean> {
    if (reason !== 'missing') {
      return false;
    }
    const tokenState = getSubscriptionTokenState();
    if (tokenState.kind === 'ready') {
      return false;
    }
    if (isAgentEnvironment()) {
      throw new ValidationError(t('errors.subscription.tokenRequired'));
    }
    await authorizeSubscriptionViaDeviceCode(undefined, {
      interactive: process.stdin.isTTY && process.stdout.isTTY,
      announceIntro: true,
    });
    return true;
  }

  /**
   * Pre-flight for the repo-provisioning verbs (isRepoProvisioningFunction,
   * i.e. create-tier in renet's map: repository_create / repository_fork):
   * Ensure subscription token exists (trigger device-code auth if needed)
   * and pre-issue a repo license (without identity proofs since the repo
   * doesn't exist yet). The server enforces machine slot limits during
   * issuance. After creation, maybeRefreshRepoIdentity re-issues the
   * license with identity proofs.
   */
  private async ensureRepoLicenseForProvisioning(
    options: ExecuteOptions,
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string,
    remoteRenetPath: string,
    sftp?: SFTPClient
  ): Promise<void> {
    // Allow bypassing activation for nolicense/CI builds where no subscription server exists
    if (process.env.REDIACC_SKIP_MACHINE_ACTIVATION === '1') {
      return;
    }

    const tokenState = getSubscriptionTokenState();
    if (tokenState.kind !== 'ready') {
      if (isAgentEnvironment()) {
        throw new ValidationError(t('errors.subscription.tokenRequired'));
      }
      await authorizeSubscriptionViaDeviceCode(undefined, {
        interactive: process.stdin.isTTY && process.stdout.isTTY,
        announceIntro: true,
      });
    }

    const repoLicenseCtx = await resolveRepoLicenseContext(
      options.functionName,
      options.machineName,
      options.params ?? {},
      sftp!,
      { remoteRenetPath, required: true }
    );
    if (!repoLicenseCtx) {
      throw new Error(t('errors.subscription.activationFailed'));
    }

    const issued = await this.issueOrExplainSlotLimit(
      machine,
      sshPrivateKey,
      repoLicenseCtx,
      remoteRenetPath,
      sftp
    );
    if (!issued) {
      throw new Error(t('errors.subscription.activationFailed'));
    }
  }

  /**
   * Issue, and answer the server's machine-slot refusal in the same words the
   * pre-flight uses.
   *
   * A single-machine `repo create` never reaches the multi-machine pre-flight,
   * so this is where the wall is first seen for it. The raw server message says
   * the limit was reached; what the operator needs on top of that is that the
   * repository was NOT created and that a slot frees itself on the 5-hour
   * float, which is often the whole remedy.
   */
  private async issueOrExplainSlotLimit(
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string,
    repoLicenseCtx: RepoLicenseContext,
    remoteRenetPath: string,
    sftp?: SFTPClient
  ): Promise<boolean> {
    try {
      return await issueRepoLicense(
        machine,
        sshPrivateKey,
        {
          repositoryGuid: repoLicenseCtx.repositoryGuid,
          grandGuid: repoLicenseCtx.grandGuid,
          kind: repoLicenseCtx.kind,
          requestedSizeGb: repoLicenseCtx.requestedSizeGb,
          // Both halves of the scope, from one resolution: the server embeds it
          // in the signed payload and the writer puts the blob on the path
          // renet reads for this datastore. Sending one without the other is
          // how the license ends up somewhere nothing looks.
          datastoreId: repoLicenseCtx.datastoreId,
        },
        remoteRenetPath,
        sftp
      );
    } catch (error) {
      if (!isMachineSlotLimitError(error)) throw error;
      const slots = await readMachineSlotStatus();
      const detail = slots
        ? machineSlotLimitMessage({
            needed: 1,
            active: slots.activeMachineCount,
            max: slots.maxMachines,
          })
        : (error as Error).message;
      throw new ValidationError(`${detail} ${t('errors.license.nothingProvisioned')}`);
    }
  }

  private buildMissingLicenseMessage(
    outcome: { failureMode: RepoBatchRecoveryFailureMode; serverErrorSample?: string } | undefined,
    machineName: string
  ): string {
    const base = ((): string => {
      switch (outcome?.failureMode) {
        case 'token_not_ready':
          return t('errors.license.recoveryFailedTokenNotReady');
        case 'no_known_repos':
          return t('errors.license.recoveryFailedNoKnownRepos', { machine: machineName });
        case 'server_rejected_all': {
          const errorDetail = outcome.serverErrorSample ?? '';
          return t('errors.license.recoveryFailedServerRejected', {
            error: errorDetail,
            machine: machineName,
          });
        }
        default:
          return (
            `A repo license is required for this operation, and automatic issuance did not succeed. ` +
            `Run: rdc subscription refresh -m ${machineName}`
          );
      }
    })();
    // Name the dev/test escape here (read by needsLicenseRecovery): it has bitten
    // three agents who hit a license wall on a throwaway machine and did not know
    // they could bypass activation entirely.
    return `${base} ${t('errors.license.skipActivationHint')}`;
  }

  private resolveLicenseRecoveryGuidance(
    failure: RenetLicenseFailure,
    machineName: string,
    outcome?: { failureMode: RepoBatchRecoveryFailureMode; serverErrorSample?: string }
  ): {
    errorCode?: string;
    guidance?: string;
    failFastMessage?: string;
    recoveryFailedMessage?: string;
  } {
    switch (failure.reason) {
      case 'missing': {
        const recoveryFailedMessage = this.buildMissingLicenseMessage(outcome, machineName);
        return {
          errorCode: 'REPO_LICENSE_ISSUANCE_REQUIRED',
          guidance: `Issue repo licenses explicitly with: rdc subscription refresh -m ${machineName}`,
          recoveryFailedMessage,
        };
      }
      case 'expired':
        return {
          errorCode: 'REPO_LICENSE_REFRESH_REQUIRED',
          guidance: `Refresh repo licenses explicitly with: rdc subscription refresh -m ${machineName}`,
          recoveryFailedMessage:
            `The installed repo license must be refreshed before this operation can continue. ` +
            `Run: rdc subscription refresh -m ${machineName}`,
        };
      case 'machine_mismatch':
        return {
          errorCode: 'REPO_LICENSE_MACHINE_MISMATCH',
          guidance: `Reissue repo licenses from this machine context with: rdc subscription refresh -m ${machineName}`,
          failFastMessage:
            `The installed repo license belongs to a different machine. ` +
            `Reissue it from this machine context with: rdc subscription refresh -m ${machineName}`,
        };
      case 'repository_mismatch':
        return {
          errorCode: 'REPO_LICENSE_REPOSITORY_MISMATCH',
          guidance: `Refresh repo licenses explicitly with: rdc subscription refresh -m ${machineName}`,
          failFastMessage:
            `The installed repo license does not match the target repository. ` +
            `Refresh repo licenses explicitly with: rdc subscription refresh -m ${machineName}`,
        };
      case 'sequence_regression':
        return {
          errorCode: 'REPO_LICENSE_INTEGRITY_ERROR',
          guidance: `Replace the installed repo license with: rdc subscription refresh -m ${machineName}`,
          failFastMessage:
            `The installed repo license is older than the latest accepted sequence. ` +
            `Replace it with a newer repo license using: rdc subscription refresh -m ${machineName}`,
        };
      case 'invalid_signature':
        return {
          errorCode: 'REPO_LICENSE_INTEGRITY_ERROR',
          guidance: `Replace the installed repo license with: rdc subscription refresh -m ${machineName}`,
          failFastMessage:
            `The installed repo license could not be trusted. ` +
            `Replace it with a newly issued repo license using: rdc subscription refresh -m ${machineName}`,
        };
      case 'identity_mismatch':
        return {
          errorCode: 'REPO_LICENSE_IDENTITY_MISMATCH',
          guidance: `Reissue repo licenses with: rdc subscription refresh -m ${machineName}`,
          failFastMessage:
            `The repository identity does not match the installed repo license. ` +
            `Reissue repo licenses with: rdc subscription refresh -m ${machineName}`,
        };
      case 'cert_expired':
        return {
          errorCode: 'REPO_LICENSE_DELEGATION_CERT_EXPIRED',
          guidance: `Renew the on-prem delegation cert, then: rdc subscription refresh -m ${machineName}`,
          failFastMessage:
            `The on-prem delegation cert covering this license has expired. ` +
            `Renew it on the on-prem account server (auto-renew or the portal renew flow), ` +
            `then run: rdc subscription refresh -m ${machineName}`,
        };
      case 'cert_invalid':
        return {
          errorCode: 'REPO_LICENSE_DELEGATION_CERT_INVALID',
          guidance: `Fix the on-prem delegation cert, then: rdc subscription refresh -m ${machineName}`,
          failFastMessage:
            `The delegation cert attached to the installed repo license could not be trusted. ` +
            `Fix the on-prem cert, then reissue with: rdc subscription refresh -m ${machineName}`,
        };
      default:
        return {};
    }
  }

  private async maybeRefreshRepoIdentity(
    options: ExecuteOptions,
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string,
    remoteRenetPath: string,
    sftp: SFTPClient
  ): Promise<void> {
    if (process.env.REDIACC_SKIP_MACHINE_ACTIVATION === '1') return;
    if (!isRepoProvisioningFunction(options.functionName)) return;
    const repoLicense = await resolveRepoLicenseContext(
      options.functionName,
      options.machineName,
      options.params ?? {},
      sftp,
      { remoteRenetPath, required: false }
    );
    if (repoLicense) {
      await refreshRepoLicenseIdentity(machine, sshPrivateKey, repoLicense, remoteRenetPath, sftp);
    }
  }

  /**
   * Re-issue a repo license with identity proofs, for callers that ran a
   * create/fork with deferIdentityRefresh. Resolves the machine and SSH key
   * from the active config, reuses a pooled connection, and shares the SFTP
   * session with license issuance.
   */
  async refreshIdentityFor(
    functionName: string,
    machineName: string,
    params: Record<string, unknown>
  ): Promise<void> {
    if (process.env.REDIACC_SKIP_MACHINE_ACTIVATION === '1') return;
    const lease = await machineConnections.acquire(machineName);
    try {
      const repoLicense = await resolveRepoLicenseContext(
        functionName,
        machineName,
        params,
        lease.sftp,
        { required: false }
      );
      if (repoLicense) {
        await refreshRepoLicenseIdentity(
          lease.machine,
          lease.sshPrivateKey,
          repoLicense,
          undefined,
          lease.sftp
        );
      }
    } finally {
      lease.release();
    }
  }

  /**
   * Thin wrapper around `buildRemoteRenetCommand` that pulls the
   * environment-detection logic from the service instance. Kept as a
   * class method so call sites don't need to recompute `isDevelopment`
   * / `isTelemetryDisabled` themselves.
   */
  private buildRemoteCommand(
    remoteRenetPath: string,
    eventsMode?: boolean,
    otlpCreds?: { user: string; pass: string } | null,
    envSecrets?: Record<string, string>,
    kubeconfig?: string
  ): string {
    return buildRemoteRenetCommand({
      remoteRenetPath,
      eventsMode,
      isDevelopment: this.detectEnvironment() === 'development',
      telemetryDisabled: isTelemetryDisabled(),
      otlpCreds,
      envSecrets,
      kubeconfig,
    });
  }

  /**
   * Resolve env-mode per-repo secrets for the focal repository, prefixed
   * `REDIACC_SECRET_<NAME>`. Returns undefined when no repo is targeted.
   * File-mode secrets are out of band — they ride the vault stdin (Step 6),
   * not the shell prefix, so they never appear in `ps`.
   */
  private async resolveEnvSecrets(
    repoRef: string | undefined
  ): Promise<Record<string, string> | undefined> {
    if (!repoRef) return undefined;
    try {
      const repoConfig = await configService.getRepository(repoRef);
      const secrets = repoConfig?.secrets;
      if (!secrets) return undefined;
      const out: Record<string, string> = {};
      for (const [name, entry] of Object.entries(secrets)) {
        if (entry.mode === 'env') out[`REDIACC_SECRET_${name}`] = entry.value;
      }
      return Object.keys(out).length > 0 ? out : undefined;
    } catch {
      return undefined;
    }
  }

  private async runRemoteExecution(
    sftp: SFTPClient,
    remoteRenetPath: string,
    vault: string,
    options: ExecuteOptions
  ): Promise<ExecuteResult> {
    // Fetch OTLP credentials so renet inherits them as env vars and its
    // telemetry init picks them up. Skip the fetch entirely when telemetry
    // is opted out — no wasted network round-trip, no credentials in
    // memory to accidentally propagate downstream. `buildRemoteCommand`
    // still injects `REDIACC_TELEMETRY_DISABLED=1` for the remote end.
    const otlpCreds = isTelemetryDisabled() ? null : await fetchOtlpCredentials();
    const repoRef =
      typeof options.params?.repository === 'string' ? options.params.repository : undefined;
    const envSecrets = await this.resolveEnvSecrets(repoRef);
    const kubeconfig = options.kubeCluster
      ? clusterKubeconfigRemotePath(options.kubeCluster)
      : undefined;
    const command = this.buildRemoteCommand(
      remoteRenetPath,
      options.eventsMode,
      otlpCreds,
      envSecrets,
      kubeconfig
    );
    // Events mode streams NDJSON, not text. Reconstruct the real stdout from the
    // events (below) instead of accumulating the raw stream: handing an event
    // stream straight to parseCapturedJson is the pre-existing --proxy bug (#31).
    const collector = options.eventsMode ? createJobOutputCollector() : undefined;
    let stdout = '';
    let stderr = '';
    const stdoutHandler = createStdoutHandler(options, collector);
    // Renet routes diagnostics (lifecycle brackets, relayed sub-command
    // stderr) to ITS stderr so they can never interleave with parseable
    // stdout. Echo them live in interactive text mode — to OUR stderr, same
    // "stdout belongs to the command" rule as createStdoutHandler.
    const echoStderrLive = Boolean(!options.captureOutput && !options.eventsMode);
    const execStart = Date.now();
    const exitCode = await sftp.execStreaming(command, {
      stdin: vault,
      onStdout: (data) => {
        // Events mode reconstructs stdout from the parsed events (below), so the
        // raw NDJSON is only fed to the handler, never accumulated as text.
        if (!collector) stdout += data;
        stdoutHandler(data);
      },
      onStderr: (data) => {
        stderr += data;
        if (echoStderrLive) process.stderr.write(data);
      },
    });
    // Emit any final line that arrived without a trailing newline.
    stdoutHandler.flush?.();

    if (collector) stdout = collector.stdout;

    const combined = stdout + stderr;
    const renetDurationMatch = /operation completed.*?duration_ms=(\d+)/.exec(combined);
    const operationMs = renetDurationMatch
      ? Number.parseInt(renetDurationMatch[1], 10)
      : Date.now() - execStart;

    surfaceRenetWarnings(exitCode, combined, options);

    return {
      success: exitCode === 0,
      exitCode,
      error: exitCode === 0 ? undefined : buildRenetExitError(exitCode, stderr, stdout),
      durationMs: operationMs,
      stdout,
      stderr,
      outputEchoed: echoRenetFailure(exitCode, combined, options),
      steps: extractStepsFromOutput(combined),
    };
  }

  /**
   * Run an operation as a DETACHED renet job, so it survives this connection.
   *
   * Three phases: start the job and get its ID back, tail its event stream
   * (reconnecting and resuming if the network drops), then read its terminal
   * status and map that onto the same ExecuteResult a synchronous run produces.
   * The render path is byte-for-byte the same one `runRemoteExecution` uses, so
   * spinners and the step timeline behave identically. Under `follow: false`
   * (`--background`) it returns the moment the job starts, leaving the work
   * running on the machine.
   *
   * Returns null in exactly one case: the renet deployed on the machine is too
   * old to know the `job` command. That is a version-skew signal for the caller
   * to fall back to a synchronous run, and it is safe precisely because cobra
   * rejects an unknown command before running any work.
   */
  private async runDetachedExecution(
    remoteRenetPath: string,
    vault: string,
    options: ExecuteOptions,
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string
  ): Promise<ExecuteResult | null> {
    const startedAt = Date.now();

    // Every phase goes through the lease rather than a captured client, so a
    // connection that dies between phases is transparently re-established.
    const lease = await machineConnections.acquireFor(machine, sshPrivateKey);
    try {
      const handle = await this.startJob(await lease.ensure(), remoteRenetPath, vault, options);
      if (handle === null) return null; // version skew: caller falls back

      // Announce the job the instant it exists, before any event, so a serve
      // route can emit its kind:'job' line and a client can re-attach even if
      // the connection drops before the first event arrives.
      options.onJobStarted?.(handle.job_id);

      if (options.follow === false) {
        // Fire-and-forget (--background): hand back the id and how to catch up,
        // and return success without waiting for the job to finish.
        writeStdout(`${backgroundStartedHint(handle.job_id, options.machineName)}\n`);
        return {
          success: true,
          exitCode: 0,
          durationMs: Date.now() - startedAt,
          jobId: handle.job_id,
        };
      }

      // Follow through the SAME implementation `rdc job logs` uses, so a detached
      // run and a re-attached one render identically and share one
      // reconnect-and-resume path rather than two that can drift apart. The
      // collector captures the output unconditionally (the spool is always
      // NDJSON), independent of whether the caller wants it rendered.
      const cursor = new JobLogCursor();
      const collector = createJobOutputCollector();
      const render = options.onEvent ?? (options.captureOutput ? undefined : renderJobEvent);
      const interrupted = await followJobLogs(
        lease,
        remoteRenetPath,
        handle.job_id,
        {
          onEvent: (event, line) => {
            collector.consume(event);
            render?.(event, line);
          },
          debug: options.debug,
        },
        cursor
      );

      if (interrupted) {
        // The operator stopped WATCHING; the job keeps running. Cancelling here
        // would destroy a half-finished migration because someone hit Ctrl-C on
        // a scrolling log, which is the opposite of what a detached job is for.
        const hint = resumeHint(handle.job_id, options.machineName);
        writeStderr(`\n${hint}\n`);
        return {
          success: false,
          exitCode: EXIT_DETACHED,
          error: hint,
          durationMs: Date.now() - startedAt,
          outputEchoed: true,
        };
      }

      const status = await readJobStatus(await lease.ensure(), remoteRenetPath, handle.job_id);
      return jobStatusToExecuteResult(status, Date.now() - startedAt, collector);
    } finally {
      lease.release();
    }
  }

  /**
   * Start a detached job. Returns its handle, or null when the machine's renet
   * does not support detached jobs at all.
   *
   * The version-skew check is deliberately narrow: ONLY "unknown command" earns
   * a null. Any other failure throws, because a `job start` that failed AFTER
   * spawning the unit could already be doing the work, and falling back would
   * then run the operation a second time.
   */
  private async startJob(
    sftp: SFTPClient,
    remoteRenetPath: string,
    vault: string,
    options: ExecuteOptions
  ): Promise<{ job_id: string } | null> {
    const otlpCreds = isTelemetryDisabled() ? null : await fetchOtlpCredentials();
    const repoRef =
      typeof options.params?.repository === 'string' ? options.params.repository : undefined;
    const envSecrets = await this.resolveEnvSecrets(repoRef);
    const kubeconfig = options.kubeCluster
      ? clusterKubeconfigRemotePath(options.kubeCluster)
      : undefined;

    // The env prefix is load-bearing: `job start` snapshots the environment it
    // is handed into the job's spool, so `job run` (which systemd spawns with a
    // clean environment) can re-inject the repo's secrets and the OTLP creds.
    const command = buildJobStartCommand({
      remoteRenetPath,
      envPrefix: buildRenetEnvPrefix({
        isDevelopment: this.detectEnvironment() === 'development',
        telemetryDisabled: isTelemetryDisabled(),
        otlpCreds,
        envSecrets,
        kubeconfig,
      }),
      timeoutMs: options.timeout,
      debug: options.debug,
    });

    let stdout = '';
    let stderr = '';
    const exitCode = await sftp.execStreaming(command, {
      stdin: vault,
      onStdout: (data) => {
        stdout += data;
      },
      onStderr: (data) => {
        stderr += data;
      },
    });

    if (exitCode !== 0) {
      const combined = stdout + stderr;
      if (isJobCommandUnsupported(combined)) {
        outputService.warn(versionSkewWarning(options.machineName));
        return null;
      }
      throw new JobStartFailedError(options.machineName, capReason((stderr || stdout).trim()));
    }

    return parseJobHandle(stdout);
  }

  /**
   * Provision renet, verify machine setup, and handle pre-flight licensing.
   * Returns the remote renet path and whether the binary was uploaded.
   */
  private async provisionAndVerify(
    config: Awaited<ReturnType<typeof configService.getLocalConfig>>,
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string,
    options: ExecuteOptions,
    sftp: SFTPClient,
    cliSteps: { name: string; duration_ms: number; startedAtMs?: number }[],
    quiet: boolean
  ): Promise<{ remoteRenetPath: string; renetUploaded: boolean }> {
    const provStart = Date.now();
    const provisionFn = () => provisionRenetToRemote(config, machine, sshPrivateKey, options, sftp);
    const { remotePath: remoteRenetPath, uploaded: renetUploaded } = quiet
      ? await provisionFn()
      : await timedStep(t('timing.step.provisioning'), 'timing.step.renetProvisioned', provisionFn);
    cliSteps.push({
      name: 'renet_provision',
      duration_ms: Date.now() - provStart,
      startedAtMs: provStart,
    });

    const verifyFn = () =>
      verifyMachineSetup(
        machine,
        sshPrivateKey,
        { ...options, functionName: options.functionName },
        sftp
      );
    const runVerify = async () => {
      const verifyStart = Date.now();
      if (quiet) {
        await verifyFn();
      } else {
        await timedStep(t('timing.step.verifying'), 'timing.step.machineVerified', verifyFn);
      }
      cliSteps.push({
        name: 'machine_verify',
        duration_ms: Date.now() - verifyStart,
        startedAtMs: verifyStart,
      });
    };

    if (isRepoProvisioningFunction(options.functionName)) {
      // License issuance only needs the provisioned renet binary, not the
      // verified machine setup — run it concurrently with verification.
      const runLicense = async () => {
        const licStart = Date.now();
        await timedStep(t('timing.step.activating'), 'timing.step.licenseActivated', () =>
          this.ensureRepoLicenseForProvisioning(
            options,
            machine,
            sshPrivateKey,
            remoteRenetPath,
            sftp
          )
        );
        cliSteps.push({
          name: 'license',
          duration_ms: Date.now() - licStart,
          startedAtMs: licStart,
        });
      };
      await Promise.all([runVerify(), runLicense()]);
    } else {
      await runVerify();
    }

    await this.maybeRefreshRepoLicenses(
      machine,
      options.machineName,
      sshPrivateKey,
      remoteRenetPath,
      sftp
    );

    return { remoteRenetPath, renetUploaded };
  }

  /**
   * Execute a function on a machine via direct SSH.
   * SSHes to the machine and runs `renet execute --executor local` with vault via stdin.
   */
  private async loadConfigAndBuildVault(
    options: ExecuteOptions,
    startTime: number,
    cliSteps: { name: string; duration_ms: number; startedAtMs?: number }[]
  ) {
    const config = await configService.getLocalConfig();
    const machine = await configService.getLocalMachine(options.machineName);

    if (options.debug) {
      outputService.info(`Executing '${options.functionName}' on ${options.machineName}`);
    }

    const sshPrivateKey = config.sshPrivateKey ?? (await readSSHKey(config.ssh.privateKeyPath));
    const sshPublicKey =
      config.sshPublicKey ?? (await readOptionalSSHKey(config.ssh.publicKeyPath));
    const sshKnownHosts = await resolveKnownHosts(machine.knownHosts);
    const storages = await loadContextStorages();
    const { credentials: repositoryCredentials, configs: repositoryConfigs } =
      await loadContextRepositories();

    // Peer machines (backup push/pull targets) are resolved HERE, from params,
    // against the executor's own config. Callers may still pass them explicitly
    // (tests do), but no command should: a proxy client holds no config and so
    // cannot resolve a peer's IP. Deriving executor-side keeps one code path.
    const params = options.params ?? {};
    const extraMachines = options.extraMachines ?? (await resolveExtraMachines(params));

    const vault = buildLocalVault({
      functionName: options.functionName,
      machineName: options.machineName,
      // #74: a caller that KNOWS the repo's placement declares its datastore here,
      // and it must land in the MACHINE VAULT — that is the only datastore renet
      // ever reads (`p.Datastore()` -> `machineDatastore`, set by WithMachineVault).
      // A `datastore` PARAM would not do it: `repository_create` resolves the
      // datastore through AddDatastore, which reads the vault, not the params bag.
      // The fallback below is untouched and still correct: a machine with no named
      // datastore keeps its own default. This only lets a caller stop staying silent.
      machine: options.datastore ? { ...machine, datastore: options.datastore } : machine,
      sshPrivateKey,
      sshPublicKey,
      sshKnownHosts,
      params,
      extraMachines,
      storages,
      repositoryCredentials,
      repositoryConfigs,
    });
    cliSteps.push({ name: 'config', duration_ms: Date.now() - startTime, startedAtMs: startTime });
    return { config, machine, sshPrivateKey, vault };
  }

  private async executeSession(
    sftp: SFTPClient,
    config: Awaited<ReturnType<typeof configService.getLocalConfig>>,
    machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
    sshPrivateKey: string,
    vault: ReturnType<typeof buildLocalVault>,
    options: ExecuteOptions,
    cliSteps: { name: string; duration_ms: number; startedAtMs?: number }[],
    quiet: boolean,
    startTime: number
  ): Promise<ExecuteResult> {
    const { remoteRenetPath } = await this.provisionAndVerify(
      config,
      machine,
      sshPrivateKey,
      options,
      sftp,
      cliSteps,
      quiet
    );

    const result = await this.executeWithConnectedSftp(
      sftp,
      options,
      remoteRenetPath,
      vault,
      machine,
      sshPrivateKey,
      startTime
    );
    result.cliSteps = [...cliSteps];
    result.allSteps = [...cliSteps, ...(result.steps ?? [])];

    if (result.success) {
      outputService.setOperationDuration(result.operationDurationMs ?? result.durationMs);
    }
    return result;
  }

  private recordAudit(
    options: ExecuteOptions,
    result: Pick<ExecuteResult, 'success' | 'exitCode' | 'durationMs' | 'error'>
  ) {
    auditService.recordOperation({
      functionName: options.functionName,
      machineName: options.machineName,
      repoName:
        typeof options.params?.repository === 'string' ? options.params.repository : undefined,
      success: result.success,
      exitCode: result.exitCode,
      durationMs: result.durationMs,
      error: result.success ? undefined : result.error,
    });
  }

  async execute(options: ExecuteOptions): Promise<ExecuteResult> {
    // BUG #46 (ruling: the executor injects KUBECONFIG WITHOUT rerouting the
    // machine). `kubeCluster` used to ALSO overwrite `machineName` with the
    // cluster's control node here. That was defensible while kubeCluster could
    // only come from an explicit `--cluster` flag ("run this against the
    // cluster"), but the reshape DERIVES it from placement, so the override
    // silently sent every verb on a k8s-placed repo to the control node -
    // including volume-level operations (trim, diff, commit, merge, and repo
    // up's LUKS mount) that MUST run on the machine which actually mounts the
    // datastore (state.datastores[D].attachedTo).
    //
    // KUBECONFIG is the k8s analog of DOCKER_HOST, and DOCKER_HOST never
    // reroutes the machine either: it is still injected from options.kubeCluster
    // in runRemoteExecution. The caller's derived machineName now stands, and a
    // verb that genuinely must run FROM the control node resolves that machine
    // explicitly at its call site (resolveExecutionTarget({ cluster })) rather
    // than relying on an ambient rewrite.
    const startTime = Date.now();
    const configSpinner = options.quietSpinners ? null : startSpinner(t('timing.step.loading'));
    const cliSteps: { name: string; duration_ms: number; startedAtMs?: number }[] = [];

    try {
      const { config, machine, sshPrivateKey, vault } = await this.loadConfigAndBuildVault(
        options,
        startTime,
        cliSteps
      );
      const configText = t('timing.step.configLoaded', {
        duration: formatDuration(cliSteps[0].duration_ms),
      });
      if (configSpinner) stopSpinner(true, configText);
      else if (!options.quietSpinners) outputService.info(configText);

      const quiet = options.quietSpinners ?? false;
      const sshStart = Date.now();
      const acquireFn = () => machineConnections.acquireFor(machine, sshPrivateKey);
      const lease = quiet
        ? await acquireFn()
        : await timedStep(t('timing.step.connecting'), 'timing.step.connected', acquireFn);
      cliSteps.push({
        name: 'ssh_connect',
        duration_ms: Date.now() - sshStart,
        startedAtMs: sshStart,
      });

      try {
        const result = await this.executeSession(
          lease.sftp,
          config,
          machine,
          sshPrivateKey,
          vault,
          options,
          cliSteps,
          quiet,
          startTime
        );
        this.recordAudit(options, result);
        return result;
      } finally {
        lease.release();
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      const durationMs = Date.now() - startTime;
      this.recordAudit(options, { success: false, exitCode: 1, durationMs, error: errorMessage });
      // A CliExitError is a deliberate REFUSAL carrying its own exit code, its
      // retryable flag and its next-actions. Flattening it into a generic
      // {exitCode: 1} result throws all of that away: a BUSY provisioning-lock
      // timeout (exit 15, retryable, "here is the pid holding it") arrived at
      // the user as an anonymous exit 1. Let it through untouched.
      if (error instanceof CliExitError) throw error;
      return { success: false, exitCode: 1, error: errorMessage, durationMs };
    }
  }

  /**
   * Detect whether CLI is running in development (tsx) or production.
   */
  private detectEnvironment(): string {
    const execArgs = process.execArgv.join(' ');
    if (
      execArgs.includes('tsx') ||
      execArgs.includes('ts-node') ||
      process.argv[1]?.endsWith('.ts')
    ) {
      return 'development';
    }
    return isDevBuild() ? 'development' : DEFAULTS.TELEMETRY.ENVIRONMENT;
  }

  /**
   * Check if renet binary is available.
   */
  async checkRenetAvailable(): Promise<boolean> {
    try {
      const config = await configService.getLocalConfig();
      const renetPath = await getLocalRenetPath(config);
      return new Promise((resolve) => {
        const child = spawn(renetPath, ['version'], {
          stdio: ['ignore', 'pipe', 'pipe'],
        });
        child.on('close', (code) => resolve(code === 0));
        child.on('error', () => resolve(false));
      });
    } catch {
      return false;
    }
  }
}

export const localExecutorService = new LocalExecutorService();
