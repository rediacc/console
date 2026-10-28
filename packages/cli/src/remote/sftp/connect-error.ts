/**
 * Named SSH connect failures.
 *
 * ssh2 reports every connect failure as an `error` event with only a message,
 * and "Timed out while waiting for handshake" covers two very different
 * causes: a TCP connection that never completed, and a peer that connected and
 * never sent a banner. The client `connect` event (TCP is up) tells them apart,
 * so the classifier takes it as an input and the error carries the answer.
 */

import { EXIT_CODES } from '../../types/index.js';

export type SshConnectFailureKind =
  | 'unreachable'
  | 'handshake-timeout'
  | 'refused'
  | 'auth'
  | 'other';

export interface SshConnectFailureInput {
  /** ssh2's `err.level`, e.g. 'client-timeout'. */
  level?: string;
  /** ssh2's `err.code`, e.g. 'ECONNREFUSED'. */
  code?: string;
  /** Whether the client `connect` event (TCP socket connected) fired first. */
  tcpConnected: boolean;
}

export function classifySshConnectFailure(input: SshConnectFailureInput): SshConnectFailureKind {
  const { level, code, tcpConnected } = input;
  if (level === 'client-timeout') return tcpConnected ? 'handshake-timeout' : 'unreachable';
  if (level === 'client-socket') {
    if (code === 'ETIMEDOUT') return 'unreachable';
    if (code === 'ECONNREFUSED') return 'refused';
    return 'other';
  }
  if (level === 'client-authentication') return 'auth';
  return 'other';
}

interface KindInfo {
  errorCode?: string;
  exitCode: number;
  retryable: boolean;
  guidance?: string;
}

const KIND_INFO: Record<SshConnectFailureKind, KindInfo> = {
  unreachable: {
    errorCode: 'EGRESS_UNREACHABLE',
    exitCode: EXIT_CODES.NETWORK_ERROR,
    retryable: true,
    guidance:
      'Retry the command. If it keeps failing, check that the machine accepts SSH from the internet.',
  },
  refused: {
    errorCode: 'SSH_REFUSED',
    exitCode: EXIT_CODES.NETWORK_ERROR,
    retryable: true,
    guidance: 'Check that the SSH service is running on the machine and the port is right.',
  },
  'handshake-timeout': {
    errorCode: 'SSH_HANDSHAKE_TIMEOUT',
    exitCode: EXIT_CODES.NETWORK_ERROR,
    retryable: true,
    guidance:
      'Retry the command. The machine accepted the connection but its SSH service did not answer.',
  },
  auth: {
    errorCode: 'SSH_AUTH_FAILED',
    exitCode: EXIT_CODES.GENERAL_ERROR,
    retryable: false,
    guidance: 'Check the machine user and the SSH key in the config.',
  },
  other: { exitCode: EXIT_CODES.GENERAL_ERROR, retryable: false },
};

export interface SshConnectErrorInit {
  kind: SshConnectFailureKind;
  host: string;
  port: number;
  timeoutMs: number;
  /** The ssh2 message, kept for `other` and for the detail of the named kinds. */
  cause: string;
}

function describeFailure(init: SshConnectErrorInit): string {
  const target = `${init.host}:${init.port}`;
  const seconds = Math.round(init.timeoutMs / 100) / 10;
  switch (init.kind) {
    case 'unreachable':
      return `${target} never answered the TCP connection attempt within ${seconds} s; the address is valid but no reply came back. The machine may be down, a firewall may be dropping the traffic, or the executor's network path to it is blocked.`;
    case 'refused':
      return `${target} refused the TCP connection. The machine is reachable, but nothing is accepting SSH on that port.`;
    case 'handshake-timeout':
      return `${target} accepted the TCP connection but did not complete the SSH handshake within ${seconds} s.`;
    case 'auth':
      return `${target} rejected the SSH credentials: ${init.cause}`;
    default:
      return `SSH connection error: ${init.cause}`;
  }
}

export class SshConnectError extends Error {
  readonly kind: SshConnectFailureKind;
  readonly host: string;
  readonly port: number;
  readonly timeoutMs: number;
  readonly errorCode: string | undefined;
  readonly exitCode: number;
  readonly retryable: boolean;
  readonly guidance: string | undefined;

  constructor(init: SshConnectErrorInit) {
    super(describeFailure(init));
    this.name = 'SshConnectError';
    const info = KIND_INFO[init.kind];
    this.kind = init.kind;
    this.host = init.host;
    this.port = init.port;
    this.timeoutMs = init.timeoutMs;
    this.errorCode = info.errorCode;
    this.exitCode = info.exitCode;
    this.retryable = info.retryable;
    this.guidance = info.guidance;
  }
}
