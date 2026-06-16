import { spawn } from 'node:child_process';

/**
 * Open a URL in the platform default browser, detached so the CLI can keep
 * holding a foreground tunnel. Failures are reported, never thrown — the
 * URL is always printed separately for manual fallback.
 */
/** Resolve the platform-specific command used to open a URL. */
function browserCommand(url: string): { command: string; args: string[] } {
  if (process.platform === 'darwin') {
    return { command: 'open', args: [url] };
  }
  if (process.platform === 'win32') {
    return { command: 'cmd', args: ['/c', 'start', '', url] };
  }
  return { command: 'xdg-open', args: [url] };
}

export function openBrowser(url: string): boolean {
  const { command, args } = browserCommand(url);

  try {
    const child = spawn(command, args, { detached: true, stdio: 'ignore' });
    child.once('error', () => {});
    child.unref();
    return true;
  } catch {
    return false;
  }
}
