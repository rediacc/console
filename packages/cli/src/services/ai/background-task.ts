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
type TaskState = 'running' | 'needs_approval' | 'succeeded' | 'failed' | 'cancelled';

/** The end of a task's plan-4 run. */
export interface TaskEnd {
  state: 'succeeded' | 'failed' | 'cancelled';
  errorCode?: string;
}

/** The slice of a plan-4 run handle (run-index.ts) a task reports through. */
export interface TaskRun {
  end(outcome: TaskEnd): Promise<void>;
}

/** The command a task is paused on: what the resumed turn tells the model it approved. */
export interface HeldCall {
  toolCallId: string;
  name: string;
  input: unknown;
}

/** D5: finished tasks kept per user for the result card; the oldest finished one goes first. */
export const MAX_FINISHED_PER_USER = 20;

/** What one turn of a task is given. */
export interface TaskStep {
  /** The task's own signal: aborted by a cancel or a session end, never by a client leaving. */
  signal: AbortSignal;
  emit: (event: AiEvent) => void;
  /** True for the turn that follows an approved command. */
  resumed: boolean;
  /** The command the approval released, on a resumed turn. */
  held?: HeldCall;
}

export interface TaskStart {
  /** Whose task this is: org, user and the like, joined into one key by the host. */
  owner: string;
  taskId: string;
  /** Runs one turn; a thrown error ends the task `failed`. */
  step: (input: TaskStep) => Promise<void>;
  /** Opens the task's run record; called only once the start is accepted, so a refused start leaves no run behind. */
  beginRun: () => TaskRun;
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
  run: TaskRun;
  state: TaskState;
  reason?: string;
  abort: AbortController;
  events: AiEvent[];
  /** The command the task is paused on. */
  held?: HeldCall;
  /** Resolves when the task's current step has ended; used by tests and shutdown. */
  settled: Promise<void>;
}

const LIVE: ReadonlySet<TaskState> = new Set<TaskState>(['running', 'needs_approval']);

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
      run: input.beginRun(),
      state: 'running',
      abort: new AbortController(),
      events: [],
      settled: Promise.resolve(),
    };
    this.tasks.set(input.taskId, task);
    this.advance(task, false);
    // Once the new task is in: a task that ends at once is finished already, and the cap is for what stays.
    this.pruneFinished(input.owner);
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

  /** The user approved the held command: the task runs its next step. False when it was not waiting, or `toolCallId` is another call's. */
  approve(owner: string, taskId: string, toolCallId?: string): boolean {
    const task = this.owned(owner, taskId);
    if (task?.state !== 'needs_approval' || !this.holds(task, toolCallId)) return false;
    task.state = 'running';
    this.advance(task, true);
    return true;
  }

  /** The user rejected the held command: the task ends `cancelled` without running it. */
  async reject(owner: string, taskId: string, toolCallId?: string): Promise<boolean> {
    const task = this.owned(owner, taskId);
    if (task?.state !== 'needs_approval' || !this.holds(task, toolCallId)) return false;
    await this.finish(task, 'cancelled');
    return true;
  }

  /** Stop a live task now. */
  async cancel(owner: string, taskId: string): Promise<boolean> {
    const task = this.owned(owner, taskId);
    if (!task || !LIVE.has(task.state)) return false;
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
      if (LIVE.has(task.state) && !task.sessionAlive()) {
        task.abort.abort();
        task.reason = SESSION_EXPIRED_REASON;
        this.finish(task, 'failed', SESSION_EXPIRED_REASON).catch(() => undefined);
      }
    }
  }

  /** True when no call is named or the task is paused on the named one. */
  private holds(task: Task, toolCallId: string | undefined): boolean {
    return toolCallId === undefined || task.held?.toolCallId === toolCallId;
  }

  /** Drop the owner's oldest finished tasks beyond {@link MAX_FINISHED_PER_USER}; a live task is never dropped. */
  private pruneFinished(owner: string): void {
    const finished = [...this.tasks.values()].filter(
      (t) => t.owner === owner && !LIVE.has(t.state)
    );
    for (const task of finished.slice(0, Math.max(0, finished.length - MAX_FINISHED_PER_USER))) {
      this.tasks.delete(task.taskId);
    }
  }

  private owned(owner: string, taskId: string): Task | undefined {
    const task = this.tasks.get(taskId);
    return task?.owner === owner ? task : undefined;
  }

  private liveOf(owner: string): number {
    let live = 0;
    for (const task of this.tasks.values()) {
      if (task.owner === owner && LIVE.has(task.state)) live += 1;
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
    const seen: StepSeen = {};
    const released = task.held;
    try {
      await task.step({
        signal: task.abort.signal,
        resumed,
        ...(resumed && released ? { held: released } : {}),
        emit: (event) => noteEvent(task, event, seen),
      });
    } catch (error) {
      seen.failure = error instanceof Error ? error.message : String(error);
    }
    await this.settleStep(task, seen);
  }

  /** Where a task stands once a step ended: failed, paused on a held command, or done. */
  private async settleStep(task: Task, seen: StepSeen): Promise<void> {
    if (task.state !== 'running') return;
    if (!task.sessionAlive()) await this.finish(task, 'failed', SESSION_EXPIRED_REASON);
    else if (seen.failure !== undefined) await this.finish(task, 'failed', seen.failure);
    else if (seen.held) {
      task.held = seen.held;
      task.state = 'needs_approval';
    } else await this.finish(task, 'succeeded');
  }

  private async finish(task: Task, state: TaskEnd['state'], reason?: string): Promise<void> {
    if (!LIVE.has(task.state)) return;
    task.state = state;
    if (reason) task.reason = reason;
    await task.run
      .end({ state, ...(reason ? { errorCode: 'AI_TASK_FAILED' } : {}) })
      .catch(() => undefined);
  }
}

/** What one step reported: the command it paused on, or the failure it ended with. */
interface StepSeen {
  held?: HeldCall;
  failure?: string;
}

/** Keep an event of a step and note a hold or a failure it carries. */
function noteEvent(task: Task, event: AiEvent, seen: StepSeen): void {
  task.events.push(event);
  if (event.type === 'approval_required') {
    seen.held = { toolCallId: event.toolCallId, name: event.name, input: event.input };
  }
  if (event.type === 'error') seen.failure = event.message;
}

function viewOf(task: Task): TaskView {
  return {
    taskId: task.taskId,
    state: task.state,
    ...(task.reason ? { reason: task.reason } : {}),
    events: task.events.length,
  };
}
