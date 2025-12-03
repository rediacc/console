import ora, { Ora } from 'ora'

let currentSpinner: Ora | null = null

export function startSpinner(text: string): Ora {
  if (currentSpinner) {
    currentSpinner.stop()
  }
  currentSpinner = ora(text).start()
  return currentSpinner
}

export function stopSpinner(success = true, text?: string): void {
  if (!currentSpinner) return

  if (success) {
    currentSpinner.succeed(text)
  } else {
    currentSpinner.fail(text)
  }
  currentSpinner = null
}

export function updateSpinner(text: string): void {
  if (currentSpinner) {
    currentSpinner.text = text
  }
}

export async function withSpinner<T>(
  text: string,
  fn: () => Promise<T>,
  successText?: string
): Promise<T> {
  const spinner = startSpinner(text)
  try {
    const result = await fn()
    spinner.succeed(successText || text)
    return result
  } catch (error) {
    spinner.fail()
    throw error
  }
}
