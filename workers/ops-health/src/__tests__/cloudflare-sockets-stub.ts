/**
 * Stands in for `cloudflare:sockets`, which exists only inside workerd (vitest.config.ts aliases the module here). Every suite injects its own `connect` through the Runtime, so this one throws: no test opens a real socket by accident.
 */
export function connect(_address: string | SocketAddress, _options?: SocketOptions): Socket {
  throw new Error('cloudflare:sockets: inject a connect through the Runtime under vitest');
}
