/**
 * Auth Parsers
 */

import { DEFAULTS } from '../../config';
import type {
  AuthLoginResult,
  AuthRequestStatus,
  EnableTfaResponse,
  ForkSessionCredentials,
  GetUserRequests_ResultSet1,
  VerifyTfaResult,
} from '../../types';
import type { ApiResponse } from '../../types/api';
import {
  extractFirstByIndex,
  extractPrimaryOrSecondary,
  extractRowsByIndex,
  toBoolean,
} from './base';

interface AuthStatusRow {
  isTFAEnabled?: boolean | number | string;
  isAuthorized?: boolean | number | string;
  authenticationStatus?: string;
}

interface AuthLoginRow {
  isAuthorized?: boolean | number | string;
  authenticationStatus?: string;
  vaultOrganization?: string | null;
  organizationName?: string | null;
  organization?: string | null;
  preferredLanguage?: string | null;
}

function normalizeAuthStatus(row?: AuthStatusRow | null): AuthRequestStatus {
  return {
    isTFAEnabled: toBoolean(row?.isTFAEnabled),
    isAuthorized: toBoolean(row?.isAuthorized),
    authenticationStatus: row?.authenticationStatus ?? DEFAULTS.STATUS.UNKNOWN,
  };
}

export function parseGetRequestAuthenticationStatus(
  response: ApiResponse<AuthStatusRow>
): AuthRequestStatus {
  const row =
    extractFirstByIndex<AuthStatusRow>(response, 1) ??
    extractFirstByIndex<AuthStatusRow>(response, 0) ??
    (typeof (response as AuthStatusRow).isTFAEnabled === 'undefined'
      ? null
      : (response as AuthStatusRow));

  return normalizeAuthStatus(row);
}

export function parseCreateAuthenticationRequest(response: ApiResponse): AuthLoginResult {
  const row =
    extractFirstByIndex<AuthLoginRow>(response, 1) ??
    extractPrimaryOrSecondary(response as ApiResponse<AuthLoginRow>)[0];

  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- row may be undefined at runtime
  if (!row) {
    return {
      isAuthorized: false,
      authenticationStatus: 'unknown',
      vaultOrganization: null,
      organizationName: null,
      organization: null,
      preferredLanguage: null,
    };
  }

  return {
    isAuthorized: toBoolean(row.isAuthorized),
    authenticationStatus: row.authenticationStatus ?? DEFAULTS.TELEMETRY.UNKNOWN,
    vaultOrganization: typeof row.vaultOrganization === 'string' ? row.vaultOrganization : null,
    organizationName: row.organizationName ?? row.organization ?? null,
    organization: row.organization ?? null,
    preferredLanguage: typeof row.preferredLanguage === 'string' ? row.preferredLanguage : null,
  };
}

export function parseUpdateUserTFA(
  response: ApiResponse<EnableTfaResponse>
): EnableTfaResponse | null {
  return (
    extractFirstByIndex<EnableTfaResponse>(response, 1) ??
    extractFirstByIndex<EnableTfaResponse>(response, 0) ??
    null
  );
}

export function parsePrivilegeAuthenticationRequest(
  response: ApiResponse<VerifyTfaResult>
): VerifyTfaResult {
  const row =
    extractFirstByIndex<VerifyTfaResult>(response, 1) ??
    extractFirstByIndex<VerifyTfaResult>(response, 0) ??
    null;

  return {
    isAuthorized: toBoolean(row?.isAuthorized),
    result: row?.result,
    isTFAEnabled: row?.isTFAEnabled,
  };
}

export function parseForkAuthenticationRequest(response: ApiResponse): ForkSessionCredentials {
  const foundSet = response.resultSets.find((set) => set.resultSetName === 'Credentials');
  const fallbackSet = response.resultSets.length > 1 ? response.resultSets[1] : undefined;
  const credentialsSet = foundSet ?? fallbackSet;

  const row = (credentialsSet ? credentialsSet.data[0] : undefined) as
    | (Partial<ForkSessionCredentials> & { parentRequestId?: number | string })
    | undefined;

  const parentRequestId = row?.parentRequestId;
  let resolvedParentRequestId: number | null;
  if (typeof parentRequestId === 'number') {
    resolvedParentRequestId = parentRequestId;
  } else if (typeof parentRequestId === 'string') {
    resolvedParentRequestId = Number(parentRequestId) || null;
  } else {
    resolvedParentRequestId = null;
  }
  return {
    requestToken: typeof row?.requestToken === 'string' ? row.requestToken : null,
    nextRequestToken: typeof row?.nextRequestToken === 'string' ? row.nextRequestToken : null,
    parentRequestId: resolvedParentRequestId,
  };
}

export function parseGetUserRequests(
  response: ApiResponse<GetUserRequests_ResultSet1>
): GetUserRequests_ResultSet1[] {
  return extractRowsByIndex<GetUserRequests_ResultSet1>(response, 1);
}

export function parseIsRegistered(response: ApiResponse): { isRegistered: boolean } {
  interface RegistrationRow {
    isRegistered?: boolean | number | string;
  }
  const row = extractPrimaryOrSecondary(response as ApiResponse<RegistrationRow>)[0];
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- row may be undefined at runtime
  return { isRegistered: row ? toBoolean(row.isRegistered) : false };
}

export const parseAuthStatus = parseGetRequestAuthenticationStatus;
export const parseLoginResult = parseCreateAuthenticationRequest;
export const parseTfaVerification = parsePrivilegeAuthenticationRequest;
