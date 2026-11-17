import { WK_SITE_ORIGIN } from './well-known.generated.js';

/** Bare quick-install one-liners; callers add any comment line they want. */
export function quickInstallUnixCommand(origin: string = WK_SITE_ORIGIN): string {
  return `curl -fsSL ${origin}/install.sh | bash`;
}

export function quickInstallWinCommand(origin: string = WK_SITE_ORIGIN): string {
  return `irm ${origin}/install.ps1 | iex`;
}

export const QUICK_INSTALL_UNIX_COMMAND = quickInstallUnixCommand();
export const QUICK_INSTALL_WIN_COMMAND = quickInstallWinCommand();
