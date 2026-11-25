/**
 * The incident record the account stores and the read verbs return (D4). The
 * database columns are snake_case; the API shape is camelCase like every other
 * shared schema.
 */
import { z } from 'zod';

export const INCIDENT_STATUSES = ['declared', 'contained', 'closed'] as const;
export type IncidentStatus = (typeof INCIDENT_STATUSES)[number];

export const INCIDENT_SCOPE_KINDS = ['repo', 'machine'] as const;
export type IncidentScopeKind = (typeof INCIDENT_SCOPE_KINDS)[number];

/** The steps a declare runs; a failed one stays visible as a retry action. */
export const INCIDENT_STEP_NAMES = ['hold', 'lock', 'fork', 'level'] as const;

export const IncidentStepSchema = z.strictObject({
  name: z.enum(INCIDENT_STEP_NAMES),
  status: z.enum(['pending', 'ok', 'failed']),
  at: z.iso.datetime(),
  detail: z.string().max(500).optional(),
});
export type IncidentStep = z.infer<typeof IncidentStepSchema>;

/** Days after close before the hold and the lock rules are released. */
export const INCIDENT_RELEASE_DAYS = 30;

const instant = z.iso.datetime();

export const IncidentSchema = z
  .strictObject({
    id: z.string().min(1).max(100),
    orgId: z.string().min(1).max(200),
    scopeKind: z.enum(INCIDENT_SCOPE_KINDS),
    scopeRef: z.string().min(1).max(200),
    windowFrom: instant,
    windowTo: instant,
    status: z.enum(INCIDENT_STATUSES),
    declaredBy: z.string().min(1).max(200),
    declaredAt: instant,
    awareAt: instant,
    notifiedAt: instant.nullable(),
    containedAt: instant.nullable(),
    closedAt: instant.nullable(),
    closedBy: z.string().min(1).max(200).nullable(),
    forkRef: z.string().min(1).max(200).nullable(),
    steps: z.array(IncidentStepSchema).max(50),
  })
  .refine((i) => Date.parse(i.windowFrom) <= Date.parse(i.windowTo), {
    message: 'windowFrom is after windowTo',
    path: ['windowTo'],
  })
  .refine((i) => Date.parse(i.awareAt) <= Date.parse(i.declaredAt), {
    message: 'awareAt may be earlier than declaredAt, never later',
    path: ['awareAt'],
  });
export type Incident = z.infer<typeof IncidentSchema>;

/** The instant a closed incident's hold and lock rules may be released, null while it is open. */
export function releaseAt(incident: Pick<Incident, 'closedAt'>): string | null {
  if (incident.closedAt === null) return null;
  return new Date(Date.parse(incident.closedAt) + INCIDENT_RELEASE_DAYS * 86_400_000).toISOString();
}
