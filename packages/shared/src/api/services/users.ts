import { endpoints } from '../../endpoints';
import type { User, UserVault } from '../../types';
import { parseFirst, parseResponse, responseExtractors } from '../parseResponse';
import type { ApiClient } from './types';

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

    activate: (email: string) =>
      client.post(endpoints.users.updateUserToActivated, { userEmail: email }),

    deactivate: (email: string) =>
      client.post(endpoints.users.updateUserToDeactivated, { userEmail: email }),

    updateEmail: (currentEmail: string, newEmail: string) =>
      client.post(endpoints.users.updateUserEmail, {
        currentUserEmail: currentEmail,
        newUserEmail: newEmail,
      }),

    updatePassword: (passwordHash: string) =>
      client.post(endpoints.users.updateUserPassword, { userNewPass: passwordHash }),

    updateLanguage: (language: string) =>
      client.post(endpoints.users.updateUserLanguage, { preferredLanguage: language }),

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

    updateVault: (vault: string, vaultVersion: number) =>
      client.post(endpoints.users.updateUserVault, {
        vaultContent: vault,
        vaultVersion,
      }),

    assignPermissions: (email: string, groupName: string) =>
      client.post(endpoints.users.updateUserAssignedPermissions, {
        userEmail: email,
        permissionGroupName: groupName,
      }),
  };
}
