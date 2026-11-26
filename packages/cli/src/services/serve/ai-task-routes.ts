/**
 * The executor's background task routes (AX6 of agent/plans/PLAN-console-ai-in-pages.md, D5),
 * registered beside the chat routes of ai-routes.ts, which build the turn a task runs.
 *
 * `POST /v1/ai/tasks` starts the chat body as a task (services/ai/background-task.ts): one task per
 * conversation, two live per user (`AI_TASK_LIMIT`, 429), recorded as an `ai.task` plan-4 run. The
 * answer is 202 and the task runs on, whatever the client does next. `GET /v1/ai/tasks` lists the
 * caller's tasks, `GET /v1/ai/tasks/:conversationId` reads one with its events, and `POST
 * .../cancel` stops one. The approval route answers a paused task through {@link TaskRoutes.answer}.
 */

import type { Context, Hono } from 'hono';
import {
  AI_TASK_LIMIT,
  BackgroundTasks,
  type HeldCall,
  TASK_PATH_KEY,
  type TaskRun,
  type TaskStep,
} from '../ai/background-task.js';
import type { ServeDeps } from './deps.js';
import type { JobRouteHelpers } from './job-routes.js';
import type { SessionPrincipal } from './sessions.js';

export const AI_TASK_ROUTES = {
  tasks: '/v1/ai/tasks',
  task: '/v1/ai/tasks/:conversationId',
  taskCancel: '/v1/ai/tasks/:conversationId/cancel',
} as const;

/** The user message a task resumes with once its held command was approved. */
export const TASK_RESUME_MESSAGE = 'The command you proposed was approved. Run it now.';

/** The longest input of the held call a resume message repeats. */
const MAX_HELD_INPUT_CHARS = 2000;

/** The resume message, naming the call the approval released: the resumed turn starts from the request alone, so the model never saw it. */
export function resumeMessageFor(held: HeldCall | undefined): string {
  if (!held) return TASK_RESUME_MESSAGE;
  const input = JSON.stringify(held.input ?? {}).slice(0, MAX_HELD_INPUT_CHARS);
  return `The command you proposed (the ${held.name} tool with input ${input}) was approved. Run it now.`;
}

const UNKNOWN_TASK = 'AI_TASK_UNKNOWN';
const NO_STORE = { 'Cache-Control': 'no-store' };

/** What a task is started from: whose it is, which session key it lives on, and its turn. */
export interface PreparedTask {
  principal: SessionPrincipal;
  conversationId: string;
  configSessionId: string | undefined;
  step: (input: TaskStep) => Promise<void>;
}

export interface TaskRoutes {
  /** The user's answer to the command a task holds: approve runs its next step, a rejection ends it. Only the held call's own id answers it. */
  answer: (
    principal: SessionPrincipal,
    answer: { conversationId: string; toolCallId: string; decision: 'approve' | 'reject' }
  ) => Promise<void>;
}

/** One key per user, so the cap and every task route are the caller's own. */
const ownerOf = (principal: SessionPrincipal) => `${principal.orgId}\u0000${principal.userId}`;

export function registerTaskRoutes(
  app: Hono,
  host: {
    deps: ServeDeps;
    helpers: JobRouteHelpers;
    refusal: (c: Context, error: unknown) => Response;
    prepare: (c: Context) => Promise<PreparedTask | Response>;
  }
): TaskRoutes {
  const { deps, helpers, refusal } = host;
  const tasks = new BackgroundTasks();

  /** The plan-4 run of a task: `ai.task`, or nothing where no run index is wired. */
  const runOf = (principal: SessionPrincipal): TaskRun => {
    const run = deps.runIndex?.begin({ principal, pathKey: TASK_PATH_KEY });
    return { end: (outcome) => run?.end(outcome) ?? Promise.resolve() };
  };

  /** False once the session key the task runs on is gone; a task on no named session has none to lose. */
  const aliveOf = (prepared: PreparedTask) => () => {
    if (!prepared.configSessionId) return true;
    try {
      deps.sessions.sessionForExec(prepared.principal, prepared.configSessionId);
      return true;
    } catch {
      return false;
    }
  };

  app.post(AI_TASK_ROUTES.tasks, async (c) => {
    try {
      const prepared = await host.prepare(c);
      if (prepared instanceof Response) return prepared;
      const started = tasks.start({
        owner: ownerOf(prepared.principal),
        taskId: prepared.conversationId,
        step: prepared.step,
        beginRun: () => runOf(prepared.principal),
        sessionAlive: aliveOf(prepared),
      });
      if (started.ok) return c.json(started.task, 202);
      return c.json(
        { error: started.message, code: started.code },
        started.code === AI_TASK_LIMIT ? 429 : 409
      );
    } catch (error) {
      return refusal(c, error);
    }
  });

  app.get(AI_TASK_ROUTES.tasks, async (c) => {
    try {
      const principal = await helpers.authenticate(c.req.header('authorization'));
      return c.json({ tasks: tasks.list(ownerOf(principal)) }, 200, NO_STORE);
    } catch (error) {
      return refusal(c, error);
    }
  });

  app.get(AI_TASK_ROUTES.task, async (c) => {
    try {
      const owner = ownerOf(await helpers.authenticate(c.req.header('authorization')));
      const id = c.req.param('conversationId');
      const task = tasks.get(owner, id);
      if (!task) return c.json({ error: 'Unknown task.', code: UNKNOWN_TASK }, 404);
      return c.json({ ...task, events: tasks.eventsOf(owner, id) ?? [] }, 200, NO_STORE);
    } catch (error) {
      return refusal(c, error);
    }
  });

  app.post(AI_TASK_ROUTES.taskCancel, async (c) => {
    try {
      const owner = ownerOf(await helpers.authenticate(c.req.header('authorization')));
      const id = c.req.param('conversationId');
      if (!(await tasks.cancel(owner, id))) {
        return c.json({ error: 'No live task to cancel.', code: UNKNOWN_TASK }, 404);
      }
      return c.json({ conversationId: id, state: 'cancelled' });
    } catch (error) {
      return refusal(c, error);
    }
  });

  return {
    answer: async (principal, { conversationId, toolCallId, decision }) => {
      if (decision === 'approve') tasks.approve(ownerOf(principal), conversationId, toolCallId);
      else await tasks.reject(ownerOf(principal), conversationId, toolCallId);
    },
  };
}
