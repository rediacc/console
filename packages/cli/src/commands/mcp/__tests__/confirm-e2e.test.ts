/**
 * The whole confirmation path in memory (PLAN-rmcp-local-mcp LM4): a real McpServer with every tool registered, a
 * real SDK Client, and a stand-in for the child `rdc` that prints the refusal the real command-policy check prints
 * for a destructive command on a grand repo (exit 2, `errors[0]` code VALIDATION_ERROR, details
 * `[code, reason, '--confirm-grand <value>']`). The refusal becomes an elicitation, and the user's yes reruns the
 * child with `--confirm-grand`.
 */
import { Client, InMemoryTransport } from '@modelcontextprotocol/client';
import type { CallToolResult } from '@modelcontextprotocol/server';
import { McpServer } from '@modelcontextprotocol/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MCP_SERVER_OPTIONS } from '../server.js';
import { buildAllTools, registerAllTools } from '../tools.js';

const mockExecFile = vi.fn();
vi.mock('node:child_process', () => ({
  execFile: (...args: unknown[]) => mockExecFile(...args),
}));

const TOOL = 'repo_delete';
const REASON =
  '"rdc repo delete" is destructive and would change foo, a grand repo. Confirm to proceed.';

function envelope(success: boolean, errors: unknown[] | null) {
  return JSON.stringify({
    success,
    command: 'repo delete',
    data: success ? { deleted: true } : null,
    errors,
    warnings: [],
    metrics: { duration_ms: 0 },
  });
}

/** The child: exit 2 with the refusal until argv carries `--confirm-grand foo`, then success. */
function childNeedsConfirmGrand() {
  mockExecFile.mockImplementation(
    (_cmd: string, args: string[], _opts: unknown, callback: (...a: unknown[]) => void) => {
      const at = args.indexOf('--confirm-grand');
      if (at >= 0 && args[at + 1] === 'foo') {
        callback(null, { stdout: envelope(true, null), stderr: '' });
        return;
      }
      const stdout = envelope(false, [
        {
          code: 'VALIDATION_ERROR',
          origin: 'user',
          message: 'translated refusal',
          details: ['CONFIRMATION_REQUIRED', REASON, '--confirm-grand foo'],
          retryable: false,
        },
      ]);
      callback(Object.assign(new Error('Command failed'), { stdout, stderr: '', code: 2 }));
    }
  );
}

const servers: McpServer[] = [];
const clients: Client[] = [];

afterEach(async () => {
  for (const c of clients.splice(0)) await c.close();
  for (const s of servers.splice(0)) await s.close();
  vi.clearAllMocks();
});

async function connect(elicit?: (message: string) => void): Promise<Client> {
  const server = new McpServer({ name: 'rdc', version: '0.0.0' }, MCP_SERVER_OPTIONS);
  registerAllTools(server, { defaultTimeoutMs: 1000 });
  servers.push(server);
  const client = new Client(
    { name: 'lm4-e2e', version: '0.0.0' },
    elicit ? { capabilities: { elicitation: { form: {} } } } : {}
  );
  if (elicit) {
    client.setRequestHandler('elicitation/create', (request) => {
      elicit(request.params.message);
      return { action: 'accept' as const, content: { confirm: true } };
    });
  }
  clients.push(client);
  const [clientSide, serverSide] = InMemoryTransport.createLinkedPair();
  await server.connect(serverSide);
  await client.connect(clientSide);
  return client;
}

const argvOf = (call: unknown[]) => call[1] as string[];

describe('a grand-guarded destructive tool, end to end', () => {
  it('control: the tool is destructive and takes a confirm field', () => {
    const tool = buildAllTools().find((t) => t.name === TOOL);
    expect(tool?.isDestructive).toBe(true);
    expect(tool?.schema).toHaveProperty('confirm');
  });

  it('the refusal becomes an elicitation, and the yes reruns the child with --confirm-grand', async () => {
    childNeedsConfirmGrand();
    const asked: string[] = [];
    const client = await connect((message) => asked.push(message));
    const result = (await client.callTool({
      name: TOOL,
      arguments: { ref: 'foo' },
    })) as CallToolResult;
    expect(asked).toEqual([REASON]);
    expect(result.isError).not.toBe(true);
    expect(mockExecFile).toHaveBeenCalledTimes(2);
    expect(argvOf(mockExecFile.mock.calls[0])).not.toContain('--confirm-grand');
    const second = argvOf(mockExecFile.mock.calls[1]);
    expect(second.slice(second.indexOf('--confirm-grand'))).toEqual(['--confirm-grand', 'foo']);
  });

  it('a client that cannot elicit is told the confirm argument, and the retry with it runs', async () => {
    childNeedsConfirmGrand();
    const client = await connect();
    const refused = (await client.callTool({
      name: TOOL,
      arguments: { ref: 'foo' },
    })) as CallToolResult;
    expect(refused.isError).toBe(true);
    expect(refused.structuredContent).toMatchObject({
      code: 'CONFIRMATION_REQUIRED',
      next: { confirm: { argument: 'confirm', value: 'foo' } },
    });
    const ran = (await client.callTool({
      name: TOOL,
      arguments: { ref: 'foo', confirm: 'foo' },
    })) as CallToolResult;
    expect(ran.isError).not.toBe(true);
    expect(mockExecFile).toHaveBeenCalledTimes(2);
  });
});
