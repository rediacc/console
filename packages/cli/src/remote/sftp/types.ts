/**
 * SFTP client configuration and exec-session types.
 */

/**
 * Configuration for SFTP client connection
 */
export interface SFTPClientConfig {
  /** SSH host */
  host: string;
  /** SSH port (default: 22) */
  port?: number;
  /** SSH username */
  username: string;
  /** SSH private key (PEM format) */
  privateKey: string;
  /** SSH private key passphrase */
  passphrase?: string;
  /** Connection timeout in ms (default: 10000) */
  timeout?: number;
  /** Keep-alive interval in ms (default: 10000) */
  keepaliveInterval?: number;
  /**
   * Machine name as configured, used only to make a host-key mismatch error
   * actionable (it names the machine to pass to `rdc machine scan-keys`).
   * Falls back to `host` when absent.
   */
  machineName?: string;
  /** Known hosts entries for host-key verification (OpenSSH format) */
  knownHosts?: string;
  /**
   * The machine's IPv6 address. A connect to `host` that never completes
   * (EGRESS_UNREACHABLE) is retried once over it; some egress networks drop
   * IPv4 to a host they reach over IPv6.
   */
  ipv6?: string;
}

/** A live exec channel with stdin held open, returned by `SFTPClient.execSession`. */
export interface ExecSessionHandle {
  /** Write one line to the remote stdin (a trailing newline is added when missing). */
  write(line: string): void;
  /** End the remote stdin (EOF). */
  end(): void;
  /** The next stdout line, or null once the channel has closed and no line is buffered. */
  nextLine(): Promise<string | null>;
  /** Exit code on close; null when the channel closed without one. */
  exit: Promise<number | null>;
  isClosed(): boolean;
}

export type Ipv6Resolver = (hostname: string) => Promise<string | undefined>;
