import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockInfo } = vi.hoisted(() => ({
  mockInfo: vi.fn(),
}));

vi.mock('../../services/output.js', () => ({
  outputService: {
    info: mockInfo,
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

import { printServiceUrlPattern } from '../repo-batch-utils.js';

describe('printServiceUrlPattern', () => {
  beforeEach(() => {
    mockInfo.mockClear();
  });

  it('builds {service}.<repo>.<machineDomain> for a grand repo', () => {
    printServiceUrlPattern('mail', 'hostinger.example.com');

    expect(mockInfo).toHaveBeenCalledTimes(1);
    const printed = mockInfo.mock.calls[0][0] as string;
    expect(printed).toContain('https://{service}.mail.hostinger.example.com');
    expect(printed).not.toContain(':aldaniz');
    expect(printed.split('https://')[1] ?? '').not.toContain(':');
  });

  it('flattens fork composite key into {service}-fork-<tag>.<parent>.<machineDomain>', () => {
    printServiceUrlPattern('demo-stackoverflow:aldaniz2', 'hostinger.example.com');

    expect(mockInfo).toHaveBeenCalledTimes(1);
    const printed = mockInfo.mock.calls[0][0] as string;
    expect(printed).toContain(
      'https://{service}-fork-aldaniz2.demo-stackoverflow.hostinger.example.com'
    );
    expect(printed.split('https://')[1] ?? '').not.toContain(':');
  });
});
