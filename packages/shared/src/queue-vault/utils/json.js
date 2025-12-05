export function minifyJSON(json) {
  try {
    return JSON.stringify(JSON.parse(json));
  } catch {
    return json;
  }
}
//# sourceMappingURL=json.js.map
