/**
 * The executor's AI mode and approval routes (AI5 of agent/plans/PLAN-console-ai-assistant.md, D4
 * and D6). The account Worker forwards both from its session routes (`AI_EXECUTOR_ROUTES` in
 * private/account/src/routes/console-ai.ts) under the caller's executor bearer and config session.
 *
 * `POST /v1/ai/mode` changes a conversation's autonomy mode. The executor enforces the mode, so it
 * hears the change first and refuses a mode the org or team policy disabled (`aiModesDisabled`,
 * read from the same effective policy every command is authorized against); the account stores the
 * mode only once this route accepted it.
 *
 * `POST /v1/ai/approval` takes the user's answer to one `approval_required` event. The account ran
 * plan 2's server step-up before forwarding an approval it judged destructive or grand, and names
 * the method in `stepUpMethod`. The executor does not take that judgment on trust: it resolves the
 * command's target from its own config, and an approval of a destructive command or of a grand-repo
 * target without a step-up method is refused here, whatever the browser claimed about `grand`. The
 * single-use token itself is redeemed by the approval ledger the loop owns (`AiApprovals`), bound
 * to the conversation and the command.
 */

import { isPreviewRun, isStepUpMethod, STEP_UP_METHODS } from '@rediacc/shared/auth';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import {
  type AiDisableableMode,
  type DecisionTarget,
  disabledAiModes,
  type EffectivePolicy,
  mergePolicies,
  PolicyDocumentSchema,
} from '@rediacc/shared/policy';
import type { Context, Hono } from 'hono';
import { z } from 'zod';
import { boundEffectivePolicy } from '../config/policy-record.js';
import { prepareCommand } from './command-dispatch.js';
import type { ServeDeps } from './deps.js';
import type { JobRouteHelpers } from './job-routes.js';
import { clusterSubjectOf, resolveExecutorTarget } from './policy.js';
import type { SessionPrincipal } from './sessions.js';

/** The issue text when the schema names none. */
const UNNAMED_ISSUE = 'invalid';

/** Route paths; the account Worker's `AI_EXECUTOR_ROUTES` names the same two. */
export const AI_ROUTES = {
  mode: '/v1/ai/mode',
  approval: '/v1/ai/approval',
} as const;

const AI_MODES = ['ask', 'auto', 'skip'] as const;
export type AiMode = (typeof AI_MODES)[number];

/** Refusal codes these routes answer with. */
export const AI_MODE_DISABLED = 'AI_MODE_DISABLED';
export const AI_APPROVAL_STEPUP_REQUIRED = 'AI_APPROVAL_STEPUP_REQUIRED';

const IdSchema = z
  .string()
  .min(1)
  .max(128)
  .regex(/^[A-Za-z0-9][A-Za-z0-9._:-]*$/);

const ModeRequestSchema = z.strictObject({
  conversationId: IdSchema,
  mode: z.enum(AI_MODES),
});

const ApprovedCommandSchema = z.strictObject({
  pathKey: z.string().min(1).max(256),
  params: z.record(z.string(), z.unknown()).default({}),
  positionals: z.record(z.string(), z.unknown()).default({}),
});

/** What the account forwards: its own `grand` input is not among the fields, the executor decides it. */
const ApprovalRequestSchema = z.strictObject({
  conversationId: IdSchema,
  toolCallId: z.string().min(1).max(256),
  approvalToken: z.string().min(1).max(4096),
  decision: z.enum(['approve', 'reject']),
  command: ApprovedCommandSchema,
  stepUpMethod: z.enum(STEP_UP_METHODS).nullable(),
});

type ApprovalRequest = z.infer<typeof ApprovalRequestSchema>;

/** Where the loop keeps each conversation's mode (D4); the autonomy gate reads it. */
interface AiConversationModes {
  set(principal: SessionPrincipal, conversationId: string, mode: AiMode): void;
}

/** One approval answer as the executor verified it. */
export interface AiApprovalSubmit extends Omit<ApprovalRequest, 'stepUpMethod'> {
  principal: SessionPrincipal;
  stepUpMethod: ApprovalRequest['stepUpMethod'];
  /** The command is destructive and the run is not a preview. */
  destructive: boolean;
  /** The executor resolved the target to a grand repo (or an unresolved one) off the ops VMs. */
  grand: boolean;
}

export type AiApprovalVerdict =
  | { ok: true }
  | { ok: false; status: 403 | 404 | 409; code: string; message: string };

/** The single-use approval tokens the loop issued, bound to (conversation, command). */
interface AiApprovals {
  submit(answer: AiApprovalSubmit): Promise<AiApprovalVerdict>;
}

export interface AiRouteDeps {
  modes: AiConversationModes;
  approvals: AiApprovals;
}

/** A request these routes refuse before any policy work. */
class BadAiRequest extends Error {}

/**
 * The effective policy the config carries: the policy records bound to a remote config, else the
 * `policy` field of a local-file config (the same sources serve/policy.ts authorizes against). A
 * malformed local document disables nothing here; authorize() refuses every command under it.
 */
function effectivePolicyOf(config: RdcConfig): EffectivePolicy | null {
  const bound = boundEffectivePolicy(config);
  if (bound) return bound;
  if (config.remote !== undefined || config.policy === undefined) return null;
  const parsed = PolicyDocumentSchema.safeParse(config.policy);
  return parsed.success ? mergePolicies(parsed.data) : null;
}

/** The modes the policy disables for this caller (D6), in `AI_DISABLEABLE_MODES` order. */
function disabledModesFor(config: RdcConfig, principal: SessionPrincipal): AiDisableableMode[] {
  const effective = effectivePolicyOf(config);
  if (!effective) return [];
  return disabledAiModes(effective, {
    userEmail: principal.userEmail,
    ...(principal.teamSlug ? { teamSlug: principal.teamSlug } : {}),
  });
}

/** A grand-repo target as the grand-repo rule reads it: unresolved counts as grand; ops VMs never do. */
function isGrandTarget(target: DecisionTarget): boolean {
  return !!target.repo && target.repo.state !== 'fork' && !target.isOpsVm;
}

function stringOf(name: string | null, bag: Record<string, unknown>): string | undefined {
  const value = name ? bag[name] : undefined;
  return typeof value === 'string' ? value : undefined;
}

/**
 * What the executor itself makes of an approval: whether the command is destructive (and not a
 * preview) and whether its target is a grand repo, and the refusal of an approval of either that
 * names no step-up method.
 */
async function judgeApproval(
  body: ApprovalRequest,
  config: RdcConfig | undefined
): Promise<{ grand: boolean; destructive: boolean } | { refusal: Record<string, unknown> }> {
  const { pathKey, params, positionals } = body.command;
  const { entry } = prepareCommand(pathKey, params, positionals);
  const target = await resolveExecutorTarget(
    entry,
    {
      ref: stringOf(entry.repoOption, params) ?? stringOf(entry.repoPositional, positionals),
      machine:
        stringOf(entry.machineOption, params) ?? stringOf(entry.machinePositional, positionals),
      subject: clusterSubjectOf(entry, positionals),
    },
    config
  );
  const grand = isGrandTarget(target);
  const destructive = entry.severity === 'destructive' && !isPreviewRun(entry, params);
  const needsStepUp = body.decision === 'approve' && (grand || destructive);
  if (!needsStepUp || isStepUpMethod(body.stepUpMethod)) return { grand, destructive };
  const why = grand ? `targets the grand repo "${target.repo?.name}"` : 'is destructive';
  return {
    refusal: {
      error: `Approving "rdc ${pathKey}" needs a fresh re-authentication: the command ${why}.`,
      code: AI_APPROVAL_STEPUP_REQUIRED,
      grand,
      destructive,
    },
  };
}

export function registerAiRoutes(
  app: Hono,
  deps: ServeDeps,
  /** What server.ts lends these routes: the same helpers the job routes take. */
  helpers: JobRouteHelpers,
  ai: AiRouteDeps
): void {
  /** Authenticate, parse, and open the config of the request's session. */
  async function admit<T>(c: Context, schema: z.ZodType<T>) {
    const principal = await helpers.authenticate(c.req.header('authorization'));
    const parsed = schema.safeParse(await c.req.json().catch(() => null));
    if (!parsed.success) {
      const issue = parsed.error.issues[0];
      const where = issue?.path.length ? `${issue.path.join('.')}: ` : '';
      throw new BadAiRequest(`Malformed AI request: ${where}${issue?.message ?? UNNAMED_ISSUE}`);
    }
    const session = helpers.configSession(c.req.header('x-config-session'));
    if (session) deps.sessions.sessionForExec(principal, session);
    const config = await deps.loadConfig(principal, session);
    return { principal, body: parsed.data, config };
  }

  function refusal(c: Context, error: unknown) {
    if (error instanceof BadAiRequest) return c.json({ error: error.message }, 400);
    const { status, message, code } = helpers.statusFor(error);
    return c.json({ error: message, ...(code ? { code } : {}) }, status);
  }

  app.post(AI_ROUTES.mode, async (c) => {
    try {
      const { principal, body, config } = await admit(c, ModeRequestSchema);
      const disabled = disabledModesFor(config, principal);
      if ((disabled as readonly string[]).includes(body.mode)) {
        return c.json(
          {
            error: `The ${body.mode} mode is disabled by your organization's policy (aiModesDisabled).`,
            code: AI_MODE_DISABLED,
            disabled,
          },
          403
        );
      }
      ai.modes.set(principal, body.conversationId, body.mode);
      return c.json({ conversationId: body.conversationId, mode: body.mode });
    } catch (error) {
      return refusal(c, error);
    }
  });

  app.post(AI_ROUTES.approval, async (c) => {
    try {
      const { principal, body, config } = await admit(c, ApprovalRequestSchema);
      const judged = await judgeApproval(body, helpers.requestScopedConfig(config));
      if ('refusal' in judged) return c.json(judged.refusal, 403);
      const { grand, destructive } = judged;

      const verdict = await ai.approvals.submit({ ...body, principal, destructive, grand });
      if (!verdict.ok) {
        return c.json({ error: verdict.message, code: verdict.code }, verdict.status);
      }
      return c.json(
        {
          conversationId: body.conversationId,
          toolCallId: body.toolCallId,
          decision: body.decision,
          stepUpMethod: body.stepUpMethod,
        },
        200,
        { 'Cache-Control': 'no-store' }
      );
    } catch (error) {
      return refusal(c, error);
    }
  });
}
