export const TeamPageIDS = {
    // Navigation
    mainNavOrganization: 'main-nav-organization',
    mainNavOrganizationUsers: 'main-nav-organization-users',
    mainNavOrganizationTeams: 'main-nav-organization-teams',
    mainNavOrganizationAccess: 'main-nav-organization-access',
    mainNavMachines: 'main-nav-machines',
    mainNavSettings: 'main-nav-settings',
    notificationBell: 'notification-bell',
    userMenuButton: 'user-menu-button',

    // Main Content
    mainContent: 'main-content',
    resourceListContainer: 'resource-list-container',
    resourceListFilters: 'resource-list-filters',
    resourceListActions: 'resource-list-actions',

    // Team Actions
    systemCreateTeamButton: 'system-create-team-button',
    systemTeamTable: 'system-team-table',
    resourceListItemPrivateTeam: 'resource-list-item-Private Team',
    systemTeamEditButton: (teamName: string) => `system-team-edit-button-${teamName}`,
    systemTeamMembersButton: (teamName: string) => `system-team-members-button-${teamName}`,
    systemTeamTraceButton: (teamName: string) => `system-team-trace-button-${teamName}`,
    systemTeamDeleteButton: (teamName: string) => `system-team-delete-button-${teamName}`,

    // Toaster
    themedToasterContainer: 'themed-toaster-container',

    // Resource Modal
    resourceModal: 'resource-modal',
    resourceModalForm: 'resource-modal-form',
    resourceModalFieldTeamName: 'resource-modal-field-teamName',
    resourceModalFieldTeamNameInput: 'resource-modal-field-teamName-input',
    resourceModalVaultEditorSection: 'resource-modal-vault-editor-section',
    resourceModalCancelButton: 'resource-modal-cancel-button',
    resourceModalOkButton: 'resource-modal-ok-button',

    // Vault Editor
    vaultEditorForm: 'vault-editor-form',
    vaultEditorCards: 'vault-editor-cards',
    vaultEditorFieldSshPrivateKey: 'vault-editor-field-SSH_PRIVATE_KEY',
    vaultEditorGenerateSshPrivateKey: 'vault-editor-generate-SSH_PRIVATE_KEY',
    vaultEditorFieldSshPublicKey: 'vault-editor-field-SSH_PUBLIC_KEY',
    vaultEditorGenerateSshPublicKey: 'vault-editor-generate-SSH_PUBLIC_KEY',
    vaultEditorFieldSshKnownHosts: 'vault-editor-field-SSH_KNOWN_HOSTS',
    vaultEditorFieldSshPassword: 'vault-editor-field-SSH_PASSWORD',
    vaultEditorCopySshPrivateKey: 'vault-editor-copy-ssh_private_key',
    vaultEditorCopySshPublicKey: 'vault-editor-copy-ssh_public_key',
    vaultEditorGenerateCancel: 'vault-editor-generate-cancel',
    vaultEditorRegenerateButton: 'vault-editor-regenerate-button',
    vaultEditorApplyGenerated: 'vault-editor-apply-generated',
    vaultEditorGenerateButton: 'vault-editor-generate-button',

    // Audit
    auditTraceTotalRecords: 'audit-trace-total-records',
} as const;
