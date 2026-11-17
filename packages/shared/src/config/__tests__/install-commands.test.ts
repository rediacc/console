import { describe, expect, it } from 'vitest';
import {
  QUICK_INSTALL_UNIX_COMMAND,
  QUICK_INSTALL_WIN_COMMAND,
  quickInstallUnixCommand,
  quickInstallWinCommand,
} from '../install-commands.js';

describe('install-commands', () => {
  it('pins the unix one-liner', () => {
    expect(QUICK_INSTALL_UNIX_COMMAND).toBe('curl -fsSL https://www.rediacc.com/install.sh | bash');
  });

  it('pins the windows one-liner', () => {
    expect(QUICK_INSTALL_WIN_COMMAND).toBe('irm https://www.rediacc.com/install.ps1 | iex');
  });

  it('builds against an overridden origin', () => {
    expect(quickInstallUnixCommand('https://x.test')).toBe(
      'curl -fsSL https://x.test/install.sh | bash'
    );
    expect(quickInstallWinCommand('https://x.test')).toBe('irm https://x.test/install.ps1 | iex');
  });
});
