// User page test IDs
export const UserPageIDs = {
  // Navigation
  mainNavOrganization: 'main-nav-organization',
  mainNavOrganizationUsers: 'main-nav-organization-users',
  mainNavOrganizationTeams: 'main-nav-organization-teams',
  
  // User List & Table
  resourceListContainer: 'resource-list-container',
  resourceListFilters: 'resource-list-filters',
  resourceListActions: 'resource-list-actions',
  systemUserTable: 'system-user-table',
  resourceListItem: (identifier: string) => `resource-list-item-${identifier}`,
  
  // User Actions
  systemCreateUserButton: 'system-create-user-button',
  systemUserActivateButton: (email: string) => `system-user-activate-button-${email}`,
  systemUserDeactivateButton: (email: string) => `system-user-deactivate-button-${email}`,
  systemUserTraceButton: (email: string) => `system-user-trace-button-${email}`,
  systemUserPermissionsButton: (email: string) => `system-user-permissions-button-${email}`,
  
  // User Form
  resourceForm: 'resource-form',
  resourceFormFieldEmail: 'resource-form-field-email',
  resourceFormFieldPassword: 'resource-form-field-password',
  resourceFormCancelButton: 'resource-form-cancel-button',
  resourceFormSubmitButton: 'resource-form-submit-button',
  
  // Team Actions
  systemTeamMembersButton: (teamName: string) => `system-team-members-button-${teamName}`,
  
  // Audit & Trace
  auditTraceVisibleRecords: 'audit-trace-visible-records',
  
  // Modals
  modalAssignPermissionsOk: 'modal-assign-permissions-ok',
} as const;
