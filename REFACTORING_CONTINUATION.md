# DRY Refactoring Continuation Prompt - Phase 8

## Overview

This prompt continues the DRY (Don't Repeat Yourself) consolidation effort for the Rediacc console codebase. Phases 1-7 (Tasks 1-3) are complete. Phase 8 focuses on Filter UI components and Column renderer utilities.

---

## Completed Work Summary

### Phases 1-6 - Modal Hook Migrations (Complete)

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

### Phase 7 Tasks 1-3 (Complete)

#### Task 1: Styled Component Consolidation ✅

**Added to `/src/styles/primitives.ts`:**
- Card variants: `FilterCard`, `TableCard`, `SectionCard`
- Button variants: `CompactIconButton`, `PrimaryIconButton`, `SecondaryIconButton`, `CompactButton`

**Files updated to import directly from primitives (clean imports, no re-exports):**
- `ArchitecturePage.tsx` → imports `SectionCard`, `IconButton`, `CompactIconButton`
- `AuditPage/index.tsx` → imports `FilterCard`, `TableCard`, `CompactButton`
- `DistributedStoragePage.tsx` → imports `PageCard`, `PrimaryIconButton`, `SecondaryIconButton`
- `QueuePage.tsx` → imports `IconButton`
- `RepositoryContainersPage.tsx` → imports `IconButton`
- `MachineRepositoriesPage.tsx` → imports `IconButton`

**Style files cleaned (removed all backward-compatibility re-exports):**
- `architecture/styles.ts`
- `audit/AuditPage/styles.ts`
- `distributedStorage/styles.ts`
- `resources/styles.ts`
- `queue/styles.ts`

#### Task 2: Modal.confirm Utility Adoption ✅

**Files migrated to use `confirmAction` from `@/utils/confirmations`:**
- `PoolTable/index.tsx` - Added `Modal.useModal()`, replaced inline Modal.confirm
- `ClusterTable/index.tsx` - Added `Modal.useModal()`, replaced inline Modal.confirm
- `ManageClusterMachinesModal.tsx` - Added `Modal.useModal()`, replaced inline Modal.confirm
- `QueuePage.tsx` - Added `Modal.useModal()`, replaced inline Modal.confirm, added i18n keys

**Translation keys added to `/src/i18n/locales/en/queue.json`:**
- `cancelConfirm.title`
- `cancelConfirm.content`
- `cancelConfirm.okText`

**Note:** `CloneMachineManager/index.tsx` was skipped - it has custom `okButtonProps`/`cancelButtonProps` with data-testid for testing that `confirmAction` doesn't support.

#### Task 3: useExpandableTable Hook ✅

**Created `/src/hooks/useExpandableTable.ts`:**
- Returns: `{ expandedRowKeys, toggleRow, expandAll, collapseAll, isExpanded, setExpandedRowKeys }`
- Exported from `/src/hooks/index.ts`

**Files migrated:**
- `PoolTable/index.tsx`
- `ClusterTable/index.tsx`
- `RbdImageList.tsx`
- `SnapshotList/index.tsx`

**Final Status:**
- TypeScript: 0 errors
- Build: Success
- Estimated lines reduced: ~300+

---

## Phase 8: Filter UI & Column Utilities

### Goal
Create reusable components for filter tag display and column renderers to eliminate remaining duplication.

---

## Task 4: Filter UI Component (MEDIUM PRIORITY)

### Problem
Filter tag rendering is duplicated across QueuePage, AuditPage, and other list pages.

### Current Repeated Pattern
Each page renders filter tags similarly with this pattern repeated 7+ times per page:
```tsx
{filters.teamName && (
  <Tag closable onClose={() => setFilter('teamName', '')} color="blue">
    {label}
  </Tag>
)}
```

### Files to Analyze

**QueuePage.tsx** - Search for filter tag rendering patterns:
- Location: `/src/pages/queue/QueuePage.tsx`
- Look for: `<Tag closable` patterns in JSX
- Note how filters are structured and cleared

**AuditPage/index.tsx** - Similar patterns:
- Location: `/src/pages/audit/AuditPage/index.tsx`
- Compare filter rendering approach

### Solution Approach

1. **Create component** at `/src/components/common/FilterTagDisplay/index.tsx`

2. **Define interface** for filter config:
   ```tsx
   interface FilterTagConfig {
     key: string
     value: string | string[]
     label: string
     color?: string
   }

   interface FilterTagDisplayProps {
     filters: FilterTagConfig[]
     onClear: (key: string) => void
     onClearAll?: () => void
     showClearAll?: boolean
   }
   ```

3. **Component should handle:**
   - Rendering tags for active filters only (non-empty values)
   - Close button that calls `onClear(key)`
   - Optional "Clear All" button
   - Array values (multiple selections)
   - Color variants

4. **Migrate pages** to use the new component:
   - `QueuePage.tsx`
   - `AuditPage/index.tsx`
   - Any other pages with similar patterns

### Estimated Impact
- 200-300 lines reduced
- Consistent filter tag UX
- Easier to add filters to new pages

---

## Task 5: Column Renderer Utilities (LOW PRIORITY)

### Problem
Column files repeat similar renderers for status tags, timestamps, and action buttons.

### Files to Analyze

**AuditPage columns:**
- Location: `/src/pages/audit/AuditPage/columns.tsx`
- Look for: status tag rendering, timestamp formatting

**DistributedStorage columns:**
- Location: `/src/pages/distributedStorage/components/*/columns.tsx`
- Multiple files: ClusterTable, PoolTable, SnapshotList, CloneList, etc.

**QueuePage:**
- Location: `/src/pages/queue/QueuePage.tsx`
- Inline column definitions

### Common Patterns to Extract

1. **Status Tag Renderer:**
   - Maps status values to colors and labels
   - Uses `<Tag>` with appropriate styling

2. **Timestamp Renderer:**
   - Formats dates consistently (e.g., `formatTimestampAsIs`)
   - Handles null/undefined gracefully

3. **Action Column Renderer:**
   - Dropdown menus with edit/delete/view actions
   - Uses `ActionButtonGroup` or similar

### Solution Approach

1. **Create directory** at `/src/components/common/columns/`

2. **Create utilities:**
   - `StatusColumnRenderer.tsx` - Reusable status tag column
   - `TimestampColumnRenderer.tsx` - Date formatting column
   - `ActionColumnRenderer.tsx` - Action button/dropdown column
   - `index.ts` - Export all renderers

3. **Define interfaces** for each renderer's props

4. **Migrate column files** to use shared renderers

### Estimated Impact
- 100-150 lines reduced
- Consistent column styling across all tables

---

## Implementation Guidelines

### Best Practices

1. **Clean Imports** - Import directly from source, no re-exports for backward compatibility
2. **Type Safety** - Always use proper TypeScript generics
3. **Null Guards** - Use proper checks instead of `|| ''` fallbacks
4. **Translation Keys** - Use i18n for all user-facing strings

### Verification Steps

After each task:
1. Run TypeScript check: `npx tsc --noEmit`
2. Run build: `npm run build`
3. Verify 0 errors

---

## Reference: Key File Locations

### Hooks
- `/src/hooks/useDialogState.ts` - Dialog state hooks
- `/src/hooks/useFormModal.ts` - Form modal hooks
- `/src/hooks/useExpandableTable.ts` - Table expansion hook
- `/src/hooks/useFilters.ts` - Filter state management
- `/src/hooks/index.ts` - All hook exports

### Utilities
- `/src/utils/confirmations.ts` - `confirmDelete`, `confirmAction`
- `/src/styles/primitives.ts` - Shared styled components (IconButton, cards, etc.)
- `/src/core/index.ts` - Core utilities like `formatTimestampAsIs`, `createSorter`

### Existing Patterns to Follow
- `ActionButtonGroup` - `/src/components/common/ActionButtonGroup/index.tsx`
- Shared styled components - `/src/components/common/styled/index.ts`

---

## Remaining Consolidation Potential

| Task | Lines Saved | Complexity | Status |
|------|-------------|------------|--------|
| Styled Components | ~150 | MEDIUM | ✅ Complete |
| Modal.confirm | ~50 | LOW | ✅ Complete |
| Table Hooks | ~100 | MEDIUM | ✅ Complete |
| Filter UI | 200-300 | MEDIUM | 📋 Pending |
| Column Utilities | 100-150 | MEDIUM | 📋 Pending |
| **TOTAL REMAINING** | **300-450** | | |

---

## Phase 8 Status: COMPLETE

Tasks 4-5 have been completed:
- `FilterTagDisplay` component created at `/src/components/common/FilterTagDisplay/index.tsx`
- Column renderer utilities created at `/src/components/common/columns/`
- Migrated: QueuePage, AuditPage/columns, ClusterTable/columns, PoolTable/columns, RbdImageList
- TypeScript: 0 errors
- Build: Success

---

## Phase 9: Naming Consistency Standardization

### Goal
Standardize naming conventions across the codebase to improve consistency, discoverability, and maintainability.

---

## Task 6: Modal Props Standardization (HIGH PRIORITY)

### Problem
Modal components use inconsistent prop names for visibility and close callbacks.

### Current Inconsistencies

**Visibility prop:**
- `open={...}` - Used by newer components (FunctionSelectionModal, UnifiedResourceModal, AuditTraceModal)
- `visible={...}` - Used by older components (QueueItemTraceModal, RegistrationModal)

**Close callback:**
- `onCancel` - 31 occurrences
- `onClose` - 22 occurrences

### Files to Update

**Components using `visible` prop (change to `open`):**
- `/src/components/common/QueueItemTraceModal/index.tsx`
- `/src/components/auth/RegistrationModal/index.tsx`
- `/src/components/common/FunctionSelectionModal/index.tsx` (internal `showTemplateDetails`)

**Usage sites to update:**
- All pages that use QueueItemTraceModal: `visible={...}` → `open={...}`
  - QueuePage.tsx, MachinesPage.tsx, CredentialsPage.tsx, etc.

### Solution Approach

1. **Standardize on `open` for visibility** (matches Ant Design Modal API)
2. **Standardize on `onCancel` for close callback** (matches Ant Design Modal API)

3. **Update QueueItemTraceModal:**
   ```tsx
   // Change interface
   interface QueueItemTraceModalProps {
     open: boolean      // was: visible
     onCancel: () => void  // was: onClose
     taskId: string | null
   }
   ```

4. **Update all usage sites** to use new prop names

5. **Update hooks for consistency:**
   - `useQueueTraceModal` should return `isOpen` instead of `state.visible`
   - Align with `useDialogState` and `useTraceModal` patterns

### Estimated Impact
- ~50 prop name changes across files
- Consistent API across all modals

---

## Task 7: Hook State Standardization (MEDIUM PRIORITY)

### Problem
Modal-related hooks return different property names for the same concept.

### Current Inconsistencies

```typescript
// useDialogState returns:
{ isOpen: boolean, state: { open: boolean } }

// useTraceModal returns:
{ isOpen: boolean, state: { visible: boolean } }  // Internal uses 'visible'

// useQueueTraceModal returns:
{ state: { visible: boolean } }  // No isOpen helper
```

### Files to Analyze

- `/src/hooks/useDialogState.ts` - Reference implementation (good)
- `/src/hooks/useDialogState.ts` (useTraceModal) - Lines ~100-130
- `/src/hooks/useDialogState.ts` (useQueueTraceModal) - Lines ~150-180

### Solution Approach

1. **Standardize internal state to use `open`:**
   ```typescript
   // All hooks should use:
   state: { open: boolean, ... }
   ```

2. **All hooks should expose `isOpen` helper**

3. **Update useQueueTraceModal to match useTraceModal pattern**

### Estimated Impact
- ~20 lines changed in hooks
- Consistent mental model for developers

---

## Task 8: Query Hook Naming Standardization (MEDIUM PRIORITY)

### Problem
Some query hooks use `useGet*` prefix while others don't.

### Current Inconsistencies

| With `Get` prefix | Without prefix |
|-------------------|----------------|
| `useGetAvailableMachinesForClone` | `useMachines` |
| `useGetCloneMachines` | `useTeams` |
| `useGetCloneMachineAssignmentValidation` | `useBridges` |
| `useGetTFAStatus` | `useRegions` |
| `useGetMachineAssignmentStatus` | `useUsers` |
| `useGetCompanyVaults` | `useCompanyVault` |

### Files to Analyze

- `/src/api/queries/distributedStorage.ts` - Has `useGet*` hooks
- `/src/api/queries/machines.ts` - Has `useGet*` hooks
- `/src/api/queries/twoFactor.ts` - Has `useGet*` hooks
- Other query files use plain `use*` pattern

### Solution Approach

**Option A: Remove `Get` prefix (Recommended)**
- Simpler, shorter names
- Consistent with majority of codebase
- `useGetAvailableMachinesForClone` → `useAvailableMachinesForClone`

**Option B: Add `Get` prefix everywhere**
- More explicit about operation type
- Would require many more changes

### Migration Steps

1. For each `useGet*` hook:
   - Rename the hook function
   - Update the export
   - Search and replace all usages across codebase

2. **Hooks to rename (if Option A):**
   - `useGetAvailableMachinesForClone` → `useAvailableMachinesForClone`
   - `useGetCloneMachines` → `useCloneMachines`
   - `useGetCloneMachineAssignmentValidation` → `useCloneMachineAssignmentValidation`
   - `useGetTFAStatus` → `useTFAStatus`
   - `useGetMachineAssignmentStatus` → `useMachineAssignmentStatus`
   - `useGetCompanyVaults` → `useCompanyVaults`

### Estimated Impact
- 6 hook renames
- ~30-50 import/usage updates

---

## Task 9: Mutation Hook Naming (Delete vs Remove) (LOW PRIORITY)

### Problem
Mutation hooks use both `Delete` and `Remove` for similar operations.

### Current Pattern

| Delete (for entities) | Remove (for relationships) |
|-----------------------|---------------------------|
| `useDeleteBridge` | `useRemovePermissionFromGroup` |
| `useDeleteMachine` | `useRemoveTeamMember` |
| `useDeleteTeam` | |
| `useDeleteRepository` | |

### Analysis
This may actually be intentional semantic distinction:
- **Delete**: Permanently removes an entity from the system
- **Remove**: Removes a relationship/membership (entity still exists)

### Recommendation
**Keep current pattern** - the distinction is meaningful:
- Deleting a machine removes it entirely
- Removing a team member just removes the membership

Document this convention in a coding standards guide.

---

## Task 10: List vs Table Component Naming (LOW PRIORITY)

### Problem
Data grid components use inconsistent suffixes.

### Current State

**Using `Table`:**
- `ClusterTable`
- `PoolTable`
- `FilterableMachineTable`
- `MachineTable`
- `VirtualMachineTable`

**Using `List`:**
- `CloneList`
- `SnapshotList`
- `RbdImageList`
- `MachineRepositoryList`
- `RepositoryContainerList`
- `CloneMachineList`

### Analysis
All these components render `<Table>` from Ant Design, so `Table` suffix is more accurate.

### Solution Approach

1. **Standardize on `*Table` suffix** for components that render data tables

2. **Renames needed:**
   - `CloneList` → `CloneTable`
   - `SnapshotList` → `SnapshotTable`
   - `RbdImageList` → `RbdImageTable`
   - `MachineRepositoryList` → `MachineRepositoryTable`
   - `RepositoryContainerList` → `RepositoryContainerTable`
   - `CloneMachineList` → `CloneMachineTable`

3. **For each rename:**
   - Rename directory/file
   - Update component name
   - Update all imports
   - Update any test files

### Estimated Impact
- 6 component renames
- High number of import updates
- Consider doing this as a separate PR due to scope

---

## Task 11: State Variable Naming Convention (LOW PRIORITY)

### Problem
Modal state variables use various naming patterns.

### Current Patterns

```typescript
// Pattern 1: *Modal
const [assignModalOpen, setAssignModalOpen] = useState(false)

// Pattern 2: *Visible
const [versionSelectorVisible, setVersionSelectorVisible] = useState(false)

// Pattern 3: show*
const [showTFAModal, setShowTFAModal] = useState(false)

// Pattern 4: is*Open
const [isCreateUserModalOpen, setIsCreateUserModalOpen] = useState(false)
```

### Recommendation

**Standardize on Pattern 4: `is*Open`**
- Clear boolean naming with `is` prefix
- Explicit about what it controls
- Example: `isAssignModalOpen`, `isTFAModalOpen`

This is lower priority as it's internal implementation detail.

---

## Implementation Guidelines

### Migration Order (Recommended)

1. **Task 6: Modal Props** - High impact, improves API consistency
2. **Task 7: Hook State** - Required for Task 6 to be complete
3. **Task 8: Query Hooks** - Medium impact, improves discoverability
4. **Task 10: List→Table** - Can be done as separate PR
5. **Task 9 & 11** - Document conventions, opportunistic fixes

### Testing Strategy

After each task:
1. Run TypeScript check: `npx tsc --noEmit`
2. Run build: `npm run build`
3. Run existing tests if available
4. Manual smoke test of affected pages

### Search Patterns for Migration

```bash
# Find all visible prop usages
grep -r "visible={" src --include="*.tsx"

# Find all onClose prop usages
grep -r "onClose={" src --include="*.tsx"

# Find useGet* hooks
grep -r "useGet[A-Z]" src --include="*.ts"

# Find *List components
find src -name "*List.tsx" -o -name "*List" -type d
```

---

## Reference: Key File Locations

### Hooks
- `/src/hooks/useDialogState.ts` - Contains useDialogState, useTraceModal, useQueueTraceModal
- `/src/hooks/index.ts` - All hook exports

### Modal Components
- `/src/components/common/QueueItemTraceModal/index.tsx`
- `/src/components/common/AuditTraceModal/index.tsx`
- `/src/components/auth/RegistrationModal/index.tsx`

### Query Files
- `/src/api/queries/distributedStorage.ts`
- `/src/api/queries/machines.ts`
- `/src/api/queries/twoFactor.ts`

### Table Components (to rename)
- `/src/pages/distributedStorage/components/CloneList/`
- `/src/pages/distributedStorage/components/SnapshotList/`
- `/src/pages/distributedStorage/components/RbdImageList.tsx`

---

## Remaining Consolidation Potential

| Task | Impact | Complexity | Status |
|------|--------|------------|--------|
| Modal Props (open/onCancel) | HIGH | MEDIUM | Pending |
| Hook State Consistency | MEDIUM | LOW | Pending |
| Query Hook Names | MEDIUM | MEDIUM | Pending |
| List→Table Naming | LOW | HIGH | Pending |
| Delete vs Remove | - | - | Keep as-is |
| State Variable Names | LOW | LOW | Document only |

---

## Session Goal

Complete Tasks 6-8 for immediate consistency wins. Tasks 9-11 can be addressed opportunistically or in future sessions.

### Expected Outcome
- All modals use `open` prop and `onCancel` callback
- All modal hooks return consistent `isOpen` state
- Query hooks follow `use*` pattern (no `Get` prefix)
- TypeScript: 0 errors
- Build: Success
