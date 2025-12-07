import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { createMutation } from '@/hooks/api/mutationFactory';
import i18n from '@/i18n/config';
import { hashPassword } from '@/utils/auth';
import { showMessage } from '@/utils/messages';
import { createErrorHandler } from '@/utils/mutationUtils';
import type { PermissionGroup, User, UserRequest, UserVault } from '@rediacc/shared/types';

// Get all users
export const useUsers = () => {
  return useQuery<User[]>({
    queryKey: ['users'],
    queryFn: () => api.users.list(),
  });
};

// Create user
export const useCreateUser = createMutation<
  { email: string; password: string },
  unknown,
  { email: string; passwordHash: string }
>({
  request: ({ email, passwordHash }) =>
    api.users.create(email, passwordHash, { language: i18n.language || 'en' }),
  invalidateKeys: ['users', 'dropdown-data'],
  successMessage: (vars) => i18n.t('organization:users.success.created', { email: vars.email }),
  errorMessage: i18n.t('organization:users.errors.createFailed'),
  transformData: async (data) => {
    const passwordHash = await hashPassword(data.password);
    return {
      email: data.email,
      passwordHash,
    };
  },
  operationName: 'users.create',
});

// Activate user - special case using auth service
export const useActivateUser = () => {
  const queryClient = useQueryClient();
  const activationErrorHandler = createErrorHandler(
    i18n.t('organization:users.errors.activateFailed')
  );

  return useMutation({
    mutationFn: async (data: {
      userEmail: string;
      activationCode: string;
      passwordHash: string;
    }) => {
      return api.auth.activateAccount(data.userEmail, data.activationCode, data.passwordHash);
    },
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      showMessage(
        'success',
        i18n.t('organization:users.success.activated', { email: variables.userEmail })
      );
    },
    onError: activationErrorHandler,
  });
};

// Deactivate user
export const useDeactivateUser = createMutation<string>({
  request: (userEmail) => api.users.deactivate(userEmail),
  invalidateKeys: ['users'],
  successMessage: (userEmail) =>
    i18n.t('organization:users.success.deactivated', { email: userEmail }),
  errorMessage: i18n.t('organization:users.errors.deactivateFailed'),
  operationName: 'users.deactivate',
});

// Reactivate user
export const useReactivateUser = createMutation<string>({
  request: (userEmail) => api.users.activate(userEmail),
  invalidateKeys: ['users'],
  successMessage: (userEmail) =>
    i18n.t('organization:users.success.activated', { email: userEmail }),
  errorMessage: i18n.t('organization:users.errors.activateFailed'),
  operationName: 'users.activate',
});

// Update user email
export const useUpdateUserEmail = createMutation<{
  currentUserEmail: string;
  newUserEmail: string;
}>({
  request: ({ currentUserEmail, newUserEmail }) =>
    api.users.updateEmail(currentUserEmail, newUserEmail),
  invalidateKeys: ['users'],
  successMessage: (vars) =>
    i18n.t('organization:users.success.emailUpdated', { email: vars.newUserEmail }),
  errorMessage: i18n.t('organization:users.errors.emailUpdateFailed'),
  operationName: 'users.updateEmail',
});

// Update user language preference
export const useUpdateUserLanguage = createMutation<string>({
  request: (preferredLanguage) => api.users.updateLanguage(preferredLanguage),
  invalidateKeys: [],
  successMessage: () => i18n.t('organization:users.success.languageSaved'),
  errorMessage: i18n.t('organization:users.errors.languageUpdateFailed'),
  operationName: 'users.updateLanguage',
});

// Get permission groups
export const usePermissionGroups = () => {
  return useQuery<PermissionGroup[]>({
    queryKey: ['permission-groups'],
    queryFn: () => api.permissions.listGroups(),
  });
};

// Create permission group
export const useCreatePermissionGroup = createMutation<string>({
  request: (permissionGroupName) => api.permissions.createGroup(permissionGroupName),
  invalidateKeys: ['permission-groups'],
  successMessage: (groupName) =>
    i18n.t('organization:users.success.permissionGroupCreated', { groupName }),
  errorMessage: i18n.t('organization:users.errors.permissionGroupCreateFailed'),
  operationName: 'permissions.createGroup',
});

// Assign user to permission group
export const useAssignUserPermissions = createMutation<{
  userEmail: string;
  permissionGroupName: string;
}>({
  request: ({ userEmail, permissionGroupName }) =>
    api.users.assignPermissions(userEmail, permissionGroupName),
  invalidateKeys: ['users'],
  successMessage: (vars) =>
    i18n.t('organization:users.success.permissionsAssigned', {
      email: vars.userEmail,
      group: vars.permissionGroupName,
    }),
  errorMessage: i18n.t('organization:users.errors.assignPermissionsFailed'),
  operationName: 'users.assignPermissions',
});

// Update user password
export const useUpdateUserPassword = createMutation<
  { userEmail: string; newPassword: string },
  unknown,
  { passwordHash: string }
>({
  request: ({ passwordHash }) => api.users.updatePassword(passwordHash),
  invalidateKeys: [],
  successMessage: () => i18n.t('organization:users.success.passwordUpdated'),
  errorMessage: i18n.t('organization:users.errors.passwordUpdateFailed'),
  transformData: async (data) => {
    const passwordHash = await hashPassword(data.newPassword);
    return {
      passwordHash,
    };
  },
  operationName: 'users.updatePassword',
});

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
export const useDeleteUserRequest = createMutation<{ requestId: number }>({
  request: ({ requestId }) => api.auth.terminateSession(requestId),
  invalidateKeys: ['user-requests'],
  successMessage: () => i18n.t('organization:users.success.sessionTerminated'),
  errorMessage: i18n.t('organization:users.errors.sessionTerminateFailed'),
  operationName: 'auth.terminateSession',
});

// Get current user's vault data
export const useUserVault = () => {
  return useQuery<UserVault>({
    queryKey: ['user-vault'],
    queryFn: () => api.users.getVault(),
  });
};

// Update current user's vault
export const useUpdateUserVault = createMutation<{ vaultContent: string; vaultVersion: number }>({
  request: ({ vaultContent, vaultVersion }) => api.users.updateVault(vaultContent, vaultVersion),
  invalidateKeys: ['user-vault'],
  successMessage: () => i18n.t('organization:users.success.userVaultUpdated'),
  errorMessage: i18n.t('organization:users.errors.userVaultUpdateFailed'),
  operationName: 'users.updateVault',
});

export type { User, PermissionGroup, UserRequest, UserVault };
