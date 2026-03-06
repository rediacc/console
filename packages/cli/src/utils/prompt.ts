import { createPromptModule } from 'inquirer';
import { EXIT_CODES } from '../types/index.js';

const prompt = createPromptModule();

function requireInteractive(context: string): void {
  if (process.stdin.isTTY !== true) {
    console.error(`Error: ${context} required but stdin is not a TTY. Use --yes to auto-confirm.`);
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }
}

export async function askText(
  message: string,
  options: { default?: string; validate?: (input: string) => boolean | string } = {}
): Promise<string> {
  requireInteractive('Interactive input');
  const { answer } = await prompt([
    {
      type: 'input',
      name: 'answer',
      message,
      default: options.default,
      validate: options.validate,
    },
  ]);
  return answer;
}

export async function askPassword(message: string): Promise<string> {
  requireInteractive('Password input');
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
