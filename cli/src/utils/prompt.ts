import { createPromptModule } from 'inquirer'

const prompt = createPromptModule()

export async function askText(
  message: string,
  options: { default?: string; validate?: (input: string) => boolean | string } = {}
): Promise<string> {
  const { answer } = await prompt([
    {
      type: 'input',
      name: 'answer',
      message,
      default: options.default,
      validate: options.validate,
    },
  ])
  return answer
}

export async function askPassword(message: string): Promise<string> {
  const { answer } = await prompt([
    {
      type: 'password',
      name: 'answer',
      message,
      mask: '*',
    },
  ])
  return answer
}

export async function askConfirm(message: string, defaultValue = false): Promise<boolean> {
  const { answer } = await prompt([
    {
      type: 'confirm',
      name: 'answer',
      message,
      default: defaultValue,
    },
  ])
  return answer
}

export async function askSelect<T extends string>(
  message: string,
  choices: Array<{ name: string; value: T } | T>
): Promise<T> {
  const { answer } = await prompt([
    {
      type: 'list',
      name: 'answer',
      message,
      choices,
    },
  ])
  return answer
}

export async function askMultiSelect<T extends string>(
  message: string,
  choices: Array<{ name: string; value: T; checked?: boolean } | T>
): Promise<T[]> {
  const { answer } = await prompt([
    {
      type: 'checkbox',
      name: 'answer',
      message,
      choices,
    },
  ])
  return answer
}
