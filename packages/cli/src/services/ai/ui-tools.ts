/**
 * The model's UI tools (AI3 of agent/plans/PLAN-console-ai-assistant.md, D1): `plan` shows the
 * steps the model intends to take as a checklist, and `present` shows a structured answer (a
 * table, a status line, or choice chips). Neither runs anything: the input is validated against
 * the wire schema, the loop turns the call into its own typed `plan` or `present` event in place of
 * a `tool_call`/`tool_result` pair, and the model reads a one-line acknowledgement.
 *
 * The names are reserved: a registry tool can never be called `plan` or `present`, and a test holds
 * that.
 */

import { type AiEvent, AiPresentCardSchema } from '@rediacc/shared/cli-contract/wire';
import { type ToolSet, tool } from 'ai';
import { z } from 'zod';

export const PLAN_TOOL = 'plan';
export const PRESENT_TOOL = 'present';

/** The tool names the loop renders as their own events. */
export const UI_TOOL_NAMES: ReadonlySet<string> = new Set([PLAN_TOOL, PRESENT_TOOL]);

const PlanInputSchema = z.strictObject({
  steps: z
    .array(z.strictObject({ title: z.string().min(1).max(500) }))
    .min(1)
    .max(30),
});

const PresentInputSchema = z.strictObject({ card: AiPresentCardSchema });

/** What a UI tool answers the model: nothing it could read as data from the user. */
const SHOWN = { shown: true } as const;

/** The `plan` and `present` tools of one chat. */
export function uiTools(): ToolSet {
  return {
    [PLAN_TOOL]: tool({
      description:
        'Shows the user the intended steps as a checklist before commands run. Runs nothing.',
      inputSchema: PlanInputSchema,
      execute: () => Promise.resolve(SHOWN),
    }),
    [PRESENT_TOOL]: tool({
      description:
        'Shows the user a structured answer: a table, a status line, or choice chips to pick from. Runs nothing.',
      inputSchema: PresentInputSchema,
      execute: () => Promise.resolve(SHOWN),
    }),
  };
}

/** The typed event of a UI tool call, or null when the name is not a UI tool or the input does not parse. */
export function uiEventOf(part: {
  toolCallId: string;
  toolName: string;
  input: unknown;
}): AiEvent | null {
  if (part.toolName === PLAN_TOOL) {
    const parsed = PlanInputSchema.safeParse(part.input);
    return parsed.success
      ? { type: 'plan', toolCallId: part.toolCallId, steps: parsed.data.steps }
      : null;
  }
  if (part.toolName === PRESENT_TOOL) {
    const parsed = PresentInputSchema.safeParse(part.input);
    return parsed.success
      ? { type: 'present', toolCallId: part.toolCallId, card: parsed.data.card }
      : null;
  }
  return null;
}
