/**
 * The local MCP server maps the child's policy answer to MCP (PLAN-rmcp-local-mcp LM4, Design 7): the
 * executor lifts the refusal the child prints, a `deny` becomes an `isError` result with
 * `structuredContent { code, reason, next }`, and a `needs_confirmation` becomes a form-mode elicitation
 * when the client declared one, else an error naming the `confirm` argument.
 */
import { Client, InMemoryTransport } from '@modelcontextprotocol/client';
import type { CallToolResult } from '@modelcontextprotocol/server';
import { McpServer } from '@modelcontextprotocol/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import { type ExecutionResult, executeRdcCommand, runUnderPolicy } from '../executor.js';
import { MCP_SERVER_OPTIONS } from '../server.js';

const mockExecFile = vi.fn();
vi.mock('node:child_process', () => ({
  execFile: (...args: unknown[]) => mockExecFile(...args),
}));

/** The envelope the child prints for a refusal of its policy check (exit 2), as `rdc repo down foo` printed it. */
function refusalEnvelope(details: string[], message = 'translated refusal') {
  return JSON.stringify({
    success: false,
    command: 'unknown',
    data: null,
    errors: [{ code: 'VALIDATION_ERROR', origin: 'user', message, details, retryable: false }],
    warnings: [],
    metrics: { duration_ms: 0 },
  });
}

function childExits(stdout: string) {
  mockExecFile.mockImplementation(
    (_cmd: string, _args: string[], _opts: unknown, callback: (...args: unknown[]) => void) => {
      const err = Object.assign(new Error('Command failed'), { stdout, stderr: '', code: 2 });
      callback(err);
    }
  );
}

const baseOptions = { defaultTimeoutMs: 1000 };
const REASON =
  '"rdc repo down" is destructive and would change foo, a grand repo. Confirm to proceed.';

afterEach(() => {
  vi.clearAllMocks();
});

describe('executeRdcCommand lifts the child policy refusal', () => {
  it('a deny code becomes decision.verdict deny with the command past it', async () => {
    childExits(
      refusalEnvelope(['GRAND_REPO_DENIED', 'would change foo', 'rdc repo fork foo --tag <tag>'])
    );
    const result = await executeRdcCommand(['repo', 'down', 'foo'], baseOptions);
    expect(result.decision).toEqual({
      verdict: 'deny',
      code: 'GRAND_REPO_DENIED',
      reason: 'would change foo',
      message: 'translated refusal',
      next: { run: 'rdc repo fork foo --tag <tag>' },
    });
  });

  it('CONFIRMATION_REQUIRED becomes needs_confirmation with the confirm value after the flag', async () => {
    childExits(refusalEnvelope(['CONFIRMATION_REQUIRED', REASON, '--confirm-grand foo']));
    const result = await executeRdcCommand(['repo', 'down', 'foo'], baseOptions);
    expect(result.decision?.verdict).toBe('needs_confirmation');
    expect(result.decision?.next).toEqual({ confirm: { argument: 'confirm', value: 'foo' } });
  });

  it('control: a VALIDATION_ERROR that names no decision code carries no decision', async () => {
    childExits(refusalEnvelope(['some other detail']));
    const result = await executeRdcCommand(['repo', 'down', 'foo'], baseOptions);
    expect(result.success).toBe(false);
    expect(result.decision).toBeUndefined();
  });

  it('the confirm option repeats the value after --confirm-grand', async () => {
    childExits(refusalEnvelope(['AGENT_BLOCKED', 'not for agents']));
    await executeRdcCommand(['repo', 'down', 'foo'], { ...baseOptions, confirm: 'foo' });
    const argv = mockExecFile.mock.calls[0][1] as string[];
    expect(argv.slice(-2)).toEqual(['--confirm-grand', 'foo']);
  });
});

const OK: ExecutionResult = {
  success: true,
  command: 'repo down',
  data: { ran: true },
  errors: null,
  warnings: [],
  duration_ms: 1,
};

function refused(
  verdict: 'deny' | 'needs_confirmation',
  next?: ExecutionResult['decision'] extends infer D
    ? D extends { next?: infer N }
      ? N
      : never
    : never
): ExecutionResult {
  return {
    success: false,
    command: 'repo down',
    data: null,
    errors: [{ code: 'VALIDATION_ERROR' }],
    warnings: [],
    duration_ms: 0,
    decision: {
      verdict,
      code: verdict === 'deny' ? 'AGENT_OPT_IN_MISSING' : 'CONFIRMATION_REQUIRED',
      reason: REASON,
      message: 'translated refusal',
      ...(next ? { next } : {}),
    },
  };
}

const CONFIRM_NEXT = { confirm: { argument: 'confirm' as const, value: 'foo' } };

/** The child: refuses until it is confirmed with `accepts`, then runs. */
function childConfirmedBy(accepts: string | null) {
  return vi.fn(async (confirm: string | undefined) =>
    accepts !== null && confirm === accepts ? OK : refused('needs_confirmation', CONFIRM_NEXT)
  );
}

const servers: McpServer[] = [];
const clients: Client[] = [];

afterEach(async () => {
  for (const c of clients.splice(0)) await c.close();
  for (const s of servers.splice(0)) await s.close();
});

interface Setup {
  run: (confirm: string | undefined) => Promise<ExecutionResult>;
  era?: 'auto' | 'legacy';
  elicit?: (message: string) => { action: 'accept' | 'decline' | 'cancel'; confirm?: boolean };
}

/** A server built with the stdio server's options and one tool that runs `run` under the policy mapping. */
async function connect({ run, era = 'auto', elicit }: Setup): Promise<Client> {
  const server = new McpServer({ name: 'rdc', version: '0.0.0' }, MCP_SERVER_OPTIONS);
  server.registerTool(
    'repo_down',
    { inputSchema: z.object({ name: z.string(), confirm: z.string().optional() }) },
    async (args, ctx) => {
      const outcome = await runUnderPolicy({ server, ctx, tool: 'repo_down', args }, (confirm) =>
        run(confirm)
      );
      if ('answer' in outcome) return outcome.answer;
      return { content: [{ type: 'text', text: JSON.stringify(outcome.result) }] };
    }
  );
  servers.push(server);
  const client = new Client(
    { name: 'lm4-test', version: '0.0.0' },
    {
      versionNegotiation: { mode: era },
      ...(elicit ? { capabilities: { elicitation: { form: {} } } } : {}),
    }
  );
  if (elicit) {
    client.setRequestHandler('elicitation/create', (request) => {
      const answer = elicit(request.params.message);
      return {
        action: answer.action,
        ...(answer.action === 'accept' ? { content: { confirm: answer.confirm ?? true } } : {}),
      };
    });
  }
  clients.push(client);
  const [clientSide, serverSide] = InMemoryTransport.createLinkedPair();
  await server.connect(serverSide);
  await client.connect(clientSide);
  return client;
}

async function call(client: Client, args: Record<string, unknown>): Promise<CallToolResult> {
  return (await client.callTool({ name: 'repo_down', arguments: args })) as CallToolResult;
}

const textOf = (result: CallToolResult) => (result.content[0] as { text: string }).text;

describe('runUnderPolicy maps the decision to MCP', () => {
  it('a deny is an isError result with structuredContent { code, reason, next }', async () => {
    const next = { run: 'rdc repo fork foo --tag <tag>' };
    const client = await connect({ run: async () => refused('deny', next) });
    const result = await call(client, { name: 'foo' });
    expect(result.isError).toBe(true);
    expect(result.structuredContent).toEqual({
      code: 'AGENT_OPT_IN_MISSING',
      reason: REASON,
      next,
    });
    expect(textOf(result)).toBe('translated refusal');
  });

  it('needs_confirmation without elicitation names the confirm argument and its value', async () => {
    const run = childConfirmedBy('foo');
    const client = await connect({ run });
    const result = await call(client, { name: 'foo' });
    expect(result.isError).toBe(true);
    expect(result.structuredContent).toEqual({
      code: 'CONFIRMATION_REQUIRED',
      reason: REASON,
      next: CONFIRM_NEXT,
    });
    expect(textOf(result)).toContain('repo_down');
    expect(textOf(result)).toContain('confirm set to "foo"');
    expect(run).toHaveBeenCalledTimes(1);
  });

  it('the retry carrying the confirm argument runs the child with that value', async () => {
    const run = childConfirmedBy('foo');
    const client = await connect({ run });
    const result = await call(client, { name: 'foo', confirm: 'foo' });
    expect(result.isError).not.toBe(true);
    expect(run).toHaveBeenCalledWith('foo');
    expect(JSON.parse(textOf(result)).data).toEqual({ ran: true });
  });

  it('a confirm value the child still refuses is answered once, not asked again', async () => {
    const run = childConfirmedBy('foo');
    const client = await connect({ run });
    const result = await call(client, { name: 'foo', confirm: 'bar' });
    expect(result.isError).toBe(true);
    expect(run).toHaveBeenCalledTimes(1);
  });

  it('a client that can elicit and sends confirm on its first call is still asked, and the argument is not run', async () => {
    const run = childConfirmedBy('foo');
    const elicit = vi.fn(() => ({ action: 'accept' as const }));
    const client = await connect({ run, elicit });
    const result = await call(client, { name: 'foo', confirm: 'foo' });
    expect(elicit).toHaveBeenCalledWith(REASON);
    expect(run.mock.calls.map(([confirm]) => confirm)).toEqual([undefined, 'foo']);
    expect(result.isError).not.toBe(true);
  });

  it('a client that can elicit, sends confirm and declines runs the child only unconfirmed', async () => {
    const run = childConfirmedBy('foo');
    const client = await connect({ run, elicit: () => ({ action: 'decline' }) });
    const result = await call(client, { name: 'foo', confirm: 'foo' });
    expect(result.isError).toBe(true);
    expect(run.mock.calls.map(([confirm]) => confirm)).toEqual([undefined]);
  });

  it('control: a needs_confirmation detail without the --confirm-grand prefix is a plain refusal with no next', async () => {
    const elicit = vi.fn(() => ({ action: 'accept' as const }));
    childExits(refusalEnvelope(['CONFIRMATION_REQUIRED', REASON, 'foo']));
    const lifted = await executeRdcCommand(['repo', 'down', 'foo'], baseOptions);
    expect(lifted.decision?.verdict).toBe('needs_confirmation');
    expect(lifted.decision?.next).toBeUndefined();
    const client = await connect({ run: async () => lifted, elicit });
    const result = await call(client, { name: 'foo' });
    expect(result.isError).toBe(true);
    expect(elicit).not.toHaveBeenCalled();
    expect(result.structuredContent).toEqual({ code: 'CONFIRMATION_REQUIRED', reason: REASON });
  });

  for (const era of ['auto', 'legacy'] as const) {
    it(`a client that declared elicitation is asked, and its yes runs the child confirmed (${era})`, async () => {
      const run = childConfirmedBy('foo');
      const elicit = vi.fn(() => ({ action: 'accept' as const }));
      const client = await connect({ run, era, elicit });
      const result = await call(client, { name: 'foo' });
      expect(elicit).toHaveBeenCalledWith(REASON);
      expect(run.mock.calls.map(([confirm]) => confirm)).toEqual([undefined, 'foo']);
      expect(result.isError).not.toBe(true);
      expect(JSON.parse(textOf(result)).data).toEqual({ ran: true });
    });
  }

  it('a declined elicitation runs nothing more and says so', async () => {
    const run = childConfirmedBy('foo');
    const client = await connect({ run, elicit: () => ({ action: 'decline' }) });
    const result = await call(client, { name: 'foo' });
    expect(result.isError).toBe(true);
    expect(result.structuredContent).toMatchObject({ code: 'CONFIRMATION_REQUIRED' });
    expect(textOf(result)).toContain('did not confirm');
    expect(run).toHaveBeenCalledTimes(1);
  });

  it('an accepted form that does not say yes counts as a decline', async () => {
    const run = childConfirmedBy('foo');
    const client = await connect({ run, elicit: () => ({ action: 'accept', confirm: false }) });
    const result = await call(client, { name: 'foo' });
    expect(result.isError).toBe(true);
    expect(run).toHaveBeenCalledTimes(1);
  });

  it('control: needs_confirmation that names no value is a plain refusal, even with elicitation', async () => {
    const elicit = vi.fn(() => ({ action: 'accept' as const }));
    const client = await connect({ run: async () => refused('needs_confirmation'), elicit });
    const result = await call(client, { name: 'foo' });
    expect(result.isError).toBe(true);
    expect(elicit).not.toHaveBeenCalled();
    expect(result.structuredContent).toEqual({ code: 'CONFIRMATION_REQUIRED', reason: REASON });
  });

  it('a yes whose state was minted for other arguments runs nothing', async () => {
    const run = childConfirmedBy('foo');
    const ctx = {
      mcpReq: {
        inputResponses: { confirm: { action: 'accept', content: { confirm: true } } },
        requestState: () => ({ tool: 'repo_down', args: '[["name","other"]]', value: 'foo' }),
      },
    };
    const outcome = await runUnderPolicy(
      { server: {} as McpServer, ctx: ctx as never, tool: 'repo_down', args: { name: 'foo' } },
      run
    );
    expect(outcome).toHaveProperty('answer.isError', true);
    expect(run).not.toHaveBeenCalled();
  });

  it('control: an allowed run passes through untouched', async () => {
    const run = vi.fn(async () => OK);
    const client = await connect({ run });
    const result = await call(client, { name: 'foo' });
    expect(result.isError).not.toBe(true);
    expect(run).toHaveBeenCalledWith(undefined);
  });
});
