/**
 * `rdc server` parses into the engine (PLAN-enterprise-tenants C7): the verbs exist, the install
 * flags reach ServerInstall under their names, and `install --help` carries the step list.
 */

import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  installOpts: undefined as Record<string, unknown> | undefined,
  run: vi.fn(),
  status: vi.fn(),
  backup: vi.fn(),
  print: vi.fn(),
}));

vi.mock('../../i18n/index.js', () => ({ t: (key: string) => key }));
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    success: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    print: m.print,
    report: vi.fn(),
  },
}));
vi.mock('../../services/core/output-format.js', () => ({ isMachineReadable: () => true }));
vi.mock('../../services/core/request-context.js', () => ({ setExitCode: vi.fn() }));
vi.mock('../../services/server/deps.js', () => ({ liveServerDeps: () => ({}) }));
vi.mock('../../services/server/install.js', () => ({
  ServerInstall: class {
    constructor(opts: Record<string, unknown>) {
      m.installOpts = opts;
    }
    run = m.run;
  },
}));
vi.mock('../../services/server/verbs.js', () => ({
  serverStatus: m.status,
  serverBackup: m.backup,
  serverUpgrade: vi.fn(),
  serverLicence: vi.fn(),
}));
vi.mock('../../utils/errors.js', () => ({
  handleError: (error: unknown) => {
    throw error;
  },
}));

import { registerServerCommands } from '../server.js';

function program(): Command {
  const root = new Command('rdc');
  root.exitOverride();
  registerServerCommands(root);
  return root;
}

beforeEach(() => {
  vi.clearAllMocks();
  m.installOpts = undefined;
  m.run.mockResolvedValue({ domain: 'acme.example.com' });
  m.status.mockResolvedValue({ health: 200 });
});

describe('rdc server', () => {
  it('registers install, status, upgrade, backup and licence', () => {
    const server = program().commands.find((c) => c.name() === 'server');
    expect(server?.commands.map((c) => c.name())).toEqual([
      'install',
      'status',
      'upgrade',
      'backup',
      'licence',
    ]);
  });

  it('hands the install flags and the positional machine to the engine', async () => {
    await program().parseAsync(
      [
        'server',
        'install',
        'm1',
        '--domain',
        'acme.example.com',
        '--tls',
        'byo',
        '--tls-cert',
        'c.pem',
        '--tls-key',
        'k.pem',
        '--licence',
        'free',
        '--bws-project',
        'p1',
        '--rotate',
        '--no-dns-wait',
        '--yes',
      ],
      { from: 'user' }
    );
    expect(m.installOpts).toMatchObject({
      machine: 'm1',
      domain: 'acme.example.com',
      tls: 'byo',
      tlsCert: 'c.pem',
      tlsKey: 'k.pem',
      licence: 'free',
      bwsProject: 'p1',
      rotate: true,
      dnsWait: false,
      yes: true,
      machineReadable: true,
    });
    expect(m.print).toHaveBeenCalledWith({ domain: 'acme.example.com' }, 'json');
  });

  it('registers an existing machine by --ip and --user', async () => {
    await program().parseAsync(
      ['server', 'install', '--ip', '192.168.111.11', '--user', 'ops', '--name', 'lab'],
      { from: 'user' }
    );
    expect(m.installOpts).toMatchObject({ ip: '192.168.111.11', user: 'ops', name: 'lab' });
    expect(m.installOpts?.machine).toBeUndefined();
  });

  it('refuses an unknown TLS method', async () => {
    const root = program();
    root.commands.forEach((c) => {
      c.exitOverride();
      c.commands.forEach((s) => {
        s.exitOverride();
        s.configureOutput({ writeErr: () => undefined });
      });
    });
    await expect(
      root.parseAsync(['server', 'install', 'm1', '--tls', 'selfsigned'], { from: 'user' })
    ).rejects.toThrow();
  });

  it('documents the steps in install --help', () => {
    const install = program()
      .commands.find((c) => c.name() === 'server')
      ?.commands.find((c) => c.name() === 'install');
    let help = '';
    install?.configureOutput({ writeOut: (s) => (help += s) });
    install?.outputHelp();
    expect(help).toContain('commands.server.install.help');
    expect(help).toContain('--bws-project');
  });

  it('passes the locator flags to status', async () => {
    await program().parseAsync(['server', 'status', 'acme.example.com', '-m', 'm1'], {
      from: 'user',
    });
    expect(m.status).toHaveBeenCalledWith({}, { domain: 'acme.example.com', machine: 'm1' });
  });
});
