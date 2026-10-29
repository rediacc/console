/**
 * Stands in for `cloudflare:sockets`, which exists only inside workerd (vitest.config.ts aliases the module here). `connect` calls whatever `setConnect` installed; with nothing installed it throws, so no suite opens a real socket by accident.
 *
 * `fakeSocket` builds a socket from a script of reads, and records `close()` calls and any writer taken, which the probe must never do.
 */

type ConnectImpl = (address: string | SocketAddress, options?: SocketOptions) => Socket;

const unset: ConnectImpl = () => {
  throw new Error('cloudflare:sockets: no connect installed (setConnect) under vitest');
};

let impl: ConnectImpl = unset;

export function connect(address: string | SocketAddress, options?: SocketOptions): Socket {
  return impl(address, options);
}

/** Install the `connect` the next calls use; undefined restores the throwing default. */
export function setConnect(next: ConnectImpl | undefined): void {
  impl = next ?? unset;
}

/** One scripted `read()`: bytes (a string is UTF-8), the end of the stream, a rejection, or a read that never settles. */
export type ScriptedRead = string | Uint8Array | 'end' | { reject: unknown } | 'hang';

export interface FakeSocket {
  socket: Socket;
  closes: number;
  writersTaken: number;
  reads: number;
}

/** A socket whose reads follow `script`, then end. `opened` resolves unless `openedRejects`. */
export function fakeSocket(script: ScriptedRead[], options: { openedRejects?: boolean } = {}) {
  const state: FakeSocket = {
    socket: undefined as unknown as Socket,
    closes: 0,
    writersTaken: 0,
    reads: 0,
  };
  const queue = [...script];
  const reader = {
    read: (): Promise<ReadableStreamReadResult<Uint8Array>> => {
      state.reads += 1;
      const next = queue.shift() ?? 'end';
      if (next === 'end') return Promise.resolve({ done: true, value: undefined });
      if (next === 'hang') return new Promise(() => undefined);
      if (typeof next === 'object' && 'reject' in next) return Promise.reject(next.reject);
      const value = typeof next === 'string' ? new TextEncoder().encode(next) : next;
      return Promise.resolve({ done: false, value });
    },
    releaseLock: () => undefined,
    cancel: () => Promise.resolve(),
    closed: Promise.resolve(undefined),
  };
  const opened = options.openedRejects
    ? Promise.reject(new Error('connect failed'))
    : Promise.resolve({ remoteAddress: '203.0.113.7:22' });
  opened.catch(() => undefined);
  state.socket = {
    readable: { getReader: () => reader } as unknown as ReadableStream,
    get writable(): WritableStream {
      state.writersTaken += 1;
      return { getWriter: () => ({}) } as unknown as WritableStream;
    },
    // Never settles, as for a reset connect (workerd #1305): the probe must not await it.
    closed: new Promise<void>(() => undefined),
    opened,
    upgraded: false,
    secureTransport: 'off',
    close: () => {
      state.closes += 1;
      return Promise.resolve();
    },
    startTls: () => {
      throw new Error('not used');
    },
  } as Socket;
  return state;
}
