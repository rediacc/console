export function minifyJSON(json: string): string {
  try {
    return JSON.stringify(JSON.parse(json))
  } catch (error) {
    console.error('Failed to minify JSON:', error)
    return json
  }
}

export function objectToMinifiedJSON(obj: any): string {
  try {
    return JSON.stringify(obj)
  } catch (error) {
    console.error('Failed to convert object to minified JSON:', error)
    return '{}'
  }
}

export function prettifyJSON(json: string, indent = 2): string {
  try {
    return JSON.stringify(JSON.parse(json), null, indent)
  } catch (error) {
    console.error('Failed to prettify JSON:', error)
    return json
  }
}