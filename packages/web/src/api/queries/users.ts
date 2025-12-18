import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { useMutationWithFeedback } from '@/hooks/useMutationWithFeedback';
import i18n from '@/i18n/config';
import { hashPassword } from '@/utils/auth';
import type {
  CreatePermissionGroupParams,
  DeleteUserRequestParams,
  GetCompanyUsers_ResultSet1,
  UpdateUserAssignedPermissionsParams,
  UpdateUserEmailParams,
  UpdateUserLanguageParams,
  UpdateUserPasswordParams,
  UpdateUserToActivatedParams,
  UpdateUserToDeactivatedParams,
  UpdateUserVaultParams,
  UserRequest,
  UserVault,
} from '@rediacc/shared/types';
import type { PermissionGroupWithParsedPermissions } from '@rediacc/shared/api';

// Get all users
export const useUsers = () => {
  return useQuery<GetCompanyUsers_ResultSet1[]>({
    queryKey: ['users'],
    queryFn: () => api.users.list(),
  });
};

// Create user
export const useCreateUser = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, { email: string; password: string }>({
    mutationFn: async ({ email, password }) => {
      const passwordHash = await hashPassword(password);
      return api.users.create(email, passwordHash, { language: i18n.language || 'en' });
    },
    successMessage: (_, vars) =>
      i18n.t('organization:users.success.created', { email: vars.email }),
    errorMessage: i18n.t('organization:users.errors.createFailed'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      queryClient.invalidateQueries({ queryKey: ['dropdown-data'] });
    },
  });
};

// Activate user - special case using auth service
export const useActivateUser = () => {
  const queryClient = useQueryClient();

  return useMutationWithFeedback({
    mutationFn: async (data: {
      userEmail: string;
      activationCode: string;
      passwordHash: string;
    }) => {
      return api.auth.activateAccount(data.userEmail, data.activationCode, data.passwordHash);
    },
    successMessage: (_, variables) =>
      i18n.t('organization:users.success.activated', { email: variables.userEmail }),
    errorMessage: i18n.t('organization:users.errors.activateFailed'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
};

// Deactivate user
export const useDeactivateUser = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateUserToDeactivatedParams>({
    mutationFn: (params) => api.users.deactivate(params),
    successMessage: (_, params) =>
      i18n.t('organization:users.success.deactivated', { email: params.userEmail }),
    errorMessage: i18n.t('organization:users.errors.deactivateFailed'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
};

// Reactivate user
export const useReactivateUser = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateUserToActivatedParams>({
    mutationFn: (params) => api.users.activate(params),
    successMessage: (_, params) =>
      i18n.t('organization:users.success.activated', { email: params.userEmail }),
    errorMessage: i18n.t('organization:users.errors.activateFailed'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
};

// Update user email
export const useUpdateUserEmail = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateUserEmailParams>({
    mutationFn: (params) => api.users.updateEmail(params),
    successMessage: (_, vars) =>
      i18n.t('organization:users.success.emailUpdated', { email: vars.newUserEmail }),
    errorMessage: i18n.t('organization:users.errors.emailUpdateFailed'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
};

// Update user language preference
export const useUpdateUserLanguage = () => {
  return useMutationWithFeedback<unknown, Error, UpdateUserLanguageParams>({
    mutationFn: (params) => api.users.updateLanguage(params),
    successMessage: () => i18n.t('organization:users.success.languageSaved'),
    errorMessage: i18n.t('organization:users.errors.languageUpdateFailed'),
  });
};

// Get permission groups
export const usePermissionGroups = () => {
  return useQuery<PermissionGroupWithParsedPermissions[]>({
    queryKey: ['permission-groups'],
    queryFn: () => api.permissions.listGroups(),
  });
};

// Create permission group
export const useCreatePermissionGroup = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, CreatePermissionGroupParams>({
    mutationFn: (params) => api.permissions.createGroup(params),
    successMessage: (_, params) =>
      i18n.t('organization:users.success.permissionGroupCreated', {
        groupName: params.permissionGroupName,
      }),
    errorMessage: i18n.t('organization:users.errors.permissionGroupCreateFailed'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['permission-groups'] });
    },
  });
};

// Assign user to permission group
export const useAssignUserPermissions = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateUserAssignedPermissionsParams>({
    mutationFn: (params) => api.users.assignPermissions(params),
    successMessage: (_, vars) =>
      i18n.t('organization:users.success.permissionsAssigned', {
        email: vars.userEmail,
        group: vars.permissionGroupName,
      }),
    errorMessage: i18n.t('organization:users.errors.assignPermissionsFailed'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
};

// Update user password
export const useUpdateUserPassword = () => {
  return useMutationWithFeedback<unknown, Error, { userEmail: string; newPassword: string }>({
    mutationFn: async ({ newPassword }) => {
      const passwordHash = await hashPassword(newPassword);
      const params: UpdateUserPasswordParams = { userNewPass: passwordHash };
      return api.users.updatePassword(params);
    },
    successMessage: () => i18n.t('organization:users.success.passwordUpdated'),
    errorMessage: i18n.t('organization:users.errors.passwordUpdateFailed'),
  });
};

// Get active user requests/sessions
export const useUserRequests = () => {
  return useQuery<UserRequest[]>({
    queryKey: ['user-requests'],
    queryFn: () => api.auth.getSessions(),
    staleTime: 10 * 1000,
    refetchInterval: 30 * 1000,
  });
};

// Delete/terminate a user request/session
export const useDeleteUserRequest = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, DeleteUserRequestParams>({
    mutationFn: (params) => api.auth.terminateSession(params),
    successMessage: () => i18n.t('organization:users.success.sessionTerminated'),
    errorMessage: i18n.t('organization:users.errors.sessionTerminateFailed'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-requests'] });
    },
  });
};

// Get current user's vault data
export const useUserVault = () => {
  return useQuery<UserVault>({
    queryKey: ['user-vault'],
    queryFn: () => api.users.getVault(),
  });
};

// Update current user's vault
export const useUpdateUserVault = () => {
  const queryClient = useQueryClient();
  return useMutationWithFeedback<unknown, Error, UpdateUserVaultParams>({
    mutationFn: (params) => api.users.updateVault(params),
    successMessage: () => i18n.t('organization:users.success.userVaultUpdated'),
    errorMessage: i18n.t('organization:users.errors.userVaultUpdateFailed'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-vault'] });
    },
  });
};

export type {
  GetCompanyUsers_ResultSet1,
  GetCompanyUsers_ResultSet1 as User,
  UserRequest,
  UserVault,
} from '@rediacc/shared/types';
export type { PermissionGroupWithParsedPermissions } from '@rediacc/shared/api';
