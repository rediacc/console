/**
 * The task routes (ai-task-routes.ts) driven directly: the run an accepted start records, the
 * single-call answer, and the resume message that names the call the approval released.
 */

import type { AiEvent } from '@rediacc/shared/cli-contract/wire';
import { Hono } from 'hono';
import { describe, expect, it, vi } from 'vitest';
import { TASK_PATH_KEY, type TaskStep } from '../../ai/background-task.js';
import {
  AI_TASK_ROUTES,
  type PreparedTask,
  registerTaskRoutes,
  resumeMessageFor,
  TASK_RESUME_MESSAGE,
} from '../ai-task-routes.js';
import type { ServeDeps } from '../deps.js';
import type { SessionPrincipal } from '../sessions.js';

const ALICE: SessionPrincipal = {
  orgId: 'org-1',
  teamId: null,
  userId: 'user-alice',
  userEmail: 'alice@example.com',
  orgRole: 'owner',
};

const held = (toolCallId: string): AiEvent =>
  ({
    type: 'approval_required',
    toolCallId,
    name: 'repo_down',
    input: { ref: 'shop' },
    approvalToken: 'tok',
    command: { pathKey: 'repo down', params: {}, positionals: {} },
    risk: 'destructive',
  }) as AiEvent;

function build() {
  const begun: { pathKey: string }[] = [];
  const ended: unknown[] = [];
  const resumes: TaskStep['held'][] = [];
  const deps = {
    sessions: { sessionForExec: () => undefined },
    runIndex: {
      begin: (run: { pathKey: string }) => {
        begun.push(run);
        return {
          end: (outcome: unknown) => {
            ended.push(outcome);
            return Promise.resolve();
          },
        };
      },
    },
  } as unknown as ServeDeps;
  const app = new Hono();
  const routes = registerTaskRoutes(app, {
    deps,
    helpers: { authenticate: () => Promise.resolve(ALICE) } as never,
    refusal: (c, error) => c.json({ error: String(error) }, 500),
    prepare: (c) => {
      const id = c.req.query('id') ?? 'conv-1';
      const prepared: PreparedTask = {
        principal: ALICE,
        conversationId: id,
        configSessionId: undefined,
        step: ({ emit, resumed, held: released }) => {
          if (resumed) resumes.push(released);
          else emit(held('call-1'));
          return Promise.resolve();
        },
      };
      return Promise.resolve(prepared);
    },
  });
  const start = (id: string) => app.request(`${AI_TASK_ROUTES.tasks}?id=${id}`, { method: 'POST' });
  const stateOf = async (id: string) =>
    ((await (await app.request(`${AI_TASK_ROUTES.tasks}/${id}`)).json()) as { state: string })
      .state;
  return { app, routes, start, stateOf, begun, ended, resumes };
}

describe('task routes', () => {
  it('records an accepted start as one ai.task run and a refused start as none', async () => {
    const t = build();
    expect((await t.start('c1')).status).toBe(202);
    expect(t.begun).toEqual([expect.objectContaining({ pathKey: TASK_PATH_KEY })]);
    expect((await t.start('c1')).status).toBe(409);
    expect(t.begun).toHaveLength(1);
    expect((await t.start('c2')).status).toBe(202);
    const third = await t.start('c3');
    expect(third.status).toBe(429);
    expect(t.begun).toHaveLength(2);
    expect(t.ended).toEqual([]);
  });

  it('answers only the held call, and resumes the model with that call named', async () => {
    const t = build();
    await t.start('c1');
    await vi.waitFor(async () => expect(await t.stateOf('c1')).toBe('needs_approval'));
    // Another call's approval in the same conversation leaves the task paused.
    await t.routes.answer(ALICE, {
      conversationId: 'c1',
      toolCallId: 'call-other',
      decision: 'approve',
    });
    expect(await t.stateOf('c1')).toBe('needs_approval');
    await t.routes.answer(ALICE, {
      conversationId: 'c1',
      toolCallId: 'call-other',
      decision: 'reject',
    });
    expect(await t.stateOf('c1')).toBe('needs_approval');
    // The held call's own approval resumes it, handing the step the call it released.
    await t.routes.answer(ALICE, {
      conversationId: 'c1',
      toolCallId: 'call-1',
      decision: 'approve',
    });
    await vi.waitFor(async () => expect(await t.stateOf('c1')).toBe('succeeded'));
    expect(t.resumes).toEqual([
      { toolCallId: 'call-1', name: 'repo_down', input: { ref: 'shop' } },
    ]);
  });
});

describe('resumeMessageFor', () => {
  it('names the tool and input the approval released', () => {
    const message = resumeMessageFor({
      toolCallId: 'c',
      name: 'repo_down',
      input: { ref: 'shop' },
    });
    expect(message).toContain('repo_down');
    expect(message).toContain('{"ref":"shop"}');
  });

  it('falls back to the plain message with no held call, and bounds the input', () => {
    expect(resumeMessageFor(undefined)).toBe(TASK_RESUME_MESSAGE);
    const long = resumeMessageFor({ toolCallId: 'c', name: 'x', input: 'y'.repeat(9000) });
    expect(long.length).toBeLessThan(2300);
  });
});
