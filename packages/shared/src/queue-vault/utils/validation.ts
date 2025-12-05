export function isBase64(value: string): boolean {
  const base64Pattern = /^[A-Za-z0-9+/]*={0,2}$/;
  const valueWithoutWhitespace = value.replace(/\s/g, '');
  return base64Pattern.test(valueWithoutWhitespace) && valueWithoutWhitespace.length % 4 === 0;
}

export function getParamArray(params: Record<string, unknown>, key: string): string[] {
  const value = params[key];
  if (Array.isArray(value)) {
    return value.filter((item): item is string => typeof item === 'string');
  }
  if (typeof value === 'string' && value.length > 0) {
    return [value];
  }
  return [];
}

export function getParamValue(params: Record<string, unknown>, key: string): string | undefined {
  const value = params[key];
  return typeof value === 'string' && value.length > 0 ? value : undefined;
}
