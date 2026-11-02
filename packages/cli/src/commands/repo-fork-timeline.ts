/**
 * The timeline rendering of `rdc repo fork`: the streamed renet-event handler and the final
 * timeline, timing summary and total. The fork orchestration lives in repo-fork.ts.
 */

import { t } from '../i18n/index.js';
import { outputService } from '../services/core/output.js';
import { writeStderr, writeStdout } from '../services/core/request-context.js';
import { type ExecuteResult, type RenetEvent } from '../services/executor/executor-factory.js';
import { debugEnabled } from '../utils/debug.js';
import {
  buildTimingSummary,
  formatStepDuration,
  getActiveLabel,
  getDoneLine,
  type TimelineStep,
} from '../utils/timeline.js';
import type { ForkPlan } from './repo-fork.js';

/** Print one completed-step line in the streamed timeline format. */
function printStepLine(step: TimelineStep): void {
  writeStdout(
    `✔ ${getDoneLine(step.name, step.detail)} (${formatStepDuration(step.duration_ms)})\n`
  );
}

/** Print "Total: <wall>" once at the true end and mark the timeline rendered. */
function renderTimelineTotal(wallMs: number): void {
  writeStdout(`\nTotal: ${formatStepDuration(wallMs)}\n`);
  outputService.setTimelineRendered();
}

/** Handle a log event: only show errors/warnings. */
function handleLogEvent(event: RenetEvent): void {
  if (event.level === 'error' || event.level === 'fatal' || event.level === 'warning') {
    writeStderr(`  ${event.msg ?? ''}\n`);
  }
}

/** Handle a step_done event: render and record the step. */
function handleStepDoneEvent(
  event: RenetEvent,
  allSteps: TimelineStep[],
  startedAtMs?: number
): void {
  if (!event.name || event.duration_ms === undefined) return;
  writeStdout(
    `\r✔ ${getDoneLine(event.name, event.detail)} (${formatStepDuration(event.duration_ms)})\n`
  );
  allSteps.push({
    name: event.name,
    duration_ms: event.duration_ms,
    detail: event.detail,
    ...(startedAtMs === undefined ? {} : { startedAtMs }),
  });
}

/** Create an event handler for streaming renet events during fork/up legs. */
export function createForkEventHandler(allSteps: TimelineStep[]): (event: RenetEvent) => void {
  // step_start arrival times anchor the end-of-run waterfall chart.
  const stepStarts = new Map<string, number>();
  return (event: RenetEvent) => {
    switch (event.type) {
      case 'log':
        handleLogEvent(event);
        break;
      case 'step_start':
        if (event.name) stepStarts.set(event.name, Date.now());
        writeStdout(`⠋ ${getActiveLabel(event.name ?? '')}...`);
        break;
      case 'step_done': {
        const startedAtMs = event.name ? stepStarts.get(event.name) : undefined;
        if (event.name) stepStarts.delete(event.name);
        handleStepDoneEvent(event, allSteps, startedAtMs);
        break;
      }
      case 'output':
        if (
          event.msg &&
          (event.msg.includes('✔') || event.msg.includes('✗') || event.msg.includes('Error'))
        ) {
          writeStdout(`  ${event.msg}`);
        }
        break;
    }
  };
}

/**
 * Render the end-of-run timing charts (bars + waterfall + attribution).
 * TTY-gated; REDIACC_DEBUG=timing (or 1/*) forces rendering for piped output.
 */
function printTimingSummary(plan: ForkPlan, steps: TimelineStep[], wallMs: number): void {
  if (!process.stdout.isTTY && !debugEnabled('timing')) return;
  const summary = buildTimingSummary(steps, wallMs, {
    epochMs: plan.startedAt,
    suggestDetach: Boolean(plan.options.up && !plan.options.detach),
  });
  if (summary) writeStdout(`\n${summary}\n`);
}

/**
 * Render the final timeline: CLI steps from each execute leg (recorded but
 * not streamed under quietSpinners), then orchestrated phases, then a single
 * wall-clock Total. Streamed renet steps were already printed live.
 */
export function finishTimeline(
  plan: ForkPlan,
  orchestrated: TimelineStep[],
  renetSteps: TimelineStep[],
  results: (ExecuteResult | undefined)[]
): void {
  const cliSteps = results.flatMap((r) => r?.cliSteps ?? []);
  for (const step of cliSteps) {
    printStepLine(step);
  }
  for (const step of orchestrated) {
    printStepLine(step);
  }
  if (cliSteps.length + orchestrated.length + renetSteps.length > 0) {
    const wallMs = Date.now() - plan.startedAt;
    renderTimelineTotal(wallMs);
    if (plan.options.detach && plan.options.up) {
      outputService.info(t('commands.repo.fork.detachedHint', { machine: plan.options.machine }));
    }
    printTimingSummary(plan, [...cliSteps, ...orchestrated, ...renetSteps], wallMs);
  } else {
    outputService.success(
      t('commands.repo.fork.completed', {
        repository: plan.forkKey,
        machine: plan.options.machine,
      })
    );
  }
}
