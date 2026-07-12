import { exitProcess } from '../services/core/request-context.js';
import { EXIT_CODES } from '../types/index.js';

// Lazy-load inquirer (pulls in rxjs and the whole prompt graph) only when
// an interactive prompt is actually shown. Startup — including --version,
// --help, and every non-prompting command — never executes it. The dynamic
// import is cached by the module loader, so repeated prompts pay once.
async function getPrompt(): Promise<ReturnType<typeof import('inquirer')['createPromptModule']>> {
  const { createPromptModule } = await import('inquirer');
  return createPromptModule();
}

function requireInteractive(context: string): void {
  if (process.stdin.isTTY !== true) {
    console.error(`Error: ${context} required but stdin is not a TTY. Use --yes to auto-confirm.`);
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
