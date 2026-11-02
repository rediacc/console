import { SFTPClient } from '../remote/sftp/client.js';

/**
 * Build an SFTPClient with the ssh2 client factory and the AAAA resolver the tests plant. The
 * connection pool offers neither seam, and these tests drive `connect()` itself rather than a lease.
 */
export function seamedSftpClient(...args: ConstructorParameters<typeof SFTPClient>): SFTPClient {
  return new SFTPClient(...args);
}
