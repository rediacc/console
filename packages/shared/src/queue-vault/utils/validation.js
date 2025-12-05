export function isBase64(value) {
  const base64Pattern = /^[A-Za-z0-9+/]*={0,2}$/;
  const valueWithoutWhitespace = value.replace(/\s/g, '');
  return base64Pattern.test(valueWithoutWhitespace) && valueWithoutWhitespace.length % 4 === 0;
}
export function getParamArray(params, key) {
  const value = params[key];
  if (Array.isArray(value)) {
    return value.filter((item) => typeof item === 'string');
  }
  if (typeof value === 'string' && value.length > 0) {
    return [value];
  }
  return [];
}
export function getParamValue(params, key) {
  const value = params[key];
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}
//# sourceMappingURL=validation.js.map
