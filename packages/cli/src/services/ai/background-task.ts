/**
 * Executor background tasks (AX6 of agent/plans/PLAN-console-ai-in-pages.md, D5): an AI loop the
 * executor runs detached from the HTTP stream that started it.
 *
 * A task is a plan-4 run with the path key {@link TASK_PATH_KEY}, so it holds keep-awake and shows
 * as a pill; the run ends `succeeded`, `failed` or `cancelled`. The task's abort signal is its own:
 * the client that started it disconnecting never reaches it, only {@link BackgroundTasks.cancel}
 * and the end of the session do. A task uses its chat's mode and gate unchanged, so a destructive
 * proposal ends the step with an `approval_required` event, and the task then waits as
 * `needs_approval` rather than running the command: only {@link BackgroundTasks.approve} runs the
 * next step, and {@link BackgroundTasks.reject} ends the task. At most {@link MAX_TASKS_PER_USER}
 * tasks are live per user (running or waiting for an approval), a third is refused, and a task
 * whose session key is gone ends `failed` with {@link SESSION_EXPIRED_REASON}.
 *
 * The manager knows nothing about models or routes: the host passes the step that runs one turn.
 */

import type { AiEvent } from '@rediacc/shared/cli-contract/wire';

/** The plan-4 run path key every task is recorded under. */
export const TASK_PATH_KEY = 'ai.task';

/** D5: live tasks (running or waiting for an approval) per user. */
export const MAX_TASKS_PER_USER = 2;

/** The error code of a start the cap refused. */
export const AI_TASK_LIMIT = 'AI_TASK_LIMIT';

/** The reason a task ends `failed` once its session key is gone. */
export const SESSION_EXPIRED_REASON = 'The session key expired, so the task ended.';

/** What a task is doing: `needs_approval` is a task paused on a held command. */
export type TaskState = 'running' | 'needs_approval' | 'succeeded' | 'failed' | 'cancelled';

/** The end of a task's plan-4 run. */
export interface TaskEnd {
  state: 'succeeded' | 'failed' | 'cancelled';
  errorCode?: string;
}

/** The slice of a plan-4 run handle (run-index.ts) a task reports through. */
export interface TaskRun {
  end(outcome: TaskEnd): Promise<void>;
}

/** What one turn of a task is given. */
export interface TaskStep {
  /** The task's own signal: aborted by a cancel or a session end, never by a client leaving. */
  signal: AbortSignal;
  emit: (event: AiEvent) => void;
  /** True for the turn that follows an approved command. */
  resumed: boolean;
}

export interface TaskStart {
  /** Whose task this is: org, user and the like, joined into one key by the host. */
  owner: string;
  taskId: string;
  /** Runs one turn; a thrown error ends the task `failed`. */
  step: (input: TaskStep) => Promise<void>;
  run: TaskRun;
  /** False once the session key behind the task is gone. */
  sessionAlive: () => boolean;
}

/** A task as the routes report it. */
export interface TaskView {
  taskId: string;
  state: TaskState;
  /** Why a task ended `failed`. */
  reason?: string;
  events: number;
}

interface Task extends TaskStart {
  state: TaskState;
  reason?: string;
  abort: AbortController;
  events: AiEvent[];
  /** Resolves when the task's current step has ended; used by tests and shutdown. */
  settled: Promise<void>;
}

const LIVE: readonly TaskState[] = ['running', 'needs_approval'];

export type StartResult =
  | { ok: true; task: TaskView }
  | { ok: false; code: string; message: string };

export class BackgroundTasks {
  private readonly tasks = new Map<string, Task>();

  /** Start a task detached from the caller; refused when the owner already has the cap live. */
  start(input: TaskStart): StartResult {
    this.sweep();
    if (this.tasks.has(input.taskId)) {
      return { ok: false, code: 'AI_TASK_EXISTS', message: 'That task already exists.' };
    }
    if (this.liveOf(input.owner) >= MAX_TASKS_PER_USER) {
      return {
        ok: false,
        code: AI_TASK_LIMIT,
        message: `At most ${MAX_TASKS_PER_USER} background tasks run at once.`,
      };
    }
    const task: Task = {
      ...input,
      state: 'running',
      abort: new AbortController(),
      events: [],
      settled: Promise.resolve(),
    };
    this.tasks.set(input.taskId, task);
    this.advance(task, false);
    return { ok: true, task: viewOf(task) };
  }

  /** The owner's tasks, newest last; a task whose session ended is closed first. */
  list(owner: string): TaskView[] {
    this.sweep();
    return [...this.tasks.values()].filter((t) => t.owner === owner).map(viewOf);
  }

  get(owner: string, taskId: string): TaskView | undefined {
    this.sweep();
    const task = this.owned(owner, taskId);
    return task ? viewOf(task) : undefined;
  }

  /** The events a task has emitted, for the result card; undefined for a task the owner does not hold. */
  eventsOf(owner: string, taskId: string): AiEvent[] | undefined {
    return this.owned(owner, taskId)?.events;
  }

  /** The user approved the held command: the task runs its next step. False when it was not waiting. */
  approve(owner: string, taskId: string): boolean {
    const task = this.owned(owner, taskId);
    if (task?.state !== 'needs_approval') return false;
    task.state = 'running';
    this.advance(task, true);
    return true;
  }

  /** The user rejected the held command: the task ends `cancelled` without running it. */
  async reject(owner: string, taskId: string): Promise<boolean> {
    const task = this.owned(owner, taskId);
    if (task?.state !== 'needs_approval') return false;
    await this.finish(task, 'cancelled');
    return true;
  }

  /** Stop a live task now. */
  async cancel(owner: string, taskId: string): Promise<boolean> {
    const task = this.owned(owner, taskId);
    if (!task || !LIVE.includes(task.state)) return false;
    task.abort.abort();
    await this.finish(task, 'cancelled');
    return true;
  }

  /** Resolves once the task's current step has ended. */
  async settled(taskId: string): Promise<void> {
    await this.tasks.get(taskId)?.settled;
  }

  /** End every live task whose session key is gone. */
  sweep(): void {
    for (const task of this.tasks.values()) {
      if (LIVE.includes(task.state) && !task.sessionAlive()) {
        task.abort.abort();
        task.reason = SESSION_EXPIRED_REASON;
        this.finish(task, 'failed', SESSION_EXPIRED_REASON).catch(() => undefined);
      }
    }
  }

  private owned(owner: string, taskId: string): Task | undefined {
    const task = this.tasks.get(taskId);
    return task?.owner === owner ? task : undefined;
  }

  private liveOf(owner: string): number {
    let live = 0;
    for (const task of this.tasks.values()) {
      if (task.owner === owner && LIVE.includes(task.state)) live += 1;
    }
    return live;
  }

  private advance(task: Task, resumed: boolean): void {
    task.settled = this.runStep(task, resumed);
  }

  private async runStep(task: Task, resumed: boolean): Promise<void> {
    if (!task.sessionAlive()) {
      await this.finish(task, 'failed', SESSION_EXPIRED_REASON);
      return;
    }
    let held = false;
    let failure: string | undefined;
    try {
      await task.step({
        signal: task.abort.signal,
        resumed,
        emit: (event) => {
          task.events.push(event);
          if (event.type === 'approval_required') held = true;
          if (event.type === 'error') failure = event.message;
        },
      });
    } catch (error) {
      failure = error instanceof Error ? error.message : String(error);
    }
    if (task.state !== 'running') return;
    if (!task.sessionAlive()) await this.finish(task, 'failed', SESSION_EXPIRED_REASON);
    else if (failure !== undefined) await this.finish(task, 'failed', failure);
    else if (held) task.state = 'needs_approval';
    else await this.finish(task, 'succeeded');
  }

  private async finish(task: Task, state: TaskEnd['state'], reason?: string): Promise<void> {
    if (!LIVE.includes(task.state)) return;
    task.state = state;
    if (reason) task.reason = reason;
    await task.run
      .end({ state, ...(reason ? { errorCode: 'AI_TASK_FAILED' } : {}) })
      .catch(() => undefined);
  }
}

function viewOf(task: Task): TaskView {
  return {
    taskId: task.taskId,
    state: task.state,
    ...(task.reason ? { reason: task.reason } : {}),
    events: task.events.length,
  };
}
