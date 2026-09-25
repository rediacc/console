import { exitProcess, writeStderr } from '../services/core/request-context.js';
import { EXIT_CODES } from '../types/index.js';

// Lazy-load inquirer (pulls in rxjs and the whole prompt graph) only when an interactive prompt is actually shown. Startup, including --version, --help, and every non-prompting command, never executes it. The dynamic
// import is cached by the module loader, so repeated prompts pay once.
async function getPrompt(
  streams?: Parameters<typeof import('inquirer')['createPromptModule']>[0]
): Promise<ReturnType<typeof import('inquirer')['createPromptModule']>> {
  const { createPromptModule } = await import('inquirer');
  return createPromptModule(streams);
}

function requireInteractive(context: string): void {
  if (process.stdin.isTTY !== true) {
    writeStderr(`Error: ${context} required but stdin is not a TTY. Use --yes to auto-confirm.\n`);
    exitProcess(EXIT_CODES.INVALID_ARGUMENTS);
  }
}

export async function askPassword(message: string): Promise<string> {
  requireInteractive('Password input');
  const prompt = await getPrompt();
  const { answer } = await prompt([
    {
      type: 'password',
      name: 'answer',
      message,
      mask: '*',
    },
  ]);
  return answer;
}

export async function askConfirm(message: string, defaultValue = false): Promise<boolean> {
  if (process.env.REDIACC_YES === '1') return true;
  requireInteractive('Confirmation');
  const prompt = await getPrompt();
  const { answer } = await prompt([
    {
      type: 'confirm',
      name: 'answer',
      message,
      default: defaultValue,
    },
  ]);
  return answer;
}

/**
 * Ask for a short visible value that must match `pattern` (re-asks until it does).
 * Renders on stderr, so `--output json` stdout stays clean. Returns the trimmed input.
 */
export async function askInput(message: string, pattern: RegExp): Promise<string> {
  requireInteractive('Input');
  const prompt = await getPrompt({ output: process.stderr });
  const { answer } = await prompt([
    {
      type: 'input',
      name: 'answer',
      message,
      validate: (value: string) => pattern.test(value.trim()),
    },
  ]);
  return String(answer).trim();
}
