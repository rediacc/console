import { describe, expect, it } from 'vitest';
import { isMcpServeFastPath } from '../fast-path.js';

const base = ['node', 'rdc'];

describe('isMcpServeFastPath', () => {
  it('takes the fast path for mcp serve', () => {
    expect(isMcpServeFastPath([...base, 'mcp', 'serve'])).toBe(true);
    expect(isMcpServeFastPath([...base, 'mcp', 'serve', '--config', 'x', '--timeout', '5'])).toBe(
      true
    );
  });

  it('leaves the fast path for --help and -h so Commander prints help', () => {
    expect(isMcpServeFastPath([...base, 'mcp', 'serve', '--help'])).toBe(false);
    expect(isMcpServeFastPath([...base, 'mcp', 'serve', '-h'])).toBe(false);
    expect(isMcpServeFastPath([...base, '--help', 'mcp', 'serve'])).toBe(false);
  });

  it('ignores other commands', () => {
    expect(isMcpServeFastPath([...base, 'mcp'])).toBe(false);
    expect(isMcpServeFastPath([...base, 'serve'])).toBe(false);
  });
});
