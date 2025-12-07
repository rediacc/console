import { endpoints } from '../../endpoints';
import { parseFirst, parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';
import type { User, UserVault } from '../../types';
import type {
  CreateNewUserParams,
  UpdateUserToActivatedParams,
  UpdateUserToDeactivatedParams,
  UpdateUserEmailParams,
  UpdateUserPasswordParams,
  UpdateUserLanguageParams,
  UpdateUserVaultParams,
  UpdateUserAssignedPermissionsParams,
} from '../../types';

export interface CreateUserOptions {
  passwordHash?: string;
  language?: string;
  fullName?: string;
}

export interface CreateUserResult {
  activationCode?: string;
}

export function createUsersService(client: ApiClient) {
  return {
    list: async (): Promise<User[]> => {
      const response = await client.get<User>(endpoints.company.getCompanyUsers);
      return parseResponse(response, {
        extractor: responseExtractors.byIndex<User>(1),
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
      if (options.fullName) payload.fullName = options.fullName;
      const response = await client.post<{ activationCode?: string }>(
        endpoints.users.createUser,
        payload
      );
      const row = parseFirst<{ activationCode?: string }>(response, {
        extractor: responseExtractors.byIndex(0),
      });
      return {
        activationCode: row?.activationCode,
      };
    },

    activate: (params: UpdateUserToActivatedParams) =>
      client.post(endpoints.users.updateUserToActivated, params),

    deactivate: (params: UpdateUserToDeactivatedParams) =>
      client.post(endpoints.users.updateUserToDeactivated, params),

    updateEmail: (params: UpdateUserEmailParams) => client.post(endpoints.users.updateUserEmail, params),

    updatePassword: (params: UpdateUserPasswordParams) =>
      client.post(endpoints.users.updateUserPassword, params),

    updateLanguage: (params: UpdateUserLanguageParams) =>
      client.post(endpoints.users.updateUserLanguage, params),

    getVault: async (): Promise<UserVault> => {
      interface UserVaultRow {
        vaultContent?: string;
        vaultVersion?: number;
        userCredential?: string | null;
      }

      const response = await client.get<UserVaultRow>(endpoints.users.getUserVault);
      const first = parseFirst<UserVaultRow>(response, {
        extractor: responseExtractors.byIndex(1),
      });
      return {
        vault: first?.vaultContent || '{}',
        vaultVersion: first?.vaultVersion || 1,
        userCredential: first?.userCredential ?? null,
      };
    },

    updateVault: (params: UpdateUserVaultParams) =>
      client.post(endpoints.users.updateUserVault, params),

    assignPermissions: (params: UpdateUserAssignedPermissionsParams) =>
      client.post(endpoints.users.updateUserAssignedPermissions, params),
  };
}
