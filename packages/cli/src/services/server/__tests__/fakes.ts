/**
 * A scripted box, account server and terminal for the `rdc server` tests. Every outside call
 * `ServerDeps` makes is recorded in `calls`, in order.
 */

import { createHash } from 'node:crypto';
import { existsSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';
import { delegationCertId } from '@rediacc/shared/subscription';
import { ServerError } from '../box.js';
import { fingerprintOf } from '../bundle/signing.js';
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
export function certFor(
  key: string,
  sub = 'sub-1',
  planCode = 'ENTERPRISE',
  issuedAt = '2026-11-12T00:00:00Z'
): string {
  const payload = Buffer.from(
    JSON.stringify({
      version: 1,
      subscriptionId: sub,
      planCode,
      delegatedPublicKey: key,
      validFrom: issuedAt,
      validUntil: '2027-11-12T00:00:00Z',
      issuedAt,
    })
  ).toString('base64');
  return Buffer.from(JSON.stringify({ payload, signature: 'sig', publicKeyId: 'k1' })).toString(
    'base64'
  );
}

export const FAKE_RELEASE_BASE = 'https://releases.test/cli';
const FAKE_MODELS_BASE = 'https://releases.test/models';

/** The stable models channel the release host serves by default: a pointer, its manifest, two objects, each signed. */
export const FAKE_MODELS: Record<string, string> = (() => {
  const sha = (text: string) => createHash('sha256').update(text).digest('hex');
  const objects = { 'params.json': '{"k":1}', 'priors.json': '{"p":2}' };
  const manifest = JSON.stringify({
    schema: 1,
    version: '7',
    files: Object.entries(objects).map(([path, body]) => ({
      path,
      sha256: sha(body),
      size: body.length,
    })),
  });
  const served: Record<string, string> = {
    [`${FAKE_MODELS_BASE}/channels/stable.json`]: JSON.stringify({
      seq: 1,
      version: '7',
      manifest_sha256: sha(manifest),
    }),
    [`${FAKE_MODELS_BASE}/channels/stable.json.sig`]: 'sig-channel',
    [`${FAKE_MODELS_BASE}/manifests/7.json`]: manifest,
    [`${FAKE_MODELS_BASE}/manifests/7.json.sig`]: 'sig-manifest',
  };
  for (const body of Object.values(objects)) {
    served[`${FAKE_MODELS_BASE}/objects/${sha(body)}`] = body;
    served[`${FAKE_MODELS_BASE}/objects/${sha(body)}.sig`] = `sig-${sha(body).slice(0, 8)}`;
  }
  return served;
})();

export interface FakeOptions {
  /** What the release host serves, by full URL; any other URL answers like a 404. */
  release?: Record<string, string>;
  tty?: boolean;
  preflight?: Partial<Record<string, string>>;
  secrets?: Record<string, string>;
  templateVersion?: number;
  resolveSequence?: string[][];
  issue?: IssueOutcome;
  /** Whether the config holds a registered account's login; by default, unless `issue` is `no-login`. */
  loggedIn?: boolean;
  health?: number;
  sans?: string[];
  freeProbe?: number;
  /** Free-probe statuses answered in order before `freeProbe` takes over. */
  freeProbeSequence?: number[];
  bwsRows?: BwsRow[];
  zoneToken?: string;
  files?: Record<string, string>;
  rdcFail?: string;
  /** The stderr a failing `rdcFail` call carries. */
  rdcStderr?: string;
  /** Per-path-suffix answers that win over the defaults (a refused login, a 404 route). */
  boxReplies?: Record<string, Partial<BoxReply>>;
  /** The box's live `data/web/delegation-cert.json`, as `certFor` gives it (base64 of the JSON). */
  liveCert?: string;
  /**
   * How the server answers an inbox drop: `apply` (the default) makes the dropped cert live and
   * answers applied; `reject` answers rejected with `reason`; `none` never answers; `busy` refuses
   * the drop.
   */
  inbox?: 'apply' | 'none' | 'busy' | { reason: string; detail?: string };
  /** The box's `cert-inbox/boot-rejected.json`: present until an applied drop clears it (unless `markerSticks`). */
  bootRejected?: { reason: string; detail?: string; certId?: string | null; at?: string };
  /** The marker survives an applied drop (a server that did not clear it). */
  markerSticks?: boolean;
  /** What the offline essentials probe reports missing (space-separated). */
  essentialsMissing?: string;
  /** Whether the machine's Docker already holds the proxy image. */
  proxyImage?: 'present' | 'absent';
  /** The sha256 this CLI's renet reports, to simulate a bundle built with another renet. */
  renetSha?: string;
  /** The template sums on the box: `baseline` false is a box that recorded none. */
  templateEdits?: { baseline?: boolean; edited?: string[] };
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
  /** Every body dropped into the inbox (`new.json`), parsed. */
  drops: { requestId: string; cert: { payload: string; signature: string; publicKeyId: string } }[];
  /** Every local file the run read or wrote, by path. Mutable: a test edits one to tamper with it. */
  files: Record<string, string>;
  /** Every file copied to the machine, as `machine:remote`. */
  uploads: string[];
  /** The box's live cert JSON after the run, or undefined. */
  live(): string | undefined;
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
  const files: Record<string, string> = { ...opts.files };
  const uploads: string[] = [];
  const sha = (text: string) => createHash('sha256').update(text).digest('hex');
  const resolves = [...(opts.resolveSequence ?? [['203.0.113.10']])];
  const drops: Fake['drops'] = [];
  let live: string | undefined = opts.liveCert
    ? Buffer.from(opts.liveCert, 'base64').toString('utf-8')
    : undefined;
  let liveCertId: string | undefined;
  const refreshLiveId = async () => {
    liveCertId = live ? await delegationCertId(JSON.parse(live) as { payload: string }) : undefined;
  };
  /** The inbox file waiting for the server, as the box would hold it. */
  let pending: Fake['drops'][number] | undefined;
  const inboxDrop = (_command: string, stdin?: string) => {
    if (opts.inbox === 'busy' || pending) return 'inbox=busy\n';
    pending = JSON.parse(stdin ?? '{}') as Fake['drops'][number];
    drops.push(pending);
    return 'inbox=dropped\n';
  };
  const inboxResult = async (_command: string, stdin?: string) => {
    const id = (stdin ?? '').trim();
    const decided = pending;
    if (!decided || decided.requestId !== id || opts.inbox === 'none') return 'result=none\n';
    pending = undefined;
    const certId = await delegationCertId(decided.cert);
    if (typeof opts.inbox === 'object') {
      const answer = { requestId: id, reason: opts.inbox.reason, detail: opts.inbox.detail ?? '' };
      return `result=rejected\n${JSON.stringify(answer, null, 2)}\n`;
    }
    live = JSON.stringify(decided.cert);
    if (!opts.markerSticks) marker = undefined;
    await refreshLiveId();
    const payload = JSON.parse(Buffer.from(decided.cert.payload, 'base64').toString()) as {
      issuedAt: string;
    };
    const answer = { requestId: id, certId, issuedAt: payload.issuedAt };
    return `result=applied\n${JSON.stringify(answer, null, 2)}\n`;
  };
  const migrate = (_command: string, stdin?: string) => {
    const value = secrets.DELEGATION_CERT_BASE64;
    let state = 'none';
    if (value && !live) {
      if (pending) return 'migrate=busy\n';
      pending = {
        requestId: (stdin ?? '').trim(),
        cert: JSON.parse(Buffer.from(value, 'base64').toString()) as Fake['drops'][number]['cert'],
      };
      drops.push(pending);
      state = 'dropped';
    }
    delete secrets.DELEGATION_CERT_BASE64;
    return `migrate=${state}\n`;
  };
  let marker = opts.bootRejected;
  const readMarker = () =>
    marker
      ? JSON.stringify({ detail: '', certId: null, at: '2026-11-12T19:58:00Z', ...marker })
      : '';
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
  const SSH_HANDLERS: [
    string,
    string,
    (command: string, stdin?: string) => string | Promise<string>,
  ][] = [
    ['missing=$miss', 'essentials', () => `missing=${opts.essentialsMissing ?? ''}\n`],
    ['traefik=present', 'proxy-probe', () => `traefik=${opts.proxyImage ?? 'absent'}\n`],
    ['docker load -i', 'proxy-load', () => ''],
    [
      'baseline=none',
      'template-edits',
      () => {
        const e = opts.templateEdits;
        if (e?.baseline === false) return 'baseline=none\n';
        return `baseline=sums\n${(e?.edited ?? []).map((f) => `edited=${f}\n`).join('')}`;
      },
    ],
    ['.template-sums.tmp', 'template-sums', () => ''],
    ['inbox=dropped', 'inbox-drop', inboxDrop],
    ['result=none', 'inbox-result', inboxResult],
    ['migrate=$state', 'migrate-cert', migrate],
    ['boot-rejected.json', 'read-boot-rejected', readMarker],
    ['then cat "$f"', 'read-live-cert', () => live ?? ''],
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
  const probeQueue = [...(opts.freeProbeSequence ?? [])];
  const BOX_REPLIES: [string, Partial<BoxReply>][] = [
    ['/health', { status: opts.health ?? 200 }],
    ['/onprem/free-license', { status: opts.freeProbe ?? 400 }],
    ['/auth/login', { cookie: 'access_token=c' }],
    ['/portal/terms', { body: { satisfied: true } }],
    ['/portal/subscription', { body: { id: 'sub-1' } }],
  ];

  /** Answers that follow the fake's state: the live cert's id, and the scripted free-probe queue. */
  const certStatusBody = async () => {
    await refreshLiveId();
    return { cert: liveCertId ? { certId: liveCertId } : null };
  };
  const stateReply = async (path: string, base: BoxReply): Promise<BoxReply | undefined> => {
    if (path.endsWith('/onprem/cert-status')) return { ...base, body: await certStatusBody() };
    const queued = path.endsWith('/onprem/free-license') ? probeQueue.shift() : undefined;
    return queued === undefined ? undefined : { ...base, status: queued };
  };

  const deps: ServerDeps = {
    rdc(argv) {
      calls.push(`rdc ${argv.join(' ')}`);
      if (opts.rdcFail && argv.join(' ').startsWith(opts.rdcFail)) {
        return Promise.resolve({ code: 1, stdout: '', stderr: opts.rdcStderr ?? '' });
      }
      return Promise.resolve(ok());
    },
    async ssh(machine, command, stdin) {
      const handler = SSH_HANDLERS.find(([marker]) => command.includes(marker));
      if (!handler) {
        calls.push(`ssh ${machine} ?`);
        return { code: 9, stdout: '', stderr: 'unknown script' };
      }
      const [, name, answer] = handler;
      const out = await answer(command, stdin);
      calls.push(name === 'setenv' ? `ssh ${machine} setenv ${out}` : `ssh ${machine} ${name}`);
      return ok(name === 'setenv' ? '' : out);
    },
    async box(_target, method, path, body, cookie) {
      calls.push(`https ${method} ${path}`);
      boxRequests.push({ method, path, body, cookie });
      const base: BoxReply = { status: 200, body: {}, sans: opts.sans ?? ['acme.example.com'] };
      const override = Object.entries(opts.boxReplies ?? {}).find(([suffix]) =>
        path.endsWith(suffix)
      );
      if (override) return { ...base, ...override[1] };
      const live = await stateReply(path, base);
      if (live) return live;
      const tweak = BOX_REPLIES.find(([suffix]) => path.endsWith(suffix));
      return tweak ? { ...base, ...tweak[1] } : base;
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
    hasAccountLogin: () => opts.loggedIn ?? opts.issue?.kind !== 'no-login',
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
      const out = args.indexOf('-o');
      if (args[0] === 'save' && out >= 0) files[args[out + 1]] = `tar:${args.at(-1)}`;
      return Promise.resolve(0);
    },
    localOut(command, args) {
      calls.push(`localOut ${command} ${args.join(' ')}`);
      return Promise.resolve(ok(`sha256:id-of-${args.at(-1)}\n`));
    },
    sha256File(path) {
      const text = files[path];
      return text === undefined ? Promise.reject(new Error('ENOENT')) : Promise.resolve(sha(text));
    },
    makeDir(path) {
      calls.push(`mkdir ${path}`);
      return Promise.resolve();
    },
    renetAsset(arch, dest) {
      if (dest) files[dest] = `renet-bytes-${arch}`;
      return Promise.resolve({
        sha256: opts.renetSha ?? sha(`renet-bytes-${arch}`),
        version: 'v-test',
      });
    },
    release: {
      baseUrl: () => FAKE_RELEASE_BASE,
      fetchText(url) {
        calls.push(`release GET ${url}`);
        const body = opts.release?.[url] ?? FAKE_MODELS[url];
        return body === undefined
          ? Promise.reject(new ServerError(`cliDownloadFailed ${url} HTTP 404`))
          : Promise.resolve(body);
      },
      download(url, dest) {
        calls.push(`release GET ${url}`);
        const body = opts.release?.[url] ?? FAKE_MODELS[url];
        if (body === undefined) {
          return Promise.reject(new ServerError(`cliDownloadFailed ${url} HTTP 404`));
        }
        files[dest] = body;
        return Promise.resolve();
      },
    },
    uploadFile(machine, _local, remote) {
      calls.push(`upload ${machine} ${remote}`);
      uploads.push(`${machine}:${remote}`);
      return Promise.resolve();
    },
    tempDir: () => Promise.resolve('/tmp/fake-dir'),
    readFile(path) {
      const text = files[path];
      return text === undefined ? Promise.reject(new Error('ENOENT')) : Promise.resolve(text);
    },
    writePrivate(path, text) {
      written[path] = text;
      files[path] = text;
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
  return {
    deps,
    calls,
    stdout,
    setEnv,
    written,
    bwsWrites,
    dnsWrites,
    secrets,
    boxRequests,
    drops,
    files,
    uploads,
    live: () => live,
  };
}

/** The fingerprint `rdc server bundle` printed for the bundle held in `files` under `dir`. */
export function signerOf(files: Record<string, string>, dir: string): string {
  const fingerprint = fingerprintOf(files[`${dir}/signer.pub`] ?? '');
  if (!fingerprint) throw new Error(`no signer.pub under ${dir}`);
  return fingerprint;
}
