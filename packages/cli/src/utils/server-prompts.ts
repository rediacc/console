/**
 * The questions `rdc server install` asks on a terminal when a value has no flag.
 *
 * Every value also has a flag. With no terminal a missing value is refused, naming its flag, the
 * way the region picker refuses (region-prompt.ts). inquirer is loaded only when a question is
 * actually asked.
 */

import { t } from '../i18n/index.js';
import type { TlsMethod } from '../services/server/types.js';
import { TLS_METHODS } from '../services/server/types.js';
import { ValidationError } from './errors.js';

export type MachineAnswer =
  | { kind: 'existing'; name: string }
  | { kind: 'add'; name: string; ip: string; user: string; port: number };

export interface ServerPrompts {
  /** Pick a configured machine, or register an existing server or LAN device. */
  machine(configured: string[]): Promise<MachineAnswer>;
  text(message: string, defaultValue?: string): Promise<string>;
  tls(defaultValue: TlsMethod): Promise<TlsMethod>;
  confirm(message: string, defaultValue: boolean): Promise<boolean>;
}

/** The refusal for a value that has no flag and no terminal to ask on. */
export function promptRequiresTTY(flag: string): ValidationError {
  return new ValidationError(t('commands.server.errors.needsTTY', { flag }));
}

const ADD_EXISTING = '__add-existing__';

const TLS_LABELS: Record<TlsMethod, string> = {
  letsencrypt: 'commands.server.prompts.tlsLetsencrypt',
  cloudflare: 'commands.server.prompts.tlsCloudflare',
  byo: 'commands.server.prompts.tlsByo',
};

type PromptFn = (questions: Record<string, unknown>[]) => Promise<Record<string, unknown>>;

async function loadPrompt(): Promise<PromptFn> {
  // Lazy: rxjs and the prompt graph load only when a question is shown.
  const inquirer = await import('inquirer');
  return inquirer.createPromptModule() as unknown as PromptFn;
}

async function ask<T>(question: Record<string, unknown>): Promise<T> {
  const prompt = await loadPrompt();
  const answer = await prompt([{ ...question, name: 'value' }]);
  return answer.value as T;
}

const required = (value: string) =>
  value.trim().length > 0 || t('commands.server.prompts.required');

/** The live prompts, over inquirer. */
export function inquirerPrompts(): ServerPrompts {
  return {
    async machine(configured) {
      const choices = [
        { name: t('commands.server.prompts.machineAddExisting'), value: ADD_EXISTING },
        ...configured.map((name) => ({ name, value: name })),
      ];
      const picked = await ask<string>({
        type: 'select',
        message: t('commands.server.prompts.machine'),
        choices,
        default: ADD_EXISTING,
      });
      if (picked !== ADD_EXISTING) return { kind: 'existing', name: picked };
      process.stderr.write(`${t('commands.server.prompts.provisionHint')}\n`);
      const ip = await ask<string>({
        type: 'input',
        message: t('commands.server.prompts.machineIp'),
        validate: required,
      });
      const user = await ask<string>({
        type: 'input',
        message: t('commands.server.prompts.machineUser'),
        default: process.env.USER,
        validate: required,
      });
      const port = await ask<string>({
        type: 'input',
        message: t('commands.server.prompts.machinePort'),
        default: '22',
      });
      const name = await ask<string>({
        type: 'input',
        message: t('commands.server.prompts.machineName'),
        validate: required,
      });
      return {
        kind: 'add',
        name: name.trim(),
        ip: ip.trim(),
        user: user.trim(),
        port: Number.parseInt(port, 10) || 22,
      };
    },
    text(message, defaultValue) {
      return ask<string>({
        type: 'input',
        message,
        default: defaultValue,
        validate: required,
      }).then((v) => v.trim());
    },
    tls(defaultValue) {
      return ask<TlsMethod>({
        type: 'select',
        message: t('commands.server.prompts.tls'),
        choices: TLS_METHODS.map((m) => ({ name: t(TLS_LABELS[m]), value: m })),
        default: defaultValue,
      });
    },
    confirm(message, defaultValue) {
      return ask<boolean>({ type: 'confirm', message, default: defaultValue });
    },
  };
}
