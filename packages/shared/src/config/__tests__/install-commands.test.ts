import { describe, expect, it } from 'vitest';
import {
  QUICK_INSTALL_UNIX_COMMAND,
  QUICK_INSTALL_WIN_COMMAND,
  quickInstallUnixCommand,
  quickInstallWinCommand,
} from '../install-commands.js';
import { WK_SITE_ORIGIN } from '../well-known.generated.js';

describe('install-commands', () => {
  it('reads the site origin from the well-known list as a bare https origin', () => {
    // The pins below build from WK_SITE_ORIGIN, so they follow a host change; this keeps the value itself a bare https origin, the shape the one-liners need.
    expect(WK_SITE_ORIGIN).toMatch(/^https:\/\/[a-z0-9.-]+$/);
  });

  it('pins the unix one-liner', () => {
    expect(QUICK_INSTALL_UNIX_COMMAND).toBe(`curl -fsSL ${WK_SITE_ORIGIN}/install.sh | bash`);
  });

  it('pins the windows one-liner', () => {
    expect(QUICK_INSTALL_WIN_COMMAND).toBe(`irm ${WK_SITE_ORIGIN}/install.ps1 | iex`);
  });

  it('pins the production host literally, so a host change fails here too', () => {
    expect(QUICK_INSTALL_UNIX_COMMAND).toBe('curl -fsSL https://www.rediacc.com/install.sh | bash');
    expect(QUICK_INSTALL_WIN_COMMAND).toBe('irm https://www.rediacc.com/install.ps1 | iex');
  });

  it('builds against an overridden origin', () => {
    expect(quickInstallUnixCommand('https://x.test')).toBe(
      'curl -fsSL https://x.test/install.sh | bash'
    );
    expect(quickInstallWinCommand('https://x.test')).toBe('irm https://x.test/install.ps1 | iex');
  });
});
