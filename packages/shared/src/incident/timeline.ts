/**
 * The investigation timeline row (D2 of PLAN-forensics-investigation): one union
 * over every source the read service merges, sorted by time. A row says where it
 * came from (`source`) and whether the store observed it or the service inferred
 * it (`basis`); a gap is inferred, everything a store holds is observed.
 */
import { z } from 'zod';

export const TIMELINE_KINDS = [
  'audit',
  'run',
  'flow',
  'open',
  'anomaly',
  'gap',
  'incident',
] as const;
export type TimelineKind = (typeof TIMELINE_KINDS)[number];

const base = {
  id: z.string().min(1).max(200),
  ts: z.iso.datetime(),
  /** The store the row was read from, such as `audit-r2` or `forensics`. */
  source: z.string().min(1).max(100),
  basis: z.enum(['observed', 'inferred']),
};

const auditRow = z.strictObject({
  ...base,
  kind: z.literal('audit'),
  data: z.strictObject({
    type: z.string().min(1).max(100),
    actorId: z.string().min(1).max(200),
    actorKind: z.enum(['human', 'agent', 'support']),
    pathKey: z.string().min(1).max(200).optional(),
    target: z.record(z.string(), z.union([z.string(), z.array(z.string())])),
  }),
});

const runRow = z.strictObject({
  ...base,
  kind: z.literal('run'),
  data: z.strictObject({
    requestId: z.string().min(1).max(200),
    pathKey: z.string().min(1).max(200),
    exitCode: z.number().int().nullable(),
    /** A run tail stays sealed under the org key: the row says one exists and never carries it. */
    tailSealed: z.boolean(),
  }),
});

const flowRow = z.strictObject({
  ...base,
  kind: z.literal('flow'),
  data: z.strictObject({
    repoGuid: z.string().min(1).max(100),
    process: z.string().max(200),
    dstAddress: z.string().min(1).max(100),
    dstPort: z.number().int().min(0).max(65535),
    dstName: z.string().max(253).optional(),
    asn: z.number().int().min(0).optional(),
    country: z.string().length(2).optional(),
    bytesOut: z.number().int().min(0),
    bytesIn: z.number().int().min(0),
  }),
});

const openRow = z.strictObject({
  ...base,
  kind: z.literal('open'),
  data: z.strictObject({
    repoGuid: z.string().min(1).max(100),
    process: z.string().max(200),
    path: z.string().min(1).max(4096),
    sensitive: z.boolean(),
  }),
});

const anomalyRow = z.strictObject({
  ...base,
  kind: z.literal('anomaly'),
  data: z.strictObject({
    findingId: z.string().min(1).max(200),
    detector: z.enum(['machine', 'server']),
    rule: z.string().min(1).max(200),
    score: z.number().min(0).max(1),
  }),
});

const gapRow = z.strictObject({
  ...base,
  kind: z.literal('gap'),
  data: z.strictObject({
    machineId: z.string().min(1).max(128),
    from: z.iso.datetime(),
    to: z.iso.datetime(),
    reason: z.enum(['heartbeat', 'sequence', 'chain']),
  }),
});

const incidentRow = z.strictObject({
  ...base,
  kind: z.literal('incident'),
  data: z.strictObject({
    incidentId: z.string().min(1).max(100),
    action: z.enum(['declared', 'contained', 'closed']),
    actorId: z.string().min(1).max(200),
  }),
});

export const TimelineRowSchema = z.discriminatedUnion('kind', [
  auditRow,
  runRow,
  flowRow,
  openRow,
  anomalyRow,
  gapRow,
  incidentRow,
]);
export type TimelineRow = z.infer<typeof TimelineRowSchema>;

/** Time order; equal instants fall back to the id so a cursor never skips or repeats a row. */
export function compareRows(
  a: Pick<TimelineRow, 'ts' | 'id'>,
  b: Pick<TimelineRow, 'ts' | 'id'>
): number {
  const left = Date.parse(a.ts);
  const right = Date.parse(b.ts);
  if (left !== right) return left - right;
  if (a.id === b.id) return 0;
  return a.id < b.id ? -1 : 1;
}

export function mergeRows(...sources: readonly (readonly TimelineRow[])[]): TimelineRow[] {
  return sources.flat().sort(compareRows);
}
