# DRY Refactoring Continuation Prompt - Phase 11

## Overview

This prompt continues the DRY (Don't Repeat Yourself) consolidation effort for the Rediacc console codebase. **Phases 1-10 (Priorities 1-3) are complete.** This document serves as a reference for the current codebase state and remaining refactoring opportunities.

---

## Current Codebase State (After Phase 10)

### Established Conventions

#### 1. Modal Props
All modals now use consistent prop names:
- **Visibility**: `open` (not `visible`)
- **Close callback**: `onCancel` (not `onClose`)
- **Example**: `<Modal open={isOpen} onCancel={handleClose} />`

#### 2. Hook State
All modal hooks use consistent internal state:
- **State property**: `open` (not `visible`)
- **Helper**: All hooks expose `isOpen` boolean
- **File**: `/src/hooks/useDialogState.ts`

#### 3. Query Hook Naming
All query hooks follow `use*` pattern (no `Get` prefix):
- `useTFAStatus` (was `useGetTFAStatus`)
- `useCompanyVaults` (was `useGetCompanyVaults`)
- `useMachineAssignmentStatus` (was `useGetMachineAssignmentStatus`)
- `useAvailableMachinesForClone` (was `useGetAvailableMachinesForClone`)
- `useCloneMachineAssignmentValidation` (was `useGetCloneMachineAssignmentValidation`)
- `useCloneMachines` (was `useGetCloneMachines`)

#### 4. Mutation Hook Naming (Semantic Distinction)
- `useDelete*` - Permanently removes an entity from the system
- `useRemove*` - Removes a relationship/membership (entity still exists)

#### 5. Component Naming
All data table components use `*Table` suffix:
- `CloneTable` (was `CloneList`)
- `SnapshotTable` (was `SnapshotList`)
- `RbdImageTable` (was `RbdImageList`)
- `CloneMachineTable` (was `CloneMachineList`)
- `MachineRepositoryTable` (was `MachineRepositoryList`)
- `RepositoryContainerTable` (was `RepositoryContainerList`)

#### 6. State Variable Convention (Documented Standard)
For modal state variables, use the `is*Open` pattern.

**Correct:**
- `const [isAssignModalOpen, setIsAssignModalOpen] = useState(false)`

**Incorrect examples to avoid:**
- `const [assignModalOpen, setAssignModalOpen] = useState(false)`
- `const [showTFAModal, setShowTFAModal] = useState(false)`

#### 7. Form Field Components (NEW in Phase 10)
Use reusable form field components from `/src/components/forms/FormFields/`:
- `PasswordField` - Password input with validation
- `PasswordConfirmField` - Confirmation with match validation
- `OTPCodeField` - 6-digit code input

#### 8. Mutation Error Handling (NEW in Phase 10)
Use utilities from `/src/utils/mutationUtils.ts`:
- `createErrorHandler(fallbackMessage)` - Standard error handler
- `handleMutationError(error, fallback)` - Direct error handling
- Always use `i18n.t()` for messages, never hardcoded strings

#### 9. i18n for Mutations (NEW in Phase 10)
All mutation messages must use translation keys:
```typescript
// Correct
onError: createErrorHandler(i18n.t('queue:errors.createFailed'))
showMessage('success', i18n.t('queue:success.created', { taskId }))

// Incorrect
onError: createErrorHandler('Failed to create queue item')
showMessage('success', `Queue item ${taskId} created`)
```

---

## Completed Work Summary

### Phases 1-6 - Modal Hook Migrations

**Hooks Created** (exported from `/src/hooks/index.ts`):
- `useDialogState<T>()` - Generic dialog/modal state
- `useTraceModal()` - Audit trace modal with typed accessors
- `useQueueTraceModal()` - Queue trace modal
- `useFormModal<T>()` - Create/edit/vault form modals
- `useExtendedFormModal<T>()` - Form modal with creationContext support
- `useFilters<T>()` - Filter state management
- `useAsyncAction()` - Async error handling
- `useFormSubmission<T>()` - Form submit wrapper

**Components Created:**
- `ActionButtonGroup<T>` - `/src/components/common/ActionButtonGroup/index.tsx`
- Shared styled components - `/src/components/common/styled/index.ts`

### Phase 7 - Styled Components & Utilities

- Styled component consolidation in `/src/styles/primitives.ts`
- Modal.confirm utility adoption via `confirmAction`
- `useExpandableTable` hook created

### Phase 8 - Filter UI & Column Utilities

- `FilterTagDisplay` component at `/src/components/common/FilterTagDisplay/index.tsx`
- Column renderer utilities at `/src/components/common/columns/`

### Phase 9 - Naming Consistency

- Task 6: Modal props standardized (open/onCancel)
- Task 7: Hook state standardized (open internally)
- Task 8: Query hooks renamed (removed Get prefix)
- Task 9: Delete/Remove naming documented
- Task 10: List→Table component renaming
- Task 11: State variable convention documented

### Phase 10 - Form Patterns, Error Handling & i18n

#### Priority 1: Form Patterns Consolidation

**Components Created:**
- `/src/components/forms/FormFields/PasswordField.tsx` - Password with validation
- `/src/components/forms/FormFields/PasswordConfirmField.tsx` - Match validation
- `/src/components/forms/FormFields/OTPCodeField.tsx` - 6-digit code input
- `/src/components/forms/FormFields/index.ts` - Clean exports with `export *`

**Hooks Created:**
- `/src/hooks/useModalForm.ts` - Combines Form.useForm with dialog state

**Files Updated:**
- `ProfilePage.tsx` - Uses PasswordField, PasswordConfirmField, useModalForm
- `CompanyPage.tsx` - Uses PasswordField, PasswordConfirmField
- `TwoFactorSettings/index.tsx` - Uses OTPCodeField

#### Priority 2: Error Handling Standardization

**Utilities Created:**
- `/src/utils/mutationUtils.ts`
  - `extractErrorMessage(error, fallback)` - Extract message from error
  - `handleMutationError(error, fallback)` - Show error message
  - `createErrorHandler(fallback)` - Create onError callback
  - `createSuccessHandler(message)` - Create onSuccess callback
  - `createMutationCallbacks(options)` - Full callback factory

**Files Updated:**
- `queue.ts` - 8 mutations use createErrorHandler
- `permissions.ts` - 5 mutations use createErrorHandler

#### Priority 3: Loading State Patterns

**Component Created:**
- `/src/components/common/LoadingWrapper/index.tsx`
  - Consistent loading/empty state handling
  - Configurable size, centering, tips
  - Empty state support

#### i18n Consolidation

**Translation Keys Added:**

`/src/i18n/locales/en/queue.json`:
```json
"errors": {
  "createFailed": "Failed to create queue item",
  "updateFailed": "Failed to update queue item",
  "updatePriorityFailed": "Failed to update queue item priority",
  "updateProtectionFailed": "Failed to update queue item protection",
  "cancelFailed": "Failed to cancel queue item",
  "deleteFailed": "Failed to delete queue item",
  "retryFailed": "Failed to retry queue item"
},
"success": {
  "created": "Queue item created",
  "createdWithId": "Queue item created with ID: {{taskId}}",
  "responseUpdated": "Queue item {{taskId}} response updated",
  "completed": "Queue item {{taskId}} completed",
  "markedFailed": "Queue item {{taskId}} marked as failed",
  "priorityUpdated": "Queue item {{taskId}} priority updated to {{priority}}",
  "protectionEnabled": "Queue item {{taskId}} protection enabled",
  "protectionDisabled": "Queue item {{taskId}} protection disabled",
  "cancellationInitiated": "Queue item {{taskId}} cancellation initiated",
  "deleted": "Queue item {{taskId}} deleted",
  "queuedForRetry": "Queue item {{taskId}} queued for retry"
}
```

`/src/i18n/locales/en/organization.json` (under `access`):
```json
"errors": {
  "createGroupFailed": "Failed to create permission group",
  "deleteGroupFailed": "Failed to delete permission group",
  "addPermissionFailed": "Failed to add permission to group",
  "removePermissionFailed": "Failed to remove permission from group",
  "assignUserFailed": "Failed to assign user to permission group"
},
"success": {
  "groupCreated": "Permission group \"{{group}}\" created successfully",
  "groupDeleted": "Permission group \"{{group}}\" deleted successfully",
  "permissionAdded": "Permission \"{{permission}}\" added to group",
  "permissionRemoved": "Permission \"{{permission}}\" removed from group",
  "userAssigned": "User assigned to permission group \"{{group}}\""
}
```

**Files Migrated to i18n:**
- `queue.ts` - 8 mutations with full i18n
- `permissions.ts` - 5 mutations with full i18n

---

## Phase 11: Remaining Refactoring Opportunities

### Priority 1: Table Column Patterns

#### Problem
While column renderers were created in Phase 8, many tables still define columns inline with duplicated patterns.

#### Patterns to Consolidate
1. **Action columns** - Dropdown menus with edit/delete/view
2. **Status columns** - Tag rendering with color mapping
3. **Date columns** - Timestamp formatting
4. **Truncated text** - Ellipsis with tooltip

#### Files to Analyze
- `/src/pages/*/columns.tsx` or inline column definitions
- `/src/pages/audit/AuditPage/columns.tsx`
- `/src/pages/distributedStorage/components/*/columns.tsx`

---

### Priority 2: API Response Handling

#### Problem
API response extraction patterns vary across the codebase.

#### Current Patterns
```typescript
// Pattern 1
const results = extractTableData<T[]>(response, 0, [])

// Pattern 2
const data = getFirstRow<T>(response, 1) ?? getFirstRow<T>(response, 0)

// Pattern 3
const allVaults = getResultSet<Record<string, unknown>>(response, 1)
```

#### Files to Analyze
- `/src/api/queries/*.ts`
- `/src/core/api/response.ts`

#### Potential Solutions
1. Standardize response extraction patterns
2. Create typed response extractors for common patterns
3. Document when to use each pattern

---

### Priority 3: Continue i18n Migration

#### Problem
Many mutation files still have hardcoded English strings.

#### Files to Migrate
- `/src/api/queries/company.ts` - Some mutations still hardcoded
- `/src/api/queries/users.ts` - Needs i18n
- `/src/api/queries/twoFactor.ts` - Needs i18n
- `/src/api/queries/vaultProtocol.ts` - Needs i18n
- `/src/api/queries/distributedStorageMutations.ts` - Needs i18n
- All other mutation files in `/src/api/queries/`

#### Pattern to Follow
```typescript
import i18n from '@/i18n/config'
import { createErrorHandler } from '@/utils/mutationUtils'

// In mutation:
onSuccess: () => {
  showMessage('success', i18n.t('namespace:success.key', { param: value }))
},
onError: createErrorHandler(i18n.t('namespace:errors.key'))
```

---

### Priority 4: Test Coverage Improvements

#### Problem
Test coverage may be inconsistent after refactoring.

#### Areas to Review
1. New form field components (`PasswordField`, `PasswordConfirmField`, `OTPCodeField`)
2. New hooks (`useModalForm`)
3. New utilities (`mutationUtils.ts`)
4. `LoadingWrapper` component

#### Action Items
1. Add unit tests for new components and hooks
2. Update E2E tests if form interactions changed
3. Verify all tests pass

---

### Priority 5: LoadingWrapper Adoption

#### Problem
`LoadingWrapper` component was created but not yet adopted across the codebase.

#### Files to Update
There are 29 files using `<Spin>` that could potentially use `LoadingWrapper`:
- Modal components with loading states
- Pages with data fetching
- Tables with loading indicators

---

## Reference: Key File Locations

### Hooks
- `/src/hooks/useDialogState.ts` - Dialog state hooks
- `/src/hooks/useFormModal.ts` - Form modal hooks
- `/src/hooks/useModalForm.ts` - Modal form hook (NEW)
- `/src/hooks/useExpandableTable.ts` - Table expansion hook
- `/src/hooks/useFilters.ts` - Filter state management
- `/src/hooks/index.ts` - All hook exports

### Form Components (NEW)
- `/src/components/forms/FormFields/PasswordField.tsx`
- `/src/components/forms/FormFields/PasswordConfirmField.tsx`
- `/src/components/forms/FormFields/OTPCodeField.tsx`
- `/src/components/forms/FormFields/index.ts`

### Utilities
- `/src/utils/confirmations.ts` - confirmDelete, confirmAction
- `/src/utils/mutationUtils.ts` - Error handling utilities (NEW)
- `/src/styles/primitives.ts` - Shared styled components
- `/src/core/index.ts` - Core utilities

### Common Components (NEW)
- `/src/components/common/LoadingWrapper/index.tsx`

### Query Files
- `/src/api/queries/queue.ts` - Queue queries (i18n complete)
- `/src/api/queries/permissions.ts` - Permission queries (i18n complete)
- `/src/api/queries/distributedStorage.ts` - DS queries
- `/src/api/queries/machines.ts` - Machine queries
- `/src/api/queries/twoFactor.ts` - TFA queries
- `/src/api/queries/company.ts` - Company queries

### Table Components
- `/src/pages/distributedStorage/components/CloneTable/`
- `/src/pages/distributedStorage/components/SnapshotTable/`
- `/src/pages/distributedStorage/components/RbdImageTable.tsx`
- `/src/components/resources/MachineRepositoryTable/`
- `/src/components/resources/RepositoryContainerTable/`

---

## Implementation Guidelines

### Best Practices

1. **Clean Exports** - Use `export *` pattern, no verbose aliasing
2. **Named Exports** - Prefer named exports over default exports
3. **Type Safety** - Always use proper TypeScript generics
4. **Translation Keys** - Use i18n.t() for ALL user-facing strings
5. **Component Naming** - Use `*Table` for data grids, `*Modal` for dialogs
6. **Error Handling** - Use `createErrorHandler()` from mutationUtils

### Verification Steps

After any refactoring task:
1. Run TypeScript check: `npx tsc --noEmit`
2. Run build: `npm run build`
3. Verify 0 errors
4. Test affected pages manually if needed

---

## Search Patterns for Common Issues

```bash
# Find hardcoded error messages in mutations
grep -r "showMessage('error'" src/api/queries --include="*.ts"

# Find mutations without i18n
grep -r "onError:" src/api/queries --include="*.ts" | grep -v "i18n.t"

# Find remaining Spin components (candidates for LoadingWrapper)
grep -r "<Spin" src --include="*.tsx"

# Find inline column definitions
grep -r "columns:" src/pages --include="*.tsx"
```

---

## Session Prompt

Use this prompt to complete all remaining Phase 11 work:

```
Please continue the DRY refactoring effort for the Rediacc console codebase.

Reference: @console/REFACTORING_CONTINUATION.md

Current Status: Phases 1-10 are complete.

Complete ALL remaining Phase 11 priorities in this session.

---

## Phase 11 Priorities (Complete All)

### Priority 1: Continue i18n Migration

**Files to migrate:**
- `/src/api/queries/twoFactor.ts`
- `/src/api/queries/users.ts`
- `/src/api/queries/company.ts`
- `/src/api/queries/vaultProtocol.ts`
- `/src/api/queries/distributedStorageMutations.ts`

**Pattern:**
import i18n from '@/i18n/config'
import { createErrorHandler } from '@/utils/mutationUtils'

onSuccess: () => {
  showMessage('success', i18n.t('namespace:success.key', { param: value }))
},
onError: createErrorHandler(i18n.t('namespace:errors.key'))

**Add translation keys to `/src/i18n/locales/en/` files:**
- twoFactor.ts → settings.json (under twoFactorAuth.errors/success)
- users.ts → organization.json (under users.errors/success)
- company.ts → system.json
- vaultProtocol.ts → system.json
- distributedStorageMutations.ts → distributedStorage.json

---

### Priority 2: Table Column Patterns

**Analyze and consolidate column definitions:**
- `/src/pages/distributedStorage/components/CloneTable/`
- `/src/pages/distributedStorage/components/SnapshotTable/`
- `/src/pages/audit/AuditPage/`

**Create column factories in `/src/components/common/columns/`:**
- `createActionColumn<T>()` - Dropdown with edit/delete/view
- `createStatusColumn()` - Tag with color mapping
- `createDateColumn()` - Timestamp formatting
- `createTruncatedColumn()` - Ellipsis with tooltip

**Update 2-3 tables to use the new factories as proof of concept.**

---

### Priority 3: LoadingWrapper Adoption

**Replace `<Spin>` with `<LoadingWrapper>` in key files:**
- Modal components with loading states
- Pages with centered loading spinners
- Components with empty state handling

**Target 5-10 high-impact replacements.**

---

### Priority 4: API Response Handling (If Time Permits)

**Document patterns in `/src/core/api/response.ts`:**
- When to use `extractTableData` vs `getFirstRow` vs `getResultSet`
- Add JSDoc comments explaining each function's use case

---

## Execution Order

1. i18n migration (highest priority - affects most files)
2. Table column patterns (high code reduction)
3. LoadingWrapper adoption (quick wins)
4. API response documentation (if time permits)

---

## Verification

After each priority:
- `npx tsc --noEmit`

Final verification:
- `npm run build`

---

## Important Guidelines

- Use `export *` pattern for clean exports
- ALL user-facing strings must use i18n.t()
- Only add translations to en locale
- Maintain type safety with generics
- No breaking changes to existing functionality

Please ultrathink before making changes. Work through priorities in order, completing each fully before moving to the next.
```

---

## Consolidation Progress

| Phase | Tasks | Status |
|-------|-------|--------|
| Phases 1-6 | Modal Hook Migrations | Complete |
| Phase 7 | Styled Components & Utilities | Complete |
| Phase 8 | Filter UI & Column Utilities | Complete |
| Phase 9 | Naming Consistency | Complete |
| Phase 10 P1 | Form Patterns Consolidation | Complete |
| Phase 10 P2 | Error Handling Standardization | Complete |
| Phase 10 P3 | Loading State Patterns | Complete |
| Phase 10 i18n | Queue & Permissions | Complete |
| Phase 11 P1 | Table Column Patterns | Pending |
| Phase 11 P2 | API Response Handling | Pending |
| Phase 11 P3 | Continue i18n Migration | Pending |
| Phase 11 P4 | Test Coverage | Pending |
| Phase 11 P5 | LoadingWrapper Adoption | Pending |

**Total Estimated Lines Reduced: 850+**

---

## Notes for Next Session

1. **i18n migration** is highest priority - many mutations still have hardcoded strings
2. **Table column patterns** can reduce significant duplication
3. **LoadingWrapper** adoption should be done opportunistically
4. Consider creating a **coding standards document** to formalize all conventions
5. **Test coverage** should be improved for all new components/hooks
