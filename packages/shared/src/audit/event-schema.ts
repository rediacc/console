/**
 * Audit event contract shared between the CLI emitter
 * (packages/cli/src/services/audit.ts) and the account-server ingest
 * route (private/account/src/routes/license.ts).
 *
 * The event-type union is closed: every renet bridge function the CLI
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
  'cli.repo.prune',
  'cli.repo.resize',
  'cli.repo.status',
  'cli.repo.takeover',
  'cli.repo.template_apply',
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

const datastoreEventTypes = [
  'cli.datastore.ceph_fork',
  'cli.datastore.ceph_init',
  'cli.datastore.ceph_unfork',
  'cli.datastore.init',
  'cli.datastore.status',
] as const;

const explicitEventTypes = ['cli.sync.upload', 'cli.sync.download', 'cli.term.session'] as const;

export const MACHINE_OP_EVENT_TYPES = [
  ...machineEventTypes,
  ...repoEventTypes,
  ...backupEventTypes,
  ...datastoreEventTypes,
] as const;

export const ALL_EVENT_TYPES = [...MACHINE_OP_EVENT_TYPES, ...explicitEventTypes] as const;

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

const machineOpEvent = z.object({
  type: z.enum(MACHINE_OP_EVENT_TYPES),
  data: baseData,
});

const syncEvent = z.object({
  type: z.enum(['cli.sync.upload', 'cli.sync.download']),
  data: baseData.extend({
    filesTransferred: z.number().int().min(0).optional(),
    bytesTransferred: z.number().int().min(0).optional(),
  }),
});

const termEvent = z.object({
  type: z.literal('cli.term.session'),
  data: baseData.extend({
    sessionDurationMs: z.number().int().min(0).optional(),
  }),
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
 * Map a renet bridge function name to its canonical event type.
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
  if (functionName === 'sync_upload') return 'cli.sync.upload';
  if (functionName === 'sync_download') return 'cli.sync.download';
  if (functionName === 'term_connect') return 'cli.term.session';
  return `cli.${functionName}`;
}
