export function minifyJSON(json: string): string {
  try {
    return JSON.stringify(JSON.parse(json));
  } catch {
    return json;
  }
}
