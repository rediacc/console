import { describe, expect, it } from 'vitest';
import { quoteCmdArg, windowsLaunch } from '../executable.js';

const CODE_CMD = 'C:\\Program Files\\Microsoft VS Code\\bin\\code.cmd';
const URI = 'vscode-remote://ssh-remote+rediacc-m1/mnt/my repo';

describe('windowsLaunch', () => {
  it('runs a batch wrapper through cmd.exe with verbatim arguments, never shell: true', () => {
    const launch = windowsLaunch(CODE_CMD, ['--folder-uri', URI], 'C:\\Windows\\system32\\cmd.exe');
    expect(launch).not.toHaveProperty('shell');
    expect(launch.command).toBe('C:\\Windows\\system32\\cmd.exe');
    expect(launch.windowsVerbatimArguments).toBe(true);
    expect(launch.args.slice(0, 3)).toEqual(['/d', '/s', '/c']);
    expect(launch.args).toHaveLength(4);
  });

  it('keeps a path with spaces and a spaced argument each as one token', () => {
    const line = windowsLaunch(CODE_CMD, ['--folder-uri', URI]).args[3]!;
    // The whole line is wrapped once for /s /c; inside it every space is caret-escaped, so cmd never splits on it.
    expect(line).toBe(
      `"C:\\Program^ Files\\Microsoft^ VS^ Code\\bin\\code.cmd ${quoteCmdArg('--folder-uri')} ${quoteCmdArg(URI)}"`
    );
    // Only the two token separators are bare spaces; the ones inside the path and the URI are escaped.
    expect(line.match(/[^^] /g)).toHaveLength(2);
  });

  it('spawns a real .exe directly, with no cmd.exe in between', () => {
    const exe = 'C:\\Users\\me\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe';
    expect(windowsLaunch(exe, ['--folder-uri', URI])).toEqual({
      command: exe,
      args: ['--folder-uri', URI],
      windowsVerbatimArguments: false,
    });
  });
});

describe('quoteCmdArg', () => {
  it('double-escapes cmd metacharacters for the batch re-parse', () => {
    expect(quoteCmdArg('a b')).toBe('^^^"a^^^ b^^^"');
    expect(quoteCmdArg('%PATH%&x')).toBe('^^^"^^^%PATH^^^%^^^&x^^^"');
  });

  it('escapes inner quotes and trailing backslashes for CommandLineToArgvW', () => {
    expect(quoteCmdArg('say "hi"')).toBe('^^^"say^^^ \\^^^"hi\\^^^"^^^"');
    expect(quoteCmdArg('C:\\dir\\')).toBe('^^^"C:\\dir\\\\^^^"');
  });
});
