import { useQuery, useQueryClient } from '@tanstack/react-query';
import { typedApi } from '@/api/client';
import { useMutationWithFeedback } from '@/hooks/useMutationWithFeedback';
import i18n from '@/i18n/config';
import { hashPassword } from '@/utils/auth';
import { parseGetCompanyUsers, parseGetUserRequests } from '@rediacc/shared/api';
import type {
  DeleteUserRequestParams,
  GetCompanyUsers_ResultSet1,
  UpdateUserAssignedPermissionsParams,
  UpdateUserLanguageParams,
  UpdateUserPasswordParams,
  UpdateUserToActivatedParams,
  UpdateUserToDeactivatedParams,
  UpdateUserVaultParams,
  UserRequest,
  UserVault,
} from '@rediacc/shared/types';

// Get all users
export const useUsers = () => {
  return useQuery<GetCompanyUsers_ResultSet1[]>({
    queryKey: ['users'],
    queryFn: async () => {
      const response = await typedApi.GetCompanyUsers({});
      return parseGetCompanyUsers(response as never);
    },
  });
};

// Create user
export const useCreateUser = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, { email: string; password: string }>({
    mutationFn: async ({ email, password }) => {
      const passwordHash = await hashPassword(password);
      return typedApi.CreateNewUser({
        newUserEmail: email,
        newUserHash: passwordHash,
        activationCode: '',
        languagePreference: i18n.language || 'en',
      });
    },
    successMessage: (_, vars) =>
      i18n.t('organization:users.success.created', { email: vars.email }),
    errorMessage: i18n.t('organization:users.errors.createFailed'),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['users'] });
      void queryClient.invalidateQueries({ queryKey: ['dropdown-data'] });
    },
  });
};

// Deactivate user
export const useDeactivateUser = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateUserToDeactivatedParams>({
    mutationFn: (params) => typedApi.UpdateUserToDeactivated(params),
    successMessage: (_, params) =>
      i18n.t('organization:users.success.deactivated', { email: params.userEmail }),
    errorMessage: i18n.t('organization:users.errors.deactivateFailed'),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
};

// Reactivate user
export const useReactivateUser = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateUserToActivatedParams>({
    mutationFn: (params) => typedApi.UpdateUserToActivated(params),
    successMessage: (_, params) =>
      i18n.t('organization:users.success.activated', { email: params.userEmail }),
    errorMessage: i18n.t('organization:users.errors.activateFailed'),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
};

// Update user language preference
export const useUpdateUserLanguage = () => {
  return useMutationWithFeedback<unknown, Error, UpdateUserLanguageParams>({
    mutationFn: (params) => typedApi.UpdateUserLanguage(params),
    successMessage: () => i18n.t('organization:users.success.languageSaved'),
    errorMessage: i18n.t('organization:users.errors.languageUpdateFailed'),
  });
};

// Assign user to permission group
export const useAssignUserPermissions = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateUserAssignedPermissionsParams>({
    mutationFn: (params) => typedApi.UpdateUserAssignedPermissions(params),
    successMessage: (_, vars) =>
      i18n.t('organization:users.success.permissionsAssigned', {
        email: vars.userEmail,
        group: vars.permissionGroupName,
      }),
    errorMessage: i18n.t('organization:users.errors.assignPermissionsFailed'),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
};

// Update user password
export const useUpdateUserPassword = () => {
  return useMutationWithFeedback<unknown, Error, { userEmail: string; newPassword: string }>({
    mutationFn: async ({ newPassword }) => {
      const passwordHash = await hashPassword(newPassword);
      const params: UpdateUserPasswordParams = { userNewPass: passwordHash };
      return typedApi.UpdateUserPassword(params);
    },
    successMessage: () => i18n.t('organization:users.success.passwordUpdated'),
    errorMessage: i18n.t('organization:users.errors.passwordUpdateFailed'),
  });
};

// Get active user requests/sessions
export const useUserRequests = () => {
  return useQuery<UserRequest[]>({
    queryKey: ['user-requests'],
    queryFn: async () => {
      const response = await typedApi.GetUserRequests({});
      return parseGetUserRequests(response as never);
    },
    staleTime: 10 * 1000,
    refetchInterval: 30 * 1000,
  });
};

// Delete/terminate a user request/session
export const useDeleteUserRequest = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, DeleteUserRequestParams>({
    mutationFn: (params) => typedApi.DeleteUserRequest(params),
    successMessage: () => i18n.t('organization:users.success.sessionTerminated'),
    errorMessage: i18n.t('organization:users.errors.sessionTerminateFailed'),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['user-requests'] });
    },
  });
};

// Get current user's vault data
export const useUserVault = () => {
  return useQuery<UserVault>({
    queryKey: ['user-vault'],
    queryFn: async () => {
      const response = await typedApi.GetUserVault({});
      // GetUserVault returns the vault data in resultSet[1]
      const resultSet = response.results[1];
      // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- results may be empty at runtime
      const vaultData = resultSet?.[0];
      // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- vaultData may be undefined at runtime
      if (!vaultData) {
        return { vault: '{}', vaultVersion: 0, userCredential: null };
      }
      return {
        vault: vaultData.vaultContent ?? '{}',
        // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- vaultVersion may be null at runtime
        vaultVersion: vaultData.vaultVersion ?? 0,
        userCredential: vaultData.userEmail ?? null,
      };
    },
  });
};

// Update current user's vault
export const useUpdateUserVault = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateUserVaultParams>({
    mutationFn: (params) => typedApi.UpdateUserVault(params),
    successMessage: () => i18n.t('organization:users.success.userVaultUpdated'),
    errorMessage: i18n.t('organization:users.errors.userVaultUpdateFailed'),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['user-vault'] });
    },
  });
};

export type {
  GetCompanyUsers_ResultSet1,
  GetCompanyUsers_ResultSet1 as User,
  UserRequest,
  UserVault,
} from '@rediacc/shared/types';
