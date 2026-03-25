import type { UserContext } from '@rediacc/shared/api';
import { TELEMETRY_ATTRIBUTES } from '@rediacc/shared/telemetry';

export function buildUserAttributes(userContext: Partial<UserContext>): Record<string, string> {
  const attrs: Record<string, string> = {};

  if (userContext.email) {
    const domain = userContext.email.split('@')[1];
    if (domain) {
      attrs['user.email_domain'] = domain;
    }
  }

  if (userContext.organization) {
    attrs['user.organization'] = userContext.organization;
  }

  if (userContext.teamName) {
    attrs['user.team'] = userContext.teamName;
    attrs['team.name'] = userContext.teamName;
  }

  if (userContext.subscriptionId) {
    attrs[TELEMETRY_ATTRIBUTES.subscriptionId] = userContext.subscriptionId;
  }

  if (userContext.subscriptionPlanCode) {
    attrs[TELEMETRY_ATTRIBUTES.subscriptionPlanCode] = userContext.subscriptionPlanCode;
  }

  if (userContext.subscriptionStatus) {
    attrs[TELEMETRY_ATTRIBUTES.subscriptionStatus] = userContext.subscriptionStatus;
  }

  if (userContext.subscriptionSource) {
    attrs[TELEMETRY_ATTRIBUTES.subscriptionSource] = userContext.subscriptionSource;
  }

  return attrs;
}

export function flattenAttributes(
  obj: Record<string, unknown>,
  prefix = ''
): Record<string, string | number | boolean> {
  const result: Record<string, string | number | boolean> = {};

  for (const [key, value] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key;

    if (value === null || value === undefined) {
      continue;
    } else if (typeof value === 'object' && !Array.isArray(value)) {
      Object.assign(result, flattenAttributes(value as Record<string, unknown>, fullKey));
    } else if (
      typeof value === 'string' ||
      typeof value === 'number' ||
      typeof value === 'boolean'
    ) {
      result[fullKey] = value;
    } else {
      result[fullKey] = String(value);
    }
  }

  return result;
}
