import {
  quickInstallUnixCommand,
  quickInstallWinCommand,
} from '@rediacc/shared/config/install-commands';
import { describe, expect, it } from 'vitest';
import { SITE_URL } from '../constants';
import { QUICK_INSTALL_UNIX, QUICK_INSTALL_WIN } from '../install';

describe('quick install snippets', () => {
  it('renders the unix comment line followed by the shared one-liner for the site origin', () => {
    expect(QUICK_INSTALL_UNIX).toBe(`# Linux / macOS\n${quickInstallUnixCommand(SITE_URL)}`);
    expect(QUICK_INSTALL_UNIX.split('\n')).toEqual([
      '# Linux / macOS',
      `curl -fsSL ${SITE_URL}/install.sh | bash`,
    ]);
  });

  it('renders the windows comment line followed by the shared one-liner for the site origin', () => {
    expect(QUICK_INSTALL_WIN).toBe(`# Windows (PowerShell)\n${quickInstallWinCommand(SITE_URL)}`);
    expect(QUICK_INSTALL_WIN.split('\n')).toEqual([
      '# Windows (PowerShell)',
      `irm ${SITE_URL}/install.ps1 | iex`,
    ]);
  });
});
