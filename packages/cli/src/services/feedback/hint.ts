/**
 * The failure hint: one pointer to `rdc feedback report --last` after a command
 * fails. It is on for every caller, CI and agents included, and
 * `REDIACC_FEEDBACK_HINT=0` turns it off.
 */
import { t } from '../../i18n/index.js';
import type { NextAction } from '../../types/errors.js';
import { EXIT_CODES } from '../../types/index.js';
import { currentRequestContext, writeStderr } from '../core/request-context.js';
import { commandWords } from './redact.js';

const FEEDBACK_HINT_RUN = 'rdc feedback report --last';

export interface HintContext {
  argv: readonly string[];
  exitCode: number;
}

/** Whether the hint applies: not disabled, not a usage error, not a failing `feedback`, not a served request. */
export function shouldHint(ctx: HintContext): boolean {
  if (process.env.REDIACC_FEEDBACK_HINT === '0') return false;
  if (ctx.exitCode === 0 || ctx.exitCode === EXIT_CODES.INVALID_ARGUMENTS) return false;
  if (currentRequestContext() !== undefined) return false;
  return commandWords(ctx.argv)[0] !== 'feedback';
}

/** The stderr line, or undefined when the hint does not apply. */
export function feedbackHint(ctx: HintContext): string | undefined {
  return shouldHint(ctx) ? t('feedback.hint', { run: FEEDBACK_HINT_RUN }) : undefined;
}

/** The error's `next` with the report option appended (a summary is created when the error had none). */
export function withFeedbackOption(
  next: NextAction | undefined,
  ctx: HintContext
): NextAction | undefined {
  if (!shouldHint(ctx)) return next;
  const option = { description: t('feedback.hintDescription'), run: FEEDBACK_HINT_RUN };
  return {
    summary: next?.summary ?? t('feedback.hintSummary'),
    options: [...(next?.options ?? []), option],
  };
}

/** Write the hint line to stderr when it applies. */
export function printFeedbackHint(ctx: HintContext): void {
  const line = feedbackHint(ctx);
  if (line) writeStderr(`${line}\n`);
}
