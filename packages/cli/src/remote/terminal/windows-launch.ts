import { randomBytes } from 'node:crypto';
import { rmSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { gzipSync } from 'node:zlib';
import { getTempPath } from '../utils/platform.js';

/**
 * Windows external terminals run ssh from a temp `.cmd` file (cmd, Windows
 * Terminal) or an encoded PowerShell script. Neither can carry a command with
 * line breaks or shell metacharacters through its own command line, so the
 * remote command ships as base64 text with none of them (`windowsRemoteBootstrap`).
 */

/** A cmd.exe line is cut at 8191 characters; a `.cmd` file line is too. */
const CMD_LINE_LIMIT = 8000;

/** The quote characters PowerShell treats as single-quote delimiters (U+2018, U+2019, U+201A, U+201B). */
const POWERSHELL_QUOTES = /[‘’‚‛]/;

/**
 * The remote command a Windows terminal passes to ssh: the real script
 * (gzip, base64) is decoded into a private temp file on the machine and run by
 * bash, which deletes the file as it starts. Bash keeps the terminal as stdin,
 * so the script's own `exec bash --rcfile ...` is the same interactive session
 * the inline path starts. The text holds no line break, quote, caret or percent
 * sign; `|`, `>`, `&&`, `$` and `()` stay literal because the one argument
 * sits inside double quotes on both cmd.exe and the MSVC argv rules.
 *
 * The sandbox gateway points BASH_ENV at the repo's sandbox bashrc, which prints
 * the "Rediacc sandbox" banner on a tty. The inline path starts one non-interactive
 * bash (the gateway's `bash -c`); this wrapper would start a second, so the
 * script's bash runs with BASH_ENV empty and the script restores it first thing.
 */
export function windowsRemoteBootstrap(remoteCommand: string): string {
  const script = `export BASH_ENV=$RDC_BASH_ENV; unset RDC_BASH_ENV; rm -f -- "$0"\n${remoteCommand}\n`;
  const payload = gzipSync(Buffer.from(script, 'utf8')).toString('base64');
  return `f=$(mktemp)&&echo ${payload}|base64 -d|gzip -dc>$f&&exec env RDC_BASH_ENV=$BASH_ENV BASH_ENV= bash $f`;
}

/** The text of a file or argument cmd.exe reads: printable ASCII only, no double quote. */
function assertCmdSafe(text: string, what: string): void {
  if (/[^ -~]|"/.test(text)) {
    throw new Error(`cannot quote ${what} for cmd.exe: ${JSON.stringify(text)}`);
  }
}

/** One argument for a `.cmd` line: bare when plain, else in double quotes, where cmd.exe keeps `& | < > ( ) ^ !` literal and `%` doubles. */
export function cmdQuoteArg(arg: string): string {
  assertCmdSafe(arg, 'an argument');
  if (/^[\w./\\:@+=-]+$/.test(arg)) return arg;
  const body = arg.replaceAll('%', '%%').replace(/\\+$/, (run) => run + run);
  return `"${body}"`;
}

/**
 * The `.cmd` text of a launch: line 1 runs the command, line 2 deletes the
 * handed-off files, and the last line deletes the script with the silent
 * `(goto) 2>nul & del` idiom (the failing `(goto)` unwinds the batch context, so
 * cmd does not print "The batch file cannot be found."). Every line ends in CRLF. A path with
 * `%` (cmd expands it even inside quotes) or a non-ASCII character is refused.
 */
export function cmdLaunchScript(argv: string[], cleanupFiles: string[]): string {
  const run = `@${argv.map(cmdQuoteArg).join(' ')}`;
  if (run.length > CMD_LINE_LIMIT) {
    throw new Error(`the terminal command is ${run.length} characters, too long for cmd.exe`);
  }
  const files = cleanupFiles.map((file) => {
    assertCmdSafe(file, 'a temp file path');
    if (file.includes('%'))
      throw new Error(`cannot quote a temp file path for cmd.exe: ${JSON.stringify(file)}`);
    return `"${file.replaceAll('/', '\\')}"`;
  });
  const deleteFiles = files.length > 0 ? `@del /q ${files.join(' ')}\r\n` : '';
  return `${run}\r\n${deleteFiles}@(goto) 2>nul & del /q "%~f0"\r\n`;
}

/**
 * Writes the launch `.cmd` into the temp directory, owner-only like the key
 * files it deletes, and returns its path. The path is the only thing that
 * crosses cmd.exe and wt.exe, so `%`, `;` (Windows Terminal splits on it),
 * `"` and non-ASCII characters in it are refused.
 */
export function writeCmdLaunchFile(argv: string[], cleanupFiles: string[]): string {
  const content = cmdLaunchScript(argv, cleanupFiles);
  const path = join(getTempPath(), `rdc-term-${randomBytes(8).toString('hex')}.cmd`);
  assertCmdSafe(path, 'the launch script path');
  if (/[%;]/.test(path)) {
    throw new Error(`cannot quote the launch script path for cmd.exe: ${JSON.stringify(path)}`);
  }
  writeFileSync(path, content, { mode: 0o600 });
  return path;
}

/** Removes a launch script a failed spawn left behind. */
export function discardCmdLaunchFile(path: string): void {
  rmSync(path, { force: true });
}

/** One PowerShell single-quoted literal. U+2018/U+2019/U+201A/U+201B also delimit one, so a value holding them is refused. */
export function powershellLiteral(value: string): string {
  if (POWERSHELL_QUOTES.test(value)) {
    throw new Error(`cannot quote a value for PowerShell: ${JSON.stringify(value)}`);
  }
  return `'${value.replaceAll("'", "''")}'`;
}

/** The PowerShell tail that deletes `files` after the command, ignoring failures. */
export function powershellCleanupSuffix(files: string[]): string {
  if (files.length === 0) return '';
  return `\nRemove-Item -LiteralPath ${files.map(powershellLiteral).join(',')} -Force -ErrorAction SilentlyContinue`;
}

/**
 * A PowerShell script that runs `argv`, each element a single-quoted literal
 * (the remote command holds no quote or line break), and its `-EncodedCommand`
 * form (UTF-16LE, base64), so the script crosses powershell.exe's own command
 * line without quoting.
 */
export function powershellEncodedCommand(
  argv: string[],
  keepOpen: boolean,
  cleanupFiles: string[] = []
): string {
  if (argv.some((arg) => /["\r\n]/.test(arg))) {
    throw new Error('cannot quote a double quote or line break in a PowerShell argument');
  }
  const run = `& ${argv.map(powershellLiteral).join(' ')}${powershellCleanupSuffix(cleanupFiles)}`;
  const script = keepOpen ? run : `${run}\nRead-Host -Prompt 'Press Enter to exit'`;
  return Buffer.from(script, 'utf16le').toString('base64');
}
