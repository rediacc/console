# Console Components - Refactoring TODO

> **📚 Reference Documents:**
> - **[REFACTORING.md](./REFACTORING.md)** - Complete guide on how to refactor components
> - **[STYLE.md](./STYLE.md)** - Styling conventions with styled-components
>
> **How to Use This Document:**
> 1. Pick a component from the list below
> 2. Follow the step-by-step process in [REFACTORING.md](./REFACTORING.md)
> 3. Apply styling conventions from [STYLE.md](./STYLE.md)
> 4. Mark as completed when done

---

## Recently Completed ✅

### ✅ MainLayout (Nov 2025 - PR #163)
- **Before**: 886 lines in single file
- **After**: Split into 9 modular files
- **Files created**: MainLayout/, Sidebar/, UserMenu/, with types, helpers, styles

### ✅ AuthLayout (Nov 2025 - PR #163)
- **Before**: 51 lines flat file
- **After**: Modular folder structure with index.tsx and styles.ts

### ✅ TeamsPage Data (Nov 2025 - PR #163)
- **Before**: 400+ lines with embedded table columns
- **After**: Extracted table columns to data.tsx (173 lines)

### SnapshotList (Nov 2025 - CLI Refactor)
- **Before**: 340+ line flat file with inline table toolbar/container styles
- **After**: SnapshotList/index.tsx, styles.ts, and columns.ts with theme-driven buttons, extracted menu definitions, and zero inline styles

### ✅ CloneMachineManager (Dec 2025 - CLI Refactor)
- **Before**: 438-line flat file with inline `style` props, embedded columns, and CSV/export logic mixed into the view
- **After**: CloneMachineManager/index.tsx + styles.ts + columns.ts with dedicated components for the header stats, action toolbar, and assign-machines modal, plus fully themed styled-components

### ✅ ClusterTable (Dec 2025 - CLI Refactor)
- **Before**: 400+ lines with chevron rotation, hover states, and machine badges controlled via inline styles
- **After**: ClusterTable/index.tsx backed by styles.ts, columns.ts, menus.ts, and components/ for MachineCountBadge + ClusterMachines so expandable rows, menus, and actions stay modular

### ✅ PoolTable (Dec 2025 - CLI Refactor)
- **Before**: 293-line monolith with inline card/table styling and duplicated dropdown definitions
- **After**: PoolTable/index.tsx with styles.ts, columns.ts, menus.ts, and a ClusterPoolsCard subcomponent that renders themed cluster cards and tables without inline CSS

### ✅ ResourceFormWithVault (Dec 2025 - CLI Refactor)
- **Before**: 470+ line form with field rendering, import/export controls, and defaults banner defined inline alongside business logic
- **After**: ResourceFormWithVault/index.tsx orchestrates helpers in components/ + types.ts while styles.ts exposes full-width selects, size inputs, and import/export rows for a purely styled-components implementation

---

## Remaining Components

> **Identification criteria for components needing refactoring:**
> - ❌ Not using folder structure with `index.tsx`
> - ❌ Missing co-located `styles.ts` file
> - ❌ Contains hard-coded hex colors
> - ❌ Contains inline `style={{}}` attributes
> - ❌ Not using styled-components
> - ❌ File size > 300 lines

## Priority 1: High Violation Count (Critical)

### 1. MachineTable (1077 lines)
**Location:** `src/components/resources/MachineTable.tsx`

**Violations:**
- ❌ **16 hard-coded hex colors**
- ❌ **21 inline styles**
- ❌ No styled-components usage
- ❌ No `styles.ts` file

**Required Actions:**
1. Create folder structure: `MachineTable/index.tsx` and `MachineTable/styles.ts`
2. Move all inline styles to styled-components
3. Replace hex colors with theme tokens (CSS variables)
4. Extract table column configurations
5. Use styled Table wrapper instead of inline styles

---

### 2. MachineVaultStatusPanel (636 lines)
**Location:** `src/components/resources/MachineVaultStatusPanel.tsx`

**Violations:**
- ❌ **15 hard-coded hex colors**
- ❌ **60 inline styles** (highest count!)
- ❌ No `styles.ts` file

**Required Actions:**
1. Create folder structure: `MachineVaultStatusPanel/index.tsx` and `MachineVaultStatusPanel/styles.ts`
2. Replace all hard-coded colors with theme tokens
3. Create styled primitives for repeating layout patterns
4. Extract vault status components

**Example violations:**
```tsx
// ❌ Current
<CloudServerOutlined style={{ fontSize: 24, color: '#556b2f' }} />
<Tag color="#8FBC8F" icon={<AppstoreOutlined />}>
<Badge count={machine.queueCount} style={{ backgroundColor: '#52c41a' }} />

// ✅ Should be
<StyledCloudServerIcon />
<StyledTeamTag icon={<AppstoreOutlined />}>
<StyledQueueBadge count={machine.queueCount} />
```

---

### 3. RcloneImportWizard (569 lines)
**Location:** `src/components/resources/RcloneImportWizard.tsx`

**Violations:**
- ❌ **9 inline styles**
- ❌ No styled-components usage
- ❌ No `styles.ts` file

**Required Actions:**
1. Create folder structure
2. Extract wizard step components
3. Create styled primitives for wizard layout

---

### 4. TwoFactorSettings (531 lines)
**Location:** `src/components/settings/TwoFactorSettings.tsx`

**Violations:**
- ❌ **32 inline styles**
- ❌ No styled-components usage
- ❌ No `styles.ts` file

**Required Actions:**
1. Create folder structure
2. Extract QR code display component
3. Extract recovery codes component
4. Move all inline styles to styled-components

---

### 5. RepositoryDetailPanel (525 lines)
**Location:** `src/components/resources/RepositoryDetailPanel.tsx`

**Violations:**
- ❌ **9 hard-coded hex colors**
- ❌ **42 inline styles**
- ✅ Already imports from styles (partial refactor)

**Required Actions:**
1. Complete migration to folder structure
2. Replace remaining hex colors with theme tokens
3. Remove remaining inline styles
4. Consolidate styled-components in `styles.ts`

---

## Priority 2: Medium Violation Count

### 6. AuditPage (470 lines)
**Location:** `src/pages/audit/AuditPage.tsx`

**Violations:**
- ❌ **3 hex colors**
- ❌ **13 inline styles**
- ✅ Already imports from styles (partial refactor)

**Required Actions:**
- Complete styled-components migration
- Remove remaining hard-coded colors

---

### 7. CloneList (445 lines)
**Location:** `src/pages/distributedStorage/components/CloneList.tsx`

**Violations:**
- ❌ **3 hex colors**
- ❌ **9 inline styles**
- ❌ No `styles.ts` file

**Required Actions:**
1. Create a `CloneList/` folder with `index.tsx`, `styles.ts`, and move `CloneMachineList`/`MachineCountBadge` into a `components/` subfolder
2. Define styled containers for the empty state, machines section, action toolbar, and table wrapper to eliminate inline padding/margin/width styles
3. Replace the `#4a4a4a`, `#d9d9d9`, and `#fafafa` literals with semantic theme tokens declared in `styles.ts`
4. Extract the table column configuration and dropdown menu definitions into dedicated modules so `index.tsx` only handles data flow

---

### 8. UserSessionsTab (372 lines)
**Location:** `src/components/system/UserSessionsTab.tsx`

**Violations:**
- ❌ **14 inline styles**
- ❌ No `styles.ts` file

**Required Actions:**
1. Adopt the folder structure (`UserSessionsTab/index.tsx`, `styles.ts`) so layout styles sit next to the component
2. Replace the inline styles on summary cards, buttons, inputs, tags, and pagination text with styled components wired to the theme tokens
3. Create styled tag variants for "current session", "fork", child-count, and status badges instead of passing raw `color` props and inline radius rules
4. Extract the large table `columns` definition (and perhaps the summary-stat grid) into separate modules to shrink `index.tsx`

---

### 9. DistributedStorageDashboardWidget (270 lines)
**Location:** `src/components/dashboard/DistributedStorageDashboardWidget.tsx`

**Violations:**
- ❌ **1 hex color**
- ❌ **12 inline styles**
- ❌ No `styles.ts` file

**Required Actions:**
1. Restructure the widget into `DistributedStorageDashboardWidget/index.tsx` with a companion `styles.ts` (and subcomponents for assignment cards, summaries, and team list rows)
2. Replace every inline style block (card borders, padding, typography, list item boxes) with styled components that read theme spacing and color tokens
3. Swap the hard-coded `#fa8c16` clone color for a semantic token defined once inside `styles.ts`
4. Extract repeated fragments (`AssignmentCard`, `SummaryPanel`, `TeamBreakdownItem`) into their own files to keep `index.tsx` lean

---

### 10. VirtualFilterableMachineTable (231 lines)
**Location:** `src/features/distributed-storage/components/performance/VirtualFilterableMachineTable.tsx`

**Violations:**
- ❌ **12 inline styles**
- ❌ No `styles.ts` file

**Required Actions:**
1. Create the folder structure and add `styles.ts` so the container, toolbar, and status bar styling is centralized
2. Move inline styles for the wrapping `Space`, filter `Input`/`Select` widths, badge padding, and status copy into styled components that consume spacing tokens
3. Extract a `FilterControls` subcomponent (with `FilterOption` helpers) so `index.tsx` only handles filtering logic and virtualization props
4. Hoist the footer ("Showing X of Y machines") into a styled `StatusBar` component that can surface the "load more" hint without inline CSS

---

### 11. ResourceForm (174 lines)
**Location:** `src/components/forms/ResourceForm.tsx`

**Violations:**
- ❌ **3 inline styles**
- ❌ No `styles.ts` file

**Required Actions:**
1. Split the component into `ResourceForm/index.tsx`, `styles.ts`, and optional `types.ts` so the generic form definition is modular
2. Create styled components for the form wrapper, full-width selects, and button row to eliminate the inline styles on `Select`, `Form.Item`, and `Space`
3. Replace the `spacing('PAGE_CONTAINER')` usage with theme spacing tokens defined in `styles.ts`
4. Extract reusable field renderers (text/password/select) into helpers shared with `ResourceFormWithVault` to keep styling consistent

---

### 12. MachineAvailabilitySummary (166 lines)
**Location:** `src/pages/distributedStorage/components/MachineAvailabilitySummary.tsx`

**Violations:**
- ❌ **5 hex colors**
- ❌ **13 inline styles**
- ❌ No `styles.ts` file

**Required Actions:**
1. Add the folder structure with `MachineAvailabilitySummary/index.tsx`, `styles.ts`, and a small `types.ts` for the stats model
2. Move all inline styles on the cards, statistics, loading placeholder, and refresh icon into styled components (`SummaryGrid`, `SummaryCard`, `RefreshButton`)
3. Replace the hard-coded hex colors (#1890ff, #52c41a, #fa8c16, #722ed1, #666) with semantic theme tokens managed in `styles.ts`
4. Create styled wrappers for the loading state and percentage suffix so typography no longer embeds inline CSS

---

## Refactoring Process

> **For complete refactoring guidelines, see [REFACTORING.md](./REFACTORING.md)**

### Quick Reference

### Folder Structure Pattern
```
ComponentName/
├── index.tsx          # Main component file
├── styles.ts          # Styled-components
└── types.ts           # (optional) Type definitions
```

### styles.ts Template
```typescript
import styled from 'styled-components'
import { ComponentName } from 'antd'

export const StyledWrapper = styled.div`
  display: flex;
  gap: ${({ theme }) => theme.spacing.MD}px;
  background: ${({ theme }) => theme.colors.bgPrimary};
`

export const StyledAntComponent = styled(ComponentName)`
  && {
    // Ant Design overrides with theme tokens
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  }
`
```

### Color Replacement Guide
```typescript
// ❌ Hard-coded
color: '#556b2f'
backgroundColor: '#52c41a'
borderColor: '#8FBC8F'

// ✅ Theme tokens
color: var(--color-primary)
backgroundColor: var(--color-success)
borderColor: var(--color-border-primary)
```

### Inline Style Replacement
```tsx
// ❌ Before
<div style={{ display: 'flex', gap: '16px', padding: '12px' }}>

// ✅ After (styles.ts)
export const Container = styled.div`
  display: flex;
  gap: ${({ theme }) => theme.spacing.MD}px;
  padding: ${({ theme }) => theme.spacing.SM}px;
`

// Usage
<Container>
```

---

## Summary Statistics

- **Completed:** 7 components (PR #163 + Dec 2025 CLI refactors)
- **Remaining:** 12 components
- **Total lines remaining:** ~6,300 lines
- **Total hex colors:** ~70
- **Total inline styles:** ~300

### By Category
- **Components:** 10 files
- **Pages:** 1 file
- **Features:** 1 file

### By Priority
- **Priority 1 (Critical):** 5 files (2,700+ lines)
- **Priority 2 (Medium):** 7 files (3,600+ lines)

---

## Recommended Approach

1. **Start with Priority 1** - Highest impact components first
2. **Follow [REFACTORING.md](./REFACTORING.md)** - Step-by-step refactoring process
3. **One component at a time** - Ensure quality over speed
4. **Test after each refactor** - Verify in both light and dark themes
5. **Create PR per component** - Makes reviews easier
6. **Apply [STYLE.md](./STYLE.md) conventions** - Maintain styling consistency
7. **Update this file** - Mark completed items in "Recently Completed" section

---

## Success Criteria per Component

- ✅ Folder structure created (`ComponentName/index.tsx`, `styles.ts`)
- ✅ All styled-components imported from `./styles`
- ✅ Zero hard-coded hex colors (except in fallbacks with `||`)
- ✅ Zero inline `style={{}}` attributes
- ✅ All colors use theme tokens or CSS variables
- ✅ Build passes without TypeScript errors
- ✅ Component renders correctly in both light and dark themes
