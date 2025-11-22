export function minifyJSON(json: string): string {
  try {
    return JSON.stringify(JSON.parse(json))
  } catch (error) {
    return json
  }
}

export function objectToMinifiedJSON(obj: any): string {
  try {
    return JSON.stringify(obj)
  } catch (error) {
    return '{}'
  }
}

export function prettifyJSON(json: string, indent = 2): string {
  try {
    return JSON.stringify(JSON.parse(json), null, indent)
  } catch (error) {
    return json
  }
}