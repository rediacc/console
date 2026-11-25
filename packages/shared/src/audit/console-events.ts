/**
 * Console audit events: every action taken through the console (command runs
 * and their results, config-editor saves, policy saves, step-ups, reveals, AI
 * approvals, feedback sends), each with who, what and the target, and never a
 * secret parameter.
 *
 * One event is one object in the audit bucket. The envelope is the same for
 * every type; `data` is a strict object per type, so a field that is not
 * named here (a parameter value, a secret) fails validation instead of being
 * stored.
 */

import { z } from 'zod';
import { STEP_UP_METHODS } from '../auth/step-up.js';
import type { ContractCommand } from '../cli-contract/types.js';
import type { CommandRequest } from '../cli-contract/wire.js';

export const CONSOLE_AUDIT_TYPES = [
  'console.command.run',
  'console.command.result',
  'console.config.saved',
  'console.policy.saved',
  'console.stepup',
  'console.reveal',
  // Emitted by the AI assistant plans, not by the console exec path.
  'console.ai.approval',
  'console.feedback.sent',
  // Forensics investigation (PLAN-forensics-investigation D3, D4).
  'console.forensics.open',
  'console.forensics.view',
  'console.forensics.grant',
  'console.incident.declared',
  'console.incident.contained',
  'console.incident.closed',
] as const;

export const consoleAuditTypeEnum = z.enum(CONSOLE_AUDIT_TYPES);
type ConsoleAuditType = z.infer<typeof consoleAuditTypeEnum>;

export type { ConsoleAuditType };

/**
 * Identifying values of the command a run acted on: positionals and the
 * options that name a resource. A value is a string or a list of strings.
 */
export const consoleTargetSchema = z.record(z.string(), z.union([z.string(), z.array(z.string())]));
type ConsoleTarget = z.infer<typeof consoleTargetSchema>;

export type { ConsoleTarget };

const stepUpMethod = z.enum(STEP_UP_METHODS);
const requestId = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._:@-]{0,199}$/);
const severity = z.enum(['none', 'caution', 'destructive']);

const actorSchema = z.strictObject({
  userId: z.string().min(1).max(200),
  kind: z.enum(['human', 'agent', 'support']),
});

const envelope = {
  v: z.literal(1),
  id: z.string().min(1).max(100),
  ts: z.iso.datetime(),
  orgId: z.string().min(1).max(200),
  /** Null for an event that belongs to the org and no team. */
  teamId: z.string().min(1).max(200).nullable(),
  actor: actorSchema,
  target: consoleTargetSchema,
};

const commandRun = z.strictObject({
  ...envelope,
  type: z.literal('console.command.run'),
  data: z.strictObject({
    requestId,
    pathKey: z.string().min(1).max(200),
    severity,
    /** The step-up method of the elevation that admitted the run, when it needed one. */
    method: stepUpMethod.nullable(),
  }),
});

const commandResult = z.strictObject({
  ...envelope,
  type: z.literal('console.command.result'),
  data: z.strictObject({
    requestId,
    exitCode: z.number().int(),
    success: z.boolean(),
    jobId: z.string().min(1).max(100).optional(),
  }),
});

const configSaved = z.strictObject({
  ...envelope,
  type: z.literal('console.config.saved'),
  data: z.strictObject({
    configId: z.string().min(1).max(200),
    action: z.enum(['push', 'restore']),
    version: z.number().int().min(0).optional(),
  }),
});

// Names the policy store, config and version that changed, never the policy content.
const policySaved = z.strictObject({
  ...envelope,
  type: z.literal('console.policy.saved'),
  data: z.strictObject({
    storeId: z.string().min(1).max(200),
    configId: z.string().min(1).max(200),
    version: z.number().int().min(0),
  }),
});

const stepUp = z.strictObject({
  ...envelope,
  type: z.literal('console.stepup'),
  data: z.strictObject({
    method: stepUpMethod,
  }),
});

// Two reveals: a command reveal names the command (`pathKey`), a config-editor
// reveal names the config and how many leaves it unmasked. Neither carries a value.
const commandReveal = z.strictObject({
  requestId: requestId.optional(),
  pathKey: z.string().min(1).max(200),
  method: stepUpMethod.nullable(),
});

const editorReveal = z.strictObject({
  configId: z.string().min(1).max(200),
  leafCount: z.number().int().min(0),
  revealUntil: z.iso.datetime(),
  method: stepUpMethod.nullable(),
});

const reveal = z.strictObject({
  ...envelope,
  type: z.literal('console.reveal'),
  data: z.union([commandReveal, editorReveal]),
});

const aiApproval = z.strictObject({
  ...envelope,
  type: z.literal('console.ai.approval'),
  data: z.strictObject({
    requestId: requestId.optional(),
    pathKey: z.string().min(1).max(200),
    decision: z.enum(['approved', 'rejected']),
  }),
});

const feedbackSent = z.strictObject({
  ...envelope,
  type: z.literal('console.feedback.sent'),
  data: z.strictObject({
    feedbackId: z.string().min(1).max(100),
  }),
});

const isoWindow = {
  from: z.iso.datetime(),
  to: z.iso.datetime(),
};
const scopeKind = z.enum(['repo', 'machine']);
const rowKind = z.enum(['audit', 'run', 'flow', 'open', 'anomaly', 'gap', 'incident']);

// Opening an investigation: which scope and how long the 60 minute window holds.
const forensicsOpen = z.strictObject({
  ...envelope,
  type: z.literal('console.forensics.open'),
  data: z.strictObject({
    investigationId: z.string().min(1).max(100),
    scopeKind,
    expiresAt: z.iso.datetime(),
    method: stepUpMethod.nullable(),
  }),
});

// One per read: the scope, the window and the row kinds returned, never a row's content.
const forensicsView = z.strictObject({
  ...envelope,
  type: z.literal('console.forensics.view'),
  data: z.strictObject({
    investigationId: z.string().min(1).max(100).nullable(),
    grantId: z.string().min(1).max(100).optional(),
    scopeKind,
    ...isoWindow,
    kinds: z.array(rowKind).max(7),
  }),
});

const forensicsGrant = z.strictObject({
  ...envelope,
  type: z.literal('console.forensics.grant'),
  data: z.strictObject({
    grantId: z.string().min(1).max(100),
    action: z.enum(['issued', 'revoked']),
    scopeKind,
    expiresAt: z.iso.datetime(),
  }),
});

const incidentData = {
  incidentId: z.string().min(1).max(100),
  scopeKind,
};

const incidentDeclared = z.strictObject({
  ...envelope,
  type: z.literal('console.incident.declared'),
  data: z.strictObject({
    ...incidentData,
    ...isoWindow,
    awareAt: z.iso.datetime(),
  }),
});

const incidentContained = z.strictObject({
  ...envelope,
  type: z.literal('console.incident.contained'),
  data: z.strictObject(incidentData),
});

const incidentClosed = z.strictObject({
  ...envelope,
  type: z.literal('console.incident.closed'),
  data: z.strictObject({
    ...incidentData,
    releaseAt: z.iso.datetime(),
  }),
});

export const ConsoleAuditEventSchema = z.discriminatedUnion('type', [
  commandRun,
  commandResult,
  configSaved,
  policySaved,
  stepUp,
  reveal,
  aiApproval,
  feedbackSent,
  forensicsOpen,
  forensicsView,
  forensicsGrant,
  incidentDeclared,
  incidentContained,
  incidentClosed,
]);
type ConsoleAuditEvent = z.infer<typeof ConsoleAuditEventSchema>;

export type { ConsoleAuditEvent };

/**
 * The target of a console run: its positionals that name something (a
 * `plain` positional is free text, such as `config set <key> <value>`, so it
 * is dropped), and the options whose contract entry names a resource
 * (`kinds`) and is not `sensitive`. Every other param is dropped, so a secret passed through a mislabelled or
 * unlabelled option never reaches an audit object.
 */
export function consoleTargetOf(
  entry: Pick<ContractCommand, 'positionals' | 'options'>,
  request: Pick<CommandRequest, 'params' | 'positionals'>
): ConsoleTarget {
  const target: ConsoleTarget = {};
  const keep = (key: string, raw: unknown): void => {
    const value = asTargetValue(raw);
    if (value !== undefined) target[key] = value;
  };
  for (const positional of entry.positionals) {
    if (positional.kind !== 'plain') keep(positional.name, request.positionals[positional.name]);
  }
  for (const option of entry.options) {
    if (option.sensitive !== true && (option.kinds?.length ?? 0) > 0) {
      keep(option.long, request.params[option.long]);
    }
  }
  return target;
}

function asTargetValue(value: unknown): string | string[] | undefined {
  if (typeof value === 'string') return value;
  if (Array.isArray(value) && value.every((item): item is string => typeof item === 'string')) {
    return value;
  }
  return undefined;
}
