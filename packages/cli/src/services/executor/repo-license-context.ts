/**
 * What a repo license issued by the executor must say: the repo's guid and
 * lineage, its size, and the datastore identity that scopes both the signed
 * payload and where renet looks for the blob. Resolved before provisioning,
 * before a restore, and for the post-create identity refresh.
 */

import { DEFAULTS, NETWORK_DEFAULTS } from '@rediacc/shared/config';
// Type-only, so nothing from the command layer is pulled in at runtime. The declaration is imported rather than restated because it is a WIRE shape: a hand-written twin here is how the two sides drift apart while both stay green.
import type { BackupManifestsResponse } from '../../commands/backup-storage.js';
import type { SFTPClient } from '../../remote/sftp/index.js';
import type { RepositoryConfig } from '../../types/index.js';
import { ValidationError } from '../../utils/errors.js';
import { shellQuote } from '../../utils/shell-quote.js';
import { accountServerFetch } from '../account/account-client.js';
import { isDatastoreScopedId, readRuntimeRepoLicenseStatuses } from '../account/license.js';
import { namedDatastoreMount } from '../cluster/cluster-target.js';
import { configService } from '../config/config-resources.js';
import { outputService } from '../core/output.js';
import { usesTagAsProvisioningTarget } from '../renet/renet-license-contract.js';

export interface RepoLicenseContext {
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
   * only a fallback for a scan that cannot answer, refusing there would fail
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
 * exist, and it is the thing that carries the identity, so we ask the machine
 * registry for it.
 *
 * Getting this wrong is expensive and silent, and it happened live: `repo
 * create --datastore <d>` minted the license (slot claimed, meter moved) and
 * wrote it to the unscoped `repos/<guid>/` path, while renet's create-tier
 * check for a datastore-resident repo reads ONLY
 * `datastores/<id>/repos/<guid>/`, a clean break, no dual read. renet exited
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
  // carries no descriptor and therefore no identity: unscoped is CORRECT there, and it is what renet reads. Same for a config that predates placement.
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

export async function resolveRepoLicenseContext(
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
  // there is nothing to fingerprint; the proofs arrive afterwards, when refreshRepoLicenseIdentity reissues from renet's own licence scan.
  //
  // A `stat`-based fingerprint used to be computed on this path and it was dead code that was ALSO wrong: `storageFingerprint` is a signed payload field whose exact bytes renet re-derives (pkg/license/identity.go, `kind:size:mtime:mode` over Go's FileMode), and no `stat -c` format string produces them. One producer of those bytes now, and it is renet's scan.
  //
  // The datastore identity is the exception, and it is resolved here rather than scanned: see resolveProvisioningDatastoreId. For a tag-targeted verb (fork, commit) the placement read is the SOURCE repo's, which is the right one, a fork lands in the datastore its parent lives in, and placement is a property of the family, not of the tag.
  const built = buildRepoLicenseContext(functionName, params, repo, requestedSizeGb);
  if (!built) return null;
  const ctx: RepoLicenseContext = { ...built, datastoreMount };
  const datastoreId = await resolveProvisioningDatastoreId(repo, sftp, scope);
  return datastoreId === undefined ? ctx : { ...ctx, datastoreId };
}

/**
 * The licence context for `backup_restore`, resolved from the RESTORE's own
 * inputs rather than from a repo that exists on the machine.
 *
 * A deliberate copy of `resolveRepoLicenseContext` rather than a shared helper,
 * and the copy is the design (see `ensureRepoLicenseForRestore`). Every one of
 * its four inputs comes from somewhere else here:
 *
 * - The repo record is the one `backup restore` wrote BEFORE invoking the
 *   executor, carrying the SOURCE's guid (backup.ts's `addRepository` sets
 *   `repositoryGuid: source.repositoryGuid`). That is deliberate on both sides:
 *   the licence minted here is the one `repository_up` will look for after the
 *   restore, so `--up` works and nothing is orphaned.
 * - The lineage comes from `params.lineage`, NOT from the record. The restored
 *   record carries no `grandGuid` at all, `addRepository` is called with five
 *   fields and that is not one of them, and `grandGuid` is stored, never
 *   derived (resource-state.ts). `params.lineage` is the same value the command
 *   computed (`source.grandGuid ?? source.repositoryGuid`) and hands to the
 *   chunk store, so reading it keeps one number in play instead of two.
 * - The size comes from the MANIFEST, because the machine cannot answer: the
 *   image being licensed does not exist there yet by construction, so the
 *   `stat` probe would report the 1 GB floor and cap a restored 500 GB repo.
 * - The datastore identity reuses `resolveProvisioningDatastoreId` unchanged.
 *   `backup restore` records `placement` for both the `--datastore` and the
 *   `--machine` case, and this is the piece that decides whether the blob lands
 *   where `datastore.IdentityAt` will look for it. Getting it wrong is a
 *   licence installed somewhere nothing reads.
 */
export async function resolveRestoreLicenseContext(
  machineName: string,
  params: Record<string, unknown>,
  sftp: SFTPClient,
  scope: DatastoreScopeOptions
): Promise<Omit<RepoLicenseContext, 'requestedSizeGb'> | null> {
  const repoName = typeof params.repository === 'string' ? params.repository : '';
  if (!repoName) return null;
  // A bare name resolves to the family's grand, whatever its tag.
  const repo = await configService.getRepository(repoName);
  if (!repo?.repositoryGuid) return null;
  const machine = await configService.getLocalMachine(machineName);

  const repositoryGuid = repo.repositoryGuid;
  const lineage = typeof params.lineage === 'string' && params.lineage ? params.lineage : undefined;
  const grandGuid = lineage ?? repo.grandGuid ?? repositoryGuid;

  // Size is deliberately NOT resolved here. It costs a round trip to the account server, and the caller's skip probe may decide no licence needs issuing at all, in which case that round trip buys nothing.
  const ctx: Omit<RepoLicenseContext, 'requestedSizeGb'> = {
    repositoryGuid,
    grandGuid,
    // Same rule buildRepoLicenseContext applies: a lineage that is the repo's own guid is a grand, anything else is a fork of one.
    kind: grandGuid === repositoryGuid ? 'grand' : 'fork',
    datastoreMount: repoImageDatastoreMount(repo, machine),
  };
  const datastoreId = await resolveProvisioningDatastoreId(repo, sftp, scope);
  return datastoreId === undefined ? ctx : { ...ctx, datastoreId };
}

/**
 * Whether the target already holds a usable licence for the repo about to be
 * restored, in which case issuance is skipped entirely.
 *
 * This is a cost control, and it is part of the fix rather than a refinement.
 * `claimRepoLicenseIssuanceSlot` is unconditional on the single-issue path and
 * dedupes by NOTHING: not by repo, not by machine. Without this probe a DR
 * session that fails three times on an unrelated error would spend four monthly
 * issuances, which is exactly the shape of surprise a disaster is the worst
 * moment to receive.
 *
 * Scoped to the SOURCE GUID IN THE TARGET DATASTORE, never "any licence on the
 * machine". Probing for "any" would reproduce the carrier-repo bug from the
 * other direction: it would skip issuance on a machine holding some unrelated
 * blob, the restore would then succeed through renet's any-repo fallback, and
 * the `--up` that follows would fail for want of a licence for THIS guid.
 *
 * Best-effort: a scan that cannot answer means "issue", never "refuse". The
 * cost of a redundant issuance is one slot; the cost of a refused pre-flight is
 * a failed disaster recovery.
 */
export async function restoreLicenseAlreadyInstalled(
  ctx: Omit<RepoLicenseContext, 'requestedSizeGb'>,
  machine: Awaited<ReturnType<typeof configService.getLocalMachine>>,
  sshPrivateKey: string,
  remoteRenetPath: string,
  sftp: SFTPClient
): Promise<boolean> {
  // `--all-datastores`, so a licence in a NAMED datastore is visible here; the scope comparison below is what keeps that breadth from being permissive.
  const statuses = await readRuntimeRepoLicenseStatuses(
    machine,
    sshPrivateKey,
    remoteRenetPath,
    sftp
  ).catch(() => []);
  // Both sides normalised through the same predicate the licence WRITER uses, so an empty string, a missing field and a malformed id all collapse to the unscoped population, which is the population they would actually be written to.
  const wanted = isDatastoreScopedId(ctx.datastoreId) ? ctx.datastoreId : undefined;
  return statuses.some(
    (entry) =>
      entry.repositoryGuid === ctx.repositoryGuid &&
      entry.runtimeValid &&
      (isDatastoreScopedId(entry.datastoreId) ? entry.datastoreId : undefined) === wanted
  );
}

/**
 * The size to request for a restore's licence, read from the SNAPSHOT the
 * restore is about to materialise.
 *
 * `resolveRequestedSizeGb` cannot answer this one: it `stat`s the repo image,
 * and on a restore that image does not exist yet, on a DR machine nothing
 * does. It would fall back to the 1 GB floor and cap the restored repo at 1 GB
 * for the rest of its life, because `MaxRepositorySizeGb` is signed into the
 * payload and read back by renet's `repository_limits`.
 *
 * The manifest index is the authority instead: its `totalBytes` is written from
 * the snapshot's `ImageBytes`, i.e. the full LOGICAL image size, which is the
 * size the restored repo will present. `params.at` is already a snapshot id by
 * the time the executor sees it (the command resolves a time to an id before
 * dispatching), so this is an exact lookup rather than a search.
 *
 * Best-effort, and the floor is the fallback: this runs inside a pre-flight for
 * disaster recovery, and refusing the restore because a size lookup failed
 * would be a worse outcome than an under-sized licence the operator can
 * re-issue. It warns rather than throws, for the same reason
 * `warnUnmeasuredRepoSize` does.
 */
export async function resolveRestoreSizeGb(lineage: string, at: unknown): Promise<number> {
  const snapshotId = typeof at === 'string' ? at : '';
  try {
    const index = await accountServerFetch<BackupManifestsResponse>(
      `/account/api/v1/backups/manifests?lineage=${encodeURIComponent(lineage)}`
    );
    const manifest = index.manifests.find((m) => m.snapshotId === snapshotId);
    if (!manifest) throw new Error(`no manifest for snapshot ${snapshotId || '(unset)'}`);
    return Math.max(MIN_REQUESTED_SIZE_GB, Math.ceil(manifest.totalBytes / (1024 * 1024 * 1024)));
  } catch (error) {
    outputService.warn(
      `Could not read the size of snapshot ${snapshotId || '(unset)'} from the manifest index ` +
        `(${error instanceof Error ? error.message : String(error)}), so the restored ` +
        `repository's license is being requested at the ${MIN_REQUESTED_SIZE_GB} GB minimum. ` +
        `If the restored repository is larger than that, re-issue its license afterwards ` +
        `("rdc subscription refresh").`
    );
    return MIN_REQUESTED_SIZE_GB;
  }
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
  // For a tag-targeted verb `params.repository` names the SOURCE, and the licence target is `params.tag`; a missing source is not fatal here because buildRepoLicenseContext decides what it can build without one.
  if (!repoName && !usesTagAsProvisioningTarget(functionName)) return null;
  // A bare name resolves to the family's grand, whatever its tag.
  const repo = await configService.getRepository(repoName);
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
  // fork and commit both mint against `params.tag`, and both are derived snapshots of the source repo rather than new lineages, so both are kind 'fork' rooted at the source's grand. `repo commit` registers the commit object with exactly that lineage (repo-branching.ts handleCommit sets grandGuid: cfg.grandGuid ?? cfg.repositoryGuid), so the batch refresh path classifies it the
  // same way on every later touch.
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
 * size probe below, and it failed SILENTLY rather than loudly, the stat found
 * nothing, the old `|| echo ${REPO_SIZE_PROBE_UNKNOWN}` turned that into 0 bytes, and every fork or
 * commit of a named-datastore repo was pre-issued a licence for the 1 GB floor
 * regardless of the repo's real size. Neither verb exposes `--size`, so that
 * estimate was not a fallback for them; it was the only number they ever sent.
 *
 * Placement is a property of the FAMILY, and the flat per-tag records carry a
 * copy of it (resource-state.ts flattening), so `repo.placement` answers for a
 * fork's parent as well, which is the repo this probe measures.
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
  // Sized from the PARENT image in every case, fork included: a fork has no image of its own yet, and it starts as a reflink of its parent.
  if (!repositoryGuid) return null;
  const imagePath = `${datastore}/repositories/${repositoryGuid}`;
  // A sentinel, not `|| echo 0`. Under the old probe a stat that failed for ANY reason, wrong datastore, unreadable mount, missing image, produced the same bytes as a genuinely tiny image, and the caller then reported the 1 GB floor with the confidence of a measurement. The sentinel keeps "we did not measure" expressible, which is the whole point of the distinction.
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
 * Say out loud that the licence size is a floor rather than a measurement ,
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
