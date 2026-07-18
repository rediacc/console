/**
 * Audit event contract shared between the CLI emitter
 * (packages/cli/src/services/core/audit.ts) and the account-server ingest
 * route (private/account/src/routes/license.ts).
 *
 * The event-type union is closed: every renet function the CLI
 * may invoke through localExecutorService, plus three explicit
 * non-bridge events (sync.upload, sync.download, term.session). New
 * event types must be added here AND covered by a Sigma rule stub —
 * the CI gate check:ci-audit-coverage enforces both.
 */

import { z } from 'zod';

const machineEventTypes = [
  'cli.machine.containers',
  'cli.machine.deprovision',
  'cli.machine.health',
  'cli.machine.id',
  'cli.machine.list',
  'cli.machine.match',
  'cli.machine.mismatch',
  'cli.machine.ping',
  'cli.machine.provision',
  'cli.machine.query',
  'cli.machine.repos',
  'cli.machine.services',
  'cli.machine.ssh_test',
] as const;

const repoEventTypes = [
  'cli.repo.autostart_disable',
  'cli.repo.autostart_disable_all',
  'cli.repo.autostart_enable',
  'cli.repo.autostart_enable_all',
  'cli.repo.autostart_list',
  'cli.repo.cat',
  'cli.repo.commit',
  'cli.repo.commit_meta',
  'cli.repo.create',
  'cli.repo.delete',
  'cli.repo.diff',
  'cli.repo.down',
  'cli.repo.down_all',
  'cli.repo.expand',
  'cli.repo.fork',
  'cli.repo.guid',
  'cli.repo.list',
  'cli.repo.log',
  'cli.repo.merge',
  'cli.repo.mismatch',
  'cli.repo.mount',
  'cli.repo.ownership',
  'cli.repo.policy_get',
  'cli.repo.policy_set',
  'cli.repo.promote',
  'cli.repo.prune',
  'cli.repo.resize',
  'cli.repo.status',
  'cli.repo.template_apply',
  'cli.repo.trim',
  'cli.repo.unmount',
  'cli.repo.up',
  'cli.repo.up_all',
  'cli.repo.validate',
] as const;

const backupEventTypes = [
  'cli.backup.delete',
  'cli.backup.list',
  'cli.backup.pull',
  'cli.backup.push',
] as const;

// Every datastore verb `packages/cli/src/commands/datastore.ts` dispatches. It goes
// through a `dispatch(functionName, …)` helper rather than a `functionName: '…'`
// literal, so check-audit-coverage.sh — which greps for the literal — cannot see most
// of them: it only ever flagged `fork` and `volumes_close`. The rest were emitting
// event types absent from this union, which makes functionNameToEventType return null
// and the audit record vanish, on exactly the class-D ops (attach, delete, resize)
// that most need an audit trail. `init`, `ceph_init` and `ceph_unfork` are the mirror
// image: literals for functions that no longer exist (#34 / the P4 rename).
const datastoreEventTypes = [
  'cli.datastore.adopt',
  'cli.datastore.attach',
  'cli.datastore.ceph_fork',
  'cli.datastore.create',
  'cli.datastore.delete',
  'cli.datastore.detach',
  'cli.datastore.forget',
  'cli.datastore.fork',
  'cli.datastore.list',
  'cli.datastore.resize',
  'cli.datastore.snapshot_create',
  'cli.datastore.snapshot_delete',
  'cli.datastore.snapshot_list',
  'cli.datastore.status',
  'cli.datastore.volumes_close',
  'cli.datastore.volumes_open',
] as const;

// `repo logs` / `repo exec` (repo-container.ts, new in P4). Dotted, like every other
// group — the fall-through would have produced `cli.container_exec`.
const containerEventTypes = ['cli.container.exec', 'cli.container.logs'] as const;

const explicitEventTypes = ['cli.sync.upload', 'cli.sync.download', 'cli.term.session'] as const;

// Cluster + k8s-namespace lifecycle ops. functionNameToEventType has no
// cluster_/kube_ prefix rule, so these map through the `cli.${functionName}`
// fall-through (underscores preserved), unlike the dotted machine/repo groups.
const clusterEventTypes = [
  'cli.ceph_client_config_export',
  'cli.ceph_health',
  'cli.cluster_create',
  'cli.cluster_destroy',
  'cli.cluster_evict',
  'cli.cluster_fork',
  'cli.cluster_join',
  'cli.cluster_migrate',
  'cli.cluster_scale',
  'cli.kube_health',
  'cli.kube_namespace_create',
  'cli.kube_namespace_delete',
  'cli.kube_namespace_fork',
] as const;

export const MACHINE_OP_EVENT_TYPES = [
  ...machineEventTypes,
  ...repoEventTypes,
  ...backupEventTypes,
  ...datastoreEventTypes,
  ...containerEventTypes,
] as const;

export const ALL_EVENT_TYPES = [
  ...MACHINE_OP_EVENT_TYPES,
  ...clusterEventTypes,
  ...explicitEventTypes,
] as const;

export const auditEventTypeEnum = z.enum(ALL_EVENT_TYPES);
export type AuditEventType = z.infer<typeof auditEventTypeEnum>;

const baseData = z.object({
  functionName: z.string().min(1).max(100),
  machineName: z.string().min(1).max(200),
  repoName: z.string().min(1).max(200).optional(),
  success: z.boolean(),
  exitCode: z.number().int(),
  durationMs: z.number().int().min(0),
  cliVersion: z.string().min(1).max(50),
  error: z.string().max(500).optional(),
});

/**
 * Envelope carried by every event, independent of its type.
 *
 * `idempotencyKey` is minted per event by the emitter and is the server-side
 * dedup key: the ingest route inserts under a unique index, so replaying a
 * batch (a retried flush, a proxy re-delivery) stores each event exactly once
 * and the reported `accepted` count reflects rows actually written.
 *
 * `onBehalfOfTokenId` names the API token whose user actually performed the
 * operation, for events relayed by a broker (rdc serve) that authenticates to
 * the account server with its OWN token. The ingest route verifies the named
 * token lives in the same organization as the authenticating token before
 * attributing the event to it, so a caller can never forge attribution.
 */
const eventEnvelope = {
  idempotencyKey: z.uuid(),
  onBehalfOfTokenId: z.uuid().optional(),
};

// Machine/repo/backup/datastore ops AND cluster/k8s-namespace ops all carry the
// same plain baseData, so they share one discriminated-union branch. Kept as one
// branch (not two) because the audit.ts fall-through assigns a union-typed `type`
// that TypeScript can only resolve against a single branch.
const baseOpEventTypes = [...MACHINE_OP_EVENT_TYPES, ...clusterEventTypes] as const;
const machineOpEvent = z.object({
  type: z.enum(baseOpEventTypes),
  data: baseData,
  ...eventEnvelope,
});

const syncEvent = z.object({
  type: z.enum(['cli.sync.upload', 'cli.sync.download']),
  data: baseData.extend({
    filesTransferred: z.number().int().min(0).optional(),
    bytesTransferred: z.number().int().min(0).optional(),
  }),
  ...eventEnvelope,
});

const termEvent = z.object({
  type: z.literal('cli.term.session'),
  data: baseData.extend({
    sessionDurationMs: z.number().int().min(0).optional(),
  }),
  ...eventEnvelope,
});

export const AuditEventSchema = z.discriminatedUnion('type', [
  machineOpEvent,
  syncEvent,
  termEvent,
]);
export type AuditEvent = z.infer<typeof AuditEventSchema>;

export const AuditEventsRequestSchema = z.object({
  events: z.array(AuditEventSchema).min(1).max(50),
});
export type AuditEventsRequest = z.infer<typeof AuditEventsRequestSchema>;

export const AuditEventsResponseSchema = z.object({
  accepted: z.number().int().min(0),
});
export type AuditEventsResponse = z.infer<typeof AuditEventsResponseSchema>;

/**
 * Map a renet function name to its canonical event type.
 * Returns `null` if the function isn't in the closed union — callers
 * should drop the event rather than emit an unrecognized type that
 * would fail server-side validation.
 */
export function functionNameToEventType(functionName: string): AuditEventType | null {
  const candidate = mapToEventTypeString(functionName);
  return (ALL_EVENT_TYPES as readonly string[]).includes(candidate)
    ? (candidate as AuditEventType)
    : null;
}

function mapToEventTypeString(functionName: string): string {
  if (functionName.startsWith('repository_')) {
    return `cli.repo.${functionName.slice('repository_'.length)}`;
  }
  if (functionName.startsWith('backup_')) {
    return `cli.backup.${functionName.slice('backup_'.length)}`;
  }
  if (functionName.startsWith('datastore_')) {
    return `cli.datastore.${functionName.slice('datastore_'.length)}`;
  }
  if (functionName.startsWith('machine_')) {
    return `cli.machine.${functionName.slice('machine_'.length)}`;
  }
  if (functionName.startsWith('container_')) {
    return `cli.container.${functionName.slice('container_'.length)}`;
  }
  if (functionName === 'sync_upload') return 'cli.sync.upload';
  if (functionName === 'sync_download') return 'cli.sync.download';
  if (functionName === 'term_connect') return 'cli.term.session';
  return `cli.${functionName}`;
}
