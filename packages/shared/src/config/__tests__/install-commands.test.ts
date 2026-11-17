import { describe, expect, it } from 'vitest';
import {
  QUICK_INSTALL_UNIX_COMMAND,
  QUICK_INSTALL_WIN_COMMAND,
  quickInstallUnixCommand,
  quickInstallWinCommand,
} from '../install-commands.js';
import { WK_SITE_ORIGIN } from '../well-known.generated.js';

describe('install-commands', () => {
  it('pins the unix one-liner', () => {
    expect(QUICK_INSTALL_UNIX_COMMAND).toBe(`curl -fsSL ${WK_SITE_ORIGIN}/install.sh | bash`);
  });

  it('pins the windows one-liner', () => {
    expect(QUICK_INSTALL_WIN_COMMAND).toBe(`irm ${WK_SITE_ORIGIN}/install.ps1 | iex`);
  });

  it('builds against an overridden origin', () => {
    expect(quickInstallUnixCommand('https://x.test')).toBe(
      'curl -fsSL https://x.test/install.sh | bash'
    );
    expect(quickInstallWinCommand('https://x.test')).toBe('irm https://x.test/install.ps1 | iex');
  });
});
