import { parseFirst, parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';
import type {
  GetCompanyUsers_ResultSet1,
  UpdateUserAssignedPermissionsParams,
  UpdateUserEmailParams,
  UpdateUserLanguageParams,
  UpdateUserPasswordParams,
  UpdateUserToActivatedParams,
  UpdateUserToDeactivatedParams,
  UpdateUserVaultParams,
  UserVault,
} from '../../types';

export interface CreateUserOptions {
  passwordHash?: string;
  language?: string;
}

export interface CreateUserResult {
  activationCode?: string;
}

export function createUsersService(client: ApiClient) {
  return {
    list: async (): Promise<GetCompanyUsers_ResultSet1[]> => {
      const response = await client.get<GetCompanyUsers_ResultSet1>('/GetCompanyUsers');
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<GetCompanyUsers_ResultSet1>(1),
        filter: (user) => Boolean(user.userEmail),
        map: (user) => ({
          ...user,
          activated: Boolean(user.activated),
        }),
      });
    },

    create: async (
      email: string,
      passwordHash?: string,
      options: CreateUserOptions = {}
    ): Promise<CreateUserResult> => {
      const payload: Record<string, unknown> = {
        newUserEmail: email,
      };
      if (passwordHash) payload.newUserHash = passwordHash;
      if (options.language) payload.languagePreference = options.language;
      const response = await client.post<{ activationCode?: string }>('/CreateNewUser', payload);
      const row = parseFirst<{ activationCode?: string }>(response, {
        extractor: responseExtractors.byIndex(0),
      });
      return {
        activationCode: row?.activationCode,
      };
    },

    activate: (params: UpdateUserToActivatedParams) =>
      client.post('/UpdateUserToActivated', params),

    deactivate: (params: UpdateUserToDeactivatedParams) =>
      client.post('/UpdateUserToDeactivated', params),

    updateEmail: (params: UpdateUserEmailParams) => client.post('/UpdateUserEmail', params),

    updatePassword: (params: UpdateUserPasswordParams) =>
      client.post('/UpdateUserPassword', params),

    updateLanguage: (params: UpdateUserLanguageParams) =>
      client.post('/UpdateUserLanguage', params),

    getVault: async (): Promise<UserVault> => {
      interface UserVaultRow {
        vaultContent?: string;
        vaultVersion?: number;
        userCredential?: string | null;
      }

      const response = await client.get<UserVaultRow>('/GetUserVault');
      const first = parseFirst<UserVaultRow>(response, {
        extractor: responseExtractors.byIndex(1),
      });
      return {
        vault: first?.vaultContent ?? '{}',
        vaultVersion: first?.vaultVersion ?? 1,
        userCredential: first?.userCredential ?? null,
      };
    },

    updateVault: (params: UpdateUserVaultParams) => client.post('/UpdateUserVault', params),

    assignPermissions: (params: UpdateUserAssignedPermissionsParams) =>
      client.post('/UpdateUserAssignedPermissions', params),
  };
}
