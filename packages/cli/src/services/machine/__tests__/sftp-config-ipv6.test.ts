import { describe, expect, it } from 'vitest';
import { sftpConfigForMachine } from '../machine-connection.js';

describe('sftpConfigForMachine IPv6', () => {
  it("carries the machine's public IPv6 as the connect retry target", () => {
    const config = sftpConfigForMachine(
      { ip: '72.61.137.225', user: 'root', infra: { publicIPv6: '2a02:4780:c:e9b5::1' } },
      'KEY'
    );
    expect(config.host).toBe('72.61.137.225');
    expect(config.ipv6).toBe('2a02:4780:c:e9b5::1');
  });

  it('omits ipv6 for a machine without one', () => {
    const config = sftpConfigForMachine({ ip: '192.0.2.10', user: 'root' }, 'KEY');
    expect(config).not.toHaveProperty('ipv6');
  });
});
