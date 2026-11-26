/**
 * Review 1121-1 219d0972.3: `config show --reveal` is refused inside an executor request, whatever the
 * executor process's own terminal is. The gate (config.ts applyRevealGate) reads the request context,
 * so a regression that drops it would otherwise pass every suite.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  getCurrent: vi.fn(),
  print: vi.fn(),
  handled: vi.fn(),
  isAgent: vi.fn(() => false),
}));

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getCurrent: m.getCurrent,
    getCurrentName: () => 'default',
  },
}));
vi.mock('../../services/core/output.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../services/core/output.js')>()),
  outputService: {
    print: m.print,
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    success: vi.fn(),
  },
}));
vi.mock('../../utils/errors.js', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/errors.js')>()),
  handleError: m.handled,
}));
vi.mock('../../utils/agent-guard.js', () => ({ isAgentEnvironment: m.isAgent }));
vi.mock('../../services/core/audit-log.js', () => ({ auditLog: vi.fn() }));
vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));

const { Command } = await import('commander');
const { registerConfigCommands } = await import('../config.js');
const { createOutputState, createRequestConfigScope, runInRequestContext } = await import(
  '../../services/core/request-context.js'
);

const CONFIG = { schemaVersion: 3, id: 'cfg-1', version: 2, resources: { machines: {} } };

function showReveal(): Promise<unknown> {
  const program = new Command();
  program.option('-o, --output <format>', 'format', 'json');
  registerConfigCommands(program);
  return program.parseAsync(['node', 'rdc', 'config', 'show', '--reveal']);
}

describe('config show --reveal', () => {
  const tty = Object.getOwnPropertyDescriptor(process.stdout, 'isTTY');

  beforeEach(() => {
    vi.clearAllMocks();
    m.getCurrent.mockResolvedValue(structuredClone(CONFIG));
    m.isAgent.mockReturnValue(false);
    Object.defineProperty(process.stdout, 'isTTY', { value: true, configurable: true });
  });

  afterEach(() => {
    if (tty) Object.defineProperty(process.stdout, 'isTTY', tty);
    else Reflect.deleteProperty(process.stdout, 'isTTY');
  });

  it('is refused inside an executor request even with a terminal and no agent environment', async () => {
    await runInRequestContext(
      {
        output: createOutputState(),
        stdout: [],
        stderr: [],
        config: createRequestConfigScope(structuredClone(CONFIG) as never),
      },
      showReveal
    );

    expect(m.print).not.toHaveBeenCalled();
    expect(m.handled).toHaveBeenCalledOnce();
    expect(String((m.handled.mock.calls[0][0] as Error).message)).toContain('showReveal');
  });

  it('control: a human at a terminal outside a request is granted it', async () => {
    await showReveal();

    expect(m.handled).not.toHaveBeenCalled();
    expect(m.print).toHaveBeenCalledOnce();
  });

  it('control: an agent environment outside a request is refused', async () => {
    m.isAgent.mockReturnValue(true);
    await showReveal();

    expect(m.print).not.toHaveBeenCalled();
    expect(m.handled).toHaveBeenCalledOnce();
  });
});
