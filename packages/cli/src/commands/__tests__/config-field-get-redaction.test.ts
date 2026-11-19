import { beforeEach, describe, expect, it, vi } from 'vitest';

// `config field get` redacts every non-public value at or below the pointer it is given, not only a pointer that names a sensitive leaf: a parent pointer once printed every secret under it in plaintext. All values here are synthetic.

const { state, printed } = vi.hoisted(() => ({
  state: { format: 'json' as 'json' | 'table', config: {} as unknown },
  printed: [] as string[],
}));

vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getCurrent: vi.fn(async () => state.config), getCurrentName: () => 'test' },
}));
vi.mock('../../services/core/audit-log.js', () => ({ auditLog: vi.fn() }));
vi.mock('../../utils/agent-guard.js', () => ({ isAgentEnvironment: () => false }));
vi.mock('../../utils/errors.js', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../utils/errors.js')>();
  return {
    ...actual,
    getOutputFormat: () => state.format,
    handleError: vi.fn((e: unknown) => {
      throw e instanceof Error ? e : new Error(String(e));
    }),
  };
});

const { Command } = await import('commander');
const { registerFieldCommands } = await import('../config/field.js');
const { outputService } = await import('../../services/core/output.js');

const SECRETS = {
  cfToken: 'SYNTHETIC-cf-dns-token-0000000000000000',
  sshKey: 'SYNTHETIC-ssh-private-key-material',
  repoCredential: 'SYNTHETIC-repo-luks-credential',
  repoSshKey: 'SYNTHETIC-repo-ssh-private-key',
  secretValue: 'SYNTHETIC-repo-secret-value',
};

const CONFIG = {
  schemaVersion: 3,
  id: 'cfg-id',
  version: 1,
  defaults: { language: 'en' },
  credentials: {
    cfDnsApiToken: SECRETS.cfToken,
    ssh: { privateKey: SECRETS.sshKey, publicKey: 'ssh-ed25519 AAAAsynthetic' },
  },
  resources: {
    machines: { m1: { ip: '10.0.0.1', user: 'root', port: 2222 } },
    repositories: {
      app: {
        tags: {
          latest: {
            repositoryGuid: '33333333-3333-4333-8333-333333333333',
            credential: SECRETS.repoCredential,
            sshPrivateKey: SECRETS.repoSshKey,
            sshPublicKey: 'ssh-ed25519 AAAArepo',
            secrets: { DB_PASSWORD: { value: SECRETS.secretValue } },
          },
        },
      },
    },
  },
};

async function fieldGet(pointer: string, format: 'json' | 'table'): Promise<string> {
  state.format = format;
  printed.length = 0;
  const program = new Command();
  const config = program.command('config');
  registerFieldCommands(config, program);
  await program.parseAsync(['config', 'field', 'get', '--pointer', pointer], { from: 'user' });
  return printed.join('\n');
}

/** The JSON output is the standard envelope; the printed payload is its `data`. */
function dataOf(output: string): unknown {
  return (JSON.parse(output) as { data: unknown }).data;
}

function expectNoSecret(output: string): void {
  for (const secret of Object.values(SECRETS)) expect(output).not.toContain(secret);
}

describe('config field get redacts below any pointer', () => {
  beforeEach(() => {
    state.config = structuredClone(CONFIG);
    vi.spyOn(outputService, 'print').mockImplementation((data, format) => {
      printed.push(
        outputService.format(data as Record<string, unknown>, format as 'json' | 'table')
      );
    });
  });

  it.each(['json', 'table'] as const)('/credentials redacts its leaves (%s)', async (format) => {
    const out = await fieldGet('/credentials', format);
    expectNoSecret(out);
    expect(out).toMatch(/<redacted:secret>:[0-9a-f]{8}/);
    expect(out).toMatch(/<redacted:credential>:[0-9a-f]{8}/);
    // The public half of the keypair is not a secret and stays readable.
    expect(out).toContain('ssh-ed25519 AAAAsynthetic');
  });

  it.each(['json', 'table'] as const)('/resources redacts repo secrets (%s)', async (format) => {
    const out = await fieldGet('/resources', format);
    expectNoSecret(out);
    expect(out).toMatch(/<redacted:credential>:[0-9a-f]{8}/);
    expect(out).toMatch(/<redacted:secret>:[0-9a-f]{8}/);
  });

  it.each(['json', 'table'] as const)('the root pointer redacts (%s)', async (format) => {
    expectNoSecret(await fieldGet('', format));
  });

  it('JSON output carries the stub at the leaf position', async () => {
    const out = dataOf(await fieldGet('/credentials', 'json')) as {
      value: { cfDnsApiToken: string; ssh: { privateKey: string } };
    };
    expect(out.value.cfDnsApiToken).toMatch(/^<redacted:secret>:[0-9a-f]{8}$/);
    expect(out.value.ssh.privateKey).toMatch(/^<redacted:credential>:[0-9a-f]{8}$/);
  });

  it.each(['json', 'table'] as const)('a leaf pointer still redacts (%s)', async (format) => {
    const out = await fieldGet('/credentials/cfDnsApiToken', format);
    expectNoSecret(out);
    expect(out).toMatch(/<redacted:secret>:[0-9a-f]{8}/);
  });

  it.each(['json', 'table'] as const)(
    'a pointer below a secret stays redacted (%s)',
    async (format) => {
      const out = await fieldGet('/resources/repositories/app/tags/latest/secrets', format);
      expectNoSecret(out);
    }
  );

  it('a public field is returned verbatim', async () => {
    const out = dataOf(await fieldGet('/resources/machines/m1/port', 'json')) as { value: unknown };
    expect(out.value).toBe(2222);
    const lang = dataOf(await fieldGet('/defaults/language', 'json')) as { value: unknown };
    expect(lang.value).toBe('en');
  });

  it('a missing pointer is refused', async () => {
    await expect(fieldGet('/credentials/nope', 'json')).rejects.toThrow();
  });
});
