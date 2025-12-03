const tryParseJson = (value: unknown): unknown => {
  if (typeof value !== 'string') {
    return value
  }

  try {
    return JSON.parse(value)
  } catch {
    return value
  }
}

export function parseDoubleEncodedJson<T>(value: string, nestedKeys: string[] = []): T {
  let parsed: unknown = value
  let previous: unknown = undefined

  while (typeof parsed === 'string' && parsed !== previous) {
    previous = parsed
    parsed = tryParseJson(parsed)
  }

  if (typeof parsed === 'object' && parsed !== null) {
    for (const key of nestedKeys) {
      const current = (parsed as Record<string, unknown>)[key]
      if (current !== undefined) {
        ;(parsed as Record<string, unknown>)[key] = tryParseJson(current)
      }
    }
  }

  return parsed as T
}

export function fixTripleEncodedFields(
  source: Record<string, unknown>,
  fields: string[]
): void {
  fields.forEach((field) => {
    if (!Object.prototype.hasOwnProperty.call(source, field)) return
    source[field] = tryParseJson(source[field])
  })
}
