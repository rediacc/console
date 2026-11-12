/**
 * A scripted box, account server and terminal for the `rdc server` tests. Every outside call
 * `ServerDeps` makes is recorded in `calls`, in order.
 */

import { existsSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
import type {
  BoxReply,
  BwsRow,
  BwsWriteRequest,
  IssueOutcome,
  ProcResult,
  ServerDeps,
} from '../types.js';

export const BOX_KEY = 'MCowBQYDK2VwAyEAboxkey0000000000000000000000000000000=';

/** A signed cert whose payload names `key` and `sub`, as base64 of its JSON. */
export function certFor(key: string, sub = 'sub-1', planCode = 'ENTERPRISE'): string {
  const payload = Buffer.from(
    JSON.stringify({
      version: 1,
      subscriptionId: sub,
      planCode,
      delegatedPublicKey: key,
      validFrom: '2026-11-12T00:00:00Z',
      validUntil: '2027-11-12T00:00:00Z',
    })
  ).toString('base64');
  return Buffer.from(JSON.stringify({ payload, signature: 'sig', publicKeyId: 'k1' })).toString(
    'base64'
  );
}

export interface FakeOptions {
  tty?: boolean;
  preflight?: Partial<Record<string, string>>;
  secrets?: Record<string, string>;
  templateVersion?: number;
  resolveSequence?: string[][];
  issue?: IssueOutcome;
  health?: number;
  sans?: string[];
  freeProbe?: number;
  bwsRows?: BwsRow[];
  zoneToken?: string;
  files?: Record<string, string>;
  rdcFail?: string;
  /** Per-path-suffix answers that win over the defaults (a refused login, a 404 route). */
  boxReplies?: Record<string, Partial<BoxReply>>;
}

export interface Fake {
  deps: ServerDeps;
  calls: string[];
  stdout: string[];
  setEnv: Record<string, string>[];
  written: Record<string, string>;
  bwsWrites: BwsWriteRequest[];
  dnsWrites: string[];
  secrets: Record<string, string>;
  /** Every HTTPS request to the box, with its body and the cookie it carried. */
  boxRequests: { method: string; path: string; body?: unknown; cookie?: string }[];
}

const DEFAULT_SECRETS: Record<string, string> = {
  ACCOUNT_ED25519_PRIVATE_KEY: 'edpriv',
  ACCOUNT_ED25519_PUBLIC_KEY: BOX_KEY,
  ACCOUNT_X25519_PRIVATE_KEY: 'xpriv',
  ACCOUNT_X25519_PUBLIC_KEY: 'xpub',
  ACCOUNT_CONFIG_SERVER_KEY: 'cfgkey',
  RUSTFS_ACCESS_KEY: 'rsaccess',
  RUSTFS_SECRET_KEY: 'rssecret',
  ACCOUNT_SERVER_API_KEY: 'apikey',
  ACCOUNT_JWT_SECRET: 'jwt',
};

function ok(stdout = ''): ProcResult {
  return { code: 0, stdout, stderr: '' };
}

export function makeFake(opts: FakeOptions = {}): Fake {
  const calls: string[] = [];
  const stdout: string[] = [];
  const setEnv: Record<string, string>[] = [];
  const written: Record<string, string> = {};
  const bwsWrites: BwsWriteRequest[] = [];
  const dnsWrites: string[] = [];
  const boxRequests: Fake['boxRequests'] = [];
  const secrets: Record<string, string> = { ...DEFAULT_SECRETS, ...opts.secrets };
  const resolves = [...(opts.resolveSequence ?? [['203.0.113.10']])];
  let now = Date.parse('2026-11-12T12:00:00Z');

  const preflight = {
    sudo: '1',
    arch: 'x86_64',
    epoch: String(Math.floor(now / 1000)),
    renet: '1',
    free_kb: String(100 * 1024 * 1024),
    port80: '',
    port443: '',
    ...opts.preflight,
  };

  const preflightText = Object.entries(preflight)
    .map(([k, v]) => `${k}=${v}`)
    .join('\n');
  const readKeys = (command: string) => {
    const lines = Object.entries(secrets)
      .filter(([k]) => command.includes(k))
      .map(([k, v]) => `${k}=${v}`);
    if (opts.templateVersion !== undefined) lines.push(`VERSION=${opts.templateVersion}`);
    return `${lines.join('\n')}\n`;
  };
  const applyEnv = (_command: string, stdin?: string) => {
    const values: Record<string, string> = {};
    for (const line of (stdin ?? '').split('\n').filter(Boolean)) {
      const eq = line.indexOf('=');
      values[line.slice(0, eq)] = line.slice(eq + 1);
    }
    setEnv.push(values);
    Object.assign(secrets, values);
    return Object.keys(values).join(',');
  };
  /** Marker in the script, the name recorded in `calls`, and the stdout it answers. */
  const SSH_HANDLERS: [string, string, (command: string, stdin?: string) => string][] = [
    ['ss -ltnpH', 'preflight', () => preflightText],
    [
      'openssl genpkey',
      'keygen',
      () => `ACCOUNT_ED25519_PUBLIC_KEY=${secrets.ACCOUNT_ED25519_PUBLIC_KEY}\n`,
    ],
    ['IFS= read -r line', 'setenv', applyEnv],
    ['grep -E', 'read', readKeys],
    ['proxy cert install', 'byo', () => ''],
    ['docker pull', 'pull', () => ''],
  ];
  const BOX_REPLIES: [string, Partial<BoxReply>][] = [
    ['/health', { status: opts.health ?? 200 }],
    ['/onprem/free-license', { status: opts.freeProbe ?? 400 }],
    ['/auth/login', { cookie: 'access_token=c' }],
    ['/portal/terms', { body: { satisfied: true } }],
    ['/portal/subscription', { body: { id: 'sub-1' } }],
  ];

  const deps: ServerDeps = {
    rdc(argv) {
      calls.push(`rdc ${argv.join(' ')}`);
      if (opts.rdcFail && argv.join(' ').startsWith(opts.rdcFail)) {
        return Promise.resolve({ code: 1, stdout: '', stderr: '' });
      }
      return Promise.resolve(ok());
    },
    ssh(machine, command, stdin) {
      const handler = SSH_HANDLERS.find(([marker]) => command.includes(marker));
      if (!handler) {
        calls.push(`ssh ${machine} ?`);
        return Promise.resolve({ code: 9, stdout: '', stderr: 'unknown script' });
      }
      const [, name, answer] = handler;
      const out = answer(command, stdin);
      calls.push(name === 'setenv' ? `ssh ${machine} setenv ${out}` : `ssh ${machine} ${name}`);
      return Promise.resolve(ok(name === 'setenv' ? '' : out));
    },
    box(_target, method, path, body, cookie) {
      calls.push(`https ${method} ${path}`);
      boxRequests.push({ method, path, body, cookie });
      const base: BoxReply = { status: 200, body: {}, sans: opts.sans ?? ['acme.example.com'] };
      const override = Object.entries(opts.boxReplies ?? {}).find(([suffix]) =>
        path.endsWith(suffix)
      );
      if (override) return Promise.resolve({ ...base, ...override[1] });
      const tweak = BOX_REPLIES.find(([suffix]) => path.endsWith(suffix));
      return Promise.resolve(tweak ? { ...base, ...tweak[1] } : base);
    },
    resolve(host) {
      calls.push(`resolve ${host}`);
      return Promise.resolve(resolves.length > 1 ? (resolves.shift() ?? []) : (resolves[0] ?? []));
    },
    ownedZoneToken: () => opts.zoneToken,
    writeDns(_token, zone, type, name, value) {
      dnsWrites.push(`${zone} ${type} ${name} ${value}`);
      return Promise.resolve();
    },
    bwsList: () => Promise.resolve(opts.bwsRows ?? []),
    bwsWrite(request) {
      bwsWrites.push(request);
      return Promise.resolve();
    },
    issueCert(key) {
      calls.push('issue');
      return Promise.resolve(
        opts.issue ?? {
          kind: 'issued',
          cert: {
            certBase64: certFor(key),
            subscriptionId: 'sub-1',
            autoRenewToken: 'renew-token',
            upstreamUrl: 'https://bench.example',
          },
        }
      );
    },
    local(command, args) {
      calls.push(`local ${command} ${args.join(' ')}`);
      return Promise.resolve(0);
    },
    tempDir: () => Promise.resolve('/tmp/fake-dir'),
    readFile(path) {
      const text = opts.files?.[path];
      return text === undefined ? Promise.reject(new Error('ENOENT')) : Promise.resolve(text);
    },
    writePrivate(path, text) {
      written[path] = text;
      // The install record and the owner file are read back from disk by the next verb.
      if (existsSync(dirname(path))) writeFileSync(path, text, { mode: 0o600 });
      return Promise.resolve();
    },
    stdout: (text) => {
      stdout.push(text);
    },
    isTTY: () => opts.tty === true,
    sleep: (ms) => {
      now += ms;
      return Promise.resolve();
    },
    now: () => now,
    secret: () => 'Secret123A1!',
  };
  return { deps, calls, stdout, setEnv, written, bwsWrites, dnsWrites, secrets, boxRequests };
}
