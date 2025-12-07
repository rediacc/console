import { endpoints } from '../../endpoints';
import { parseFirst, parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';
import type {
  AuthLoginResult,
  AuthRequestStatus,
  EnableTfaResponse,
  ForkSessionCredentials,
  UserRequest,
  VerifyTfaResult,
} from '../../types';
import type { ApiResponse } from '../../types/api';

export interface ForkSessionOptions {
  permissionsName?: string;
  expiresInHours?: number;
}

export interface EnableTfaOptions {
  generateOnly?: boolean;
  verificationCode?: string;
  secret?: string;
  confirmEnable?: boolean;
}

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

const toBoolean = (value: unknown): boolean =>
  value === true || value === 1 || value === '1' || value === 'true';

const normalizeAuthStatus = (row?: AuthStatusRow | null): AuthRequestStatus => ({
  isTFAEnabled: toBoolean(row?.isTFAEnabled),
  isAuthorized: toBoolean(row?.isAuthorized),
  authenticationStatus: row?.authenticationStatus ?? 'Unknown',
});

const extractAuthStatus = (response: ApiResponse<AuthStatusRow>): AuthRequestStatus => {
  const row =
    parseFirst<AuthStatusRow>(response, {
      extractor: responseExtractors.byIndex<AuthStatusRow>(1),
    }) ??
    parseFirst<AuthStatusRow>(response, {
      extractor: responseExtractors.byIndex<AuthStatusRow>(0),
    }) ??
    (typeof (response as AuthStatusRow).isTFAEnabled !== 'undefined'
      ? (response as AuthStatusRow)
      : null);

  return normalizeAuthStatus(row);
};

const extractTfaResponse = (response: ApiResponse<EnableTfaResponse>): EnableTfaResponse | null => {
  return (
    parseFirst<EnableTfaResponse>(response, {
      extractor: responseExtractors.byIndex<EnableTfaResponse>(1),
    }) ??
    parseFirst<EnableTfaResponse>(response, {
      extractor: responseExtractors.byIndex<EnableTfaResponse>(0),
    }) ??
    null
  );
};

const extractLoginRow = (response: ApiResponse): AuthLoginRow | null =>
  parseFirst<AuthLoginRow>(response as ApiResponse<AuthLoginRow>, {
    extractor: responseExtractors.primaryOrSecondary,
  });

export function createAuthService(client: ApiClient) {
  return {
    login: (email: string, passwordHash: string, sessionName = 'Web Session') =>
      client.post(
        endpoints.auth.createAuthenticationRequest,
        { name: sessionName },
        {
          headers: {
            'Rediacc-UserEmail': email,
            'Rediacc-UserHash': passwordHash,
          },
        }
      ),

    logout: () => client.post(endpoints.users.deleteUserRequest, {}),

    forkSession: async (
      sessionName: string,
      options: ForkSessionOptions = {}
    ): Promise<ForkSessionCredentials> => {
      const payload: Record<string, unknown> = { childName: sessionName };
      if (options.permissionsName && options.permissionsName.trim() !== '') {
        payload.forkedPermissionsName = options.permissionsName;
      }
      if (options.expiresInHours !== undefined) {
        payload.tokenExpirationHours = options.expiresInHours;
      }
      const response = await client.post(endpoints.auth.forkAuthenticationRequest, payload);

      const credentialsSet =
        response.resultSets?.find((set) => set.resultSetName === 'Credentials') ??
        response.resultSets?.[1] ??
        response.resultSets?.[0];

      const row = credentialsSet?.data?.[0] as
        | (Partial<ForkSessionCredentials> & {
            parentRequestId?: number | string;
          })
        | undefined;

      return {
        requestToken: typeof row?.requestToken === 'string' ? row.requestToken : null,
        nextRequestToken: typeof row?.nextRequestToken === 'string' ? row.nextRequestToken : null,
        parentRequestId:
          typeof row?.parentRequestId === 'number'
            ? row.parentRequestId
            : row?.parentRequestId
              ? Number(row.parentRequestId) || null
              : null,
      };
    },

    activateAccount: (email: string, code: string, passwordHash: string) =>
      client.post(
        endpoints.auth.activateUserAccount,
        { activationCode: code },
        {
          headers: {
            'Rediacc-UserEmail': email,
            'Rediacc-UserHash': passwordHash,
          },
        }
      ),

    getRequestStatus: async (): Promise<AuthRequestStatus> => {
      const response = await client.get<AuthStatusRow>(
        endpoints.auth.getRequestAuthenticationStatus
      );
      return extractAuthStatus(response);
    },

    getSessions: async (): Promise<UserRequest[]> => {
      const response = await client.get<UserRequest>(endpoints.users.getUserRequests);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<UserRequest>(1),
      });
    },

    terminateSession: (requestId: number | string) =>
      client.post(endpoints.users.deleteUserRequest, { requestId }),

    getTfaStatus: async (): Promise<AuthRequestStatus> => {
      const response = await client.post<AuthStatusRow>(endpoints.users.updateUserTfa, {
        action: 'status',
      });
      return extractAuthStatus(response);
    },

    enableTfa: async (
      passwordHash?: string,
      options: EnableTfaOptions = {}
    ): Promise<EnableTfaResponse | null> => {
      // Legacy mode for CLI - no password/options provided
      if (!passwordHash && Object.keys(options).length === 0) {
        const response = await client.post<EnableTfaResponse>(endpoints.users.updateUserTfa, {
          action: 'enable',
        });
        return extractTfaResponse(response);
      }

      const payload: Record<string, unknown> = { enable: true };
      if (passwordHash) payload.userHash = passwordHash;
      if (options.generateOnly) payload.generateOnly = true;
      if (options.verificationCode) payload.verificationCode = options.verificationCode;
      if (options.secret) payload.secret = options.secret;
      if (options.confirmEnable) payload.confirmEnable = true;

      const response = await client.post<EnableTfaResponse>(endpoints.users.updateUserTfa, payload);
      return extractTfaResponse(response);
    },

    disableTfa: async (passwordHash?: string, currentCode?: string): Promise<void> => {
      if (!passwordHash && !currentCode) {
        await client.post(endpoints.users.updateUserTfa, { action: 'disable' });
        return;
      }

      await client.post(endpoints.users.updateUserTfa, {
        enable: false,
        userHash: passwordHash,
        currentCode,
      });
    },

    verifyTfa: async (code: string, sessionName?: string): Promise<VerifyTfaResult> => {
      const response = await client.post<VerifyTfaResult>(
        endpoints.auth.privilegeAuthenticationRequest,
        {
          currentCode: code,
          sessionName,
        }
      );

      const row =
        parseFirst<VerifyTfaResult>(response, {
          extractor: responseExtractors.byIndex<VerifyTfaResult>(1),
        }) ??
        parseFirst<VerifyTfaResult>(response, {
          extractor: responseExtractors.byIndex<VerifyTfaResult>(0),
        }) ??
        null;

      return {
        isAuthorized: toBoolean(row?.isAuthorized),
        result: row?.result,
        hasTFAEnabled: row?.hasTFAEnabled,
      };
    },

    checkRegistration: async (email: string): Promise<{ isRegistered: boolean }> => {
      interface RegistrationRow {
        isRegistered?: boolean | number | string;
      }

      const response = await client.get<RegistrationRow>(endpoints.auth.isRegistered, {
        userEmail: email,
      });
      const row = parseFirst<RegistrationRow>(response, {
        extractor: responseExtractors.primaryOrSecondary,
      });
      const value = row?.isRegistered;
      const isRegistered = value === true || value === 1 || value === '1' || value === 'true';

      return { isRegistered };
    },
  };
}

export function parseAuthenticationResult(response: ApiResponse): AuthLoginResult {
  const row = extractLoginRow(response);
  return {
    isAuthorized: toBoolean(row?.isAuthorized),
    authenticationStatus: row?.authenticationStatus ?? 'unknown',
    vaultCompany: typeof row?.vaultCompany === 'string' ? row.vaultCompany : null,
    companyName: row?.companyName ?? row?.company ?? null,
    company: row?.company ?? null,
    preferredLanguage: typeof row?.preferredLanguage === 'string' ? row.preferredLanguage : null,
  };
}
