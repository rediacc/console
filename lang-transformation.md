# Language Transformation Plan for Console Components

## Overview

This document outlines the transformation plan to add `data-testid` attributes to all interactive components in the Rediacc Console application. This will ensure that Playwright tests work consistently across all language settings.

## Why This Transformation is Needed

- **Current Issue**: Playwright's inspector writer generates text-based selectors that break when the UI language changes
- **Solution**: Add stable `data-testid` attributes that remain constant regardless of language
- **Benefit**: Tests will be maintainable and language-agnostic

## Naming Convention

All data-testid attributes should follow this pattern:
- `{page/section}-{component}-{action/type}`
- Use kebab-case
- Be descriptive but concise

Examples:
- `login-email-input`
- `dashboard-refresh-button`
- `machine-table-row`

## Complete Component Inventory

Based on a comprehensive search of the codebase, we have identified **64 files with interactive elements** that need data-testid attributes. Currently, only 2 files have been completed (LoginPage.tsx and LanguageSelector.tsx).

## Components to Transform

### 1. Authentication Components ✅ (Partially Completed)

#### LoginPage.tsx ✅
- [x] `data-testid="login-email-input"`
- [x] `data-testid="login-password-input"`
- [x] `data-testid="login-master-password-input"`
- [x] `data-testid="login-submit-button"`
- [x] `data-testid="login-register-link"`
- [x] `data-testid="tfa-code-input"`
- [x] `data-testid="tfa-verify-button"`

#### RegistrationModal.tsx
- [ ] `data-testid="registration-company-input"`
- [ ] `data-testid="registration-email-input"`
- [ ] `data-testid="registration-password-input"`
- [ ] `data-testid="registration-confirm-password-input"`
- [ ] `data-testid="registration-submit-button"`
- [ ] `data-testid="registration-cancel-button"`
- [ ] `data-testid="activation-code-input"`
- [ ] `data-testid="activation-verify-button"`

### 2. Common Components

#### LanguageSelector.tsx ✅
- [x] `data-testid="language-selector"`

#### ThemeToggle.tsx
- [ ] `data-testid="theme-toggle-button"`

#### TeamSelector.tsx
- [ ] `data-testid="team-selector"`
- [ ] `data-testid="team-option-{teamName}"` (dynamic)

#### NotificationBell.tsx
- [ ] `data-testid="notification-bell"`
- [ ] `data-testid="notification-item-{index}"` (dynamic)
- [ ] `data-testid="notification-clear-all"`

#### VaultEditor.tsx
- [ ] `data-testid="vault-editor-field-{fieldName}"` (dynamic)
- [ ] `data-testid="vault-editor-save"`
- [ ] `data-testid="vault-editor-cancel"`

#### ResourceListView.tsx
- [ ] `data-testid="resource-list-item-{id}"` (dynamic)
- [ ] `data-testid="resource-list-create"`
- [ ] `data-testid="resource-list-search"`
- [ ] `data-testid="resource-list-filter"`

### 3. Layout Components

#### MainLayout.tsx
- [ ] `data-testid="main-nav-{item}"` (dynamic for each nav item)
- [ ] `data-testid="main-sidebar-toggle"`
- [ ] `data-testid="main-user-menu"`
- [ ] `data-testid="main-logout-button"`

### 4. Dashboard Components

#### DashboardPage.tsx
- [ ] `data-testid="dashboard-stat-{statName}"` (dynamic)
- [ ] `data-testid="dashboard-refresh-button"`
- [ ] `data-testid="dashboard-date-filter"`

#### DistributedStorageDashboardWidget.tsx
- [ ] `data-testid="ds-widget-expand"`
- [ ] `data-testid="ds-widget-stat-{type}"` (dynamic)

### 5. Resource Management Components

#### MachineTable.tsx
- [ ] `data-testid="machine-table"`
- [ ] `data-testid="machine-row-{machineId}"` (dynamic)
- [ ] `data-testid="machine-select-{machineId}"` (dynamic)
- [ ] `data-testid="machine-actions-{machineId}"` (dynamic)

#### RepositoryDetailPanel.tsx
- [ ] `data-testid="repo-detail-name"`
- [ ] `data-testid="repo-detail-edit"`
- [ ] `data-testid="repo-detail-delete"`
- [ ] `data-testid="repo-detail-tab-{tabName}"` (dynamic)

#### LocalActionsMenu.tsx
- [ ] `data-testid="local-actions-menu"`
- [ ] `data-testid="local-action-{actionName}"` (dynamic)

### 6. Distributed Storage Components

#### ClusterTable.tsx
- [ ] `data-testid="cluster-table"`
- [ ] `data-testid="cluster-row-{clusterId}"` (dynamic)
- [ ] `data-testid="cluster-create-button"`
- [ ] `data-testid="cluster-actions-{clusterId}"` (dynamic)

#### PoolTable.tsx
- [ ] `data-testid="pool-table"`
- [ ] `data-testid="pool-row-{poolId}"` (dynamic)
- [ ] `data-testid="pool-create-button"`

#### RbdImageList.tsx
- [ ] `data-testid="rbd-image-list"`
- [ ] `data-testid="rbd-image-{imageId}"` (dynamic)
- [ ] `data-testid="rbd-image-create"`

### 7. Queue Management

#### QueuePage.tsx
- [ ] `data-testid="queue-filter-status"`
- [ ] `data-testid="queue-filter-team"`
- [ ] `data-testid="queue-filter-date"`
- [ ] `data-testid="queue-item-{itemId}"` (dynamic)
- [ ] `data-testid="queue-item-retry-{itemId}"` (dynamic)
- [ ] `data-testid="queue-item-cancel-{itemId}"` (dynamic)

### 8. System Management

#### SystemPage.tsx
- [ ] `data-testid="system-tab-{tabName}"` (dynamic)
- [ ] `data-testid="system-settings-save"`
- [ ] `data-testid="system-settings-reset"`

#### UserSessionsTab.tsx
- [ ] `data-testid="session-table"`
- [ ] `data-testid="session-row-{sessionId}"` (dynamic)
- [ ] `data-testid="session-terminate-{sessionId}"` (dynamic)

### 9. Settings Components

#### TwoFactorSettings.tsx
- [ ] `data-testid="tfa-enable-button"`
- [ ] `data-testid="tfa-disable-button"`
- [ ] `data-testid="tfa-qr-code"`
- [ ] `data-testid="tfa-backup-codes"`

### 10. Form Components

#### ResourceForm.tsx
- [ ] `data-testid="resource-form-field-{fieldName}"` (dynamic)
- [ ] `data-testid="resource-form-submit"`
- [ ] `data-testid="resource-form-cancel"`
- [ ] `data-testid="resource-form-reset"`

#### FieldGenerator.tsx
- [ ] `data-testid="field-{fieldName}"` (dynamic based on field type)
- [ ] `data-testid="field-{fieldName}-add"` (for array fields)
- [ ] `data-testid="field-{fieldName}-remove-{index}"` (for array items)

### 11. Modal Components

#### UnifiedResourceModal.tsx
- [ ] `data-testid="resource-modal-title"`
- [ ] `data-testid="resource-modal-confirm"`
- [ ] `data-testid="resource-modal-cancel"`
- [ ] `data-testid="resource-modal-form-{fieldName}"` (dynamic)

#### VaultEditorModal.tsx
- [ ] `data-testid="vault-modal-editor"`
- [ ] `data-testid="vault-modal-save"`
- [ ] `data-testid="vault-modal-cancel"`
- [ ] `data-testid="vault-modal-import"`
- [ ] `data-testid="vault-modal-export"`

#### ConnectivityTestModal.tsx
- [ ] `data-testid="connectivity-test-start"`
- [ ] `data-testid="connectivity-test-stop"`
- [ ] `data-testid="connectivity-test-result"`
- [ ] `data-testid="connectivity-test-table"`

#### FunctionSelectionModal.tsx
- [ ] `data-testid="function-search-input"`
- [ ] `data-testid="function-item-{functionName}"` (dynamic)
- [ ] `data-testid="function-machine-select"`
- [ ] `data-testid="function-repo-select"`
- [ ] `data-testid="function-storage-select"`
- [ ] `data-testid="function-submit-button"`
- [ ] `data-testid="function-cancel-button"`

#### QueueItemTraceModal.tsx
- [ ] `data-testid="trace-modal-close"`
- [ ] `data-testid="trace-modal-table"`
- [ ] `data-testid="trace-modal-refresh"`

#### AuditTraceModal.tsx
- [ ] `data-testid="audit-modal-close"`
- [ ] `data-testid="audit-modal-table"`

#### TemplateDetailsModal.tsx
- [ ] `data-testid="template-modal-close"`
- [ ] `data-testid="template-modal-select"`

### 12. Virtual/Performance Components

#### VirtualMachineTable.tsx
- [ ] `data-testid="virtual-machine-checkbox-{machineId}"` (dynamic)
- [ ] `data-testid="virtual-machine-row-{machineId}"` (dynamic)
- [ ] `data-testid="virtual-machine-list"`

#### VirtualFilterableMachineTable.tsx
- [ ] `data-testid="machine-search-input"`
- [ ] `data-testid="machine-assignment-filter"`
- [ ] `data-testid="machine-pagesize-select"`
- [ ] `data-testid="machine-refresh-button"`

### 13. Architecture & Audit Pages

#### ArchitecturePage.tsx
- [ ] `data-testid="architecture-tab-{tabName}"` (dynamic)
- [ ] `data-testid="architecture-refresh-button"`
- [ ] `data-testid="architecture-export-button"`

#### AuditPage.tsx
- [ ] `data-testid="audit-filter-date"`
- [ ] `data-testid="audit-filter-user"`
- [ ] `data-testid="audit-filter-action"`
- [ ] `data-testid="audit-table"`
- [ ] `data-testid="audit-export-button"`

### 14. Additional Resource Modals

#### AssignMachinesToCloneModal.tsx
- [ ] `data-testid="assign-machines-select"`
- [ ] `data-testid="assign-machines-submit"`
- [ ] `data-testid="assign-machines-cancel"`

#### RemoveFromClusterModal.tsx
- [ ] `data-testid="remove-cluster-confirm"`
- [ ] `data-testid="remove-cluster-cancel"`

#### ImageMachineReassignmentModal.tsx
- [ ] `data-testid="reassign-machine-select"`
- [ ] `data-testid="reassign-submit-button"`
- [ ] `data-testid="reassign-cancel-button"`

#### PipInstallationModal.tsx
- [ ] `data-testid="pip-command-input"`
- [ ] `data-testid="pip-install-button"`
- [ ] `data-testid="pip-close-button"`

#### RemoteFileBrowserModal.tsx
- [ ] `data-testid="file-browser-table"`
- [ ] `data-testid="file-browser-navigate-{path}"` (dynamic)
- [ ] `data-testid="file-browser-download-{file}"` (dynamic)
- [ ] `data-testid="file-browser-close"`

#### ViewAssignmentStatusModal.tsx
- [ ] `data-testid="assignment-status-table"`
- [ ] `data-testid="assignment-status-close"`

### 15. Marketplace Components

#### MarketplaceCard.tsx
- [ ] `data-testid="marketplace-card-{itemId}"` (dynamic)
- [ ] `data-testid="marketplace-preview-{itemId}"` (dynamic)
- [ ] `data-testid="marketplace-deploy-{itemId}"` (dynamic)

#### MarketplaceFilters.tsx
- [ ] `data-testid="marketplace-category-filter"`
- [ ] `data-testid="marketplace-difficulty-filter"`
- [ ] `data-testid="marketplace-tags-filter"`
- [ ] `data-testid="marketplace-clear-filters"`
- [ ] `data-testid="marketplace-popular-tag-{tag}"` (dynamic)

#### MarketplacePreview.tsx
- [ ] `data-testid="marketplace-preview-close"`
- [ ] `data-testid="marketplace-preview-deploy"`

### 16. Additional Common Components

#### SimpleJsonEditor.tsx
- [ ] `data-testid="json-editor-textarea"`
- [ ] `data-testid="json-editor-format"`
- [ ] `data-testid="json-editor-validate"`

#### NestedObjectEditor.tsx
- [ ] `data-testid="nested-editor-field-{path}"` (dynamic)
- [ ] `data-testid="nested-editor-add-{path}"` (dynamic)
- [ ] `data-testid="nested-editor-remove-{path}"` (dynamic)

#### RcloneImportWizard.tsx
- [ ] `data-testid="rclone-upload-dragger"`
- [ ] `data-testid="rclone-select-all"`
- [ ] `data-testid="rclone-select-{configName}"` (dynamic)
- [ ] `data-testid="rclone-import-button"`
- [ ] `data-testid="rclone-cancel-button"`
- [ ] `data-testid="rclone-back-button"`

### 17. Additional Dashboard Components

#### DistributedStorageDashboardWidget.tsx (Extended)
- [ ] `data-testid="ds-widget-card-{type}"` (dynamic)
- [ ] `data-testid="ds-widget-progress-{type}"` (dynamic)
- [ ] `data-testid="ds-widget-view-details"`

### 18. Additional Table Components

#### MachineAssignmentStatusCell.tsx
- [ ] `data-testid="assignment-status-badge-{status}"` (dynamic)
- [ ] `data-testid="assignment-status-popover"`

#### MachineAssignmentStatusBadge.tsx
- [ ] `data-testid="assignment-badge-{type}"` (dynamic)

#### ContainerDetailPanel.tsx
- [ ] `data-testid="container-action-{action}"` (dynamic)
- [ ] `data-testid="container-status-{status}"` (dynamic)

#### MachineVaultStatusPanel.tsx
- [ ] `data-testid="vault-status-badge"`
- [ ] `data-testid="vault-status-details"`

## Updated Statistics

- **Total files identified**: 64 files with interactive elements
- **Completed**: 2 files (3.1%)
- **Remaining**: 62 files (96.9%)
- **Total estimated data-testid attributes needed**: ~500-600 (based on component complexity)

## Implementation Strategy

### Phase 1: Critical User Paths (Week 1) - High Priority
1. **Authentication Flow** (Partially Complete ✅)
   - LoginPage.tsx ✅
   - RegistrationModal.tsx
   - TwoFactorSettings.tsx
   
2. **Main Layout & Navigation**
   - MainLayout.tsx
   - AuthLayout.tsx
   - TeamSelector.tsx
   - ThemeToggle.tsx
   - NotificationBell.tsx
   
3. **Dashboard Components**
   - DashboardPage.tsx
   - DistributedStorageDashboardWidget.tsx

### Phase 2: Core Resource Management (Week 2) - High Priority
1. **Resource Pages**
   - ResourcesPage.tsx
   - MachineTable.tsx
   - RepositoryDetailPanel.tsx
   - LocalActionsMenu.tsx
   
2. **Resource Modals**
   - UnifiedResourceModal.tsx
   - ResourceForm.tsx
   - ResourceFormWithVault.tsx
   - VaultEditor.tsx
   - VaultEditorModal.tsx
   
3. **Queue Management**
   - QueuePage.tsx
   - QueueItemTraceModal.tsx

### Phase 3: Distributed Storage & Advanced Features (Week 3) - Medium Priority
1. **Distributed Storage Components**
   - DistributedStoragePage.tsx
   - ClusterTable.tsx
   - PoolTable.tsx
   - RbdImageList.tsx
   - ManageClusterMachinesModal.tsx
   - VirtualMachineTable.tsx
   - VirtualFilterableMachineTable.tsx
   
2. **System & Settings**
   - SystemPage.tsx
   - UserSessionsTab.tsx
   - AuditPage.tsx
   - ArchitecturePage.tsx

### Phase 4: Marketplace & Supporting Components (Week 4) - Low Priority
1. **Marketplace**
   - MarketplacePage.tsx
   - MarketplaceCard.tsx
   - MarketplaceFilters.tsx
   - MarketplacePreview.tsx
   
2. **Supporting Components**
   - All remaining modal components
   - Helper components (badges, cells, panels)
   - Specialized editors and selectors

### Phase 5: Testing & Validation (Week 5)
1. Update all existing Playwright tests to use data-testid
2. Create test coverage for new components
3. Validate all tests pass in all 9 supported languages:
   - English (en)
   - Spanish (es)
   - French (fr)
   - German (de)
   - Chinese (zh)
   - Japanese (ja)
   - Arabic (ar)
   - Turkish (tr)
   - Russian (ru)
4. Add automated checks to ensure new components include data-testid

## Testing Guidelines

### For Developers
1. Always add `data-testid` when creating new interactive elements
2. Use the naming convention consistently
3. Don't use data-testid for styling or JavaScript logic

### For QA/Test Engineers
1. Prefer `data-testid` selectors over text, class, or id selectors
2. Use Playwright's built-in selector engine: `page.locator('[data-testid="..."]')`
3. For dynamic IDs, use template literals: `` `[data-testid="machine-row-${machineId}"]` ``

## Playwright Configuration

Add to `playwright.config.js`:

```javascript
use: {
  // ... existing config
  // This will make Playwright prefer data-testid attributes
  testIdAttribute: 'data-testid'
}
```

## Example Test Pattern

```javascript
// Bad - Language dependent
await page.locator('button:has-text("Sign In")').click();

// Good - Language agnostic
await page.locator('[data-testid="login-submit-button"]').click();
```

## Validation Checklist

- [ ] All buttons have data-testid
- [ ] All form inputs have data-testid
- [ ] All links have data-testid
- [ ] All selectable items in lists/tables have data-testid
- [ ] All modal actions have data-testid
- [ ] No data-testid values contain translatable text
- [ ] Tests pass in all supported languages

## Progress Tracking

### Component Completion Status
| Category | Total Files | Completed | Remaining | Progress |
|----------|------------|-----------|-----------|----------|
| Authentication | 3 | 3 | 0 | 100% ✅ |
| Common Components | 19 | 8 | 11 | 42% |
| Layout | 2 | 1 | 1 | 50% |
| Dashboard | 2 | 1 | 1 | 50% |
| Resources | 21 | 3 | 18 | 14% |
| Distributed Storage | 12 | 2 | 10 | 17% |
| Queue | 2 | 1 | 1 | 50% |
| System/Audit | 4 | 3 | 1 | 75% |
| Marketplace | 4 | 1 | 3 | 25% |
| Forms | 3 | 0 | 3 | 0% |
| **Total** | **64** | **23** | **41** | **35.9%** |

### Completed Components (23 files)
✅ LoginPage.tsx
✅ RegistrationModal.tsx  
✅ TwoFactorSettings.tsx
✅ MainLayout.tsx
✅ TeamSelector.tsx
✅ ThemeToggle.tsx
✅ NotificationBell.tsx
✅ LanguageSelector.tsx
✅ VaultEditor.tsx
✅ VaultEditorModal.tsx
✅ ConnectivityTestModal.tsx
✅ DashboardPage.tsx
✅ ResourcesPage.tsx
✅ MachineTable.tsx
✅ UnifiedResourceModal.tsx
✅ QueuePage.tsx
✅ SystemPage.tsx
✅ UserSessionsTab.tsx
✅ AuditPage.tsx
✅ DistributedStoragePage.tsx
✅ ClusterTable.tsx
✅ MarketplacePage.tsx
✅ MarketplaceCard.tsx

## Notes

- This transformation should not affect the visual appearance or functionality
- data-testid attributes are for testing only and should not be used for styling
- Consider adding a linting rule to enforce data-testid on interactive elements
- Document this convention in the project's contributing guidelines
- Priority should be given to components used in critical user flows (login, resource creation, etc.)
- Dynamic testids should use template literals for consistency

## Automated Validation Script

Create a script to validate data-testid coverage:

```javascript
// scripts/validate-testids.js
const glob = require('glob');
const fs = require('fs');

const interactiveElements = [
  'Button', 'Input', 'Select', 'Checkbox', 'Radio', 'Switch',
  'Table', 'Modal', 'Form', 'DatePicker', 'Upload', 'Dropdown'
];

const validateFile = (filePath) => {
  const content = fs.readFileSync(filePath, 'utf8');
  const missing = [];
  
  interactiveElements.forEach(element => {
    const regex = new RegExp(`<${element}[^>]*>`, 'g');
    const matches = content.match(regex) || [];
    
    matches.forEach(match => {
      if (!match.includes('data-testid')) {
        missing.push({ element, line: match });
      }
    });
  });
  
  return missing;
};

// Run validation on all component files
const files = glob.sync('src/**/*.tsx');
const report = files.map(file => ({
  file,
  missing: validateFile(file)
})).filter(r => r.missing.length > 0);

console.log('Components missing data-testid:', report);
```