/**
 * Auth Parsers
 */

import { extractPrimaryOrSecondary, extractFirstByIndex, extractRowsByIndex, toBoolean } from './base';
import type {
  AuthLoginResult,
  AuthRequestStatus,
  EnableTfaResponse,
  ForkSessionCredentials,
  UserRequest,
  VerifyTfaResult,
} from '../../types';
import type { ApiResponse } from '../../types/api';

interface AuthStatusRow {
  isTFAEnabled?: boolean | number | string;
  isAuthorized?: boolean | number | string;
  authenticationStatus?: string;
}

interface AuthLoginRow {
  isAuthorized?: boolean | number | string;
  authenticationStatus?: string;
  vaultCompany?: string | null;
  companyName?: string | null;
  company?: string | null;
  preferredLanguage?: string | null;
}

function normalizeAuthStatus(row?: AuthStatusRow | null): AuthRequestStatus {
  return {
    isTFAEnabled: toBoolean(row?.isTFAEnabled),
    isAuthorized: toBoolean(row?.isAuthorized),
    authenticationStatus: row?.authenticationStatus ?? 'Unknown',
  };
}

export function parseGetRequestAuthenticationStatus(
  response: ApiResponse<AuthStatusRow>
): AuthRequestStatus {
  const row =
    extractFirstByIndex<AuthStatusRow>(response, 1) ??
    extractFirstByIndex<AuthStatusRow>(response, 0) ??
    (typeof (response as AuthStatusRow).isTFAEnabled !== 'undefined'
      ? (response as AuthStatusRow)
      : null);

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
      vaultCompany: null,
      companyName: null,
      company: null,
      preferredLanguage: null,
    };
  }

  return {
    isAuthorized: toBoolean(row.isAuthorized),
    authenticationStatus: row.authenticationStatus ?? 'unknown',
    vaultCompany: typeof row.vaultCompany === 'string' ? row.vaultCompany : null,
    companyName: row.companyName ?? row.company ?? null,
    company: row.company ?? null,
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
    hasTFAEnabled: row?.hasTFAEnabled,
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
  return {
    requestToken: typeof row?.requestToken === 'string' ? row.requestToken : null,
    nextRequestToken: typeof row?.nextRequestToken === 'string' ? row.nextRequestToken : null,
    parentRequestId:
      typeof parentRequestId === 'number'
        ? parentRequestId
        : typeof parentRequestId === 'string'
          ? Number(parentRequestId) || null
          : null,
  };
}

export function parseGetUserRequests(response: ApiResponse<UserRequest>): UserRequest[] {
  return extractRowsByIndex<UserRequest>(response, 1);
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
