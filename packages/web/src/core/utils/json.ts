export function minifyJSON(json: string): string {
  try {
    return JSON.stringify(JSON.parse(json))
  } catch {
    return json
  }
}

export function objectToMinifiedJSON(obj: unknown): string {
  try {
    return JSON.stringify(obj)
  } catch {
    return '{}'
  }
}

export function prettifyJSON(json: string, indent = 2): string {
  try {
    return JSON.stringify(JSON.parse(json), null, indent)
  } catch {
    return json
  }
}
