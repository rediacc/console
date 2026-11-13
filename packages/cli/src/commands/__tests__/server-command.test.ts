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
  upgrade: vi.fn(),
  licence: vi.fn(),
  confirm: vi.fn(),
  print: vi.fn(),
  report: vi.fn(),
  machine: true,
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, p?: object) => (p ? `${key} ${JSON.stringify(p)}` : key),
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: {
    info: vi.fn(),
    success: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
    print: m.print,
    report: m.report,
  },
}));
vi.mock('../../services/core/output-format.js', () => ({ isMachineReadable: () => m.machine }));
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
  serverUpgrade: m.upgrade,
  serverLicence: m.licence,
}));
vi.mock('../../utils/prompt.js', () => ({ askConfirm: m.confirm }));
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
  m.machine = true;
  m.run.mockResolvedValue({ domain: 'acme.example.com' });
  m.status.mockResolvedValue({ health: 200 });
  m.upgrade.mockResolvedValue({ rollback: 'acme:rollback' });
  m.licence.mockResolvedValue({ subscriptionId: 'sub-1' });
  m.confirm.mockResolvedValue(true);
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

  it('registers the upgrade summary from its short description key', () => {
    const server = program().commands.find((c) => c.name() === 'server');
    const upgrade = server?.commands.find((c) => c.name() === 'upgrade');
    expect(upgrade?.summary()).toBe('commands.server.upgrade.descriptionShort');
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
  it.each([true, false])(
    'upgrade asks for confirmation without --yes when stdin.isTTY is %s',
    async (tty) => {
      const saved = Object.getOwnPropertyDescriptor(process.stdin, 'isTTY');
      Object.defineProperty(process.stdin, 'isTTY', { value: tty, configurable: true });
      try {
        await program().parseAsync(['server', 'upgrade', 'acme.example.com'], { from: 'user' });
      } finally {
        if (saved) Object.defineProperty(process.stdin, 'isTTY', saved);
        else delete (process.stdin as { isTTY?: boolean }).isTTY;
      }
      expect(m.confirm).toHaveBeenCalledTimes(1);
      expect(m.upgrade).toHaveBeenCalledTimes(1);
    }
  );

  it('upgrade stops when the confirmation is declined', async () => {
    m.confirm.mockResolvedValue(false);
    await program().parseAsync(['server', 'upgrade', 'acme.example.com'], { from: 'user' });
    expect(m.upgrade).not.toHaveBeenCalled();
  });

  it('upgrade with --yes skips the prompt and hands the parsed options to the verb', async () => {
    await program().parseAsync(
      ['server', 'upgrade', 'acme.example.com', '--image', 'img:2', '--local-image', '--yes'],
      { from: 'user' }
    );
    expect(m.confirm).not.toHaveBeenCalled();
    expect(m.upgrade).toHaveBeenCalledTimes(1);
    const [, loc, opts] = m.upgrade.mock.calls[0];
    expect(loc).toMatchObject({ domain: 'acme.example.com' });
    expect(opts).toMatchObject({ image: 'img:2', localImage: true, yes: true });
    expect(m.print).toHaveBeenCalledWith({ rollback: 'acme:rollback' }, 'json');
  });

  it('upgrade passes --image-file through', async () => {
    await program().parseAsync(
      ['server', 'upgrade', 'acme.example.com', '--image-file', 'a.tar', '-y'],
      { from: 'user' }
    );
    expect(m.upgrade.mock.calls[0][2]).toMatchObject({ imageFile: 'a.tar' });
  });

  it('backup hands the domain and --out to the verb', async () => {
    await program().parseAsync(['server', 'backup', 'acme.example.com', '--out', 'b.json'], {
      from: 'user',
    });
    expect(m.backup).toHaveBeenCalledTimes(1);
    const [, loc, out] = m.backup.mock.calls[0];
    expect(loc).toMatchObject({ domain: 'acme.example.com' });
    expect(out).toBe('b.json');
  });

  it('licence hands the domain and --cert to the verb', async () => {
    await program().parseAsync(['server', 'licence', 'acme.example.com', '--cert', 'c.json'], {
      from: 'user',
    });
    expect(m.licence).toHaveBeenCalledTimes(1);
    const [, loc, cert] = m.licence.mock.calls[0];
    expect(loc).toMatchObject({ domain: 'acme.example.com' });
    expect(cert).toBe('c.json');
    expect(m.print).toHaveBeenCalledWith({ subscriptionId: 'sub-1' }, 'json');
  });

  describe('status in the human-readable form', () => {
    const lines = () => m.report.mock.calls.map((c) => String(c[0]));
    const refusal = (at: string) => ({
      health: 200,
      certRefused: { reason: 'bad-signature', detail: 'd', at },
    });
    const run = () =>
      program().parseAsync(['server', 'status', 'acme.example.com'], { from: 'user' });

    it('prints the cert refusal and the command that fixes it', async () => {
      m.machine = false;
      m.status.mockResolvedValue(refusal('2026-11-01T10:20:30.123Z'));
      await run();
      const cert = lines().find((l) => l.startsWith('cert '));
      expect(cert).toContain('commands.server.status.certRefused');
      expect(cert).toContain('"reason":"bad-signature"');
      expect(lines().some((l) => l.includes('commands.server.status.certRefusedRun'))).toBe(true);
      expect(lines().some((l) => l.includes('"domain":"acme.example.com"'))).toBe(true);
      expect(m.print).not.toHaveBeenCalled();
    });

    it('prints no cert line when nothing was refused (control)', async () => {
      m.machine = false;
      await run();
      expect(lines().some((l) => l.startsWith('cert '))).toBe(false);
      expect(lines().some((l) => l.includes('certRefusedRun'))).toBe(false);
    });

    it.each([
      ['2026-11-01T10:20:30.123Z', '2026-11-01 10:20Z'],
      ['2026-11-01T10:20:30+00:00', '2026-11-01 10:20Z'],
      ['2026-11-01T12:20:30+02:00', '2026-11-01 10:20Z'],
      ['', '?'],
    ])('shows the timestamp %j as %j', async (at, shown) => {
      m.machine = false;
      m.status.mockResolvedValue(refusal(at));
      await run();
      expect(lines().find((l) => l.startsWith('cert '))).toContain(`"at":"${shown}"`);
    });
  });
});
