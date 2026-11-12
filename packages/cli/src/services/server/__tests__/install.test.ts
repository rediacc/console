/**
 * `rdc server install` (PLAN-enterprise-tenants C7) against a scripted box: the machine step
 * (by name, by --ip), the preflight refusals, the TTY rules and prompt order, the DNS wait and the
 * owned-zone write, the three licence paths, the bws backup, and the one-time recovery bundle.
 */

import { rmSync } from 'node:fs';
import { WK_INFRA_DOMAIN } from '@rediacc/shared/config/well-known.generated';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const m = vi.hoisted(() => ({
  machines: [] as { name: string; config: { ip: string; user: string; datastore?: string } }[],
  repos: new Map<string, { repositoryGuid: string; networkId?: number }>(),
  addExisting: vi.fn(),
}));

vi.mock('../../../i18n/index.js', () => ({
  t: (key: string, vars?: Record<string, unknown>) =>
    vars ? `${key} ${JSON.stringify(vars)}` : key,
}));
vi.mock('../../core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn(), error: vi.fn(), print: vi.fn() },
}));
vi.mock('../../config/config-resources.js', () => ({
  configService: {
    listMachines: () => Promise.resolve(m.machines),
    getLocalMachine: (name: string) => {
      const found = m.machines.find((x) => x.name === name);
      return found ? Promise.resolve(found.config) : Promise.reject(new Error('no machine'));
    },
    getLocalConfig: () => Promise.resolve({ machines: {}, certEmail: undefined }),
    getRepository: (name: string) => Promise.resolve(m.repos.get(name)),
  },
}));
vi.mock('../../../utils/repo-executor.js', () => ({
  recordedDatastoreMount: () => Promise.resolve(undefined),
}));
vi.mock('../../machine/add-existing.js', () => ({ addExistingMachine: m.addExisting }));

import type { MachineAnswer, ServerPrompts } from '../../../utils/server-prompts.js';
import { ServerInstall } from '../install.js';
import { serverStateDir } from '../state.js';
import { BOX_KEY, certFor, type FakeOptions, makeFake } from './fakes.js';

const BASE = { domain: 'acme.example.com', owner: 'owner@example.com', dnsWait: false };

/** `repo create` makes the repo exist for the steps after it, as the real child would. */
function createsRepo(fake: ReturnType<typeof makeFake>) {
  const rdc = fake.deps.rdc;
  fake.deps.rdc = (argv) => {
    if (argv[0] === 'repo' && argv[1] === 'create') {
      m.repos.set(argv[2], { repositoryGuid: 'guid-1', networkId: 2816 });
    }
    return rdc(argv);
  };
  return fake;
}

function prompts(overrides: Partial<ServerPrompts> = {}, log: string[] = []): ServerPrompts {
  return {
    machine: (configured) => {
      log.push(`machine ${configured.join(',')}`);
      return Promise.resolve({ kind: 'existing', name: 'm1' } as MachineAnswer);
    },
    text: (message, def) => {
      log.push(`text ${message.split(' ')[0]}`);
      if (message.includes('storeDomain')) return Promise.resolve(def ?? '');
      if (message.includes('owner')) return Promise.resolve('owner@example.com');
      return Promise.resolve('acme.example.com');
    },
    tls: (def) => {
      log.push('tls');
      return Promise.resolve(def);
    },
    confirm: () => Promise.resolve(true),
    ...overrides,
  };
}

function run(opts: Record<string, unknown>, fakeOpts: FakeOptions = {}, p = prompts()) {
  const fake = createsRepo(makeFake(fakeOpts));
  const install = new ServerInstall({ ...BASE, ...opts }, fake.deps, p);
  return { fake, result: install.run() };
}

beforeEach(() => {
  vi.clearAllMocks();
  m.machines = [{ name: 'm1', config: { ip: '203.0.113.10', user: 'admin' } }];
  m.repos = new Map();
  rmSync(serverStateDir(), { recursive: true, force: true });
});

describe('the machine step', () => {
  it('installs on a configured machine named on the command line', async () => {
    const { fake, result } = run({ machine: 'm1' });
    const out = await result;
    expect(out.machine).toBe('m1');
    expect(m.addExisting).not.toHaveBeenCalled();
    expect(fake.calls).toContain('rdc repo create elite -m m1 --size 10G');
    expect(fake.calls).toContain('rdc repo up elite@m1');
  });

  it('registers an existing server from --ip and --user through the machine add helper', async () => {
    m.addExisting.mockImplementation((name: string, input: { ip: string; user: string }) => {
      const config = { ip: input.ip, user: input.user };
      m.machines.push({ name, config });
      return Promise.resolve(config);
    });
    const { result } = run({ ip: '192.168.111.11', user: 'ops', name: 'lab-brought' });
    const out = await result;
    expect(m.addExisting).toHaveBeenCalledWith('lab-brought', {
      ip: '192.168.111.11',
      user: 'ops',
    });
    expect(out.machine).toBe('lab-brought');
  });

  it('refuses a machine name the config does not hold', async () => {
    await expect(run({ machine: 'ghost' }).result).rejects.toThrow(/machineUnknown/);
  });
});

describe('preflight', () => {
  it('refuses without passwordless sudo, naming it', async () => {
    const { result } = run({ machine: 'm1' }, { preflight: { sudo: '0' } });
    await expect(result).rejects.toThrow(/preflight.*noSudo/s);
  });

  it('refuses a port held by something other than the renet proxy', async () => {
    const busy = 'LISTEN 0 511 0.0.0.0:80 0.0.0.0:* users:(("nginx",pid=1,fd=6))';
    await expect(run({ machine: 'm1' }, { preflight: { port80: busy } }).result).rejects.toThrow(
      /portBusy.*nginx/s
    );
  });

  it('accepts ports held by the renet proxy', async () => {
    const proxy = 'LISTEN 0 4096 *:443 *:* users:(("traefik",pid=7,fd=8))';
    const { result } = run({ machine: 'm1' }, { preflight: { port443: proxy } });
    await expect(result).resolves.toBeDefined();
  });

  it('refuses a skewed clock, an unsupported architecture and a full disk', async () => {
    const { result } = run(
      { machine: 'm1' },
      { preflight: { epoch: '1000', arch: 'riscv64', free_kb: '1024' } }
    );
    await expect(result).rejects.toThrow(/arch.*disk.*clock/s);
  });

  it('runs machine setup when renet is missing', async () => {
    const { fake, result } = run({ machine: 'm1' }, { preflight: { renet: '0' } });
    await result;
    expect(fake.calls).toContain('rdc machine setup m1');
  });
});

describe('values and prompts', () => {
  it('refuses a missing value off a terminal, naming its flag', async () => {
    const { result } = run({ machine: 'm1', domain: undefined }, { tty: false });
    await expect(result).rejects.toThrow(/needsTTY.*--domain/);
  });

  it('refuses a missing machine off a terminal', async () => {
    const { result } = run({}, { tty: false });
    await expect(result).rejects.toThrow(/needsTTY/);
  });

  it('asks machine, domain, store domain, TLS and owner, in that order, on a terminal', async () => {
    const log: string[] = [];
    const { result } = run(
      { domain: undefined, owner: undefined },
      { tty: true },
      prompts({}, log)
    );
    const out = await result;
    expect(log).toEqual([
      'machine m1',
      'text commands.server.prompts.domain',
      'text commands.server.prompts.storeDomain',
      'tls',
      'text commands.server.prompts.owner',
    ]);
    expect(out.storeDomain).toBe('acme-store.example.com');
  });

  it('asks nothing under --yes', async () => {
    const log: string[] = [];
    const { result } = run({ machine: 'm1', yes: true }, { tty: true }, prompts({}, log));
    await result;
    expect(log).toEqual([]);
  });
});

describe('dns', () => {
  it('waits until both names resolve to the machine', async () => {
    const { fake, result } = run(
      { machine: 'm1', dnsWait: true },
      { resolveSequence: [[], [], ['203.0.113.10']] }
    );
    await result;
    const resolves = fake.calls.filter((c) => c.startsWith('resolve '));
    expect(resolves.length).toBeGreaterThan(2);
    expect(fake.dnsWrites).toEqual([]);
  });

  it('never writes a customer zone, even with a token set', async () => {
    const { fake, result } = run(
      { machine: 'm1', dnsWait: false },
      { zoneToken: 'cf', resolveSequence: [[]] }
    );
    await result;
    expect(fake.dnsWrites).toEqual([]);
  });

  it('writes a Rediacc-owned zone when the token is set and the name does not resolve', async () => {
    const { fake, result } = run(
      {
        machine: 'm1',
        domain: `acme.${WK_INFRA_DOMAIN}`,
        dnsWait: false,
      },
      { zoneToken: 'cf', resolveSequence: [[]], sans: [`acme.${WK_INFRA_DOMAIN}`] }
    );
    await result;
    expect(fake.dnsWrites).toEqual([
      `${WK_INFRA_DOMAIN} A acme.${WK_INFRA_DOMAIN} 203.0.113.10`,
      `${WK_INFRA_DOMAIN} A acme-store.${WK_INFRA_DOMAIN} 203.0.113.10`,
    ]);
  });
});

describe('settings', () => {
  it('writes ROOT_EMAIL from the owner and no ELITE_TLS for the acme methods', async () => {
    const { fake, result } = run({ machine: 'm1' });
    await result;
    const env = fake.setEnv.find((e) => e.ELITE_DOMAIN);
    expect(env?.ROOT_EMAIL).toBe('owner@example.com');
    expect(env).not.toHaveProperty('ELITE_TLS');
  });

  it('byo writes ELITE_TLS=provided so the compose labels skip the router resolver', async () => {
    const { fake, result } = run(
      { machine: 'm1', tls: 'byo', tlsCert: '/c.pem', tlsKey: '/k.pem' },
      { files: { '/c.pem': 'CERT', '/k.pem': 'KEY' } }
    );
    await result;
    expect(fake.setEnv.find((e) => e.ELITE_DOMAIN)?.ELITE_TLS).toBe('provided');
  });
});

describe('licence', () => {
  it('auto: the logged-in config issues a cert for the box key, written to secrets.env', async () => {
    const { fake, result } = run({ machine: 'm1' });
    const out = await result;
    const env = fake.setEnv.find((e) => e.DELEGATION_CERT_BASE64);
    expect(env?.DELEGATION_CERT_BASE64).toBe(certFor(BOX_KEY));
    expect(env?.UPSTREAM_API_KEY).toBe('renew-token');
    expect(out.tier).toBe('licensed');
    expect(out.subscriptionId).toBe('sub-1');
  });

  it('auto with no login starts on the free tier', async () => {
    const { fake, result } = run({ machine: 'm1' }, { issue: { kind: 'no-login' } });
    const out = await result;
    expect(out.tier).toBe('free');
    expect(fake.setEnv.some((e) => e.DELEGATION_CERT_BASE64)).toBe(false);
  });

  it('auto with a login lacking the scope refuses off a terminal, naming the relogin', async () => {
    const { result } = run({ machine: 'm1' }, { issue: { kind: 'missing-scope' } });
    await expect(result).rejects.toThrow(/missingScope/);
  });

  it('--licence free never asks the account server and probes the relay', async () => {
    const { fake, result } = run({ machine: 'm1', licence: 'free' });
    await result;
    expect(fake.calls).not.toContain('issue');
    expect(fake.calls).toContain('https POST /account/api/v1/onprem/free-license');
  });

  it('--cert for another key than the box generated is refused', async () => {
    const files = { '/c.json': certFor('some-other-key') };
    const { result } = run({ machine: 'm1', cert: '/c.json' }, { files });
    await expect(result).rejects.toThrow(/keyMismatch/);
  });

  it('--cert for the box key is installed without the account server', async () => {
    const files = { '/c.json': certFor(BOX_KEY, 'sub-1') };
    const { fake, result } = run({ machine: 'm1', cert: '/c.json' }, { files });
    const out = await result;
    expect(fake.calls).not.toContain('issue');
    expect(out.subscriptionId).toBe('sub-1');
  });

  it('refuses when the owner lands on another subscription than the cert names', async () => {
    const files = { '/c.json': certFor(BOX_KEY, 'sub-offline') };
    await expect(run({ machine: 'm1', cert: '/c.json' }, { files }).result).rejects.toThrow(
      /owner: .*raced/
    );
  });
});

describe('bws backup', () => {
  it('copies nothing without --bws-project', async () => {
    const { fake, result } = run({ machine: 'm1' });
    await result;
    expect(fake.bwsWrites).toEqual([]);
  });

  it('creates opaque entries, and never names the domain', async () => {
    const { fake, result } = run({ machine: 'm1', bwsProject: 'proj-1' });
    await result;
    expect(fake.bwsWrites).toHaveLength(9);
    for (const w of fake.bwsWrites) {
      expect(w.key).toMatch(/^ONPREM_[0-9a-f]{12}_[A-Z0-9_]+$/);
      expect(w.key).not.toContain('acme');
      expect(w.projectIds).toEqual(['proj-1']);
    }
  });

  it('refuses a differing stored value unless --rotate', async () => {
    const { bwsName } = await import('../bws-backup.js');
    const row = {
      id: 'id-1',
      key: bwsName('acme.example.com', 'ACCOUNT_JWT_SECRET'),
      value: 'old',
      projectId: 'proj-1',
    };
    await expect(
      run({ machine: 'm1', bwsProject: 'proj-1' }, { bwsRows: [row] }).result
    ).rejects.toThrow(/differs/);
    const { fake, result } = run(
      { machine: 'm1', bwsProject: 'proj-1', rotate: true },
      { bwsRows: [row] }
    );
    await result;
    expect(fake.bwsWrites.find((w) => w.op === 'edit')?.id).toBe('id-1');
  });
});

describe('the recovery bundle', () => {
  it('is printed once on a terminal, and not again on a rerun', async () => {
    const first = run({ machine: 'm1' }, { tty: true });
    await first.result;
    const printed = first.fake.stdout.join('');
    expect(printed).toContain('ACCOUNT_ED25519_PRIVATE_KEY=edpriv');
    expect(printed).toContain('ACCOUNT_CONFIG_SERVER_KEY=cfgkey');
    expect(printed).toContain('RUSTFS_SECRET_KEY=rssecret');

    const second = run({ machine: 'm1' }, { tty: true });
    await second.result;
    expect(second.fake.stdout.join('')).not.toContain('edpriv');
  });

  it('is never printed under --output json, nor off a terminal', async () => {
    const json = run({ machine: 'm1', machineReadable: true }, { tty: true });
    const out = await json.result;
    expect(json.fake.stdout.join('')).toBe('');
    expect(JSON.stringify(out)).not.toContain('edpriv');

    rmSync(serverStateDir(), { recursive: true, force: true });
    m.repos = new Map();
    const pipe = run({ machine: 'm1' }, { tty: false });
    await pipe.result;
    expect(pipe.fake.stdout.join('')).toBe('');
  });
});
