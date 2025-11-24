# Component Consolidation Refactoring Plan

## Executive Summary

**Current State**: 89 components in `src/components/` with significant misplacement
**Issue**: ~44% of components are single-use but placed in shared locations
**Goal**: Co-locate single-use components with their consumers, establish proper feature boundaries

### Quick Stats

| Category | Count | Percentage |
|----------|-------|------------|
| Truly Shared (3+ consumers) | 26 | 29.2% |
| Dual-Use (2 consumers) | 12 | 13.5% |
| Single-Use (1 consumer) | 36 | 40.4% |
| Unused (0 consumers) | 15 | 16.9% |
| **Total** | **89** | |

---

## Complete Component Inventory

### src/components/auth/ (2 components)

| Component | Consumers | Consumer Paths |
|-----------|-----------|----------------|
| **RegistrationModal** | 1 | `pages/login/index.tsx` |
| **SessionExpiredDialog** | 1 | `App.tsx` |

**Recommendation**: Dissolve folder entirely

---

### src/components/common/ (32 components)

#### Truly Shared (Keep in common/)

| Component | Consumers | Key Consumer Paths |
|-----------|-----------|-------------------|
| **columns/** | 25 | Multiple pages and components (createActionColumn, createTruncatedColumn, createStatusColumn, renderTimestamp, renderBoolean, VersionTag) |
| **LoadingWrapper** | 21 | App.tsx, multiple pages, multiple modals |
| **AuditTraceModal** | 12 | StoragePage, InfrastructurePage, UsersPage, TeamsPage, AccessPage, MachineTable, ClusterTable, PoolTable, CredentialsPage, AuditPage |
| **UnifiedResourceModal** | 11 | DistributedStoragePage, StoragePage, MachinesPage, InfrastructurePage, TeamsPage, MachineRepositoriesPage, CredentialsPage, SnapshotTable, RbdImageTable |
| **QueueItemTraceModal** | 10 | DistributedStoragePage, StoragePage, QueuePage, MachinesPage, MachineRepositoriesPage, RepositoryContainersPage, CredentialsPage, SnapshotTable, RbdImageTable |
| **ResourceListView** | 6 | QueuePage, InfrastructurePage, UsersPage, TeamsPage, AccessPage |
| **TeamSelector** | 5 | DistributedStoragePage, StoragePage, MachinesPage, CredentialsPage |
| **TelemetryProvider** | 4 | App.tsx, useTelemetryTracking hook, MainLayout, login page |
| **InlineLoadingIndicator** | 4 | VirtualMachineTable, RemoteFileBrowserModal, LocalCommandModal, MachineAssignmentStatusCell |
| **ActionButtonGroup** | 7 | StoragePage, CredentialsPage, MachineTable columns, ClusterTable columns, PoolTable columns, SnapshotTable columns, RbdImageTable |
| **VaultEditorModal** | 3 | ProfilePage, CompanyPage, UnifiedResourceModal |
| **TemplatePreviewModal** | 3 | UnifiedResourceModal, FunctionSelectionModal |

#### Dual-Use (Evaluate case-by-case)

| Component | Consumers | Consumer Paths |
|-----------|-----------|----------------|
| **AppProviders** | 2 | `App.tsx`, `main.tsx` |
| **SandboxWarning** | 2 | `MainLayout`, `pages/login/index.tsx` |
| **LanguageSelector** | 2 | `MainLayout/UserMenu`, `AuthLayout` |
| **ThemeToggle** | 2 | `MainLayout/UserMenu`, `AuthLayout` |
| **FunctionSelectionModal** | 2 | `UnifiedResourceModal`, `MachineRepositoryTable` |
| **TemplateSelector** | 2 | `UnifiedResourceModal`, `FunctionSelectionModal` |

#### Single-Use (Move to consumers)

| Component | Consumers | Consumer Path |
|-----------|-----------|---------------|
| **EndpointSelector** | 1 | `pages/login/index.tsx` |
| **VersionSelector** | 1 | `pages/login/index.tsx` |
| **Turnstile** | 1 | `auth/RegistrationModal` |
| **LanguageLink** | 1 | `auth/RegistrationModal` |
| **FilterTagDisplay** | 1 | `pages/queue/QueuePage.tsx` |
| **NotificationBell** | 1 | `layout/MainLayout/index.tsx` |
| **ErrorBoundary** | 1 | `App.tsx` |
| **InteractionTracker** | 1 | `App.tsx` |
| **ThemedToaster** | 1 | `App.tsx` |
| **ConnectivityTestModal** | 1 | `pages/machines/MachinesPage.tsx` |
| **VaultEditor** | 1 | `forms/ResourceFormWithVault` |

#### Unused (Delete or verify internal usage)

| Component | Notes |
|-----------|-------|
| **FieldGenerator** | Check if used internally by VaultEditor |
| **NestedObjectEditor** | Check if used internally by VaultEditor |
| **SimpleJsonEditor** | Check if used internally by VaultEditor/QueueItemTraceModal |
| **styled/** | Utility file - verify usage |

---

### src/components/dashboard/ (1 component)

| Component | Consumers | Consumer Path |
|-----------|-----------|---------------|
| **DistributedStorageDashboardWidget** | 1 | `pages/dashboard/DashboardPage.tsx` |

**Recommendation**: Move entire folder to `pages/dashboard/components/`

---

### src/components/distributedStorage/ (1 component)

| Component | Consumers | Consumer Path |
|-----------|-----------|---------------|
| **MachineExclusivityWarning** | 1 | `pages/distributedStorage/components/CloneMachineManager/index.tsx` |

**Recommendation**: Move to `pages/distributedStorage/components/`

---

### src/components/forms/ (6 components)

| Component | Consumers | Consumer Paths |
|-----------|-----------|----------------|
| **FormFields/PasswordField** | 2 | `pages/settings/company/CompanyPage.tsx`, `pages/settings/profile/ProfilePage.tsx` |
| **FormFields/PasswordConfirmField** | 2 | `pages/settings/company/CompanyPage.tsx`, `pages/settings/profile/ProfilePage.tsx` |
| **FormFields/OTPCodeField** | 1 | `settings/TwoFactorSettings/index.tsx` |
| **ResourceForm** | 1 | `pages/organization/users/UsersPage.tsx` |
| **ResourceFormWithVault** | 1 | `common/UnifiedResourceModal/index.tsx` |

**Recommendation**:
- Keep PasswordField, PasswordConfirmField as shared
- Move OTPCodeField with TwoFactorSettings
- Move ResourceForm to users page
- Co-locate ResourceFormWithVault with UnifiedResourceModal

---

### src/components/layout/ (2 main + sub-components)

| Component | Consumers | Consumer Path |
|-----------|-----------|---------------|
| **AuthLayout** | 1 | `App.tsx` |
| **MainLayout** | 1 | `App.tsx` |
| **MainLayout/Sidebar** | 0 | Internal to MainLayout |
| **MainLayout/UserMenu** | 0 | Internal to MainLayout |

**Recommendation**: Keep as-is (app-level layout concerns)

---

### src/components/resources/ (23 components)

#### Dual-Use (Keep in resources/)

| Component | Consumers | Consumer Paths |
|-----------|-----------|----------------|
| **MachineRepositoryTable** | 2 | `pages/resources/MachineRepositoriesPage.tsx`, `pages/distributedStorage/components/FilterableMachineTable/index.tsx` |
| **UnifiedDetailPanel** | 2 | `pages/resources/MachineRepositoriesPage.tsx`, `pages/resources/RepositoryContainersPage.tsx` |
| **AvailableMachinesSelector** | 2 | `pages/distributedStorage/components/CloneMachineManager/components/AssignMachinesModal.tsx`, `pages/distributedStorage/components/ManageClusterMachinesModal.tsx` |
| **MachineAssignmentStatusBadge** | 2 | `features/distributed-storage/components/performance/LazyAssignmentStatus.tsx`, `pages/distributedStorage/components/CloneMachineManager/columns.tsx` |
| **MachineAssignmentStatusCell** | 2 | `features/distributed-storage/components/performance/VirtualMachineTable.tsx`, `pages/distributedStorage/components/FilterableMachineTable/columns.tsx` |

#### Single-Use (Move to consumers)

| Component | Consumers | Consumer Path |
|-----------|-----------|---------------|
| **AssignToClusterModal** | 1 | `pages/distributedStorage/components/DistributedStorageMachinesTab.tsx` |
| **RemoveFromClusterModal** | 1 | `pages/distributedStorage/components/DistributedStorageMachinesTab.tsx` |
| **ViewAssignmentStatusModal** | 1 | `pages/distributedStorage/components/DistributedStorageMachinesTab.tsx` |
| **AssignMachinesToCloneModal** | 1 | `pages/distributedStorage/components/CloneTable/index.tsx` |
| **ImageMachineReassignmentModal** | 1 | `pages/distributedStorage/components/RbdImageTable.tsx` |
| **RcloneImportWizard** | 1 | `pages/storage/StoragePage.tsx` |
| **RemoteFileBrowserModal** | 1 | `pages/resources/MachineRepositoriesPage.tsx` |
| **RepositoryContainerTable** | 1 | `pages/resources/RepositoryContainersPage.tsx` |
| **SplitResourceView** | 1 | `pages/machines/MachinesPage.tsx` |

#### Unused (Verify internal usage)

| Component | Notes |
|-----------|-------|
| **ContainerDetailPanel** | Likely used by UnifiedDetailPanel internally |
| **RepositoryDetailPanel** | Likely used by UnifiedDetailPanel internally |
| **MachineVaultStatusPanel** | Likely used by UnifiedDetailPanel internally |
| **MachineTable** | Likely used by SplitResourceView internally |
| **LocalActionsMenu** | Likely used by table components internally |
| **LocalCommandModal** | Likely used by LocalActionsMenu internally |
| **PipInstallationModal** | Likely used by LocalActionsMenu internally |
| **DistributedStorageSection** | Likely used by MachineVaultStatusPanel internally |
| **SplitRepositoryView** | Check usage |
| **detailPanelPrimitives** | Utility file - verify usage |

---

### src/components/settings/ (1 component)

| Component | Consumers | Consumer Path |
|-----------|-----------|---------------|
| **TwoFactorSettings** | 1 | `pages/settings/profile/ProfilePage.tsx` |

**Recommendation**: Move to `pages/settings/profile/components/`

---

### src/components/system/ (1 component)

| Component | Consumers | Consumer Path |
|-----------|-----------|---------------|
| **UserSessionsTab** | 1 | `pages/organization/access/AccessPage.tsx` |

**Recommendation**: Move to `pages/organization/access/components/`

---

### src/components/ui/ (9 exports)

| Component | Consumers | Notes |
|-----------|-----------|-------|
| **index.ts** | 7+ | ProfilePage, CompanyPage, InfrastructurePage, AccessPage, TeamsPage, UsersPage + their styles |
| card.tsx, danger.tsx, form.tsx, list.tsx, modal.tsx, page.tsx, text.tsx, utils.tsx | - | All exported via index.ts |

**Recommendation**: Keep as shared UI primitives

---

## Phased Refactoring Plan

### Phase 1: Delete Single-Component Feature Folders

Move entire folders that contain only single-use components:

#### 1.1 Dashboard
```
src/components/dashboard/DistributedStorageDashboardWidget/
  → src/pages/dashboard/components/DistributedStorageDashboardWidget/
```

#### 1.2 Settings
```
src/components/settings/TwoFactorSettings/
  → src/pages/settings/profile/components/TwoFactorSettings/
```

#### 1.3 System
```
src/components/system/UserSessionsTab/
  → src/pages/organization/access/components/UserSessionsTab/
```

#### 1.4 DistributedStorage
```
src/components/distributedStorage/MachineExclusivityWarning/
  → src/pages/distributedStorage/components/MachineExclusivityWarning/
```

**Delete empty folders**: `dashboard/`, `settings/`, `system/`, `distributedStorage/`

---

### Phase 2: Auth Components

#### 2.1 Create App-level components folder
```
src/components/auth/SessionExpiredDialog/
  → src/components/app/SessionExpiredDialog/
```

#### 2.2 Move to login page
```
src/components/auth/RegistrationModal/
  → src/pages/login/components/RegistrationModal/
```

**Delete**: `src/components/auth/`

---

### Phase 3: Login-specific "Common" Components

Move from `src/components/common/` to `src/pages/login/components/`:

```
EndpointSelector/
VersionSelector/
Turnstile.tsx
LanguageLink/
```

---

### Phase 4: DistributedStorage Modals from Resources

Move from `src/components/resources/` to `src/pages/distributedStorage/components/`:

```
AssignToClusterModal/
RemoveFromClusterModal/
ViewAssignmentStatusModal/
AssignMachinesToCloneModal/
ImageMachineReassignmentModal/
```

---

### Phase 5: Other Single-Use Relocations

#### 5.1 App-level components
Create `src/components/app/` and move:
```
src/components/common/AppProviders/
src/components/common/ErrorBoundary/
src/components/common/InteractionTracker/
src/components/common/ThemedToaster/
src/components/auth/SessionExpiredDialog/ (from Phase 2)
```

#### 5.2 Queue-specific
```
src/components/common/FilterTagDisplay/
  → src/pages/queue/components/FilterTagDisplay/
```

#### 5.3 Machines-specific
```
src/components/common/ConnectivityTestModal/
  → src/pages/machines/components/ConnectivityTestModal/
```

#### 5.4 Layout internals
```
src/components/common/NotificationBell/
  → src/components/layout/MainLayout/components/NotificationBell/
```

#### 5.5 Storage-specific
```
src/components/resources/RcloneImportWizard/
  → src/pages/storage/components/RcloneImportWizard/
```

#### 5.6 Resources page-specific
```
src/components/resources/RemoteFileBrowserModal/
  → src/pages/resources/components/RemoteFileBrowserModal/

src/components/resources/RepositoryContainerTable/
  → src/pages/resources/components/RepositoryContainerTable/
```

#### 5.7 Machines page-specific
```
src/components/resources/SplitResourceView/
  → src/pages/machines/components/SplitResourceView/
```

---

### Phase 6: Forms Consolidation

#### 6.1 Keep shared
- `FormFields/PasswordField` - stays in forms/
- `FormFields/PasswordConfirmField` - stays in forms/

#### 6.2 Move to consumers
```
FormFields/OTPCodeField/
  → src/pages/settings/profile/components/OTPCodeField/

ResourceForm/
  → src/pages/organization/users/components/ResourceForm/

ResourceFormWithVault/
  → src/components/common/UnifiedResourceModal/components/ResourceFormWithVault/
```

---

### Phase 7: Resources Internal Restructure

Create `src/components/resources/internal/` for tightly-coupled components:

```
ContainerDetailPanel/
RepositoryDetailPanel/
MachineVaultStatusPanel/
MachineTable/
LocalActionsMenu/
LocalCommandModal/
PipInstallationModal/
DistributedStorageSection/
SplitRepositoryView/
detailPanelPrimitives.ts
```

Keep at resources root:
```
MachineRepositoryTable/
UnifiedDetailPanel/
AvailableMachinesSelector/
MachineAssignmentStatusBadge/
MachineAssignmentStatusCell/
```

---

### Phase 8: VaultEditor Internals

Move internal components to `src/components/common/VaultEditor/components/`:

```
src/components/common/FieldGenerator/
src/components/common/NestedObjectEditor/
src/components/common/SimpleJsonEditor/
```

---

### Phase 9: Cleanup Unused Components

After all moves, verify and potentially delete:
- Any components with 0 external consumers that aren't used internally
- Empty index.ts barrel exports
- Orphaned style files

---

## Target Folder Structure

```
src/components/
├── app/                              # App.tsx level components (NEW)
│   ├── AppProviders/
│   ├── ErrorBoundary/
│   ├── InteractionTracker/
│   ├── SessionExpiredDialog/
│   └── ThemedToaster/
│
├── common/                           # Truly shared components only
│   ├── ActionButtonGroup/
│   ├── AuditTraceModal/
│   ├── columns/
│   │   └── index.ts
│   ├── FunctionSelectionModal/
│   ├── InlineLoadingIndicator/
│   ├── LanguageSelector/
│   ├── LoadingWrapper/
│   ├── QueueItemTraceModal/
│   ├── ResourceListView/
│   ├── SandboxWarning/
│   ├── TeamSelector/
│   ├── TelemetryProvider/
│   ├── TemplatePreviewModal/
│   ├── TemplateSelector/
│   ├── ThemeToggle/
│   ├── UnifiedResourceModal/
│   │   └── components/
│   │       └── ResourceFormWithVault/
│   ├── VaultEditor/
│   │   └── components/
│   │       ├── FieldGenerator/
│   │       ├── NestedObjectEditor/
│   │       └── SimpleJsonEditor/
│   └── VaultEditorModal/
│
├── forms/                            # Shared form components only
│   └── FormFields/
│       ├── PasswordField/
│       └── PasswordConfirmField/
│
├── layout/
│   ├── AuthLayout/
│   └── MainLayout/
│       ├── components/
│       │   └── NotificationBell/
│       ├── Sidebar/
│       └── UserMenu/
│
├── resources/                        # Multi-page resource components
│   ├── internal/                     # Tightly coupled internals
│   │   ├── ContainerDetailPanel/
│   │   ├── RepositoryDetailPanel/
│   │   ├── MachineVaultStatusPanel/
│   │   ├── MachineTable/
│   │   ├── LocalActionsMenu/
│   │   ├── LocalCommandModal/
│   │   ├── PipInstallationModal/
│   │   ├── DistributedStorageSection/
│   │   ├── SplitRepositoryView/
│   │   └── detailPanelPrimitives.ts
│   ├── AvailableMachinesSelector/
│   ├── MachineAssignmentStatusBadge/
│   ├── MachineAssignmentStatusCell/
│   ├── MachineRepositoryTable/
│   └── UnifiedDetailPanel/
│
└── ui/                               # UI primitives
    ├── card.tsx
    ├── danger.tsx
    ├── form.tsx
    ├── index.ts
    ├── list.tsx
    ├── modal.tsx
    ├── page.tsx
    ├── text.tsx
    └── utils.tsx

src/pages/
├── dashboard/
│   └── components/
│       └── DistributedStorageDashboardWidget/
│
├── distributedStorage/
│   └── components/
│       ├── AssignMachinesToCloneModal/
│       ├── AssignToClusterModal/
│       ├── ImageMachineReassignmentModal/
│       ├── MachineExclusivityWarning/
│       ├── RemoveFromClusterModal/
│       ├── ViewAssignmentStatusModal/
│       └── ... (existing components)
│
├── login/
│   └── components/
│       ├── EndpointSelector/
│       ├── LanguageLink/
│       ├── RegistrationModal/
│       ├── Turnstile.tsx
│       └── VersionSelector/
│
├── machines/
│   └── components/
│       ├── ConnectivityTestModal/
│       └── SplitResourceView/
│
├── organization/
│   ├── access/
│   │   └── components/
│   │       └── UserSessionsTab/
│   └── users/
│       └── components/
│           └── ResourceForm/
│
├── queue/
│   └── components/
│       └── FilterTagDisplay/
│
├── resources/
│   └── components/
│       ├── RemoteFileBrowserModal/
│       └── RepositoryContainerTable/
│
├── settings/
│   └── profile/
│       └── components/
│           ├── OTPCodeField/
│           └── TwoFactorSettings/
│
└── storage/
    └── components/
        └── RcloneImportWizard/
```

---

## Validation Steps

### After Each Phase

1. **Build check**
   ```bash
   npm run build
   ```

2. **TypeScript check**
   ```bash
   npm run typecheck
   ```

3. **Search for broken imports**
   ```bash
   # Search for imports from old paths
   grep -r "from.*components/[old-path]" src/
   ```

4. **Update barrel exports**
   - Remove from old `index.ts` files
   - Add to new `index.ts` files if needed

### Import Update Pattern

For each moved component:

1. **Update component's internal imports** (relative paths may change)
2. **Find all import statements**
   ```bash
   grep -r "from.*ComponentName" src/
   grep -r "import.*ComponentName" src/
   ```
3. **Update all import paths**
4. **Remove from old barrel exports**
5. **Test affected pages manually**

---

## Key Files Requiring Updates

### High-impact barrel exports

- `src/components/common/index.ts` - Remove relocated components
- `src/components/resources/index.ts` - Remove relocated components
- `src/components/forms/index.ts` - Remove relocated components

### Pages with most import changes

| Page | Affected Components Count |
|------|--------------------------|
| `pages/login/index.tsx` | 4-5 components |
| `App.tsx` | 4-5 components |
| `pages/distributedStorage/` (multiple files) | 5+ components |
| `pages/settings/profile/ProfilePage.tsx` | 2-3 components |

---

## Benefits After Refactoring

1. **Reduced cognitive load** - Components live near their usage
2. **Clearer dependencies** - Easy to see what a feature needs
3. **Smaller bundles** - Better code splitting potential
4. **Easier maintenance** - Changes isolated to feature folders
5. **True shared components** - `components/common/` only has genuinely shared code
6. **Consistent patterns** - Each page follows same structure

---

## Estimated Scope

| Metric | Count |
|--------|-------|
| Components to move | ~40 |
| Folders to create | ~15 |
| Folders to delete | 4 |
| Files requiring import updates | ~50-70 |
| Barrel exports to update | 3 |

---

## Notes

- Always verify internal usage before declaring a component "unused"
- Some components show 0 consumers because they're used via internal imports within parent components
- The `features/` folder also contains distributed-storage components - consider consolidating with pages/distributedStorage
- UI primitives in `components/ui/` are already well-organized and shared appropriately
