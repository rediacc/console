import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { createMutation } from '@/hooks/api/mutationFactory';
import i18n from '@/i18n/config';
import { hashPassword } from '@/utils/auth';
import { showMessage } from '@/utils/messages';
import { createErrorHandler } from '@/utils/mutationUtils';
import type { PermissionGroupWithParsedPermissions } from '@rediacc/shared/api';
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

// Get all users
export const useUsers = () => {
  return useQuery<GetCompanyUsers_ResultSet1[]>({
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
export const useDeactivateUser = createMutation<UpdateUserToDeactivatedParams>({
  request: (params) => api.users.deactivate(params),
  invalidateKeys: ['users'],
  successMessage: (params) =>
    i18n.t('organization:users.success.deactivated', { email: params.userEmail }),
  errorMessage: i18n.t('organization:users.errors.deactivateFailed'),
  operationName: 'users.deactivate',
});

// Reactivate user
export const useReactivateUser = createMutation<UpdateUserToActivatedParams>({
  request: (params) => api.users.activate(params),
  invalidateKeys: ['users'],
  successMessage: (params) =>
    i18n.t('organization:users.success.activated', { email: params.userEmail }),
  errorMessage: i18n.t('organization:users.errors.activateFailed'),
  operationName: 'users.activate',
});

// Update user email
export const useUpdateUserEmail = createMutation<UpdateUserEmailParams>({
  request: (params) => api.users.updateEmail(params),
  invalidateKeys: ['users'],
  successMessage: (vars) =>
    i18n.t('organization:users.success.emailUpdated', { email: vars.newUserEmail }),
  errorMessage: i18n.t('organization:users.errors.emailUpdateFailed'),
  operationName: 'users.updateEmail',
});

// Update user language preference
export const useUpdateUserLanguage = createMutation<UpdateUserLanguageParams>({
  request: (params) => api.users.updateLanguage(params),
  invalidateKeys: [],
  successMessage: () => i18n.t('organization:users.success.languageSaved'),
  errorMessage: i18n.t('organization:users.errors.languageUpdateFailed'),
  operationName: 'users.updateLanguage',
});

// Get permission groups
export const usePermissionGroups = () => {
  return useQuery<PermissionGroupWithParsedPermissions[]>({
    queryKey: ['permission-groups'],
    queryFn: () => api.permissions.listGroups(),
  });
};

// Create permission group
export const useCreatePermissionGroup = createMutation<CreatePermissionGroupParams>({
  request: (params) => api.permissions.createGroup(params),
  invalidateKeys: ['permission-groups'],
  successMessage: (params) =>
    i18n.t('organization:users.success.permissionGroupCreated', {
      groupName: params.permissionGroupName,
    }),
  errorMessage: i18n.t('organization:users.errors.permissionGroupCreateFailed'),
  operationName: 'permissions.createGroup',
});

// Assign user to permission group
export const useAssignUserPermissions = createMutation<UpdateUserAssignedPermissionsParams>({
  request: (params) => api.users.assignPermissions(params),
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
  UpdateUserPasswordParams
>({
  request: (params) => api.users.updatePassword(params),
  invalidateKeys: [],
  successMessage: () => i18n.t('organization:users.success.passwordUpdated'),
  errorMessage: i18n.t('organization:users.errors.passwordUpdateFailed'),
  transformData: async (data) => {
    const passwordHash = await hashPassword(data.newPassword);
    return {
      userNewPass: passwordHash,
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
export const useDeleteUserRequest = createMutation<DeleteUserRequestParams>({
  request: (params) => api.auth.terminateSession(params),
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
export const useUpdateUserVault = createMutation<UpdateUserVaultParams>({
  request: (params) => api.users.updateVault(params),
  invalidateKeys: ['user-vault'],
  successMessage: () => i18n.t('organization:users.success.userVaultUpdated'),
  errorMessage: i18n.t('organization:users.errors.userVaultUpdateFailed'),
  operationName: 'users.updateVault',
});

export type {
  GetCompanyUsers_ResultSet1,
  GetCompanyUsers_ResultSet1 as User,
  PermissionGroupWithParsedPermissions,
  UserRequest,
  UserVault,
};
