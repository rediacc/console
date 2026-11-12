/**
 * `rdc server`: the self-hosted account server (Elite) as a repo on one machine.
 *
 * Every step reaches the outside world through `ServerDeps`, so the tests script it: the child
 * `rdc` calls, the SSH channel to the box, HTTPS to the domain, DNS, the account server, the clock
 * and the terminal.
 */

export type TlsMethod = 'letsencrypt' | 'cloudflare' | 'byo';
export type LicenceMode = 'auto' | 'free';

export const TLS_METHODS: readonly TlsMethod[] = ['letsencrypt', 'cloudflare', 'byo'];
export const LICENCE_MODES: readonly LicenceMode[] = ['auto', 'free'];

export interface ProcResult {
  code: number;
  stdout: string;
  stderr: string;
}

/** One HTTPS answer from the box. `sans` are the DNS names of the presented certificate. */
export interface BoxReply {
  status: number;
  body: unknown;
  cookie?: string;
  sans: string[];
}

export interface BoxTarget {
  domain: string;
  /** Connect here instead of resolving the domain (a LAN box, or DNS that has not caught up). */
  address?: string;
  /** PEM of a private CA that signed the box's certificate (bring-your-own TLS). */
  ca?: string;
}

/** What `POST /delegation/issue` answers, reduced to what the install keeps. */
export interface IssuedCert {
  certBase64: string;
  subscriptionId: string;
  autoRenewToken?: string;
  upstreamUrl?: string;
}

export type IssueOutcome =
  | { kind: 'issued'; cert: IssuedCert }
  | { kind: 'no-login' }
  | { kind: 'missing-scope' }
  | { kind: 'plan-disallows'; message: string }
  | { kind: 'other-key'; certId: string; message: string };

/** One `bws secret list` row, as far as the backup reads it. */
export interface BwsRow {
  id?: string;
  key?: string;
  value?: string;
  projectId?: string;
}

/** One write `bws-write.ts` performs; the value travels on its stdin. */
export interface BwsWriteRequest {
  op: 'create' | 'edit';
  id?: string;
  key: string;
  value: string;
  note: string;
  projectIds: [string];
}

export interface ServerDeps {
  /** Run a child `rdc` with these arguments (the active `--config` is prepended by the caller). */
  rdc(argv: string[]): Promise<ProcResult>;
  /** Run `command` on the machine over SSH, feeding `stdin`; never through argv for a secret. */
  ssh(machine: string, command: string, stdin?: string): Promise<ProcResult>;
  /** One HTTPS request to the box. Status 0 when nothing answered. */
  box(
    target: BoxTarget,
    method: string,
    path: string,
    body?: unknown,
    cookie?: string
  ): Promise<BoxReply>;
  /** The A and AAAA answers for `host`; empty when it does not resolve. */
  resolve(host: string): Promise<string[]>;
  /** The Cloudflare token for the zones Rediacc owns, from the environment; undefined when unset. */
  ownedZoneToken(): string | undefined;
  /** Create or update one DNS-only record in a zone Rediacc owns. */
  writeDns(
    token: string,
    zone: string,
    type: 'A' | 'AAAA',
    name: string,
    value: string
  ): Promise<void>;
  /** `bws secret list` rows (Bitwarden Secrets Manager), under BWS_ACCESS_TOKEN. */
  bwsList(): Promise<BwsRow[]>;
  /** One value-carrying write through `bws-write.ts`, the value on stdin. */
  bwsWrite(request: BwsWriteRequest): Promise<void>;
  /** `POST /delegation/issue` under the logged-in config's token. */
  issueCert(delegatedPublicKey: string): Promise<IssueOutcome>;
  /** Run a local program (`docker save` for `--local-image`); resolves to its exit code. */
  local(command: string, args: string[]): Promise<number>;
  /** A fresh private temporary directory. */
  tempDir(): Promise<string>;
  /** Read a local file (a cert, a TLS pair, a CA). */
  readFile(path: string): Promise<string>;
  /** Write `text` to `path` at mode 0600. */
  writePrivate(path: string, text: string): Promise<void>;
  /** Write to stdout: data, the recovery bundle, `server backup`. */
  stdout(text: string): void;
  /** Whether stdin and stdout are a terminal: prompts and the one-time bundle need both. */
  isTTY(): boolean;
  sleep(ms: number): Promise<void>;
  now(): number;
  /** Random secret for the owner's first password. */
  secret(): string;
}
